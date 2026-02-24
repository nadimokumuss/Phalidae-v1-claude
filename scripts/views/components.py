"""
Phalidae v2 - Reusable Streamlit Components
Wrapper functions for TradingView-style UI elements.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from views.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_SURFACE,
    BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BULL, BEAR, ACCENT_BLUE, ACCENT_YELLOW,
    REGIME_COLORS, REGIME_LABELS,
    metric_strip_html, status_dot_html, pnl_colored_html,
    regime_badge_html,
)
from views.cache import (
    get_portfolio_summary_cached,
    get_daily_pnl_cached,
)


def render_top_bar():
    """Top bar: Equity | P&L | Exposure | Open Positions | Status Dot.
    Uses st.fragment for auto-refresh every 30s."""

    @st.fragment(run_every=30)
    def _top_bar_fragment():
        ps = get_portfolio_summary_cached()
        daily = get_daily_pnl_cached()

        equity = ps.get("equity", 0)
        total_pnl = ps.get("total_pnl", 0)
        total_pnl_pct = ps.get("total_pnl_pct", 0)
        unrealized = ps.get("unrealized_pnl", 0)
        exposure = ps.get("exposure_pct", 0)
        open_pos = ps.get("open_positions", 0)
        daily_pnl = daily.get("pnl_usd", 0)
        daily_pnl_pct = daily.get("pnl_pct", 0)

        items = [
            {
                "label": "Equity",
                "value": f"${equity:,.2f}",
                "delta": f"{total_pnl_pct:+.1f}%",
            },
            {
                "label": "Unrealized",
                "value": f"${unrealized:+,.2f}",
            },
            {
                "label": "Daily P&L",
                "value": f"${daily_pnl:+,.2f}",
                "delta": f"{daily_pnl_pct:+.1f}%",
            },
            {
                "label": "Exposure",
                "value": f"{exposure:.1f}%",
            },
            {
                "label": "Open",
                "value": str(open_pos),
            },
        ]

        dot = status_dot_html(True)
        html = metric_strip_html(items)
        # Append status dot
        html = html.replace("</div></div>", f'{dot}</div></div>', 1)
        st.markdown(html, unsafe_allow_html=True)

    _top_bar_fragment()


def render_watchlist(watchlist_data: list[dict], selected_symbol: str):
    """Left panel watchlist using a single selectbox for speed.
    No per-symbol DB queries — just symbol names and trade indicators."""

    # Search filter
    search = st.text_input(
        "Ara", placeholder="BTC, ETH...",
        label_visibility="collapsed", key="watchlist_search",
    )

    filtered = watchlist_data
    if search:
        search_upper = search.upper()
        filtered = [
            w for w in watchlist_data
            if search_upper in w.get("symbol", "").upper()
        ]

    # Separate: open trades first, then by symbol name
    with_trade = [w for w in filtered if w.get("has_open_trade")]
    without_trade = [w for w in filtered if not w.get("has_open_trade")]
    sorted_list = with_trade + without_trade

    if not sorted_list:
        st.caption("Coin bulunamadi.")
        return

    # Build display labels — lightweight, no DB calls
    sym_list = [w.get("symbol", "") for w in sorted_list]
    labels = []
    for w in sorted_list:
        clean = w.get("symbol", "").replace("/USDT:USDT", "")
        trade_mark = " *" if w.get("has_open_trade") else ""
        labels.append(f"{clean}{trade_mark}")

    # Find current selected index
    try:
        current_idx = sym_list.index(selected_symbol)
    except ValueError:
        current_idx = 0

    sel_idx = st.selectbox(
        "Coin",
        range(len(sym_list)),
        index=current_idx,
        format_func=lambda i: labels[i],
        label_visibility="collapsed",
        key="watchlist_select",
    )

    new_sym = sym_list[sel_idx]
    if new_sym != st.session_state.get("selected_symbol"):
        st.session_state["selected_symbol"] = new_sym
        st.rerun()

    # Show compact list below selectbox (just text, no widgets)
    container = st.container(height=470)
    with container:
        # Show top 30 as simple text
        for i, w in enumerate(sorted_list[:30]):
            clean = w.get("symbol", "").replace("/USDT:USDT", "")
            regime = w.get("regime", "")
            has_trade = w.get("has_open_trade", False)
            is_sel = w.get("symbol", "") == new_sym

            r_color = REGIME_COLORS.get(regime, TEXT_MUTED)
            bg = BG_TERTIARY if is_sel else "transparent"
            weight = "600" if is_sel else "400"
            trade_dot = f' <span style="color:{ACCENT_YELLOW};">●</span>' if has_trade else ""

            st.markdown(
                f'<div style="padding:2px 6px;background:{bg};font-size:12px;'
                f'color:{TEXT_PRIMARY};font-weight:{weight};border-left:'
                f'{"3px solid " + ACCENT_BLUE if is_sel else "3px solid transparent"};">'
                f'<span style="color:{r_color};font-size:8px;">●</span> {clean}{trade_dot}'
                f'</div>',
                unsafe_allow_html=True,
            )

        if len(sorted_list) > 30:
            st.caption(f"+{len(sorted_list) - 30} daha (arama ile bulun)")


def render_bottom_panel_trades(trades: list[dict], mode: str = "open"):
    """Bottom panel trade table. Compact dataframe render."""
    if not trades:
        st.caption("Islem bulunamadi.")
        return

    rows = []
    for t in trades:
        coin = t.get("symbol", "").replace("/USDT:USDT", "")
        bias = t.get("bias", "")

        if mode == "open":
            pnl_pct = t.get("unrealized_pnl_pct", 0)
            size = t.get("position_size_usd")
            rows.append({
                "Coin": coin,
                "Yon": bias,
                "Giris": f"${t['entry_price']:,.4f}" if t["entry_price"] < 1 else f"${t['entry_price']:,.2f}",
                "P&L": f"{pnl_pct:+.2f}%" if pnl_pct else "-",
                "TP": f"${t['tp_price']:,.2f}" if t.get("tp_price") else "-",
                "SL": f"${t['sl_price']:,.2f}" if t.get("sl_price") else "-",
                "Trail": f"${t['trailing_stop_price']:,.2f}" if t.get("trailing_stop_price") else "-",
                "Boyut": f"${size:,.0f}" if size else "-",
                "Rejim": REGIME_LABELS.get(t.get("regime_at_entry", ""), "-"),
                "Acilis": t.get("opened_at", "-"),
            })
        else:
            rows.append({
                "Coin": coin,
                "Yon": bias,
                "Sonuc": t.get("status", "-"),
                "Giris": f"${t['entry_price']:,.2f}",
                "Cikis": f"${t['exit_price']:,.2f}" if t.get("exit_price") else "-",
                "P&L$": f"${t.get('pnl_usd', 0):+,.2f}",
                "P&L%": f"{t.get('pnl_percent', 0):+.2f}%",
                "Sure": t.get("duration", "-"),
                "Rejim": REGIME_LABELS.get(t.get("regime_at_entry", ""), "-"),
            })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(len(rows) * 36 + 40, 350))


def render_bottom_panel_signals(signals: list[dict]):
    """Bottom panel signal table."""
    if not signals:
        st.caption("Sinyal bulunamadi.")
        return

    rows = []
    for s in signals:
        coin = (s.get("symbol") or "").replace("/USDT:USDT", "")
        rows.append({
            "Coin": coin,
            "Yon": s.get("bias", "-"),
            "Entry": f"${s.get('entry_price', 0):,.2f}" if s.get("entry_price") else "-",
            "TP": f"${s.get('tp_price', 0):,.2f}" if s.get("tp_price") else "-",
            "SL": f"${s.get('sl_price', 0):,.2f}" if s.get("sl_price") else "-",
            "Skor": f"{s.get('score', 0):+.1f}" if s.get("score") else "-",
            "Guven": s.get("confidence_label", "-"),
            "Rejim": REGIME_LABELS.get(s.get("regime", ""), s.get("regime", "-")),
            "Zaman": s.get("created_at", "-")[:16] if s.get("created_at") else "-",
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(len(rows) * 36 + 40, 350))


def render_signal_detail(signal: dict):
    """Right panel signal detail: confidence bar, score breakdown, reasoning."""
    if not signal:
        st.caption("Sinyal secilmedi.")
        return

    coin = (signal.get("symbol") or "").replace("/USDT:USDT", "")
    bias = signal.get("bias", "-")
    score = signal.get("score", 0)
    confidence = signal.get("confidence_score", 0)
    conf_label = signal.get("confidence_label", "-")
    regime = signal.get("regime", "-")

    bias_color = BULL if bias == "LONG" else BEAR
    st.markdown(
        f'<div style="font-size:16px;font-weight:600;color:{bias_color};">'
        f'{coin} {bias}</div>',
        unsafe_allow_html=True,
    )

    # Confidence bar
    conf_pct = min(max(confidence, 0), 100)
    bar_color = BULL if conf_pct >= 75 else ACCENT_YELLOW if conf_pct >= 50 else BEAR
    st.markdown(
        f'<div style="margin:6px 0;">'
        f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-bottom:2px;">'
        f'Guven: {conf_label} ({conf_pct:.0f}/100)</div>'
        f'<div style="background:{BG_SURFACE};border-radius:3px;height:8px;overflow:hidden;">'
        f'<div style="width:{conf_pct}%;height:100%;background:{bar_color};'
        f'border-radius:3px;"></div></div></div>',
        unsafe_allow_html=True,
    )

    # Score
    st.markdown(
        f'<div style="font-size:11px;color:{TEXT_SECONDARY};margin-top:6px;">'
        f'Skor: <span style="color:{TEXT_PRIMARY};font-family:monospace;">'
        f'{score:+.1f}</span></div>',
        unsafe_allow_html=True,
    )

    # Regime
    st.markdown(
        f'<div style="font-size:11px;color:{TEXT_SECONDARY};margin-top:4px;">'
        f'Rejim: {regime_badge_html(regime)}</div>',
        unsafe_allow_html=True,
    )

    # Score breakdown if available
    breakdown = signal.get("score_breakdown")
    if breakdown and isinstance(breakdown, dict):
        st.markdown(
            f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-top:8px;'
            f'font-weight:500;">SKOR DAGILIMI</div>',
            unsafe_allow_html=True,
        )
        for key, val in breakdown.items():
            if isinstance(val, (int, float)):
                val_color = BULL if val > 0 else BEAR if val < 0 else TEXT_MUTED
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;'
                    f'font-size:11px;padding:1px 0;">'
                    f'<span style="color:{TEXT_SECONDARY};">{key}</span>'
                    f'<span style="color:{val_color};font-family:monospace;">'
                    f'{val:+.2f}</span></div>',
                    unsafe_allow_html=True,
                )

    # Entry/TP/SL
    entry = signal.get("entry_price")
    tp = signal.get("tp_price")
    sl = signal.get("sl_price")
    if entry:
        st.markdown(
            f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-top:8px;'
            f'font-weight:500;">SEVIYELERI</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="font-size:11px;font-family:monospace;color:{TEXT_PRIMARY};">'
            f'Entry: ${entry:,.2f}</div>',
            unsafe_allow_html=True,
        )
        if tp:
            st.markdown(
                f'<div style="font-size:11px;font-family:monospace;color:{BULL};">'
                f'TP: ${tp:,.2f}</div>',
                unsafe_allow_html=True,
            )
        if sl:
            st.markdown(
                f'<div style="font-size:11px;font-family:monospace;color:{BEAR};">'
                f'SL: ${sl:,.2f}</div>',
                unsafe_allow_html=True,
            )
