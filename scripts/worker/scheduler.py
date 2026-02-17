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


def start_scheduler():
    """Start the background scheduler with all jobs."""
    global _scheduler, _started

    if _started:
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)

    # OHLCV Collector - every 5 minutes
    _scheduler.add_job(
        _job_collect,
        trigger=IntervalTrigger(minutes=5),
        id="collector",
        name="OHLCV Collector",
        replace_existing=True,
        max_instances=1,
    )

    # Signal Analyzer - every 15 minutes
    _scheduler.add_job(
        _job_analyze,
        trigger=IntervalTrigger(minutes=15),
        id="analyzer",
        name="Signal Analyzer",
        replace_existing=True,
        max_instances=1,
    )

    # Trade Checker - every 5 minutes
    _scheduler.add_job(
        _job_check_trades,
        trigger=IntervalTrigger(minutes=5),
        id="trade_checker",
        name="Trade Checker",
        replace_existing=True,
        max_instances=1,
    )

    # Strategy Optimizer - every 6 hours
    _scheduler.add_job(
        _job_optimize,
        trigger=IntervalTrigger(hours=6),
        id="optimizer",
        name="Strategy Optimizer",
        replace_existing=True,
        max_instances=1,
    )

    # Market Data Collector - every 15 minutes
    _scheduler.add_job(
        _job_market_data,
        trigger=IntervalTrigger(minutes=15),
        id="market_data",
        name="Market Data Collector",
        replace_existing=True,
        max_instances=1,
    )

    # Symbol Refresh - every 24 hours
    _scheduler.add_job(
        _job_refresh_symbols,
        trigger=IntervalTrigger(hours=24),
        id="symbol_refresh",
        name="Symbol Refresh",
        replace_existing=True,
        max_instances=1,
    )

    # Phase 1: Quick optimization - runs once, 3 minutes after startup
    _scheduler.add_job(
        _job_quick_optimize,
        trigger=DateTrigger(run_date=datetime.utcnow() + timedelta(minutes=3)),
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
    )

    # Phase 2: Portfolio Snapshot - every 5 minutes (with trade checker)
    _scheduler.add_job(
        _job_portfolio_snapshot,
        trigger=IntervalTrigger(minutes=5),
        id="portfolio_snapshot",
        name="Portfolio Snapshot",
        replace_existing=True,
        max_instances=1,
    )

    _scheduler.start()
    _started = True
    logger.info("Scheduler started with 10 jobs")
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
