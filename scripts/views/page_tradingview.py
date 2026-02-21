"""
Phalidae v2 - TradingView Canli Grafik
TradingView Lightweight Charts v4 ile OHLCV + trade overlay.
"""

import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone

from commentary import generate_page_header
from views.cache import (
    get_ohlcv_cached,
    get_open_trades_cached,
    get_closed_trades_cached,
)


def render():
    generate_page_header("TradingView")
    st.title("TradingView Canli Grafik")
    st.caption("Bot islemlerini canli grafik uzerinde takip edin.")

    # --- Kontroller ---
    open_trades = get_open_trades_cached()
    open_symbols = sorted(set(t["symbol"] for t in open_trades))

    if not open_symbols:
        st.warning("Acik islem bulunamadi. Bot islem actiktan sonra burada gorunecek.")
        return

    display_names = [s.replace("/USDT:USDT", "") for s in open_symbols]

    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        sel_idx = st.selectbox(
            "Coin",
            range(len(open_symbols)),
            format_func=lambda i: display_names[i],
        )
        selected_symbol = open_symbols[sel_idx]
        coin_name = display_names[sel_idx]
    with col2:
        tf_options = ["5m", "15m", "30m", "1h", "4h"]
        selected_tf = st.selectbox("Timeframe", tf_options, index=3)
    with col3:
        candle_count = st.slider("Mum Sayisi", 100, 1000, 300, step=50)

    # --- Grafik (auto-refresh fragment) ---
    @st.fragment(run_every=60)
    def _chart_fragment():
        ohlcv = get_ohlcv_cached(selected_symbol, selected_tf, candle_count)
        if not ohlcv:
            st.info(f"{coin_name} / {selected_tf} icin veri bulunamadi.")
            return

        # Trade verileri
        open_trades = [
            t for t in get_open_trades_cached() if t["symbol"] == selected_symbol
        ]
        closed_trades = [
            t for t in get_closed_trades_cached(limit=50)
            if t["symbol"] == selected_symbol
        ][:20]

        # Overlay verileri
        price_lines = _build_price_lines(open_trades)
        markers = _build_markers(open_trades, closed_trades, ohlcv)

        html = _build_chart_html(ohlcv, price_lines, markers, coin_name, selected_tf)
        components.html(html, height=560, scrolling=False)

        # Trade info paneli
        _render_trade_info(open_trades, closed_trades)

    _chart_fragment()


# ---------------------------------------------------------------------------
# Price lines (acik tradelerin entry/TP/SL cizgileri)
# ---------------------------------------------------------------------------

def _build_price_lines(open_trades: list[dict]) -> list[dict]:
    """Acik tradelerin yatay cizgileri — Lightweight Charts priceLine API."""
    lines = []
    for t in open_trades:
        bias = t["bias"]

        # Entry
        lines.append({
            "price": t["entry_price"],
            "color": "#FFD700",
            "lineWidth": 2,
            "lineStyle": 0,  # solid
            "title": f"Entry ({bias})",
        })

        # TP levels
        tp_levels = [
            ("partial_tp_price", "TP1"),
            ("tp_price", "TP2"),
            ("tp2_price", "TP2"),
            ("tp3_price", "TP3"),
        ]
        for key, label in tp_levels:
            val = t.get(key)
            if val and not t.get("partial_tp_taken", False) if key == "partial_tp_price" else val:
                lines.append({
                    "price": val,
                    "color": "#26a69a",
                    "lineWidth": 1,
                    "lineStyle": 2,  # dashed
                    "title": label,
                })

        # SL
        if t["sl_price"]:
            lines.append({
                "price": t["sl_price"],
                "color": "#ef5350",
                "lineWidth": 1,
                "lineStyle": 2,  # dashed
                "title": "SL",
            })

        # Trailing SL
        if t.get("trailing_stop_price"):
            lines.append({
                "price": t["trailing_stop_price"],
                "color": "#FF8C00",
                "lineWidth": 1,
                "lineStyle": 3,  # dotted
                "title": "Trail SL",
            })

    return lines


# ---------------------------------------------------------------------------
# Markers (ok isaretleri — giris/cikis)
# ---------------------------------------------------------------------------

def _build_markers(
    open_trades: list[dict],
    closed_trades: list[dict],
    ohlcv: list[dict],
) -> list[dict]:
    """Trade giris/cikis noktalarini marker olarak doner."""
    markers = []

    def _find_nearest_time(ts_iso: str | None, ts_short: str | None) -> int | None:
        """Trade zamanina en yakin mum zamanini bul."""
        if not ohlcv:
            return None

        target_ts = None
        if ts_iso:
            try:
                dt = datetime.fromisoformat(ts_iso)
                target_ts = int(dt.replace(tzinfo=None).timestamp())
            except (ValueError, TypeError):
                pass

        if target_ts is None and ts_short:
            try:
                # Format: "MM-DD HH:MM" — bu yilin tarihini varsay
                now = datetime.utcnow()
                dt = datetime.strptime(ts_short, "%m-%d %H:%M").replace(year=now.year)
                target_ts = int(dt.timestamp())
            except (ValueError, TypeError):
                return None

        if target_ts is None:
            return None

        # En yakin mumu bul
        best_time = ohlcv[0]["time"]
        best_diff = abs(ohlcv[0]["time"] - target_ts)
        for candle in ohlcv:
            diff = abs(candle["time"] - target_ts)
            if diff < best_diff:
                best_diff = diff
                best_time = candle["time"]
        return best_time

    # Acik trade giris oklari
    for t in open_trades:
        time_val = _find_nearest_time(None, t.get("opened_at"))
        if time_val is None:
            continue
        is_long = t["bias"] == "LONG"
        markers.append({
            "time": time_val,
            "position": "belowBar" if is_long else "aboveBar",
            "color": "#26a69a" if is_long else "#ef5350",
            "shape": "arrowUp" if is_long else "arrowDown",
            "text": f"{t['bias']} Entry",
        })

    # Kapali trade giris + cikis
    for t in closed_trades:
        is_long = t["bias"] == "LONG"
        pnl = t.get("pnl_percent", 0)
        is_win = pnl > 0

        # Giris
        entry_time = _find_nearest_time(t.get("opened_at"), None)
        if entry_time is not None:
            markers.append({
                "time": entry_time,
                "position": "belowBar" if is_long else "aboveBar",
                "color": "#26a69a" if is_long else "#ef5350",
                "shape": "arrowUp" if is_long else "arrowDown",
                "text": t["bias"],
            })

        # Cikis
        exit_time = _find_nearest_time(t.get("closed_at"), None)
        if exit_time is not None:
            markers.append({
                "time": exit_time,
                "position": "aboveBar" if is_long else "belowBar",
                "color": "#26a69a" if is_win else "#ef5350",
                "shape": "circle",
                "text": f"{pnl:+.1f}%",
            })

    # Zamana gore sirala (Lightweight Charts gerekliligi)
    markers.sort(key=lambda m: m["time"])
    return markers


# ---------------------------------------------------------------------------
# Chart HTML (Lightweight Charts v4)
# ---------------------------------------------------------------------------

def _build_chart_html(
    ohlcv: list[dict],
    price_lines: list[dict],
    markers: list[dict],
    coin_name: str,
    timeframe: str,
) -> str:
    """TradingView Lightweight Charts v4 HTML — CDN'den yuklenir."""
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

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: #0e1117; overflow: hidden; }}
  #chart {{ width: 100%; height: 520px; }}
  #legend {{
    position: absolute; top: 8px; left: 12px; z-index: 10;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 12px; color: #d1d4dc; pointer-events: none;
  }}
  #legend .title {{ font-size: 14px; font-weight: 600; margin-bottom: 2px; }}
  #legend .ohlc {{ color: #aaa; }}
  #legend .up {{ color: #26a69a; }}
  #legend .down {{ color: #ef5350; }}
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
    height: 520,
    layout: {{
      background: {{ type: 'solid', color: '#0e1117' }},
      textColor: '#d1d4dc',
    }},
    grid: {{
      vertLines: {{ color: 'rgba(42, 46, 57, 0.5)' }},
      horzLines: {{ color: 'rgba(42, 46, 57, 0.5)' }},
    }},
    crosshair: {{
      mode: LightweightCharts.CrosshairMode.Normal,
    }},
    rightPriceScale: {{
      borderColor: 'rgba(197, 203, 206, 0.3)',
    }},
    timeScale: {{
      borderColor: 'rgba(197, 203, 206, 0.3)',
      timeVisible: true,
      secondsVisible: false,
    }},
  }});

  // Candlestick series
  const candleSeries = chart.addCandlestickSeries({{
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderDownColor: '#ef5350',
    borderUpColor: '#26a69a',
    wickDownColor: '#ef5350',
    wickUpColor: '#26a69a',
  }});

  const ohlcvData = {ohlcv_json};
  candleSeries.setData(ohlcvData);

  // Volume histogram
  const volumeSeries = chart.addHistogramSeries({{
    priceFormat: {{ type: 'volume' }},
    priceScaleId: 'volume',
  }});
  chart.priceScale('volume').applyOptions({{
    scaleMargins: {{ top: 0.8, bottom: 0 }},
  }});
  volumeSeries.setData({volume_data});

  // Price lines (entry/TP/SL)
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

  // Markers (trade entry/exit arrows)
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

  // Fit content
  chart.timeScale().fitContent();

  // Responsive
  new ResizeObserver(function() {{
    chart.applyOptions({{ width: chartEl.clientWidth }});
  }}).observe(chartEl);
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Trade info paneli (grafik altinda)
# ---------------------------------------------------------------------------

def _render_trade_info(open_trades: list[dict], closed_trades: list[dict]):
    """Grafik altinda acik/kapali trade detaylari."""
    if not open_trades and not closed_trades:
        return

    # --- Acik islemler ---
    if open_trades:
        st.subheader(f"Acik Islemler ({len(open_trades)})")
        for t in open_trades:
            bias_icon = "LONG" if t["bias"] == "LONG" else "SHORT"
            tp_status = ""
            if t.get("partial_tp_taken"):
                tp_status = " | TP1 alindi"

            cols = st.columns([1, 1, 1, 1, 1])
            cols[0].metric("Yon", bias_icon)
            cols[1].metric("Entry", f"${t['entry_price']:,.4f}" if t["entry_price"] < 1 else f"${t['entry_price']:,.2f}")
            tp_val = t.get("tp_price") or t.get("tp2_price")
            cols[2].metric("TP", f"${tp_val:,.4f}" if tp_val and tp_val < 1 else (f"${tp_val:,.2f}" if tp_val else "-"))
            cols[3].metric("SL", f"${t['sl_price']:,.4f}" if t["sl_price"] and t["sl_price"] < 1 else (f"${t['sl_price']:,.2f}" if t["sl_price"] else "-"))
            trail = t.get("trailing_stop_price")
            cols[4].metric("Trail SL", f"${trail:,.4f}" if trail and trail < 1 else (f"${trail:,.2f}" if trail else "-"))

            detail_cols = st.columns([1, 1, 1, 1, 1])
            detail_cols[0].caption(f"MFE: {t['mfe_pct']:.2f}%")
            detail_cols[1].caption(f"MAE: {t['mae_pct']:.2f}%")
            detail_cols[2].caption(f"Rejim: {t.get('regime_at_entry', '-')}")
            detail_cols[3].caption(f"Giris: {t.get('opened_at', '-')}")
            detail_cols[4].caption(f"Multi-TP{tp_status}")
            st.divider()

    # --- Kapali islemler ---
    if closed_trades:
        st.subheader(f"Son Kapali Islemler ({len(closed_trades)})")
        import pandas as pd
        rows = []
        for t in closed_trades:
            pnl = t.get("pnl_percent", 0)
            rows.append({
                "Yon": t["bias"],
                "Durum": t["status"],
                "Entry": t["entry_price"],
                "Exit": t.get("exit_price") or 0,
                "P&L%": f"{pnl:+.2f}%",
                "P&L$": f"${t.get('pnl_usd', 0):+.2f}",
                "Sure": t.get("duration", "-"),
                "Cikis": t.get("exit_reason", "-"),
                "Rejim": t.get("regime_at_entry", "-"),
            })
        if rows:
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=min(len(rows) * 38 + 40, 400))
