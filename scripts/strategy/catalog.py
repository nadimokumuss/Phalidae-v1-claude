"""
Phalidae v2 - Indicator/Pattern Category Catalog
Maps the 45 scoring criteria from indicators.py into 4 functional categories.
"""

# Category -> list of scoring key names (must match keys from score_all_indicators)
INDICATOR_CATALOG = {
    "trend": [
        "EMA Ribbon", "SMA Cross", "Fiyat/EMA200", "HMA", "McGinley",
        "MACD", "ADX/DI", "Ichimoku", "PSAR", "Supertrend",
        "Aroon", "Vortex", "TRIX", "KST", "STC", "Coppock",
    ],
    "entry": [
        "RSI", "RSI Divergence", "Stochastic", "StochRSI", "Williams %R",
        "CCI", "ROC", "TSI", "UO", "AO", "PPO",
        "Elder Ray", "CMO", "BOP", "Connors RSI",
    ],
    "volume": [
        "OBV", "CMF", "Force Index", "MFI", "Volume Spike", "PVO", "Klinger",
    ],
    "volatility": [
        "BB Position", "Squeeze", "Keltner", "Donchian", "Choppiness",
    ],
}

# Flat set of all scoring keys for quick lookup
ALL_KEYS = set()
for keys in INDICATOR_CATALOG.values():
    ALL_KEYS.update(keys)

# Category -> key mapping for reverse lookup
CATEGORY_KEYS = {}
for cat, keys in INDICATOR_CATALOG.items():
    for k in keys:
        CATEGORY_KEYS[k] = cat

# Weights from indicators.py (duplicated here for strategy scoring)
INDICATOR_WEIGHTS = {
    "EMA Ribbon": 1.5, "SMA Cross": 1.4, "Fiyat/EMA200": 1.5, "HMA": 1.0, "McGinley": 0.8,
    "MACD": 1.5, "ADX/DI": 1.5, "Ichimoku": 1.3, "PSAR": 1.2, "Supertrend": 1.4,
    "Aroon": 1.0, "Vortex": 0.8, "TRIX": 0.7, "KST": 0.8, "STC": 0.9,
    "Coppock": 0.9, "DPO": 0.6, "Mass Index": 0.5,
    "RSI": 1.3, "RSI Divergence": 1.6, "Stochastic": 1.0, "StochRSI": 0.9,
    "Williams %R": 0.8, "CCI": 0.9, "ROC": 0.7, "TSI": 0.8, "UO": 0.7,
    "AO": 0.7, "PPO": 0.8, "Elder Ray": 1.1, "CMO": 0.8, "BOP": 0.7,
    "Connors RSI": 0.9, "RVI": 0.7,
    "BB Position": 1.0, "Squeeze": 1.3, "Keltner": 0.7, "Donchian": 0.8, "Choppiness": 0.8,
    "OBV": 1.2, "CMF": 1.1, "Force Index": 0.8, "MFI": 1.0,
    "Volume Spike": 1.0, "PVO": 0.6, "Klinger": 0.9,
}
