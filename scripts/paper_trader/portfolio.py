"""
Phalidae v2 - Portfolio Manager (Phase 2)
Dynamic position sizing, risk management, portfolio snapshots.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import func

from db.engine import get_session
from db.models import PaperTrade, PortfolioSnapshot, CorrelationCache, TradeSnapshot
from paper_trader.position import calculate_pnl

logger = logging.getLogger("phalidae.portfolio")

INITIAL_CAPITAL = 100_000.0
MAX_RISK_PER_TRADE_PCT = 1.0          # Small positions, many trades (learning mode)
MAX_TOTAL_EXPOSURE_PCT = 95.0          # 150 coins x ~$600 = $90K
MAX_POSITION_SIZE_USD = 800.0          # Hard cap per trade (learning mode: small + many)
MAX_OPEN_POSITIONS = 150               # ~120-150 active coins = theoretical max
MAX_DAILY_LOSS_PCT = 15.0              # Learning mode: higher tolerance


def get_portfolio_equity() -> float:
    """Total equity = initial capital + all realized P&L + unrealized P&L."""
    session = get_session()
    try:
        # Sum of all closed trade P&L
        realized_pnl = (
            session.query(func.sum(PaperTrade.pnl_usd))
            .filter(PaperTrade.status != "OPEN")
            .scalar()
        ) or 0.0

        # Add partial TP P&L from open trades
        partial_pnl = (
            session.query(func.sum(PaperTrade.partial_tp_pnl))
            .filter(PaperTrade.status == "OPEN")
            .scalar()
        ) or 0.0

        return INITIAL_CAPITAL + realized_pnl + partial_pnl
    finally:
        session.close()


def get_cash_balance() -> float:
    """Available cash = equity - total position sizes of open trades."""
    equity = get_portfolio_equity()
    session = get_session()
    try:
        open_notional = (
            session.query(func.sum(PaperTrade.position_size_usd))
            .filter_by(status="OPEN")
            .scalar()
        ) or 0.0
        return max(equity - open_notional, 0.0)
    finally:
        session.close()


def calculate_position_size(
    symbol: str,
    bias: str,
    entry: float,
    sl: float,
    leverage: float = 5.0,
) -> float:
    """
    Risk-based position sizing:
    risk_amount = equity * (MAX_RISK_PER_TRADE_PCT / 100)
    distance_pct = abs(entry - sl) / entry
    position_size = risk_amount / (distance_pct * leverage)
    Clamped between $50 and max per-position limit.
    """
    equity = get_portfolio_equity()
    if equity < 100:
        return 0.0

    risk_amount = equity * (MAX_RISK_PER_TRADE_PCT / 100)
    distance_pct = abs(entry - sl) / entry if entry > 0 else 0.05

    if distance_pct <= 0:
        distance_pct = 0.01

    position_size = risk_amount / (distance_pct * leverage)

    # Clamp
    session = get_session()
    try:
        open_count = session.query(PaperTrade).filter_by(status="OPEN").count()
    finally:
        session.close()

    max_per_position = (equity * MAX_TOTAL_EXPOSURE_PCT / 100) / max(open_count + 1, 1)
    position_size = max(100.0, min(position_size, max_per_position, MAX_POSITION_SIZE_USD))

    return round(position_size, 2)


def can_open_trade(symbol: str = None) -> tuple[bool, str]:
    """
    Pre-trade portfolio checks:
    1. cash_balance > minimum ($50)
    2. total_exposure < MAX_TOTAL_EXPOSURE_PCT
    3. open_positions < MAX_OPEN_POSITIONS
    4. daily_realized_loss < MAX_DAILY_LOSS_PCT
    Returns (allowed, reason).
    """
    equity = get_portfolio_equity()
    if equity <= 0:
        return False, f"Portfoy sifir veya negatif: ${equity:.2f}"

    cash = get_cash_balance()

    if cash < 100:
        return False, f"Yetersiz nakit: ${cash:.2f}"

    session = get_session()
    try:
        open_count = session.query(PaperTrade).filter_by(status="OPEN").count()
        if open_count >= MAX_OPEN_POSITIONS:
            return False, f"Max pozisyon limiti: {open_count}/{MAX_OPEN_POSITIONS}"

        open_notional = (
            session.query(func.sum(PaperTrade.position_size_usd))
            .filter_by(status="OPEN")
            .scalar()
        ) or 0.0

        exposure_pct = (open_notional / equity * 100) if equity > 0 else 100
        if exposure_pct >= MAX_TOTAL_EXPOSURE_PCT:
            return False, f"Max exposure: {exposure_pct:.1f}% >= {MAX_TOTAL_EXPOSURE_PCT}%"

        # Daily loss check
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_pnl = (
            session.query(func.sum(PaperTrade.pnl_usd))
            .filter(
                PaperTrade.status != "OPEN",
                PaperTrade.closed_at >= today_start,
            )
            .scalar()
        ) or 0.0

        daily_loss_pct = (daily_pnl / equity * 100) if equity > 0 else 0
        if daily_loss_pct < -MAX_DAILY_LOSS_PCT:
            return False, f"Gunluk kayip limiti: {daily_loss_pct:.1f}%"

    finally:
        session.close()

    return True, "OK"


def record_portfolio_snapshot():
    """Record current portfolio state as a snapshot."""
    equity = get_portfolio_equity()
    cash = get_cash_balance()

    session = get_session()
    try:
        open_trades = session.query(PaperTrade).filter_by(status="OPEN").all()
        open_count = len(open_trades)
        total_notional = sum(t.position_size_usd for t in open_trades)

        # Unrealized P&L from latest TradeSnapshot (actual current P&L, not MFE)
        unrealized = 0.0
        for t in open_trades:
            latest_snap = (
                session.query(TradeSnapshot)
                .filter_by(paper_trade_id=t.id)
                .order_by(TradeSnapshot.timestamp.desc())
                .first()
            )
            if latest_snap:
                unrealized += latest_snap.unrealized_pnl
            else:
                # Fallback if no snapshot yet
                unrealized += t.max_profit * t.position_size_usd / 100

        # Today's realized
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        realized_today = (
            session.query(func.sum(PaperTrade.pnl_usd))
            .filter(
                PaperTrade.status != "OPEN",
                PaperTrade.closed_at >= today_start,
            )
            .scalar()
        ) or 0.0

        # Max drawdown from all snapshots
        all_snapshots = (
            session.query(PortfolioSnapshot.total_equity)
            .order_by(PortfolioSnapshot.timestamp)
            .all()
        )

        max_dd = 0.0
        peak = INITIAL_CAPITAL
        for (eq,) in all_snapshots:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Current DD
        current_dd = (peak - equity) / peak * 100 if peak > 0 and equity < peak else 0
        max_dd = max(max_dd, current_dd)

        # Regime distribution of open trades
        regime_dist = {}
        for t in open_trades:
            r = t.regime_at_entry or "UNKNOWN"
            regime_dist[r] = regime_dist.get(r, 0) + 1

        session.add(PortfolioSnapshot(
            timestamp=datetime.utcnow(),
            total_equity=round(equity, 2),
            cash_balance=round(cash, 2),
            open_positions=open_count,
            total_notional=round(total_notional, 2),
            unrealized_pnl=round(unrealized, 2),
            realized_pnl_today=round(realized_today, 2),
            max_drawdown_pct=round(max_dd, 2),
            regime_distribution=regime_dist if regime_dist else None,
        ))
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Portfolio snapshot error: {e}")
    finally:
        session.close()


def _compute_unrealized_pnl(session) -> float:
    """Compute total unrealized P&L from latest TradeSnapshot per open trade."""
    open_trades = session.query(PaperTrade).filter_by(status="OPEN").all()
    if not open_trades:
        return 0.0

    unrealized = 0.0
    for t in open_trades:
        latest_snap = (
            session.query(TradeSnapshot)
            .filter_by(paper_trade_id=t.id)
            .order_by(TradeSnapshot.timestamp.desc())
            .first()
        )
        if latest_snap:
            unrealized += latest_snap.unrealized_pnl
        elif t.max_profit and t.position_size_usd:
            # Fallback: approximate from max_profit percentage
            unrealized += t.max_profit * t.position_size_usd / 100

    return unrealized


def get_portfolio_summary() -> dict:
    """Dashboard-friendly portfolio summary (includes unrealized P&L)."""
    equity = get_portfolio_equity()
    cash = get_cash_balance()

    session = get_session()
    try:
        open_count = session.query(PaperTrade).filter_by(status="OPEN").count()
        open_notional = (
            session.query(func.sum(PaperTrade.position_size_usd))
            .filter_by(status="OPEN")
            .scalar()
        ) or 0.0

        exposure_pct = (open_notional / equity * 100) if equity > 0 else 0

        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        daily_pnl = (
            session.query(func.sum(PaperTrade.pnl_usd))
            .filter(
                PaperTrade.status != "OPEN",
                PaperTrade.closed_at >= today_start,
            )
            .scalar()
        ) or 0.0

        # Unrealized P&L from open positions
        unrealized_pnl = _compute_unrealized_pnl(session)

        # True portfolio value = equity (realized) + unrealized
        total_equity = equity + unrealized_pnl
        total_pnl = total_equity - INITIAL_CAPITAL
        total_pnl_pct = (total_pnl / INITIAL_CAPITAL * 100) if INITIAL_CAPITAL > 0 else 0

        return {
            "equity": round(total_equity, 2),
            "realized_equity": round(equity, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "cash": round(cash, 2),
            "open_positions": open_count,
            "exposure_pct": round(exposure_pct, 1),
            "daily_pnl": round(daily_pnl, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
            "initial_capital": INITIAL_CAPITAL,
        }
    finally:
        session.close()
