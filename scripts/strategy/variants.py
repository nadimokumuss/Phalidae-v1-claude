"""
Phalidae v2 - Strategy Variant Generator
Seed variants + random exploration + genetic refinement.
Each variant is a composition of indicators from 4 categories:
  - trend (King): 1-2 trend indicators
  - entry (Queen): 1-2 momentum indicators
  - volume (Soldier): 1 volume indicator
  - volatility (Optional): 0-1 volatility filter
"""

import random
import logging
from itertools import combinations

from db.engine import get_session
from db.models import StrategyVariant
from strategy.catalog import INDICATOR_CATALOG

logger = logging.getLogger("phalidae.variants")

# Proven high-weight indicators per category (for seed generation)
_TOP_TREND = ["EMA Ribbon", "MACD", "ADX/DI", "Supertrend", "Ichimoku", "SMA Cross", "Fiyat/EMA200", "PSAR"]
_TOP_ENTRY = ["RSI", "RSI Divergence", "Stochastic", "StochRSI", "Elder Ray", "CCI", "Connors RSI"]
_TOP_VOLUME = ["OBV", "CMF", "MFI", "Klinger"]
_TOP_VOLATILITY = ["Squeeze", "BB Position", "Choppiness"]


def _make_name(comp: dict) -> str:
    """Generate a human-readable strategy name from composition."""
    parts = []
    for key in ["trend", "entry", "volume", "volatility"]:
        items = comp.get(key, [])
        if items:
            abbrevs = [i.replace(" ", "")[:6] for i in items]
            parts.append("+".join(abbrevs))
    return " | ".join(parts)


def _variant_exists(session, composition: dict) -> bool:
    """Check if an identical composition already exists."""
    existing = session.query(StrategyVariant.id).filter(
        StrategyVariant.composition == composition
    ).first()
    return existing is not None


def generate_seed_variants() -> int:
    """
    Generate ~200-300 seed strategy variants from proven indicator combinations.
    Returns number of new variants created.
    """
    session = get_session()
    created = 0

    try:
        variants = []

        # Generate combinations: 2 trend x 2 entry x 1 volume (x optional volatility)
        for t_combo in combinations(_TOP_TREND, 2):
            for e_combo in combinations(_TOP_ENTRY, 2):
                for vol in _TOP_VOLUME:
                    comp = {
                        "trend": list(t_combo),
                        "entry": list(e_combo),
                        "volume": [vol],
                        "volatility": [],
                    }
                    variants.append(comp)

        # Add some with volatility filter
        for t_combo in combinations(_TOP_TREND[:5], 2):
            for e_combo in combinations(_TOP_ENTRY[:4], 1):
                for vol in _TOP_VOLUME[:2]:
                    for vola in _TOP_VOLATILITY:
                        comp = {
                            "trend": list(t_combo),
                            "entry": list(e_combo),
                            "volume": [vol],
                            "volatility": [vola],
                        }
                        variants.append(comp)

        # Add single-trend + single-entry simpler variants
        for t in _TOP_TREND:
            for e in _TOP_ENTRY[:5]:
                for vol in _TOP_VOLUME[:3]:
                    comp = {
                        "trend": [t],
                        "entry": [e],
                        "volume": [vol],
                        "volatility": [],
                    }
                    variants.append(comp)

        # Shuffle and cap at 300
        random.shuffle(variants)
        variants = variants[:300]

        # Threshold variations
        threshold_combos = [
            (0.3, 0.3, True),
            (0.4, 0.3, True),
            (0.3, 0.4, False),
            (0.2, 0.2, True),
        ]

        for comp in variants:
            if _variant_exists(session, comp):
                continue

            t_thresh, e_thresh, vol_req = random.choice(threshold_combos)
            name = _make_name(comp)

            session.add(StrategyVariant(
                name=name,
                composition=comp,
                trend_threshold=t_thresh,
                entry_threshold=e_thresh,
                volume_required=vol_req,
            ))
            created += 1

        session.commit()
        logger.info(f"Generated {created} seed variants")

    except Exception as e:
        session.rollback()
        logger.error(f"Seed generation error: {e}")
    finally:
        session.close()

    return created


def generate_random_variants(count: int = 20) -> int:
    """Generate random new variants for exploration."""
    session = get_session()
    created = 0

    all_trend = INDICATOR_CATALOG["trend"]
    all_entry = INDICATOR_CATALOG["entry"]
    all_volume = INDICATOR_CATALOG["volume"]
    all_volatility = INDICATOR_CATALOG["volatility"]

    try:
        for _ in range(count * 3):  # Try more to account for duplicates
            if created >= count:
                break

            n_trend = random.choice([1, 2])
            n_entry = random.choice([1, 2])
            use_volatility = random.random() < 0.3

            comp = {
                "trend": random.sample(all_trend, min(n_trend, len(all_trend))),
                "entry": random.sample(all_entry, min(n_entry, len(all_entry))),
                "volume": [random.choice(all_volume)],
                "volatility": [random.choice(all_volatility)] if use_volatility else [],
            }

            if _variant_exists(session, comp):
                continue

            session.add(StrategyVariant(
                name=_make_name(comp),
                composition=comp,
                trend_threshold=round(random.uniform(0.15, 0.5), 2),
                entry_threshold=round(random.uniform(0.15, 0.5), 2),
                volume_required=random.choice([True, False]),
            ))
            created += 1

        session.commit()
        logger.info(f"Generated {created} random variants")

    except Exception as e:
        session.rollback()
        logger.error(f"Random generation error: {e}")
    finally:
        session.close()

    return created


def generate_genetic_variants(top_n: int = 10, children: int = 15) -> int:
    """
    Crossover top-performing variants to create children.
    Takes components from two parents and mixes them.
    """
    session = get_session()
    created = 0

    try:
        # Get top performing variants (by average composite_score across symbols)
        from sqlalchemy import func
        from db.models import StrategyPerformance

        top_ids = (
            session.query(
                StrategyPerformance.strategy_variant_id,
                func.avg(StrategyPerformance.composite_score).label("avg_score")
            )
            .group_by(StrategyPerformance.strategy_variant_id)
            .having(func.avg(StrategyPerformance.composite_score) > 0)
            .order_by(func.avg(StrategyPerformance.composite_score).desc())
            .limit(top_n)
            .all()
        )

        if len(top_ids) < 2:
            logger.info("Not enough high-scoring variants for genetic crossover")
            return 0

        parents = []
        for row in top_ids:
            variant = session.query(StrategyVariant).get(row.strategy_variant_id)
            if variant:
                parents.append(variant.composition)

        for _ in range(children * 3):
            if created >= children:
                break

            p1, p2 = random.sample(parents, 2)

            # Crossover: take trend from one, entry from other, random volume/volatility
            child = {
                "trend": random.choice([p1, p2])["trend"],
                "entry": random.choice([p1, p2])["entry"],
                "volume": random.choice([p1, p2])["volume"],
                "volatility": random.choice([p1, p2])["volatility"],
            }

            # Mutation: 20% chance to swap one component
            if random.random() < 0.2:
                cat = random.choice(["trend", "entry", "volume"])
                pool = INDICATOR_CATALOG[cat]
                n = len(child[cat])
                child[cat] = random.sample(pool, min(n, len(pool)))

            if _variant_exists(session, child):
                continue

            session.add(StrategyVariant(
                name=_make_name(child),
                composition=child,
                trend_threshold=round(random.uniform(0.2, 0.45), 2),
                entry_threshold=round(random.uniform(0.2, 0.45), 2),
                volume_required=random.choice([True, False]),
            ))
            created += 1

        session.commit()
        logger.info(f"Generated {created} genetic variants")

    except Exception as e:
        session.rollback()
        logger.error(f"Genetic generation error: {e}")
    finally:
        session.close()

    return created
