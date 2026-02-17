"""
Phalidae v2 - Always-On Commentary Engine (Phase 5)
Generates market commentary for each page.
"""

import logging
from datetime import datetime, timedelta

import streamlit as st
from sqlalchemy import func

from db.engine import get_session
from db.models import (
    PaperTrade, Signal, TrackedSymbol, MarketRegimeRecord, AgentJob,
)

logger = logging.getLogger("phalidae.commentary")

REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay",
    "HIGH_VOLATILITY": "Yuksek Vol.",
    "LOW_VOLATILITY": "Dusuk Vol.",
    "BREAKOUT": "Kirilim",
}


def generate_market_commentary(symbol: str = None) -> str:
    """
    Generate market commentary.
    If symbol is None: general market overview.
    If symbol is provided: coin-specific commentary.
    """
    session = get_session()
    try:
        if symbol:
            return _coin_commentary(session, symbol)
        else:
            return _general_commentary(session)
    except Exception as e:
        return f"Yorum olusturulamadi: {e}"
    finally:
        session.close()


def _general_commentary(session) -> str:
    """General market overview."""
    parts = []

    # Regime distribution
    from sqlalchemy import and_
    subq = (
        session.query(
            MarketRegimeRecord.symbol,
            func.max(MarketRegimeRecord.timestamp).label("max_ts")
        )
        .group_by(MarketRegimeRecord.symbol)
        .subquery()
    )
    regimes = (
        session.query(MarketRegimeRecord.regime_label, func.count().label("cnt"))
        .join(subq, and_(
            MarketRegimeRecord.symbol == subq.c.symbol,
            MarketRegimeRecord.timestamp == subq.c.max_ts,
        ))
        .group_by(MarketRegimeRecord.regime_label)
        .all()
    )

    if regimes:
        total = sum(r.cnt for r in regimes)
        dominant = max(regimes, key=lambda r: r.cnt)
        label = REGIME_LABELS.get(dominant.regime_label, dominant.regime_label)
        pct = dominant.cnt / total * 100 if total > 0 else 0
        parts.append(f"Piyasa: {total} coin'in %{pct:.0f}'i {label} rejiminde")

    # Today's signals
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    signal_count = session.query(func.count(Signal.id)).filter(
        Signal.created_at >= today_start
    ).scalar() or 0

    long_count = session.query(func.count(Signal.id)).filter(
        Signal.created_at >= today_start, Signal.bias == "LONG"
    ).scalar() or 0

    if signal_count > 0:
        parts.append(f"Bugun {signal_count} sinyal ({long_count} LONG, {signal_count - long_count} SHORT)")

    # Portfolio
    try:
        from paper_trader.portfolio import get_portfolio_summary
        ps = get_portfolio_summary()
        parts.append(f"Portfolio: ${ps['equity']:,.0f} ({ps['total_pnl_pct']:+.1f}%)")
    except Exception:
        pass

    # Warnings
    last_24h = datetime.utcnow() - timedelta(hours=24)
    failed_jobs = session.query(func.count(AgentJob.id)).filter(
        AgentJob.status == "FAILED",
        AgentJob.started_at >= last_24h,
    ).scalar() or 0

    if failed_jobs > 0:
        parts.append(f"Uyari: Son 24 saatte {failed_jobs} basarisiz job")

    return " | ".join(parts) if parts else "Sistem baslatiliyor..."


def _coin_commentary(session, symbol: str) -> str:
    """Coin-specific commentary."""
    clean = symbol.replace("/USDT:USDT", "")
    parts = []

    # Latest regime
    regime = (
        session.query(MarketRegimeRecord)
        .filter_by(symbol=symbol)
        .order_by(MarketRegimeRecord.timestamp.desc())
        .first()
    )
    if regime:
        label = REGIME_LABELS.get(regime.regime_label, regime.regime_label)
        parts.append(f"{clean}: {label}")
        if regime.adx_value:
            parts.append(f"ADX={regime.adx_value:.0f}")

    # Latest signal
    latest_signal = (
        session.query(Signal)
        .filter_by(symbol=symbol)
        .order_by(Signal.created_at.desc())
        .first()
    )
    if latest_signal:
        age = datetime.utcnow() - latest_signal.created_at
        hours = age.total_seconds() / 3600
        conf = f" (guven: {latest_signal.confidence_score:.0f}/100)" if latest_signal.confidence_score else ""
        parts.append(f"Son sinyal: {hours:.0f} saat once {latest_signal.bias}{conf}")

    # Open trade
    open_trade = session.query(PaperTrade).filter_by(symbol=symbol, status="OPEN").first()
    if open_trade:
        parts.append(f"Acik trade: {open_trade.bias} (max kar: {open_trade.max_profit:+.1f}%)")

    return " | ".join(parts) if parts else f"{clean}: Veri bekleniyor..."


def generate_page_header(page_name: str):
    """
    Render a Streamlit page header with last update time and market summary.
    Call at the top of each page's render() function.
    """
    now = datetime.utcnow()

    commentary = generate_market_commentary()

    # Compact header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(commentary)
    with col2:
        st.caption(f"Son guncelleme: {now.strftime('%H:%M')} UTC")

    # Check for warnings
    session = get_session()
    try:
        # High drawdown warning
        try:
            from paper_trader.portfolio import get_portfolio_summary
            ps = get_portfolio_summary()
            if ps["total_pnl_pct"] < -10:
                st.error(f"Yuksek drawdown: {ps['total_pnl_pct']:.1f}%")
            elif ps["daily_pnl"] < -30:
                st.warning(f"Gunluk kayip: ${ps['daily_pnl']:+.2f}")
        except Exception:
            pass

        # Stale agent warning
        last_hour = now - timedelta(hours=1)
        recent_collector = session.query(AgentJob).filter(
            AgentJob.job_name == "collector",
            AgentJob.status == "SUCCESS",
            AgentJob.completed_at >= last_hour,
        ).first()

        if recent_collector is None:
            last_collector = session.query(AgentJob).filter(
                AgentJob.job_name == "collector",
            ).order_by(AgentJob.completed_at.desc()).first()
            if last_collector and last_collector.completed_at:
                st.warning(f"Collector son calistigi zaman: {last_collector.completed_at.strftime('%H:%M')} UTC")
    except Exception:
        pass
    finally:
        session.close()
