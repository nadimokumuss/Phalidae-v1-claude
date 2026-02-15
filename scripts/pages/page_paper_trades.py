"""
Phalidae v2 - Paper Trades Page
Open/closed trades, equity curve, trade details with P&L timeline.
Includes: MFE/MAE bars, trailing stop display, regime badge, enhanced reasoning.
"""

import json
import streamlit as st
import pandas as pd

from db.engine import get_session
from db.models import PaperTrade, TradeSnapshot, Signal
from sqlalchemy import func
from paper_trader.position import calculate_pnl

REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay",
    "HIGH_VOLATILITY": "Yuksek Vol.",
    "LOW_VOLATILITY": "Dusuk Vol.",
    "BREAKOUT": "Kirilim",
}


def render():
    st.title("Paper Trades")

    session = get_session()
    try:
        _render_summary(session)
        st.divider()

        tab_open, tab_closed, tab_detail = st.tabs([
            "Acik Islemler", "Kapali Islemler", "Islem Detayi"
        ])

        with tab_open:
            _render_open_trades(session)
        with tab_closed:
            _render_closed_trades(session)
        with tab_detail:
            _render_trade_detail(session)

    finally:
        session.close()


def _render_summary(session):
    """Overall P&L summary."""
    closed = session.query(PaperTrade).filter(PaperTrade.status != "OPEN").all()
    open_trades = session.query(PaperTrade).filter_by(status="OPEN").all()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Acik", len(open_trades))
    c2.metric("Kapali", len(closed))

    if closed:
        wins = sum(1 for t in closed if t.pnl_usd > 0)
        wr = wins / len(closed) if closed else 0
        total_pnl = sum(t.pnl_usd for t in closed)
        tp_hits = sum(1 for t in closed if t.status == "TP_HIT")
        sl_hits = sum(1 for t in closed if t.status == "SL_HIT")

        c3.metric("Win Rate", f"{wr * 100:.1f}%")
        c4.metric("Toplam P&L", f"${total_pnl:+,.2f}")
        c5.metric("TP Hit", tp_hits)
        c6.metric("SL Hit", sl_hits)

        # Exit reason breakdown
        trail_stops = sum(1 for t in closed if t.status == "TRAILING_STOP")
        time_expired = sum(1 for t in closed if t.status == "TIME_EXPIRED")
        if trail_stops > 0 or time_expired > 0:
            c7, c8 = st.columns(2)
            c7.metric("Trailing Stop", trail_stops)
            c8.metric("Time Expired", time_expired)

        # Equity curve
        if len(closed) > 1:
            _render_equity_curve(closed)
    else:
        c3.metric("Win Rate", "-")
        c4.metric("Toplam P&L", "$0")
        c5.metric("TP Hit", 0)
        c6.metric("SL Hit", 0)


def _render_equity_curve(closed_trades: list):
    """Render equity curve from closed trades."""
    from charting import plot_equity_curve

    sorted_trades = sorted(closed_trades, key=lambda t: t.closed_at or t.opened_at)
    cumulative = []
    running = 0
    for t in sorted_trades:
        running += t.pnl_usd
        cumulative.append({
            "date": t.closed_at or t.opened_at,
            "equity": running,
        })

    if cumulative:
        fig = plot_equity_curve(cumulative)
        st.plotly_chart(fig, width="stretch")


def _render_open_trades(session):
    """Show currently open trades with trailing stop info."""
    trades = session.query(PaperTrade).filter_by(status="OPEN").order_by(PaperTrade.opened_at.desc()).all()

    if not trades:
        st.info("Acik islem yok.")
        return

    rows = []
    for t in trades:
        rows.append({
            "ID": t.id,
            "Coin": t.symbol.replace("/USDT:USDT", ""),
            "Yon": t.bias,
            "Giris": f"${t.entry_price:,.2f}",
            "TP": f"${t.tp_price:,.2f}" if t.tp_price else "-",
            "SL": f"${t.sl_price:,.2f}" if t.sl_price else "-",
            "Trail SL": f"${t.trailing_stop_price:,.2f}" if t.trailing_stop_price else "-",
            "Kaldırac": f"{t.leverage:.0f}x",
            "MFE": f"{(t.mfe_pct or 0):+.1f}%",
            "MAE": f"{(t.mae_pct or 0):+.1f}%",
            "Rejim": REGIME_LABELS.get(t.regime_at_entry, "-"),
            "Acilis": t.opened_at.strftime("%m-%d %H:%M") if t.opened_at else "-",
        })

    st.dataframe(pd.DataFrame(rows), width="stretch")


def _render_closed_trades(session):
    """Show closed trades with exit reason and MFE/MAE."""
    trades = (
        session.query(PaperTrade)
        .filter(PaperTrade.status != "OPEN")
        .order_by(PaperTrade.closed_at.desc())
        .limit(200)
        .all()
    )

    if not trades:
        st.info("Kapali islem yok.")
        return

    rows = []
    for t in trades:
        duration = ""
        if t.opened_at and t.closed_at:
            delta = t.closed_at - t.opened_at
            hours = delta.total_seconds() / 3600
            if hours >= 24:
                duration = f"{hours/24:.1f}g"
            else:
                duration = f"{hours:.1f}s"

        rows.append({
            "ID": t.id,
            "Coin": t.symbol.replace("/USDT:USDT", ""),
            "Yon": t.bias,
            "Sonuc": t.exit_reason or t.status,
            "Giris": f"${t.entry_price:,.2f}",
            "Cikis": f"${t.exit_price:,.2f}" if t.exit_price else "-",
            "P&L $": f"${t.pnl_usd:+,.2f}",
            "P&L %": f"{t.pnl_percent:+.1f}%",
            "MFE": f"{(t.mfe_pct or 0):+.1f}%",
            "MAE": f"{(t.mae_pct or 0):+.1f}%",
            "Rejim": REGIME_LABELS.get(t.regime_at_entry, "-"),
            "Sure": duration,
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", height=500)


def _render_trade_detail(session):
    """Detailed view of a single trade with MFE/MAE visualization."""
    trades = (
        session.query(PaperTrade)
        .order_by(PaperTrade.opened_at.desc())
        .limit(50)
        .all()
    )

    if not trades:
        st.info("Henuz islem yok.")
        return

    sel = st.selectbox(
        "Islem sec:",
        range(len(trades)),
        format_func=lambda i: (
            f"#{trades[i].id} {trades[i].symbol.replace('/USDT:USDT', '')} "
            f"{trades[i].bias} {trades[i].status} "
            f"P&L: {trades[i].pnl_percent:+.1f}%"
        ),
    )
    trade = trades[sel]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Yon", trade.bias)
    c2.metric("Giris", f"${trade.entry_price:,.2f}")
    c3.metric("Durum", trade.exit_reason or trade.status)
    c4.metric("P&L", f"${trade.pnl_usd:+,.2f}" if trade.status != "OPEN" else "Acik")

    # MFE/MAE visual
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("MFE (Max Kar)", f"{(trade.mfe_pct or 0):+.1f}%")
    c6.metric("MAE (Max Kayip)", f"{(trade.mae_pct or 0):+.1f}%")
    c7.metric("Rejim", REGIME_LABELS.get(trade.regime_at_entry, "-"))
    c8.metric("Kaldırac", f"{trade.leverage:.0f}x")

    # Trailing stop info
    if trade.trailing_stop_price:
        st.caption(f"Trailing Stop: ${trade.trailing_stop_price:,.2f} | Orijinal SL: ${trade.sl_price:,.2f}" if trade.sl_price else "")

    # MFE/MAE progress bars
    if trade.mfe_pct and trade.mfe_pct > 0:
        mfe_norm = min(trade.mfe_pct / 50, 1.0)  # Normalize to 50% max
        st.progress(mfe_norm, text=f"MFE: {trade.mfe_pct:+.1f}%")
    if trade.mae_pct and trade.mae_pct < 0:
        mae_norm = min(abs(trade.mae_pct) / 50, 1.0)
        st.progress(mae_norm, text=f"MAE: {trade.mae_pct:+.1f}%")

    if trade.reasoning:
        with st.expander("Islem Nedeni (Detayli)", expanded=True):
            st.text(trade.reasoning)

    # P&L timeline from snapshots
    snapshots = (
        session.query(TradeSnapshot)
        .filter_by(paper_trade_id=trade.id)
        .order_by(TradeSnapshot.timestamp)
        .all()
    )

    if snapshots:
        from charting import plot_pnl_timeline
        snap_data = [
            {"timestamp": s.timestamp, "pnl": s.unrealized_pnl}
            for s in snapshots
        ]
        fig = plot_pnl_timeline(snap_data, trade.symbol)
        st.plotly_chart(fig, width="stretch")
    else:
        st.caption("Bu islem icin snapshot verisi yok.")
