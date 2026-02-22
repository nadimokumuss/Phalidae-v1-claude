"""
Phalidae v2 - Signal Analyzer & Trade Checker Worker
Runs every 15 min (analyzer) and 5 min (trade checker).
Phase 1: Agent health logging + CoinConfig fallback.
Phase 4: News risk filtering.
Phase 5: Enhanced decision trace + confidence scoring.
"""

import logging
from datetime import datetime, timedelta

import ccxt
import pandas as pd

from db.engine import get_session
from db.models import (
    TrackedSymbol, CoinConfig, StrategyVariant, StrategyPerformance,
    Signal, PaperTrade, AgentJob,
)
from indicators import compute_all_indicators, score_all_indicators, score_selected_indicators
from patterns import detect_all_patterns, score_patterns
from levels import get_all_levels
from worker.collector import get_ohlcv_df, _start_agent_job, _finish_agent_job
from paper_trader.trader import open_paper_trade, close_paper_trade, record_snapshot
from paper_trader.position import generate_reasoning
from regime import classify_regime, get_regime_details, MarketRegime

logger = logging.getLogger("phalidae.analyzer")

# Coins with consistently negative paper trading performance.
# These are temporarily excluded from signal generation.
# Review periodically and re-enable when market conditions change.
COIN_BLACKLIST = {
    "WLFI/USDT:USDT",   # -$54 cumulative loss, 0% win rate on LONG
    "SPACE/USDT:USDT",   # -$32 single SL_HIT in TRENDING_UP
}

# Auto-blacklist threshold: skip coins with >= this many consecutive losses
AUTO_BLACKLIST_CONSECUTIVE_LOSSES = 5
# Auto-blacklist: minimum paper trade count to evaluate
AUTO_BLACKLIST_MIN_TRADES = 5


def _is_coin_blacklisted(symbol: str) -> bool:
    """Check if a coin is on the static blacklist or has poor recent performance."""
    if symbol in COIN_BLACKLIST:
        return True

    # Dynamic check: skip coins with N consecutive recent losses
    try:
        session = get_session()
        try:
            recent_trades = (
                session.query(PaperTrade)
                .filter(
                    PaperTrade.symbol == symbol,
                    PaperTrade.status != "OPEN",
                )
                .order_by(PaperTrade.closed_at.desc())
                .limit(AUTO_BLACKLIST_MIN_TRADES)
                .all()
            )
            if len(recent_trades) >= AUTO_BLACKLIST_MIN_TRADES:
                consecutive_losses = 0
                for t in recent_trades:
                    total_pnl = (t.pnl_usd or 0) + (t.partial_tp_pnl or 0)
                    if total_pnl < 0:
                        consecutive_losses += 1
                    else:
                        break
                if consecutive_losses >= AUTO_BLACKLIST_CONSECUTIVE_LOSSES:
                    logger.info(
                        f"Auto-blacklist: {symbol} has {consecutive_losses} consecutive losses, skipping"
                    )
                    return True
        finally:
            session.close()
    except Exception:
        pass

    return False


def _to_float(val) -> float:
    """Convert numpy/pandas numeric types to native Python float for PostgreSQL."""
    if val is None:
        return 0.0
    return float(val)


def _sanitize_scores(scores: dict) -> dict:
    """Convert all values in a scores dict to native Python types."""
    return {k: float(v) if v is not None else 0.0 for k, v in scores.items()}

_exchange = None


def _get_exchange() -> ccxt.binanceusdm:
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binanceusdm({"enableRateLimit": True, "timeout": 15000})
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


def _ensure_coin_configs():
    """Create CoinConfig entries for active symbols that don't have one."""
    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        for ts in symbols:
            existing = session.query(CoinConfig).filter_by(symbol=ts.symbol).first()
            if existing is None:
                session.add(CoinConfig(symbol=ts.symbol, auto_trade=True))
        session.commit()
    except Exception as e:
        session.rollback()
        logger.debug(f"CoinConfig creation error: {e}")
    finally:
        session.close()


def _assign_fallback_strategies():
    """
    For coins with no best_strategy_id, assign the highest composite_score variant.
    This fixes the bug where analyzer won't produce signals until optimizer runs (6h later).
    """
    session = get_session()
    try:
        configs = session.query(CoinConfig).filter(CoinConfig.best_strategy_id.is_(None)).all()
        assigned = 0
        for config in configs:
            best = (
                session.query(StrategyPerformance)
                .filter_by(symbol=config.symbol)
                .filter(StrategyPerformance.composite_score > 0)
                .order_by(StrategyPerformance.composite_score.desc())
                .first()
            )
            if best:
                config.best_strategy_id = best.strategy_variant_id
                config.updated_at = datetime.utcnow()
                assigned += 1
        if assigned > 0:
            session.commit()
            logger.info(f"Fallback: assigned best_strategy_id to {assigned} coins")
    except Exception as e:
        session.rollback()
        logger.debug(f"Fallback strategy assignment error: {e}")
    finally:
        session.close()


def run_analysis_cycle():
    """
    Main analysis loop (called by scheduler every 5 min):
    For each active symbol, generate a signal using all resources.
    Strategy variant is optional — if assigned, used for optimizer learning.
    """
    job_id = _start_agent_job("analyzer")
    signals_created = 0

    try:
        # Ensure all active coins have a CoinConfig
        _ensure_coin_configs()

        # Fallback: assign strategies to coins without one
        _assign_fallback_strategies()

        session = get_session()
        try:
            # LEFT OUTER JOIN: analyze ALL coins, even without a strategy
            configs = (
                session.query(CoinConfig, StrategyVariant)
                .outerjoin(StrategyVariant, CoinConfig.best_strategy_id == StrategyVariant.id)
                .filter(CoinConfig.auto_trade.is_(True))
                .all()
            )
        finally:
            session.close()

        if not configs:
            logger.info("No active coin configs found")
            _finish_agent_job(job_id, "SUCCESS", 0, context={"reason": "no_configs"})
            return

        for config, variant in configs:
            try:
                created = _analyze_single(config, variant)
                if created:
                    signals_created += 1
            except Exception as e:
                logger.error(f"Analysis error for {config.symbol}: {e}")

        _finish_agent_job(job_id, "SUCCESS", signals_created, context={
            "coins_analyzed": len(configs),
        })
    except Exception as e:
        logger.error(f"Analysis cycle error: {e}")
        _finish_agent_job(job_id, "FAILED", signals_created, error=str(e))


def _get_news_risk(symbol: str) -> float:
    """Get news risk score for a symbol (0-1). Returns 0 if news module unavailable."""
    try:
        from worker.news_collector import get_news_risk_score
        return get_news_risk_score(symbol)
    except (ImportError, Exception):
        return 0.0


def _analyze_single(config: CoinConfig, variant: StrategyVariant | None) -> bool:
    """Analyze a single symbol with multi-TF, all indicators, and full scoring. Returns True if signal created."""
    symbol = config.symbol

    # --- Coin blacklist check ---
    if _is_coin_blacklisted(symbol):
        logger.debug(f"Blacklist: {symbol} skipped")
        return False

    # --- Multi-timeframe data loading ---
    tf_weights = {"5m": 0.05, "15m": 0.10, "30m": 0.15, "1h": 0.25, "4h": 0.35}
    tf_results = {}

    for tf, weight in tf_weights.items():
        df = get_ohlcv_df(symbol, tf, limit=300)
        if df.empty or len(df) < 50:
            continue
        df = compute_all_indicators(df)
        all_scores = score_all_indicators(df)
        patterns = detect_all_patterns(df)
        pattern_score = score_patterns(patterns)
        tf_results[tf] = {
            "df": df,
            "all_scores": all_scores,
            "patterns": patterns,
            "pattern_score": pattern_score,
            "weight": weight,
        }

    if not tf_results:
        return False

    # Must have at least 4h data
    if "4h" not in tf_results:
        return False

    # --- Weighted multi-TF score ---
    weighted_ind = 0
    weighted_pat = 0
    total_weight = 0
    for tf, data in tf_results.items():
        w = data["weight"]
        weighted_ind += data["all_scores"]["total_normalized"] * w
        weighted_pat += data["pattern_score"] * w
        total_weight += w

    final_ind_score = weighted_ind / total_weight
    final_pat_score = weighted_pat / total_weight

    # --- Chart pattern & trend line bonuses (from 4h) ---
    primary = tf_results["4h"]
    levels = get_all_levels(primary["df"])

    chart_pattern_bonus = 0
    for cp in levels.get("chart_patterns", []):
        if cp["bias"] == "Bullish":
            chart_pattern_bonus += cp["strength"] * 0.4
        elif cp["bias"] == "Bearish":
            chart_pattern_bonus -= cp["strength"] * 0.4
    chart_pattern_bonus = max(-3, min(3, chart_pattern_bonus))

    trend_line_bonus = 0
    last_close = primary["df"]["close"].iloc[-1]
    for tl in levels.get("trend_lines", []):
        distance = abs(last_close - tl["current_value"]) / last_close
        if distance < 0.01:
            if tl["bias"] == "Bullish":
                trend_line_bonus += tl["touches"] * 0.3
            else:
                trend_line_bonus -= tl["touches"] * 0.3
    trend_line_bonus = max(-2, min(2, trend_line_bonus))

    # --- Total score (4 components like manual scan) ---
    total_score = round(final_ind_score + final_pat_score + chart_pattern_bonus + trend_line_bonus, 1)

    # Bias from full score (lower threshold for more learning signals)
    if total_score >= 1.5:
        bias = "LONG"
    elif total_score <= -1.5:
        bias = "SHORT"
    else:
        return False

    # Use 4h data for regime detection and downstream calculations
    df = primary["df"]
    patterns = primary["patterns"]

    # Detect current regime
    regime_details = get_regime_details(df)
    current_regime = regime_details["regime"]

    # Try regime-specific strategy first, fallback to general best
    best_variant = variant
    selected_variant_id = variant.id if variant else None

    session = get_session()
    try:
        regime_variant = _get_regime_best_strategy(session, symbol, current_regime)
        if regime_variant is not None:
            best_variant = regime_variant
            selected_variant_id = regime_variant.id
    finally:
        session.close()

    # Strategy-specific scores for optimizer learning (tracked separately)
    composition = best_variant.composition if best_variant else {}
    keys = []
    for cat in ["trend", "entry", "volume", "volatility"]:
        keys.extend(composition.get(cat, []))

    # Get strategy-specific indicator scores for the optimizer (with variant's custom weights)
    custom_w = best_variant.custom_weights if best_variant else None
    strategy_result = score_selected_indicators(df, keys, custom_weights=custom_w) if keys else None

    # TP/SL from levels
    atr = df["atr"].iloc[-1] if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else 0
    if atr <= 0:
        return False

    entry_price = df["close"].iloc[-1]

    from signal_generator import calculate_optimal_tp_sl
    tp_sl = calculate_optimal_tp_sl(
        entry=entry_price,
        atr=atr,
        bias=bias,
        all_levels=levels,
        fib_data=levels.get("fibonacci", {}),
    )

    if tp_sl["rr_ratio"] is None or tp_sl["rr_ratio"] < 1.5:
        return False

    # News risk check (Phase 4)
    news_risk = _get_news_risk(symbol)

    if news_risk > 0.9:
        logger.info(f"Skipping {symbol}: news risk too high ({news_risk:.2f})")
        return False

    # Confidence scoring (Phase 5)
    from signal_generator import calculate_confidence_score, estimate_time_to_target

    # Get backtest win rate for this strategy (prefer regime-specific WR)
    backtest_wr = 0.0
    if selected_variant_id:
        session = get_session()
        try:
            perf = (
                session.query(StrategyPerformance)
                .filter_by(strategy_variant_id=selected_variant_id, symbol=symbol)
                .first()
            )
            if perf:
                backtest_wr = perf.win_rate or 0.0
                # Regime-specific WR: use if higher than general WR
                if current_regime in ("TRENDING_UP", "TRENDING_DOWN"):
                    regime_wr = perf.regime_trending_score or 0.0
                elif current_regime in ("HIGH_VOLATILITY", "BREAKOUT"):
                    regime_wr = perf.regime_volatile_score or 0.0
                else:
                    regime_wr = perf.regime_ranging_score or 0.0
                backtest_wr = max(backtest_wr, regime_wr)
        finally:
            session.close()

    # Use full all_scores from 4h for confidence calculation
    all_indicator_scores = primary["all_scores"]["scores"]

    # Volume confirmation: check all volume-related indicators directly
    # Keys must match score_all_indicators() output in indicators.py
    vol_indicators = ["OBV", "CMF", "MFI", "Volume Spike", "Klinger", "Force Index", "PVO"]
    vol_scores_direct = [all_indicator_scores.get(k, 0) for k in vol_indicators
                         if all_indicator_scores.get(k, 0) != 0]
    if vol_scores_direct:
        if bias == "LONG":
            vol_confirmed = sum(1 for v in vol_scores_direct if v > 0) / len(vol_scores_direct)
        else:
            vol_confirmed = sum(1 for v in vol_scores_direct if v < 0) / len(vol_scores_direct)
    else:
        vol_confirmed = 0.5  # Neutral if no volume data

    conf_score, conf_breakdown = calculate_confidence_score(
        indicator_scores=all_indicator_scores,
        pattern_count=len(patterns),
        regime=current_regime,
        rr_ratio=tp_sl["rr_ratio"],
        news_risk=news_risk,
        backtest_win_rate=backtest_wr,
        volume_confirmation=vol_confirmed,
    )

    # If backtest data is missing, redistribute those points proportionally
    # Without backtest: regime_fit(20) + backtest_history(10) = 30 points unavailable
    # Scale the available 70 points to 100
    if backtest_wr == 0:
        available_max = 25 + 15 + 10 + 10 + 10  # confluence + rr + patterns + volume + news = 70
        if available_max > 0:
            conf_score = round(conf_score / available_max * 100, 1)
            # Cap at 74.9 so untested strategies can never reach YUKSEK (>=75)
            conf_score = min(conf_score, 74.9)

    # ETA estimation
    eta_low, eta_high = estimate_time_to_target(symbol, bias, entry_price, tp_sl["tp"])

    # Confidence label (ASCII for DB/filter compatibility)
    if conf_score >= 75:
        confidence = "YUKSEK"
    elif conf_score >= 50:
        confidence = "ORTA"
    else:
        confidence = "DUSUK"

    # Invalidation note
    invalidation = _generate_invalidation(bias, entry_price, tp_sl["sl"], atr)

    # Evaluate top 3 strategies for decision trace
    alternative_signals, rejection_reasons = _evaluate_alternatives(
        df, symbol, current_regime, selected_variant_id, entry_price, atr, levels, patterns
    )

    # Multi-TP calculation (Phase 2) — scaled by variant's tp_atr_mult
    from signal_generator import calculate_multi_tp
    variant_tp_mult = best_variant.tp_atr_mult if best_variant and best_variant.tp_atr_mult else 2.5
    multi_tp = calculate_multi_tp(entry_price, atr, bias, tp_atr_mult=variant_tp_mult)

    # --- Smart Dedup: position-aware signal deduplication ---
    session = get_session()
    try:
        # 1) If there's an OPEN paper trade for this symbol with same bias, skip entirely
        open_trade = (
            session.query(PaperTrade)
            .filter(
                PaperTrade.symbol == symbol,
                PaperTrade.bias == bias,
                PaperTrade.status == "OPEN",
            )
            .first()
        )
        if open_trade:
            logger.debug(f"Dedup: {symbol} {bias} skipped — open trade #{open_trade.id} exists")
            return False

        # 2) Check most recent signal for this symbol (any bias)
        last_signal = (
            session.query(Signal)
            .filter(Signal.symbol == symbol)
            .order_by(Signal.created_at.desc())
            .first()
        )
        if last_signal:
            # Same bias — only allow if entry price moved >3% from last signal
            if last_signal.bias == bias:
                if not last_signal.entry_price or last_signal.entry_price <= 0:
                    logger.info(f"Dedup: {symbol} {bias} — last signal has invalid entry_price, allowing new signal")
                else:
                    price_change = abs(entry_price - last_signal.entry_price) / last_signal.entry_price
                    if price_change < 0.015:
                        logger.debug(
                            f"Dedup: {symbol} {bias} skipped — same bias, price change only {price_change:.1%} "
                            f"(need >1.5%)"
                        )
                        return False
                    logger.info(
                        f"Dedup: {symbol} {bias} NEW signal — price moved {price_change:.1%} from last"
                    )
            else:
                # Bias flipped (LONG→SHORT or SHORT→LONG) — always allow
                logger.info(
                    f"Dedup: {symbol} bias flipped {last_signal.bias}→{bias}, generating new signal"
                )
    finally:
        session.close()

    # Save signal to DB (convert all numpy types to native Python for PostgreSQL)
    raw_scores = strategy_result["scores"] if strategy_result else all_indicator_scores
    clean_scores = _sanitize_scores(raw_scores)
    clean_breakdown = {
        "indicators": round(float(final_ind_score), 2),
        "patterns": round(float(final_pat_score), 2),
        "chart_patterns": round(float(chart_pattern_bonus), 2),
        "trend_lines": round(float(trend_line_bonus), 2),
    }
    clean_conf_breakdown = {k: float(v) for k, v in conf_breakdown.items()} if conf_breakdown else {}

    session = get_session()
    try:
        signal = Signal(
            symbol=symbol,
            bias=bias,
            entry_price=_to_float(entry_price),
            tp_price=_to_float(tp_sl["tp"]),
            sl_price=_to_float(tp_sl["sl"]),
            rr_ratio=_to_float(tp_sl["rr_ratio"]),
            confidence=confidence,
            score=round(float(total_score), 1),
            strategy_variant_id=selected_variant_id,
            score_breakdown=clean_breakdown,
            indicator_scores=clean_scores,
            detected_patterns=[
                {"pattern": p["pattern"], "bias": p["bias"], "strength": int(p["strength"])}
                for p in patterns[:20]
            ],
            regime=current_regime,
            alternative_signals=alternative_signals or None,
            rejection_reasons=rejection_reasons or None,
            confidence_score=_to_float(conf_score),
            confidence_breakdown=clean_conf_breakdown,
            eta_hours_low=_to_float(eta_low),
            eta_hours_high=_to_float(eta_high),
            news_risk_score=_to_float(news_risk),
            invalidation_note=invalidation,
            reasoning=_generate_decision_trace(
                symbol, bias, conf_score, total_score, entry_price,
                tp_sl, multi_tp, composition, all_indicator_scores, patterns,
                current_regime, news_risk, eta_low, eta_high,
                invalidation, alternative_signals, rejection_reasons,
                config.leverage or 5.0,
            ),
            created_at=datetime.utcnow(),
        )
        session.add(signal)
        session.commit()
        signal_id = signal.id
        logger.info(f"Signal #{signal_id}: {symbol} {bias} score={total_score:+.1f} conf={conf_score:.0f}/100 regime={current_regime}")
    except Exception as e:
        session.rollback()
        logger.error(f"Signal save error: {e}")
        return False
    finally:
        session.close()

    # Auto paper trade if configured (learning mode: DUSUK also trades)
    if config.auto_trade and confidence in ("YUKSEK", "ORTA", "DUSUK"):
        # Reduce position size if news risk is high
        position_size_override = None
        if news_risk > 0.7:
            position_size_override = (config.max_position_size or 200.0) * 0.5
            logger.info(f"News risk {news_risk:.2f}: halving position size for {symbol}")

        # DUSUK confidence: 50% smaller position for learning with less risk
        if confidence == "DUSUK" and position_size_override is None:
            position_size_override = (config.max_position_size or 200.0) * 0.5

        open_paper_trade(
            signal_id=signal_id,
            symbol=symbol,
            bias=bias,
            entry_price=entry_price,
            tp_price=multi_tp.get("tp1", tp_sl["tp"]),
            sl_price=tp_sl["sl"],
            reasoning=signal.reasoning,
            regime_at_entry=current_regime,
            position_size_usd=position_size_override,
            tp2_price=multi_tp.get("tp2"),
            tp3_price=multi_tp.get("tp3"),
        )

    return True


def _generate_invalidation(bias: str, entry: float, sl: float, atr: float) -> str:
    """Generate invalidation note for a signal."""
    clean_entry = f"${entry:,.2f}"
    if bias == "LONG":
        inv_price = sl - 0.1 * atr
        return f"Fiyat ${inv_price:,.2f} altina duserse sinyal iptal (SL altinda)"
    else:
        inv_price = sl + 0.1 * atr
        return f"Fiyat ${inv_price:,.2f} ustune cikarsa sinyal iptal (SL ustunde)"


def _generate_decision_trace(
    symbol, bias, conf_score, total_score, entry_price,
    tp_sl, multi_tp, composition, scores, patterns,
    regime, news_risk, eta_low, eta_high,
    invalidation, alternatives, rejections, leverage,
) -> str:
    """Generate the Phase 5 zorunlu decision trace format."""
    clean_sym = symbol.replace("/USDT:USDT", "")

    # Gather indicator names per category
    trend_keys = composition.get("trend", [])
    entry_keys = composition.get("entry", [])
    confirm_keys = composition.get("volume", []) + composition.get("volatility", [])

    trend_vals = {k: scores.get(k, 0) for k in trend_keys}
    entry_vals = {k: scores.get(k, 0) for k in entry_keys}
    confirm_vals = {k: scores.get(k, 0) for k in confirm_keys}

    trend_direction = "yukari" if sum(trend_vals.values()) > 0 else "asagi"
    trend_str = ", ".join(f"{k}={v:+.2f}" for k, v in trend_vals.items())

    entry_trigger = max(entry_vals, key=lambda k: abs(entry_vals[k])) if entry_vals else "-"
    entry_reason = f"{entry_trigger}={entry_vals.get(entry_trigger, 0):+.2f}" if entry_vals else "-"

    confirm_str = ", ".join(f"{k}={v:+.2f}" for k, v in confirm_vals.items())
    confirmed = all(
        (v > 0 if bias == "LONG" else v < 0)
        for v in confirm_vals.values()
    ) if confirm_vals else False

    tp1 = multi_tp.get("tp1", tp_sl["tp"])
    tp2 = multi_tp.get("tp2", tp_sl["tp"])
    tp3 = multi_tp.get("tp3", tp_sl["tp"])

    # News risk level
    if news_risk > 0.7:
        news_level = "YUKSEK"
    elif news_risk > 0.3:
        news_level = "ORTA"
    else:
        news_level = "DUSUK"

    lines = [
        f"{clean_sym} {bias} Sinyali (Guven: {conf_score:.0f}/100)",
        "",
        f"  Bias (Trend): {trend_str} -> {trend_direction}",
        f"  Tetikleyici: {entry_reason}",
        f"  Onay: {confirm_str} -> {'onaylandi' if confirmed else 'zayif'}",
        f"  Risk Plani: SL ${tp_sl['sl']:,.2f} | TP1 ${tp1:,.2f} | TP2 ${tp2:,.2f} | TP3 ${tp3:,.2f} | R:R {tp_sl['rr_ratio']:.2f}",
        f"  Kaldirac: {leverage:.0f}x",
        f"  Tahmini Sure: {eta_low:.0f}-{eta_high:.0f} saat",
    ]

    # Patterns
    bullish = [p["pattern"] for p in patterns[:10] if p.get("bias") == "Bullish"]
    bearish = [p["pattern"] for p in patterns[:10] if p.get("bias") == "Bearish"]
    if bullish:
        lines.append(f"  Bullish Formasyonlar: {', '.join(bullish[:3])}")
    if bearish:
        lines.append(f"  Bearish Formasyonlar: {', '.join(bearish[:3])}")

    # Alternatives
    if alternatives:
        for alt in alternatives[:2]:
            lines.append(f"  Alternatif: {alt['strategy']} (skor: {alt['score']:+.2f}) -> {alt['bias']}")

    # Rejections
    if rejections:
        for rej in rejections[:2]:
            lines.append(f"  Elenen: {rej['strategy']} -> {rej['reason']}")

    lines.append(f"  Iptal Kosulu: {invalidation}")
    lines.append(f"  News Risk: {news_level} ({news_risk:.2f})")

    return "\n".join(lines)


def _get_regime_best_strategy(session, symbol: str, regime: str) -> StrategyVariant | None:
    """Get the best strategy for a specific regime via CoinConfig lookup (no query needed)."""
    config = session.query(CoinConfig).filter_by(symbol=symbol).first()
    if not config:
        return None

    if regime in ("TRENDING_UP", "TRENDING_DOWN"):
        sid = getattr(config, 'best_trending_strategy_id', None)
    elif regime in ("HIGH_VOLATILITY", "BREAKOUT"):
        sid = getattr(config, 'best_volatile_strategy_id', None)
    else:
        sid = getattr(config, 'best_ranging_strategy_id', None)

    if not sid:
        return None

    return session.query(StrategyVariant).get(sid)


def _evaluate_alternatives(
    df, symbol, current_regime, selected_variant_id, entry_price, atr, levels, patterns
) -> tuple[list, list]:
    """Evaluate top 3 alternative strategies for decision trace."""
    alternative_signals = []
    rejection_reasons = []

    session = get_session()
    try:
        query = (
            session.query(StrategyPerformance, StrategyVariant)
            .join(StrategyVariant, StrategyPerformance.strategy_variant_id == StrategyVariant.id)
            .filter(
                StrategyPerformance.symbol == symbol,
                StrategyPerformance.composite_score > 0,
            )
        )
        if selected_variant_id is not None:
            query = query.filter(StrategyVariant.id != selected_variant_id)
        top_perfs = (
            query.order_by(StrategyPerformance.composite_score.desc())
            .limit(3)
            .all()
        )

        for perf, alt_variant in top_perfs:
            try:
                comp = alt_variant.composition
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
                        "reason": "Notr sinyal (yetersiz skor)",
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
    Phase 1: Agent health logging.
    """
    job_id = _start_agent_job("trade_checker")

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
                "partial_tp_taken": t.partial_tp_taken,
                "partial_tp_price": t.partial_tp_price,
                "tp2_price": t.tp2_price,
                "tp3_price": t.tp3_price,
                "leverage": t.leverage,
                "position_size_usd": t.position_size_usd,
            })
    finally:
        session.close()

    if not trade_data:
        _finish_agent_job(job_id, "SUCCESS", 0, context={"open_trades": 0})
        return

    checked = 0
    try:
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
                        checked += 1
                        continue

                # Phase 2: Partial TP logic
                if not trade["partial_tp_taken"] and trade["partial_tp_price"]:
                    hit = False
                    if trade["bias"] == "LONG" and current_price >= trade["partial_tp_price"]:
                        hit = True
                    elif trade["bias"] == "SHORT" and current_price <= trade["partial_tp_price"]:
                        hit = True

                    if hit:
                        _handle_partial_tp(trade, current_price)
                        checked += 1
                        continue

                # Phase 2: TP2 check (for trades that already took partial)
                if trade["partial_tp_taken"] and trade["tp2_price"]:
                    tp2_hit = False
                    if trade["bias"] == "LONG" and current_price >= trade["tp2_price"]:
                        tp2_hit = True
                    elif trade["bias"] == "SHORT" and current_price <= trade["tp2_price"]:
                        tp2_hit = True

                    if tp2_hit:
                        # TP2 is the main TP — close remaining
                        close_paper_trade(trade["id"], current_price, "TP_HIT")
                        _log_trade_management(trade["id"], "TP2_HIT", trade["tp_price"], current_price,
                                              "TP2 hedefine ulasildi", current_price, 0)
                        checked += 1
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
                        checked += 1
                        continue
                    if trailing_sl and current_price <= trailing_sl:
                        status = "TRAILING_STOP" if trailing_sl > (trade["sl_price"] or 0) else "SL_HIT"
                        close_paper_trade(trade["id"], current_price, status)
                        checked += 1
                        continue
                    if trade["liquidation_price"] and current_price <= trade["liquidation_price"]:
                        close_paper_trade(trade["id"], current_price, "LIQUIDATED")
                        checked += 1
                        continue
                else:  # SHORT
                    if trade["tp_price"] and current_price <= trade["tp_price"]:
                        close_paper_trade(trade["id"], current_price, "TP_HIT")
                        checked += 1
                        continue
                    if trailing_sl and current_price >= trailing_sl:
                        status = "TRAILING_STOP" if trailing_sl < (trade["sl_price"] or float('inf')) else "SL_HIT"
                        close_paper_trade(trade["id"], current_price, status)
                        checked += 1
                        continue
                    if trade["liquidation_price"] and current_price >= trade["liquidation_price"]:
                        close_paper_trade(trade["id"], current_price, "LIQUIDATED")
                        checked += 1
                        continue

            except Exception as e:
                logger.error(f"Trade check error for #{trade['id']}: {e}")

        _finish_agent_job(job_id, "SUCCESS", checked, context={"open_trades": len(trade_data)})
    except Exception as e:
        _finish_agent_job(job_id, "FAILED", checked, error=str(e))


def _handle_partial_tp(trade: dict, current_price: float):
    """Handle partial TP: close 50% of position, move SL to breakeven."""
    from paper_trader.position import calculate_pnl

    session = get_session()
    try:
        t = session.query(PaperTrade).get(trade["id"])
        if t is None or t.status != "OPEN":
            return

        # Calculate P&L for the partial close (50% of position)
        pnl = calculate_pnl(
            t.entry_price, current_price, t.bias,
            t.leverage, t.position_size_usd * 0.5,
            include_fees=True,
        )

        t.partial_tp_taken = True
        t.partial_tp_pnl = pnl["pnl_usd"]
        # Move SL to breakeven
        old_sl = t.sl_price
        t.sl_price = t.entry_price
        t.trailing_stop_price = t.entry_price
        # Reduce position size by 50%
        t.position_size_usd = t.position_size_usd * 0.5

        session.commit()

        _log_trade_management(
            trade["id"], "PARTIAL_TP", old_sl, t.entry_price,
            f"TP1'e ulasildi, %50 kapandi (PnL: ${pnl['pnl_usd']:+.2f}), SL breakeven'a tasildi",
            current_price, pnl["pnl_percent"],
        )
        _log_trade_management(
            trade["id"], "BE_MOVED", old_sl, t.entry_price,
            "SL breakeven'a tasindi (partial TP sonrasi)",
            current_price, pnl["pnl_percent"],
        )

        logger.info(f"Partial TP: trade #{trade['id']} +${pnl['pnl_usd']:+.2f}, SL->BE")
    except Exception as e:
        session.rollback()
        logger.error(f"Partial TP error for #{trade['id']}: {e}")
    finally:
        session.close()


def _log_trade_management(trade_id, event_type, old_value, new_value, reason, current_price, pnl_pct):
    """Log a trade management event."""
    from db.models import TradeManagementLog
    session = get_session()
    try:
        session.add(TradeManagementLog(
            paper_trade_id=trade_id,
            timestamp=datetime.utcnow(),
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            reason=reason,
            current_price=current_price,
            current_pnl_pct=pnl_pct,
        ))
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _update_trailing_stop(
    trade_id: int,
    bias: str,
    entry_price: float,
    current_price: float,
    current_trailing: float,
    atr: float,
) -> float:
    """
    Phase 2 improved trailing stop:
    1.0xATR profit -> SL = entry (breakeven)
    1.5xATR profit -> SL = entry + 0.5xATR (profit lock)
    2.0xATR profit -> trail 1xATR behind price
    """
    old_trailing = current_trailing
    if bias == "LONG":
        profit = current_price - entry_price
        if profit >= 2 * atr:
            new_trail = current_price - atr
            if new_trail > current_trailing:
                current_trailing = new_trail
        elif profit >= 1.5 * atr:
            target = entry_price + 0.5 * atr
            if target > current_trailing:
                current_trailing = target
        elif profit >= 1.0 * atr:
            if entry_price > current_trailing:
                current_trailing = entry_price
    else:  # SHORT
        profit = entry_price - current_price
        if profit >= 2 * atr:
            new_trail = current_price + atr
            if new_trail < current_trailing:
                current_trailing = new_trail
        elif profit >= 1.5 * atr:
            target = entry_price - 0.5 * atr
            if target < current_trailing:
                current_trailing = target
        elif profit >= 1.0 * atr:
            if entry_price < current_trailing:
                current_trailing = entry_price

    # Persist updated trailing stop
    if current_trailing != old_trailing:
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

        # Log the trailing update
        _log_trade_management(
            trade_id, "TRAIL_UPDATED", old_trailing, current_trailing,
            f"Trailing stop guncellendi (profit={profit/atr:.1f}xATR)",
            current_price, 0,
        )

    return current_trailing
