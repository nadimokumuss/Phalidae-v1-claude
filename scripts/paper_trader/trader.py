"""
Phalidae v2 - Paper Trade Manager
Opens and closes simulated trades based on signals.
Includes: daily drawdown limit, correlation check, coin-based leverage/position sizing.
"""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from db.engine import get_session
from db.models import PaperTrade, Signal, TradeSnapshot, StrategyPerformance, CoinConfig, CorrelationCache
from paper_trader.position import calculate_pnl

logger = logging.getLogger("phalidae.trader")

DEFAULT_LEVERAGE = 5.0
DEFAULT_POSITION_SIZE = 1000.0
MAX_OPEN_TRADES_PER_SYMBOL = 1
MAX_TOTAL_OPEN_TRADES = 20
MAX_CORRELATION = 0.7  # Max allowed correlation with existing open trades


def _check_daily_drawdown(session, symbol: str) -> bool:
    """
    Check if daily drawdown limit is exceeded for a symbol.
    Returns True if it's OK to trade, False if limit exceeded.
    """
    config = session.query(CoinConfig).filter_by(symbol=symbol).first()
    limit_pct = config.daily_drawdown_limit if config and config.daily_drawdown_limit else 10.0

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    daily_pnl = (
        session.query(func.sum(PaperTrade.pnl_percent))
        .filter(
            PaperTrade.symbol == symbol,
            PaperTrade.status != "OPEN",
            PaperTrade.closed_at >= today_start,
        )
        .scalar()
    ) or 0.0

    if daily_pnl < -limit_pct:
        logger.info(f"Daily drawdown limit hit for {symbol}: {daily_pnl:.1f}% (limit: -{limit_pct}%)")
        return False
    return True


def _check_correlation(session, symbol: str) -> bool:
    """
    Check if new trade would be too correlated with existing open trades.
    Returns True if it's OK to trade, False if too correlated.
    """
    open_symbols = (
        session.query(PaperTrade.symbol)
        .filter_by(status="OPEN")
        .distinct()
        .all()
    )
    open_symbols = [s[0] for s in open_symbols if s[0] != symbol]

    if not open_symbols:
        return True

    for open_sym in open_symbols:
        # Check both orderings
        corr = (
            session.query(CorrelationCache.correlation)
            .filter(
                ((CorrelationCache.symbol_a == symbol) & (CorrelationCache.symbol_b == open_sym)) |
                ((CorrelationCache.symbol_a == open_sym) & (CorrelationCache.symbol_b == symbol))
            )
            .first()
        )
        if corr and corr[0] is not None and abs(corr[0]) > MAX_CORRELATION:
            logger.info(f"Correlation too high between {symbol} and {open_sym}: {corr[0]:.2f}")
            return False

    return True


def open_paper_trade(
    signal_id: int | None,
    symbol: str,
    bias: str,
    entry_price: float,
    tp_price: float,
    sl_price: float,
    reasoning: str = "",
    leverage: float | None = None,
    position_size_usd: float | None = None,
    regime_at_entry: str | None = None,
) -> int | None:
    """
    Open a new paper trade. Returns trade ID or None if rejected.
    Uses coin-specific leverage and position size from CoinConfig.
    """
    session = get_session()
    try:
        # Load coin config for per-coin settings
        config = session.query(CoinConfig).filter_by(symbol=symbol).first()
        if leverage is None:
            leverage = config.leverage if config and config.leverage else DEFAULT_LEVERAGE
        if position_size_usd is None:
            position_size_usd = config.max_position_size if config and config.max_position_size else DEFAULT_POSITION_SIZE

        # Check limits
        open_for_symbol = (
            session.query(PaperTrade)
            .filter_by(symbol=symbol, status="OPEN")
            .count()
        )
        if open_for_symbol >= MAX_OPEN_TRADES_PER_SYMBOL:
            logger.info(f"Skip: already {open_for_symbol} open trades for {symbol}")
            return None

        total_open = session.query(PaperTrade).filter_by(status="OPEN").count()
        if total_open >= MAX_TOTAL_OPEN_TRADES:
            logger.info(f"Skip: max open trades reached ({total_open})")
            return None

        # Daily drawdown check
        if not _check_daily_drawdown(session, symbol):
            return None

        # Correlation check
        if not _check_correlation(session, symbol):
            return None

        # Calculate liquidation price
        pnl_info = calculate_pnl(entry_price, entry_price, bias, leverage, position_size_usd)

        trade = PaperTrade(
            signal_id=signal_id,
            symbol=symbol,
            bias=bias,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage,
            liquidation_price=pnl_info["liquidation_price"],
            position_size_usd=position_size_usd,
            status="OPEN",
            reasoning=reasoning,
            regime_at_entry=regime_at_entry,
            trailing_stop_price=sl_price,  # Initialize trailing stop at SL
            opened_at=datetime.utcnow(),
        )
        session.add(trade)
        session.commit()

        trade_id = trade.id
        logger.info(f"Opened paper trade #{trade_id}: {symbol} {bias} @ {entry_price} ({leverage}x)")
        return trade_id

    except Exception as e:
        session.rollback()
        logger.error(f"Open trade error: {e}")
        return None
    finally:
        session.close()


def close_paper_trade(
    trade_id: int,
    exit_price: float,
    status: str,
):
    """
    Close a paper trade with given exit price and status.
    Updates P&L and optionally updates strategy performance paper stats.
    """
    session = get_session()
    try:
        trade = session.query(PaperTrade).get(trade_id)
        if trade is None or trade.status != "OPEN":
            return

        pnl = calculate_pnl(
            trade.entry_price, exit_price, trade.bias,
            trade.leverage, trade.position_size_usd,
            include_fees=True,
        )

        trade.exit_price = exit_price
        trade.status = status
        trade.exit_reason = status
        trade.pnl_usd = pnl["pnl_usd"]
        trade.pnl_percent = pnl["pnl_percent"]
        trade.closed_at = datetime.utcnow()

        session.commit()

        # Update strategy performance paper stats
        _update_paper_stats(session, trade)

        logger.info(
            f"Closed trade #{trade_id}: {status} P&L={pnl['pnl_percent']:+.2f}%"
        )

    except Exception as e:
        session.rollback()
        logger.error(f"Close trade error: {e}")
    finally:
        session.close()


def _update_paper_stats(session, trade: PaperTrade):
    """Update strategy_performance paper trade columns after a trade closes."""
    if trade.signal_id is None:
        return

    signal = session.query(Signal).get(trade.signal_id)
    if signal is None or signal.strategy_variant_id is None:
        return

    perf = (
        session.query(StrategyPerformance)
        .filter_by(strategy_variant_id=signal.strategy_variant_id, symbol=trade.symbol)
        .first()
    )
    if perf is None:
        return

    # Recalculate paper stats from all closed trades for this strategy/symbol
    closed_trades = (
        session.query(PaperTrade)
        .join(Signal, PaperTrade.signal_id == Signal.id)
        .filter(
            Signal.strategy_variant_id == signal.strategy_variant_id,
            PaperTrade.symbol == trade.symbol,
            PaperTrade.status != "OPEN",
        )
        .all()
    )

    if not closed_trades:
        return

    total = len(closed_trades)
    wins = sum(1 for t in closed_trades if t.pnl_usd > 0)
    total_pnl = sum(t.pnl_percent for t in closed_trades)

    perf.paper_total = total
    perf.paper_wins = wins
    perf.paper_win_rate = round(wins / total, 4) if total > 0 else 0
    perf.paper_pnl_pct = round(total_pnl, 2)

    try:
        session.commit()
    except Exception:
        session.rollback()


def record_snapshot(trade_id: int, current_price: float):
    """Record a price snapshot for an open trade. Updates MFE/MAE."""
    session = get_session()
    try:
        trade = session.query(PaperTrade).get(trade_id)
        if trade is None or trade.status != "OPEN":
            return

        pnl = calculate_pnl(
            trade.entry_price, current_price, trade.bias,
            trade.leverage, trade.position_size_usd,
        )

        # Update max drawdown / max profit
        if pnl["pnl_percent"] < trade.max_drawdown:
            trade.max_drawdown = pnl["pnl_percent"]
        if pnl["pnl_percent"] > trade.max_profit:
            trade.max_profit = pnl["pnl_percent"]

        # Update MFE/MAE (Faz 7)
        if pnl["pnl_percent"] > (trade.mfe_pct or 0):
            trade.mfe_pct = pnl["pnl_percent"]
        if pnl["pnl_percent"] < (trade.mae_pct or 0):
            trade.mae_pct = pnl["pnl_percent"]

        session.add(TradeSnapshot(
            paper_trade_id=trade_id,
            current_price=current_price,
            unrealized_pnl=pnl["pnl_usd"],
            timestamp=datetime.utcnow(),
        ))

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Snapshot error: {e}")
    finally:
        session.close()
