"""
Phalidae v2 - Dashboard Page
System status, data coverage, active trades summary, best strategies per coin.
Includes: regime display, funding rate table, daily P&L tracker.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from db.engine import get_session
from db.models import (
    OHLCVData, TrackedSymbol, PaperTrade, StrategyVariant,
    StrategyPerformance, CoinConfig, Signal, FundingData,
    MarketRegimeRecord,
)
from sqlalchemy import func, text

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


def render():
    st.title("Dashboard")
    st.caption("Sistem durumu, veri kapsami ve performans ozeti")

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

        # --- Daily P&L Tracker ---
        _render_daily_pnl(session)

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
                    "Kaldırac": f"{config.leverage:.0f}x",
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
                    "Max Profit": f"{t.max_profit:+.1f}%",
                    "Max DD": f"{t.max_drawdown:+.1f}%",
                    "Rejim": REGIME_LABELS.get(t.regime_at_entry, "-"),
                    "Acilis": t.opened_at.strftime("%m-%d %H:%M") if t.opened_at else "-",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch")

    finally:
        session.close()


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

        # Drawdown warning bar
        if today_pnl_pct < -5:
            st.warning(f"Gunluk kayip: {today_pnl_pct:.1f}% - Drawdown limitine yaklasiliyor!")
        if today_pnl_pct < -10:
            st.error(f"Gunluk drawdown limiti asildi: {today_pnl_pct:.1f}% - Yeni trade'ler engellenecek")
    else:
        st.caption("Bugun kapanan islem yok.")


def _render_regime_map(session):
    """Show current regime for each active coin."""
    st.subheader("Piyasa Rejimleri")

    # Get latest regime for each symbol
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
        session.query(MarketRegimeRecord)
        .join(subq, and_(
            MarketRegimeRecord.symbol == subq.c.symbol,
            MarketRegimeRecord.timestamp == subq.c.max_ts,
        ))
        .all()
    )

    if regimes:
        # Display as colored chips
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

    # Get latest funding data for each symbol
    from sqlalchemy import and_

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
