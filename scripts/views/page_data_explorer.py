"""
Phalidae v2 - Data Explorer Page (Phase 5)
Raw OHLCV viewer, data coverage matrix, indicator overlay chart.
Optimized: 968 queries -> 1 (cached GROUP BY).
"""

import streamlit as st
import pandas as pd

from worker.collector import get_ohlcv_df
from charting import plot_interactive_chart
from commentary import generate_page_header
from views.cache import (
    get_coverage_matrix_cached,
    get_active_symbols_cached,
    get_system_stats_cached,
)


def render():
    generate_page_header("Data Explorer")
    st.title("Data Explorer")
    st.caption("Ham veri goruntuleyici ve kapsam matrisi")

    tab_matrix, tab_viewer, tab_chart = st.tabs([
        "Veri Kapsam Matrisi", "Ham Veri", "Indikator Grafigi"
    ])

    with tab_matrix:
        _render_coverage_matrix()
    with tab_viewer:
        _render_raw_data()
    with tab_chart:
        _render_indicator_chart()


def _render_coverage_matrix():
    """Show data coverage: which coin has how many candles per timeframe.
    Uses single GROUP BY query instead of 968 individual COUNT queries.
    """
    pivot = get_coverage_matrix_cached()

    if pivot.empty:
        st.info("Henuz veri yok.")
        return

    # Determine timeframe columns present
    timeframes = [tf for tf in ["5m", "15m", "30m", "1h", "4h", "1d"] if tf in pivot.columns]

    if not timeframes:
        st.info("Henuz veri yok.")
        return

    # Build display DataFrame
    display_df = pivot[["Coin"] + timeframes].copy()
    display_df = display_df.sort_values("Coin").reset_index(drop=True)

    # Color code: green for >500, yellow for 100-500, red for <100
    def _style_cell(val):
        if isinstance(val, (int, float)):
            if val >= 500:
                return "background-color: rgba(38,166,154,0.3)"
            elif val >= 100:
                return "background-color: rgba(255,235,59,0.2)"
            elif val > 0:
                return "background-color: rgba(239,83,80,0.2)"
        return ""

    styled = display_df.style.map(_style_cell, subset=timeframes)
    st.dataframe(styled, width="stretch", height=600)

    # Summary
    stats = get_system_stats_cached()
    symbols = get_active_symbols_cached()
    st.caption(f"Toplam {stats['total_candles']:,} mum verisi, {len(symbols)} coin, {len(timeframes)} zaman dilimi")


def _render_raw_data():
    """Raw OHLCV data viewer."""
    symbols = get_active_symbols_cached()

    if not symbols:
        st.info("Henuz veri yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    c1, c2, c3 = st.columns(3)
    with c1:
        sel_sym = st.selectbox("Coin:", range(len(sym_list)), format_func=lambda i: sym_labels[i])
        symbol = sym_list[sel_sym]
    with c2:
        tf = st.selectbox("Zaman Dilimi:", ["15m", "1h", "4h", "1d"], index=2)
    with c3:
        limit = st.number_input("Son N mum:", value=100, min_value=10, max_value=2000, step=50)

    df = get_ohlcv_df(symbol, tf, limit=limit)
    if df.empty:
        st.warning("Bu coin/TF icin veri bulunamadi.")
        return

    st.write(f"{len(df)} mum - {df['timestamp'].iloc[0]} ile {df['timestamp'].iloc[-1]} arasi")
    st.dataframe(
        df.style.format({
            "open": "{:.6f}", "high": "{:.6f}", "low": "{:.6f}", "close": "{:.6f}",
            "volume": "{:,.0f}",
        }),
        width="stretch",
        height=500,
    )


def _render_indicator_chart():
    """Interactive chart with indicator overlays from DB data."""
    symbols = get_active_symbols_cached()

    if not symbols:
        st.info("Henuz veri yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    c1, c2 = st.columns(2)
    with c1:
        sel_sym = st.selectbox("Coin (grafik):", range(len(sym_list)), format_func=lambda i: sym_labels[i], key="chart_coin")
        symbol = sym_list[sel_sym]
    with c2:
        tf = st.selectbox("Zaman Dilimi (grafik):", ["15m", "1h", "4h", "1d"], index=2, key="chart_tf")

    df = get_ohlcv_df(symbol, tf, limit=300)
    if df.empty:
        st.warning("Veri bulunamadi.")
        return

    show_bb = st.checkbox("Bollinger Bands", value=True)
    show_ema = st.checkbox("EMA (20/50/200)", value=True)

    fig = plot_interactive_chart(
        df,
        symbol=f"{sym_labels[sel_sym]} {tf}",
        show_bb=show_bb,
        show_ema=show_ema,
    )
    st.plotly_chart(fig, width="stretch")
