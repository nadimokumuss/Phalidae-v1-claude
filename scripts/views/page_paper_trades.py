"""
Phalidae v2 - Paper Trades Page (Phase 2 + 5)
Open/closed trades, equity curve, trade details with P&L timeline.
Includes: MFE/MAE bars, trailing stop display, regime badge, enhanced reasoning.
Optimized: aggregation queries, cached open trades, cached equity curve.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from db.engine import get_session
from db.models import PaperTrade, TradeSnapshot, Signal, TradeManagementLog
from sqlalchemy import func
from paper_trader.position import calculate_pnl
from commentary import generate_page_header
from views.cache import (
    get_trade_summary_cached,
    get_open_trades_cached,
    get_closed_trades_cached,
    get_portfolio_snapshots_cached,
)

REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay",
    "HIGH_VOLATILITY": "Yuksek Vol.",
    "LOW_VOLATILITY": "Dusuk Vol.",
    "BREAKOUT": "Kirilim",
}


def render():
    generate_page_header("Paper Trades")
    st.title("Paper Trades")

    _render_summary()
    st.divider()

    tab_open, tab_closed, tab_detail, tab_equity = st.tabs([
        "Acik Islemler", "Kapali Islemler", "Islem Detayi", "Portfolio Equity"
    ])

    with tab_open:
        _render_open_trades()
    with tab_closed:
        _render_closed_trades()
    with tab_detail:
        _render_trade_detail()
    with tab_equity:
        _render_portfolio_equity()


def _render_summary():
    """Overall P&L summary — aggregation query, no row loading."""
    summary = get_trade_summary_cached()

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Acik", summary["open_count"])
    c2.metric("Kapali", summary["closed_count"])

    if summary["closed_count"] > 0:
        c3.metric("Win Rate", f"{summary['win_rate'] * 100:.1f}%")
        c4.metric("Toplam P&L", f"${summary['total_pnl']:+,.2f}")
        c5.metric("TP Hit", summary["tp_hits"])
        c6.metric("SL Hit", summary["sl_hits"])

        if summary["trail_stops"] > 0 or summary["time_expired"] > 0 or summary["partial_tps"] > 0:
            c7, c8, c9 = st.columns(3)
            c7.metric("Trailing Stop", summary["trail_stops"])
            c8.metric("Partial TP", summary["partial_tps"])
            c9.metric("Time Expired", summary["time_expired"])

        # Equity curve from closed trades (cached)
        if summary["closed_count"] > 1:
            closed = get_closed_trades_cached()
            _render_equity_curve(closed)
    else:
        c3.metric("Win Rate", "-")
        c4.metric("Toplam P&L", "$0")
        c5.metric("TP Hit", 0)
        c6.metric("SL Hit", 0)


def _render_equity_curve(closed_trades: list[dict]):
    """Render equity curve from closed trades."""
    from charting import plot_equity_curve

    sorted_trades = sorted(closed_trades, key=lambda t: t["closed_at"] or t["opened_at"] or "")
    cumulative = []
    running = 0
    for t in sorted_trades:
        running += t["pnl_usd"]
        date_str = t["closed_at"] or t["opened_at"]
        if date_str:
            try:
                date = datetime.fromisoformat(date_str)
            except (ValueError, TypeError):
                continue
        else:
            continue
        cumulative.append({
            "date": date,
            "equity": running,
        })

    if cumulative:
        fig = plot_equity_curve(cumulative)
        st.plotly_chart(fig, width="stretch")


def _render_open_trades():
    """Show currently open trades — cached."""
    trades = get_open_trades_cached()

    if not trades:
        st.info("Acik islem yok.")
        return

    rows = []
    for t in trades:
        rows.append({
            "ID": t["id"],
            "Coin": t["symbol"].replace("/USDT:USDT", ""),
            "Yon": t["bias"],
            "Giris": f"${t['entry_price']:,.2f}",
            "TP": f"${t['tp_price']:,.2f}" if t["tp_price"] else "-",
            "SL": f"${t['sl_price']:,.2f}" if t["sl_price"] else "-",
            "Trail SL": f"${t['trailing_stop_price']:,.2f}" if t["trailing_stop_price"] else "-",
            "Partial TP": "Alindi" if t["partial_tp_taken"] else "Bekliyor",
            "Boyut": f"${t['position_size_usd']:,.0f}" if t["position_size_usd"] else "-",
            "Kaldırac": f"{t['leverage']:.0f}x",
            "MFE": f"{t['mfe_pct']:+.1f}%",
            "MAE": f"{t['mae_pct']:+.1f}%",
            "Rejim": REGIME_LABELS.get(t["regime_at_entry"], "-"),
            "Acilis": t["opened_at"],
        })

    st.dataframe(pd.DataFrame(rows), width="stretch")


def _render_closed_trades():
    """Show closed trades — cached."""
    trades = get_closed_trades_cached()

    if not trades:
        st.info("Kapali islem yok.")
        return

    rows = []
    for t in trades:
        rows.append({
            "ID": t["id"],
            "Coin": t["symbol"].replace("/USDT:USDT", ""),
            "Yon": t["bias"],
            "Sonuc": t["exit_reason"] or t["status"],
            "Giris": f"${t['entry_price']:,.2f}",
            "Cikis": f"${t['exit_price']:,.2f}" if t["exit_price"] else "-",
            "P&L $": f"${t['pnl_usd']:+,.2f}",
            "P&L %": f"{t['pnl_percent']:+.1f}%",
            "Boyut": f"${t['position_size_usd']:,.0f}" if t["position_size_usd"] else "-",
            "MFE": f"{t['mfe_pct']:+.1f}%",
            "MAE": f"{t['mae_pct']:+.1f}%",
            "Rejim": REGIME_LABELS.get(t["regime_at_entry"], "-"),
            "Sure": t["duration"],
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, width="stretch", height=500)


def _render_trade_detail():
    """Detailed view of a single trade — not cached (user selection dependent)."""
    session = get_session()
    try:
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

        # MFE/MAE + position info
        c5, c6, c7, c8 = st.columns(4)
        c5.metric("MFE (Max Kar)", f"{(trade.mfe_pct or 0):+.1f}%")
        c6.metric("MAE (Max Kayip)", f"{(trade.mae_pct or 0):+.1f}%")
        c7.metric("Rejim", REGIME_LABELS.get(trade.regime_at_entry, "-"))
        c8.metric("Kaldırac", f"{trade.leverage:.0f}x")

        c9, c10, c11, c12 = st.columns(4)
        c9.metric("Pozisyon", f"${trade.position_size_usd:,.0f}" if trade.position_size_usd else "-")
        c10.metric("Risk %", f"{trade.risk_pct:.1f}%" if trade.risk_pct else "-")
        c11.metric("Partial TP", "Alindi" if trade.partial_tp_taken else "Hayir")
        partial_pnl = trade.partial_tp_pnl or 0
        c12.metric("Partial P&L", f"${partial_pnl:+,.2f}" if partial_pnl != 0 else "-")

        # TP levels display
        if trade.partial_tp_price or trade.tp2_price or trade.tp3_price:
            st.caption(
                f"TP1: ${trade.partial_tp_price:,.2f}" if trade.partial_tp_price else "" +
                (f" | TP2: ${trade.tp2_price:,.2f}" if trade.tp2_price else "") +
                (f" | TP3: ${trade.tp3_price:,.2f}" if trade.tp3_price else "")
            )

        # Trailing stop info
        if trade.trailing_stop_price:
            st.caption(f"Trailing Stop: ${trade.trailing_stop_price:,.2f} | Orijinal SL: ${trade.sl_price:,.2f}" if trade.sl_price else "")

        # MFE/MAE progress bars
        if trade.mfe_pct and trade.mfe_pct > 0:
            mfe_norm = min(trade.mfe_pct / 50, 1.0)
            st.progress(mfe_norm, text=f"MFE: {trade.mfe_pct:+.1f}%")
        if trade.mae_pct and trade.mae_pct < 0:
            mae_norm = min(abs(trade.mae_pct) / 50, 1.0)
            st.progress(mae_norm, text=f"MAE: {trade.mae_pct:+.1f}%")

        if trade.reasoning:
            with st.expander("Islem Nedeni (Detayli)", expanded=True):
                st.text(trade.reasoning)

        # Trade Management Timeline
        _render_management_timeline(session, trade.id)

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

    finally:
        session.close()


def _render_management_timeline(session, trade_id: int):
    """Show trade management log entries as a timeline."""
    logs = (
        session.query(TradeManagementLog)
        .filter_by(paper_trade_id=trade_id)
        .order_by(TradeManagementLog.timestamp)
        .all()
    )

    if not logs:
        return

    with st.expander(f"Yonetim Gecmisi ({len(logs)} olay)", expanded=False):
        event_labels = {
            "BE_MOVED": "Break-Even",
            "PARTIAL_TP": "Kismi Kar Al",
            "TP2_HIT": "TP2 Ulasildi",
            "TRAIL_UPDATED": "Trailing Guncellendi",
            "SL_TIGHTENED": "SL Daraltildi",
        }

        rows = []
        for log in logs:
            rows.append({
                "Zaman": log.timestamp.strftime("%m-%d %H:%M") if log.timestamp else "-",
                "Olay": event_labels.get(log.event_type, log.event_type),
                "Eski": f"${log.old_value:,.2f}" if log.old_value else "-",
                "Yeni": f"${log.new_value:,.2f}" if log.new_value else "-",
                "Fiyat": f"${log.current_price:,.2f}" if log.current_price else "-",
                "P&L %": f"{log.current_pnl_pct:+.1f}%" if log.current_pnl_pct else "-",
                "Neden": log.reason or "-",
            })

        st.dataframe(pd.DataFrame(rows), width="stretch")


def _render_portfolio_equity():
    """Portfolio equity curve — cached snapshots."""
    snapshots = get_portfolio_snapshots_cached()

    if not snapshots:
        st.info("Henuz portfolio snapshot verisi yok. Sistem calismaya basladiktan sonra burada gorunecek.")
        return

    st.subheader("Portfolio Equity Curve")

    # Metrics from latest snapshot
    latest = snapshots[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Toplam Equity", f"${latest['total_equity']:,.2f}")
    c2.metric("Nakit", f"${latest['cash_balance']:,.2f}")
    c3.metric("Acik Pozisyon", latest["open_positions"])
    c4.metric("Max DD", f"{latest['max_drawdown_pct']:.1f}%")

    # Equity curve chart
    import plotly.graph_objects as go

    timestamps = [datetime.fromisoformat(s["timestamp"]) for s in snapshots if s["timestamp"]]
    equities = [s["total_equity"] for s in snapshots if s["timestamp"]]
    unrealized = [s["unrealized_pnl"] for s in snapshots if s["timestamp"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=equities,
        mode="lines", name="Equity",
        line=dict(color="#26a69a", width=2),
        fill="tozeroy", fillcolor="rgba(38,166,154,0.1)",
    ))
    fig.add_trace(go.Scatter(
        x=timestamps, y=unrealized,
        mode="lines", name="Unrealized P&L",
        line=dict(color="#ff9800", width=1, dash="dot"),
    ))

    fig.update_layout(
        template="plotly_dark",
        height=400,
        title="Portfolio Equity Over Time",
        xaxis_title="Zaman",
        yaxis_title="USD",
        hovermode="x unified",
    )
    st.plotly_chart(fig, width="stretch")

    # Regime distribution from latest snapshot
    if latest.get("regime_distribution"):
        regime_labels = {
            "TRENDING_UP": "Yukari Trend",
            "TRENDING_DOWN": "Asagi Trend",
            "RANGING": "Yatay",
            "HIGH_VOLATILITY": "Yuksek Vol.",
            "LOW_VOLATILITY": "Dusuk Vol.",
            "BREAKOUT": "Kirilim",
        }
        dist = latest["regime_distribution"]
        if dist:
            st.caption("Acik pozisyonlardaki rejim dagilimi:")
            cols = st.columns(len(dist))
            for idx, (regime, count) in enumerate(dist.items()):
                label = regime_labels.get(regime, regime)
                cols[idx % len(cols)].metric(label, count)
