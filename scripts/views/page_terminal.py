"""
Phalidae v2 - Trading Terminal Page
TradingView-style main screen: Watchlist + Chart + Detail Panel + Bottom Tabs.
"""

import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta

from views.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_SURFACE,
    BORDER_DEFAULT, BORDER_ACTIVE,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BULL, BEAR, BULL_BG, BEAR_BG,
    ACCENT_BLUE, ACCENT_YELLOW, ACCENT_PURPLE,
    REGIME_COLORS, REGIME_LABELS,
    metric_strip_html, status_dot_html, pnl_colored_html, regime_badge_html,
)
from views.components import (
    render_top_bar,
    render_watchlist,
    render_bottom_panel_trades,
    render_bottom_panel_signals,
    render_signal_detail,
)
from views.cache import (
    get_portfolio_summary_cached,
    get_daily_pnl_cached,
    get_open_trades_cached,
    get_closed_trades_cached,
    get_recent_signals_cached,
    get_ohlcv_cached,
    get_watchlist_data_cached,
    get_agent_health_cached,
    get_system_stats_cached,
    get_portfolio_snapshots_cached,
    get_regime_map_cached,
)

# Reuse chart-building functions from existing TradingView page
from views.page_tradingview import (
    _calc_ema,
    _build_price_lines,
    _build_markers,
)


def render():
    """Main Trading Terminal page."""

    # --- Initialize session state ---
    if "selected_symbol" not in st.session_state:
        # Default to first open trade's symbol, or first tracked symbol
        open_trades = get_open_trades_cached()
        if open_trades:
            st.session_state["selected_symbol"] = open_trades[0]["symbol"]
        else:
            watchlist = get_watchlist_data_cached()
            if watchlist:
                st.session_state["selected_symbol"] = watchlist[0]["symbol"]
            else:
                st.session_state["selected_symbol"] = ""

    if "selected_timeframe" not in st.session_state:
        st.session_state["selected_timeframe"] = "1h"

    # --- Top Bar ---
    render_top_bar()

    # --- Proximity Alerts (compact) ---
    _render_proximity_alerts_compact()

    # --- 3-Panel Layout: Watchlist | Chart | Detail ---
    col_wl, col_chart, col_detail = st.columns([1.5, 5, 2.5])

    with col_wl:
        _render_watchlist_panel()

    with col_chart:
        _render_chart_panel()

    with col_detail:
        _render_detail_panel()

    # --- Bottom Panel (tabbed) ---
    st.markdown(
        f'<div style="border-top:1px solid {BORDER_DEFAULT};margin-top:4px;"></div>',
        unsafe_allow_html=True,
    )
    _render_bottom_panel()


# ---------------------------------------------------------------------------
# Watchlist Panel
# ---------------------------------------------------------------------------

def _render_watchlist_panel():
    """Left panel — watchlist with search and clickable rows."""
    watchlist = get_watchlist_data_cached()
    selected = st.session_state.get("selected_symbol", "")

    # Enrich with unrealized P&L from open trades
    open_trades = get_open_trades_cached()
    trade_map: dict[str, dict] = {}
    for t in open_trades:
        trade_map[t["symbol"]] = t

    for w in watchlist:
        sym = w["symbol"]
        if sym in trade_map:
            t = trade_map[sym]
            w["has_open_trade"] = True
            # Calculate unrealized P&L using latest 1h candle
            candles = get_ohlcv_cached(sym, "1h", 1)
            if candles:
                price = candles[-1]["close"]
                entry = t["entry_price"]
                leverage = t.get("leverage", 5.0)
                if price and entry:
                    if t["bias"] == "LONG":
                        pnl = ((price - entry) / entry) * 100 * leverage
                    else:
                        pnl = ((entry - price) / entry) * 100 * leverage
                    w["unrealized_pnl_pct"] = round(pnl, 2)

    render_watchlist(watchlist, selected)


# ---------------------------------------------------------------------------
# Chart Panel
# ---------------------------------------------------------------------------

def _render_chart_panel():
    """Center panel — Lightweight Charts v4 candlestick chart."""
    selected = st.session_state.get("selected_symbol", "")
    if not selected:
        st.info("Watchlist'ten bir coin secin.")
        return

    coin_name = selected.replace("/USDT:USDT", "")

    # Timeframe selector
    tf_options = ["5m", "15m", "30m", "1h", "4h"]
    current_tf = st.session_state.get("selected_timeframe", "1h")
    current_idx = tf_options.index(current_tf) if current_tf in tf_options else 3

    sel_tf = st.radio(
        "tf_select",
        tf_options,
        index=current_idx,
        horizontal=True,
        label_visibility="collapsed",
        key="tf_radio",
    )
    if sel_tf != st.session_state.get("selected_timeframe"):
        st.session_state["selected_timeframe"] = sel_tf

    @st.fragment(run_every=60)
    def _chart_fragment():
        tf = st.session_state.get("selected_timeframe", "1h")
        sym = st.session_state.get("selected_symbol", "")
        if not sym:
            return

        ohlcv = get_ohlcv_cached(sym, tf, 300)
        if not ohlcv:
            st.info(f"{sym.replace('/USDT:USDT', '')} / {tf} icin veri bulunamadi.")
            return

        # Trade data
        sym_open_trades = [
            t for t in get_open_trades_cached() if t["symbol"] == sym
        ]
        closed_trades = [
            t for t in get_closed_trades_cached(limit=50)
            if t["symbol"] == sym
        ][:20]

        sym_signals = [
            s for s in get_recent_signals_cached(limit=100)
            if s["symbol"] == sym
        ][:20]

        current_price = ohlcv[-1]["close"] if ohlcv else 0

        # EMAs
        ema21 = _calc_ema(ohlcv, 21)
        ema55 = _calc_ema(ohlcv, 55)

        # Overlays
        price_lines = _build_price_lines(sym_open_trades, current_price)
        markers = _build_markers(sym_open_trades, closed_trades, ohlcv, sym_signals)

        html = _build_terminal_chart_html(
            ohlcv, price_lines, markers,
            sym.replace("/USDT:USDT", ""), tf,
            ema21=ema21, ema55=ema55,
        )
        components.html(html, height=580, scrolling=False)

    _chart_fragment()


def _build_terminal_chart_html(
    ohlcv: list[dict],
    price_lines: list[dict],
    markers: list[dict],
    coin_name: str,
    timeframe: str,
    ema21: list[dict] | None = None,
    ema55: list[dict] | None = None,
) -> str:
    """TradingView Lightweight Charts v4 HTML — dark theme matching terminal."""
    ohlcv_json = json.dumps(ohlcv)
    volume_data = json.dumps([
        {
            "time": c["time"],
            "value": c["volume"],
            "color": "rgba(38,166,154,0.3)" if c["close"] >= c["open"]
                     else "rgba(239,83,80,0.3)",
        }
        for c in ohlcv
    ])
    price_lines_json = json.dumps(price_lines)
    markers_json = json.dumps(markers)
    ema21_json = json.dumps(ema21 or [])
    ema55_json = json.dumps(ema55 or [])

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: {BG_PRIMARY}; overflow: hidden; }}
  #chart {{ width: 100%; height: 560px; }}
  #legend {{
    position: absolute; top: 8px; left: 12px; z-index: 10;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 12px; color: {TEXT_PRIMARY}; pointer-events: none;
  }}
  #legend .title {{ font-size: 14px; font-weight: 600; margin-bottom: 2px; }}
  #legend .ohlc {{ color: #aaa; }}
  #legend .up {{ color: {BULL}; }}
  #legend .down {{ color: {BEAR}; }}
</style>
</head>
<body>
<div id="legend">
  <div class="title">{coin_name} / {timeframe}</div>
  <div id="ohlc-info" class="ohlc"></div>
</div>
<div id="chart"></div>
<script>
(function() {{
  const chartEl = document.getElementById('chart');
  const chart = LightweightCharts.createChart(chartEl, {{
    width: chartEl.clientWidth,
    height: 560,
    layout: {{
      background: {{ type: 'solid', color: '{BG_PRIMARY}' }},
      textColor: '{TEXT_PRIMARY}',
    }},
    grid: {{
      vertLines: {{ color: 'rgba(54, 58, 69, 0.5)' }},
      horzLines: {{ color: 'rgba(54, 58, 69, 0.5)' }},
    }},
    crosshair: {{
      mode: LightweightCharts.CrosshairMode.Normal,
    }},
    rightPriceScale: {{
      borderColor: '{BORDER_DEFAULT}',
    }},
    timeScale: {{
      borderColor: '{BORDER_DEFAULT}',
      timeVisible: true,
      secondsVisible: false,
    }},
  }});

  const candleSeries = chart.addCandlestickSeries({{
    upColor: '{BULL}',
    downColor: '{BEAR}',
    borderDownColor: '{BEAR}',
    borderUpColor: '{BULL}',
    wickDownColor: '{BEAR}',
    wickUpColor: '{BULL}',
  }});

  candleSeries.setData({ohlcv_json});

  // Volume histogram
  const volumeSeries = chart.addHistogramSeries({{
    priceFormat: {{ type: 'volume' }},
    priceScaleId: 'volume',
  }});
  chart.priceScale('volume').applyOptions({{
    scaleMargins: {{ top: 0.8, bottom: 0 }},
  }});
  volumeSeries.setData({volume_data});

  // EMA 21 (yellow)
  const ema21Data = {ema21_json};
  if (ema21Data.length > 0) {{
    const ema21Series = chart.addLineSeries({{
      color: '#FFD700',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }});
    ema21Series.setData(ema21Data);
  }}

  // EMA 55 (purple)
  const ema55Data = {ema55_json};
  if (ema55Data.length > 0) {{
    const ema55Series = chart.addLineSeries({{
      color: '{ACCENT_PURPLE}',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }});
    ema55Series.setData(ema55Data);
  }}

  // Price lines
  const priceLines = {price_lines_json};
  priceLines.forEach(function(pl) {{
    candleSeries.createPriceLine({{
      price: pl.price,
      color: pl.color,
      lineWidth: pl.lineWidth,
      lineStyle: pl.lineStyle,
      axisLabelVisible: true,
      title: pl.title,
    }});
  }});

  // Markers
  const markers = {markers_json};
  if (markers.length > 0) {{
    candleSeries.setMarkers(markers);
  }}

  // Crosshair legend
  chart.subscribeCrosshairMove(function(param) {{
    const infoEl = document.getElementById('ohlc-info');
    if (!param || !param.time || !param.seriesData || !param.seriesData.get(candleSeries)) {{
      infoEl.innerHTML = '';
      return;
    }}
    const d = param.seriesData.get(candleSeries);
    if (!d) return;
    const change = d.close - d.open;
    const pct = d.open !== 0 ? (change / d.open * 100).toFixed(2) : '0.00';
    const cls = change >= 0 ? 'up' : 'down';
    const sign = change >= 0 ? '+' : '';
    infoEl.innerHTML =
      'O <span class="' + cls + '">' + d.open.toFixed(6) + '</span> ' +
      'H <span class="' + cls + '">' + d.high.toFixed(6) + '</span> ' +
      'L <span class="' + cls + '">' + d.low.toFixed(6) + '</span> ' +
      'C <span class="' + cls + '">' + d.close.toFixed(6) + '</span> ' +
      '<span class="' + cls + '">(' + sign + pct + '%)</span>';
  }});

  chart.timeScale().fitContent();

  new ResizeObserver(function() {{
    chart.applyOptions({{ width: chartEl.clientWidth }});
  }}).observe(chartEl);
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Detail Panel
# ---------------------------------------------------------------------------

def _render_detail_panel():
    """Right panel — dynamic content based on selected coin's state."""
    selected = st.session_state.get("selected_symbol", "")
    if not selected:
        st.caption("Coin secilmedi.")
        return

    coin_name = selected.replace("/USDT:USDT", "")

    # Check for open trade
    open_trades = get_open_trades_cached()
    sym_trade = next((t for t in open_trades if t["symbol"] == selected), None)

    # Check for latest signal
    signals = get_recent_signals_cached(limit=100)
    sym_signal = next((s for s in signals if s.get("symbol") == selected), None)

    # Regime
    regime_map = get_regime_map_cached()
    regime = next((r["regime_label"] for r in regime_map if r["symbol"] == selected), "")

    st.markdown(
        f'<div style="font-size:14px;font-weight:600;color:{TEXT_PRIMARY};'
        f'padding-bottom:4px;border-bottom:1px solid {BORDER_DEFAULT};">'
        f'{coin_name} {regime_badge_html(regime)}</div>',
        unsafe_allow_html=True,
    )

    if sym_trade:
        _render_open_trade_detail(sym_trade, selected)
    elif sym_signal:
        render_signal_detail(sym_signal)
    else:
        st.caption("Acik islem veya sinyal bulunamadi.")
        if regime:
            st.markdown(
                f'<div style="font-size:11px;color:{TEXT_SECONDARY};margin-top:8px;">'
                f'Rejim: {REGIME_LABELS.get(regime, regime)}</div>',
                unsafe_allow_html=True,
            )


def _render_open_trade_detail(trade: dict, symbol: str):
    """Detail view for an open trade."""
    bias = trade["bias"]
    entry = trade["entry_price"]
    leverage = trade.get("leverage", 5.0)
    size_usd = trade.get("position_size_usd") or 200

    # Current price from latest candle
    candles = get_ohlcv_cached(symbol, "1h", 1)
    current_price = candles[-1]["close"] if candles else 0

    # Calculate unrealized P&L
    pnl_pct = 0.0
    pnl_usd = 0.0
    if current_price and entry:
        if bias == "LONG":
            pnl_pct = ((current_price - entry) / entry) * 100 * leverage
        else:
            pnl_pct = ((entry - current_price) / entry) * 100 * leverage
        pnl_usd = size_usd * (pnl_pct / 100)

    bias_color = BULL if bias == "LONG" else BEAR

    # Direction
    st.markdown(
        f'<div style="font-size:13px;font-weight:600;color:{bias_color};margin-top:8px;">'
        f'{bias} {leverage:.0f}x</div>',
        unsafe_allow_html=True,
    )

    # P&L
    pnl_color = BULL if pnl_pct >= 0 else BEAR
    st.markdown(
        f'<div style="font-size:18px;font-weight:700;color:{pnl_color};'
        f'font-family:monospace;margin:4px 0;">'
        f'{pnl_pct:+.2f}%</div>'
        f'<div style="font-size:12px;color:{pnl_color};font-family:monospace;">'
        f'${pnl_usd:+,.2f}</div>',
        unsafe_allow_html=True,
    )

    # Entry & levels
    st.markdown(
        f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-top:8px;'
        f'font-weight:500;">SEVIYELERI</div>',
        unsafe_allow_html=True,
    )

    def _level_row(label: str, value: float | None, color: str = TEXT_PRIMARY):
        if value:
            fmt = f"${value:,.4f}" if value < 1 else f"${value:,.2f}"
            st.markdown(
                f'<div style="display:flex;justify-content:space-between;'
                f'font-size:11px;padding:2px 0;">'
                f'<span style="color:{TEXT_SECONDARY};">{label}</span>'
                f'<span style="color:{color};font-family:monospace;">{fmt}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    _level_row("Entry", entry)
    _level_row("TP1", trade.get("partial_tp_price"), BULL)
    _level_row("TP2", trade.get("tp_price") or trade.get("tp2_price"), BULL)
    _level_row("TP3", trade.get("tp3_price"), BULL)
    _level_row("SL", trade.get("sl_price"), BEAR)
    _level_row("Trail SL", trade.get("trailing_stop_price"), ACCENT_YELLOW)

    # MFE/MAE
    mfe = trade.get("mfe_pct", 0)
    mae = trade.get("mae_pct", 0)
    st.markdown(
        f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-top:8px;'
        f'font-weight:500;">ISTATISTIKLER</div>'
        f'<div style="font-size:11px;padding:2px 0;">'
        f'<span style="color:{TEXT_SECONDARY};">MFE:</span> '
        f'<span style="color:{BULL};font-family:monospace;">{mfe:.2f}%</span>'
        f'</div>'
        f'<div style="font-size:11px;padding:2px 0;">'
        f'<span style="color:{TEXT_SECONDARY};">MAE:</span> '
        f'<span style="color:{BEAR};font-family:monospace;">{mae:.2f}%</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Position info
    st.markdown(
        f'<div style="font-size:10px;color:{TEXT_SECONDARY};margin-top:6px;">'
        f'Boyut: ${size_usd:,.0f} | '
        f'Giris: {trade.get("opened_at", "-")}</div>',
        unsafe_allow_html=True,
    )

    if trade.get("partial_tp_taken"):
        st.markdown(
            f'<div style="font-size:10px;color:{BULL};margin-top:2px;">'
            f'TP1 alinmis</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Proximity Alerts (compact)
# ---------------------------------------------------------------------------

def _render_proximity_alerts_compact():
    """Compact proximity alerts in top bar area."""
    open_trades = get_open_trades_cached()
    if not open_trades:
        return

    alerts = []
    for t in open_trades:
        sym = t["symbol"]
        coin = sym.replace("/USDT:USDT", "")

        candles = get_ohlcv_cached(sym, "1h", 1)
        if not candles:
            continue
        price = candles[-1]["close"]

        sl = t.get("sl_price") or 0
        tp = t.get("tp_price") or t.get("tp2_price") or 0
        trail = t.get("trailing_stop_price") or 0
        effective_sl = trail if trail else sl

        if effective_sl and effective_sl > 0:
            sl_dist = abs(price - effective_sl) / price * 100
            if sl_dist <= 2.0:
                alerts.append(("sl", coin, sl_dist))

        if tp and tp > 0:
            tp_dist = abs(tp - price) / price * 100
            if tp_dist <= 2.0:
                alerts.append(("tp", coin, tp_dist))

    if alerts:
        pills = []
        for kind, coin, dist in alerts:
            if kind == "sl":
                pills.append(
                    f'<span style="background:{BEAR_BG};color:{BEAR};'
                    f'padding:2px 8px;border-radius:10px;font-size:11px;'
                    f'margin-right:4px;">{coin} SL %{dist:.1f}</span>'
                )
            else:
                pills.append(
                    f'<span style="background:{BULL_BG};color:{BULL};'
                    f'padding:2px 8px;border-radius:10px;font-size:11px;'
                    f'margin-right:4px;">{coin} TP %{dist:.1f}</span>'
                )
        st.markdown(
            f'<div style="padding:2px 12px;">{"".join(pills)}</div>',
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Bottom Panel
# ---------------------------------------------------------------------------

def _render_bottom_panel():
    """Bottom tabbed panel: Open Trades | Closed | Signals | System | News."""
    tab_open, tab_closed, tab_signals, tab_system, tab_news = st.tabs([
        "Acik Islemler", "Kapali Islemler", "Sinyaller", "Sistem", "Haberler",
    ])

    with tab_open:
        _render_tab_open_trades()

    with tab_closed:
        _render_tab_closed_trades()

    with tab_signals:
        _render_tab_signals()

    with tab_system:
        _render_tab_system()

    with tab_news:
        _render_tab_news()


@st.fragment(run_every=30)
def _render_tab_open_trades():
    """Open trades tab with auto-refresh."""
    trades = get_open_trades_cached()
    if not trades:
        st.caption("Acik islem yok.")
        return

    # Enrich with current price P&L
    rows = []
    for t in trades:
        coin = t["symbol"].replace("/USDT:USDT", "")
        entry = t["entry_price"]
        leverage = t.get("leverage", 5.0)
        size_usd = t.get("position_size_usd") or 200

        candles = get_ohlcv_cached(t["symbol"], "1h", 1)
        price = candles[-1]["close"] if candles else 0
        pnl_pct = 0.0
        if price and entry:
            if t["bias"] == "LONG":
                pnl_pct = ((price - entry) / entry) * 100 * leverage
            else:
                pnl_pct = ((entry - price) / entry) * 100 * leverage

        rows.append({
            "Coin": coin,
            "Yon": t["bias"],
            "Giris": f"${entry:,.4f}" if entry < 1 else f"${entry:,.2f}",
            "P&L": f"{pnl_pct:+.2f}%",
            "TP": f"${t['tp_price']:,.2f}" if t.get("tp_price") else "-",
            "SL": f"${t['sl_price']:,.2f}" if t.get("sl_price") else "-",
            "Trail": f"${t['trailing_stop_price']:,.2f}" if t.get("trailing_stop_price") else "-",
            "Boyut": f"${size_usd:,.0f}",
            "Rejim": REGIME_LABELS.get(t.get("regime_at_entry", ""), "-"),
            "Acilis": t.get("opened_at", "-"),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(len(rows) * 36 + 40, 350))


def _render_tab_closed_trades():
    """Closed trades tab."""
    trades = get_closed_trades_cached(limit=50)
    render_bottom_panel_trades(trades, mode="closed")


@st.fragment(run_every=60)
def _render_tab_signals():
    """Signals tab with auto-refresh."""
    signals = get_recent_signals_cached(limit=50)
    render_bottom_panel_signals(signals)


@st.fragment(run_every=45)
def _render_tab_system():
    """System health tab."""
    health = get_agent_health_cached()
    stats = get_system_stats_cached()

    # System stats row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("OHLCV Veri", f"{stats['total_candles']:,}")
    c2.metric("Aktif Coin", stats['active_symbols'])
    c3.metric("Strateji", stats['total_variants'])
    c4.metric("Toplam P&L", f"${stats['total_pnl']:+,.2f}")

    # Agent health table
    JOB_LABELS = {
        "collector": "Collector",
        "analyzer": "Analyzer",
        "trade_checker": "Trade Check",
        "optimizer": "Optimizer",
        "market_data": "Market Data",
        "symbol_refresh": "Sym Refresh",
        "news_collector": "News",
    }
    JOB_INTERVALS = {
        "collector": 5, "analyzer": 15, "trade_checker": 5,
        "optimizer": 360, "market_data": 15, "symbol_refresh": 1440,
        "news_collector": 15,
    }

    now = datetime.utcnow()
    rows = []
    for job_name in JOB_LABELS:
        job_info = health["jobs"].get(job_name)
        if not job_info:
            rows.append({
                "Job": JOB_LABELS[job_name],
                "Durum": "Bekleniyor",
                "Son": "-",
                "Sure": "-",
            })
            continue

        completed_at = None
        if job_info["completed_at"]:
            completed_at = datetime.fromisoformat(job_info["completed_at"])

        interval_min = JOB_INTERVALS.get(job_name, 60)
        age_min = (now - completed_at).total_seconds() / 60 if completed_at else 999

        if job_info["status"] == "FAILED":
            status = "HATA"
        elif job_info["status"] == "RUNNING":
            status = "Calisiyor"
        elif age_min > interval_min * 3:
            status = "Eski"
        else:
            status = "Aktif"

        if completed_at:
            delta = now - completed_at
            if delta.total_seconds() < 3600:
                age_str = f"{delta.total_seconds() / 60:.0f}dk"
            else:
                age_str = f"{delta.total_seconds() / 3600:.1f}sa"
        else:
            age_str = "-"

        rows.append({
            "Job": JOB_LABELS[job_name],
            "Durum": status,
            "Son": age_str,
            "Sure": f"{job_info['duration_sec']:.1f}s" if job_info.get("duration_sec") else "-",
        })

    df = pd.DataFrame(rows)

    def _color_status(val):
        if val == "Aktif":
            return f"color: {BULL}"
        elif val == "HATA":
            return f"color: {BEAR}; font-weight: bold"
        elif val == "Calisiyor":
            return "color: #42a5f5"
        elif val == "Eski":
            return "color: #ff7043"
        return f"color: {ACCENT_YELLOW}"

    styled = df.style.map(_color_status, subset=["Durum"])
    st.dataframe(styled, use_container_width=True, height=min(len(rows) * 36 + 40, 300))
    st.caption(f"24s: {health['success_24h']} basarili, {health['fail_24h']} hatali")


def _render_tab_news():
    """Market news tab."""
    import os
    try:
        from worker.news_collector import get_todays_events
        events = get_todays_events(limit=15)
    except ImportError:
        events = []
    except Exception:
        st.caption("Haber yuklenirken hata.")
        return

    if not events:
        api_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
        if not api_key:
            st.caption("CRYPTOPANIC_API_KEY env variable ayarlanmamis.")
        else:
            st.caption("Haber verisi henuz mevcut degil.")
        return

    for e in events:
        sentiment_map = {"bullish": BULL, "bearish": BEAR, "neutral": TEXT_MUTED}
        s_color = sentiment_map.get(e.get("sentiment", ""), TEXT_MUTED)
        symbols_str = ", ".join(e.get("symbols", [])[:5])
        important = " *" if e.get("is_important") else ""

        st.markdown(
            f'<div style="font-size:11px;padding:3px 0;border-bottom:1px solid {BORDER_DEFAULT};">'
            f'<span style="color:{s_color};font-weight:600;">●</span> '
            f'<span style="color:{TEXT_SECONDARY};">{e.get("published_at", "")}</span> '
            f'<span style="color:{TEXT_PRIMARY};">{symbols_str}</span> '
            f'<span style="color:{TEXT_SECONDARY};">{e.get("title", "")[:100]}{important}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
