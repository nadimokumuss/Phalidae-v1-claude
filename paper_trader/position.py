"""
Phalidae v2 - Position P&L Calculation & Reasoning Generator
"""

import json

FEE_RATE = 0.0004       # Taker fee per side (%0.04)
SLIPPAGE_RATE = 0.0002  # Estimated slippage per side (%0.02)


def calculate_pnl(
    entry_price: float,
    current_price: float,
    bias: str,
    leverage: float = 5.0,
    position_size_usd: float = 1000.0,
    include_fees: bool = False,
) -> dict:
    """
    Calculate P&L for a position.
    Returns: pnl_usd, pnl_percent, liquidation_price
    """
    if entry_price <= 0:
        return {"pnl_usd": 0, "pnl_percent": 0, "liquidation_price": 0}

    if bias == "LONG":
        pnl_pct = ((current_price - entry_price) / entry_price) * leverage * 100
        liquidation_price = entry_price * (1 - 1 / leverage * 0.95)  # 95% of margin
    else:
        pnl_pct = ((entry_price - current_price) / entry_price) * leverage * 100
        liquidation_price = entry_price * (1 + 1 / leverage * 0.95)

    # Deduct round-trip fees when closing (entry+exit fee+slippage)
    if include_fees:
        fee_cost_pct = (FEE_RATE * 2 + SLIPPAGE_RATE * 2) * leverage * 100
        pnl_pct -= fee_cost_pct

    pnl_usd = position_size_usd * (pnl_pct / 100)

    return {
        "pnl_usd": round(pnl_usd, 2),
        "pnl_percent": round(pnl_pct, 2),
        "liquidation_price": round(liquidation_price, 6),
    }


REGIME_LABELS = {
    "TRENDING_UP": "Yukari Trend",
    "TRENDING_DOWN": "Asagi Trend",
    "RANGING": "Yatay Piyasa",
    "HIGH_VOLATILITY": "Yuksek Volatilite",
    "LOW_VOLATILITY": "Dusuk Volatilite",
    "BREAKOUT": "Kirilim",
}


def generate_reasoning(
    symbol: str,
    bias: str,
    score: float,
    composition: dict,
    indicator_scores: dict,
    detected_patterns: list | None = None,
    regime: str | None = None,
    alternatives: list | None = None,
    rejections: list | None = None,
) -> str:
    """
    Generate human-readable reasoning for why this trade was opened.
    Includes regime info and decision trace.
    """
    lines = []
    clean_sym = symbol.replace("/USDT:USDT", "")
    lines.append(f"{clean_sym} {bias} sinyali (skor: {score:+.1f})")
    lines.append("")

    # Regime info
    if regime:
        regime_label = REGIME_LABELS.get(regime, regime)
        lines.append(f"Piyasa Rejimi: {regime_label}")
        lines.append("")

    # Trend analysis
    trend_keys = composition.get("trend", [])
    if trend_keys:
        trend_vals = {k: indicator_scores.get(k, 0) for k in trend_keys}
        avg = sum(trend_vals.values()) / len(trend_vals) if trend_vals else 0
        direction = "yukari" if avg > 0 else "asagi"
        lines.append(f"Trend ({direction}): {', '.join(f'{k}={v:+.2f}' for k, v in trend_vals.items())}")

    # Entry analysis
    entry_keys = composition.get("entry", [])
    if entry_keys:
        entry_vals = {k: indicator_scores.get(k, 0) for k in entry_keys}
        lines.append(f"Giris: {', '.join(f'{k}={v:+.2f}' for k, v in entry_vals.items())}")

    # Volume analysis
    vol_keys = composition.get("volume", [])
    if vol_keys:
        vol_vals = {k: indicator_scores.get(k, 0) for k in vol_keys}
        confirmed = all(
            (v > 0 if bias == "LONG" else v < 0) for v in vol_vals.values()
        )
        status = "onaylandi" if confirmed else "zayif"
        lines.append(f"Hacim ({status}): {', '.join(f'{k}={v:+.2f}' for k, v in vol_vals.items())}")

    # Patterns
    if detected_patterns:
        bullish = [p["pattern"] for p in detected_patterns if p.get("bias") == "Bullish"]
        bearish = [p["pattern"] for p in detected_patterns if p.get("bias") == "Bearish"]
        if bullish:
            lines.append(f"Bullish formasyonlar: {', '.join(bullish[:5])}")
        if bearish:
            lines.append(f"Bearish formasyonlar: {', '.join(bearish[:5])}")

    # Decision trace: alternatives
    if alternatives:
        lines.append("")
        lines.append("Alternatif stratejiler:")
        for alt in alternatives[:3]:
            lines.append(f"  - {alt['strategy']}: {alt['bias']} skor={alt['score']:+.2f} (composite={alt.get('composite', 0):.3f})")

    # Decision trace: rejections
    if rejections:
        lines.append("")
        lines.append("Reddedilen stratejiler:")
        for rej in rejections[:3]:
            lines.append(f"  - {rej['strategy']}: {rej['reason']} (skor={rej['score']:+.2f})")

    return "\n".join(lines)
