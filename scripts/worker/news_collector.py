"""
Phalidae v2 - News Collector (Phase 4)
Fetches crypto news from CryptoPanic API.
"""

import os
import logging
from datetime import datetime, timedelta

import requests

from db.engine import get_session
from db.models import NewsEvent
from worker.collector import _start_agent_job, _finish_agent_job

logger = logging.getLogger("phalidae.news")

CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"

# Map common crypto symbols to CryptoPanic currency codes
SYMBOL_MAP = {
    "BTC/USDT:USDT": "BTC",
    "ETH/USDT:USDT": "ETH",
    "SOL/USDT:USDT": "SOL",
    "XRP/USDT:USDT": "XRP",
    "DOGE/USDT:USDT": "DOGE",
    "ADA/USDT:USDT": "ADA",
    "AVAX/USDT:USDT": "AVAX",
    "DOT/USDT:USDT": "DOT",
    "LINK/USDT:USDT": "LINK",
    "MATIC/USDT:USDT": "MATIC",
}


def collect_news():
    """Fetch latest news from CryptoPanic. Called every 15 minutes."""
    api_key = os.environ.get("CRYPTOPANIC_API_KEY", "")
    if not api_key:
        logger.info("CRYPTOPANIC_API_KEY not set, skipping news collection")
        return

    # Quick availability check before starting agent job
    try:
        probe = requests.head(CRYPTOPANIC_URL, timeout=5)
        if probe.status_code == 404:
            logger.info("CryptoPanic API unavailable (404), skipping")
            return
    except requests.RequestException:
        pass  # Network error, try full request anyway

    job_id = _start_agent_job("news_collector")
    collected = 0

    try:
        params = {
            "auth_token": api_key,
            "public": "true",
            "kind": "news",
        }

        try:
            resp = requests.get(CRYPTOPANIC_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"CryptoPanic HTTP {resp.status_code}: {resp.text[:200]}")
            # Fallback: try pro endpoint if free fails
            if "free" in CRYPTOPANIC_URL:
                try:
                    pro_url = CRYPTOPANIC_URL.replace("/free/", "/")
                    resp = requests.get(pro_url, params=params, timeout=15)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception:
                    _finish_agent_job(job_id, "FAILED", 0, error=f"Both endpoints failed: {e}")
                    return
            else:
                _finish_agent_job(job_id, "FAILED", 0, error=str(e))
                return
        except Exception as e:
            logger.error(f"CryptoPanic request error: {e}")
            _finish_agent_job(job_id, "FAILED", 0, error=str(e))
            return

        results = data.get("results", [])

        session = get_session()
        try:
            for item in results:
                ext_id = str(item.get("id", ""))
                if not ext_id:
                    continue

                # Check dedup
                existing = session.query(NewsEvent).filter_by(
                    source="cryptopanic", external_id=ext_id
                ).first()
                if existing:
                    continue

                # Extract symbols
                currencies = item.get("currencies", []) or []
                symbols = [c.get("code", "") for c in currencies if c.get("code")]

                # Sentiment from votes
                votes = item.get("votes", {}) or {}
                pos = votes.get("positive", 0) or 0
                neg = votes.get("negative", 0) or 0
                total_votes = pos + neg

                if total_votes > 0:
                    if pos > neg * 2:
                        sentiment = "bullish"
                    elif neg > pos * 2:
                        sentiment = "bearish"
                    else:
                        sentiment = "neutral"
                    impact_score = round(neg / total_votes, 3) if total_votes > 0 else 0.0
                else:
                    sentiment = "neutral"
                    impact_score = 0.0

                # Parse published date
                pub_str = item.get("published_at", "")
                try:
                    published_at = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(tzinfo=None)
                except (ValueError, AttributeError):
                    published_at = datetime.utcnow()

                session.add(NewsEvent(
                    source="cryptopanic",
                    external_id=ext_id,
                    title=item.get("title", "")[:500],
                    url=item.get("url", "")[:500],
                    published_at=published_at,
                    symbols=symbols if symbols else None,
                    sentiment=sentiment,
                    impact_score=impact_score,
                    votes_positive=pos,
                    votes_negative=neg,
                    is_important=item.get("important", False),
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
            logger.info(f"Collected {collected} news items")
        _finish_agent_job(job_id, "SUCCESS", collected)

    except Exception as e:
        logger.error(f"News collection error: {e}")
        _finish_agent_job(job_id, "FAILED", collected, error=str(e))


def get_news_risk_score(symbol: str) -> float:
    """
    Calculate news risk score for a symbol (0.0 to 1.0).
    Based on last 24h of news sentiment.
    0.0 = no risk, 1.0 = high risk (many bearish news)
    """
    # Extract currency code
    clean = symbol.replace("/USDT:USDT", "")

    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=24)

        # Get news mentioning this symbol
        news = (
            session.query(NewsEvent)
            .filter(
                NewsEvent.published_at >= since,
            )
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
