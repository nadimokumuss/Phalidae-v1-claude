"""
VibeTrader Pro - Tam Kapsamlı Seviye Tespiti
Fibonacci, Pivot Points, Volume Profile, Trend Lines, Chart Patterns,
Psikolojik Seviyeler, Order Blocks, Fair Value Gaps, Swing Points
"""

import pandas as pd
import numpy as np
from scipy import stats


# ═══════════════════════════════════════════════
# YARDIMCI FONKSİYONLAR
# ═══════════════════════════════════════════════

def find_pivot_points(df: pd.DataFrame, left: int = 5, right: int = 5) -> dict:
    """Lokal minimum ve maksimum noktalarını bulur."""
    highs = df["high"].values
    lows = df["low"].values

    pivot_highs = []  # (index, price)
    pivot_lows = []

    for i in range(left, len(df) - right):
        # Pivot High
        if highs[i] == max(highs[i - left: i + right + 1]):
            pivot_highs.append((i, highs[i]))
        # Pivot Low
        if lows[i] == min(lows[i - left: i + right + 1]):
            pivot_lows.append((i, lows[i]))

    return {"pivot_highs": pivot_highs, "pivot_lows": pivot_lows}


def find_swing_points(df: pd.DataFrame, strength: int = 3) -> dict:
    """Swing High ve Swing Low noktalarını tespit eder."""
    highs = df["high"].values
    lows = df["low"].values
    swing_highs = []
    swing_lows = []

    for i in range(strength, len(df) - strength):
        is_swing_high = all(highs[i] > highs[i - j] for j in range(1, strength + 1)) and \
                        all(highs[i] > highs[i + j] for j in range(1, strength + 1))
        if is_swing_high:
            swing_highs.append({"index": i, "price": highs[i], "timestamp": df["timestamp"].iloc[i]})

        is_swing_low = all(lows[i] < lows[i - j] for j in range(1, strength + 1)) and \
                       all(lows[i] < lows[i + j] for j in range(1, strength + 1))
        if is_swing_low:
            swing_lows.append({"index": i, "price": lows[i], "timestamp": df["timestamp"].iloc[i]})

    return {"swing_highs": swing_highs, "swing_lows": swing_lows}


# ═══════════════════════════════════════════════
# 1. PIVOT CLUSTERING S/R
# ═══════════════════════════════════════════════

def cluster_support_resistance(df: pd.DataFrame, window: int = 20, num_levels: int = 8) -> dict:
    """Pivot noktalarını clustering ile birleştirerek S/R seviyeleri üretir."""
    pivots = find_pivot_points(df, left=window // 4, right=window // 4)
    close_now = df["close"].iloc[-1]

    def cluster(levels, threshold_pct=0.003):
        if not levels:
            return []
        prices = sorted([p for _, p in levels])
        clusters = [[prices[0]]]
        for p in prices[1:]:
            if (p - clusters[-1][-1]) / clusters[-1][-1] < threshold_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        return sorted(
            [{"level": round(np.mean(c), 6), "touches": len(c), "method": "Pivot Cluster"}
             for c in clusters],
            key=lambda x: x["touches"], reverse=True
        )[:num_levels]

    supports = cluster([p for p in pivots["pivot_lows"] if p[1] < close_now])
    resistances = cluster([p for p in pivots["pivot_highs"] if p[1] > close_now])

    return {"supports": supports, "resistances": resistances}


# ═══════════════════════════════════════════════
# 2. FİBONACCİ RETRACEMENT & EXTENSION
# ═══════════════════════════════════════════════

FIBO_LEVELS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
FIBO_EXT_LEVELS = [1.0, 1.272, 1.414, 1.618, 2.0, 2.618]


def fibonacci_retracement(df: pd.DataFrame, lookback: int = 100) -> dict:
    """
    Son N mum içindeki en yüksek ve en düşük noktalar arasında
    Fibonacci retracement seviyelerini hesaplar.
    """
    subset = df.tail(lookback)
    swing_high = subset["high"].max()
    swing_low = subset["low"].min()
    close_now = df["close"].iloc[-1]
    diff = swing_high - swing_low

    if diff == 0:
        return {"levels": [], "trend": "flat"}

    # Trend yönünü belirle
    high_idx = subset["high"].idxmax()
    low_idx = subset["low"].idxmin()
    uptrend = low_idx < high_idx  # Önce dip sonra tepe = uptrend

    levels = []
    for fib in FIBO_LEVELS:
        if uptrend:
            # Yukarı trend: tepeden aşağı retracement
            price = swing_high - diff * fib
        else:
            # Aşağı trend: dipten yukarı retracement
            price = swing_low + diff * fib

        level_type = "support" if price < close_now else "resistance"
        levels.append({
            "fib_level": fib,
            "price": round(price, 6),
            "type": level_type,
            "method": "Fibonacci Retracement",
        })

    return {"levels": levels, "trend": "uptrend" if uptrend else "downtrend",
            "swing_high": swing_high, "swing_low": swing_low}


def fibonacci_extension(df: pd.DataFrame, lookback: int = 100) -> list[dict]:
    """Fibonacci extension seviyelerini hesaplar."""
    subset = df.tail(lookback)
    swing_high = subset["high"].max()
    swing_low = subset["low"].min()
    diff = swing_high - swing_low

    if diff == 0:
        return []

    high_idx = subset["high"].idxmax()
    low_idx = subset["low"].idxmin()
    uptrend = low_idx < high_idx

    levels = []
    for ext in FIBO_EXT_LEVELS:
        if uptrend:
            price = swing_low + diff * ext
        else:
            price = swing_high - diff * ext

        levels.append({
            "ext_level": ext,
            "price": round(price, 6),
            "method": "Fibonacci Extension",
        })

    return levels


# ═══════════════════════════════════════════════
# 3. KLASİK PİVOT POINTS (4 YÖNTEM)
# ═══════════════════════════════════════════════

def classic_pivot_points(df: pd.DataFrame) -> dict:
    """Standard (Floor) Pivot Points."""
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    c = df["close"].iloc[-1]

    pp = (h + l + c) / 3
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)
    r3 = h + 2 * (pp - l)
    s3 = l - 2 * (h - pp)

    return {
        "method": "Classic Pivot",
        "PP": round(pp, 6),
        "R1": round(r1, 6), "R2": round(r2, 6), "R3": round(r3, 6),
        "S1": round(s1, 6), "S2": round(s2, 6), "S3": round(s3, 6),
    }


def camarilla_pivot_points(df: pd.DataFrame) -> dict:
    """Camarilla Pivot Points."""
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    c = df["close"].iloc[-1]
    hl = h - l

    return {
        "method": "Camarilla",
        "R4": round(c + hl * 1.1 / 2, 6),
        "R3": round(c + hl * 1.1 / 4, 6),
        "R2": round(c + hl * 1.1 / 6, 6),
        "R1": round(c + hl * 1.1 / 12, 6),
        "S1": round(c - hl * 1.1 / 12, 6),
        "S2": round(c - hl * 1.1 / 6, 6),
        "S3": round(c - hl * 1.1 / 4, 6),
        "S4": round(c - hl * 1.1 / 2, 6),
    }


def woodie_pivot_points(df: pd.DataFrame) -> dict:
    """Woodie Pivot Points."""
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    c = df["close"].iloc[-1]

    pp = (h + l + 2 * c) / 4
    r1 = 2 * pp - l
    s1 = 2 * pp - h
    r2 = pp + (h - l)
    s2 = pp - (h - l)

    return {
        "method": "Woodie",
        "PP": round(pp, 6),
        "R1": round(r1, 6), "R2": round(r2, 6),
        "S1": round(s1, 6), "S2": round(s2, 6),
    }


def demark_pivot_points(df: pd.DataFrame) -> dict:
    """DeMark Pivot Points."""
    h = df["high"].iloc[-1]
    l = df["low"].iloc[-1]
    c = df["close"].iloc[-1]
    o = df["open"].iloc[-1]

    if c < o:
        x = h + 2 * l + c
    elif c > o:
        x = 2 * h + l + c
    else:
        x = h + l + 2 * c

    return {
        "method": "DeMark",
        "R1": round(x / 2 - l, 6),
        "S1": round(x / 2 - h, 6),
    }


# ═══════════════════════════════════════════════
# 4. PSİKOLOJİK SEVİYELER
# ═══════════════════════════════════════════════

def psychological_levels(price: float, num_levels: int = 5) -> list[dict]:
    """
    Yuvarlak sayı seviyelerini tespit eder.
    Örn: BTC 97500 ise → 95000, 96000, 97000, 98000, 99000, 100000
    """
    magnitude = 10 ** (len(str(int(price))) - 2)
    if magnitude < 1:
        magnitude = 1

    base = int(price / magnitude) * magnitude
    levels = []
    for offset in range(-num_levels, num_levels + 1):
        level = base + offset * magnitude
        if level > 0:
            level_type = "support" if level < price else "resistance"
            levels.append({
                "level": level,
                "type": level_type,
                "method": "Psychological",
                "significance": "major" if level % (magnitude * 5) == 0 else "minor",
            })
    return levels


# ═══════════════════════════════════════════════
# 5. VOLUME PROFİLE
# ═══════════════════════════════════════════════

def volume_profile(df: pd.DataFrame, num_bins: int = 50) -> dict:
    """
    Fiyat aralığını bölgelere ayırıp hacim dağılımını analiz eder.
    POC (Point of Control), VAH (Value Area High), VAL (Value Area Low) hesaplar.
    """
    price_min = df["low"].min()
    price_max = df["high"].max()

    if price_max == price_min:
        return {"poc": price_min, "vah": price_max, "val": price_min, "profile": []}

    bin_size = (price_max - price_min) / num_bins
    bins = np.zeros(num_bins)

    for _, row in df.iterrows():
        low_bin = int((row["low"] - price_min) / bin_size)
        high_bin = int((row["high"] - price_min) / bin_size)
        low_bin = min(low_bin, num_bins - 1)
        high_bin = min(high_bin, num_bins - 1)
        for b in range(low_bin, high_bin + 1):
            bins[b] += row["volume"]

    # POC: en yüksek hacimli seviye
    poc_bin = np.argmax(bins)
    poc_price = price_min + (poc_bin + 0.5) * bin_size

    # Value Area (%70 hacim)
    total_vol = bins.sum()
    target_vol = total_vol * 0.7
    cumulative = 0
    va_bins = [poc_bin]
    cumulative = bins[poc_bin]

    low_ptr = poc_bin - 1
    high_ptr = poc_bin + 1

    while cumulative < target_vol and (low_ptr >= 0 or high_ptr < num_bins):
        low_vol = bins[low_ptr] if low_ptr >= 0 else 0
        high_vol = bins[high_ptr] if high_ptr < num_bins else 0

        if low_vol >= high_vol and low_ptr >= 0:
            cumulative += low_vol
            va_bins.append(low_ptr)
            low_ptr -= 1
        elif high_ptr < num_bins:
            cumulative += high_vol
            va_bins.append(high_ptr)
            high_ptr += 1
        else:
            break

    val_price = price_min + (min(va_bins) + 0.5) * bin_size
    vah_price = price_min + (max(va_bins) + 0.5) * bin_size

    # High Volume Nodes (HVN) - hacmin yoğun olduğu bölgeler
    mean_vol = bins.mean()
    hvn = []
    for b in range(num_bins):
        if bins[b] > mean_vol * 1.5:
            hvn.append({
                "price": round(price_min + (b + 0.5) * bin_size, 6),
                "volume": round(bins[b], 2),
                "method": "Volume Profile HVN",
            })

    return {
        "poc": round(poc_price, 6),
        "vah": round(vah_price, 6),
        "val": round(val_price, 6),
        "hvn": hvn,
    }


# ═══════════════════════════════════════════════
# 6. ORDER BLOCKS
# ═══════════════════════════════════════════════

def detect_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[dict]:
    """
    Order Block'ları tespit eder.
    Bullish OB: Güçlü yükseliş öncesindeki son bearish mum.
    Bearish OB: Güçlü düşüş öncesindeki son bullish mum.
    """
    obs = []
    subset = df.tail(lookback)
    o = subset["open"].values
    h = subset["high"].values
    l = subset["low"].values
    c = subset["close"].values
    avg_body = np.mean(np.abs(c - o))

    for idx in range(2, len(subset) - 1):
        body_next = abs(c[idx + 1] - o[idx + 1]) if idx + 1 < len(subset) else 0
        body_curr = abs(c[idx] - o[idx])

        # Bullish OB: bearish mum + sonrasında güçlü bullish hareket
        if c[idx] < o[idx] and body_next > avg_body * 2 and c[idx + 1] > o[idx + 1]:
            obs.append({
                "type": "Bullish OB",
                "high": h[idx],
                "low": l[idx],
                "mid": (h[idx] + l[idx]) / 2,
                "method": "Order Block",
                "bias": "Bullish",
            })

        # Bearish OB: bullish mum + sonrasında güçlü bearish hareket
        if c[idx] > o[idx] and body_next > avg_body * 2 and c[idx + 1] < o[idx + 1]:
            obs.append({
                "type": "Bearish OB",
                "high": h[idx],
                "low": l[idx],
                "mid": (h[idx] + l[idx]) / 2,
                "method": "Order Block",
                "bias": "Bearish",
            })

    return obs[-10:]  # Son 10 OB


# ═══════════════════════════════════════════════
# 7. FAIR VALUE GAPS (FVG)
# ═══════════════════════════════════════════════

def detect_fair_value_gaps(df: pd.DataFrame, lookback: int = 50) -> list[dict]:
    """
    Fair Value Gap (FVG) tespiti.
    Bullish FVG: Mum 1 high < Mum 3 low (arada gap)
    Bearish FVG: Mum 1 low > Mum 3 high (arada gap)
    """
    fvgs = []
    subset = df.tail(lookback)
    h = subset["high"].values
    l = subset["low"].values
    c = subset["close"].values
    close_now = df["close"].iloc[-1]

    for idx in range(2, len(subset)):
        # Bullish FVG
        if l[idx] > h[idx - 2]:
            gap_low = h[idx - 2]
            gap_high = l[idx]
            if close_now < gap_high:  # Henüz kapatılmamış
                fvgs.append({
                    "type": "Bullish FVG",
                    "high": round(gap_high, 6),
                    "low": round(gap_low, 6),
                    "mid": round((gap_high + gap_low) / 2, 6),
                    "method": "FVG",
                    "bias": "Bullish",
                })

        # Bearish FVG
        if h[idx] < l[idx - 2]:
            gap_high = l[idx - 2]
            gap_low = h[idx]
            if close_now > gap_low:
                fvgs.append({
                    "type": "Bearish FVG",
                    "high": round(gap_high, 6),
                    "low": round(gap_low, 6),
                    "mid": round((gap_high + gap_low) / 2, 6),
                    "method": "FVG",
                    "bias": "Bearish",
                })

    return fvgs[-10:]


# ═══════════════════════════════════════════════
# 8. TREND ÇİZGİLERİ
# ═══════════════════════════════════════════════

def detect_trend_lines(df: pd.DataFrame, min_touches: int = 3) -> list[dict]:
    """
    Otomatik trend çizgisi tespiti.
    Pivot noktalarına lineer regresyon uygular.
    En az min_touches noktaya dokunan çizgileri döndürür.
    """
    swings = find_swing_points(df, strength=3)
    trend_lines = []
    close_now = df["close"].iloc[-1]

    # Yükselen trend çizgisi (swing low'lardan)
    if len(swings["swing_lows"]) >= 3:
        lows = [(s["index"], s["price"]) for s in swings["swing_lows"]]
        for start_idx in range(len(lows) - 2):
            for end_idx in range(start_idx + 2, len(lows)):
                x = np.array([lows[start_idx][0], lows[end_idx][0]])
                y = np.array([lows[start_idx][1], lows[end_idx][1]])

                if y[1] <= y[0]:
                    continue  # Sadece yükselen çizgiler

                slope = (y[1] - y[0]) / (x[1] - x[0])
                intercept = y[0] - slope * x[0]

                # Kaç noktaya dokunuyor
                touches = 0
                for idx, price in lows:
                    expected = slope * idx + intercept
                    tolerance = close_now * 0.003
                    if abs(price - expected) < tolerance:
                        touches += 1

                if touches >= min_touches:
                    # Çizgiyi şimdiki zamana uzat
                    current_value = slope * (len(df) - 1) + intercept
                    trend_lines.append({
                        "type": "Ascending Trend Line",
                        "slope": round(slope, 8),
                        "current_value": round(current_value, 6),
                        "touches": touches,
                        "bias": "Bullish",
                        "method": "Trend Line",
                    })

    # Alçalan trend çizgisi (swing high'lardan)
    if len(swings["swing_highs"]) >= 3:
        highs = [(s["index"], s["price"]) for s in swings["swing_highs"]]
        for start_idx in range(len(highs) - 2):
            for end_idx in range(start_idx + 2, len(highs)):
                x = np.array([highs[start_idx][0], highs[end_idx][0]])
                y = np.array([highs[start_idx][1], highs[end_idx][1]])

                if y[1] >= y[0]:
                    continue  # Sadece alçalan çizgiler

                slope = (y[1] - y[0]) / (x[1] - x[0])
                intercept = y[0] - slope * x[0]

                touches = 0
                for idx, price in highs:
                    expected = slope * idx + intercept
                    tolerance = close_now * 0.003
                    if abs(price - expected) < tolerance:
                        touches += 1

                if touches >= min_touches:
                    current_value = slope * (len(df) - 1) + intercept
                    trend_lines.append({
                        "type": "Descending Trend Line",
                        "slope": round(slope, 8),
                        "current_value": round(current_value, 6),
                        "touches": touches,
                        "bias": "Bearish",
                        "method": "Trend Line",
                    })

    # Dokunma sayısına göre sırala
    trend_lines.sort(key=lambda x: x["touches"], reverse=True)
    return trend_lines[:5]


# ═══════════════════════════════════════════════
# 9. CHART PATTERN TESPİTİ
# ═══════════════════════════════════════════════

def detect_chart_patterns(df: pd.DataFrame) -> list[dict]:
    """
    Geometrik grafik formasyonlarını tespit eder:
    - Double Top / Double Bottom
    - Head & Shoulders / Inverse H&S
    - Ascending / Descending / Symmetric Triangle
    - Rising / Falling Wedge
    - Flag / Pennant
    """
    chart_patterns = []
    swings = find_swing_points(df, strength=5)
    sh = swings["swing_highs"]
    sl = swings["swing_lows"]
    close_now = df["close"].iloc[-1]

    if len(sh) < 2 or len(sl) < 2:
        return chart_patterns

    tolerance_pct = 0.015  # %1.5 tolerans

    # DOUBLE TOP
    if len(sh) >= 2:
        h1 = sh[-2]["price"]
        h2 = sh[-1]["price"]
        if abs(h1 - h2) / h1 < tolerance_pct and close_now < min(h1, h2):
            neckline = min(s["price"] for s in sl[-3:]) if len(sl) >= 1 else close_now
            target = neckline - abs(h1 - neckline)
            chart_patterns.append({
                "pattern": "Double Top",
                "bias": "Bearish",
                "strength": 4,
                "neckline": round(neckline, 6),
                "target": round(target, 6),
                "description": "İki eşit tepe, kırılırsa hedef: neckline mesafesi kadar düşüş",
            })

    # DOUBLE BOTTOM
    if len(sl) >= 2:
        l1 = sl[-2]["price"]
        l2 = sl[-1]["price"]
        if abs(l1 - l2) / l1 < tolerance_pct and close_now > max(l1, l2):
            neckline = max(s["price"] for s in sh[-3:]) if len(sh) >= 1 else close_now
            target = neckline + abs(neckline - l1)
            chart_patterns.append({
                "pattern": "Double Bottom",
                "bias": "Bullish",
                "strength": 4,
                "neckline": round(neckline, 6),
                "target": round(target, 6),
                "description": "İki eşit dip, kırılırsa hedef: neckline mesafesi kadar yükseliş",
            })

    # HEAD & SHOULDERS
    if len(sh) >= 3 and len(sl) >= 2:
        left_s = sh[-3]["price"]
        head = sh[-2]["price"]
        right_s = sh[-1]["price"]

        if (head > left_s and head > right_s
                and abs(left_s - right_s) / left_s < tolerance_pct * 2):
            neckline = (sl[-2]["price"] + sl[-1]["price"]) / 2
            target = neckline - abs(head - neckline)
            chart_patterns.append({
                "pattern": "Head & Shoulders",
                "bias": "Bearish",
                "strength": 5,
                "neckline": round(neckline, 6),
                "target": round(target, 6),
                "description": "Baş-omuz formasyonu, güçlü dönüş sinyali",
            })

    # INVERSE HEAD & SHOULDERS
    if len(sl) >= 3 and len(sh) >= 2:
        left_s = sl[-3]["price"]
        head = sl[-2]["price"]
        right_s = sl[-1]["price"]

        if (head < left_s and head < right_s
                and abs(left_s - right_s) / left_s < tolerance_pct * 2):
            neckline = (sh[-2]["price"] + sh[-1]["price"]) / 2
            target = neckline + abs(neckline - head)
            chart_patterns.append({
                "pattern": "Inverse Head & Shoulders",
                "bias": "Bullish",
                "strength": 5,
                "neckline": round(neckline, 6),
                "target": round(target, 6),
                "description": "Ters baş-omuz, güçlü dönüş sinyali",
            })

    # ASCENDING TRIANGLE
    if len(sh) >= 3 and len(sl) >= 3:
        recent_highs = [s["price"] for s in sh[-3:]]
        recent_lows = [s["price"] for s in sl[-3:]]

        highs_flat = (max(recent_highs) - min(recent_highs)) / max(recent_highs) < tolerance_pct
        lows_rising = recent_lows[-1] > recent_lows[0]

        if highs_flat and lows_rising:
            resistance = np.mean(recent_highs)
            chart_patterns.append({
                "pattern": "Ascending Triangle",
                "bias": "Bullish",
                "strength": 3,
                "resistance": round(resistance, 6),
                "description": "Düz direnç + yükselen dipler, kırılım yukarı beklenir",
            })

    # DESCENDING TRIANGLE
    if len(sh) >= 3 and len(sl) >= 3:
        recent_highs = [s["price"] for s in sh[-3:]]
        recent_lows = [s["price"] for s in sl[-3:]]

        lows_flat = (max(recent_lows) - min(recent_lows)) / max(recent_lows) < tolerance_pct
        highs_falling = recent_highs[-1] < recent_highs[0]

        if lows_flat and highs_falling:
            support = np.mean(recent_lows)
            chart_patterns.append({
                "pattern": "Descending Triangle",
                "bias": "Bearish",
                "strength": 3,
                "support": round(support, 6),
                "description": "Düz destek + alçalan tepeler, kırılım aşağı beklenir",
            })

    # SYMMETRIC TRIANGLE
    if len(sh) >= 3 and len(sl) >= 3:
        recent_highs = [s["price"] for s in sh[-3:]]
        recent_lows = [s["price"] for s in sl[-3:]]

        highs_falling = recent_highs[-1] < recent_highs[0]
        lows_rising = recent_lows[-1] > recent_lows[0]

        if highs_falling and lows_rising:
            chart_patterns.append({
                "pattern": "Symmetric Triangle",
                "bias": "Nötr",
                "strength": 3,
                "description": "Daralan üçgen, kırılım yönü belirsiz ama güçlü olacak",
            })

    # RISING WEDGE (Bearish)
    if len(sh) >= 3 and len(sl) >= 3:
        recent_highs = [s["price"] for s in sh[-3:]]
        recent_lows = [s["price"] for s in sl[-3:]]
        h_slope = recent_highs[-1] - recent_highs[0]
        l_slope = recent_lows[-1] - recent_lows[0]

        if h_slope > 0 and l_slope > 0 and l_slope > h_slope:
            chart_patterns.append({
                "pattern": "Rising Wedge",
                "bias": "Bearish",
                "strength": 3,
                "description": "Yükselen kama, genelde aşağı kırılır",
            })

    # FALLING WEDGE (Bullish)
    if len(sh) >= 3 and len(sl) >= 3:
        recent_highs = [s["price"] for s in sh[-3:]]
        recent_lows = [s["price"] for s in sl[-3:]]
        h_slope = recent_highs[-1] - recent_highs[0]
        l_slope = recent_lows[-1] - recent_lows[0]

        if h_slope < 0 and l_slope < 0 and abs(l_slope) > abs(h_slope):
            chart_patterns.append({
                "pattern": "Falling Wedge",
                "bias": "Bullish",
                "strength": 3,
                "description": "Düşen kama, genelde yukarı kırılır",
            })

    # TRIPLE TOP
    if len(sh) >= 3:
        last3 = [s["price"] for s in sh[-3:]]
        if max(last3) - min(last3) < max(last3) * tolerance_pct:
            chart_patterns.append({
                "pattern": "Triple Top",
                "bias": "Bearish",
                "strength": 5,
                "description": "Üç eşit tepe, çok güçlü direnç",
            })

    # TRIPLE BOTTOM
    if len(sl) >= 3:
        last3 = [s["price"] for s in sl[-3:]]
        if max(last3) - min(last3) < max(last3) * tolerance_pct:
            chart_patterns.append({
                "pattern": "Triple Bottom",
                "bias": "Bullish",
                "strength": 5,
                "description": "Üç eşit dip, çok güçlü destek",
            })

    return chart_patterns


# ═══════════════════════════════════════════════
# 10. TÜM SEVİYELERİ BİRLEŞTİR
# ═══════════════════════════════════════════════

def get_all_levels(df: pd.DataFrame) -> dict:
    """Tüm yöntemlerden seviyeleri toplar ve birleştirilmiş çıktı üretir."""
    close_now = df["close"].iloc[-1]

    # 1. Pivot Cluster S/R
    cluster_sr = cluster_support_resistance(df)

    # 2. Fibonacci
    fib_ret = fibonacci_retracement(df)
    fib_ext = fibonacci_extension(df)

    # 3. Pivot Points (4 yöntem)
    classic_pp = classic_pivot_points(df)
    camarilla_pp = camarilla_pivot_points(df)
    woodie_pp = woodie_pivot_points(df)
    demark_pp = demark_pivot_points(df)

    # 4. Psikolojik seviyeler
    psych = psychological_levels(close_now)

    # 5. Volume Profile
    vol_prof = volume_profile(df)

    # 6. Order Blocks
    obs = detect_order_blocks(df)

    # 7. Fair Value Gaps
    fvgs = detect_fair_value_gaps(df)

    # 8. Trend Lines
    tlines = detect_trend_lines(df)

    # 9. Chart Patterns
    chart_pats = detect_chart_patterns(df)

    # 10. Swing Points
    swings = find_swing_points(df)

    # ── Birleştirilmiş S/R listesi ──
    all_supports = []
    all_resistances = []

    # Cluster S/R
    for s in cluster_sr["supports"]:
        all_supports.append({"price": s["level"], "method": s["method"], "weight": s["touches"] * 2})
    for r in cluster_sr["resistances"]:
        all_resistances.append({"price": r["level"], "method": r["method"], "weight": r["touches"] * 2})

    # Fibonacci
    for lv in fib_ret["levels"]:
        weight = 3 if lv["fib_level"] in [0.382, 0.5, 0.618] else 1.5
        entry = {"price": lv["price"], "method": f"Fib {lv['fib_level']}", "weight": weight}
        if lv["type"] == "support":
            all_supports.append(entry)
        else:
            all_resistances.append(entry)

    # Classic Pivot Points
    for key in ["S1", "S2", "S3"]:
        if key in classic_pp:
            all_supports.append({"price": classic_pp[key], "method": f"Classic {key}", "weight": 2})
    for key in ["R1", "R2", "R3"]:
        if key in classic_pp:
            all_resistances.append({"price": classic_pp[key], "method": f"Classic {key}", "weight": 2})

    # Volume Profile
    if vol_prof["val"] < close_now:
        all_supports.append({"price": vol_prof["val"], "method": "VP VAL", "weight": 3})
    if vol_prof["vah"] > close_now:
        all_resistances.append({"price": vol_prof["vah"], "method": "VP VAH", "weight": 3})
    all_supports.append({"price": vol_prof["poc"], "method": "VP POC", "weight": 4})

    # Order Blocks
    for ob in obs:
        entry = {"price": ob["mid"], "method": ob["type"], "weight": 3}
        if ob["bias"] == "Bullish" and ob["mid"] < close_now:
            all_supports.append(entry)
        elif ob["bias"] == "Bearish" and ob["mid"] > close_now:
            all_resistances.append(entry)

    # FVG
    for fvg in fvgs:
        entry = {"price": fvg["mid"], "method": fvg["type"], "weight": 2.5}
        if fvg["bias"] == "Bullish" and fvg["mid"] < close_now:
            all_supports.append(entry)
        elif fvg["bias"] == "Bearish" and fvg["mid"] > close_now:
            all_resistances.append(entry)

    # Trend Lines
    for tl in tlines:
        entry = {"price": tl["current_value"], "method": tl["type"], "weight": tl["touches"] * 1.5}
        if tl["current_value"] < close_now:
            all_supports.append(entry)
        else:
            all_resistances.append(entry)

    # Psikolojik
    for p in psych:
        weight = 2 if p["significance"] == "major" else 1
        entry = {"price": p["level"], "method": "Psychological", "weight": weight}
        if p["type"] == "support":
            all_supports.append(entry)
        else:
            all_resistances.append(entry)

    # Ağırlığa göre sırala
    all_supports.sort(key=lambda x: x["weight"], reverse=True)
    all_resistances.sort(key=lambda x: x["weight"], reverse=True)

    return {
        "supports": all_supports,
        "resistances": all_resistances,
        "fibonacci": fib_ret,
        "fib_extensions": fib_ext,
        "pivot_points": {
            "classic": classic_pp,
            "camarilla": camarilla_pp,
            "woodie": woodie_pp,
            "demark": demark_pp,
        },
        "volume_profile": vol_prof,
        "order_blocks": obs,
        "fvg": fvgs,
        "trend_lines": tlines,
        "chart_patterns": chart_pats,
        "swing_points": swings,
    }
