"""
Phalidae v2 - Strategy Lab v2 (TradingView Style)
Redesigned strategy ranking, variant details, correlation heatmap.
"""

import streamlit as st
import pandas as pd
import numpy as np

from db.engine import get_session
from db.models import StrategyVariant
from datetime import datetime, timedelta

from views.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_SURFACE,
    BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BULL, BEAR, ACCENT_BLUE, ACCENT_PURPLE,
    REGIME_COLORS, REGIME_LABELS,
)
from views.components import render_top_bar
from views.cache import (
    get_active_symbols_cached,
    get_global_leaderboard_cached,
    get_correlation_data_cached,
    get_top_strategies_cached,
    get_regime_distribution_cached,
    get_candle_count_cached,
    get_variant_performance_cached,
)


def render():
    """Strategy Lab v2 main page."""
    render_top_bar()

    tab_leader, tab_coin, tab_detail, tab_corr = st.tabs([
        "Liderlik", "Coin Bazli", "Varyant Detay", "Korelasyon",
    ])

    with tab_leader:
        _render_leaderboard()
    with tab_coin:
        _render_coin_strategies()
    with tab_detail:
        _render_variant_detail()
    with tab_corr:
        _render_correlation()


# ---------------------------------------------------------------------------
# Leaderboard Tab
# ---------------------------------------------------------------------------

def _render_leaderboard():
    """Global strategy leaderboard — sortable table."""
    results = get_global_leaderboard_cached()

    if not results:
        st.info("Henuz yeterli backtest verisi yok. En az 3 coin'de test edilmis strateji gerekli.")
        return

    rows = []
    for r in results:
        rows.append({
            "ID": r["id"],
            "Strateji": r["name"],
            "Ort. Skor": round(r["avg_score"], 4),
            "Ort. WR": f"{r['avg_wr'] * 100:.1f}%",
            "Ort. PF": round(r["avg_pf"], 2),
            "Trade": r["total_trades"],
            "Coin": r["coin_count"],
            "Trend WR": f"{r['avg_trend_wr'] * 100:.0f}%" if r["avg_trend_wr"] else "-",
            "Yatay WR": f"{r['avg_range_wr'] * 100:.0f}%" if r["avg_range_wr"] else "-",
            "Volatil WR": f"{r['avg_vol_wr'] * 100:.0f}%" if r["avg_vol_wr"] else "-",
            "Indikatörler": r["trend_str"],
        })

    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{TEXT_PRIMARY};'
        f'padding:4px 0;">Global Top {len(rows)} Strateji</div>',
        unsafe_allow_html=True,
    )

    df = pd.DataFrame(rows)

    try:
        from st_aggrid import AgGrid, GridOptionsBuilder

        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(
            sortable=True,
            filter=True,
            resizable=True,
            cellStyle={"fontSize": "12px"},
        )
        gb.configure_column("Strateji", width=200)
        gb.configure_column("Ort. Skor", type=["numericColumn"], width=100)
        gb.configure_selection("single")

        grid_options = gb.build()

        AgGrid(
            df,
            gridOptions=grid_options,
            height=500,
            fit_columns_on_grid_load=True,
        )
    except ImportError:
        st.dataframe(df, use_container_width=True, height=500)


# ---------------------------------------------------------------------------
# Coin-Based Tab (includes periodic analysis)
# ---------------------------------------------------------------------------

def _render_coin_strategies():
    """Per-coin strategy ranking with regime breakdown."""
    symbols = get_active_symbols_cached()

    if not symbols:
        st.info("Henuz takip edilen coin yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    c1, c2 = st.columns([2, 3])
    with c1:
        sel_idx = st.selectbox(
            "Coin", range(len(sym_list)),
            format_func=lambda i: sym_labels[i], key="sl2_coin",
        )
        selected_sym = sym_list[sel_idx]
    with c2:
        regime_filter = st.radio(
            "Filtre",
            ["Genel", "Trend", "Yatay", "Volatil"],
            horizontal=True, key="sl2_regime",
        )

    strategies = get_top_strategies_cached(selected_sym, limit=20)

    if not strategies:
        st.info(f"{sym_labels[sel_idx]} icin henuz backtest sonucu yok.")
        return

    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{TEXT_PRIMARY};'
        f'padding:4px 0;">Top {len(strategies)}: {sym_labels[sel_idx]}</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for s in strategies:
        comp = s.get("composition", {})
        trend_str = ", ".join(comp.get("trend", []))

        rows.append({
            "Rank": s["rank"],
            "Skor": round(s["composite_score"], 4),
            "WR": f"{s['win_rate'] * 100:.1f}%",
            "PF": round(s["profit_factor"], 2),
            "Sharpe": round(s["sharpe_ratio"], 2),
            "Max DD": f"{s['max_drawdown']:.1f}%",
            "P&L": f"{s['total_pnl_pct']:+.1f}%",
            "Trade": s["total_trades"],
            "Trend WR": f"{s.get('regime_trending_score', 0) * 100:.0f}%" if s.get("regime_trending_score") else "-",
            "Yatay WR": f"{s.get('regime_ranging_score', 0) * 100:.0f}%" if s.get("regime_ranging_score") else "-",
            "Volatil WR": f"{s.get('regime_volatile_score', 0) * 100:.0f}%" if s.get("regime_volatile_score") else "-",
            "Trend Ind.": trend_str[:30],
        })

    df = pd.DataFrame(rows)

    try:
        from st_aggrid import AgGrid, GridOptionsBuilder

        gb = GridOptionsBuilder.from_dataframe(df)
        gb.configure_default_column(sortable=True, filter=True, resizable=True,
                                    cellStyle={"fontSize": "12px"})
        gb.configure_column("Skor", type=["numericColumn"])
        grid_options = gb.build()

        AgGrid(df, gridOptions=grid_options, height=400, fit_columns_on_grid_load=True)
    except ImportError:
        st.dataframe(df, use_container_width=True, height=400)

    # Top 5 comparison chart
    if len(strategies) >= 2:
        _render_comparison_chart(strategies[:5])

    # Periodic analysis (expandable)
    with st.expander("Donemsel Analiz", expanded=False):
        _render_periodic_section(selected_sym, sym_labels[sel_idx])


def _render_comparison_chart(top5: list[dict]):
    """Top 5 strategy comparison bar chart (Plotly)."""
    import plotly.graph_objects as go

    names = [f"#{s['rank']}" for s in top5]
    metrics = ["win_rate", "profit_factor", "sharpe_ratio"]
    labels = ["Win Rate", "Profit Factor", "Sharpe"]
    colors = [BULL, "#ff9800", ACCENT_BLUE]

    fig = go.Figure()
    for metric, label, color in zip(metrics, labels, colors):
        values = []
        for s in top5:
            val = s[metric]
            if metric == "win_rate":
                val *= 100
            values.append(val)
        fig.add_trace(go.Bar(name=label, x=names, y=values, marker_color=color))

    fig.update_layout(
        barmode="group",
        template="plotly_dark",
        height=350,
        paper_bgcolor=BG_PRIMARY,
        plot_bgcolor=BG_PRIMARY,
        font=dict(color=TEXT_PRIMARY, size=11),
        margin=dict(l=40, r=20, t=30, b=40),
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_periodic_section(symbol: str, coin_label: str):
    """Periodic analysis: regime distribution + data depth (cached queries)."""
    period = st.selectbox(
        "Donem", ["Son 30 gun", "Son 90 gun", "Son 180 gun", "Son 1 yil"],
        key="sl2_period",
    )
    period_days = {"Son 30 gun": 30, "Son 90 gun": 90, "Son 180 gun": 180, "Son 1 yil": 365}[period]

    regimes = get_regime_distribution_cached(symbol, period_days)

    if regimes:
        import plotly.graph_objects as go

        labels = [REGIME_LABELS.get(r["regime_label"], r["regime_label"]) for r in regimes]
        values = [r["cnt"] for r in regimes]
        colors = [REGIME_COLORS.get(r["regime_label"], TEXT_MUTED) for r in regimes]

        fig = go.Figure(data=[go.Pie(
            labels=labels, values=values,
            hole=0.4,
            marker_colors=colors,
        )])
        fig.update_layout(
            template="plotly_dark",
            height=300,
            paper_bgcolor=BG_PRIMARY,
            plot_bgcolor=BG_PRIMARY,
            font=dict(color=TEXT_PRIMARY, size=11),
            margin=dict(l=20, r=20, t=20, b=20),
        )
        st.plotly_chart(fig, use_container_width=True)

    candle_count = get_candle_count_cached(symbol, "4h")
    st.caption(f"4h veri derinligi: {candle_count} mum (~{candle_count * 4 / 24:.0f} gun)")


# ---------------------------------------------------------------------------
# Variant Detail Tab
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _get_variant_list_cached() -> list[dict]:
    """Cache variant list."""
    session = get_session()
    try:
        variants = session.query(StrategyVariant).order_by(StrategyVariant.id).limit(200).all()
        return [
            {"id": v.id, "name": v.name, "composition": v.composition,
             "trend_threshold": v.trend_threshold, "entry_threshold": v.entry_threshold,
             "volume_required": v.volume_required}
            for v in variants
        ]
    finally:
        session.close()


def _render_variant_detail():
    """Detailed view of a strategy variant with cross-coin performance."""
    variant_data = _get_variant_list_cached()

    if not variant_data:
        st.info("Henuz strateji varyanti yok.")
        return

    sel = st.selectbox(
        "Varyant",
        range(len(variant_data)),
        format_func=lambda i: f"#{variant_data[i]['id']} - {variant_data[i]['name'][:50]}",
        key="sl2_variant",
    )
    v = variant_data[sel]

    st.markdown(
        f'<div style="font-size:14px;font-weight:600;color:{TEXT_PRIMARY};'
        f'padding:4px 0;">Varyant #{v["id"]}: {v["name"]}</div>',
        unsafe_allow_html=True,
    )

    try:
        comp = v["composition"] if isinstance(v["composition"], dict) else {}
    except (TypeError, AttributeError):
        comp = {}

    # Composition display
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Trend:** {', '.join(comp.get('trend', []))}")
    c2.markdown(f"**Entry:** {', '.join(comp.get('entry', []))}")
    c3.markdown(f"**Volume:** {', '.join(comp.get('volume', []))}")
    c4.markdown(f"**Volatility:** {', '.join(comp.get('volatility', []))}")

    st.caption(
        f"Trend threshold: {v['trend_threshold']} | "
        f"Entry threshold: {v['entry_threshold']} | "
        f"Volume required: {v['volume_required']}"
    )

    # Cross-coin performance (cached)
    perfs = get_variant_performance_cached(v["id"])

    if perfs:
        rows = []
        for p in perfs:
            rows.append({
                "Coin": p["symbol"].replace("/USDT:USDT", ""),
                "Rank": p["rank"],
                "Skor": round(p["composite_score"], 4),
                "WR": f"{p['win_rate'] * 100:.1f}%",
                "PF": round(p["profit_factor"], 2),
                "Sharpe": round(p["sharpe_ratio"], 2),
                "Max DD": f"{p['max_drawdown']:.1f}%",
                "P&L": f"{p['total_pnl_pct']:+.1f}%",
                "Trade": p["total_trades"],
                "Trend WR": f"{p['regime_trending_score'] * 100:.0f}%" if p["regime_trending_score"] else "-",
                "Yatay WR": f"{p['regime_ranging_score'] * 100:.0f}%" if p["regime_ranging_score"] else "-",
                "Paper WR": f"{p['paper_win_rate'] * 100:.1f}%" if p["paper_total"] and p["paper_total"] > 0 else "-",
            })

        df = pd.DataFrame(rows)

        try:
            from st_aggrid import AgGrid, GridOptionsBuilder

            gb = GridOptionsBuilder.from_dataframe(df)
            gb.configure_default_column(sortable=True, filter=True, resizable=True,
                                        cellStyle={"fontSize": "12px"})
            gb.configure_column("Skor", type=["numericColumn"])
            grid_options = gb.build()
    
            AgGrid(df, gridOptions=grid_options, height=400, fit_columns_on_grid_load=True)
        except ImportError:
            st.dataframe(df, use_container_width=True, height=400)
    else:
        st.info("Bu varyant icin henuz backtest sonucu yok.")


# ---------------------------------------------------------------------------
# Correlation Tab
# ---------------------------------------------------------------------------

def _render_correlation():
    """Pairwise correlation heatmap."""
    correlations = get_correlation_data_cached()

    if not correlations:
        st.info("Korelasyon verisi henuz hesaplanmadi.")
        return

    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{TEXT_PRIMARY};'
        f'padding:4px 0;">Coin Korelasyon Matrisi</div>',
        unsafe_allow_html=True,
    )
    st.caption("4h close getiri korelasyonu. >0.7 olan ciftlere ayni anda trade acilmaz.")

    # Build matrix
    symbols = set()
    for c in correlations:
        symbols.add(c["symbol_a"])
        symbols.add(c["symbol_b"])

    symbols = sorted(symbols)
    clean_symbols = [s.replace("/USDT:USDT", "") for s in symbols]
    n = len(symbols)

    matrix = np.eye(n)
    sym_idx = {s: i for i, s in enumerate(symbols)}

    for c in correlations:
        i = sym_idx.get(c["symbol_a"])
        j = sym_idx.get(c["symbol_b"])
        if i is not None and j is not None:
            matrix[i, j] = c["correlation"]
            matrix[j, i] = c["correlation"]

    import plotly.graph_objects as go

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=clean_symbols,
        y=clean_symbols,
        colorscale="RdYlGn_r",
        zmid=0, zmin=-1, zmax=1,
        text=np.round(matrix, 2),
        texttemplate="%{text}",
        textfont={"size": 9},
    ))

    fig.update_layout(
        template="plotly_dark",
        height=max(400, n * 25),
        paper_bgcolor=BG_PRIMARY,
        plot_bgcolor=BG_PRIMARY,
        font=dict(color=TEXT_PRIMARY, size=10),
        margin=dict(l=60, r=20, t=20, b=60),
    )
    st.plotly_chart(fig, use_container_width=True)

    # High correlation warnings
    high_corr = [c for c in correlations if abs(c["correlation"]) > 0.7]
    if high_corr:
        st.warning(f"{len(high_corr)} yuksek korelasyonlu cift (>0.7)")
        for c in sorted(high_corr, key=lambda x: abs(x["correlation"]), reverse=True)[:10]:
            a = c["symbol_a"].replace("/USDT:USDT", "")
            b = c["symbol_b"].replace("/USDT:USDT", "")
            st.caption(f"  {a} <-> {b}: {c['correlation']:.3f}")
