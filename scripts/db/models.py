"""
Phalidae v2 - ORM Models (16 tables)
Phase 1: AgentJob
Phase 2: PortfolioSnapshot, TradeManagementLog + PaperTrade new columns
Phase 4: NewsEvent, ExternalAnalysis
Phase 5: Signal new columns (confidence_score, eta, invalidation)
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime, Text, JSON,
    ForeignKey, UniqueConstraint, Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class OHLCVData(Base):
    __tablename__ = "ohlcv_data"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uix_ohlcv"),
    )


class TrackedSymbol(Base):
    __tablename__ = "tracked_symbols"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), unique=True, nullable=False)
    rank = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    data_since = Column(DateTime, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)


class StrategyVariant(Base):
    __tablename__ = "strategy_variants"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    composition = Column(JSON, nullable=False)
    trend_threshold = Column(Float, default=0.3)
    entry_threshold = Column(Float, default=0.3)
    volume_required = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    performances = relationship("StrategyPerformance", back_populates="strategy")


class StrategyPerformance(Base):
    __tablename__ = "strategy_performance"

    id = Column(Integer, primary_key=True)
    strategy_variant_id = Column(Integer, ForeignKey("strategy_variants.id"), nullable=False)
    symbol = Column(String(30), nullable=False, index=True)

    # Backtest results
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    win_rate = Column(Float, default=0.0)
    profit_factor = Column(Float, default=0.0)
    sharpe_ratio = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    total_pnl_pct = Column(Float, default=0.0)

    # Paper trade results
    paper_total = Column(Integer, default=0)
    paper_wins = Column(Integer, default=0)
    paper_win_rate = Column(Float, default=0.0)
    paper_pnl_pct = Column(Float, default=0.0)

    # Regime-specific scores (Faz 8)
    regime_trending_score = Column(Float, default=0.0)
    regime_ranging_score = Column(Float, default=0.0)
    regime_volatile_score = Column(Float, default=0.0)

    composite_score = Column(Float, default=0.0)
    rank = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    strategy = relationship("StrategyVariant", back_populates="performances")

    __table_args__ = (
        UniqueConstraint("strategy_variant_id", "symbol", name="uix_strat_perf"),
        Index("ix_strat_perf_score", "symbol", "composite_score"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), nullable=False, index=True)
    bias = Column(String(5), nullable=False)  # LONG / SHORT
    entry_price = Column(Float, nullable=False)
    tp_price = Column(Float)
    sl_price = Column(Float)
    rr_ratio = Column(Float)
    confidence = Column(String(10))
    score = Column(Float)

    strategy_variant_id = Column(Integer, ForeignKey("strategy_variants.id"), nullable=True)
    score_breakdown = Column(JSON, nullable=True)
    indicator_scores = Column(JSON, nullable=True)
    detected_patterns = Column(JSON, nullable=True)
    reasoning = Column(Text, nullable=True)

    # Regime + decision trace
    regime = Column(String(20), nullable=True)
    alternative_signals = Column(JSON, nullable=True)
    rejection_reasons = Column(JSON, nullable=True)

    # Phase 5: confidence scoring, ETA, news risk, invalidation
    confidence_score = Column(Float, nullable=True)           # 0-100
    confidence_breakdown = Column(JSON, nullable=True)
    eta_hours_low = Column(Float, nullable=True)
    eta_hours_high = Column(Float, nullable=True)
    news_risk_score = Column(Float, nullable=True)            # 0-1
    invalidation_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    paper_trades = relationship("PaperTrade", back_populates="signal")


class PaperTrade(Base):
    __tablename__ = "paper_trades"

    id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    symbol = Column(String(30), nullable=False, index=True)
    bias = Column(String(5), nullable=False)
    entry_price = Column(Float, nullable=False)
    tp_price = Column(Float)
    sl_price = Column(Float)
    leverage = Column(Float, default=1.0)
    liquidation_price = Column(Float, nullable=True)
    position_size_usd = Column(Float, default=1000.0)

    status = Column(String(15), default="OPEN", index=True)  # OPEN/TP_HIT/SL_HIT/TRAILING_STOP/TIME_EXPIRED/LIQUIDATED
    exit_price = Column(Float, nullable=True)
    pnl_usd = Column(Float, default=0.0)
    pnl_percent = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    max_profit = Column(Float, default=0.0)
    reasoning = Column(Text, nullable=True)

    # MFE/MAE, exit reason, trailing stop, regime
    mfe_pct = Column(Float, default=0.0)
    mae_pct = Column(Float, default=0.0)
    exit_reason = Column(String(20), nullable=True)
    trailing_stop_price = Column(Float, nullable=True)
    regime_at_entry = Column(String(20), nullable=True)

    # Phase 2: partial TP tracking + dynamic sizing
    partial_tp_taken = Column(Boolean, default=False)
    partial_tp_price = Column(Float, nullable=True)
    partial_tp_pnl = Column(Float, default=0.0)
    tp2_price = Column(Float, nullable=True)
    tp3_price = Column(Float, nullable=True)
    risk_pct = Column(Float, nullable=True)

    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    signal = relationship("Signal", back_populates="paper_trades")
    snapshots = relationship("TradeSnapshot", back_populates="trade", cascade="all, delete-orphan")


class TradeSnapshot(Base):
    __tablename__ = "trade_snapshots"

    id = Column(Integer, primary_key=True)
    paper_trade_id = Column(Integer, ForeignKey("paper_trades.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)

    trade = relationship("PaperTrade", back_populates="snapshots")


class CoinConfig(Base):
    __tablename__ = "coin_config"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), unique=True, nullable=False)
    best_strategy_id = Column(Integer, ForeignKey("strategy_variants.id"), nullable=True)
    auto_trade = Column(Boolean, default=True)

    # New: per-coin risk settings (Faz 5)
    leverage = Column(Float, default=5.0)
    max_position_size = Column(Float, default=1000.0)
    daily_drawdown_limit = Column(Float, default=10.0)  # Max daily loss %
    trailing_stop_enabled = Column(Boolean, default=True)
    time_stop_bars = Column(Integer, default=50)  # 4h bars until time stop

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ═══════════════════════════════════════════════════
# New tables (Faz 3/4)
# ═══════════════════════════════════════════════════

class FundingData(Base):
    __tablename__ = "funding_data"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    funding_rate = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)    # USD
    spread_pct = Column(Float, nullable=True)       # Bid-ask spread %

    __table_args__ = (
        UniqueConstraint("symbol", "timestamp", name="uix_funding"),
    )


class MarketRegimeRecord(Base):
    __tablename__ = "market_regime_records"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), nullable=False, index=True)
    timeframe = Column(String(5), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    regime_label = Column(String(20), nullable=False)
    adx_value = Column(Float, nullable=True)
    choppiness_value = Column(Float, nullable=True)
    atr_percentile = Column(Float, nullable=True)
    ema_slope = Column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uix_regime"),
    )


class CorrelationCache(Base):
    __tablename__ = "correlation_cache"

    id = Column(Integer, primary_key=True)
    symbol_a = Column(String(30), nullable=False, index=True)
    symbol_b = Column(String(30), nullable=False, index=True)
    correlation = Column(Float, nullable=False)
    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("symbol_a", "symbol_b", name="uix_corr_pair"),
    )


# ═══════════════════════════════════════════════════
# Phase 1: Agent Health
# ═══════════════════════════════════════════════════

class AgentJob(Base):
    __tablename__ = "agent_jobs"

    id = Column(Integer, primary_key=True)
    job_name = Column(String(50), nullable=False, index=True)
    status = Column(String(15), nullable=False)          # RUNNING, SUCCESS, FAILED
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_sec = Column(Float, nullable=True)
    records_affected = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    context = Column(JSON, nullable=True)


# ═══════════════════════════════════════════════════
# Phase 2: Portfolio + Trade Management
# ═══════════════════════════════════════════════════

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    total_equity = Column(Float, nullable=False)
    cash_balance = Column(Float, nullable=False)
    open_positions = Column(Integer, default=0)
    total_notional = Column(Float, default=0.0)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl_today = Column(Float, default=0.0)
    max_drawdown_pct = Column(Float, default=0.0)
    regime_distribution = Column(JSON, nullable=True)


class TradeManagementLog(Base):
    __tablename__ = "trade_management_log"

    id = Column(Integer, primary_key=True)
    paper_trade_id = Column(Integer, ForeignKey("paper_trades.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    event_type = Column(String(30), nullable=False)
    old_value = Column(Float, nullable=True)
    new_value = Column(Float, nullable=True)
    reason = Column(String(200), nullable=True)
    current_price = Column(Float, nullable=True)
    current_pnl_pct = Column(Float, nullable=True)


# ═══════════════════════════════════════════════════
# Phase 4: News + External Analysis
# ═══════════════════════════════════════════════════

class NewsEvent(Base):
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True)
    source = Column(String(30), nullable=False)
    external_id = Column(String(100), nullable=True)
    title = Column(String(500), nullable=False)
    url = Column(String(500), nullable=True)
    published_at = Column(DateTime, nullable=False, index=True)
    symbols = Column(JSON, nullable=True)
    sentiment = Column(String(10), nullable=True)
    impact_score = Column(Float, default=0.0)
    votes_positive = Column(Integer, default=0)
    votes_negative = Column(Integer, default=0)
    is_important = Column(Boolean, default=False)
    fetched_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uix_news_source_id"),
    )


class ExternalAnalysis(Base):
    __tablename__ = "external_analyses"

    id = Column(Integer, primary_key=True)
    symbol = Column(String(30), nullable=True, index=True)
    source_type = Column(String(30), nullable=False)
    source_url = Column(String(500), nullable=True)
    author = Column(String(100), nullable=True)
    summary = Column(Text, nullable=False)
    tools_used = Column(JSON, nullable=True)
    bias_claimed = Column(String(5), nullable=True)
    target_price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    outcome = Column(String(15), nullable=True)
    outcome_notes = Column(Text, nullable=True)
    lesson_learned = Column(Text, nullable=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    verified_at = Column(DateTime, nullable=True)
