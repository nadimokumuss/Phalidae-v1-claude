"""
Phalidae v2 - Signals Page (Phase 5)
Two modes: "Canli Tarama" (legacy scan) + "Otomatik Sinyaller" (from DB).
Includes: confidence bar (0-100), ETA display, invalidation notes.
"""

import streamlit as st
import pandas as pd

from signal_generator import (
    scan_market, analyze_symbol, fetch_ohlcv, _init_exchange,
    get_recent_signals_from_db,
)
from charting import plot_interactive_chart
from commentary import generate_page_header


def render():
    generate_page_header("Sinyaller")
    st.title("Sinyaller")

    mode = st.radio(
        "Mod",
        ["Otomatik Sinyaller (DB)", "Canli Tarama (Legacy)"],
        horizontal=True,
    )

    if mode == "Otomatik Sinyaller (DB)":
        _render_db_signals()
    else:
        _render_live_scan()


def _render_db_signals():
    """Show recent signals from database."""
    signals = get_recent_signals_from_db(limit=100)

    if not signals:
        st.info("Henuz otomatik sinyal uretilmedi. Analyzer ilk calistiginda burada gorunecek.")
        return

    st.success(f"Son {len(signals)} sinyal")

    # Filters
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        bias_f = st.multiselect("Yon", ["LONG", "SHORT"], default=["LONG", "SHORT"])
    with col2:
        conf_f = st.multiselect("Guven", ["YUKSEK", "ORTA", "DUSUK"], default=["YUKSEK", "ORTA"])
    with col3:
        min_score = st.slider("Min |Skor|", 0.0, 10.0, 2.5, 0.5)
    with col4:
        min_conf_score = st.slider("Min Guven Skoru", 0, 100, 0, 5)

    filtered = [
        s for s in signals
        if s["bias"] in bias_f
        and s.get("confidence", "") in conf_f
        and abs(s.get("score", 0)) >= min_score
        and (s.get("confidence_score") or 0) >= min_conf_score
    ]

    rows = []
    for s in filtered:
        cn = s["symbol"].replace("/USDT:USDT", "")
        conf_score = s.get("confidence_score")
        eta_low = s.get("eta_hours_low")
        eta_high = s.get("eta_hours_high")
        rows.append({
            "Coin": cn,
            "Yon": s["bias"],
            "Entry ($)": s["entry"],
            "TP ($)": s.get("tp"),
            "SL ($)": s.get("sl"),
            "R:R": s.get("rr_ratio"),
            "Guven": s.get("confidence", ""),
            "Skor (0-100)": f"{conf_score:.0f}" if conf_score else "-",
            "Skor": s.get("score", 0),
            "ETA": f"{eta_low:.0f}-{eta_high:.0f}s" if eta_low and eta_high else "-",
            "Strateji": s.get("strategy_name", ""),
            "Zaman": s.get("created_at", "")[:16],
        })

    if rows:
        df_sig = pd.DataFrame(rows)
        st.dataframe(
            df_sig.style.format({
                "Entry ($)": "${:,.2f}", "TP ($)": "${:,.2f}", "SL ($)": "${:,.2f}",
                "R:R": "{:.2f}", "Skor": "{:+.1f}",
            }),
            width="stretch",
            height=400,
        )

        # Detail view
        st.divider()
        sel_idx = st.selectbox(
            "Sinyal detayi:",
            range(len(filtered)),
            format_func=lambda i: f"{filtered[i]['symbol'].replace('/USDT:USDT', '')} - {filtered[i]['bias']} ({filtered[i].get('score', 0):+.1f})",
        )
        sig = filtered[sel_idx]
        _render_signal_detail(sig)
    else:
        st.warning("Filtrelere uygun sinyal bulunamadi.")


def _render_live_scan():
    """Legacy live scanning mode."""
    with st.sidebar:
        st.subheader("Tarama Ayarlari")
        top_n = st.slider("Coin Sayisi", 10, 50, 30, step=5)
        timeframes = st.multiselect(
            "Zaman Dilimleri",
            ["5m", "15m", "1h", "4h", "1d"],
            default=["15m", "1h", "4h"],
        )
        min_rr = st.number_input("Min R:R", value=1.5, step=0.5)
        confidence_filter = st.multiselect(
            "Guven Filtresi",
            ["YUKSEK", "ORTA", "DUSUK"],
            default=["YUKSEK", "ORTA"],
        )
        scan_btn = st.button("PIYASAYI TARA", type="primary", width="stretch")

    if scan_btn:
        with st.spinner(f"Top {top_n} coin analiz ediliyor..."):
            signals = scan_market(top_n=top_n, timeframes=timeframes)

        signals = [s for s in signals if s.get("confidence") in confidence_filter]
        signals = [s for s in signals if s.get("rr_ratio") and s["rr_ratio"] >= min_rr]

        st.session_state["live_signals"] = signals

    signals = st.session_state.get("live_signals", [])
    if not signals:
        st.info("Sol panelden 'PIYASAYI TARA' butonuna basarak canli tarama baslatin.")
        return

    st.success(f"{len(signals)} sinyal bulundu!")

    rows = []
    for s in signals:
        cn = s["symbol"].replace("/USDT:USDT", "")
        rows.append({
            "Coin": cn,
            "Yon": s["bias"],
            "Entry ($)": s["entry"],
            "TP ($)": s["tp"],
            "SL ($)": s["sl"],
            "R:R": s["rr_ratio"],
            "Guven": s["confidence"],
            "Skor": s["score"],
        })

    df_sig = pd.DataFrame(rows)
    st.dataframe(
        df_sig.style.format({
            "Entry ($)": "${:,.2f}", "TP ($)": "${:,.2f}", "SL ($)": "${:,.2f}",
            "R:R": "{:.2f}", "Skor": "{:+.1f}",
        }),
        width="stretch",
        height=400,
    )

    st.divider()
    sel_idx = st.selectbox(
        "Sinyal detayi:",
        range(len(signals)),
        format_func=lambda i: f"{signals[i]['symbol'].replace('/USDT:USDT', '')} - {signals[i]['bias']} ({signals[i]['score']:+.1f})",
    )
    sig = signals[sel_idx]

    # Metrics
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Yon", sig["bias"])
    c2.metric("Entry", f"${sig['entry']:,.2f}")
    c3.metric("Take Profit", f"${sig['tp']:,.2f}")
    c4.metric("Stop Loss", f"${sig['sl']:,.2f}")
    c5.metric("R:R", f"{sig['rr_ratio']:.2f}")
    c6.metric("Skor", f"{sig['score']:+.1f}")

    # Chart
    try:
        exchange = _init_exchange()
        df_chart = fetch_ohlcv(exchange, sig["symbol"], "4h", 200)
        fig = plot_interactive_chart(df_chart, symbol=sig["symbol"].replace("/USDT:USDT", "") + " 4H")
        fig.add_hline(y=sig["tp"], line_color="#26a69a", line_dash="dash",
                     annotation_text=f"TP: ${sig['tp']:,.2f}")
        fig.add_hline(y=sig["sl"], line_color="#ef5350", line_dash="dash",
                     annotation_text=f"SL: ${sig['sl']:,.2f}")
        fig.add_hline(y=sig["entry"], line_color="#ffeb3b", line_dash="dot",
                     annotation_text=f"Entry: ${sig['entry']:,.2f}")
        st.plotly_chart(fig, width="stretch")
    except Exception as e:
        st.error(f"Grafik hatasi: {e}")

    # Indicator details
    if "indicator_details" in sig:
        with st.expander("Indikator Detaylari"):
            for tf, data in sig.get("indicator_details", {}).items():
                st.markdown(f"**{tf}** (skor: {data.get('normalized', 0):+.1f})")
                scores = data.get("scores", {})
                cols = st.columns(3)
                for idx, (name, val) in enumerate(scores.items()):
                    cols[idx % 3].write(f"{'🟢' if val > 0 else '🔴' if val < 0 else '⚪'} {name}: {val:+.2f}")


def _render_signal_detail(sig: dict):
    """Render detail for a DB signal with confidence bar, ETA, invalidation."""
    cn = sig["symbol"].replace("/USDT:USDT", "")

    # --- Confidence Score Bar (Phase 5) ---
    conf_score = sig.get("confidence_score")
    if conf_score is not None:
        if conf_score >= 75:
            conf_color = "🟢"
            conf_label = "Yuksek"
        elif conf_score >= 50:
            conf_color = "🟡"
            conf_label = "Orta"
        else:
            conf_color = "🔴"
            conf_label = "Dusuk"

        st.markdown(f"### {conf_color} Guven Skoru: {conf_score:.0f}/100 ({conf_label})")
        st.progress(min(conf_score / 100, 1.0), text=f"Guven: {conf_score:.0f}/100")

        # Confidence breakdown
        breakdown = sig.get("confidence_breakdown", {})
        if breakdown:
            with st.expander("Guven Dagilimi"):
                bd_cols = st.columns(4)
                bd_items = list(breakdown.items())
                for idx, (component, value) in enumerate(bd_items):
                    label_map = {
                        "confluence": "Confluence",
                        "regime_fit": "Rejim Uyumu",
                        "rr_quality": "R:R Kalitesi",
                        "patterns": "Pattern",
                        "volume": "Hacim",
                        "backtest": "Backtest",
                        "news": "Haber Riski",
                    }
                    display_name = label_map.get(component, component)
                    bd_cols[idx % 4].metric(display_name, f"{value:.1f}")

    # Metrics row
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Yon", sig["bias"])
    c2.metric("Entry", f"${sig['entry']:,.2f}")
    c3.metric("TP", f"${sig.get('tp', 0):,.2f}" if sig.get("tp") else "-")
    c4.metric("SL", f"${sig.get('sl', 0):,.2f}" if sig.get("sl") else "-")
    c5.metric("Skor", f"{sig.get('score', 0):+.1f}")

    # --- ETA Display (Phase 5) ---
    eta_low = sig.get("eta_hours_low")
    eta_high = sig.get("eta_hours_high")
    if eta_low and eta_high:
        st.info(f"Tahmini Sure: {eta_low:.0f}-{eta_high:.0f} saat")

    # --- News Risk (Phase 5) ---
    news_risk = sig.get("news_risk_score")
    if news_risk is not None and news_risk > 0:
        if news_risk > 0.7:
            st.error(f"Haber Riski: Yuksek ({news_risk:.2f})")
        elif news_risk > 0.3:
            st.warning(f"Haber Riski: Orta ({news_risk:.2f})")
        else:
            st.caption(f"Haber Riski: Dusuk ({news_risk:.2f})")

    # --- Invalidation Note (Phase 5) ---
    invalidation = sig.get("invalidation_note")
    if invalidation:
        st.error(f"Iptal Kosulu: {invalidation}")

    # Reasoning
    if sig.get("reasoning"):
        with st.expander("Analiz Aciklamasi", expanded=True):
            st.text(sig["reasoning"])

    # Indicator scores
    if sig.get("indicator_scores"):
        with st.expander("Indikator Skorlari"):
            scores = sig["indicator_scores"]
            cols = st.columns(3)
            for idx, (name, val) in enumerate(scores.items()):
                if isinstance(val, (int, float)):
                    icon = "🟢" if val > 0 else "🔴" if val < 0 else "⚪"
                    cols[idx % 3].write(f"{icon} {name}: {val:+.2f}")

    # Patterns
    if sig.get("detected_patterns"):
        with st.expander("Tespit Edilen Formasyonlar"):
            for p in sig["detected_patterns"]:
                icon = "🟢" if p.get("bias") == "Bullish" else "🔴" if p.get("bias") == "Bearish" else "⚪"
                st.write(f"{icon} {p['pattern']} (guc: {p.get('strength', 0)})")
