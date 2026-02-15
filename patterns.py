"""
VibeTrader Pro - Tam Kapsamlı Mum Formasyonu Motoru
60 mum formasyonu tespiti.
Her formasyon: isim, yön (Bullish/Bearish/Nötr), güç (1-5)
"""

import pandas as pd
import numpy as np


def _body(o, c):
    return abs(c - o)

def _upper_wick(o, h, c):
    return h - max(o, c)

def _lower_wick(o, l, c):
    return min(o, c) - l

def _range(h, l):
    return h - l

def _is_bullish(o, c):
    return c > o

def _is_bearish(o, c):
    return c < o

def _body_pct(o, h, l, c):
    r = _range(h, l)
    return _body(o, c) / r if r > 0 else 0


def detect_all_patterns(df: pd.DataFrame) -> list[dict]:
    """
    Son mumlar üzerinde 50+ formasyonu tarar.
    Returns: list of {pattern, bias, strength, description}
    """
    if len(df) < 5:
        return []

    patterns = []
    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    i = len(df) - 1  # Son mum indeksi

    body_i = _body(o[i], c[i])
    uw_i = _upper_wick(o[i], h[i], c[i])
    lw_i = _lower_wick(o[i], l[i], c[i])
    range_i = _range(h[i], l[i])
    bp_i = _body_pct(o[i], h[i], l[i], c[i])

    # Ortalama gövde büyüklüğü (referans)
    avg_body = np.mean([_body(o[j], c[j]) for j in range(max(0, i-20), i+1)])
    if avg_body == 0:
        avg_body = 0.001

    # ═══════════════════════════════════════
    # TEK MUM FORMASYONLARI (15)
    # ═══════════════════════════════════════

    # 1. Doji
    if bp_i < 0.05 and range_i > 0:
        patterns.append({"pattern": "Doji", "bias": "Nötr", "strength": 2,
                        "description": "Kararsızlık - gövde yok denecek kadar küçük"})

    # 2. Dragonfly Doji
    if bp_i < 0.05 and lw_i > range_i * 0.6 and uw_i < range_i * 0.1:
        patterns.append({"pattern": "Dragonfly Doji", "bias": "Bullish", "strength": 3,
                        "description": "Uzun alt fitil, dip ret sinyali"})

    # 3. Gravestone Doji
    if bp_i < 0.05 and uw_i > range_i * 0.6 and lw_i < range_i * 0.1:
        patterns.append({"pattern": "Gravestone Doji", "bias": "Bearish", "strength": 3,
                        "description": "Uzun üst fitil, tepe ret sinyali"})

    # 4. Long-legged Doji
    if bp_i < 0.1 and lw_i > range_i * 0.3 and uw_i > range_i * 0.3:
        patterns.append({"pattern": "Long-legged Doji", "bias": "Nötr", "strength": 2,
                        "description": "İki yönde de uzun fitiller, yüksek kararsızlık"})

    # 5. Hammer
    if lw_i > body_i * 2 and uw_i < body_i * 0.3 and _is_bullish(o[i], c[i]) and bp_i > 0.1:
        patterns.append({"pattern": "Hammer", "bias": "Bullish", "strength": 3,
                        "description": "Düşüş trendinde dip sinyali"})

    # 6. Inverted Hammer
    if uw_i > body_i * 2 and lw_i < body_i * 0.3 and _is_bullish(o[i], c[i]) and bp_i > 0.1:
        patterns.append({"pattern": "Inverted Hammer", "bias": "Bullish", "strength": 2,
                        "description": "Düşüş trendinde olası dönüş"})

    # 7. Shooting Star
    if uw_i > body_i * 2 and lw_i < body_i * 0.3 and _is_bearish(o[i], c[i]) and bp_i > 0.1:
        patterns.append({"pattern": "Shooting Star", "bias": "Bearish", "strength": 3,
                        "description": "Yükseliş trendinde tepe sinyali"})

    # 8. Hanging Man
    if lw_i > body_i * 2 and uw_i < body_i * 0.3 and _is_bearish(o[i], c[i]) and bp_i > 0.1:
        patterns.append({"pattern": "Hanging Man", "bias": "Bearish", "strength": 3,
                        "description": "Yükseliş trendinde zayıflama sinyali"})

    # 9. Bullish Marubozu
    if _is_bullish(o[i], c[i]) and bp_i > 0.9 and uw_i < range_i * 0.05 and lw_i < range_i * 0.05:
        patterns.append({"pattern": "Bullish Marubozu", "bias": "Bullish", "strength": 4,
                        "description": "Fitilsiz güçlü alım mumı"})

    # 10. Bearish Marubozu
    if _is_bearish(o[i], c[i]) and bp_i > 0.9 and uw_i < range_i * 0.05 and lw_i < range_i * 0.05:
        patterns.append({"pattern": "Bearish Marubozu", "bias": "Bearish", "strength": 4,
                        "description": "Fitilsiz güçlü satış mumı"})

    # 11. Spinning Top
    if 0.1 < bp_i < 0.4 and uw_i > body_i * 0.8 and lw_i > body_i * 0.8:
        patterns.append({"pattern": "Spinning Top", "bias": "Nötr", "strength": 1,
                        "description": "Küçük gövde, iki yönde fitil, kararsızlık"})

    # 12. Bullish Pin Bar
    if lw_i > range_i * 0.6 and body_i < range_i * 0.25 and uw_i < range_i * 0.15:
        patterns.append({"pattern": "Bullish Pin Bar", "bias": "Bullish", "strength": 4,
                        "description": "Çok uzun alt fitil, güçlü dip ret"})

    # 13. Bearish Pin Bar
    if uw_i > range_i * 0.6 and body_i < range_i * 0.25 and lw_i < range_i * 0.15:
        patterns.append({"pattern": "Bearish Pin Bar", "bias": "Bearish", "strength": 4,
                        "description": "Çok uzun üst fitil, güçlü tepe ret"})

    # 14. High Wave
    if bp_i < 0.2 and uw_i > range_i * 0.35 and lw_i > range_i * 0.35 and range_i > avg_body * 1.5:
        patterns.append({"pattern": "High Wave", "bias": "Nötr", "strength": 2,
                        "description": "Aşırı volatilite, büyük karar noktası"})

    # 15. Belt Hold Bullish
    if _is_bullish(o[i], c[i]) and lw_i < range_i * 0.02 and body_i > avg_body * 1.5:
        patterns.append({"pattern": "Belt Hold Bullish", "bias": "Bullish", "strength": 2,
                        "description": "Açılıştan güçlü yükseliş"})

    # 16. Belt Hold Bearish
    if _is_bearish(o[i], c[i]) and uw_i < range_i * 0.02 and body_i > avg_body * 1.5:
        patterns.append({"pattern": "Belt Hold Bearish", "bias": "Bearish", "strength": 2,
                        "description": "Açılıştan güçlü düşüş"})

    # ═══════════════════════════════════════
    # İKİ MUM FORMASYONLARI (14)
    # ═══════════════════════════════════════

    if i >= 1:
        body_p = _body(o[i-1], c[i-1])
        range_p = _range(h[i-1], l[i-1])

        # 17. Bullish Engulfing
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            if o[i] <= c[i-1] and c[i] >= o[i-1] and body_i > body_p:
                patterns.append({"pattern": "Bullish Engulfing", "bias": "Bullish", "strength": 4,
                                "description": "Güçlü yutma formasyonu, trend dönüşü"})

        # 18. Bearish Engulfing
        if _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
            if o[i] >= c[i-1] and c[i] <= o[i-1] and body_i > body_p:
                patterns.append({"pattern": "Bearish Engulfing", "bias": "Bearish", "strength": 4,
                                "description": "Güçlü yutma formasyonu, trend dönüşü"})

        # 19. Bullish Harami
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            if o[i] > c[i-1] and c[i] < o[i-1] and body_i < body_p * 0.5:
                patterns.append({"pattern": "Bullish Harami", "bias": "Bullish", "strength": 2,
                                "description": "Önceki mumun içinde küçük bullish mum"})

        # 20. Bearish Harami
        if _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
            if o[i] < c[i-1] and c[i] > o[i-1] and body_i < body_p * 0.5:
                patterns.append({"pattern": "Bearish Harami", "bias": "Bearish", "strength": 2,
                                "description": "Önceki mumun içinde küçük bearish mum"})

        # 21. Harami Cross (Harami + Doji)
        if body_p > avg_body and bp_i < 0.05:
            if h[i] < max(o[i-1], c[i-1]) and l[i] > min(o[i-1], c[i-1]):
                bias = "Bullish" if _is_bearish(o[i-1], c[i-1]) else "Bearish"
                patterns.append({"pattern": "Harami Cross", "bias": bias, "strength": 3,
                                "description": "Harami + Doji, güçlü dönüş sinyali"})

        # 22. Piercing Line
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            midpoint = (o[i-1] + c[i-1]) / 2
            if o[i] < c[i-1] and c[i] > midpoint and c[i] < o[i-1]:
                patterns.append({"pattern": "Piercing Line", "bias": "Bullish", "strength": 3,
                                "description": "Önceki mumun ortasını geçen bullish kapanış"})

        # 23. Dark Cloud Cover
        if _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
            midpoint = (o[i-1] + c[i-1]) / 2
            if o[i] > c[i-1] and c[i] < midpoint and c[i] > o[i-1]:
                patterns.append({"pattern": "Dark Cloud Cover", "bias": "Bearish", "strength": 3,
                                "description": "Önceki mumun ortasını geçen bearish kapanış"})

        # 24. Tweezer Top
        if abs(h[i] - h[i-1]) < range_i * 0.02 and _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
            patterns.append({"pattern": "Tweezer Top", "bias": "Bearish", "strength": 3,
                            "description": "Aynı seviyede iki tepe, direnç"})

        # 25. Tweezer Bottom
        if abs(l[i] - l[i-1]) < range_i * 0.02 and _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            patterns.append({"pattern": "Tweezer Bottom", "bias": "Bullish", "strength": 3,
                            "description": "Aynı seviyede iki dip, destek"})

        # 26. On Neck
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            if o[i] < l[i-1] and abs(c[i] - l[i-1]) < range_p * 0.05:
                patterns.append({"pattern": "On Neck", "bias": "Bearish", "strength": 2,
                                "description": "Düşüş devam formasyonu"})

        # 27. In Neck
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            if o[i] < c[i-1] and abs(c[i] - c[i-1]) < range_p * 0.05:
                patterns.append({"pattern": "In Neck", "bias": "Bearish", "strength": 2,
                                "description": "Düşüş devam formasyonu"})

        # 28. Thrusting
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            midp = (o[i-1] + c[i-1]) / 2
            if o[i] < c[i-1] and c[i] > c[i-1] and c[i] < midp:
                patterns.append({"pattern": "Thrusting", "bias": "Bearish", "strength": 1,
                                "description": "Zayıf bullish tepki, düşüş devam"})

        # 29. Separating Lines Bullish
        if _is_bearish(o[i-1], c[i-1]) and _is_bullish(o[i], c[i]):
            if abs(o[i] - o[i-1]) < avg_body * 0.1 and body_i > avg_body:
                patterns.append({"pattern": "Separating Lines Bullish", "bias": "Bullish", "strength": 2,
                                "description": "Aynı açılış, ters kapanış"})

        # 30. Separating Lines Bearish
        if _is_bullish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i]):
            if abs(o[i] - o[i-1]) < avg_body * 0.1 and body_i > avg_body:
                patterns.append({"pattern": "Separating Lines Bearish", "bias": "Bearish", "strength": 2,
                                "description": "Aynı açılış, ters kapanış"})

    # ═══════════════════════════════════════
    # ÜÇ MUM FORMASYONLARI (20)
    # ═══════════════════════════════════════

    if i >= 2:
        body_2 = _body(o[i-2], c[i-2])
        body_1 = _body(o[i-1], c[i-1])
        range_2 = _range(h[i-2], l[i-2])

        # 31. Morning Star
        if (_is_bearish(o[i-2], c[i-2]) and body_2 > avg_body * 0.8
                and body_1 < avg_body * 0.4
                and _is_bullish(o[i], c[i]) and body_i > avg_body * 0.6
                and c[i] > (o[i-2] + c[i-2]) / 2):
            patterns.append({"pattern": "Morning Star", "bias": "Bullish", "strength": 5,
                            "description": "Üç mumlu güçlü dip dönüş formasyonu"})

        # 32. Evening Star
        if (_is_bullish(o[i-2], c[i-2]) and body_2 > avg_body * 0.8
                and body_1 < avg_body * 0.4
                and _is_bearish(o[i], c[i]) and body_i > avg_body * 0.6
                and c[i] < (o[i-2] + c[i-2]) / 2):
            patterns.append({"pattern": "Evening Star", "bias": "Bearish", "strength": 5,
                            "description": "Üç mumlu güçlü tepe dönüş formasyonu"})

        # 33. Morning Doji Star
        if (_is_bearish(o[i-2], c[i-2]) and body_2 > avg_body
                and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) < 0.05
                and _is_bullish(o[i], c[i]) and body_i > avg_body * 0.6):
            patterns.append({"pattern": "Morning Doji Star", "bias": "Bullish", "strength": 5,
                            "description": "Ortada Doji olan Morning Star, çok güçlü"})

        # 34. Evening Doji Star
        if (_is_bullish(o[i-2], c[i-2]) and body_2 > avg_body
                and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) < 0.05
                and _is_bearish(o[i], c[i]) and body_i > avg_body * 0.6):
            patterns.append({"pattern": "Evening Doji Star", "bias": "Bearish", "strength": 5,
                            "description": "Ortada Doji olan Evening Star, çok güçlü"})

        # 35. Three White Soldiers
        if (all(_is_bullish(o[j], c[j]) for j in [i-2, i-1, i])
                and c[i] > c[i-1] > c[i-2]
                and o[i] > o[i-1] > o[i-2]
                and all(_body(o[j], c[j]) > avg_body * 0.5 for j in [i-2, i-1, i])):
            # Fitil kontrolü (kısa üst fitil = daha güçlü)
            short_wicks = all(_upper_wick(o[j], h[j], c[j]) < _body(o[j], c[j]) * 0.3 for j in [i-2, i-1, i])
            strength = 5 if short_wicks else 4
            patterns.append({"pattern": "Three White Soldiers", "bias": "Bullish", "strength": strength,
                            "description": "Ardışık üç güçlü bullish mum"})

        # 36. Three Black Crows
        if (all(_is_bearish(o[j], c[j]) for j in [i-2, i-1, i])
                and c[i] < c[i-1] < c[i-2]
                and o[i] < o[i-1] < o[i-2]
                and all(_body(o[j], c[j]) > avg_body * 0.5 for j in [i-2, i-1, i])):
            short_wicks = all(_lower_wick(o[j], l[j], c[j]) < _body(o[j], c[j]) * 0.3 for j in [i-2, i-1, i])
            strength = 5 if short_wicks else 4
            patterns.append({"pattern": "Three Black Crows", "bias": "Bearish", "strength": strength,
                            "description": "Ardışık üç güçlü bearish mum"})

        # 37. Three Inside Up
        if (_is_bearish(o[i-2], c[i-2]) and body_2 > avg_body
                and _is_bullish(o[i-1], c[i-1]) and o[i-1] > c[i-2] and c[i-1] < o[i-2]
                and _is_bullish(o[i], c[i]) and c[i] > o[i-2]):
            patterns.append({"pattern": "Three Inside Up", "bias": "Bullish", "strength": 4,
                            "description": "Harami + teyit, güçlü dönüş"})

        # 38. Three Inside Down
        if (_is_bullish(o[i-2], c[i-2]) and body_2 > avg_body
                and _is_bearish(o[i-1], c[i-1]) and o[i-1] < c[i-2] and c[i-1] > o[i-2]
                and _is_bearish(o[i], c[i]) and c[i] < o[i-2]):
            patterns.append({"pattern": "Three Inside Down", "bias": "Bearish", "strength": 4,
                            "description": "Harami + teyit, güçlü dönüş"})

        # 39. Three Outside Up
        if (_is_bearish(o[i-2], c[i-2])
                and _is_bullish(o[i-1], c[i-1]) and o[i-1] <= c[i-2] and c[i-1] >= o[i-2]
                and _is_bullish(o[i], c[i]) and c[i] > c[i-1]):
            patterns.append({"pattern": "Three Outside Up", "bias": "Bullish", "strength": 4,
                            "description": "Engulfing + teyit, çok güçlü"})

        # 40. Three Outside Down
        if (_is_bullish(o[i-2], c[i-2])
                and _is_bearish(o[i-1], c[i-1]) and o[i-1] >= c[i-2] and c[i-1] <= o[i-2]
                and _is_bearish(o[i], c[i]) and c[i] < c[i-1]):
            patterns.append({"pattern": "Three Outside Down", "bias": "Bearish", "strength": 4,
                            "description": "Engulfing + teyit, çok güçlü"})

        # 41. Abandoned Baby Bullish
        if (_is_bearish(o[i-2], c[i-2]) and body_2 > avg_body
                and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) < 0.05
                and h[i-1] < l[i-2] and l[i-1] < l[i]  # Gap var
                and _is_bullish(o[i], c[i])):
            patterns.append({"pattern": "Abandoned Baby Bullish", "bias": "Bullish", "strength": 5,
                            "description": "Gap'li Doji, çok nadir ve çok güçlü"})

        # 42. Abandoned Baby Bearish
        if (_is_bullish(o[i-2], c[i-2]) and body_2 > avg_body
                and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) < 0.05
                and l[i-1] > h[i-2] and h[i-1] > h[i]
                and _is_bearish(o[i], c[i])):
            patterns.append({"pattern": "Abandoned Baby Bearish", "bias": "Bearish", "strength": 5,
                            "description": "Gap'li Doji, çok nadir ve çok güçlü"})

        # 43. Tri Star Bullish
        if all(_body_pct(o[j], h[j], l[j], c[j]) < 0.05 for j in [i-2, i-1, i]):
            if l[i-1] < l[i-2] and l[i-1] < l[i]:
                patterns.append({"pattern": "Tri Star Bullish", "bias": "Bullish", "strength": 4,
                                "description": "Üç ardışık Doji, nadir dönüş sinyali"})

        # 44. Tri Star Bearish
        if all(_body_pct(o[j], h[j], l[j], c[j]) < 0.05 for j in [i-2, i-1, i]):
            if h[i-1] > h[i-2] and h[i-1] > h[i]:
                patterns.append({"pattern": "Tri Star Bearish", "bias": "Bearish", "strength": 4,
                                "description": "Üç ardışık Doji, nadir dönüş sinyali"})

        # 45. Deliberation (Advance Block)
        if (all(_is_bullish(o[j], c[j]) for j in [i-2, i-1, i])
                and c[i] > c[i-1] > c[i-2]
                and _body(o[i], c[i]) < _body(o[i-1], c[i-1]) < _body(o[i-2], c[i-2])):
            patterns.append({"pattern": "Advance Block", "bias": "Bearish", "strength": 2,
                            "description": "Küçülen bullish mumlar, momentum kaybı"})

        # 46. Identical Three Crows
        if (all(_is_bearish(o[j], c[j]) for j in [i-2, i-1, i])
                and abs(o[i-1] - c[i-2]) < avg_body * 0.1
                and abs(o[i] - c[i-1]) < avg_body * 0.1):
            patterns.append({"pattern": "Identical Three Crows", "bias": "Bearish", "strength": 5,
                            "description": "Birbirinin kapanışında açılan bearish mumlar"})

    # ═══════════════════════════════════════
    # DEVAM FORMASYONLARI (4+ mum)
    # ═══════════════════════════════════════

    if i >= 4:
        # 47. Rising Three Methods
        if (_is_bullish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body
                and all(_is_bearish(o[j], c[j]) for j in [i-3, i-2, i-1])
                and all(l[j] > l[i-4] for j in [i-3, i-2, i-1])
                and all(h[j] < h[i-4] for j in [i-3, i-2, i-1])
                and _is_bullish(o[i], c[i]) and c[i] > c[i-4]):
            patterns.append({"pattern": "Rising Three Methods", "bias": "Bullish", "strength": 4,
                            "description": "Büyük bullish + 3 küçük düzeltme + büyük bullish devam"})

        # 48. Falling Three Methods
        if (_is_bearish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body
                and all(_is_bullish(o[j], c[j]) for j in [i-3, i-2, i-1])
                and all(h[j] < h[i-4] for j in [i-3, i-2, i-1])
                and all(l[j] > l[i-4] for j in [i-3, i-2, i-1])
                and _is_bearish(o[i], c[i]) and c[i] < c[i-4]):
            patterns.append({"pattern": "Falling Three Methods", "bias": "Bearish", "strength": 4,
                            "description": "Büyük bearish + 3 küçük düzeltme + büyük bearish devam"})

        # 49. Mat Hold Bullish
        if (_is_bullish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body * 1.2
                and _is_bearish(o[i-3], c[i-3]) and o[i-3] > c[i-4]
                and all(l[j] > l[i-4] for j in [i-3, i-2, i-1])
                and _is_bullish(o[i], c[i]) and c[i] > h[i-4]):
            patterns.append({"pattern": "Mat Hold Bullish", "bias": "Bullish", "strength": 5,
                            "description": "Rising Three'nin güçlü versiyonu"})

    # ═══════════════════════════════════════
    # TASUKI GAP FORMASYONLARI
    # ═══════════════════════════════════════

    if i >= 2:
        # 50. Upside Tasuki Gap
        if (_is_bullish(o[i-2], c[i-2]) and _is_bullish(o[i-1], c[i-1])
                and o[i-1] > c[i-2]  # Gap up
                and _is_bearish(o[i], c[i])
                and o[i] > o[i-1] and c[i] < o[i-1] and c[i] > c[i-2]):
            patterns.append({"pattern": "Upside Tasuki Gap", "bias": "Bullish", "strength": 3,
                            "description": "Gap'i kapatmayan düzeltme, yükseliş devam"})

        # 51. Downside Tasuki Gap
        if (_is_bearish(o[i-2], c[i-2]) and _is_bearish(o[i-1], c[i-1])
                and o[i-1] < c[i-2]  # Gap down
                and _is_bullish(o[i], c[i])
                and o[i] < o[i-1] and c[i] > o[i-1] and c[i] < c[i-2]):
            patterns.append({"pattern": "Downside Tasuki Gap", "bias": "Bearish", "strength": 3,
                            "description": "Gap'i kapatmayan düzeltme, düşüş devam"})

    # ═══════════════════════════════════════
    # EK FORMASYONLAR (52-60)
    # ═══════════════════════════════════════

    if i >= 1:
        body_p2 = _body(o[i-1], c[i-1])

        # 52. Kicking Bullish
        if (_is_bearish(o[i-1], c[i-1]) and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) > 0.9
                and _is_bullish(o[i], c[i]) and _body_pct(o[i], h[i], l[i], c[i]) > 0.9
                and o[i] > o[i-1]):
            patterns.append({"pattern": "Kicking Bullish", "bias": "Bullish", "strength": 5,
                            "description": "İki karşıt Marubozu, çok güçlü bullish sinyal"})

        # 53. Kicking Bearish
        if (_is_bullish(o[i-1], c[i-1]) and _body_pct(o[i-1], h[i-1], l[i-1], c[i-1]) > 0.9
                and _is_bearish(o[i], c[i]) and _body_pct(o[i], h[i], l[i], c[i]) > 0.9
                and o[i] < o[i-1]):
            patterns.append({"pattern": "Kicking Bearish", "bias": "Bearish", "strength": 5,
                            "description": "İki karşıt Marubozu, çok güçlü bearish sinyal"})

        # 54. Counterattack Lines Bullish
        if (_is_bearish(o[i-1], c[i-1]) and body_p2 > avg_body
                and _is_bullish(o[i], c[i]) and body_i > avg_body
                and abs(c[i] - c[i-1]) < avg_body * 0.1):
            patterns.append({"pattern": "Counterattack Bullish", "bias": "Bullish", "strength": 3,
                            "description": "Aynı kapanış seviyesinde karşıt güçlü mumlar"})

        # 55. Counterattack Lines Bearish
        if (_is_bullish(o[i-1], c[i-1]) and body_p2 > avg_body
                and _is_bearish(o[i], c[i]) and body_i > avg_body
                and abs(c[i] - c[i-1]) < avg_body * 0.1):
            patterns.append({"pattern": "Counterattack Bearish", "bias": "Bearish", "strength": 3,
                            "description": "Aynı kapanış seviyesinde karşıt güçlü mumlar"})

        # 56. Homing Pigeon
        if (_is_bearish(o[i-1], c[i-1]) and _is_bearish(o[i], c[i])
                and body_p2 > avg_body
                and o[i] < o[i-1] and c[i] > c[i-1]
                and body_i < body_p2 * 0.5):
            patterns.append({"pattern": "Homing Pigeon", "bias": "Bullish", "strength": 2,
                            "description": "İç içe bearish mumlar, satış baskısı azalıyor"})

    if i >= 2:
        # 57. Stick Sandwich
        if (_is_bearish(o[i-2], c[i-2]) and _is_bullish(o[i-1], c[i-1])
                and _is_bearish(o[i], c[i])
                and abs(c[i] - c[i-2]) < avg_body * 0.1):
            patterns.append({"pattern": "Stick Sandwich", "bias": "Bullish", "strength": 3,
                            "description": "Aynı kapanışlı iki bearish arasında bullish, destek teyidi"})

        # 58. Unique Three River
        if (_is_bearish(o[i-2], c[i-2]) and _body(o[i-2], c[i-2]) > avg_body
                and _is_bearish(o[i-1], c[i-1]) and l[i-1] < l[i-2]
                and _lower_wick(o[i-1], l[i-1], c[i-1]) > _body(o[i-1], c[i-1])
                and _is_bullish(o[i], c[i]) and body_i < _body(o[i-1], c[i-1])
                and c[i] < c[i-1]):
            patterns.append({"pattern": "Unique Three River", "bias": "Bullish", "strength": 3,
                            "description": "Nadir dip dönüş formasyonu"})

    if i >= 4:
        # 59. Breakaway Bullish
        if (_is_bearish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body
                and o[i-3] < c[i-4]  # Gap down
                and _is_bearish(o[i-3], c[i-3])
                and _is_bearish(o[i-2], c[i-2]) and c[i-2] < c[i-3]
                and _is_bullish(o[i], c[i]) and body_i > avg_body
                and c[i] > o[i-3]):
            patterns.append({"pattern": "Breakaway Bullish", "bias": "Bullish", "strength": 4,
                            "description": "Gap'li düşüşten güçlü geri dönüş"})

        # 60. Breakaway Bearish
        if (_is_bullish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body
                and o[i-3] > c[i-4]  # Gap up
                and _is_bullish(o[i-3], c[i-3])
                and _is_bullish(o[i-2], c[i-2]) and c[i-2] > c[i-3]
                and _is_bearish(o[i], c[i]) and body_i > avg_body
                and c[i] < o[i-3]):
            patterns.append({"pattern": "Breakaway Bearish", "bias": "Bearish", "strength": 4,
                            "description": "Gap'li yükselişten güçlü geri dönüş"})

        # Mat Hold Bearish (49'un karşılığı)
        if (_is_bearish(o[i-4], c[i-4]) and _body(o[i-4], c[i-4]) > avg_body * 1.2
                and _is_bullish(o[i-3], c[i-3]) and o[i-3] < c[i-4]
                and all(h[j] < h[i-4] for j in [i-3, i-2, i-1])
                and _is_bearish(o[i], c[i]) and c[i] < l[i-4]):
            patterns.append({"pattern": "Mat Hold Bearish", "bias": "Bearish", "strength": 5,
                            "description": "Falling Three'nin güçlü versiyonu"})

    # Formasyonları güce göre sırala
    patterns.sort(key=lambda x: x["strength"], reverse=True)
    return patterns


def score_patterns(patterns: list[dict]) -> float:
    """
    Formasyonların toplam puanını hesaplar.
    Bullish: pozitif, Bearish: negatif.
    Max ±5 arası normalize edilir.
    """
    total = 0
    for p in patterns:
        weight = p["strength"]
        if p["bias"] == "Bullish":
            total += weight
        elif p["bias"] == "Bearish":
            total -= weight
    return round(np.clip(total, -5, 5), 1)
