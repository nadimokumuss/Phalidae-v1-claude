"""
Phalidae v2 - Dashboard Page
System status, data coverage, active trades summary, best strategies per coin.
Phase 1: Agent Health panel.
Phase 2: Portfolio overview.
Phase 4: Market news section.
Phase 5: Commentary header.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from db.engine import get_session
from db.models import (
    OHLCVData, TrackedSymbol, PaperTrade, StrategyVariant,
    StrategyPerformance, CoinConfig, Signal, FundingData,
    MarketRegimeRecord, AgentJob,
)
from sqlalchemy import func, text, and_
from commentary import generate_page_header

REGIME_COLORS = {
    "TRENDING_UP": "#26a69a",
    "TRENDING_DOWN": "#ef5350",
    "RANGING": "#ffca28",
    "HIGH_VOLATILITY": "#ff7043",
    "LOW_VOLATILITY": "#78909c",
    "BREAKOUT": "#42a5f5",
}

REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay",
    "HIGH_VOLATILITY": "Yuksek Vol.",
    "LOW_VOLATILITY": "Dusuk Vol.",
    "BREAKOUT": "Kirilim",
}

JOB_INTERVALS = {
    "collector": 5,
    "analyzer": 15,
    "trade_checker": 5,
    "optimizer": 360,
    "market_data": 15,
    "symbol_refresh": 1440,
    "news_collector": 15,
}


def render():
    generate_page_header("Dashboard")
    st.title("Dashboard")
    st.caption("Sistem durumu, veri kapsami ve performans ozeti")

    # --- Portfolio Overview (Phase 2) ---
    _render_portfolio_overview()

    # --- System Status ---
    col1, col2, col3, col4 = st.columns(4)

    session = get_session()
    try:
        total_candles = session.query(func.count(OHLCVData.id)).scalar() or 0
        active_symbols = session.query(TrackedSymbol).filter_by(is_active=True).count()
        total_variants = session.query(StrategyVariant).count()
        open_trades = session.query(PaperTrade).filter_by(status="OPEN").count()

        col1.metric("OHLCV Veri", f"{total_candles:,}")
        col2.metric("Aktif Coin", active_symbols)
        col3.metric("Strateji Varyant", total_variants)
        col4.metric("Acik Trade", open_trades)

        # DB size
        db_size_result = session.execute(text("SELECT pg_database_size(current_database())")).scalar()
        db_size_mb = (db_size_result or 0) / (1024 * 1024)

        col5, col6, col7, col8 = st.columns(4)
        total_signals = session.query(func.count(Signal.id)).scalar() or 0
        closed_trades = session.query(PaperTrade).filter(PaperTrade.status != "OPEN").count()
        total_pnl = session.query(func.sum(PaperTrade.pnl_usd)).filter(
            PaperTrade.status != "OPEN"
        ).scalar() or 0

        col5.metric("DB Boyutu", f"{db_size_mb:.1f} MB")
        col6.metric("Toplam Sinyal", total_signals)
        col7.metric("Kapali Trade", closed_trades)
        col8.metric("Toplam P&L", f"${total_pnl:+,.2f}")

        st.divider()

        # --- Agent Health Panel (Phase 1) ---
        _render_agent_health(session)

        st.divider()

        # --- Daily P&L Tracker ---
        _render_daily_pnl(session)

        st.divider()

        # --- Market News (Phase 4) ---
        _render_market_news()

        st.divider()

        # --- Coin Regime Map ---
        _render_regime_map(session)

        st.divider()

        # --- Funding Rate Table ---
        _render_funding_table(session)

        st.divider()

        # --- Data Coverage ---
        st.subheader("Veri Kapsami")
        symbols = (
            session.query(TrackedSymbol)
            .filter_by(is_active=True)
            .order_by(TrackedSymbol.rank)
            .limit(30)
            .all()
        )

        if symbols:
            rows = []
            for s in symbols:
                candle_count = session.query(func.count(OHLCVData.id)).filter_by(
                    symbol=s.symbol
                ).scalar() or 0
                earliest = session.query(func.min(OHLCVData.timestamp)).filter_by(
                    symbol=s.symbol
                ).scalar()
                latest = session.query(func.max(OHLCVData.timestamp)).filter_by(
                    symbol=s.symbol
                ).scalar()

                rows.append({
                    "Coin": s.symbol.replace("/USDT:USDT", ""),
                    "Rank": s.rank,
                    "Mum Sayisi": candle_count,
                    "Ilk Veri": earliest.strftime("%Y-%m-%d") if earliest else "-",
                    "Son Veri": latest.strftime("%Y-%m-%d %H:%M") if latest else "-",
                })

            st.dataframe(pd.DataFrame(rows), width="stretch", height=400)
        else:
            st.info("Henuz takip edilen coin yok. Collector ilk calistiginda otomatik eklenecek.")

        st.divider()

        # --- Best Strategies Per Coin ---
        st.subheader("Coin Bazli En Iyi Strateji")
        configs = (
            session.query(CoinConfig, StrategyVariant, StrategyPerformance)
            .join(StrategyVariant, CoinConfig.best_strategy_id == StrategyVariant.id)
            .outerjoin(
                StrategyPerformance,
                (StrategyPerformance.strategy_variant_id == StrategyVariant.id) &
                (StrategyPerformance.symbol == CoinConfig.symbol)
            )
            .all()
        )

        if configs:
            rows = []
            for config, variant, perf in configs:
                rows.append({
                    "Coin": config.symbol.replace("/USDT:USDT", ""),
                    "Strateji": variant.name[:40],
                    "Kaldirac": f"{config.leverage:.0f}x",
                    "Auto": "Evet" if config.auto_trade else "Hayir",
                    "Win Rate": f"{(perf.win_rate * 100):.1f}%" if perf else "-",
                    "Profit Factor": f"{perf.profit_factor:.2f}" if perf else "-",
                    "Sharpe": f"{perf.sharpe_ratio:.2f}" if perf else "-",
                    "Max DD": f"{perf.max_drawdown:.1f}%" if perf else "-",
                    "Skor": f"{perf.composite_score:.3f}" if perf else "-",
                    "Paper WR": f"{(perf.paper_win_rate * 100):.1f}%" if perf and perf.paper_total > 0 else "-",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch")
        else:
            st.info("Henuz strateji optimizasyonu yapilmadi.")

        # --- Open Trades Summary ---
        if open_trades > 0:
            st.divider()
            st.subheader("Acik Islemler")
            trades = session.query(PaperTrade).filter_by(status="OPEN").all()
            rows = []
            for t in trades:
                rows.append({
                    "Coin": t.symbol.replace("/USDT:USDT", ""),
                    "Yon": t.bias,
                    "Giris": f"${t.entry_price:,.2f}",
                    "TP": f"${t.tp_price:,.2f}" if t.tp_price else "-",
                    "SL": f"${t.sl_price:,.2f}" if t.sl_price else "-",
                    "Trail SL": f"${t.trailing_stop_price:,.2f}" if t.trailing_stop_price else "-",
                    "Boyut": f"${t.position_size_usd:,.0f}",
                    "Max Profit": f"{t.max_profit:+.1f}%",
                    "Max DD": f"{t.max_drawdown:+.1f}%",
                    "Partial TP": "Evet" if t.partial_tp_taken else "Hayir",
                    "Rejim": REGIME_LABELS.get(t.regime_at_entry, "-"),
                    "Acilis": t.opened_at.strftime("%m-%d %H:%M") if t.opened_at else "-",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch")

    finally:
        session.close()


def _render_portfolio_overview():
    """Phase 2: Portfolio metrics at top of dashboard."""
    try:
        from paper_trader.portfolio import get_portfolio_summary
        ps = get_portfolio_summary()

        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Portfolio Degeri", f"${ps['equity']:,.2f}",
                   delta=f"{ps['total_pnl_pct']:+.1f}%")
        c2.metric("Nakit", f"${ps['cash']:,.2f}")
        c3.metric("Exposure", f"{ps['exposure_pct']:.1f}%")
        c4.metric("Gunluk P&L", f"${ps['daily_pnl']:+,.2f}")
        c5.metric("Acik Pozisyon", ps['open_positions'])
        st.divider()
    except Exception:
        pass


def _render_agent_health(session):
    """Phase 1: Agent health monitoring panel."""
    st.subheader("Agent Durumu")

    job_names = ["collector", "analyzer", "trade_checker", "optimizer", "market_data", "symbol_refresh", "news_collector"]
    job_labels = {
        "collector": "Collector",
        "analyzer": "Analyzer",
        "trade_checker": "Trade Check",
        "optimizer": "Optimizer",
        "market_data": "Market Data",
        "symbol_refresh": "Sym Refresh",
        "news_collector": "News",
    }

    now = datetime.utcnow()
    rows = []

    for job_name in job_names:
        # Get last 3 runs
        recent = (
            session.query(AgentJob)
            .filter_by(job_name=job_name)
            .order_by(AgentJob.started_at.desc())
            .limit(3)
            .all()
        )

        if not recent:
            rows.append({
                "Job": job_labels.get(job_name, job_name),
                "Durum": "Bekleniyor",
                "Son Calisma": "-",
                "Sure": "-",
                "Kayit": "-",
            })
            continue

        last = recent[0]
        # Status color
        interval_min = JOB_INTERVALS.get(job_name, 60)
        if last.completed_at:
            age_min = (now - last.completed_at).total_seconds() / 60
        else:
            age_min = (now - last.started_at).total_seconds() / 60

        if last.status == "FAILED":
            status = "HATA"
        elif last.status == "RUNNING":
            status = "Calisiyor"
        elif age_min > interval_min * 3:
            status = "Eski"
        else:
            status = "Aktif"

        # Age display
        if last.completed_at:
            delta = now - last.completed_at
            if delta.total_seconds() < 3600:
                age_str = f"{delta.total_seconds() / 60:.0f} dk once"
            else:
                age_str = f"{delta.total_seconds() / 3600:.1f} sa once"
        else:
            age_str = "Calisir"

        rows.append({
            "Job": job_labels.get(job_name, job_name),
            "Durum": status,
            "Son Calisma": age_str,
            "Sure": f"{last.duration_sec:.1f}s" if last.duration_sec else "-",
            "Kayit": str(last.records_affected or 0),
        })

    df = pd.DataFrame(rows)

    # Color the status column
    def _color_status(val):
        if val == "Aktif":
            return "color: #26a69a"
        elif val == "HATA":
            return "color: #ef5350; font-weight: bold"
        elif val == "Eski":
            return "color: #ff7043"
        elif val == "Calisiyor":
            return "color: #42a5f5"
        return "color: #ffca28"

    styled = df.style.map(_color_status, subset=["Durum"])
    st.dataframe(styled, width="stretch", height=280)

    # Summary stats
    last_24h = now - timedelta(hours=24)
    success_count = session.query(func.count(AgentJob.id)).filter(
        AgentJob.status == "SUCCESS",
        AgentJob.started_at >= last_24h,
    ).scalar() or 0
    fail_count = session.query(func.count(AgentJob.id)).filter(
        AgentJob.status == "FAILED",
        AgentJob.started_at >= last_24h,
    ).scalar() or 0

    st.caption(f"Son 24 saat: {success_count} basarili, {fail_count} hatali")


def _render_daily_pnl(session):
    """Show today's P&L with drawdown warning."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    today_trades = (
        session.query(PaperTrade)
        .filter(
            PaperTrade.status != "OPEN",
            PaperTrade.closed_at >= today_start,
        )
        .all()
    )

    st.subheader("Gunluk P&L")

    if today_trades:
        today_pnl_usd = sum(t.pnl_usd for t in today_trades)
        today_pnl_pct = sum(t.pnl_percent for t in today_trades)
        today_wins = sum(1 for t in today_trades if t.pnl_usd > 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gunluk P&L", f"${today_pnl_usd:+,.2f}")
        c2.metric("Gunluk %", f"{today_pnl_pct:+.1f}%")
        c3.metric("Bugun Islem", len(today_trades))
        c4.metric("Bugun Win", today_wins)

        if today_pnl_pct < -5:
            st.warning(f"Gunluk kayip: {today_pnl_pct:.1f}% - Drawdown limitine yaklasiliyor!")
        if today_pnl_pct < -10:
            st.error(f"Gunluk drawdown limiti asildi: {today_pnl_pct:.1f}% - Yeni trade'ler engellenecek")
    else:
        st.caption("Bugun kapanan islem yok.")


def _render_market_news():
    """Phase 4: Show today's market news."""
    try:
        from worker.news_collector import get_todays_events
        events = get_todays_events(limit=10)
    except (ImportError, Exception):
        events = []

    st.subheader("Piyasa Haberleri")

    if not events:
        st.caption("Haber verisi henuz mevcut degil. CRYPTOPANIC_API_KEY ayarlandiginda gorunecek.")
        return

    for e in events:
        sentiment_icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(e["sentiment"], "⚪")
        symbols_str = ", ".join(e["symbols"][:5]) if e["symbols"] else ""
        important = " ⭐" if e["is_important"] else ""
        st.caption(f"{sentiment_icon} {e['published_at']} | {symbols_str} | {e['title'][:100]}{important}")


def _render_regime_map(session):
    """Show current regime for each active coin."""
    st.subheader("Piyasa Rejimleri")

    subq = (
        session.query(
            MarketRegimeRecord.symbol,
            func.max(MarketRegimeRecord.timestamp).label("max_ts")
        )
        .group_by(MarketRegimeRecord.symbol)
        .subquery()
    )

    regimes = (
        session.query(MarketRegimeRecord)
        .join(subq, and_(
            MarketRegimeRecord.symbol == subq.c.symbol,
            MarketRegimeRecord.timestamp == subq.c.max_ts,
        ))
        .all()
    )

    if regimes:
        cols = st.columns(6)
        for i, r in enumerate(regimes):
            col = cols[i % 6]
            clean_sym = r.symbol.replace("/USDT:USDT", "")
            label = REGIME_LABELS.get(r.regime_label, r.regime_label)
            color = REGIME_COLORS.get(r.regime_label, "#999")
            col.markdown(
                f'<span style="background-color:{color};color:white;padding:2px 8px;'
                f'border-radius:10px;font-size:12px;">{clean_sym}: {label}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Rejim verisi henuz mevcut degil. Market Data Collector ilk calistiginda gorunecek.")


def _render_funding_table(session):
    """Show latest funding rates for tracked symbols."""
    st.subheader("Funding Rate & Open Interest")

    subq = (
        session.query(
            FundingData.symbol,
            func.max(FundingData.timestamp).label("max_ts")
        )
        .group_by(FundingData.symbol)
        .subquery()
    )

    funding_data = (
        session.query(FundingData)
        .join(subq, and_(
            FundingData.symbol == subq.c.symbol,
            FundingData.timestamp == subq.c.max_ts,
        ))
        .order_by(FundingData.symbol)
        .all()
    )

    if funding_data:
        rows = []
        for f in funding_data:
            rows.append({
                "Coin": f.symbol.replace("/USDT:USDT", ""),
                "Funding Rate": f"{f.funding_rate * 100:.4f}%" if f.funding_rate else "-",
                "Open Interest": f"${f.open_interest:,.0f}" if f.open_interest else "-",
                "Spread": f"{f.spread_pct:.4f}%" if f.spread_pct else "-",
                "Guncelleme": f.timestamp.strftime("%H:%M") if f.timestamp else "-",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", height=300)
    else:
        st.caption("Funding verisi henuz mevcut degil.")
