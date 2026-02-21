"""
Phalidae v2 - Dashboard Page
System status, data coverage, active trades summary, best strategies per coin.
Fragment-based auto-refresh + centralized cache.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta

from commentary import generate_page_header
from views.cache import (
    get_portfolio_summary_cached,
    get_system_stats_cached,
    get_db_size_cached,
    get_agent_health_cached,
    get_daily_pnl_cached,
    get_open_trades_cached,
    get_regime_map_cached,
    get_funding_data_cached,
    get_data_coverage_summary_cached,
    get_best_strategies_cached,
)

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

JOB_LABELS = {
    "collector": "Collector",
    "analyzer": "Analyzer",
    "trade_checker": "Trade Check",
    "optimizer": "Optimizer",
    "market_data": "Market Data",
    "symbol_refresh": "Sym Refresh",
    "news_collector": "News",
}


def render():
    generate_page_header("Dashboard")
    st.title("Dashboard")
    st.caption("Sistem durumu, veri kapsami ve performans ozeti")

    _fragment_portfolio()
    st.divider()
    _fragment_system_stats()
    st.divider()
    _fragment_agent_health()
    st.divider()
    _fragment_daily_pnl()
    st.divider()
    _render_market_news()
    st.divider()
    _render_regime_map()
    st.divider()
    _render_funding_table()
    st.divider()
    _render_data_coverage()
    st.divider()
    _render_best_strategies()
    _fragment_open_trades()


# ---------------------------------------------------------------------------
# Auto-refresh fragments
# ---------------------------------------------------------------------------

@st.fragment(run_every=30)
def _fragment_portfolio():
    """Portfolio metrics — 30s auto-refresh."""
    try:
        ps = get_portfolio_summary_cached()
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Portfolio Degeri", f"${ps['equity']:,.2f}",
                   delta=f"{ps['total_pnl_pct']:+.1f}%")
        c2.metric("Nakit", f"${ps['cash']:,.2f}")
        c3.metric("Exposure", f"{ps['exposure_pct']:.1f}%")
        c4.metric("Gunluk P&L", f"${ps['daily_pnl']:+,.2f}")
        c5.metric("Acik Pozisyon", ps['open_positions'])
    except Exception:
        pass


@st.fragment(run_every=60)
def _fragment_system_stats():
    """System status metrics — 60s auto-refresh."""
    stats = get_system_stats_cached()
    db_size_mb = get_db_size_cached()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("OHLCV Veri", f"{stats['total_candles']:,}")
    col2.metric("Aktif Coin", stats['active_symbols'])
    col3.metric("Strateji Varyant", stats['total_variants'])
    col4.metric("Acik Trade", stats['open_trades'])

    col5, col6, col7, col8 = st.columns(4)
    col5.metric("DB Boyutu", f"{db_size_mb:.1f} MB")
    col6.metric("Toplam Sinyal", stats['total_signals'])
    col7.metric("Kapali Trade", stats['closed_trades'])
    col8.metric("Toplam P&L", f"${stats['total_pnl']:+,.2f}")


@st.fragment(run_every=45)
def _fragment_agent_health():
    """Agent health panel — 45s auto-refresh."""
    st.subheader("Agent Durumu")

    health = get_agent_health_cached()
    now = datetime.utcnow()
    rows = []

    for job_name in JOB_LABELS:
        job_info = health["jobs"].get(job_name)
        if not job_info:
            rows.append({
                "Job": JOB_LABELS.get(job_name, job_name),
                "Durum": "Bekleniyor",
                "Son Calisma": "-",
                "Sure": "-",
                "Kayit": "-",
            })
            continue

        # Parse timestamps
        completed_at = None
        started_at = None
        if job_info["completed_at"]:
            completed_at = datetime.fromisoformat(job_info["completed_at"])
        if job_info["started_at"]:
            started_at = datetime.fromisoformat(job_info["started_at"])

        interval_min = JOB_INTERVALS.get(job_name, 60)
        if completed_at:
            age_min = (now - completed_at).total_seconds() / 60
        elif started_at:
            age_min = (now - started_at).total_seconds() / 60
        else:
            age_min = 999

        if job_info["status"] == "FAILED":
            status = "HATA"
        elif job_info["status"] == "RUNNING":
            status = "Calisiyor"
        elif age_min > interval_min * 3:
            status = "Eski"
        else:
            status = "Aktif"

        # Age display
        if completed_at:
            delta = now - completed_at
            if delta.total_seconds() < 3600:
                age_str = f"{delta.total_seconds() / 60:.0f} dk once"
            else:
                age_str = f"{delta.total_seconds() / 3600:.1f} sa once"
        else:
            age_str = "Calisir"

        rows.append({
            "Job": JOB_LABELS.get(job_name, job_name),
            "Durum": status,
            "Son Calisma": age_str,
            "Sure": f"{job_info['duration_sec']:.1f}s" if job_info['duration_sec'] else "-",
            "Kayit": str(job_info['records_affected']),
        })

    df = pd.DataFrame(rows)

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

    st.caption(f"Son 24 saat: {health['success_24h']} basarili, {health['fail_24h']} hatali")


@st.fragment(run_every=30)
def _fragment_daily_pnl():
    """Daily P&L — 30s auto-refresh."""
    st.subheader("Gunluk P&L")

    pnl = get_daily_pnl_cached()
    if pnl["count"] > 0:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Gunluk P&L", f"${pnl['pnl_usd']:+,.2f}")
        c2.metric("Gunluk %", f"{pnl['pnl_pct']:+.1f}%")
        c3.metric("Bugun Islem", pnl["count"])
        c4.metric("Bugun Win", pnl["wins"])

        if pnl["pnl_pct"] < -5:
            st.warning(f"Gunluk kayip: {pnl['pnl_pct']:.1f}% - Drawdown limitine yaklasiliyor!")
        if pnl["pnl_pct"] < -10:
            st.error(f"Gunluk drawdown limiti asildi: {pnl['pnl_pct']:.1f}% - Yeni trade'ler engellenecek")
    else:
        st.caption("Bugun kapanan islem yok.")


@st.fragment(run_every=30)
def _fragment_open_trades():
    """Open trades table — 30s auto-refresh."""
    trades = get_open_trades_cached()
    if not trades:
        return

    st.divider()
    st.subheader("Acik Islemler")

    rows = []
    for t in trades:
        rows.append({
            "Coin": t["symbol"].replace("/USDT:USDT", ""),
            "Yon": t["bias"],
            "Giris": f"${t['entry_price']:,.2f}",
            "TP": f"${t['tp_price']:,.2f}" if t["tp_price"] else "-",
            "SL": f"${t['sl_price']:,.2f}" if t["sl_price"] else "-",
            "Trail SL": f"${t['trailing_stop_price']:,.2f}" if t["trailing_stop_price"] else "-",
            "Boyut": f"${t['position_size_usd']:,.0f}" if t["position_size_usd"] else "-",
            "Max Profit": f"{t['max_profit']:+.1f}%",
            "Max DD": f"{t['max_drawdown']:+.1f}%",
            "Partial TP": "Evet" if t["partial_tp_taken"] else "Hayir",
            "Rejim": REGIME_LABELS.get(t["regime_at_entry"], "-"),
            "Acilis": t["opened_at"],
        })
    st.dataframe(pd.DataFrame(rows), width="stretch")


# ---------------------------------------------------------------------------
# Static cached sections
# ---------------------------------------------------------------------------

def _render_market_news():
    """Market news — static, lightweight."""
    import os
    try:
        from worker.news_collector import get_todays_events
        events = get_todays_events(limit=10)
    except ImportError:
        events = []
    except Exception as e:
        st.subheader("Piyasa Haberleri")
        st.warning(f"Haber yuklenirken hata: {e}")
        return

    st.subheader("Piyasa Haberleri")

    if not events:
        api_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
        if not api_key:
            st.caption("CRYPTOPANIC_API_KEY env variable ayarlanmamis.")
        else:
            st.caption("Haber verisi henuz mevcut degil. Bir sonraki toplama dongusunde gorunecek.")
        return

    for e in events:
        sentiment_icon = {"bullish": "🟢", "bearish": "🔴", "neutral": "⚪"}.get(e["sentiment"], "⚪")
        symbols_str = ", ".join(e["symbols"][:5]) if e["symbols"] else ""
        important = " ⭐" if e["is_important"] else ""
        st.caption(f"{sentiment_icon} {e['published_at']} | {symbols_str} | {e['title'][:100]}{important}")


def _render_regime_map():
    """Regime map — cached (TTL=120s)."""
    st.subheader("Piyasa Rejimleri")

    regimes = get_regime_map_cached()
    if regimes:
        cols = st.columns(6)
        for i, r in enumerate(regimes):
            col = cols[i % 6]
            clean_sym = r["symbol"].replace("/USDT:USDT", "")
            label = REGIME_LABELS.get(r["regime_label"], r["regime_label"])
            color = REGIME_COLORS.get(r["regime_label"], "#999")
            col.markdown(
                f'<span style="background-color:{color};color:white;padding:2px 8px;'
                f'border-radius:10px;font-size:12px;">{clean_sym}: {label}</span>',
                unsafe_allow_html=True,
            )
    else:
        st.caption("Rejim verisi henuz mevcut degil. Market Data Collector ilk calistiginda gorunecek.")


def _render_funding_table():
    """Funding rate table — cached (TTL=120s)."""
    st.subheader("Funding Rate & Open Interest")

    funding_data = get_funding_data_cached()
    if funding_data:
        rows = []
        for f in funding_data:
            rows.append({
                "Coin": f["symbol"].replace("/USDT:USDT", ""),
                "Funding Rate": f"{f['funding_rate'] * 100:.4f}%" if f["funding_rate"] else "-",
                "Open Interest": f"${f['open_interest']:,.0f}" if f["open_interest"] else "-",
                "Spread": f"{f['spread_pct']:.4f}%" if f["spread_pct"] else "-",
                "Guncelleme": f["timestamp"],
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", height=300)
    else:
        st.caption("Funding verisi henuz mevcut degil.")


def _render_data_coverage():
    """Data coverage — cached (TTL=300s)."""
    st.subheader("Veri Kapsami")

    coverage = get_data_coverage_summary_cached()
    if coverage:
        rows = []
        for c in coverage:
            rows.append({
                "Coin": c["symbol"].replace("/USDT:USDT", ""),
                "Mum Sayisi": c["cnt"],
                "Ilk Veri": c["earliest"],
                "Son Veri": c["latest"],
            })
        rows.sort(key=lambda r: r["Mum Sayisi"], reverse=True)
        st.dataframe(pd.DataFrame(rows), width="stretch", height=400)
    else:
        st.info("Henuz veri yok. Collector ilk calistiginda otomatik eklenecek.")


def _render_best_strategies():
    """Best strategies per coin — cached (TTL=300s)."""
    st.subheader("Coin Bazli En Iyi Strateji")

    configs = get_best_strategies_cached()
    if configs:
        rows = []
        for c in configs:
            rows.append({
                "Coin": c["symbol"].replace("/USDT:USDT", ""),
                "Strateji": c["strategy_name"],
                "Kaldirac": f"{c['leverage']:.0f}x",
                "Auto": "Evet" if c["auto_trade"] else "Hayir",
                "Win Rate": f"{c['win_rate'] * 100:.1f}%" if c["win_rate"] is not None else "-",
                "Profit Factor": f"{c['profit_factor']:.2f}" if c["profit_factor"] is not None else "-",
                "Sharpe": f"{c['sharpe_ratio']:.2f}" if c["sharpe_ratio"] is not None else "-",
                "Max DD": f"{c['max_drawdown']:.1f}%" if c["max_drawdown"] is not None else "-",
                "Skor": f"{c['composite_score']:.3f}" if c["composite_score"] is not None else "-",
                "Paper WR": f"{c['paper_win_rate'] * 100:.1f}%" if c["paper_win_rate"] is not None else "-",
            })
        st.dataframe(pd.DataFrame(rows), width="stretch")
    else:
        st.info("Henuz strateji optimizasyonu yapilmadi.")
