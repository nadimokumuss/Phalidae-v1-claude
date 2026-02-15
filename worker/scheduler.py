"""
Phalidae v2 - APScheduler Setup
Background jobs running in a daemon thread alongside Streamlit.
"""

import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

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

    _scheduler.start()
    _started = True
    logger.info("Scheduler started with 6 jobs")
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
