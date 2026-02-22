"""
Phalidae v2 - Walk-Forward Backtest Engine
Runs strategy variants against historical OHLCV data.
compute_all_indicators() is called once per symbol/timeframe,
then each variant reads only its selected columns.
"""

import json
import logging
import numpy as np
import pandas as pd

from indicators import compute_all_indicators, score_selected_indicators
from patterns import detect_all_patterns, score_patterns
from regime import classify_regime_series

logger = logging.getLogger("phalidae.backtester")

# Default backtest parameters
DEFAULT_LEVERAGE = 5.0
DEFAULT_POSITION_SIZE = 200.0   # USD (learning mode: smaller positions)
WARMUP_BARS = 200
TP_ATR_MULT = 3.0
SL_ATR_MULT = 1.25
FEE_RATE = 0.0004       # Taker fee per side (%0.04)
SLIPPAGE_RATE = 0.0002  # Estimated slippage per side (%0.02)


def _get_variant_keys(composition: dict) -> list[str]:
    """Extract all indicator keys from a variant composition."""
    keys = []
    for cat in ["trend", "entry", "volume", "volatility"]:
        keys.extend(composition.get(cat, []))
    return keys


def _check_signal(
    df: pd.DataFrame,
    bar_idx: int,
    keys: list[str],
    trend_threshold: float,
    entry_threshold: float,
    volume_required: bool,
    composition: dict,
    custom_weights: dict = None,
) -> str | None:
    """
    Check if a strategy variant triggers a signal at bar_idx.
    Returns 'LONG', 'SHORT', or None.
    """
    if bar_idx < 2:
        return None

    # Score only selected indicators using last 2 bars context
    sub_df = df.iloc[:bar_idx + 1]
    result = score_selected_indicators(sub_df, keys, custom_weights=custom_weights)

    all_scores = result["scores"]

    # Category scores
    trend_scores = [all_scores.get(k, 0) for k in composition.get("trend", [])]
    entry_scores = [all_scores.get(k, 0) for k in composition.get("entry", [])]
    volume_scores = [all_scores.get(k, 0) for k in composition.get("volume", [])]

    avg_trend = np.mean(trend_scores) if trend_scores else 0
    avg_entry = np.mean(entry_scores) if entry_scores else 0
    avg_volume = np.mean(volume_scores) if volume_scores else 0

    # LONG signal check
    if avg_trend >= trend_threshold and avg_entry >= entry_threshold:
        if not volume_required or avg_volume > 0:
            return "LONG"

    # SHORT signal check
    if avg_trend <= -trend_threshold and avg_entry <= -entry_threshold:
        if not volume_required or avg_volume < 0:
            return "SHORT"

    return None


def _simulate_trade(
    df: pd.DataFrame,
    entry_idx: int,
    bias: str,
    atr: float,
    tp_atr_mult: float = TP_ATR_MULT,
    sl_atr_mult: float = SL_ATR_MULT,
) -> dict | None:
    """
    Simulate a trade from entry_idx forward.
    Walk through subsequent bars to find TP/SL hit.
    Returns trade result dict or None if can't simulate.
    """
    if atr <= 0 or entry_idx >= len(df) - 1:
        return None

    entry_price = df["close"].iloc[entry_idx]
    if entry_price <= 0:
        return None

    if bias == "LONG":
        tp_price = entry_price + tp_atr_mult * atr
        sl_price = entry_price - sl_atr_mult * atr
    else:
        tp_price = entry_price - tp_atr_mult * atr
        sl_price = entry_price + sl_atr_mult * atr

    # Round-trip fee+slippage cost as percentage of position (leveraged)
    fee_cost_pct = (FEE_RATE * 2 + SLIPPAGE_RATE * 2) * DEFAULT_LEVERAGE * 100

    max_bars = min(100, len(df) - entry_idx - 1)  # Max hold 100 bars

    # Track MFE/MAE and trailing stop
    max_favorable = 0.0
    max_adverse = 0.0
    trailing_sl = sl_price

    for i in range(1, max_bars + 1):
        bar = df.iloc[entry_idx + i]
        high = bar["high"]
        low = bar["low"]

        if bias == "LONG":
            # MFE/MAE tracking
            bar_best_pct = ((high - entry_price) / entry_price) * DEFAULT_LEVERAGE * 100
            bar_worst_pct = ((low - entry_price) / entry_price) * DEFAULT_LEVERAGE * 100
            max_favorable = max(max_favorable, bar_best_pct)
            max_adverse = min(max_adverse, bar_worst_pct)

            # 3-tier trailing stop (matches live trader in analyzer.py)
            # 1.0xATR profit -> SL = entry (breakeven)
            # 1.5xATR profit -> SL = entry + 0.5xATR (profit lock)
            # 2.0xATR profit -> trail 1xATR behind price
            current_profit = (high - entry_price)
            if current_profit >= 2 * atr:
                new_trail = high - atr
                trailing_sl = max(trailing_sl, new_trail)
            elif current_profit >= 1.5 * atr:
                target = entry_price + 0.5 * atr
                trailing_sl = max(trailing_sl, target)
            elif current_profit >= 1.0 * atr:
                trailing_sl = max(trailing_sl, entry_price)

            if high >= tp_price:
                pnl_pct = ((tp_price - entry_price) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct
                return {"result": "TP", "pnl_pct": pnl_pct, "bars_held": i, "mfe_pct": max_favorable, "mae_pct": max_adverse}
            if low <= trailing_sl:
                exit_p = trailing_sl
                pnl_pct = ((exit_p - entry_price) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct
                result_type = "TRAILING_STOP" if trailing_sl > sl_price else "SL"
                return {"result": result_type, "pnl_pct": pnl_pct, "bars_held": i, "mfe_pct": max_favorable, "mae_pct": max_adverse}
        else:  # SHORT
            bar_best_pct = ((entry_price - low) / entry_price) * DEFAULT_LEVERAGE * 100
            bar_worst_pct = ((entry_price - high) / entry_price) * DEFAULT_LEVERAGE * 100
            max_favorable = max(max_favorable, bar_best_pct)
            max_adverse = min(max_adverse, bar_worst_pct)

            # 3-tier trailing stop (matches live trader in analyzer.py)
            # 1.0xATR profit -> SL = entry (breakeven)
            # 1.5xATR profit -> SL = entry - 0.5xATR (profit lock)
            # 2.0xATR profit -> trail 1xATR behind price
            current_profit = (entry_price - low)
            if current_profit >= 2 * atr:
                new_trail = low + atr
                trailing_sl = min(trailing_sl, new_trail)
            elif current_profit >= 1.5 * atr:
                target = entry_price - 0.5 * atr
                trailing_sl = min(trailing_sl, target)
            elif current_profit >= 1.0 * atr:
                trailing_sl = min(trailing_sl, entry_price)

            if low <= tp_price:
                pnl_pct = ((entry_price - tp_price) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct
                return {"result": "TP", "pnl_pct": pnl_pct, "bars_held": i, "mfe_pct": max_favorable, "mae_pct": max_adverse}
            if high >= trailing_sl:
                exit_p = trailing_sl
                pnl_pct = ((entry_price - exit_p) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct
                result_type = "TRAILING_STOP" if trailing_sl < sl_price else "SL"
                return {"result": result_type, "pnl_pct": pnl_pct, "bars_held": i, "mfe_pct": max_favorable, "mae_pct": max_adverse}

    # Time stop - close at last bar
    exit_price = df["close"].iloc[entry_idx + max_bars]
    if bias == "LONG":
        pnl_pct = ((exit_price - entry_price) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct
    else:
        pnl_pct = ((entry_price - exit_price) / entry_price) * DEFAULT_LEVERAGE * 100 - fee_cost_pct

    return {"result": "TIME_EXPIRED", "pnl_pct": pnl_pct, "bars_held": max_bars, "mfe_pct": max_favorable, "mae_pct": max_adverse}


def backtest_variant(
    df: pd.DataFrame,
    composition: dict,
    trend_threshold: float = 0.3,
    entry_threshold: float = 0.3,
    volume_required: bool = True,
    custom_weights: dict = None,
    tp_atr_mult: float = 2.5,
    sl_atr_mult: float = 1.5,
) -> dict:
    """
    Walk-forward backtest of a strategy variant on pre-computed DataFrame.

    Args:
        df: DataFrame with all indicators already computed (via compute_all_indicators)
        composition: {"trend": [...], "entry": [...], "volume": [...], "volatility": [...]}
        trend_threshold: Minimum average trend score for signal
        entry_threshold: Minimum average entry score for signal
        volume_required: Whether volume confirmation is needed
        custom_weights: Optional per-variant indicator weight overrides
        tp_atr_mult: TP distance in ATR multiples (default 3.0)
        sl_atr_mult: SL distance in ATR multiples (default 1.25)

    Returns:
        dict with total_trades, winning_trades, losing_trades, win_rate,
             profit_factor, sharpe_ratio, max_drawdown, total_pnl_pct
    """
    keys = _get_variant_keys(composition)
    if not keys:
        return _empty_result()

    n = len(df)
    if n < WARMUP_BARS + 20:
        return _empty_result()

    # Compute regime series for regime-aware scoring
    regime_series = classify_regime_series(df)

    trades = []
    in_trade = False
    cooldown = 0

    for i in range(WARMUP_BARS, n - 1):
        if cooldown > 0:
            cooldown -= 1
            continue

        if in_trade:
            continue

        signal = _check_signal(
            df, i, keys, trend_threshold, entry_threshold, volume_required, composition,
            custom_weights=custom_weights,
        )
        if signal is None:
            continue

        atr = df["atr"].iloc[i] if "atr" in df.columns and pd.notna(df["atr"].iloc[i]) else 0
        if atr <= 0:
            continue

        result = _simulate_trade(df, i, signal, atr, tp_atr_mult=tp_atr_mult, sl_atr_mult=sl_atr_mult)
        if result:
            # Tag trade with regime at entry
            result["regime"] = regime_series.iloc[i]
            trades.append(result)
            cooldown = result["bars_held"] + 2  # Skip bars held + buffer

    return _compute_metrics(trades)


def _empty_result() -> dict:
    return {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "sharpe_ratio": 0.0,
        "max_drawdown": 0.0,
        "total_pnl_pct": 0.0,
        "regime_trending_score": 0.0,
        "regime_ranging_score": 0.0,
        "regime_volatile_score": 0.0,
    }


def _compute_metrics(trades: list[dict]) -> dict:
    """Compute performance metrics from a list of trade results."""
    if not trades:
        return _empty_result()

    total = len(trades)
    pnls = [t["pnl_pct"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    win_rate = len(wins) / total if total > 0 else 0
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (10.0 if gross_profit > 0 else 0)

    # Sharpe ratio (annualized, assuming ~365 trades/year is max)
    pnl_array = np.array(pnls)
    mean_pnl = np.mean(pnl_array)
    std_pnl = np.std(pnl_array) if len(pnl_array) > 1 else 1
    sharpe = (mean_pnl / std_pnl) * np.sqrt(min(total, 365)) if std_pnl > 0 else 0

    # Max drawdown from cumulative P&L
    cum_pnl = np.cumsum(pnl_array)
    peak = np.maximum.accumulate(cum_pnl)
    drawdown = peak - cum_pnl
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0

    # Regime-specific win rates
    regime_scores = _compute_regime_scores(trades)

    return {
        "total_trades": total,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(min(profit_factor, 10.0), 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "total_pnl_pct": round(sum(pnls), 2),
        "regime_trending_score": regime_scores.get("trending", 0.0),
        "regime_ranging_score": regime_scores.get("ranging", 0.0),
        "regime_volatile_score": regime_scores.get("volatile", 0.0),
    }


def _compute_regime_scores(trades: list[dict]) -> dict:
    """Compute win rate per regime category."""
    from regime import MarketRegime

    trending_regimes = {MarketRegime.TRENDING_UP.value, MarketRegime.TRENDING_DOWN.value}
    ranging_regimes = {MarketRegime.RANGING.value, MarketRegime.LOW_VOLATILITY.value}
    volatile_regimes = {MarketRegime.HIGH_VOLATILITY.value, MarketRegime.BREAKOUT.value}

    categories = {
        "trending": {"wins": 0, "total": 0},
        "ranging": {"wins": 0, "total": 0},
        "volatile": {"wins": 0, "total": 0},
    }

    for t in trades:
        regime = t.get("regime", "RANGING")
        if regime in trending_regimes:
            cat = "trending"
        elif regime in volatile_regimes:
            cat = "volatile"
        else:
            cat = "ranging"

        categories[cat]["total"] += 1
        if t["pnl_pct"] > 0:
            categories[cat]["wins"] += 1

    return {
        cat: round(data["wins"] / data["total"], 4) if data["total"] >= 5 else 0.0
        for cat, data in categories.items()
    }
