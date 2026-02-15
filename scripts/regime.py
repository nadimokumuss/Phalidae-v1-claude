"""
Phalidae v2 - Market Regime Detection
Classifies market state using existing indicators from indicators.py:
ADX, Choppiness, ATR, BB width, KC width, EMA slope.
"""

from enum import Enum

import numpy as np
import pandas as pd


class MarketRegime(Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    BREAKOUT = "BREAKOUT"


def classify_regime(df: pd.DataFrame) -> MarketRegime:
    """
    Classify market regime for the last bar using pre-computed indicators.
    Expects df to already have indicators computed via compute_all_indicators().
    """
    if df.empty or len(df) < 2:
        return MarketRegime.RANGING

    last = df.iloc[-1]

    adx = last.get("adx") if "adx" in df.columns else None
    chop = last.get("choppiness") if "choppiness" in df.columns else None

    # EMA50 slope: percentage change over last 5 bars
    ema_slope = 0.0
    if "ema_50" in df.columns and len(df) >= 6:
        ema_now = df["ema_50"].iloc[-1]
        ema_prev = df["ema_50"].iloc[-6]
        if pd.notna(ema_now) and pd.notna(ema_prev) and ema_prev > 0:
            ema_slope = (ema_now - ema_prev) / ema_prev

    # ATR percentile (rolling 100 bar window)
    atr_pctile = 50.0
    if "atr" in df.columns:
        atr_series = df["atr"].dropna()
        if len(atr_series) >= 20:
            current_atr = atr_series.iloc[-1]
            window = atr_series.tail(100)
            atr_pctile = (window < current_atr).sum() / len(window) * 100

    # BB width vs KC width for squeeze detection
    bb_width = last.get("bb_width") if "bb_width" in df.columns else None
    kc_width = last.get("kc_width") if "kc_width" in df.columns else None

    # Classification logic
    adx_val = adx if pd.notna(adx) else 20
    chop_val = chop if pd.notna(chop) else 50

    # Squeeze: BB inside KC → potential breakout
    if bb_width is not None and kc_width is not None:
        if pd.notna(bb_width) and pd.notna(kc_width) and kc_width > 0:
            if bb_width < kc_width:
                # Check if squeeze is releasing (ADX rising)
                if adx_val > 20:
                    return MarketRegime.BREAKOUT
                return MarketRegime.LOW_VOLATILITY

    # High volatility
    if atr_pctile > 80:
        return MarketRegime.HIGH_VOLATILITY

    # Strong trend
    if adx_val > 25:
        if ema_slope > 0.001:
            return MarketRegime.TRENDING_UP
        elif ema_slope < -0.001:
            return MarketRegime.TRENDING_DOWN

    # Choppy / ranging
    if chop_val > 61.8:
        return MarketRegime.RANGING

    # Weak trend based on EMA slope
    if ema_slope > 0.002:
        return MarketRegime.TRENDING_UP
    elif ema_slope < -0.002:
        return MarketRegime.TRENDING_DOWN

    return MarketRegime.RANGING


def classify_regime_series(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized regime classification for all bars (for backtest use).
    Returns a Series of MarketRegime string values aligned with df index.
    """
    n = len(df)
    regimes = pd.Series([MarketRegime.RANGING.value] * n, index=df.index)

    if n < 10:
        return regimes

    # Pre-compute all needed series
    adx = df["adx"] if "adx" in df.columns else pd.Series([20.0] * n, index=df.index)
    chop = df["choppiness"] if "choppiness" in df.columns else pd.Series([50.0] * n, index=df.index)

    # EMA slope (5-bar lookback)
    ema_slope = pd.Series([0.0] * n, index=df.index)
    if "ema_50" in df.columns:
        ema = df["ema_50"]
        ema_prev = ema.shift(5)
        mask = (ema_prev > 0) & ema_prev.notna() & ema.notna()
        ema_slope[mask] = (ema[mask] - ema_prev[mask]) / ema_prev[mask]

    # ATR percentile (rolling 100)
    atr_pctile = pd.Series([50.0] * n, index=df.index)
    if "atr" in df.columns:
        atr = df["atr"]
        rolling_rank = atr.rolling(100, min_periods=20).rank(pct=True) * 100
        valid = rolling_rank.notna()
        atr_pctile[valid] = rolling_rank[valid]

    # BB/KC squeeze
    has_squeeze_data = "bb_width" in df.columns and "kc_width" in df.columns
    if has_squeeze_data:
        bb_w = df["bb_width"]
        kc_w = df["kc_width"]
        squeeze = (bb_w < kc_w) & bb_w.notna() & kc_w.notna() & (kc_w > 0)
        breakout_mask = squeeze & (adx > 20)
        low_vol_mask = squeeze & (adx <= 20)
        regimes[breakout_mask] = MarketRegime.BREAKOUT.value
        regimes[low_vol_mask] = MarketRegime.LOW_VOLATILITY.value

    # High volatility (overrides squeeze for extreme cases)
    high_vol_mask = atr_pctile > 80
    if has_squeeze_data:
        bb_w = df["bb_width"]
        kc_w = df["kc_width"]
        squeeze = (bb_w < kc_w) & bb_w.notna() & kc_w.notna() & (kc_w > 0)
        high_vol_mask = high_vol_mask & ~squeeze
    regimes[high_vol_mask] = MarketRegime.HIGH_VOLATILITY.value

    # Trending (ADX > 25 and not already classified)
    unclassified = regimes == MarketRegime.RANGING.value
    strong_trend = (adx > 25) & adx.notna() & unclassified
    trend_up = strong_trend & (ema_slope > 0.001)
    trend_down = strong_trend & (ema_slope < -0.001)
    regimes[trend_up] = MarketRegime.TRENDING_UP.value
    regimes[trend_down] = MarketRegime.TRENDING_DOWN.value

    # Choppy
    unclassified = regimes == MarketRegime.RANGING.value
    choppy = (chop > 61.8) & chop.notna() & unclassified
    regimes[choppy] = MarketRegime.RANGING.value  # Already default

    # Weak trend from EMA slope
    unclassified = regimes == MarketRegime.RANGING.value
    weak_up = unclassified & (ema_slope > 0.002)
    weak_down = unclassified & (ema_slope < -0.002)
    regimes[weak_up] = MarketRegime.TRENDING_UP.value
    regimes[weak_down] = MarketRegime.TRENDING_DOWN.value

    return regimes


def get_regime_details(df: pd.DataFrame) -> dict:
    """Return regime classification with raw indicator values for the last bar."""
    regime = classify_regime(df)
    last = df.iloc[-1] if not df.empty else {}

    adx_val = last.get("adx") if "adx" in df.columns else None
    chop_val = last.get("choppiness") if "choppiness" in df.columns else None
    atr_val = last.get("atr") if "atr" in df.columns else None

    ema_slope = 0.0
    if "ema_50" in df.columns and len(df) >= 6:
        ema_now = df["ema_50"].iloc[-1]
        ema_prev = df["ema_50"].iloc[-6]
        if pd.notna(ema_now) and pd.notna(ema_prev) and ema_prev > 0:
            ema_slope = (ema_now - ema_prev) / ema_prev

    atr_pctile = 50.0
    if "atr" in df.columns:
        atr_series = df["atr"].dropna()
        if len(atr_series) >= 20:
            window = atr_series.tail(100)
            atr_pctile = (window < atr_series.iloc[-1]).sum() / len(window) * 100

    return {
        "regime": regime.value,
        "adx": round(float(adx_val), 2) if pd.notna(adx_val) else None,
        "choppiness": round(float(chop_val), 2) if pd.notna(chop_val) else None,
        "atr_percentile": round(atr_pctile, 1),
        "ema_slope": round(ema_slope, 6),
    }
