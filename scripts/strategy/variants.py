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


def _random_weights_perturbation() -> dict | None:
    """30% chance to generate random indicator weight perturbations."""
    if random.random() >= 0.3:
        return None
    from indicators import INDICATOR_WEIGHTS
    weights = {}
    for name, base_w in INDICATOR_WEIGHTS.items():
        weights[name] = round(max(0.1, min(3.0, base_w * random.uniform(0.5, 2.0))), 2)
    return weights


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
                custom_weights=_random_weights_perturbation(),
                tp_atr_mult=round(random.uniform(1.5, 4.0), 2),
                sl_atr_mult=round(random.uniform(1.0, 3.0), 2),
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


def _blend_weights(w1: dict | None, w2: dict | None) -> dict | None:
    """Blend two parent weight dicts with noise. Returns None if both parents are None."""
    if w1 is None and w2 is None:
        return None
    from indicators import INDICATOR_WEIGHTS
    base = dict(INDICATOR_WEIGHTS)
    p1 = w1 or base
    p2 = w2 or base

    child_w = {}
    all_keys = set(list(p1.keys()) + list(p2.keys()))
    for key in all_keys:
        v1 = p1.get(key, base.get(key, 1.0))
        v2 = p2.get(key, base.get(key, 1.0))
        blended = random.uniform(min(v1, v2), max(v1, v2)) * random.uniform(0.9, 1.1)
        child_w[key] = round(max(0.1, min(3.0, blended)), 2)

    # 15% mutation: randomize one weight completely
    if random.random() < 0.15 and child_w:
        mutate_key = random.choice(list(child_w.keys()))
        child_w[mutate_key] = round(random.uniform(0.1, 3.0), 2)

    return child_w


def _blend_tp_sl(tp1: float, tp2: float, sl1: float, sl2: float) -> tuple[float, float]:
    """Blend two parent TP/SL multipliers with noise."""
    child_tp = random.uniform(min(tp1, tp2), max(tp1, tp2)) * random.uniform(0.95, 1.05)
    child_sl = random.uniform(min(sl1, sl2), max(sl1, sl2)) * random.uniform(0.95, 1.05)

    # 10% aggressive mutation: completely random value
    if random.random() < 0.1:
        child_tp = random.uniform(1.5, 4.0)
    if random.random() < 0.1:
        child_sl = random.uniform(1.0, 3.0)

    child_tp = round(max(1.5, min(4.0, child_tp)), 2)
    child_sl = round(max(1.0, min(3.0, child_sl)), 2)
    return child_tp, child_sl


def generate_genetic_variants(top_n: int = 10, children: int = 15) -> int:
    """
    Crossover top-performing variants to create children.
    Takes components from two parents and mixes them.
    Also evolves custom_weights, tp_atr_mult, and sl_atr_mult.
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

        # Load full StrategyVariant objects (not just composition dicts)
        parents = []
        for row in top_ids:
            variant = session.query(StrategyVariant).get(row.strategy_variant_id)
            if variant:
                parents.append(variant)

        if len(parents) < 2:
            return 0

        for _ in range(children * 3):
            if created >= children:
                break

            p1, p2 = random.sample(parents, 2)
            c1, c2 = p1.composition, p2.composition

            # Crossover: take trend from one, entry from other, random volume/volatility
            child_comp = {
                "trend": random.choice([c1, c2])["trend"],
                "entry": random.choice([c1, c2])["entry"],
                "volume": random.choice([c1, c2])["volume"],
                "volatility": random.choice([c1, c2])["volatility"],
            }

            # Mutation: 20% chance to swap one component
            if random.random() < 0.2:
                cat = random.choice(["trend", "entry", "volume"])
                pool = INDICATOR_CATALOG[cat]
                n = len(child_comp[cat])
                child_comp[cat] = random.sample(pool, min(n, len(pool)))

            if _variant_exists(session, child_comp):
                continue

            # Evolve custom weights from parents
            child_weights = _blend_weights(p1.custom_weights, p2.custom_weights)

            # Evolve TP/SL multipliers from parents
            child_tp, child_sl = _blend_tp_sl(
                p1.tp_atr_mult or 2.5, p2.tp_atr_mult or 2.5,
                p1.sl_atr_mult or 1.5, p2.sl_atr_mult or 1.5,
            )

            session.add(StrategyVariant(
                name=_make_name(child_comp),
                composition=child_comp,
                trend_threshold=round(random.uniform(0.2, 0.45), 2),
                entry_threshold=round(random.uniform(0.2, 0.45), 2),
                volume_required=random.choice([True, False]),
                custom_weights=child_weights,
                tp_atr_mult=child_tp,
                sl_atr_mult=child_sl,
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
