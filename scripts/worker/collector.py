"""
Phalidae v2 - OHLCV Data Collector
Handles backfill + incremental collection for tracked symbols.
"""

import logging
import time
from datetime import datetime, timedelta

import ccxt
import pandas as pd
from sqlalchemy import func, text

from db.engine import get_session
from db.models import OHLCVData, TrackedSymbol, FundingData, MarketRegimeRecord

logger = logging.getLogger("phalidae.collector")

TIMEFRAMES = ["15m", "1h", "4h", "1d"]
BACKFILL_LIMITS = {
    "15m": 1000,   # ~10 days
    "1h": 1000,    # ~41 days
    "4h": 1000,    # ~166 days
    "1d": 1000,    # ~2.7 years
}

_exchange = None


def _get_exchange() -> ccxt.binanceusdm:
    global _exchange
    if _exchange is None:
        _exchange = ccxt.binanceusdm({"enableRateLimit": True})
    return _exchange


def refresh_tracked_symbols(top_n: int = 50):
    """Update tracked symbols list based on volume ranking."""
    exchange = _get_exchange()
    try:
        tickers = exchange.fetch_tickers()
    except Exception as e:
        logger.error(f"Failed to fetch tickers: {e}")
        return

    usdt_pairs = []
    for sym, t in tickers.items():
        if sym.endswith("/USDT:USDT"):
            usdt_pairs.append((sym, t.get("quoteVolume", 0) or 0))
    usdt_pairs.sort(key=lambda x: x[1], reverse=True)
    top_symbols = usdt_pairs[:top_n]

    session = get_session()
    try:
        # Deactivate all first
        session.execute(
            text("UPDATE tracked_symbols SET is_active = 0")
        )

        for rank, (sym, _vol) in enumerate(top_symbols, 1):
            existing = session.query(TrackedSymbol).filter_by(symbol=sym).first()
            if existing:
                existing.rank = rank
                existing.is_active = True
            else:
                session.add(TrackedSymbol(symbol=sym, rank=rank, is_active=True))

        session.commit()
        logger.info(f"Refreshed {len(top_symbols)} tracked symbols")
    except Exception as e:
        session.rollback()
        logger.error(f"Symbol refresh error: {e}")
    finally:
        session.close()


def _fetch_and_store(symbol: str, timeframe: str, limit: int = 200, since_ms: int = None):
    """Fetch OHLCV from Binance and store in DB. Returns number of new rows."""
    exchange = _get_exchange()
    try:
        bars = exchange.fetch_ohlcv(
            symbol, timeframe=timeframe, limit=limit, since=since_ms
        )
    except Exception as e:
        logger.warning(f"Fetch failed {symbol} {timeframe}: {e}")
        return 0

    if not bars:
        return 0

    session = get_session()
    new_count = 0
    try:
        for bar in bars:
            ts = datetime.utcfromtimestamp(bar[0] / 1000)
            exists = session.query(OHLCVData.id).filter_by(
                symbol=symbol, timeframe=timeframe, timestamp=ts
            ).first()
            if exists:
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
    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    if not symbol_list:
        logger.warning("No active symbols to collect")
        return

    total_new = 0
    for sym in symbol_list:
        for tf in TIMEFRAMES:
            new = _fetch_and_store(sym, tf, limit=50)
            total_new += new
        time.sleep(0.05)

    if total_new > 0:
        logger.info(f"Incremental: {total_new} new candles across {len(symbol_list)} symbols")


def initial_setup():
    """First-time setup: refresh symbols and backfill all."""
    logger.info("Starting initial data setup...")
    refresh_tracked_symbols(top_n=50)

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
    session = get_session()
    try:
        symbols = session.query(TrackedSymbol).filter_by(is_active=True).all()
        symbol_list = [s.symbol for s in symbols]
    finally:
        session.close()

    if not symbol_list:
        return

    exchange = _get_exchange()
    now = datetime.utcnow()
    # Round to nearest 15 min for dedup
    rounded_ts = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)

    collected = 0
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
                logger.debug(f"Regime save error for {sym}: {e}")
                session.rollback()
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"Regime data error for {sym}: {e}")

    if saved > 0:
        logger.info(f"Saved regime data for {saved} symbols")
