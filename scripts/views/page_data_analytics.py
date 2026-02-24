"""
Phalidae v2 - Data & Analytics Page (TradingView Style)
Combined: Data Explorer + Analysis Library.
"""

import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime

from db.engine import get_session
from db.models import ExternalAnalysis, TrackedSymbol
from worker.collector import get_ohlcv_df

from views.theme import (
    BG_PRIMARY, BG_SECONDARY, BG_TERTIARY, BG_SURFACE,
    BORDER_DEFAULT, TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BULL, BEAR, ACCENT_BLUE,
)
from views.components import render_top_bar
from views.cache import (
    get_coverage_matrix_cached,
    get_active_symbols_cached,
    get_system_stats_cached,
    get_ohlcv_cached,
    get_analyses_cached,
)


def _calc_ema(ohlcv: list[dict], period: int) -> list[dict]:
    """Compute EMA from OHLCV data. Returns list of {time, value}."""
    if not ohlcv or len(ohlcv) < period:
        return []
    closes = [c["close"] for c in ohlcv]
    multiplier = 2.0 / (period + 1)
    ema_values = []
    sma = sum(closes[:period]) / period
    ema_values.append(sma)
    for i in range(period, len(closes)):
        ema_val = (closes[i] - ema_values[-1]) * multiplier + ema_values[-1]
        ema_values.append(ema_val)
    result = []
    for i, val in enumerate(ema_values):
        idx = period - 1 + i
        result.append({"time": ohlcv[idx]["time"], "value": round(val, 8)})
    return result


def render():
    """Data & Analytics main page."""
    render_top_bar()

    tab_cov, tab_raw, tab_ind, tab_lib = st.tabs([
        "Kapsam", "Ham Veri", "Indikatorler", "Analiz Arsivi",
    ])

    with tab_cov:
        _render_coverage()
    with tab_raw:
        _render_raw_data()
    with tab_ind:
        _render_indicator_chart()
    with tab_lib:
        _render_analysis_library()


# ---------------------------------------------------------------------------
# Coverage Matrix Tab
# ---------------------------------------------------------------------------

def _render_coverage():
    """Data coverage matrix — colored pivot table."""
    pivot = get_coverage_matrix_cached()

    if pivot.empty:
        st.info("Henuz veri yok.")
        return

    timeframes = [tf for tf in ["5m", "15m", "30m", "1h", "4h", "1d"] if tf in pivot.columns]
    if not timeframes:
        st.info("Henuz veri yok.")
        return

    display_df = pivot[["Coin"] + timeframes].copy()
    display_df = display_df.sort_values("Coin").reset_index(drop=True)

    def _style_cell(val):
        if isinstance(val, (int, float)):
            if val >= 500:
                return f"background-color: rgba(38,166,154,0.3)"
            elif val >= 100:
                return "background-color: rgba(255,235,59,0.2)"
            elif val > 0:
                return "background-color: rgba(239,83,80,0.2)"
        return ""

    styled = display_df.style.map(_style_cell, subset=timeframes)
    st.dataframe(styled, use_container_width=True, height=600)

    stats = get_system_stats_cached()
    symbols = get_active_symbols_cached()
    st.caption(
        f"Toplam {stats['total_candles']:,} mum verisi, "
        f"{len(symbols)} coin, {len(timeframes)} zaman dilimi"
    )


# ---------------------------------------------------------------------------
# Raw Data Tab
# ---------------------------------------------------------------------------

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
        sel_sym = st.selectbox(
            "Coin", range(len(sym_list)),
            format_func=lambda i: sym_labels[i], key="da_raw_coin",
        )
        symbol = sym_list[sel_sym]
    with c2:
        tf = st.selectbox("TF", ["5m", "15m", "30m", "1h", "4h"], index=3, key="da_raw_tf")
    with c3:
        limit = st.number_input("Son N mum", value=100, min_value=10, max_value=2000, step=50, key="da_raw_limit")

    df = get_ohlcv_df(symbol, tf, limit=limit)
    if df.empty:
        st.warning("Veri bulunamadi.")
        return

    st.caption(f"{len(df)} mum — {df['timestamp'].iloc[0]} ile {df['timestamp'].iloc[-1]}")
    st.dataframe(
        df.style.format({
            "open": "{:.6f}", "high": "{:.6f}", "low": "{:.6f}", "close": "{:.6f}",
            "volume": "{:,.0f}",
        }),
        use_container_width=True,
        height=500,
    )


# ---------------------------------------------------------------------------
# Indicator Chart Tab (Lightweight Charts v4 — consistent with terminal)
# ---------------------------------------------------------------------------

def _render_indicator_chart():
    """Indicator chart using Lightweight Charts v4 for consistency."""
    symbols = get_active_symbols_cached()
    if not symbols:
        st.info("Henuz veri yok.")
        return

    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    c1, c2 = st.columns(2)
    with c1:
        sel_sym = st.selectbox(
            "Coin", range(len(sym_list)),
            format_func=lambda i: sym_labels[i], key="da_ind_coin",
        )
        symbol = sym_list[sel_sym]
    with c2:
        tf = st.selectbox("TF", ["5m", "15m", "30m", "1h", "4h"], index=3, key="da_ind_tf")

    show_ema = st.checkbox("EMA (21/55)", value=True, key="da_ind_ema")

    ohlcv = get_ohlcv_cached(symbol, tf, 300)
    if not ohlcv:
        st.warning("Veri bulunamadi.")
        return

    coin_name = sym_labels[sel_sym]

    ema21 = _calc_ema(ohlcv, 21) if show_ema else []
    ema55 = _calc_ema(ohlcv, 55) if show_ema else []

    html = _build_analytics_chart_html(ohlcv, coin_name, tf, ema21, ema55)
    components.html(html, height=520, scrolling=False)


def _build_analytics_chart_html(
    ohlcv: list[dict],
    coin_name: str,
    timeframe: str,
    ema21: list[dict],
    ema55: list[dict],
) -> str:
    """Lightweight Charts v4 HTML for analytics page."""
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
    ema21_json = json.dumps(ema21)
    ema55_json = json.dumps(ema55)

    return f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="https://unpkg.com/lightweight-charts@4.2.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
  body {{ margin: 0; padding: 0; background: {BG_PRIMARY}; overflow: hidden; }}
  #chart {{ width: 100%; height: 500px; }}
  #label {{
    position: absolute; top: 8px; left: 12px; z-index: 10;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
    font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY}; pointer-events: none;
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
    height: 500,
    layout: {{
      background: {{ type: 'solid', color: '{BG_PRIMARY}' }},
      textColor: '{TEXT_PRIMARY}',
    }},
    grid: {{
      vertLines: {{ color: 'rgba(54, 58, 69, 0.5)' }},
      horzLines: {{ color: 'rgba(54, 58, 69, 0.5)' }},
    }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
    rightPriceScale: {{ borderColor: '{BORDER_DEFAULT}' }},
    timeScale: {{ borderColor: '{BORDER_DEFAULT}', timeVisible: true, secondsVisible: false }},
  }});

  const candleSeries = chart.addCandlestickSeries({{
    upColor: '{BULL}', downColor: '{BEAR}',
    borderDownColor: '{BEAR}', borderUpColor: '{BULL}',
    wickDownColor: '{BEAR}', wickUpColor: '{BULL}',
  }});
  candleSeries.setData({ohlcv_json});

  const volumeSeries = chart.addHistogramSeries({{
    priceFormat: {{ type: 'volume' }},
    priceScaleId: 'volume',
  }});
  chart.priceScale('volume').applyOptions({{
    scaleMargins: {{ top: 0.8, bottom: 0 }},
  }});
  volumeSeries.setData({volume_data});

  const ema21Data = {ema21_json};
  if (ema21Data.length > 0) {{
    const ema21S = chart.addLineSeries({{
      color: '#FFD700', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    }});
    ema21S.setData(ema21Data);
  }}

  const ema55Data = {ema55_json};
  if (ema55Data.length > 0) {{
    const ema55S = chart.addLineSeries({{
      color: '#AB47BC', lineWidth: 1,
      priceLineVisible: false, lastValueVisible: false,
    }});
    ema55S.setData(ema55Data);
  }}

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
# Analysis Library Tab (combined from page_analysis_library.py)
# ---------------------------------------------------------------------------

def _render_analysis_library():
    """Combined analysis library: add + list + validation."""
    sub_tab = st.radio(
        "Islem", ["Kutuphane", "Analiz Ekle", "Dogrulama"],
        horizontal=True, label_visibility="collapsed", key="da_lib_sub",
    )

    if sub_tab == "Kutuphane":
        _render_library()
    elif sub_tab == "Analiz Ekle":
        _render_add_analysis()
    else:
        _render_pending_validation()


def _render_add_analysis():
    """Form to add a new external analysis."""
    symbols = get_active_symbols_cached()
    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    with st.form("add_analysis_v2"):
        c1, c2 = st.columns(2)
        with c1:
            if sym_labels:
                sel_idx = st.selectbox("Coin", range(len(sym_labels)),
                                       format_func=lambda i: sym_labels[i])
                symbol = sym_list[sel_idx]
            else:
                symbol = st.text_input("Coin (ornek: BTC/USDT:USDT)")
            source_type = st.selectbox("Kaynak", ["twitter", "tradingview", "blog", "youtube", "manual"])
            author = st.text_input("Yazar")
        with c2:
            source_url = st.text_input("URL (opsiyonel)")
            bias_claimed = st.radio("Bias", ["LONG", "SHORT"], horizontal=True)
            target_price = st.number_input("Hedef ($)", value=0.0, step=100.0)
            stop_price = st.number_input("Stop ($)", value=0.0, step=100.0)

        summary = st.text_area("Ozet", height=120)
        tools_used = st.multiselect(
            "Araclar",
            ["S/R", "Fibonacci", "Elliott Wave", "Orderflow", "Makro", "On-chain",
             "Volume Profile", "Ichimoku", "RSI/MACD", "Bollinger", "Trend Lines",
             "Chart Patterns", "Pivot Points", "VWAP"],
        )
        submitted = st.form_submit_button("Kaydet", type="primary")

    if submitted and summary:
        session = get_session()
        try:
            session.add(ExternalAnalysis(
                symbol=symbol,
                source_type=source_type,
                source_url=source_url if source_url else None,
                author=author if author else None,
                summary=summary,
                tools_used=tools_used if tools_used else None,
                bias_claimed=bias_claimed,
                target_price=target_price if target_price > 0 else None,
                stop_price=stop_price if stop_price > 0 else None,
                outcome="PENDING",
                added_at=datetime.utcnow(),
            ))
            session.commit()
            get_analyses_cached.clear()
            st.success("Analiz kaydedildi!")
        except Exception as e:
            session.rollback()
            st.error(f"Kayit hatasi: {e}")
        finally:
            session.close()


def _render_library():
    """Analysis library with filters."""
    analyses = get_analyses_cached()
    if not analyses:
        st.info("Henuz analiz eklenmedi.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        bias_f = st.multiselect("Bias", ["LONG", "SHORT"], default=["LONG", "SHORT"], key="da_lib_bias")
    with c2:
        source_types = list(set(a["source_type"] for a in analyses))
        source_f = st.multiselect("Kaynak", source_types, default=source_types, key="da_lib_source")
    with c3:
        outcome_f = st.multiselect("Sonuc", ["PENDING", "CORRECT", "WRONG", "PARTIAL"],
                                   default=["PENDING", "CORRECT", "WRONG", "PARTIAL"], key="da_lib_outcome")

    filtered = [
        a for a in analyses
        if a["bias_claimed"] in bias_f
        and a["source_type"] in source_f
        and a["outcome"] in outcome_f
    ]

    rows = []
    for a in filtered:
        coin = (a["symbol"] or "").replace("/USDT:USDT", "")
        rows.append({
            "ID": a["id"],
            "Coin": coin,
            "Yazar": a["author"] or "-",
            "Bias": a["bias_claimed"] or "-",
            "Hedef": f"${a['target_price']:,.2f}" if a["target_price"] else "-",
            "Stop": f"${a['stop_price']:,.2f}" if a["stop_price"] else "-",
            "Kaynak": a["source_type"],
            "Sonuc": a["outcome"],
            "Tarih": a["added_at"],
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=350)

        sel = st.selectbox(
            "Detay",
            range(len(filtered)),
            format_func=lambda i: f"#{filtered[i]['id']} {(filtered[i]['symbol'] or '').replace('/USDT:USDT', '')} {filtered[i]['bias_claimed']}",
            key="da_lib_detail",
        )
        a = filtered[sel]
        with st.expander("Analiz Detayi", expanded=True):
            st.markdown(f"**Ozet:** {a['summary']}")
            if a["tools_used"]:
                st.markdown(f"**Araclar:** {', '.join(a['tools_used'])}")
            if a["outcome_notes"]:
                st.markdown(f"**Notlar:** {a['outcome_notes']}")
            if a["lesson_learned"]:
                st.success(f"**Ders:** {a['lesson_learned']}")
    else:
        st.info("Filtrelere uygun analiz bulunamadi.")


def _render_pending_validation():
    """Pending validation list."""
    session = get_session()
    try:
        pending = (
            session.query(ExternalAnalysis)
            .filter(ExternalAnalysis.outcome == "PENDING")
            .order_by(ExternalAnalysis.added_at.desc())
            .all()
        )
        pending_data = []
        for a in pending:
            pending_data.append({
                "id": a.id, "symbol": a.symbol, "bias": a.bias_claimed,
                "target": a.target_price, "stop": a.stop_price,
                "summary": a.summary, "author": a.author, "added_at": a.added_at,
            })
    finally:
        session.close()

    if not pending_data:
        st.info("Dogrulama bekleyen analiz yok.")
        return

    st.caption(f"{len(pending_data)} dogrulama bekleyen")

    for p in pending_data:
        coin = (p["symbol"] or "").replace("/USDT:USDT", "")
        with st.expander(f"#{p['id']} {coin} {p['bias']} — {p['author'] or 'Anonim'}"):
            st.write(p["summary"][:300])
            if p["target"]:
                target_str = f"Hedef: ${p['target']:,.2f}"
                if p["stop"]:
                    target_str += f" | Stop: ${p['stop']:,.2f}"
                st.write(target_str)

            c1, c2 = st.columns(2)
            with c1:
                outcome = st.selectbox(
                    "Sonuc", ["PENDING", "CORRECT", "WRONG", "PARTIAL"],
                    key=f"da_outcome_{p['id']}",
                )
            with c2:
                lesson = st.text_input("Ders", key=f"da_lesson_{p['id']}")

            notes = st.text_area("Notlar", key=f"da_notes_{p['id']}", height=60)

            if st.button("Guncelle", key=f"da_update_{p['id']}"):
                session = get_session()
                try:
                    a = session.query(ExternalAnalysis).get(p["id"])
                    if a:
                        a.outcome = outcome
                        a.outcome_notes = notes if notes else None
                        a.lesson_learned = lesson if lesson else None
                        a.verified_at = datetime.utcnow()
                        session.commit()
                        get_analyses_cached.clear()
                        st.success("Guncellendi!")
                        st.rerun()
                except Exception as e:
                    session.rollback()
                    st.error(f"Hata: {e}")
                finally:
                    session.close()
