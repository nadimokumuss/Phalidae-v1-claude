"""
Phalidae v2 - News Collector (Phase 4)
Fetches crypto news from CryptoCompare API (primary) with CryptoPanic fallback.
"""

import os
import logging
from datetime import datetime, timedelta

import requests

from db.engine import get_session
from db.models import NewsEvent
from worker.collector import _start_agent_job, _finish_agent_job

logger = logging.getLogger("phalidae.news")

CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/v2/news/"

# Known crypto ticker symbols for filtering categories
KNOWN_TICKERS = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT", "LINK",
    "MATIC", "ATOM", "UNI", "AAVE", "LTC", "BCH", "FIL", "NEAR", "APT",
    "ARB", "OP", "INJ", "SEI", "SUI", "TIA", "PEPE", "WIF", "BONK",
    "SHIB", "BNB", "TRX", "TON", "FTM", "ALGO", "HBAR", "VET", "SAND",
    "MANA", "AXS", "CRV", "MKR", "COMP", "SNX", "RUNE", "TAO",
}


def collect_news():
    """Fetch latest news from CryptoCompare. Called every 15 minutes."""
    job_id = _start_agent_job("news_collector")
    collected = 0

    try:
        params = {
            "lang": "EN",
            "excludeCategories": "Sponsored",
        }

        # Optional: add API key for higher rate limits
        api_key = os.environ.get("CRYPTOCOMPARE_API_KEY", "")
        if api_key:
            params["api_key"] = api_key

        try:
            resp = requests.get(CRYPTOCOMPARE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"CryptoCompare request error: {e}")
            _finish_agent_job(job_id, "FAILED", 0, error=str(e))
            return

        if data.get("Type") != 100:
            msg = data.get("Message", "Unknown error")
            _finish_agent_job(job_id, "FAILED", 0, error=f"API error: {msg}")
            return

        results = data.get("Data", [])

        session = get_session()
        try:
            for item in results:
                ext_id = str(item.get("id", ""))
                if not ext_id:
                    continue

                # Dedup check
                existing = session.query(NewsEvent).filter_by(
                    source="cryptocompare", external_id=ext_id
                ).first()
                if existing:
                    continue

                # Extract symbols from pipe-delimited categories
                categories_str = item.get("categories", "")
                raw_cats = [c.strip() for c in categories_str.split("|") if c.strip()]
                symbols = [c for c in raw_cats if c in KNOWN_TICKERS]

                # Sentiment from votes
                pos = int(item.get("upvotes", 0) or 0)
                neg = int(item.get("downvotes", 0) or 0)
                total_votes = pos + neg

                if total_votes > 0:
                    if pos > neg * 2:
                        sentiment = "bullish"
                    elif neg > pos * 2:
                        sentiment = "bearish"
                    else:
                        sentiment = "neutral"
                    # impact_score = negativity ratio (neg/total), used as risk indicator
                    # Higher value = more negative votes = higher risk. Name kept for DB compatibility.
                    impact_score = round(neg / total_votes, 3)
                else:
                    sentiment = "neutral"
                    impact_score = 0.0

                # Parse published date (unix timestamp)
                pub_ts = item.get("published_on", 0)
                try:
                    published_at = datetime.utcfromtimestamp(int(pub_ts))
                except (ValueError, OSError):
                    published_at = datetime.utcnow()

                # Importance: has many votes or mentions major coins
                major_coins = {"BTC", "ETH", "SOL", "XRP"}
                is_important = total_votes > 5 or bool(major_coins & set(symbols))

                session.add(NewsEvent(
                    source="cryptocompare",
                    external_id=ext_id,
                    title=item.get("title", "")[:500],
                    url=item.get("url", "")[:500],
                    published_at=published_at,
                    symbols=symbols if symbols else None,
                    sentiment=sentiment,
                    impact_score=impact_score,
                    votes_positive=pos,
                    votes_negative=neg,
                    is_important=is_important,
                    fetched_at=datetime.utcnow(),
                ))
                collected += 1

            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"News save error: {e}")
        finally:
            session.close()

        if collected > 0:
            logger.info(f"Collected {collected} news items from CryptoCompare")
        _finish_agent_job(job_id, "SUCCESS", collected)

    except Exception as e:
        logger.error(f"News collection error: {e}")
        _finish_agent_job(job_id, "FAILED", collected, error=str(e))


def backfill_news(pages: int = 5):
    """Fetch multiple pages of historical news for cold-start using lTs pagination."""
    job_id = _start_agent_job("news_backfill")
    collected = 0
    last_ts = None

    try:
        api_key = os.environ.get("CRYPTOCOMPARE_API_KEY", "")

        for page in range(pages):
            params = {
                "lang": "EN",
                "excludeCategories": "Sponsored",
            }
            if api_key:
                params["api_key"] = api_key
            if last_ts:
                params["lTs"] = last_ts

            try:
                resp = requests.get(CRYPTOCOMPARE_URL, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"News backfill page {page} request error: {e}")
                break

            if data.get("Type") != 100:
                break

            results = data.get("Data", [])
            if not results:
                break

            # Track oldest timestamp for next page
            oldest_ts = None
            session = get_session()
            try:
                for item in results:
                    ext_id = str(item.get("id", ""))
                    if not ext_id:
                        continue

                    pub_ts = item.get("published_on", 0)
                    if oldest_ts is None or pub_ts < oldest_ts:
                        oldest_ts = pub_ts

                    # Dedup check
                    existing = session.query(NewsEvent).filter_by(
                        source="cryptocompare", external_id=ext_id
                    ).first()
                    if existing:
                        continue

                    categories_str = item.get("categories", "")
                    raw_cats = [c.strip() for c in categories_str.split("|") if c.strip()]
                    symbols = [c for c in raw_cats if c in KNOWN_TICKERS]

                    pos = int(item.get("upvotes", 0) or 0)
                    neg = int(item.get("downvotes", 0) or 0)
                    total_votes = pos + neg

                    if total_votes > 0:
                        if pos > neg * 2:
                            sentiment = "bullish"
                        elif neg > pos * 2:
                            sentiment = "bearish"
                        else:
                            sentiment = "neutral"
                        # impact_score = negativity ratio (neg/total), used as risk indicator
                        impact_score = round(neg / total_votes, 3)
                    else:
                        sentiment = "neutral"
                        impact_score = 0.0

                    try:
                        published_at = datetime.utcfromtimestamp(int(pub_ts))
                    except (ValueError, OSError):
                        published_at = datetime.utcnow()

                    major_coins = {"BTC", "ETH", "SOL", "XRP"}
                    is_important = total_votes > 5 or bool(major_coins & set(symbols))

                    session.add(NewsEvent(
                        source="cryptocompare",
                        external_id=ext_id,
                        title=item.get("title", "")[:500],
                        url=item.get("url", "")[:500],
                        published_at=published_at,
                        symbols=symbols if symbols else None,
                        sentiment=sentiment,
                        impact_score=impact_score,
                        votes_positive=pos,
                        votes_negative=neg,
                        is_important=is_important,
                        fetched_at=datetime.utcnow(),
                    ))
                    collected += 1

                session.commit()
            except Exception as e:
                session.rollback()
                logger.error(f"News backfill page {page} save error: {e}")
            finally:
                session.close()

            # Set lTs for next page
            if oldest_ts:
                last_ts = oldest_ts
            else:
                break

        if collected > 0:
            logger.info(f"News backfill: collected {collected} articles over {pages} pages")
        _finish_agent_job(job_id, "SUCCESS", collected)

    except Exception as e:
        logger.error(f"News backfill error: {e}")
        _finish_agent_job(job_id, "FAILED", collected, error=str(e))


def get_news_risk_score(symbol: str) -> float:
    """
    Calculate news risk score for a symbol (0.0 to 1.0).
    Based on last 24h of news sentiment.
    0.0 = no risk, 1.0 = high risk (many bearish news)
    """
    clean = symbol.replace("/USDT:USDT", "")

    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=24)

        news = (
            session.query(NewsEvent)
            .filter(NewsEvent.published_at >= since)
            .all()
        )

        if not news:
            return 0.0

        # Filter for this symbol
        relevant = []
        for n in news:
            if n.symbols and clean in n.symbols:
                relevant.append(n)

        if not relevant:
            return 0.0

        # Weighted sentiment calculation
        total_weight = 0
        negative_weight = 0
        for n in relevant:
            weight = 1.0
            if n.is_important:
                weight = 3.0
            total_votes = (n.votes_positive or 0) + (n.votes_negative or 0)
            if total_votes > 10:
                weight *= 1.5

            total_weight += weight
            if n.sentiment == "bearish":
                negative_weight += weight
            elif n.sentiment == "neutral":
                negative_weight += weight * 0.3

        risk = negative_weight / total_weight if total_weight > 0 else 0.0
        return round(min(risk, 1.0), 3)

    finally:
        session.close()


def get_todays_events(limit: int = 20) -> list[dict]:
    """Get today's most important news for dashboard."""
    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=24)
        news = (
            session.query(NewsEvent)
            .filter(NewsEvent.published_at >= since)
            .order_by(NewsEvent.is_important.desc(), NewsEvent.published_at.desc())
            .limit(limit)
            .all()
        )

        return [{
            "title": n.title,
            "symbols": n.symbols or [],
            "sentiment": n.sentiment,
            "impact_score": n.impact_score,
            "published_at": n.published_at.strftime("%H:%M") if n.published_at else "",
            "url": n.url,
            "is_important": n.is_important,
        } for n in news]

    finally:
        session.close()
