"""
Phalidae v2 - Signal Analyzer & Trade Checker Worker
Runs every 15 min (analyzer) and 5 min (trade checker).
Includes: regime-aware strategy selection, trailing stop, time stop, decision trace.
"""

import json
import logging
from datetime import datetime

import ccxt
import pandas as pd

from db.engine import get_session
from db.models import (
    TrackedSymbol, CoinConfig, StrategyVariant, StrategyPerformance, Signal, PaperTrade,
)
from indicators import compute_all_indicators, score_selected_indicators
from patterns import detect_all_patterns, score_patterns
from levels import get_all_levels
from worker.collector import get_ohlcv_df
from paper_trader.trader import open_paper_trade, close_paper_trade, record_snapshot
from paper_trader.position import generate_reasoning
from regime import classify_regime, get_regime_details, MarketRegime

logger = logging.getLogger("phalidae.analyzer")

_exchange = None


def _get_exchange() -> ccxt.binanceusdm:
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binanceusdm({"enableRateLimit": True})
    return _exchange


def _get_current_price(symbol: str) -> float | None:
    """Fetch current price from exchange."""
    try:
        ticker = _get_exchange().fetch_ticker(symbol)
        return ticker.get("last")
    except Exception:
        return None


def _get_current_atr(symbol: str) -> float:
    """Get current ATR for a symbol from latest 4h data."""
    df = get_ohlcv_df(symbol, "4h", limit=50)
    if df.empty or len(df) < 20:
        return 0.0
    df = compute_all_indicators(df)
    atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else 0.0
    return float(atr)


def _count_bars_since_open(symbol: str, opened_at: datetime) -> int:
    """Count how many 4h bars have passed since trade was opened."""
    df = get_ohlcv_df(symbol, "4h", limit=200)
    if df.empty or "timestamp" not in df.columns:
        return 0
    bars_after = df[df["timestamp"] > opened_at]
    return len(bars_after)


def run_analysis_cycle():
    """
    Main analysis loop (called by scheduler every 15 min):
    For each active symbol that has a best_strategy assigned,
    generate a signal and optionally open a paper trade.
    Uses regime-aware strategy selection when available.
    """
    session = get_session()
    try:
        configs = (
            session.query(CoinConfig, StrategyVariant)
            .join(StrategyVariant, CoinConfig.best_strategy_id == StrategyVariant.id)
            .all()
        )
    finally:
        session.close()

    if not configs:
        logger.info("No coin configs with best strategy yet")
        return

    for config, variant in configs:
        try:
            _analyze_single(config, variant)
        except Exception as e:
            logger.error(f"Analysis error for {config.symbol}: {e}")


def _analyze_single(config: CoinConfig, variant: StrategyVariant):
    """Analyze a single symbol with regime-aware strategy selection."""
    symbol = config.symbol

    # Get data from DB (4h primary)
    df = get_ohlcv_df(symbol, "4h", limit=300)
    if df.empty or len(df) < 200:
        return

    # Compute indicators
    df = compute_all_indicators(df)

    # Detect current regime
    regime_details = get_regime_details(df)
    current_regime = regime_details["regime"]

    # Try regime-specific strategy first, fallback to general best
    best_variant = variant
    selected_variant_id = variant.id

    session = get_session()
    try:
        regime_variant = _get_regime_best_strategy(session, symbol, current_regime)
        if regime_variant is not None:
            best_variant = regime_variant
            selected_variant_id = regime_variant.id
    finally:
        session.close()

    composition = json.loads(best_variant.composition)
    keys = []
    for cat in ["trend", "entry", "volume", "volatility"]:
        keys.extend(composition.get(cat, []))

    if not keys:
        return

    result = score_selected_indicators(df, keys)

    # Patterns
    patterns = detect_all_patterns(df)
    pattern_score = score_patterns(patterns)

    # Combined score
    total_score = result["total_normalized"] + pattern_score
    bias = result["bias"]

    if bias == "NÖTR":
        return

    # TP/SL from levels
    levels = get_all_levels(df)
    atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else 0
    if atr <= 0:
        return

    entry_price = df["close"].iloc[-1]

    from signal_generator import calculate_optimal_tp_sl
    tp_sl = calculate_optimal_tp_sl(
        entry=entry_price,
        atr=atr,
        bias=bias,
        all_levels=levels,
        fib_data=levels.get("fibonacci", {}),
    )

    if tp_sl["rr_ratio"] is None or tp_sl["rr_ratio"] < 1.8:
        return

    # Confidence
    abs_score = abs(total_score)
    if abs_score >= 6:
        confidence = "YÜKSEK"
    elif abs_score >= 4:
        confidence = "ORTA"
    else:
        confidence = "DÜŞÜK"

    # Evaluate top 3 strategies for decision trace (Faz 9)
    alternative_signals, rejection_reasons = _evaluate_alternatives(
        df, symbol, current_regime, selected_variant_id, entry_price, atr, levels, patterns
    )

    # Save signal to DB
    session = get_session()
    try:
        signal = Signal(
            symbol=symbol,
            bias=bias,
            entry_price=entry_price,
            tp_price=tp_sl["tp"],
            sl_price=tp_sl["sl"],
            rr_ratio=tp_sl["rr_ratio"],
            confidence=confidence,
            score=round(total_score, 1),
            strategy_variant_id=selected_variant_id,
            score_breakdown=json.dumps({
                "indicators": result["total_normalized"],
                "patterns": pattern_score,
            }),
            indicator_scores=json.dumps(result["scores"]),
            detected_patterns=json.dumps([
                {"pattern": p["pattern"], "bias": p["bias"], "strength": p["strength"]}
                for p in patterns[:20]
            ]),
            regime=current_regime,
            alternative_signals=json.dumps(alternative_signals) if alternative_signals else None,
            rejection_reasons=json.dumps(rejection_reasons) if rejection_reasons else None,
            reasoning=generate_reasoning(
                symbol, bias, total_score,
                composition, result["scores"], patterns,
                regime=current_regime,
                alternatives=alternative_signals,
                rejections=rejection_reasons,
            ),
            created_at=datetime.utcnow(),
        )
        session.add(signal)
        session.commit()
        signal_id = signal.id
        logger.info(f"Signal #{signal_id}: {symbol} {bias} score={total_score:+.1f} regime={current_regime}")
    except Exception as e:
        session.rollback()
        logger.error(f"Signal save error: {e}")
        return
    finally:
        session.close()

    # Auto paper trade if configured
    if config.auto_trade and confidence in ("YÜKSEK", "ORTA"):
        reasoning = generate_reasoning(
            symbol, bias, total_score,
            composition, result["scores"], patterns,
            regime=current_regime,
            alternatives=alternative_signals,
            rejections=rejection_reasons,
        )
        open_paper_trade(
            signal_id=signal_id,
            symbol=symbol,
            bias=bias,
            entry_price=entry_price,
            tp_price=tp_sl["tp"],
            sl_price=tp_sl["sl"],
            reasoning=reasoning,
            regime_at_entry=current_regime,
        )


def _get_regime_best_strategy(session, symbol: str, regime: str) -> StrategyVariant | None:
    """Get the best strategy for a specific regime, if available."""
    # Map regime to score column
    if regime in ("TRENDING_UP", "TRENDING_DOWN"):
        score_col = StrategyPerformance.regime_trending_score
    elif regime in ("HIGH_VOLATILITY", "BREAKOUT"):
        score_col = StrategyPerformance.regime_volatile_score
    else:
        score_col = StrategyPerformance.regime_ranging_score

    result = (
        session.query(StrategyVariant)
        .join(StrategyPerformance, StrategyVariant.id == StrategyPerformance.strategy_variant_id)
        .filter(
            StrategyPerformance.symbol == symbol,
            score_col > 0,
        )
        .order_by(score_col.desc())
        .first()
    )
    return result


def _evaluate_alternatives(
    df, symbol, current_regime, selected_variant_id, entry_price, atr, levels, patterns
) -> tuple[list, list]:
    """Evaluate top 3 alternative strategies for decision trace."""
    alternative_signals = []
    rejection_reasons = []

    session = get_session()
    try:
        top_perfs = (
            session.query(StrategyPerformance, StrategyVariant)
            .join(StrategyVariant, StrategyPerformance.strategy_variant_id == StrategyVariant.id)
            .filter(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.composite_score > 0,
                StrategyVariant.id != selected_variant_id,
            )
            .order_by(StrategyPerformance.composite_score.desc())
            .limit(3)
            .all()
        )

        for perf, alt_variant in top_perfs:
            try:
                comp = json.loads(alt_variant.composition)
                alt_keys = []
                for cat in ["trend", "entry", "volume", "volatility"]:
                    alt_keys.extend(comp.get(cat, []))

                if not alt_keys:
                    continue

                alt_result = score_selected_indicators(df, alt_keys)
                alt_score = alt_result["total_normalized"]

                if alt_result["bias"] == "NÖTR":
                    rejection_reasons.append({
                        "strategy": alt_variant.name,
                        "reason": "Nötr sinyal (yetersiz skor)",
                        "score": round(alt_score, 2),
                    })
                else:
                    alternative_signals.append({
                        "strategy": alt_variant.name,
                        "bias": alt_result["bias"],
                        "score": round(alt_score, 2),
                        "composite": perf.composite_score,
                    })
            except Exception:
                continue
    finally:
        session.close()

    return alternative_signals, rejection_reasons


def check_open_trades():
    """
    Check all open paper trades for TP/SL/liquidation/trailing stop/time stop hits.
    Called every 5 minutes by scheduler.
    """
    session = get_session()
    try:
        open_trades = session.query(PaperTrade).filter_by(status="OPEN").all()
        trade_data = []
        for t in open_trades:
            # Load coin config for time stop setting
            coin_config = session.query(CoinConfig).filter_by(symbol=t.symbol).first()
            time_stop_bars = coin_config.time_stop_bars if coin_config and coin_config.time_stop_bars else 50
            trailing_enabled = coin_config.trailing_stop_enabled if coin_config else True

            trade_data.append({
                "id": t.id,
                "symbol": t.symbol,
                "bias": t.bias,
                "entry_price": t.entry_price,
                "tp_price": t.tp_price,
                "sl_price": t.sl_price,
                "liquidation_price": t.liquidation_price,
                "trailing_stop_price": t.trailing_stop_price or t.sl_price,
                "opened_at": t.opened_at,
                "time_stop_bars": time_stop_bars,
                "trailing_enabled": trailing_enabled,
            })
    finally:
        session.close()

    if not trade_data:
        return

    for trade in trade_data:
        try:
            current_price = _get_current_price(trade["symbol"])
            if current_price is None:
                continue

            # Record snapshot (also updates MFE/MAE)
            record_snapshot(trade["id"], current_price)

            # Time stop check
            if trade["opened_at"]:
                bars_held = _count_bars_since_open(trade["symbol"], trade["opened_at"])
                if bars_held >= trade["time_stop_bars"]:
                    close_paper_trade(trade["id"], current_price, "TIME_EXPIRED")
                    logger.info(f"Time stop: trade #{trade['id']} after {bars_held} bars")
                    continue

            # Trailing stop logic
            trailing_sl = trade["trailing_stop_price"]
            if trade["trailing_enabled"]:
                atr = _get_current_atr(trade["symbol"])
                if atr > 0:
                    trailing_sl = _update_trailing_stop(
                        trade["id"], trade["bias"], trade["entry_price"],
                        current_price, trailing_sl, atr
                    )

            # Check TP/SL/Trailing/Liquidation
            if trade["bias"] == "LONG":
                if trade["tp_price"] and current_price >= trade["tp_price"]:
                    close_paper_trade(trade["id"], current_price, "TP_HIT")
                    continue
                if trailing_sl and current_price <= trailing_sl:
                    status = "TRAILING_STOP" if trailing_sl > (trade["sl_price"] or 0) else "SL_HIT"
                    close_paper_trade(trade["id"], current_price, status)
                    continue
                if trade["liquidation_price"] and current_price <= trade["liquidation_price"]:
                    close_paper_trade(trade["id"], current_price, "LIQUIDATED")
                    continue
            else:  # SHORT
                if trade["tp_price"] and current_price <= trade["tp_price"]:
                    close_paper_trade(trade["id"], current_price, "TP_HIT")
                    continue
                if trailing_sl and current_price >= trailing_sl:
                    status = "TRAILING_STOP" if trailing_sl < (trade["sl_price"] or float('inf')) else "SL_HIT"
                    close_paper_trade(trade["id"], current_price, status)
                    continue
                if trade["liquidation_price"] and current_price >= trade["liquidation_price"]:
                    close_paper_trade(trade["id"], current_price, "LIQUIDATED")
                    continue

        except Exception as e:
            logger.error(f"Trade check error for #{trade['id']}: {e}")


def _update_trailing_stop(
    trade_id: int,
    bias: str,
    entry_price: float,
    current_price: float,
    current_trailing: float,
    atr: float,
) -> float:
    """
    Update trailing stop for a trade.
    1×ATR profit → SL to breakeven
    2×ATR profit → trail 1 ATR behind price
    Returns new trailing stop price.
    """
    if bias == "LONG":
        profit = current_price - entry_price
        if profit >= 2 * atr:
            new_trail = current_price - atr
            if new_trail > current_trailing:
                current_trailing = new_trail
        elif profit >= atr:
            if entry_price > current_trailing:
                current_trailing = entry_price
    else:  # SHORT
        profit = entry_price - current_price
        if profit >= 2 * atr:
            new_trail = current_price + atr
            if new_trail < current_trailing:
                current_trailing = new_trail
        elif profit >= atr:
            if entry_price < current_trailing:
                current_trailing = entry_price

    # Persist updated trailing stop
    session = get_session()
    try:
        trade = session.query(PaperTrade).get(trade_id)
        if trade and trade.status == "OPEN":
            trade.trailing_stop_price = current_trailing
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()

    return current_trailing
