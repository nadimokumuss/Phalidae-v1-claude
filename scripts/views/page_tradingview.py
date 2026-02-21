"""
Phalidae v2 - TradingView Entegrasyonu
Pine Script v5 generator: DB'den son sinyalleri alir, kopyala-yapistir Pine Script olusturur.
"""

import streamlit as st
from datetime import datetime, timezone

from db.engine import get_session
from db.models import Signal
from commentary import generate_page_header
from views.cache import get_active_symbols_cached


def render():
    generate_page_header("TradingView")
    st.title("TradingView Entegrasyonu")
    st.caption("Phalidae sinyallerini TradingView grafiklerinde goruntuleyin.")

    # --- Kontroller ---
    col1, col2 = st.columns([2, 1])
    with col1:
        symbols = get_active_symbols_cached()
        symbol_list = [s["symbol"] for s in symbols]
        display_names = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

        if not symbol_list:
            st.warning("Aktif coin bulunamadi. Collector'un calismasi bekleniyor.")
            return

        sel_idx = st.selectbox(
            "Coin Sec",
            range(len(symbol_list)),
            format_func=lambda i: display_names[i],
        )
        selected_symbol = symbol_list[sel_idx]
        coin_name = display_names[sel_idx]

    with col2:
        limit = st.slider("Sinyal Sayisi", 5, 30, 15)

    generate_btn = st.button("Pine Script Olustur", type="primary")

    if generate_btn:
        signals = _get_signals_for_symbol(selected_symbol, limit)

        if not signals:
            st.warning(f"{coin_name} icin sinyal bulunamadi.")
            return

        pine_code = _generate_pine_script(coin_name, signals)

        st.success(f"{len(signals)} sinyal ile Pine Script olusturuldu!")

        # Pine Script kodu
        st.subheader("Pine Script v5 Kodu")
        st.code(pine_code, language="python")

        # Sinyal ozet tablosu
        st.subheader("Gomulu Sinyaller")
        rows = []
        for s in signals:
            rows.append({
                "Tarih": s["created_at_str"],
                "Yon": s["bias"],
                "Entry": f"${s['entry_price']:,.4f}" if s["entry_price"] < 1 else f"${s['entry_price']:,.2f}",
                "TP": f"${s['tp_price']:,.4f}" if s["tp_price"] and s["tp_price"] < 1 else (f"${s['tp_price']:,.2f}" if s["tp_price"] else "-"),
                "SL": f"${s['sl_price']:,.4f}" if s["sl_price"] and s["sl_price"] < 1 else (f"${s['sl_price']:,.2f}" if s["sl_price"] else "-"),
                "Skor": f"{s['score']:+.1f}" if s["score"] else "-",
                "Guven": f"{s['confidence_score']:.0f}" if s["confidence_score"] else "-",
            })

        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, height=min(len(rows) * 40 + 40, 400))

        # Kullanim talimatlari
        with st.expander("Nasil Kullanilir?"):
            st.markdown("""
**1.** Yukaridaki kodu kopyalayin (kod kutusunun sag ustundeki kopyala butonuna basin).

**2.** TradingView'da ilgili coin'in grafikini acin (ornegin **BINANCE:{coin}USDT.P** perpetual kontrati).

**3.** Alt panelde **Pine Editor** sekmesine tiklayin.

**4.** Mevcut kodu silin ve kopyaladiginiz kodu yapistirin.

**5.** **"Add to Chart"** butonuna basin.

**6.** Grafikte Phalidae sinyallerinin oklarini, TP/SL cizgilerini goreceksiniz.

**Not:** Pine Script'teki sinyal verileri statiktir — yeni sinyaller icin bu sayfadan tekrar olusturmaniz gerekir.
""".replace("{coin}", coin_name))


def _get_signals_for_symbol(symbol: str, limit: int) -> list[dict]:
    """DB'den coin'e ozel son N sinyali ceker."""
    session = get_session()
    try:
        rows = (
            session.query(Signal)
            .filter(Signal.symbol == symbol)
            .order_by(Signal.created_at.desc())
            .limit(limit)
            .all()
        )
        signals = []
        for r in rows:
            ts_ms = int(r.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000) if r.created_at else 0
            signals.append({
                "timestamp_ms": ts_ms,
                "bias": r.bias,
                "entry_price": float(r.entry_price) if r.entry_price else 0,
                "tp_price": float(r.tp_price) if r.tp_price else None,
                "sl_price": float(r.sl_price) if r.sl_price else None,
                "score": float(r.score) if r.score else None,
                "confidence_score": float(r.confidence_score) if r.confidence_score else None,
                "created_at_str": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "-",
            })
        # Kronolojik sira (eski -> yeni) Pine Script icin
        signals.reverse()
        return signals
    finally:
        session.close()


def _generate_pine_script(coin_name: str, signals: list[dict]) -> str:
    """Pine Script v5 kodu olusturur."""

    # Sinyal verilerini Pine array literal olarak hazirla
    timestamps = ", ".join(str(s["timestamp_ms"]) for s in signals)
    biases = ", ".join("1" if s["bias"] == "LONG" else "-1" for s in signals)
    entries = ", ".join(f"{s['entry_price']}" for s in signals)
    tps = ", ".join(f"{s['tp_price']}" if s["tp_price"] else "na" for s in signals)
    sls = ", ".join(f"{s['sl_price']}" if s["sl_price"] else "na" for s in signals)
    scores = ", ".join(f"{s['score']:.1f}" if s["score"] else "0.0" for s in signals)
    confs = ", ".join(f"{s['confidence_score']:.0f}" if s["confidence_score"] else "0" for s in signals)

    n = len(signals)

    pine = f"""//@version=5
indicator("Phalidae - {coin_name}", overlay=true, max_labels_count=500, max_lines_count=500)

// ═══════════════════════════════════════════════
// Phalidae Sinyal Verileri ({n} sinyal)
// Olusturulma: {datetime.utcnow().strftime("%Y-%m-%d %H:%M")} UTC
// ═══════════════════════════════════════════════

int   SIG_COUNT = {n}

sig_time  = array.from({timestamps})
sig_bias  = array.from({biases})
sig_entry = array.from({entries})
sig_tp    = array.from({tps})
sig_sl    = array.from({sls})
sig_score = array.from({scores})
sig_conf  = array.from({confs})

// ═══════════════════════════════════════════════
// Ayarlar
// ═══════════════════════════════════════════════

tolerance = input.int(defval=30, title="Zaman Toleransi (dakika)", minval=1, maxval=120) * 60 * 1000
showTP    = input.bool(defval=true,  title="TP Cizgilerini Goster")
showSL    = input.bool(defval=true,  title="SL Cizgilerini Goster")
showInfo  = input.bool(defval=true,  title="Bilgi Etiketlerini Goster")

// ═══════════════════════════════════════════════
// Her bar'da sinyal eslestirme
// ═══════════════════════════════════════════════

barMs = time

for i = 0 to SIG_COUNT - 1
    int   t = array.get(sig_time,  i)
    int   b = array.get(sig_bias,  i)
    float e = array.get(sig_entry, i)
    float tp_val = array.get(sig_tp, i)
    float sl_val = array.get(sig_sl, i)
    float sc = array.get(sig_score, i)
    float cf = array.get(sig_conf,  i)

    if math.abs(barMs - t) <= tolerance
        // Sinyal oku
        isLong = b == 1
        lbl_color = isLong ? color.new(color.green, 0) : color.new(color.red, 0)
        lbl_style = isLong ? label.style_label_up : label.style_label_down
        lbl_y     = isLong ? low : high

        lbl_text = (isLong ? "LONG" : "SHORT")
        if showInfo and cf > 0
            lbl_text := lbl_text + "\\n" + str.tostring(cf, "#") + "/100"
        if showInfo and sc != 0
            lbl_text := lbl_text + "\\n" + str.tostring(sc, "#.#")

        label.new(bar_index, lbl_y, lbl_text,
             color=lbl_color, textcolor=color.white,
             style=lbl_style, size=size.small)

        // TP cizgisi
        if showTP and not na(tp_val) and bar_index > 0
            line.new(bar_index - 1, tp_val, bar_index + 5, tp_val,
                 color=color.new(color.green, 30), style=line.style_dashed, width=1)
            if showInfo
                label.new(bar_index + 5, tp_val, "TP " + str.tostring(tp_val, "#.####"),
                     color=color.new(color.green, 80), textcolor=color.green,
                     style=label.style_label_left, size=size.tiny)

        // SL cizgisi
        if showSL and not na(sl_val) and bar_index > 0
            line.new(bar_index - 1, sl_val, bar_index + 5, sl_val,
                 color=color.new(color.red, 30), style=line.style_dashed, width=1)
            if showInfo
                label.new(bar_index + 5, sl_val, "SL " + str.tostring(sl_val, "#.####"),
                     color=color.new(color.red, 80), textcolor=color.red,
                     style=label.style_label_left, size=size.tiny)
"""

    return pine
