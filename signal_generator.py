"""
Phalidae v2 - Sinyal Üretici
67 indikatör + 60 mum formasyonu + 12 S/R yöntemi + chart patterns + trend lines
Legacy API (analyze_symbol, scan_market) korunur.
Yeni: analyze_symbol_with_strategy() strateji bazlı analiz + DB okuma.
"""

import json
import pandas as pd
import numpy as np
import ccxt

from indicators import compute_all_indicators, score_all_indicators, score_selected_indicators
from patterns import detect_all_patterns, score_patterns
from levels import get_all_levels


def _init_exchange() -> ccxt.binanceusdm:
    return ccxt.binanceusdm({"enableRateLimit": True})


def fetch_ohlcv(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str = "4h",
    limit: int = 200,
) -> pd.DataFrame:
    bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def get_top_symbols(exchange: ccxt.Exchange, top_n: int = 30) -> list[str]:
    """Hacme göre en aktif USDT perpetual sembollerini döndürür."""
    tickers = exchange.fetch_tickers()
    usdt_pairs = []
    for sym, t in tickers.items():
        if sym.endswith("/USDT:USDT"):
            usdt_pairs.append((sym, t.get("quoteVolume", 0) or 0))
    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in usdt_pairs[:top_n]]


def calculate_optimal_tp_sl(
    entry: float,
    atr: float,
    bias: str,
    all_levels: dict,
    fib_data: dict,
) -> dict:
    """
    Çoklu yöntem kullanarak en optimal TP ve SL hesaplar:
    1. ATR bazlı (temel)
    2. En güçlü S/R seviyeleri
    3. Fibonacci seviyeleri
    4. Volume Profile (POC, VAH, VAL)
    5. Trend çizgisi seviyeleri
    6. Chart pattern hedefleri

    Tüm yöntemlerin sonuçlarını ağırlıklı olarak birleştirir.
    """
    supports = all_levels["supports"]
    resistances = all_levels["resistances"]
    chart_patterns = all_levels.get("chart_patterns", [])
    vol_prof = all_levels.get("volume_profile", {})

    tp_candidates = []
    sl_candidates = []

    if bias == "LONG":
        # ── SL Adayları ──
        # ATR bazlı
        sl_candidates.append({"price": entry - 1.5 * atr, "weight": 2, "method": "ATR 1.5x"})
        sl_candidates.append({"price": entry - 2.0 * atr, "weight": 1.5, "method": "ATR 2.0x"})

        # Destek seviyeleri (ağırlıklı)
        for s in supports[:10]:
            if s["price"] < entry and s["price"] > entry * 0.9:  # Max %10 uzakta
                sl_candidates.append({"price": s["price"], "weight": s["weight"], "method": s["method"]})

        # ── TP Adayları ──
        # ATR bazlı
        tp_candidates.append({"price": entry + 2.0 * atr, "weight": 1.5, "method": "ATR 2.0x"})
        tp_candidates.append({"price": entry + 3.0 * atr, "weight": 2, "method": "ATR 3.0x"})
        tp_candidates.append({"price": entry + 4.0 * atr, "weight": 1, "method": "ATR 4.0x"})

        # Direnç seviyeleri
        for r in resistances[:10]:
            if r["price"] > entry:
                tp_candidates.append({"price": r["price"], "weight": r["weight"], "method": r["method"]})

        # Fibonacci extension
        for ext in all_levels.get("fib_extensions", []):
            if ext["price"] > entry:
                tp_candidates.append({"price": ext["price"], "weight": 2, "method": f"Fib Ext {ext['ext_level']}"})

        # Chart pattern hedefleri
        for cp in chart_patterns:
            if cp["bias"] == "Bullish" and cp.get("target") and cp["target"] > entry:
                tp_candidates.append({"price": cp["target"], "weight": cp["strength"], "method": cp["pattern"]})

    elif bias == "SHORT":
        # ── SL Adayları ──
        sl_candidates.append({"price": entry + 1.5 * atr, "weight": 2, "method": "ATR 1.5x"})
        sl_candidates.append({"price": entry + 2.0 * atr, "weight": 1.5, "method": "ATR 2.0x"})

        for r in resistances[:10]:
            if r["price"] > entry and r["price"] < entry * 1.1:
                sl_candidates.append({"price": r["price"], "weight": r["weight"], "method": r["method"]})

        # ── TP Adayları ──
        tp_candidates.append({"price": entry - 2.0 * atr, "weight": 1.5, "method": "ATR 2.0x"})
        tp_candidates.append({"price": entry - 3.0 * atr, "weight": 2, "method": "ATR 3.0x"})
        tp_candidates.append({"price": entry - 4.0 * atr, "weight": 1, "method": "ATR 4.0x"})

        for s in supports[:10]:
            if s["price"] < entry:
                tp_candidates.append({"price": s["price"], "weight": s["weight"], "method": s["method"]})

        for ext in all_levels.get("fib_extensions", []):
            if ext["price"] < entry:
                tp_candidates.append({"price": ext["price"], "weight": 2, "method": f"Fib Ext {ext['ext_level']}"})

        for cp in chart_patterns:
            if cp["bias"] == "Bearish" and cp.get("target") and cp["target"] < entry:
                tp_candidates.append({"price": cp["target"], "weight": cp["strength"], "method": cp["pattern"]})

    else:
        return {"tp": None, "sl": None, "rr_ratio": None, "tp_method": "", "sl_method": ""}

    if not tp_candidates or not sl_candidates:
        return {"tp": None, "sl": None, "rr_ratio": None, "tp_method": "", "sl_method": ""}

    # Ağırlıklı ortalama ile en iyi seviyeyi seç
    def weighted_select(candidates):
        total_w = sum(c["weight"] for c in candidates)
        if total_w == 0:
            return candidates[0]["price"], candidates[0]["method"]
        wp = sum(c["price"] * c["weight"] for c in candidates) / total_w
        # En yakın adayı bul
        best = min(candidates, key=lambda c: abs(c["price"] - wp))
        return round(wp, 6), best["method"]

    # SL: en yakın güçlü adayları seç (max 5)
    sl_candidates.sort(key=lambda x: x["weight"], reverse=True)
    sl_price, sl_method = weighted_select(sl_candidates[:5])

    # TP: en yakın güçlü adayları seç (max 5)
    tp_candidates.sort(key=lambda x: x["weight"], reverse=True)
    tp_price, tp_method = weighted_select(tp_candidates[:5])

    # R:R hesapla
    risk = abs(entry - sl_price)
    reward = abs(tp_price - entry)
    rr = round(reward / risk, 2) if risk > 0 else 0

    return {
        "tp": round(tp_price, 6),
        "sl": round(sl_price, 6),
        "rr_ratio": rr,
        "tp_method": tp_method,
        "sl_method": sl_method,
        "tp_candidates": tp_candidates[:5],
        "sl_candidates": sl_candidates[:5],
    }


def analyze_symbol(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframes: list[str] | None = None,
) -> dict | None:
    """
    Tek bir sembolü tam kapsamlı analiz eder.
    35 indikatör + 51 mum formasyonu + 12 S/R yöntemi + chart patterns
    """
    if timeframes is None:
        timeframes = ["15m", "1h", "4h"]

    tf_results = {}

    for tf in timeframes:
        try:
            df = fetch_ohlcv(exchange, symbol, tf, 200)
            df = compute_all_indicators(df)
            levels = get_all_levels(df)
            patterns = detect_all_patterns(df)
            ind_score = score_all_indicators(df)
            pattern_score = score_patterns(patterns)
            atr = df["atr"].iloc[-1] if pd.notna(df["atr"].iloc[-1]) else 0

            tf_results[tf] = {
                "df": df,
                "levels": levels,
                "patterns": patterns,
                "pattern_score": pattern_score,
                "ind_score": ind_score,
                "atr": atr,
                "last_close": df["close"].iloc[-1],
            }
        except Exception:
            continue

    if not tf_results:
        return None

    # ── Çoklu TF skorlarını birleştir ──
    weights = {"5m": 0.05, "15m": 0.15, "1h": 0.25, "4h": 0.35, "1d": 0.20}
    weighted_ind = 0
    weighted_pat = 0
    total_weight = 0

    for tf, data in tf_results.items():
        w = weights.get(tf, 0.2)
        weighted_ind += data["ind_score"]["total_normalized"] * w
        weighted_pat += data["pattern_score"] * w
        total_weight += w

    if total_weight > 0:
        final_ind_score = weighted_ind / total_weight
        final_pat_score = weighted_pat / total_weight
    else:
        return None

    # Chart pattern bonusu (en büyük TF'den)
    chart_pattern_bonus = 0
    primary_tf = "4h" if "4h" in tf_results else list(tf_results.keys())[-1]
    primary = tf_results[primary_tf]
    chart_pats = primary["levels"].get("chart_patterns", [])
    for cp in chart_pats:
        if cp["bias"] == "Bullish":
            chart_pattern_bonus += cp["strength"] * 0.4
        elif cp["bias"] == "Bearish":
            chart_pattern_bonus -= cp["strength"] * 0.4
    chart_pattern_bonus = np.clip(chart_pattern_bonus, -3, 3)

    # Trend line bonusu
    trend_line_bonus = 0
    tlines = primary["levels"].get("trend_lines", [])
    for tl in tlines:
        distance = abs(primary["last_close"] - tl["current_value"]) / primary["last_close"]
        if distance < 0.01:  # Fiyat trend çizgisine %1'den yakın
            if tl["bias"] == "Bullish":
                trend_line_bonus += tl["touches"] * 0.3
            else:
                trend_line_bonus -= tl["touches"] * 0.3
    trend_line_bonus = np.clip(trend_line_bonus, -2, 2)

    # TOPLAM SKOR
    final_score = round(final_ind_score + final_pat_score + chart_pattern_bonus + trend_line_bonus, 1)

    # Yön kararı
    if final_score >= 2.5:
        bias = "LONG"
    elif final_score <= -2.5:
        bias = "SHORT"
    else:
        return None

    # Güven seviyesi
    abs_score = abs(final_score)
    if abs_score >= 6:
        confidence = "YÜKSEK"
    elif abs_score >= 4:
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    entry = primary["last_close"]
    atr = primary["atr"]

    # TP/SL hesapla
    tp_sl = calculate_optimal_tp_sl(
        entry=entry,
        atr=atr,
        bias=bias,
        all_levels=primary["levels"],
        fib_data=primary["levels"].get("fibonacci", {}),
    )

    if tp_sl["rr_ratio"] is None or tp_sl["rr_ratio"] < 1.8:
        return None

    # Tüm formasyonları topla
    all_patterns = []
    for tf, data in tf_results.items():
        for p in data["patterns"]:
            all_patterns.append({**p, "timeframe": tf})

    # Detaylı indikatör skorları
    indicator_details = {}
    for tf, data in tf_results.items():
        indicator_details[tf] = {
            "scores": data["ind_score"]["scores"],
            "count": data["ind_score"]["indicator_count"],
            "normalized": data["ind_score"]["total_normalized"],
        }

    return {
        "symbol": symbol,
        "bias": bias,
        "entry": round(entry, 6),
        "tp": tp_sl["tp"],
        "sl": tp_sl["sl"],
        "rr_ratio": tp_sl["rr_ratio"],
        "tp_method": tp_sl["tp_method"],
        "sl_method": tp_sl["sl_method"],
        "confidence": confidence,
        "score": final_score,
        "score_breakdown": {
            "indicators": round(final_ind_score, 1),
            "candle_patterns": round(final_pat_score, 1),
            "chart_patterns": round(chart_pattern_bonus, 1),
            "trend_lines": round(trend_line_bonus, 1),
        },
        "patterns": all_patterns,
        "chart_patterns": chart_pats,
        "trend_lines": tlines,
        "supports": primary["levels"]["supports"][:5],
        "resistances": primary["levels"]["resistances"][:5],
        "fibonacci": primary["levels"].get("fibonacci", {}),
        "volume_profile": primary["levels"].get("volume_profile", {}),
        "order_blocks": primary["levels"].get("order_blocks", []),
        "fvg": primary["levels"].get("fvg", []),
        "indicator_details": indicator_details,
        "tp_sl_candidates": {
            "tp": tp_sl.get("tp_candidates", []),
            "sl": tp_sl.get("sl_candidates", []),
        },
    }


def scan_market(top_n: int = 30, timeframes: list[str] | None = None) -> list[dict]:
    """Piyasayı tarar, tüm coinleri tam kapsamlı analiz eder."""
    exchange = _init_exchange()
    symbols = get_top_symbols(exchange, top_n)
    signals = []

    for sym in symbols:
        result = analyze_symbol(exchange, sym, timeframes)
        if result:
            signals.append(result)

    signals.sort(key=lambda x: abs(x["score"]), reverse=True)
    return signals


# ═══════════════════════════════════════════════════
# v2: Strategy-based analysis (reads from DB)
# ═══════════════════════════════════════════════════

def analyze_symbol_with_strategy(
    df: pd.DataFrame,
    symbol: str,
    composition: dict,
    trend_threshold: float = 0.3,
    entry_threshold: float = 0.3,
    volume_required: bool = True,
) -> dict | None:
    """
    Analyze a symbol using a specific strategy variant's indicator subset.
    Uses pre-loaded DataFrame (from DB or fresh fetch).

    Args:
        df: DataFrame with OHLCV data (indicators will be computed)
        symbol: Symbol name
        composition: Strategy composition dict with trend/entry/volume/volatility keys
        trend_threshold: Min avg trend score for signal
        entry_threshold: Min avg entry score for signal
        volume_required: Whether volume confirmation needed

    Returns:
        Signal dict or None
    """
    if df.empty or len(df) < 50:
        return None

    # Compute all indicators
    df = compute_all_indicators(df)

    # Get selected indicator keys
    keys = []
    for cat in ["trend", "entry", "volume", "volatility"]:
        keys.extend(composition.get(cat, []))

    if not keys:
        return None

    # Score selected indicators
    result = score_selected_indicators(df, keys)
    all_scores = result["scores"]

    # Check category thresholds
    trend_scores = [all_scores.get(k, 0) for k in composition.get("trend", [])]
    entry_scores = [all_scores.get(k, 0) for k in composition.get("entry", [])]
    volume_scores = [all_scores.get(k, 0) for k in composition.get("volume", [])]

    avg_trend = np.mean(trend_scores) if trend_scores else 0
    avg_entry = np.mean(entry_scores) if entry_scores else 0
    avg_volume = np.mean(volume_scores) if volume_scores else 0

    # Determine bias from category scores
    if avg_trend >= trend_threshold and avg_entry >= entry_threshold:
        if not volume_required or avg_volume > 0:
            bias = "LONG"
        else:
            return None
    elif avg_trend <= -trend_threshold and avg_entry <= -entry_threshold:
        if not volume_required or avg_volume < 0:
            bias = "SHORT"
        else:
            return None
    else:
        return None

    # Patterns and levels
    patterns = detect_all_patterns(df)
    pattern_score = score_patterns(patterns)
    levels = get_all_levels(df)

    total_score = result["total_normalized"] + pattern_score

    # TP/SL
    atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else 0
    if atr <= 0:
        return None

    entry_price = df["close"].iloc[-1]
    tp_sl = calculate_optimal_tp_sl(
        entry=entry_price,
        atr=atr,
        bias=bias,
        all_levels=levels,
        fib_data=levels.get("fibonacci", {}),
    )

    if tp_sl["rr_ratio"] is None or tp_sl["rr_ratio"] < 1.8:
        return None

    abs_score = abs(total_score)
    if abs_score >= 6:
        confidence = "YÜKSEK"
    elif abs_score >= 4:
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    return {
        "symbol": symbol,
        "bias": bias,
        "entry": round(entry_price, 6),
        "tp": tp_sl["tp"],
        "sl": tp_sl["sl"],
        "rr_ratio": tp_sl["rr_ratio"],
        "tp_method": tp_sl["tp_method"],
        "sl_method": tp_sl["sl_method"],
        "confidence": confidence,
        "score": round(total_score, 1),
        "score_breakdown": {
            "indicators": result["total_normalized"],
            "patterns": round(pattern_score, 1),
            "trend_avg": round(avg_trend, 2),
            "entry_avg": round(avg_entry, 2),
            "volume_avg": round(avg_volume, 2),
        },
        "indicator_scores": result["scores"],
        "all_indicator_scores": result.get("all_scores", {}),
        "patterns": [
            {"pattern": p["pattern"], "bias": p["bias"], "strength": p["strength"]}
            for p in patterns[:20]
        ],
        "supports": levels["supports"][:5],
        "resistances": levels["resistances"][:5],
        "tp_sl_candidates": {
            "tp": tp_sl.get("tp_candidates", []),
            "sl": tp_sl.get("sl_candidates", []),
        },
    }


def get_recent_signals_from_db(limit: int = 50) -> list[dict]:
    """Fetch recent signals from database."""
    try:
        from db.engine import get_session
        from db.models import Signal, StrategyVariant
    except ImportError:
        return []

    session = get_session()
    try:
        rows = (
            session.query(Signal, StrategyVariant.name)
            .outerjoin(StrategyVariant, Signal.strategy_variant_id == StrategyVariant.id)
            .order_by(Signal.created_at.desc())
            .limit(limit)
            .all()
        )

        signals = []
        for sig, strat_name in rows:
            signals.append({
                "id": sig.id,
                "symbol": sig.symbol,
                "bias": sig.bias,
                "entry": sig.entry_price,
                "tp": sig.tp_price,
                "sl": sig.sl_price,
                "rr_ratio": sig.rr_ratio,
                "confidence": sig.confidence,
                "score": sig.score,
                "strategy_name": strat_name or "Legacy",
                "reasoning": sig.reasoning or "",
                "score_breakdown": json.loads(sig.score_breakdown) if sig.score_breakdown else {},
                "indicator_scores": json.loads(sig.indicator_scores) if sig.indicator_scores else {},
                "detected_patterns": json.loads(sig.detected_patterns) if sig.detected_patterns else [],
                "created_at": sig.created_at.isoformat() if sig.created_at else "",
            })
        return signals
    except Exception:
        return []
    finally:
        session.close()
