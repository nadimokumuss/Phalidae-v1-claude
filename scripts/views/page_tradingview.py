"""
Phalidae v2 - TradingView Canli Grafik
TradingView Lightweight Charts v4 ile OHLCV + trade overlay.
"""

import json
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timezone, timedelta

from commentary import generate_page_header
from views.cache import (
    get_ohlcv_cached,
    get_open_trades_cached,
    get_closed_trades_cached,
    get_recent_signals_cached,
)


def render():
    generate_page_header("TradingView")
    st.title("TradingView Canli Grafik")
    st.caption("Bot islemlerini canli grafik uzerinde takip edin.")

    # --- Veri yukle ---
    open_trades = get_open_trades_cached()

    if not open_trades:
        st.warning("Acik islem bulunamadi. Bot islem actiktan sonra burada gorunecek.")
        return

    # Her coin icin gercek unrealized P&L% hesapla (son 1h mum close fiyati)
    unique_symbols = sorted(set(t["symbol"] for t in open_trades))
    latest_prices: dict[str, float] = {}
    for sym in unique_symbols:
        candles = get_ohlcv_cached(sym, "1h", 1)
        if candles:
            latest_prices[sym] = candles[-1]["close"]

    # --- [1] Portfoy Ozet Dashboard ---
    _render_portfolio_summary(open_trades, latest_prices)

    # --- [6] Zaman bazli filtre ---
    filter_options = ["Tumu", "Son 1 saat", "Son 4 saat", "Son 1 gun", "Son 3 gun"]
    selected_filter = st.selectbox("Zaman Filtresi", filter_options, index=0)
    filtered_trades = _filter_trades_by_time(open_trades, selected_filter)

    if not filtered_trades:
        st.info("Secilen zaman araliginda acik islem bulunamadi.")
        return

    # P&L hesaplama (filtrelenmis)
    symbol_pnl: dict[str, float] = {}
    for t in filtered_trades:
        sym = t["symbol"]
        entry = t["entry_price"]
        leverage = t.get("leverage", 5.0)
        price = latest_prices.get(sym, 0)
        if price and entry:
            if t["bias"] == "LONG":
                pnl = ((price - entry) / entry) * 100 * leverage
            else:
                pnl = ((entry - price) / entry) * 100 * leverage
        else:
            pnl = 0.0
        symbol_pnl[sym] = symbol_pnl.get(sym, 0) + pnl

    sorted_symbols = sorted(symbol_pnl.keys(), key=lambda s: symbol_pnl[s], reverse=True)
    display_names = [
        f"{s.replace('/USDT:USDT', '')} ({symbol_pnl[s]:+.1f}%)"
        for s in sorted_symbols
    ]

    # --- Kontroller ---
    col1, col2, col3 = st.columns([2, 1, 2])
    with col1:
        sel_idx = st.selectbox(
            "Coin",
            range(len(sorted_symbols)),
            format_func=lambda i: display_names[i],
        )
        selected_symbol = sorted_symbols[sel_idx]
        coin_name = selected_symbol.replace("/USDT:USDT", "")
    with col2:
        tf_options = ["5m", "15m", "30m", "1h", "4h"]
        selected_tf = st.selectbox("Timeframe", tf_options, index=3)
    with col3:
        candle_count = st.slider("Mum Sayisi", 100, 1000, 300, step=50)

    # --- [4] 4'lu gorunum toggle ---
    grid_mode = st.toggle("4'lu Gorunum", value=False)

    # --- [5] SL/TP yakinlik uyarilari ---
    _render_proximity_alerts(filtered_trades, latest_prices)

    # --- [4] 4'lu grid VEYA tekli grafik ---
    if grid_mode:
        _render_mini_grid(sorted_symbols[:4], latest_prices, filtered_trades)
    else:
        # --- Tekli grafik (auto-refresh fragment) ---
        @st.fragment(run_every=60)
        def _chart_fragment():
            ohlcv = get_ohlcv_cached(selected_symbol, selected_tf, candle_count)
            if not ohlcv:
                st.info(f"{coin_name} / {selected_tf} icin veri bulunamadi.")
                return

            # Trade verileri
            sym_open_trades = [
                t for t in get_open_trades_cached() if t["symbol"] == selected_symbol
            ]
            closed_trades = [
                t for t in get_closed_trades_cached(limit=50)
                if t["symbol"] == selected_symbol
            ][:20]

            # Sinyal verileri [3]
            sym_signals = [
                s for s in get_recent_signals_cached(limit=100)
                if s["symbol"] == selected_symbol
            ][:20]

            # Son fiyat (unrealized P&L icin)
            current_price = ohlcv[-1]["close"] if ohlcv else 0

            # EMA hesapla [2]
            ema21 = _calc_ema(ohlcv, 21)
            ema55 = _calc_ema(ohlcv, 55)

            # Overlay verileri
            price_lines = _build_price_lines(sym_open_trades, current_price)
            markers = _build_markers(sym_open_trades, closed_trades, ohlcv, sym_signals)

            html = _build_chart_html(
                ohlcv, price_lines, markers, coin_name, selected_tf,
                ema21=ema21, ema55=ema55,
            )
            components.html(html, height=560, scrolling=False)

            # Trade info paneli
            _render_trade_info(sym_open_trades, closed_trades, current_price)

        _chart_fragment()


# ---------------------------------------------------------------------------
# [1] Portfoy Ozet Dashboard
# ---------------------------------------------------------------------------

def _render_portfolio_summary(trades: list[dict], latest_prices: dict[str, float]):
    """Sayfa basinda portfoy ozet metrikleri."""
    total_pnl_usd = 0.0
    total_cost = 0.0
    sym_pnl: dict[str, float] = {}

    for t in trades:
        sym = t["symbol"]
        entry = t["entry_price"]
        leverage = t.get("leverage", 5.0)
        size_usd = t.get("position_size_usd") or 200
        price = latest_prices.get(sym, 0)

        if price and entry:
            if t["bias"] == "LONG":
                pnl_pct = ((price - entry) / entry) * 100 * leverage
            else:
                pnl_pct = ((entry - price) / entry) * 100 * leverage
            pnl_usd = size_usd * (pnl_pct / 100)
        else:
            pnl_pct = 0.0
            pnl_usd = 0.0

        total_pnl_usd += pnl_usd
        total_cost += size_usd
        coin_short = sym.replace("/USDT:USDT", "")
        sym_pnl[coin_short] = sym_pnl.get(coin_short, 0) + pnl_pct

    total_pnl_pct = (total_pnl_usd / total_cost * 100) if total_cost else 0.0
    avg_pnl = sum(sym_pnl.values()) / len(sym_pnl) if sym_pnl else 0.0
    best_coin = max(sym_pnl, key=sym_pnl.get) if sym_pnl else "-"
    worst_coin = min(sym_pnl, key=sym_pnl.get) if sym_pnl else "-"
    best_val = sym_pnl.get(best_coin, 0)
    worst_val = sym_pnl.get(worst_coin, 0)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Acik Islem", len(trades))
    c2.metric("Toplam P&L", f"${total_pnl_usd:+,.2f}", delta=f"{total_pnl_pct:+.2f}%")
    c3.metric(f"En Karli: {best_coin}", f"{best_val:+.1f}%")
    c4.metric(f"En Zararli: {worst_coin}", f"{worst_val:+.1f}%")
    c5.metric("Ort. P&L", f"{avg_pnl:+.2f}%")
    st.divider()


# ---------------------------------------------------------------------------
# [6] Zaman bazli filtre
# ---------------------------------------------------------------------------

def _filter_trades_by_time(trades: list[dict], filter_label: str) -> list[dict]:
    """Trade'leri opened_at alanina gore filtrele."""
    if filter_label == "Tumu":
        return trades

    hours_map = {
        "Son 1 saat": 1,
        "Son 4 saat": 4,
        "Son 1 gun": 24,
        "Son 3 gun": 72,
    }
    hours = hours_map.get(filter_label, 0)
    if not hours:
        return trades

    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = []
    for t in trades:
        opened_at = t.get("opened_at", "")
        if not opened_at:
            continue
        try:
            # Format: "MM-DD HH:MM"
            dt = datetime.strptime(opened_at, "%m-%d %H:%M").replace(year=datetime.utcnow().year)
            if dt > cutoff:
                result.append(t)
        except (ValueError, TypeError):
            # ISO format fallback
            try:
                dt = datetime.fromisoformat(opened_at)
                if dt.replace(tzinfo=None) > cutoff:
                    result.append(t)
            except (ValueError, TypeError):
                result.append(t)  # parse edemezse dahil et
    return result


# ---------------------------------------------------------------------------
# [5] SL/TP Yakinlik Uyarisi
# ---------------------------------------------------------------------------

def _render_proximity_alerts(trades: list[dict], latest_prices: dict[str, float]):
    """SL veya TP'ye %2'den yakin trade'ler icin uyari goster."""
    alerts = []
    for t in trades:
        sym = t["symbol"]
        coin = sym.replace("/USDT:USDT", "")
        price = latest_prices.get(sym, 0)
        if not price:
            continue

        sl = t.get("sl_price") or 0
        tp = t.get("tp_price") or t.get("tp2_price") or 0
        trail = t.get("trailing_stop_price") or 0
        effective_sl = trail if trail else sl

        if effective_sl and effective_sl > 0:
            sl_dist = abs(price - effective_sl) / price * 100
            if sl_dist <= 2.0:
                alerts.append(("danger", f"{coin}: SL'ye %{sl_dist:.1f} kaldi!"))

        if tp and tp > 0:
            tp_dist = abs(tp - price) / price * 100
            if tp_dist <= 2.0:
                alerts.append(("success", f"{coin}: TP'ye %{tp_dist:.1f} kaldi!"))

    for kind, msg in alerts:
        if kind == "danger":
            st.warning(msg)
        else:
            st.success(msg)


# ---------------------------------------------------------------------------
# [2] EMA hesaplama
# ---------------------------------------------------------------------------

def _calc_ema(ohlcv: list[dict], period: int) -> list[dict]:
    """OHLCV verisinden EMA hesapla. {time, value} formatinda doner."""
    if not ohlcv or len(ohlcv) < period:
        return []

    closes = [c["close"] for c in ohlcv]
    multiplier = 2.0 / (period + 1)

    # Ilk EMA = ilk 'period' mum ortalamasi
    ema_values = []
    sma = sum(closes[:period]) / period
    ema_values.append(sma)
    for i in range(period, len(closes)):
        ema_val = (closes[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(ema_val)

    # time esle — ilk period-1 mum icin EMA yok
    result = []
    for i, val in enumerate(ema_values):
        idx = period - 1 + i
        result.append({"time": ohlcv[idx]["time"], "value": round(val, 8)})
    return result


# ---------------------------------------------------------------------------
# Price lines (acik tradelerin entry/TP/SL cizgileri)
# ---------------------------------------------------------------------------

def _build_price_lines(open_trades: list[dict], current_price: float) -> list[dict]:
    """Acik tradelerin yatay cizgileri — Lightweight Charts priceLine API."""
    lines = []
    for t in open_trades:
        bias = t["bias"]
        entry = t["entry_price"]
        leverage = t.get("leverage", 5.0)

        # Unrealized P&L hesapla
        if current_price and entry:
            if bias == "LONG":
                pnl_pct = ((current_price - entry) / entry) * 100 * leverage
            else:
                pnl_pct = ((entry - current_price) / entry) * 100 * leverage
            pnl_str = f" | {pnl_pct:+.2f}%"
            entry_color = "#26a69a" if pnl_pct >= 0 else "#ef5350"
        else:
            pnl_str = ""
            entry_color = "#FFD700"

        # Entry
        lines.append({
            "price": entry,
            "color": entry_color,
            "lineWidth": 2,
            "lineStyle": 0,  # solid
            "title": f"Entry ({bias}){pnl_str}",
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
# Markers (giris/cikis oklari + sinyal gecmisi)
# ---------------------------------------------------------------------------

def _build_markers(
    open_trades: list[dict],
    closed_trades: list[dict],
    ohlcv: list[dict],
    signals: list[dict] | None = None,
) -> list[dict]:
    """Trade giris/cikis + sinyal gecmisi marker'lari."""
    markers = []
    if not ohlcv or len(ohlcv) < 2:
        return markers

    # Grafik zaman araligi
    chart_start = ohlcv[0]["time"]
    chart_end = ohlcv[-1]["time"]

    def _find_nearest_time(ts_iso: str | None, ts_short: str | None) -> int | None:
        """Trade zamanina en yakin mum zamanini bul. Grafik disindaysa None."""
        target_ts = None
        if ts_iso:
            try:
                dt = datetime.fromisoformat(ts_iso)
                target_ts = int(dt.replace(tzinfo=None).timestamp())
            except (ValueError, TypeError):
                pass

        if target_ts is None and ts_short:
            try:
                now = datetime.utcnow()
                dt = datetime.strptime(ts_short, "%m-%d %H:%M").replace(year=now.year)
                target_ts = int(dt.timestamp())
            except (ValueError, TypeError):
                return None

        if target_ts is None:
            return None

        # Grafik araliginin disindaysa marker koyma
        if target_ts < chart_start or target_ts > chart_end:
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

    # [3] Sinyal gecmisi marker'lari (kare seklinde, transparan renk)
    if signals:
        for s in signals:
            sig_time = _find_nearest_time(s.get("created_at"), None)
            if sig_time is None:
                continue
            is_long = s.get("bias") == "LONG"
            score = s.get("score", 0)
            score_str = f"S {score:+.1f}" if score else "S"
            markers.append({
                "time": sig_time,
                "position": "aboveBar" if is_long else "belowBar",
                "color": "rgba(38,166,154,0.5)" if is_long else "rgba(239,83,80,0.5)",
                "shape": "square",
                "text": score_str,
            })

    # Zamana gore sirala (Lightweight Charts gerekliligi)
    markers.sort(key=lambda m: m["time"])
    return markers


# ---------------------------------------------------------------------------
# Chart HTML (Lightweight Charts v4) — EMA overlay eklendi [2]
# ---------------------------------------------------------------------------

def _build_chart_html(
    ohlcv: list[dict],
    price_lines: list[dict],
    markers: list[dict],
    coin_name: str,
    timeframe: str,
    ema21: list[dict] | None = None,
    ema55: list[dict] | None = None,
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
    ema21_json = json.dumps(ema21 or [])
    ema55_json = json.dumps(ema55 or [])

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

  // EMA 21 (sari) [2]
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

  // EMA 55 (mor) [2]
  const ema55Data = {ema55_json};
  if (ema55Data.length > 0) {{
    const ema55Series = chart.addLineSeries({{
      color: '#AB47BC',
      lineWidth: 1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    }});
    ema55Series.setData(ema55Data);
  }}

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

  // Markers (trade entry/exit arrows + signals)
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
# [4] Mini grafik (4'lu grid icin)
# ---------------------------------------------------------------------------

def _build_mini_chart_html(
    ohlcv: list[dict],
    price_lines: list[dict],
    coin_name: str,
    timeframe: str,
) -> str:
    """4'lu grid icin kucuk candlestick grafik — sadece mumlar + entry/SL cizgileri."""
    ohlcv_json = json.dumps(ohlcv)
    price_lines_json = json.dumps(price_lines)

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: #0e1117; overflow: hidden; }}
  #chart {{ width: 100%; height: 240px; }}
  #label {{
    position: absolute; top: 4px; left: 8px; z-index: 10;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 11px; font-weight: 600; color: #d1d4dc; pointer-events: none;
  }}
</style>
</head>
<body>
<div id="label">{coin_name} / {timeframe}</div>
<div id="chart"></div>
<script>
(function() {{
  const chartEl = document.getElementById('chart');
  const chart = LightweightCharts.createChart(chartEl, {{
    width: chartEl.clientWidth,
    height: 240,
    layout: {{
      background: {{ type: 'solid', color: '#0e1117' }},
      textColor: '#999',
    }},
    grid: {{
      vertLines: {{ color: 'rgba(42,46,57,0.3)' }},
      horzLines: {{ color: 'rgba(42,46,57,0.3)' }},
    }},
    rightPriceScale: {{ borderColor: 'rgba(197,203,206,0.2)', visible: true }},
    timeScale: {{ borderColor: 'rgba(197,203,206,0.2)', timeVisible: true, secondsVisible: false }},
    handleScroll: false,
    handleScale: false,
  }});

  const candleSeries = chart.addCandlestickSeries({{
    upColor: '#26a69a', downColor: '#ef5350',
    borderDownColor: '#ef5350', borderUpColor: '#26a69a',
    wickDownColor: '#ef5350', wickUpColor: '#26a69a',
  }});
  candleSeries.setData({ohlcv_json});

  const priceLines = {price_lines_json};
  priceLines.forEach(function(pl) {{
    candleSeries.createPriceLine({{
      price: pl.price, color: pl.color,
      lineWidth: pl.lineWidth, lineStyle: pl.lineStyle,
      axisLabelVisible: true, title: pl.title,
    }});
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


def _render_mini_grid(
    symbols: list[str],
    latest_prices: dict[str, float],
    trades: list[dict],
):
    """4'lu grid: ilk 4 coin icin kucuk grafik goster."""
    if not symbols:
        st.info("Gosterilecek coin yok.")
        return

    rows = [symbols[:2], symbols[2:4]] if len(symbols) > 2 else [symbols]
    for row_syms in rows:
        cols = st.columns(len(row_syms))
        for i, sym in enumerate(row_syms):
            coin_name = sym.replace("/USDT:USDT", "")
            ohlcv = get_ohlcv_cached(sym, "1h", 150)
            if not ohlcv:
                cols[i].info(f"{coin_name}: veri yok")
                continue

            current_price = ohlcv[-1]["close"]
            sym_trades = [t for t in trades if t["symbol"] == sym]
            price_lines = _build_price_lines(sym_trades, current_price)

            html = _build_mini_chart_html(ohlcv, price_lines, coin_name, "1h")
            with cols[i]:
                components.html(html, height=260, scrolling=False)


# ---------------------------------------------------------------------------
# Trade info paneli (grafik altinda)
# ---------------------------------------------------------------------------

def _render_trade_info(open_trades: list[dict], closed_trades: list[dict], current_price: float = 0):
    """Grafik altinda acik/kapali trade detaylari."""
    if not open_trades and not closed_trades:
        return

    # --- Acik islemler ---
    if open_trades:
        st.subheader(f"Acik Islemler ({len(open_trades)})")
        for t in open_trades:
            bias_icon = "LONG" if t["bias"] == "LONG" else "SHORT"
            entry = t["entry_price"]
            leverage = t.get("leverage", 5.0)
            size_usd = t.get("position_size_usd") or 200

            # Unrealized P&L
            if current_price and entry:
                if t["bias"] == "LONG":
                    pnl_pct = ((current_price - entry) / entry) * 100 * leverage
                else:
                    pnl_pct = ((entry - current_price) / entry) * 100 * leverage
                pnl_usd = size_usd * (pnl_pct / 100)
            else:
                pnl_pct = 0
                pnl_usd = 0

            tp_status = ""
            if t.get("partial_tp_taken"):
                tp_status = " | TP1 alindi"

            cols = st.columns([1, 1, 1, 1, 1, 1])
            cols[0].metric("Yon", bias_icon)
            cols[1].metric("Entry", f"${entry:,.4f}" if entry < 1 else f"${entry:,.2f}")
            cols[2].metric("Anlik P&L", f"{pnl_pct:+.2f}%", delta=f"${pnl_usd:+.2f}")
            tp_val = t.get("tp_price") or t.get("tp2_price")
            cols[3].metric("TP", f"${tp_val:,.4f}" if tp_val and tp_val < 1 else (f"${tp_val:,.2f}" if tp_val else "-"))
            cols[4].metric("SL", f"${t['sl_price']:,.4f}" if t["sl_price"] and t["sl_price"] < 1 else (f"${t['sl_price']:,.2f}" if t["sl_price"] else "-"))
            trail = t.get("trailing_stop_price")
            cols[5].metric("Trail SL", f"${trail:,.4f}" if trail and trail < 1 else (f"${trail:,.2f}" if trail else "-"))

            detail_cols = st.columns([1, 1, 1, 1, 1])
            detail_cols[0].caption(f"MFE: {t['mfe_pct']:.2f}% | MAE: {t['mae_pct']:.2f}%")
            detail_cols[1].caption(f"Rejim: {t.get('regime_at_entry', '-')}")
            detail_cols[2].caption(f"Giris: {t.get('opened_at', '-')}")
            detail_cols[3].caption(f"Kaldırac: {leverage:.0f}x | Pozisyon: ${size_usd:,.0f}")
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
