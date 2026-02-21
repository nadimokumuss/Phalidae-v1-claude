"""
Phalidae v2 - Analysis Library Page (Phase 4)
Manual external analysis entries, validation tracking, lessons learned.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

from db.engine import get_session
from db.models import ExternalAnalysis, TrackedSymbol
from commentary import generate_page_header
from views.cache import get_active_symbols_cached, get_analyses_cached


def render():
    generate_page_header("Analiz Kutuphanesi")
    st.title("Analiz Kutuphanesi")
    st.caption("Dis kaynaklardan analizleri kaydet, takip et ve dogrula")

    tab_add, tab_library, tab_pending = st.tabs([
        "Analiz Ekle", "Kutuphane", "Dogrulama Bekleyenler"
    ])

    with tab_add:
        _render_add_analysis()
    with tab_library:
        _render_library()
    with tab_pending:
        _render_pending_validation()


def _render_add_analysis():
    """Form to add a new external analysis."""
    symbols = get_active_symbols_cached()
    sym_list = [s["symbol"] for s in symbols]
    sym_labels = [s["symbol"].replace("/USDT:USDT", "") for s in symbols]

    with st.form("add_analysis"):
        c1, c2 = st.columns(2)
        with c1:
            if sym_labels:
                sel_idx = st.selectbox("Coin", range(len(sym_labels)), format_func=lambda i: sym_labels[i])
                symbol = sym_list[sel_idx]
            else:
                symbol = st.text_input("Coin (ornek: BTC/USDT:USDT)")

            source_type = st.selectbox("Kaynak Tipi", ["twitter", "tradingview", "blog", "youtube", "manual"])
            author = st.text_input("Yazar")

        with c2:
            source_url = st.text_input("URL (opsiyonel)")
            bias_claimed = st.radio("Bias", ["LONG", "SHORT"], horizontal=True)
            target_price = st.number_input("Hedef Fiyat ($)", value=0.0, step=100.0)
            stop_price = st.number_input("Stop Fiyat ($)", value=0.0, step=100.0)

        summary = st.text_area("Analiz Ozeti", height=150)

        tools_used = st.multiselect(
            "Kullanilan Araclar",
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
    """Show all analyses with filters — cached (TTL=60s)."""
    analyses = get_analyses_cached()

    if not analyses:
        st.info("Henuz analiz eklenmedi.")
        return

    # Filters
    c1, c2, c3 = st.columns(3)
    with c1:
        bias_f = st.multiselect("Bias", ["LONG", "SHORT"], default=["LONG", "SHORT"], key="lib_bias")
    with c2:
        source_types = list(set(a["source_type"] for a in analyses))
        source_f = st.multiselect("Kaynak", source_types, default=source_types, key="lib_source")
    with c3:
        outcome_f = st.multiselect("Sonuc", ["PENDING", "CORRECT", "WRONG", "PARTIAL"],
                                   default=["PENDING", "CORRECT", "WRONG", "PARTIAL"], key="lib_outcome")

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
            "Ders": (a["lesson_learned"] or "")[:50],
            "Tarih": a["added_at"],
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", height=400)

        # Detail expand
        sel = st.selectbox(
            "Detay:",
            range(len(filtered)),
            format_func=lambda i: f"#{filtered[i]['id']} {(filtered[i]['symbol'] or '').replace('/USDT:USDT', '')} {filtered[i]['bias_claimed']}",
            key="lib_detail",
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
    """Show analyses pending validation."""
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
                "id": a.id,
                "symbol": a.symbol,
                "bias": a.bias_claimed,
                "target": a.target_price,
                "stop": a.stop_price,
                "summary": a.summary,
                "author": a.author,
                "added_at": a.added_at,
            })
    finally:
        session.close()

    if not pending_data:
        st.info("Dogrulama bekleyen analiz yok.")
        return

    st.subheader(f"{len(pending_data)} Dogrulama Bekleyen")

    for p in pending_data:
        coin = (p["symbol"] or "").replace("/USDT:USDT", "")
        with st.expander(f"#{p['id']} {coin} {p['bias']} - {p['author'] or 'Anonim'}"):
            st.write(p["summary"][:300])
            if p["target"]:
                st.write(f"Hedef: ${p['target']:,.2f} | Stop: ${p['stop']:,.2f}" if p["stop"] else f"Hedef: ${p['target']:,.2f}")

            c1, c2 = st.columns(2)
            with c1:
                outcome = st.selectbox(
                    "Sonuc",
                    ["PENDING", "CORRECT", "WRONG", "PARTIAL"],
                    key=f"outcome_{p['id']}",
                )
            with c2:
                lesson = st.text_input("Ders", key=f"lesson_{p['id']}")

            notes = st.text_area("Notlar", key=f"notes_{p['id']}", height=80)

            if st.button("Guncelle", key=f"update_{p['id']}"):
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
