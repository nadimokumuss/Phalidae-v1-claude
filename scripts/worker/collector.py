"""
Phalidae v2 - OHLCV Data Collector
Handles backfill + incremental collection for tracked symbols.
Phase 1: Agent health logging + retry logic.
Phase 3: Deep backfill support.
"""

import logging
import time
from datetime import datetime, timedelta

import ccxt
import pandas as pd
from sqlalchemy import func

from db.engine import get_session
from db.models import OHLCVData, TrackedSymbol, FundingData, MarketRegimeRecord, AgentJob

logger = logging.getLogger("phalidae.collector")

TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]
BACKFILL_LIMITS = {
    "5m": 500,     # ~1.7 days
    "15m": 1000,   # ~10 days
    "30m": 1000,   # ~20 days
    "1h": 1000,    # ~41 days
    "4h": 1000,    # ~166 days
}

_exchange = None


def _get_exchange() -> ccxt.binanceusdm:
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binanceusdm({"enableRateLimit": True, "timeout": 15000})
    return _exchange


def _start_agent_job(job_name: str) -> int:
    """Create a RUNNING agent job record. Returns the job ID."""
    session = get_session()
    try:
        job = AgentJob(
            job_name=job_name,
            status="RUNNING",
            started_at=datetime.utcnow(),
        )
        session.add(job)
        session.commit()
        return job.id
    except Exception:
        session.rollback()
        return 0
    finally:
        session.close()


def _finish_agent_job(job_id: int, status: str, records: int = 0, error: str = None, context: dict = None):
    """Update an agent job with completion info."""
    if job_id == 0:
        return
    session = get_session()
    try:
        job = session.query(AgentJob).get(job_id)
        if job:
            job.status = status
            job.completed_at = datetime.utcnow()
            job.duration_sec = (job.completed_at - job.started_at).total_seconds()
            job.records_affected = records
            if error:
                job.error_message = str(error)[:2000]
            if context:
                job.context = context
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


# Leveraged token ve stablecoin sembollerini filtrele
_SYMBOL_BLACKLIST_TOKENS = {"UP", "DOWN", "BULL", "BEAR"}
_STABLECOIN_BASES = {"USDC", "TUSD", "DAI", "FDUSD", "USDP", "BUSD", "PYUSD", "AEUR", "EURI"}

MIN_QUOTE_VOLUME = 5_000_000    # $5M minimum 24h hacim
MAX_SPREAD_PCT = 0.15           # %0.15 max bid-ask spread


def _is_filtered_coin(symbol: str, ticker: dict) -> bool:
    """Filter out scam-prone and low-quality coins."""
    base = symbol.split("/")[0]

    # 1) Leveraged tokenları kaldır (BTCUP, ETHDOWN, vs.)
    for token in _SYMBOL_BLACKLIST_TOKENS:
        if base.endswith(token):
            return True

    # 2) Stablecoin perpetuallarını kaldır
    if base in _STABLECOIN_BASES:
        return True

    # 3) Minimum hacim kontrolü ($5M)
    volume = ticker.get("quoteVolume", 0) or 0
    if volume < MIN_QUOTE_VOLUME:
        return True

    # 4) Bid-ask spread kontrolü (<%0.15)
    bid = ticker.get("bid", 0) or 0
    ask = ticker.get("ask", 0) or 0
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = ((ask - bid) / mid) * 100
        if spread_pct > MAX_SPREAD_PCT:
            return True

    return False


def refresh_tracked_symbols(top_n: int = 0):
    """Update tracked symbols list. top_n=0 means all that pass filters.
    Auto-backfills newly added symbols so indicators have enough bars.
    """
    exchange = _get_exchange()
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return

    usdt_pairs = []
    filtered = 0
    for sym, t in tickers.items():
        if sym.endswith("/USDT:USDT"):
            if _is_filtered_coin(sym, t):
                filtered += 1
                continue
            usdt_pairs.append((sym, t.get("quoteVolume", 0) or 0))
    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    top_symbols = usdt_pairs[:top_n] if top_n > 0 else usdt_pairs

    new_symbols = []
    session = get_session()
    try:
        # Deactivate all first
        session.query(TrackedSymbol).update({TrackedSymbol.is_active: False})

        for rank, (sym, _vol) in enumerate(top_symbols, 1):
            existing = session.query(TrackedSymbol).filter_by(symbol=sym).first()
            if existing:
                existing.rank = rank
                existing.is_active = True
            else:
                session.add(TrackedSymbol(symbol=sym, rank=rank, is_active=True))
                new_symbols.append(sym)

        session.commit()
        logger.info(f"Refreshed {len(top_symbols)} tracked symbols ({len(new_symbols)} new, {filtered} filtered out)")
    except Exception as e:
        session.rollback()
        logger.error(f"Symbol refresh error: {e}")
        return
    finally:
        session.close()

    # Auto-backfill newly added symbols
    if new_symbols:
        logger.info(f"Backfilling {len(new_symbols)} new symbols...")
        for sym in new_symbols:
            try:
                backfill_symbol(sym)
            except Exception as e:
                logger.error(f"Backfill error for {sym}: {e}")


def _fetch_with_retry(symbol: str, timeframe: str, limit: int = 200, since_ms: int = None, retries: int = 3):
    """Fetch OHLCV with exponential backoff retry."""
    exchange = _get_exchange()
    for attempt in range(retries):
        try:
            bars = exchange.fetch_ohlcv(
                symbol, timeframe=timeframe, limit=limit, since=since_ms
            )
            return bars
        except Exception as e:
            if attempt < retries - 1:
                wait = (3 ** attempt)  # 1s, 3s, 9s
                logger.debug(f"Retry {attempt+1}/{retries} for {symbol} {timeframe}: {e} (wait {wait}s)")
                time.sleep(wait)
            else:
                logger.warning(f"Fetch failed {symbol} {timeframe} after {retries} retries: {e}")
                return None
    return None


def _fetch_and_store(symbol: str, timeframe: str, limit: int = 200, since_ms: int = None):
    """Fetch OHLCV from Binance and store in DB. Returns number of new rows."""
    bars = _fetch_with_retry(symbol, timeframe, limit, since_ms)
    if not bars:
        return 0

    session = get_session()
    new_count = 0
    try:
        # Bulk check: get all existing timestamps in one query
        all_ts = [datetime.utcfromtimestamp(bar[0] / 1000) for bar in bars]
        existing = set(
            row[0] for row in
            session.query(OHLCVData.timestamp)
            .filter(
                OHLCVData.symbol == symbol,
                OHLCVData.timeframe == timeframe,
                OHLCVData.timestamp.in_(all_ts),
            )
            .all()
        )

        for bar, ts in zip(bars, all_ts):
            if ts in existing:
                continue
            session.add(OHLCVData(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=bar[1],
                high=bar[2],
                low=bar[3],
                close=bar[4],
                volume=bar[5],
            ))
            new_count += 1

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Store error {symbol} {timeframe}: {e}")
    finally:
        session.close()

    return new_count


def backfill_symbol(symbol: str):
    """Backfill historical data for a symbol across all timeframes."""
    for tf in TIMEFRAMES:
        limit = BACKFILL_LIMITS.get(tf, 500)
        new = _fetch_and_store(symbol, tf, limit=limit)
        if new > 0:
            logger.info(f"Backfilled {new} candles for {symbol} {tf}")
        time.sleep(0.1)  # Gentle rate limiting

    # Update data_since
    session = get_session()
    try:
        earliest = session.query(func.min(OHLCVData.timestamp)).filter_by(
            symbol=symbol
        ).scalar()
        if earliest:
            tracked = session.query(TrackedSymbol).filter_by(symbol=symbol).first()
            if tracked:
                tracked.data_since = earliest
                session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def collect_incremental():
    """Incremental collection job: fetch latest candles for all active symbols."""
    job_id = _start_agent_job("collector")
    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    if not symbol_list:
        logger.warning("No active symbols — auto-refreshing symbol list...")
        try:
            refresh_tracked_symbols()
            session = get_session()
            try:
                symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
                symbol_list = [s.symbol for s in symbols]
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Auto-refresh failed: {e}")

        if not symbol_list:
            logger.error("Still no symbols after auto-refresh")
            _finish_agent_job(job_id, "SUCCESS", 0, context={"reason": "no_symbols"})
            return

    total_new = 0
    try:
        for sym in symbol_list:
            for tf in TIMEFRAMES:
                new = _fetch_and_store(sym, tf, limit=200)
                total_new += new
            time.sleep(0.05)

        if total_new > 0:
            logger.info(f"Incremental: {total_new} new candles across {len(symbol_list)} symbols")
        _finish_agent_job(job_id, "SUCCESS", total_new, context={"symbols": len(symbol_list)})
    except Exception as e:
        logger.error(f"Collector error: {e}")
        _finish_agent_job(job_id, "FAILED", total_new, error=str(e))


def initial_setup():
    """First-time setup: refresh symbols and backfill all."""
    logger.info("Starting initial data setup...")
    refresh_tracked_symbols()

    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    for i, sym in enumerate(symbol_list):
        logger.info(f"Backfilling {sym} ({i+1}/{len(symbol_list)})")
        backfill_symbol(sym)

    logger.info("Initial setup complete")


def get_ohlcv_df(symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Read OHLCV data from DB into a DataFrame."""
    session = get_session()
    try:
        rows = (
            session.query(OHLCVData)
            .filter_by(symbol=symbol, timeframe=timeframe)
            .order_by(OHLCVData.timestamp.desc())
            .limit(limit)
            .all()
        )
    finally:
        session.close()

    if not rows:
        return pd.DataFrame()

    data = [{
        "timestamp": r.timestamp,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
    } for r in reversed(rows)]

    return pd.DataFrame(data)


def collect_market_data():
    """
    Collect funding rate, open interest, and bid-ask spread for all active symbols.
    Called every 15 minutes by scheduler.
    """
    job_id = _start_agent_job("market_data")

    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    if not symbol_list:
        _finish_agent_job(job_id, "SUCCESS", 0)
        return

    exchange = _get_exchange()
    now = datetime.utcnow()
    # Round to nearest 15 min for dedup
    rounded_ts = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    collected = 0
    try:
        for sym in symbol_list:
            try:
                funding_rate = None
                open_interest = None
                spread_pct = None

                # Funding rate
                try:
                    fr = exchange.fetch_funding_rate(sym)
                    funding_rate = fr.get("fundingRate")
                except Exception as e:
                    logger.debug(f"Funding rate error for {sym}: {e}")

                # Open interest
                try:
                    oi = exchange.fetch_open_interest(sym)
                    open_interest = oi.get("openInterestValue") or oi.get("openInterestAmount")
                except Exception as e:
                    logger.debug(f"Open interest error for {sym}: {e}")

                # Bid-ask spread from ticker
                try:
                    ticker = exchange.fetch_ticker(sym)
                    bid = ticker.get("bid", 0) or 0
                    ask = ticker.get("ask", 0) or 0
                    if bid > 0 and ask > 0:
                        mid = (bid + ask) / 2
                        spread_pct = ((ask - bid) / mid) * 100
                except Exception as e:
                    logger.debug(f"Spread error for {sym}: {e}")

                if funding_rate is not None or open_interest is not None or spread_pct is not None:
                    session = get_session()
                    try:
                        # Upsert
                        existing = session.query(FundingData).filter_by(
                            symbol=sym, timestamp=rounded_ts
                        ).first()
                        if existing is None:
                            session.add(FundingData(
                                symbol=sym,
                                timestamp=rounded_ts,
                                funding_rate=funding_rate,
                                open_interest=open_interest,
                                spread_pct=spread_pct,
                            ))
                        else:
                            if funding_rate is not None:
                                existing.funding_rate = funding_rate
                            if open_interest is not None:
                                existing.open_interest = open_interest
                            if spread_pct is not None:
                                existing.spread_pct = spread_pct
                        session.commit()
                        collected += 1
                    except Exception:
                        session.rollback()
                    finally:
                        session.close()

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                logger.warning(f"Market data error for {sym}: {e}")

        if collected > 0:
            logger.info(f"Collected market data for {collected} symbols")
        _finish_agent_job(job_id, "SUCCESS", collected)
    except Exception as e:
        _finish_agent_job(job_id, "FAILED", collected, error=str(e))


def collect_regime_data():
    """
    Compute and store market regime for all active symbols (4h timeframe).
    Called alongside market data collection.
    """
    from indicators import compute_all_indicators
    from regime import get_regime_details

    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    if not symbol_list:
        return

    saved = 0
    for sym in symbol_list:
        try:
            df = get_ohlcv_df(sym, "4h", limit=300)
            if df.empty or len(df) < 50:
                continue

            df = compute_all_indicators(df)
            details = get_regime_details(df)

            ts = df["timestamp"].iloc[-1] if "timestamp" in df.columns else datetime.utcnow()

            session = get_session()
            try:
                existing = session.query(MarketRegimeRecord).filter_by(
                    symbol=sym, timeframe="4h", timestamp=ts
                ).first()
                if existing is None:
                    session.add(MarketRegimeRecord(
                        symbol=sym,
                        timeframe="4h",
                        timestamp=ts,
                        regime_label=details["regime"],
                        adx_value=details["adx"],
                        choppiness_value=details["choppiness"],
                        atr_percentile=details["atr_percentile"],
                        ema_slope=details["ema_slope"],
                    ))
                    session.commit()
                    saved += 1
            except Exception as e:
                logger.warning(f"Regime save error for {sym}: {e}")
                session.rollback()
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"Regime data error for {sym}: {e}")

    if saved > 0:
        logger.info(f"Saved regime data for {saved} symbols")


# ═══════════════════════════════════════════════════
# Phase 3: Deep backfill
# ═══════════════════════════════════════════════════

DEEP_BACKFILL_TARGETS = {
    "15m": 5000,   # ~52 days
    "1h": 5000,    # ~208 days
    "4h": 5000,    # ~833 days (~2.3 years)
    "1d": 2000,    # ~5.5 years
}

TF_MS = {
    "15m": 15 * 60 * 1000,
    "1h": 60 * 60 * 1000,
    "4h": 4 * 60 * 60 * 1000,
    "1d": 24 * 60 * 60 * 1000,
}


def deep_backfill(symbol: str, timeframe: str, target_candles: int = None):
    """
    Deep backfill: iteratively fetch older candles in 1000-candle batches
    until target_candles is reached.
    """
    if target_candles is None:
        target_candles = DEEP_BACKFILL_TARGETS.get(timeframe, 5000)

    job_id = _start_agent_job("deep_backfill")
    total_new = 0

    try:
        session = get_session()
        try:
            current_count = session.query(func.count(OHLCVData.id)).filter_by(
                symbol=symbol, timeframe=timeframe
            ).scalar() or 0
            earliest = session.query(func.min(OHLCVData.timestamp)).filter_by(
                symbol=symbol, timeframe=timeframe
            ).scalar()
        finally:
            session.close()

        if current_count >= target_candles:
            _finish_agent_job(job_id, "SUCCESS", 0, context={
                "symbol": symbol, "tf": timeframe, "reason": "already_sufficient",
                "current": current_count, "target": target_candles,
            })
            return

        remaining = target_candles - current_count
        batch_size = 1000
        tf_ms = TF_MS.get(timeframe, 4 * 60 * 60 * 1000)

        # Start from earliest known timestamp, or from now
        if earliest:
            since_ms = int(earliest.timestamp() * 1000) - (batch_size * tf_ms)
        else:
            since_ms = int(datetime.utcnow().timestamp() * 1000) - (batch_size * tf_ms)

        batches = 0
        while remaining > 0 and batches < 20:  # safety limit
            fetch_limit = min(batch_size, remaining)
            new = _fetch_and_store(symbol, timeframe, limit=fetch_limit, since_ms=since_ms)
            total_new += new
            batches += 1

            if new == 0:
                break  # No more data available

            remaining -= new
            since_ms -= (batch_size * tf_ms)  # Go further back
            time.sleep(1)  # Rate limit between batches

            logger.info(f"Deep backfill {symbol} {timeframe}: batch {batches}, +{new} candles (total new: {total_new})")

        _finish_agent_job(job_id, "SUCCESS", total_new, context={
            "symbol": symbol, "tf": timeframe, "batches": batches,
        })
    except Exception as e:
        logger.error(f"Deep backfill error for {symbol} {timeframe}: {e}")
        _finish_agent_job(job_id, "FAILED", total_new, error=str(e))


def deep_backfill_job():
    """
    Daily deep backfill job: processes 5 symbols per run (round-robin).
    After 10 days, all 50 symbols will have deep history.
    """
    job_id = _start_agent_job("deep_backfill_daily")
    total_new = 0

    try:
        session = get_session()
        try:
            # Get symbols ordered by least data first
            symbols = (
                session.query(TrackedSymbol)
                .filter_by(is_active=True)
                .order_by(TrackedSymbol.rank)
                .all()
            )
            symbol_list = [s.symbol for s in symbols]
        finally:
            session.close()

        if not symbol_list:
            _finish_agent_job(job_id, "SUCCESS", 0)
            return

        # Pick 5 symbols that have least data
        symbol_data_counts = []
        session = get_session()
        try:
            for sym in symbol_list:
                count = session.query(func.count(OHLCVData.id)).filter_by(
                    symbol=sym, timeframe="4h"
                ).scalar() or 0
                symbol_data_counts.append((sym, count))
        finally:
            session.close()

        symbol_data_counts.sort(key=lambda x: x[1])
        batch_symbols = [s[0] for s in symbol_data_counts[:5]]

        for sym in batch_symbols:
            for tf in ["4h", "1h"]:  # Prioritize 4h and 1h
                deep_backfill(sym, tf)
            time.sleep(2)

        logger.info(f"Deep backfill daily complete for {len(batch_symbols)} symbols")
        _finish_agent_job(job_id, "SUCCESS", total_new, context={
            "symbols": [s.replace("/USDT:USDT", "") for s in batch_symbols],
        })
    except Exception as e:
        logger.error(f"Deep backfill daily error: {e}")
        _finish_agent_job(job_id, "FAILED", total_new, error=str(e))


# ── Data Retention ─────────────────────────────────────────────────

# Retention rules: how many days to keep per timeframe
DATA_RETENTION_DAYS = {
    "5m": 3,
    "15m": 7,
    "30m": 14,
    "1h": 30,
    # 4h and 1d: keep forever (needed for backtesting)
}


def run_data_retention():
    """Delete old OHLCV data per timeframe retention rules. Also cleans secondary tables."""
    job_id = _start_agent_job("data_retention")
    total_deleted = 0
    try:
        session = get_session()
        try:
            now = datetime.utcnow()
            details = {}

            # Prune OHLCV by timeframe
            for tf, days in DATA_RETENTION_DAYS.items():
                cutoff = now - timedelta(days=days)
                deleted = session.query(OHLCVData).filter(
                    OHLCVData.timeframe == tf,
                    OHLCVData.timestamp < cutoff
                ).delete(synchronize_session=False)
                if deleted:
                    details[f"ohlcv_{tf}"] = deleted
                    total_deleted += deleted

            # Prune old agent_jobs (keep 7 days)
            deleted = session.query(AgentJob).filter(
                AgentJob.started_at < now - timedelta(days=7)
            ).delete(synchronize_session=False)
            if deleted:
                details["agent_jobs"] = deleted
                total_deleted += deleted

            # Prune old trade_snapshots (keep 30 days)
            from db.models import TradeSnapshot
            deleted = session.query(TradeSnapshot).filter(
                TradeSnapshot.timestamp < now - timedelta(days=30)
            ).delete(synchronize_session=False)
            if deleted:
                details["trade_snapshots"] = deleted
                total_deleted += deleted

            # Prune old news_events (keep 14 days)
            from db.models import NewsEvent
            deleted = session.query(NewsEvent).filter(
                NewsEvent.published_at < now - timedelta(days=14)
            ).delete(synchronize_session=False)
            if deleted:
                details["news_events"] = deleted
                total_deleted += deleted

            session.commit()
            logger.info(f"Data retention: deleted {total_deleted} rows: {details}")
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

        _finish_agent_job(job_id, "SUCCESS", total_deleted, context=details)
    except Exception as e:
        logger.error(f"Data retention error: {e}")
        _finish_agent_job(job_id, "FAILED", total_deleted, error=str(e))
