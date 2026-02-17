"""
Phalidae v2 - Strategy Optimization Engine
Backtests all variants, scores them, ranks per symbol, manages genetic evolution.
Phase 1: Agent health logging + quick optimization.
Phase 3: Longer backtest with deep data.
"""

import logging
from datetime import datetime

from sqlalchemy import func

import numpy as np
import pandas as pd

from db.engine import get_session
from db.models import (
    StrategyVariant, StrategyPerformance, TrackedSymbol, CoinConfig, OHLCVData,
    CorrelationCache,
)
from indicators import compute_all_indicators
from strategy.backtester import backtest_variant
from strategy.variants import generate_random_variants, generate_genetic_variants
from worker.collector import get_ohlcv_df, _start_agent_job, _finish_agent_job

logger = logging.getLogger("phalidae.optimizer")

# Composite score weights
W_WIN_RATE = 0.30
W_PROFIT_FACTOR = 0.25
W_SHARPE = 0.20
W_DRAWDOWN = 0.15
W_TRADE_COUNT = 0.10
MIN_TRADES = 20  # Minimum trades for valid scoring


def compute_composite_score(metrics: dict) -> float:
    """
    Compute composite score from backtest metrics.
    composite = 0.30*win_rate + 0.25*profit_factor + 0.20*sharpe
              + 0.15*(1-max_drawdown) + 0.10*trade_count_bonus
    """
    if metrics["total_trades"] < MIN_TRADES:
        return 0.0

    # Normalize components to 0-1 range
    wr = metrics["win_rate"]  # Already 0-1
    pf = min(metrics["profit_factor"] / 3.0, 1.0)  # Cap at PF=3
    sharpe = min(max(metrics["sharpe_ratio"] / 3.0, 0), 1.0)  # Cap at 3
    dd = max(1.0 - (metrics["max_drawdown"] / 100.0), 0)  # Invert, normalize
    tc = min(metrics["total_trades"] / 100.0, 1.0)  # Cap at 100 trades

    score = (
        W_WIN_RATE * wr +
        W_PROFIT_FACTOR * pf +
        W_SHARPE * sharpe +
        W_DRAWDOWN * dd +
        W_TRADE_COUNT * tc
    )

    return round(score, 4)


def _optimize_symbol(symbol: str, variants: list[StrategyVariant], max_bars: int = 1000) -> int:
    """Run backtest for all variants on a single symbol. Returns number of results saved."""
    # Phase 3: Use more bars if available
    df = get_ohlcv_df(symbol, "4h", limit=max_bars)
    if df.empty or len(df) < 250:
        logger.info(f"Skipping {symbol}: insufficient data ({len(df)} bars)")
        return 0

    # Compute indicators once
    try:
        df = compute_all_indicators(df)
    except Exception as e:
        logger.error(f"Indicator computation failed for {symbol}: {e}")
        return 0

    session = get_session()
    saved = 0

    try:
        for variant in variants:
            composition = variant.composition
            if not isinstance(composition, dict):
                continue

            metrics = backtest_variant(
                df,
                composition=composition,
                trend_threshold=variant.trend_threshold,
                entry_threshold=variant.entry_threshold,
                volume_required=variant.volume_required,
            )

            if metrics["total_trades"] == 0:
                continue

            composite = compute_composite_score(metrics)

            # Upsert performance record
            perf = (
                session.query(StrategyPerformance)
                .filter_by(strategy_variant_id=variant.id, symbol=symbol)
                .first()
            )

            if perf is None:
                perf = StrategyPerformance(
                    strategy_variant_id=variant.id,
                    symbol=symbol,
                )
                session.add(perf)

            perf.total_trades = metrics["total_trades"]
            perf.winning_trades = metrics["winning_trades"]
            perf.losing_trades = metrics["losing_trades"]
            perf.win_rate = metrics["win_rate"]
            perf.profit_factor = metrics["profit_factor"]
            perf.sharpe_ratio = metrics["sharpe_ratio"]
            perf.max_drawdown = metrics["max_drawdown"]
            perf.total_pnl_pct = metrics["total_pnl_pct"]
            perf.regime_trending_score = metrics.get("regime_trending_score", 0.0)
            perf.regime_ranging_score = metrics.get("regime_ranging_score", 0.0)
            perf.regime_volatile_score = metrics.get("regime_volatile_score", 0.0)
            perf.composite_score = composite
            perf.updated_at = datetime.utcnow()
            saved += 1

        session.commit()

        # Update ranks for this symbol
        _update_ranks(session, symbol)
        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"Optimization error for {symbol}: {e}")
    finally:
        session.close()

    return saved


def _update_ranks(session, symbol: str):
    """Update rank ordering for a symbol (1 = best)."""
    perfs = (
        session.query(StrategyPerformance)
        .filter_by(symbol=symbol)
        .filter(StrategyPerformance.composite_score > 0)
        .order_by(StrategyPerformance.composite_score.desc())
        .all()
    )
    for i, perf in enumerate(perfs, 1):
        perf.rank = i


def _update_best_strategies():
    """Update coin_config with the best strategy for each symbol."""
    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        for ts in symbols:
            best = (
                session.query(StrategyPerformance)
                .filter_by(symbol=ts.symbol, rank=1)
                .filter(StrategyPerformance.composite_score > 0)
                .first()
            )
            if best is None:
                continue

            config = session.query(CoinConfig).filter_by(symbol=ts.symbol).first()
            if config is None:
                config = CoinConfig(symbol=ts.symbol, auto_trade=True)
                session.add(config)

            config.best_strategy_id = best.strategy_variant_id
            config.updated_at = datetime.utcnow()

        session.commit()
        logger.info("Updated best strategies for all coins")
    except Exception as e:
        session.rollback()
        logger.error(f"Best strategy update error: {e}")
    finally:
        session.close()


def run_optimization():
    """
    Main optimization loop (called by scheduler every 6 hours):
    1. Generate some random exploration variants
    2. Try genetic crossover if enough data
    3. Backtest all variants on all active symbols
    4. Update rankings and best strategies
    """
    job_id = _start_agent_job("optimizer")
    total_saved = 0

    try:
        logger.info("Starting optimization cycle...")

        # 1. Generate new exploration variants
        generate_random_variants(count=10)

        # 2. Genetic crossover
        generate_genetic_variants(top_n=10, children=10)

        # 3. Get all variants and active symbols
        session = get_session()
        try:
            variants = session.query(StrategyVariant).all()
            symbols = (
                session.query(TrackedSymbol)
                .filter_by(is_active=True)
                .order_by(TrackedSymbol.rank)
                .limit(30)
                .all()
            )
            variant_list = list(variants)
            symbol_list = [s.symbol for s in symbols]
        finally:
            session.close()

        if not variants or not symbol_list:
            logger.warning("No variants or symbols for optimization")
            _finish_agent_job(job_id, "SUCCESS", 0, context={"reason": "no_data"})
            return

        logger.info(f"Optimizing {len(variant_list)} variants across {len(symbol_list)} symbols")

        # Phase 3: Use 3000 bars if sufficient data, else 1000
        session = get_session()
        try:
            sample_count = session.query(func.count(OHLCVData.id)).filter_by(
                symbol=symbol_list[0], timeframe="4h"
            ).scalar() or 0
        finally:
            session.close()

        max_bars = 3000 if sample_count >= 3000 else 1000

        # 4. Backtest each symbol
        for i, sym in enumerate(symbol_list):
            saved = _optimize_symbol(sym, variant_list, max_bars=max_bars)
            total_saved += saved
            if (i + 1) % 5 == 0:
                logger.info(f"Progress: {i+1}/{len(symbol_list)} symbols")

        # 5. Update best strategies
        _update_best_strategies()

        # 6. Compute correlations between symbols
        _compute_correlations(symbol_list)

        logger.info(f"Optimization complete: {total_saved} results saved")
        _finish_agent_job(job_id, "SUCCESS", total_saved, context={
            "symbols": len(symbol_list), "variants": len(variant_list), "max_bars": max_bars,
        })
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        _finish_agent_job(job_id, "FAILED", total_saved, error=str(e))


def run_quick_optimization(top_symbols: int = 10, top_variants: int = 50):
    """
    Phase 1: Quick optimization for initial startup.
    Runs on top N symbols with first M variants, using 500 bars.
    Takes ~2-3 minutes vs full optimization's ~60 minutes.
    """
    job_id = _start_agent_job("quick_optimizer")
    total_saved = 0

    try:
        logger.info(f"Quick optimization: top {top_symbols} symbols, {top_variants} variants")

        session = get_session()
        try:
            variants = (
                session.query(StrategyVariant)
                .limit(top_variants)
                .all()
            )
            symbols = (
                session.query(TrackedSymbol)
                .filter_by(is_active=True)
                .order_by(TrackedSymbol.rank)
                .limit(top_symbols)
                .all()
            )
            variant_list = list(variants)
            symbol_list = [s.symbol for s in symbols]
        finally:
            session.close()

        if not variant_list or not symbol_list:
            logger.warning("Quick optimization: no variants or symbols")
            _finish_agent_job(job_id, "SUCCESS", 0, context={"reason": "no_data"})
            return

        for sym in symbol_list:
            saved = _optimize_symbol(sym, variant_list, max_bars=500)
            total_saved += saved

        # Update best strategies
        _update_best_strategies()

        logger.info(f"Quick optimization completed: {total_saved} results for {len(symbol_list)} symbols")
        _finish_agent_job(job_id, "SUCCESS", total_saved, context={
            "symbols": len(symbol_list), "variants": len(variant_list),
        })
    except Exception as e:
        logger.error(f"Quick optimization error: {e}")
        _finish_agent_job(job_id, "FAILED", total_saved, error=str(e))


def _compute_correlations(symbol_list: list[str]):
    """Compute pairwise correlation of 4h close returns between active symbols."""
    if len(symbol_list) < 2:
        return

    # Load 4h close series for each symbol
    returns_dict = {}
    for sym in symbol_list:
        df = get_ohlcv_df(sym, "4h", limit=200)
        if df.empty or len(df) < 50:
            continue
        ret = df["close"].pct_change().dropna()
        returns_dict[sym] = ret

    if len(returns_dict) < 2:
        return

    # Build aligned DataFrame
    all_returns = pd.DataFrame(returns_dict)
    corr_matrix = all_returns.corr()

    session = get_session()
    try:
        syms = list(returns_dict.keys())
        now = datetime.utcnow()

        for i in range(len(syms)):
            for j in range(i + 1, len(syms)):
                sym_a, sym_b = syms[i], syms[j]
                corr_val = corr_matrix.loc[sym_a, sym_b]
                if pd.isna(corr_val):
                    continue

                existing = (
                    session.query(CorrelationCache)
                    .filter_by(symbol_a=sym_a, symbol_b=sym_b)
                    .first()
                )
                if existing:
                    existing.correlation = round(float(corr_val), 4)
                    existing.computed_at = now
                else:
                    session.add(CorrelationCache(
                        symbol_a=sym_a,
                        symbol_b=sym_b,
                        correlation=round(float(corr_val), 4),
                        computed_at=now,
                    ))

        session.commit()
        logger.info(f"Updated correlations for {len(syms)} symbols")
    except Exception as e:
        session.rollback()
        logger.error(f"Correlation computation error: {e}")
    finally:
        session.close()


def get_top_strategies(symbol: str, limit: int = 10) -> list[dict]:
    """Get top-ranked strategies for a symbol."""
    session = get_session()
    try:
        results = (
            session.query(StrategyPerformance, StrategyVariant)
            .join(StrategyVariant, StrategyPerformance.strategy_variant_id == StrategyVariant.id)
            .filter(StrategyPerformance.symbol == symbol)
            .filter(StrategyPerformance.composite_score > 0)
            .order_by(StrategyPerformance.rank)
            .limit(limit)
            .all()
        )

        strategies = []
        for perf, variant in results:
            strategies.append({
                "variant_id": variant.id,
                "name": variant.name,
                "composition": variant.composition,
                "rank": perf.rank,
                "composite_score": perf.composite_score,
                "win_rate": perf.win_rate,
                "profit_factor": perf.profit_factor,
                "sharpe_ratio": perf.sharpe_ratio,
                "max_drawdown": perf.max_drawdown,
                "total_pnl_pct": perf.total_pnl_pct,
                "total_trades": perf.total_trades,
                "paper_win_rate": perf.paper_win_rate,
                "paper_pnl_pct": perf.paper_pnl_pct,
                "regime_trending_score": perf.regime_trending_score,
                "regime_ranging_score": perf.regime_ranging_score,
                "regime_volatile_score": perf.regime_volatile_score,
            })
        return strategies
    finally:
        session.close()
