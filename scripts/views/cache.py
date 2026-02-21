"""
Phalidae v2 - Merkezi Cache Katmani
Tum agir DB sorgularini @st.cache_data ile sarar.
Her fonksiyon kendi session'ini acar/kapar, JSON-serializable tipler doner.

TTL Stratejisi:
  30s  → Portfolio, acik tradeler, gunluk P&L (canli hissettirmek icin)
  60s  → Agent health, sinyal sayisi (yakin-gercek-zamanli izleme)
  120s → Rejim haritasi, funding rate (market data 15dk'da guncellenir)
  300s → Kapsam matrisi, stratejiler, korelasyonlar (collector 5dk'da calisir)
  600s → DB boyutu (nadiren degisir, pahali sorgu)
"""

import logging
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from sqlalchemy import func, text, and_, case

from db.engine import get_session
from db.models import (
    OHLCVData, TrackedSymbol, PaperTrade, StrategyVariant,
    StrategyPerformance, CoinConfig, Signal, FundingData,
    MarketRegimeRecord, AgentJob, CorrelationCache,
)

logger = logging.getLogger("phalidae.cache")


# ---------------------------------------------------------------------------
# Portfolio & Trades (TTL=30s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def get_portfolio_summary_cached() -> dict:
    """Portfolio ozeti — paper_trader.portfolio.get_portfolio_summary() wrapper."""
    try:
        from paper_trader.portfolio import get_portfolio_summary
        return get_portfolio_summary()
    except Exception as e:
        logger.warning(f"Portfolio summary error: {e}")
        return {
            "equity": 0, "cash": 0, "open_positions": 0,
            "exposure_pct": 0, "daily_pnl": 0, "total_pnl": 0,
            "total_pnl_pct": 0, "initial_capital": 100_000,
        }


@st.cache_data(ttl=30, show_spinner=False)
def get_open_trades_cached() -> list[dict]:
    """Tum acik tradeleri dict listesi olarak doner."""
    session = get_session()
    try:
        trades = (
            session.query(PaperTrade)
            .filter_by(status="OPEN")
            .order_by(PaperTrade.opened_at.desc())
            .all()
        )
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "bias": t.bias,
                "entry_price": float(t.entry_price),
                "tp_price": float(t.tp_price) if t.tp_price else None,
                "sl_price": float(t.sl_price) if t.sl_price else None,
                "trailing_stop_price": float(t.trailing_stop_price) if t.trailing_stop_price else None,
                "partial_tp_taken": bool(t.partial_tp_taken),
                "position_size_usd": float(t.position_size_usd) if t.position_size_usd else None,
                "leverage": float(t.leverage) if t.leverage else 5.0,
                "mfe_pct": float(t.mfe_pct or 0),
                "mae_pct": float(t.mae_pct or 0),
                "max_profit": float(t.max_profit or 0),
                "max_drawdown": float(t.max_drawdown or 0),
                "regime_at_entry": t.regime_at_entry,
                "opened_at": t.opened_at.strftime("%m-%d %H:%M") if t.opened_at else "-",
                "risk_pct": float(t.risk_pct) if t.risk_pct else None,
                "partial_tp_price": float(t.partial_tp_price) if t.partial_tp_price else None,
                "tp2_price": float(t.tp2_price) if t.tp2_price else None,
                "tp3_price": float(t.tp3_price) if t.tp3_price else None,
            }
            for t in trades
        ]
    finally:
        session.close()


@st.cache_data(ttl=30, show_spinner=False)
def get_daily_pnl_cached() -> dict:
    """Bugunun kapanan trade ozeti — aggregation sorgusu."""
    session = get_session()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        result = (
            session.query(
                func.count(PaperTrade.id).label("count"),
                func.coalesce(func.sum(PaperTrade.pnl_usd), 0).label("pnl_usd"),
                func.coalesce(func.sum(PaperTrade.pnl_percent), 0).label("pnl_pct"),
                func.sum(
                    case((PaperTrade.pnl_usd > 0, 1), else_=0)
                ).label("wins"),
            )
            .filter(
                PaperTrade.status != "OPEN",
                PaperTrade.closed_at >= today_start,
            )
            .first()
        )
        return {
            "count": int(result.count or 0),
            "pnl_usd": float(result.pnl_usd or 0),
            "pnl_pct": float(result.pnl_pct or 0),
            "wins": int(result.wins or 0),
        }
    except Exception as e:
        logger.warning(f"Daily PnL error: {e}")
        return {"count": 0, "pnl_usd": 0, "pnl_pct": 0, "wins": 0}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# System Stats (TTL=60s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def get_system_stats_cached() -> dict:
    """Tek SQL sorgusu ile 7 metrigi toplar."""
    session = get_session()
    try:
        total_candles = session.query(func.count(OHLCVData.id)).scalar() or 0
        active_symbols = session.query(TrackedSymbol).filter_by(is_active=True).count()
        total_variants = session.query(StrategyVariant).count()
        open_trades = session.query(PaperTrade).filter_by(status="OPEN").count()
        total_signals = session.query(func.count(Signal.id)).scalar() or 0
        closed_trades = session.query(PaperTrade).filter(PaperTrade.status != "OPEN").count()
        # Kapali trade P&L
        closed_pnl = session.query(func.sum(PaperTrade.pnl_usd)).filter(
            PaperTrade.status != "OPEN"
        ).scalar() or 0
        # Acik tradelerdeki partial TP P&L (portfolio equity'ye dahil)
        partial_pnl = session.query(func.sum(PaperTrade.partial_tp_pnl)).filter(
            PaperTrade.status == "OPEN"
        ).scalar() or 0
        total_pnl = float(closed_pnl) + float(partial_pnl)

        return {
            "total_candles": int(total_candles),
            "active_symbols": int(active_symbols),
            "total_variants": int(total_variants),
            "open_trades": int(open_trades),
            "total_signals": int(total_signals),
            "closed_trades": int(closed_trades),
            "total_pnl": float(total_pnl),
        }
    finally:
        session.close()


@st.cache_data(ttl=45, show_spinner=False)
def get_agent_health_cached() -> dict:
    """Tek bulk sorgu ile tum job'larin son 3 calismasini + 24h istatistiklerini getirir."""
    session = get_session()
    try:
        job_names = [
            "collector", "analyzer", "trade_checker", "optimizer",
            "market_data", "symbol_refresh", "news_collector",
        ]

        # Son 3 calisma — her job icin
        jobs_data = {}
        for job_name in job_names:
            recent = (
                session.query(AgentJob)
                .filter_by(job_name=job_name)
                .order_by(AgentJob.started_at.desc())
                .limit(3)
                .all()
            )
            if recent:
                last = recent[0]
                jobs_data[job_name] = {
                    "status": last.status,
                    "started_at": last.started_at.isoformat() if last.started_at else None,
                    "completed_at": last.completed_at.isoformat() if last.completed_at else None,
                    "duration_sec": float(last.duration_sec) if last.duration_sec else None,
                    "records_affected": int(last.records_affected or 0),
                }
            else:
                jobs_data[job_name] = None

        # 24h basari/hata
        last_24h = datetime.utcnow() - timedelta(hours=24)
        success_count = session.query(func.count(AgentJob.id)).filter(
            AgentJob.status == "SUCCESS",
            AgentJob.started_at >= last_24h,
        ).scalar() or 0
        fail_count = session.query(func.count(AgentJob.id)).filter(
            AgentJob.status == "FAILED",
            AgentJob.started_at >= last_24h,
        ).scalar() or 0

        return {
            "jobs": jobs_data,
            "success_24h": int(success_count),
            "fail_24h": int(fail_count),
        }
    finally:
        session.close()


@st.cache_data(ttl=60, show_spinner=False)
def get_recent_signals_cached(limit: int = 100) -> list[dict]:
    """signal_generator.get_recent_signals_from_db wrapper."""
    try:
        from signal_generator import get_recent_signals_from_db
        return get_recent_signals_from_db(limit=limit)
    except Exception as e:
        logger.warning(f"Recent signals error: {e}")
        return []


# ---------------------------------------------------------------------------
# Market Data (TTL=120s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=120, show_spinner=False)
def get_regime_map_cached() -> list[dict]:
    """Son rejim/coin — subquery pattern."""
    session = get_session()
    try:
        subq = (
            session.query(
                MarketRegimeRecord.symbol,
                func.max(MarketRegimeRecord.timestamp).label("max_ts")
            )
            .group_by(MarketRegimeRecord.symbol)
            .subquery()
        )
        regimes = (
            session.query(MarketRegimeRecord)
            .join(subq, and_(
                MarketRegimeRecord.symbol == subq.c.symbol,
                MarketRegimeRecord.timestamp == subq.c.max_ts,
            ))
            .all()
        )
        return [
            {
                "symbol": r.symbol,
                "regime_label": r.regime_label,
            }
            for r in regimes
        ]
    finally:
        session.close()


@st.cache_data(ttl=120, show_spinner=False)
def get_funding_data_cached() -> list[dict]:
    """Son funding rate/coin — subquery pattern."""
    session = get_session()
    try:
        subq = (
            session.query(
                FundingData.symbol,
                func.max(FundingData.timestamp).label("max_ts")
            )
            .group_by(FundingData.symbol)
            .subquery()
        )
        funding = (
            session.query(FundingData)
            .join(subq, and_(
                FundingData.symbol == subq.c.symbol,
                FundingData.timestamp == subq.c.max_ts,
            ))
            .order_by(FundingData.symbol)
            .all()
        )
        return [
            {
                "symbol": f.symbol,
                "funding_rate": float(f.funding_rate) if f.funding_rate else None,
                "open_interest": float(f.open_interest) if f.open_interest else None,
                "spread_pct": float(f.spread_pct) if f.spread_pct else None,
                "timestamp": f.timestamp.strftime("%H:%M") if f.timestamp else "-",
            }
            for f in funding
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Strategy & Coverage (TTL=300s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def get_coverage_matrix_cached() -> pd.DataFrame:
    """TEK GROUP BY sorgusu: 968 sorguyu 1'e dusurur."""
    session = get_session()
    try:
        rows = (
            session.query(
                OHLCVData.symbol,
                OHLCVData.timeframe,
                func.count(OHLCVData.id).label("cnt"),
            )
            .group_by(OHLCVData.symbol, OHLCVData.timeframe)
            .all()
        )
        if not rows:
            return pd.DataFrame()

        data = [{"symbol": r.symbol, "timeframe": r.timeframe, "cnt": int(r.cnt)} for r in rows]
        df = pd.DataFrame(data)
        pivot = df.pivot_table(index="symbol", columns="timeframe", values="cnt", fill_value=0)
        pivot = pivot.reset_index()
        pivot["Coin"] = pivot["symbol"].str.replace("/USDT:USDT", "", regex=False)
        return pivot
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_data_coverage_summary_cached() -> list[dict]:
    """Dashboard icin: symbol, count, earliest, latest."""
    session = get_session()
    try:
        coverage = (
            session.query(
                OHLCVData.symbol,
                func.count(OHLCVData.id).label("cnt"),
                func.min(OHLCVData.timestamp).label("earliest"),
                func.max(OHLCVData.timestamp).label("latest"),
            )
            .group_by(OHLCVData.symbol)
            .all()
        )
        return [
            {
                "symbol": c.symbol,
                "cnt": int(c.cnt),
                "earliest": c.earliest.strftime("%Y-%m-%d") if c.earliest else "-",
                "latest": c.latest.strftime("%Y-%m-%d %H:%M") if c.latest else "-",
            }
            for c in coverage
        ]
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_best_strategies_cached() -> list[dict]:
    """CoinConfig + StrategyVariant + StrategyPerformance join."""
    session = get_session()
    try:
        configs = (
            session.query(CoinConfig, StrategyVariant, StrategyPerformance)
            .join(StrategyVariant, CoinConfig.best_strategy_id == StrategyVariant.id)
            .outerjoin(
                StrategyPerformance,
                (StrategyPerformance.strategy_variant_id == StrategyVariant.id) &
                (StrategyPerformance.symbol == CoinConfig.symbol)
            )
            .all()
        )
        return [
            {
                "symbol": config.symbol,
                "strategy_name": variant.name[:40] if variant.name else "?",
                "leverage": float(config.leverage) if config.leverage else 5.0,
                "auto_trade": bool(config.auto_trade),
                "win_rate": float(perf.win_rate) if perf and perf.win_rate else None,
                "profit_factor": float(perf.profit_factor) if perf and perf.profit_factor else None,
                "sharpe_ratio": float(perf.sharpe_ratio) if perf and perf.sharpe_ratio else None,
                "max_drawdown": float(perf.max_drawdown) if perf and perf.max_drawdown else None,
                "composite_score": float(perf.composite_score) if perf and perf.composite_score else None,
                "paper_win_rate": float(perf.paper_win_rate) if perf and perf.paper_total and perf.paper_total > 0 else None,
            }
            for config, variant, perf in configs
        ]
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_active_symbols_cached() -> list[dict]:
    """Tum sayfalarda ortak kullanilacak symbol listesi."""
    session = get_session()
    try:
        symbols = (
            session.query(TrackedSymbol)
            .filter_by(is_active=True)
            .order_by(TrackedSymbol.rank)
            .all()
        )
        return [
            {"symbol": s.symbol, "rank": s.rank}
            for s in symbols
        ]
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_global_leaderboard_cached() -> list[dict]:
    """Strategy Lab'daki agir join."""
    session = get_session()
    try:
        results = (
            session.query(
                StrategyVariant.id,
                StrategyVariant.name,
                StrategyVariant.composition,
                func.avg(StrategyPerformance.composite_score).label("avg_score"),
                func.avg(StrategyPerformance.win_rate).label("avg_wr"),
                func.avg(StrategyPerformance.profit_factor).label("avg_pf"),
                func.sum(StrategyPerformance.total_trades).label("total_trades"),
                func.count(StrategyPerformance.symbol).label("coin_count"),
                func.avg(StrategyPerformance.regime_trending_score).label("avg_trend_wr"),
                func.avg(StrategyPerformance.regime_ranging_score).label("avg_range_wr"),
                func.avg(StrategyPerformance.regime_volatile_score).label("avg_vol_wr"),
            )
            .join(StrategyPerformance, StrategyVariant.id == StrategyPerformance.strategy_variant_id)
            .filter(StrategyPerformance.composite_score > 0)
            .group_by(StrategyVariant.id)
            .having(func.count(StrategyPerformance.symbol) >= 3)
            .order_by(func.avg(StrategyPerformance.composite_score).desc())
            .limit(50)
            .all()
        )
        rows = []
        for r in results:
            try:
                comp = r.composition if isinstance(r.composition, dict) else {}
                trend_str = ", ".join(comp.get("trend", []))
            except (TypeError, AttributeError):
                trend_str = "?"
            rows.append({
                "id": r.id,
                "name": r.name[:35] if r.name else "?",
                "avg_score": float(r.avg_score) if r.avg_score else 0,
                "avg_wr": float(r.avg_wr) if r.avg_wr else 0,
                "avg_pf": float(r.avg_pf) if r.avg_pf else 0,
                "total_trades": int(r.total_trades) if r.total_trades else 0,
                "coin_count": int(r.coin_count) if r.coin_count else 0,
                "avg_trend_wr": float(r.avg_trend_wr) if r.avg_trend_wr else None,
                "avg_range_wr": float(r.avg_range_wr) if r.avg_range_wr else None,
                "avg_vol_wr": float(r.avg_vol_wr) if r.avg_vol_wr else None,
                "trend_str": trend_str[:30],
            })
        return rows
    finally:
        session.close()


@st.cache_data(ttl=300, show_spinner=False)
def get_correlation_data_cached() -> list[dict]:
    """Korelasyon verisi."""
    session = get_session()
    try:
        correlations = session.query(CorrelationCache).all()
        return [
            {
                "symbol_a": c.symbol_a,
                "symbol_b": c.symbol_b,
                "correlation": float(c.correlation),
            }
            for c in correlations
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# DB Size (TTL=600s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False)
def get_db_size_cached() -> float:
    """pg_database_size() — 10dk cache."""
    session = get_session()
    try:
        result = session.execute(text("SELECT pg_database_size(current_database())")).scalar()
        return float(result or 0) / (1024 * 1024)
    except Exception:
        return 0.0
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Paper Trades - Aggregated (TTL varies)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def get_trade_summary_cached() -> dict:
    """Tum kapali trade'lerin aggregated ozeti — row yuklemeden."""
    session = get_session()
    try:
        # Closed summary
        closed_agg = (
            session.query(
                func.count(PaperTrade.id).label("total"),
                func.coalesce(func.sum(PaperTrade.pnl_usd), 0).label("total_pnl"),
                func.sum(case((PaperTrade.pnl_usd > 0, 1), else_=0)).label("wins"),
            )
            .filter(PaperTrade.status != "OPEN")
            .first()
        )

        # Exit reason counts
        tp_hits = session.query(func.count(PaperTrade.id)).filter(
            PaperTrade.status == "TP_HIT"
        ).scalar() or 0
        sl_hits = session.query(func.count(PaperTrade.id)).filter(
            PaperTrade.status == "SL_HIT"
        ).scalar() or 0
        trail_stops = session.query(func.count(PaperTrade.id)).filter(
            PaperTrade.status == "TRAILING_STOP"
        ).scalar() or 0
        partial_tps = session.query(func.count(PaperTrade.id)).filter(
            PaperTrade.status == "PARTIAL_TP"
        ).scalar() or 0
        time_expired = session.query(func.count(PaperTrade.id)).filter(
            PaperTrade.status == "TIME_EXPIRED"
        ).scalar() or 0

        open_count = session.query(PaperTrade).filter_by(status="OPEN").count()

        total_closed = int(closed_agg.total or 0)
        wins = int(closed_agg.wins or 0)

        return {
            "open_count": open_count,
            "closed_count": total_closed,
            "total_pnl": float(closed_agg.total_pnl or 0),
            "wins": wins,
            "win_rate": wins / total_closed if total_closed > 0 else 0,
            "tp_hits": int(tp_hits),
            "sl_hits": int(sl_hits),
            "trail_stops": int(trail_stops),
            "partial_tps": int(partial_tps),
            "time_expired": int(time_expired),
        }
    finally:
        session.close()


@st.cache_data(ttl=60, show_spinner=False)
def get_closed_trades_cached(limit: int = 200) -> list[dict]:
    """Kapali tradeler — dict listesi."""
    session = get_session()
    try:
        trades = (
            session.query(PaperTrade)
            .filter(PaperTrade.status != "OPEN")
            .order_by(PaperTrade.closed_at.desc())
            .limit(limit)
            .all()
        )
        rows = []
        for t in trades:
            duration = ""
            if t.opened_at and t.closed_at:
                delta = t.closed_at - t.opened_at
                hours = delta.total_seconds() / 3600
                if hours >= 24:
                    duration = f"{hours/24:.1f}g"
                else:
                    duration = f"{hours:.1f}s"

            rows.append({
                "id": t.id,
                "symbol": t.symbol,
                "bias": t.bias,
                "status": t.status,
                "exit_reason": t.exit_reason,
                "entry_price": float(t.entry_price),
                "exit_price": float(t.exit_price) if t.exit_price else None,
                "pnl_usd": float(t.pnl_usd) if t.pnl_usd else 0,
                "pnl_percent": float(t.pnl_percent) if t.pnl_percent else 0,
                "position_size_usd": float(t.position_size_usd) if t.position_size_usd else None,
                "mfe_pct": float(t.mfe_pct or 0),
                "mae_pct": float(t.mae_pct or 0),
                "regime_at_entry": t.regime_at_entry,
                "duration": duration,
                "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            })
        return rows
    finally:
        session.close()


@st.cache_data(ttl=120, show_spinner=False)
def get_portfolio_snapshots_cached(limit: int = 5000) -> list[dict]:
    """PortfolioSnapshot sorgusunu cache'le."""
    session = get_session()
    try:
        from db.models import PortfolioSnapshot
        snapshots = (
            session.query(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp)
            .limit(limit)
            .all()
        )
        return [
            {
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                "total_equity": float(s.total_equity),
                "cash_balance": float(s.cash_balance),
                "open_positions": int(s.open_positions),
                "unrealized_pnl": float(s.unrealized_pnl) if s.unrealized_pnl else 0,
                "max_drawdown_pct": float(s.max_drawdown_pct) if s.max_drawdown_pct else 0,
                "regime_distribution": s.regime_distribution,
            }
            for s in snapshots
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Analysis Library (TTL=60s)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60, show_spinner=False)
def get_analyses_cached(limit: int = 200) -> list[dict]:
    """ExternalAnalysis sorgusu."""
    session = get_session()
    try:
        from db.models import ExternalAnalysis
        analyses = (
            session.query(ExternalAnalysis)
            .order_by(ExternalAnalysis.added_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": a.id,
                "symbol": a.symbol,
                "source_type": a.source_type,
                "source_url": a.source_url,
                "author": a.author,
                "summary": a.summary,
                "tools_used": a.tools_used,
                "bias_claimed": a.bias_claimed,
                "target_price": float(a.target_price) if a.target_price else None,
                "stop_price": float(a.stop_price) if a.stop_price else None,
                "outcome": a.outcome or "PENDING",
                "outcome_notes": a.outcome_notes,
                "lesson_learned": a.lesson_learned,
                "added_at": a.added_at.strftime("%m-%d %H:%M") if a.added_at else "-",
            }
            for a in analyses
        ]
    finally:
        session.close()
