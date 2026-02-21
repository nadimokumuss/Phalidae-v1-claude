"""
Phalidae v2 - Strategy Lab Page (Phase 3 + 5)
Per-coin strategy rankings, variant details, comparison, global leaderboard.
Includes: regime-based performance breakdown, correlation matrix, regime filters.
Optimized: cache + N+1 fix.
"""

import streamlit as st
import pandas as pd
import numpy as np

from db.engine import get_session
from db.models import (
    StrategyVariant, StrategyPerformance, OHLCVData,
)
from strategy.optimizer import get_top_strategies
from sqlalchemy import func
from commentary import generate_page_header
from views.cache import (
    get_active_symbols_cached,
    get_global_leaderboard_cached,
    get_correlation_data_cached,
)


def render():
    generate_page_header("Strategy Lab")
    st.title("Strategy Lab")
    st.caption("Coin bazli strateji siralamasi ve karsilastirma")

    tab_coin, tab_global, tab_detail, tab_corr, tab_periodic = st.tabs([
        "Coin Bazli", "Global Leaderboard", "Varyant Detayi", "Korelasyon", "Donemsel Analiz"
    ])

    with tab_coin:
        _render_coin_strategies()
    with tab_global:
        _render_global_leaderboard()
    with tab_detail:
        _render_variant_detail()
    with tab_corr:
        _render_correlation_matrix()
    with tab_periodic:
        _render_periodic_analysis()


def _render_coin_strategies():
    """Show strategy rankings for a selected coin with regime breakdown."""
    symbols = get_active_symbols_cached()

    if not symbols:
        st.info("Henuz takip edilen coin yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    sel_idx = st.selectbox("Coin sec:", range(len(sym_list)), format_func=lambda i: sym_labels[i])
    selected_sym = sym_list[sel_idx]

    # Regime filter
    regime_filter = st.radio(
        "Filtre:",
        ["Genel", "Trend Rejimi", "Yatay Rejim", "Volatil Rejim"],
        horizontal=True,
    )

    strategies = get_top_strategies(selected_sym, limit=20)

    if not strategies:
        st.info(f"{sym_labels[sel_idx]} icin henuz backtest sonucu yok.")
        return

    st.subheader(f"Top {len(strategies)} Strateji: {sym_labels[sel_idx]}")

    rows = []
    for s in strategies:
        comp = s["composition"]
        trend_str = ", ".join(comp.get("trend", []))
        entry_str = ", ".join(comp.get("entry", []))
        vol_str = ", ".join(comp.get("volume", []))

        row = {
            "Rank": s["rank"],
            "Skor": f"{s['composite_score']:.4f}",
            "Win Rate": f"{s['win_rate'] * 100:.1f}%",
            "PF": f"{s['profit_factor']:.2f}",
            "Sharpe": f"{s['sharpe_ratio']:.2f}",
            "Max DD": f"{s['max_drawdown']:.1f}%",
            "P&L": f"{s['total_pnl_pct']:+.1f}%",
            "Trade #": s["total_trades"],
            "Trend": trend_str[:30],
            "Entry": entry_str[:25],
            "Volume": vol_str[:15],
        }

        # Add regime scores
        row["Trend WR"] = f"{s.get('regime_trending_score', 0) * 100:.0f}%" if s.get("regime_trending_score") else "-"
        row["Yatay WR"] = f"{s.get('regime_ranging_score', 0) * 100:.0f}%" if s.get("regime_ranging_score") else "-"
        row["Volatil WR"] = f"{s.get('regime_volatile_score', 0) * 100:.0f}%" if s.get("regime_volatile_score") else "-"

        rows.append(row)

    st.dataframe(pd.DataFrame(rows), width="stretch", height=500)

    # Top 5 comparison chart
    if len(strategies) >= 2:
        st.subheader("Top 5 Karsilastirma")
        import plotly.graph_objects as go

        top5 = strategies[:5]
        names = [f"#{s['rank']}" for s in top5]

        fig = go.Figure()
        metrics = ["win_rate", "profit_factor", "sharpe_ratio"]
        labels = ["Win Rate", "Profit Factor", "Sharpe"]
        colors = ["#26a69a", "#ff9800", "#2196f3"]

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
            height=400,
            title="Top 5 Strateji Metrikleri",
        )
        st.plotly_chart(fig, width="stretch")


def _render_global_leaderboard():
    """Global strategy ranking across all coins — cached."""
    results = get_global_leaderboard_cached()

    if not results:
        st.info("Henuz yeterli backtest verisi yok. En az 3 coin'de test edilmis strateji gerekli.")
        return

    rows = []
    for r in results:
        rows.append({
            "ID": r["id"],
            "Strateji": r["name"],
            "Ort. Skor": f"{r['avg_score']:.4f}",
            "Ort. WR": f"{r['avg_wr'] * 100:.1f}%",
            "Ort. PF": f"{r['avg_pf']:.2f}",
            "Toplam Trade": r["total_trades"],
            "Coin Sayisi": r["coin_count"],
            "Trend WR": f"{r['avg_trend_wr'] * 100:.0f}%" if r["avg_trend_wr"] else "-",
            "Yatay WR": f"{r['avg_range_wr'] * 100:.0f}%" if r["avg_range_wr"] else "-",
            "Volatil WR": f"{r['avg_vol_wr'] * 100:.0f}%" if r["avg_vol_wr"] else "-",
            "Trend": r["trend_str"],
        })

    st.subheader(f"Global Top {len(rows)} Strateji")
    st.dataframe(pd.DataFrame(rows), width="stretch", height=600)


@st.cache_data(ttl=300, show_spinner=False)
def _get_variant_list_cached() -> list[dict]:
    """Cache variant list for detail view."""
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
    """Detailed view of a specific strategy variant with regime breakdown."""
    variant_data = _get_variant_list_cached()

    if not variant_data:
        st.info("Henuz strateji varyanti yok.")
        return

    sel = st.selectbox(
        "Varyant sec:",
        range(len(variant_data)),
        format_func=lambda i: f"#{variant_data[i]['id']} - {variant_data[i]['name'][:50]}",
    )
    v = variant_data[sel]

    st.subheader(f"Varyant #{v['id']}: {v['name']}")

    try:
        comp = v["composition"] if isinstance(v["composition"], dict) else {}
    except (TypeError, AttributeError):
        comp = {}

    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"**Trend:** {', '.join(comp.get('trend', []))}")
    c2.markdown(f"**Entry:** {', '.join(comp.get('entry', []))}")
    c3.markdown(f"**Volume:** {', '.join(comp.get('volume', []))}")
    c4.markdown(f"**Volatility:** {', '.join(comp.get('volatility', []))}")

    st.write(f"Trend threshold: {v['trend_threshold']}, Entry threshold: {v['entry_threshold']}, Volume required: {v['volume_required']}")

    # Performance across coins
    session = get_session()
    try:
        perfs = (
            session.query(StrategyPerformance)
            .filter_by(strategy_variant_id=v["id"])
            .filter(StrategyPerformance.total_trades > 0)
            .order_by(StrategyPerformance.composite_score.desc())
            .all()
        )
    finally:
        session.close()

    if perfs:
        rows = []
        for p in perfs:
            rows.append({
                "Coin": p.symbol.replace("/USDT:USDT", ""),
                "Rank": p.rank,
                "Skor": f"{p.composite_score:.4f}",
                "WR": f"{p.win_rate * 100:.1f}%",
                "PF": f"{p.profit_factor:.2f}",
                "Sharpe": f"{p.sharpe_ratio:.2f}",
                "Max DD": f"{p.max_drawdown:.1f}%",
                "P&L": f"{p.total_pnl_pct:+.1f}%",
                "Trade": p.total_trades,
                "Trend WR": f"{p.regime_trending_score * 100:.0f}%" if p.regime_trending_score else "-",
                "Yatay WR": f"{p.regime_ranging_score * 100:.0f}%" if p.regime_ranging_score else "-",
                "Volatil WR": f"{p.regime_volatile_score * 100:.0f}%" if p.regime_volatile_score else "-",
                "Paper WR": f"{p.paper_win_rate * 100:.1f}%" if p.paper_total > 0 else "-",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch")
    else:
        st.info("Bu varyant icin henuz backtest sonucu yok.")


def _render_correlation_matrix():
    """Show pairwise correlation heatmap between symbols — cached."""
    correlations = get_correlation_data_cached()

    if not correlations:
        st.info("Korelasyon verisi henuz hesaplanmadi. Optimizer ilk calistiginda gorunecek.")
        return

    st.subheader("Coin Korelasyon Matrisi")
    st.caption("4h close getiri korelasyonu. >0.7 olan ciftlere ayni anda trade acilmaz.")

    # Build correlation matrix
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

    # Plotly heatmap
    import plotly.graph_objects as go

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=clean_symbols,
        y=clean_symbols,
        colorscale="RdYlGn_r",
        zmid=0,
        zmin=-1,
        zmax=1,
        text=np.round(matrix, 2),
        texttemplate="%{text}",
        textfont={"size": 9},
    ))

    fig.update_layout(
        template="plotly_dark",
        height=max(400, n * 25),
        title="Korelasyon Matrisi (4h Close Returns)",
        xaxis_title="",
        yaxis_title="",
    )

    st.plotly_chart(fig, width="stretch")

    # High correlation pairs warning
    high_corr = [c for c in correlations if abs(c["correlation"]) > 0.7]
    if high_corr:
        st.warning(f"{len(high_corr)} yuksek korelasyonlu cift (>0.7) - bu ciftlere ayni anda trade acilmaz:")
        for c in sorted(high_corr, key=lambda x: abs(x["correlation"]), reverse=True)[:10]:
            a = c["symbol_a"].replace("/USDT:USDT", "")
            b = c["symbol_b"].replace("/USDT:USDT", "")
            st.caption(f"  {a} <-> {b}: {c['correlation']:.3f}")


def _render_periodic_analysis():
    """Phase 3: Period-based performance analysis — N+1 fix with join."""
    symbols = get_active_symbols_cached()

    if not symbols:
        st.info("Henuz takip edilen coin yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    st.subheader("Donemsel Performans Analizi")
    st.caption("Stratejilerin farkli zaman dilimlerindeki performansini karsilastirin")

    c1, c2 = st.columns(2)
    with c1:
        sel_idx = st.selectbox("Coin:", range(len(sym_list)),
                               format_func=lambda i: sym_labels[i], key="periodic_coin")
        symbol = sym_list[sel_idx]
    with c2:
        period = st.selectbox("Donem:", ["Son 30 gun", "Son 90 gun", "Son 180 gun", "Son 1 yil"], key="periodic_period")

    # Calculate period in days
    period_days = {"Son 30 gun": 30, "Son 90 gun": 90, "Son 180 gun": 180, "Son 1 yil": 365}[period]

    session = get_session()
    try:
        # N+1 fix: join StrategyPerformance with StrategyVariant in one query
        results = (
            session.query(StrategyPerformance, StrategyVariant.name)
            .join(StrategyVariant, StrategyPerformance.strategy_variant_id == StrategyVariant.id)
            .filter(StrategyPerformance.symbol == symbol)
            .filter(StrategyPerformance.total_trades >= 5)
            .order_by(StrategyPerformance.composite_score.desc())
            .limit(10)
            .all()
        )

        if not results:
            st.info("Bu coin icin yeterli strateji verisi yok.")
            return

        rows = []
        for p, variant_name in results:
            name = variant_name[:40] if variant_name else f"Variant #{p.strategy_variant_id}"
            rows.append({
                "Strateji": name,
                "Skor": f"{p.composite_score:.4f}",
                "WR": f"{p.win_rate * 100:.1f}%",
                "PF": f"{p.profit_factor:.2f}",
                "P&L": f"{p.total_pnl_pct:+.1f}%",
                "Trade": p.total_trades,
                "Trend WR": f"{p.regime_trending_score * 100:.0f}%" if p.regime_trending_score else "-",
                "Yatay WR": f"{p.regime_ranging_score * 100:.0f}%" if p.regime_ranging_score else "-",
                "Volatil WR": f"{p.regime_volatile_score * 100:.0f}%" if p.regime_volatile_score else "-",
                "Paper": f"{p.paper_win_rate * 100:.0f}% ({p.paper_total})" if p.paper_total > 0 else "-",
                "Son Guncelleme": p.updated_at.strftime("%Y-%m-%d") if p.updated_at else "-",
            })

        st.dataframe(pd.DataFrame(rows), width="stretch")

        # Regime distribution for this coin's data
        from db.models import MarketRegimeRecord
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(days=period_days)
        regimes = (
            session.query(
                MarketRegimeRecord.regime_label,
                func.count().label("cnt"),
            )
            .filter(
                MarketRegimeRecord.symbol == symbol,
                MarketRegimeRecord.timestamp >= cutoff,
            )
            .group_by(MarketRegimeRecord.regime_label)
            .all()
        )

        if regimes:
            st.subheader(f"Rejim Dagilimi ({period})")

            regime_labels = {
                "TRENDING_UP": "Yukari Trend",
                "TRENDING_DOWN": "Asagi Trend",
                "RANGING": "Yatay",
                "HIGH_VOLATILITY": "Yuksek Vol.",
                "LOW_VOLATILITY": "Dusuk Vol.",
                "BREAKOUT": "Kirilim",
            }

            import plotly.graph_objects as go

            labels = [regime_labels.get(r.regime_label, r.regime_label) for r in regimes]
            values = [r.cnt for r in regimes]
            colors = ["#26a69a", "#ef5350", "#ff9800", "#e91e63", "#9c27b0", "#2196f3"]

            fig = go.Figure(data=[go.Pie(
                labels=labels, values=values,
                hole=0.4,
                marker_colors=colors[:len(labels)],
            )])
            fig.update_layout(
                template="plotly_dark",
                height=350,
                title=f"{sym_labels[sel_idx]} - Rejim Dagilimi ({period})",
            )
            st.plotly_chart(fig, width="stretch")

        # Data depth info
        candle_count = (
            session.query(func.count(OHLCVData.id))
            .filter_by(symbol=symbol, timeframe="4h")
            .scalar()
        ) or 0
        st.caption(f"4h veri derinligi: {candle_count} mum (~{candle_count * 4 / 24:.0f} gun)")

    finally:
        session.close()
