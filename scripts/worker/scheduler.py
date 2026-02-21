"""
Phalidae v2 - APScheduler Setup
Background jobs running in a daemon thread alongside Streamlit.
Phase 1: Quick optimize job.
Phase 3: Deep backfill daily job.
Phase 4: News collector job.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("phalidae.scheduler")

_scheduler = None
_started = False


def _job_collect():
    from worker.collector import collect_incremental
    try:
        collect_incremental()
    except Exception as e:
        logger.error(f"Collector job error: {e}")


def _job_analyze():
    from worker.analyzer import run_analysis_cycle
    try:
        run_analysis_cycle()
    except Exception as e:
        logger.error(f"Analyzer job error: {e}")


def _job_check_trades():
    from worker.analyzer import check_open_trades
    try:
        check_open_trades()
    except Exception as e:
        logger.error(f"Trade checker job error: {e}")


def _job_optimize():
    from strategy.optimizer import run_optimization
    try:
        run_optimization()
    except Exception as e:
        logger.error(f"Optimizer job error: {e}")


def _job_quick_optimize():
    from strategy.optimizer import run_quick_optimization
    try:
        run_quick_optimization(top_symbols=10, top_variants=50)
    except Exception as e:
        logger.error(f"Quick optimizer job error: {e}")


def _job_market_data():
    from worker.collector import collect_market_data, collect_regime_data
    try:
        collect_market_data()
        collect_regime_data()
    except Exception as e:
        logger.error(f"Market data job error: {e}")


def _job_refresh_symbols():
    from worker.collector import refresh_tracked_symbols
    try:
        refresh_tracked_symbols(top_n=50)
    except Exception as e:
        logger.error(f"Symbol refresh job error: {e}")


def _job_deep_backfill():
    from worker.collector import deep_backfill_job
    try:
        deep_backfill_job()
    except Exception as e:
        logger.error(f"Deep backfill job error: {e}")


def _job_collect_news():
    try:
        from worker.news_collector import collect_news
        collect_news()
    except ImportError:
        pass  # News module not available yet (Phase 4)
    except Exception as e:
        logger.error(f"News collector job error: {e}")


def _job_portfolio_snapshot():
    try:
        from paper_trader.portfolio import record_portfolio_snapshot
        record_portfolio_snapshot()
    except Exception as e:
        logger.error(f"Portfolio snapshot job error: {e}")


def _job_backfill_underfilled():
    """Backfill symbols with insufficient data. Runs as separate job to not block bootstrap."""
    from worker.collector import _start_agent_job, _finish_agent_job, backfill_symbol
    job_id = _start_agent_job("backfill_underfilled")
    filled = 0
    try:
        from db.engine import get_session
        from db.models import TrackedSymbol, OHLCVData
        from sqlalchemy import func
        s = get_session()
        try:
            bar_counts = (
                s.query(TrackedSymbol.symbol, func.count(OHLCVData.id))
                .outerjoin(OHLCVData, (TrackedSymbol.symbol == OHLCVData.symbol) & (OHLCVData.timeframe == '4h'))
                .filter(TrackedSymbol.is_active.is_(True))
                .group_by(TrackedSymbol.symbol)
                .all()
            )
        finally:
            s.close()
        underfilled = [sym for sym, cnt in bar_counts if cnt < 200]
        if not underfilled:
            logger.info("Backfill: all symbols have sufficient data")
            _finish_agent_job(job_id, "SUCCESS", 0, context={"message": "all_filled"})
            return

        logger.info(f"Backfill: {len(underfilled)} symbols need data...")
        for sym in underfilled:
            try:
                backfill_symbol(sym)
                filled += 1
                logger.info(f"Backfill: {filled}/{len(underfilled)} done ({sym})")
            except Exception as e:
                logger.error(f"Backfill error for {sym}: {e}")

        _finish_agent_job(job_id, "SUCCESS", filled, context={"total": len(underfilled)})
    except Exception as e:
        logger.error(f"Backfill job error: {e}")
        _finish_agent_job(job_id, "FAILED", filled, error=str(e))


def _bootstrap():
    """Run once at startup: ensure symbols exist, then trigger first collection."""
    logger.info("Bootstrap: starting initial data pipeline...")
    try:
        # Step 1: Ensure tracked symbols exist
        from db.engine import get_session
        from db.models import TrackedSymbol
        session = get_session()
        try:
            count = session.query(TrackedSymbol).filter_by(is_active=True).count()
        finally:
            session.close()

        if count == 0:
            logger.info("Bootstrap: no symbols found, running refresh_tracked_symbols...")
            _job_refresh_symbols()

        # Step 2: Run first collection immediately
        logger.info("Bootstrap: running initial collector...")
        _job_collect()

        # Step 3: Run market data + regime
        logger.info("Bootstrap: running initial market data...")
        _job_market_data()

        # Step 4: Run news collector
        logger.info("Bootstrap: running initial news collection...")
        _job_collect_news()

        # Step 5: News backfill if table is nearly empty
        try:
            from db.models import NewsEvent
            s = get_session()
            try:
                news_count = s.query(NewsEvent).count()
            finally:
                s.close()
        except Exception:
            news_count = 0

        if news_count < 50:
            logger.info(f"Bootstrap: news table has {news_count} records, running backfill...")
            try:
                from worker.news_collector import backfill_news
                backfill_news(pages=5)
            except Exception as e:
                logger.error(f"Bootstrap news backfill error: {e}")

        logger.info("Bootstrap: initial pipeline complete")
    except Exception as e:
        logger.error(f"Bootstrap error: {e}")


def start_scheduler():
    """Start the background scheduler with all jobs."""
    global _scheduler, _started

    if _started:
        return _scheduler

    # Clean up stale RUNNING jobs from previous pod restart
    try:
        from db.engine import get_session
        from db.models import AgentJob
        session = get_session()
        try:
            stale_jobs = session.query(AgentJob).filter(AgentJob.status == "RUNNING").all()
            if stale_jobs:
                for job in stale_jobs:
                    job.status = "FAILED"
                    job.error_message = "Pod restart - stale job cleaned up"
                    job.completed_at = datetime.utcnow()
                session.commit()
                logger.info(f"Cleaned up {len(stale_jobs)} stale RUNNING jobs from previous restart")
        except Exception as e:
            session.rollback()
            logger.error(f"Stale job cleanup error: {e}")
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Stale job cleanup init error: {e}")

    _scheduler = BackgroundScheduler(daemon=True)

    now = datetime.utcnow()

    # Symbol Refresh - every 24 hours, start immediately
    _scheduler.add_job(
        _job_refresh_symbols,
        trigger=IntervalTrigger(hours=24),
        id="symbol_refresh",
        name="Symbol Refresh",
        replace_existing=True,
        max_instances=1,
        next_run_time=now,  # Run immediately
    )

    # OHLCV Collector - every 5 minutes
    _scheduler.add_job(
        _job_collect,
        trigger=IntervalTrigger(minutes=5),
        id="collector",
        name="OHLCV Collector",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(seconds=30),  # 30s after start (after symbols loaded)
    )

    # Market Data Collector - every 15 minutes
    _scheduler.add_job(
        _job_market_data,
        trigger=IntervalTrigger(minutes=15),
        id="market_data",
        name="Market Data Collector",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(seconds=45),  # 45s after start
    )

    # Signal Analyzer - every 5 minutes
    _scheduler.add_job(
        _job_analyze,
        trigger=IntervalTrigger(minutes=5),
        id="analyzer",
        name="Signal Analyzer",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(minutes=2),  # 2min after start (needs data)
    )

    # Trade Checker - every 5 minutes
    _scheduler.add_job(
        _job_check_trades,
        trigger=IntervalTrigger(minutes=5),
        id="trade_checker",
        name="Trade Checker",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(minutes=2, seconds=30),
    )

    # Strategy Optimizer - every 6 hours
    _scheduler.add_job(
        _job_optimize,
        trigger=IntervalTrigger(hours=6),
        id="optimizer",
        name="Strategy Optimizer",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(minutes=10),  # 10min after start (needs data)
    )

    # Phase 1: Quick optimization - runs once, 3 minutes after startup
    _scheduler.add_job(
        _job_quick_optimize,
        trigger=DateTrigger(run_date=now + timedelta(minutes=3)),
        id="quick_optimizer",
        name="Quick Optimizer (startup)",
        replace_existing=True,
        max_instances=1,
    )

    # Phase 3: Deep Backfill - daily at 02:00 UTC
    _scheduler.add_job(
        _job_deep_backfill,
        trigger=CronTrigger(hour=2, minute=0),
        id="deep_backfill",
        name="Deep Backfill Daily",
        replace_existing=True,
        max_instances=1,
    )

    # Phase 4: News Collector - every 15 minutes
    _scheduler.add_job(
        _job_collect_news,
        trigger=IntervalTrigger(minutes=15),
        id="news_collector",
        name="News Collector",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(seconds=15),  # Run quickly
    )

    # Phase 2: Portfolio Snapshot - every 5 minutes
    _scheduler.add_job(
        _job_portfolio_snapshot,
        trigger=IntervalTrigger(minutes=5),
        id="portfolio_snapshot",
        name="Portfolio Snapshot",
        replace_existing=True,
        max_instances=1,
        next_run_time=now + timedelta(minutes=1),
    )

    # Run bootstrap as a one-time job (runs immediately in background thread)
    _scheduler.add_job(
        _bootstrap,
        trigger=DateTrigger(run_date=now + timedelta(seconds=5)),
        id="bootstrap",
        name="Bootstrap Pipeline",
        replace_existing=True,
        max_instances=1,
    )

    # Backfill under-filled symbols - runs once, 1 minute after startup
    # Separate from bootstrap so it doesn't block the initial pipeline
    _scheduler.add_job(
        _job_backfill_underfilled,
        trigger=DateTrigger(run_date=now + timedelta(minutes=1)),
        id="backfill_underfilled",
        name="Backfill Under-filled Symbols",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    _started = True
    logger.info("Scheduler started with 12 jobs (bootstrap + backfill + 10 recurring)")
    return _scheduler


def get_scheduler_status() -> dict:
    """Return status of all scheduled jobs."""
    if _scheduler is None:
        return {"running": False, "jobs": []}

    jobs = []
    for job in _scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
        })

    return {
        "running": _scheduler.running if _scheduler else False,
        "jobs": jobs,
    }
