"""
VibeTrader Pro - TAM KAPASİTE İndikatör Motoru
67 hesaplanan indikatör + 45 puanlama kriteri
Trend (32), Momentum (20), Volatilite (8), Hacim (10)
"""

import pandas as pd
import numpy as np
import ta as ta_lib


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """67 teknik indikatörü hesaplar ve DataFrame'e ekler."""
    df = df.copy()
    c = df["close"]
    h = df["high"]
    l = df["low"]
    v = df["volume"]
    o = df["open"]
    n = len(df)

    # ═══════════════════════════════════════════════
    # TREND İNDİKATÖRLERİ (32 hesaplama)
    # ═══════════════════════════════════════════════

    # 1-7. EMA ailesi
    for w in [9, 12, 21, 26, 50, 100, 200]:
        df[f"ema_{w}"] = ta_lib.trend.ema_indicator(c, window=w)

    # 8-12. SMA ailesi
    for w in [10, 20, 50, 100, 200]:
        df[f"sma_{w}"] = ta_lib.trend.sma_indicator(c, window=w)

    # 13. WMA (Weighted Moving Average)
    df["wma_20"] = ta_lib.trend.wma_indicator(c, window=20)

    # 14. DEMA (Double EMA)
    ema_20 = ta_lib.trend.ema_indicator(c, window=20)
    df["dema_20"] = 2 * ema_20 - ta_lib.trend.ema_indicator(ema_20, window=20)

    # 15. TEMA (Triple EMA)
    ema1 = ta_lib.trend.ema_indicator(c, window=20)
    ema2 = ta_lib.trend.ema_indicator(ema1, window=20)
    ema3 = ta_lib.trend.ema_indicator(ema2, window=20)
    df["tema_20"] = 3 * ema1 - 3 * ema2 + ema3

    # 16. HMA (Hull Moving Average) = WMA(2*WMA(n/2) - WMA(n), sqrt(n))
    wma_half = ta_lib.trend.wma_indicator(c, window=10)
    wma_full = ta_lib.trend.wma_indicator(c, window=20)
    hull_raw = 2 * wma_half - wma_full
    df["hma_20"] = ta_lib.trend.wma_indicator(hull_raw, window=4)  # sqrt(20) ≈ 4

    # 17. McGinley Dynamic
    md = pd.Series(index=df.index, dtype=float)
    md.iloc[0] = c.iloc[0]
    for j in range(1, n):
        if pd.isna(md.iloc[j-1]) or md.iloc[j-1] == 0:
            md.iloc[j] = c.iloc[j]
        else:
            md.iloc[j] = md.iloc[j-1] + (c.iloc[j] - md.iloc[j-1]) / (20 * (c.iloc[j] / md.iloc[j-1]) ** 4)
    df["mcginley"] = md

    # 18-20. MACD
    macd_obj = ta_lib.trend.MACD(c, window_slow=26, window_fast=12, window_sign=9)
    df["macd"] = macd_obj.macd()
    df["macd_signal"] = macd_obj.macd_signal()
    df["macd_hist"] = macd_obj.macd_diff()

    # 21-23. ADX + DI
    adx_obj = ta_lib.trend.ADXIndicator(h, l, c, window=14)
    df["adx"] = adx_obj.adx()
    df["di_plus"] = adx_obj.adx_pos()
    df["di_minus"] = adx_obj.adx_neg()

    # 24-27. Ichimoku
    ich = ta_lib.trend.IchimokuIndicator(h, l, window1=9, window2=26, window3=52)
    df["ichi_a"] = ich.ichimoku_a()
    df["ichi_b"] = ich.ichimoku_b()
    df["ichi_base"] = ich.ichimoku_base_line()
    df["ichi_conv"] = ich.ichimoku_conversion_line()

    # 28-29. Parabolic SAR
    psar = ta_lib.trend.PSARIndicator(h, l, c, step=0.02, max_step=0.2)
    df["psar_up"] = psar.psar_up()
    df["psar_down"] = psar.psar_down()

    # 30-31. Aroon
    aroon = ta_lib.trend.AroonIndicator(h, l, window=25)
    df["aroon_up"] = aroon.aroon_up()
    df["aroon_down"] = aroon.aroon_down()

    # 32-33. Vortex
    vortex = ta_lib.trend.VortexIndicator(h, l, c, window=14)
    df["vortex_pos"] = vortex.vortex_indicator_pos()
    df["vortex_neg"] = vortex.vortex_indicator_neg()

    # 34. TRIX
    df["trix"] = ta_lib.trend.trix(c, window=15)

    # 35. Mass Index
    df["mass_index"] = ta_lib.trend.mass_index(h, l, window_fast=9, window_slow=25)

    # 36. CCI
    df["cci"] = ta_lib.trend.cci(h, l, c, window=20)

    # 37. DPO
    df["dpo"] = ta_lib.trend.dpo(c, window=20)

    # 38-39. KST
    kst_obj = ta_lib.trend.KSTIndicator(c)
    df["kst"] = kst_obj.kst()
    df["kst_signal"] = kst_obj.kst_sig()

    # 40. STC
    df["stc"] = ta_lib.trend.stc(c, window_slow=50, window_fast=23, cycle=10)

    # 41-42. Supertrend (manuel)
    atr_st = ta_lib.volatility.average_true_range(h, l, c, window=10)
    hl2 = (h + l) / 2
    upper_band = hl2 + 3 * atr_st
    lower_band = hl2 - 3 * atr_st
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=float)
    supertrend.iloc[0] = upper_band.iloc[0] if pd.notna(upper_band.iloc[0]) else c.iloc[0]
    direction.iloc[0] = -1
    for j in range(1, n):
        if pd.isna(upper_band.iloc[j]) or pd.isna(lower_band.iloc[j]):
            supertrend.iloc[j] = supertrend.iloc[j-1]
            direction.iloc[j] = direction.iloc[j-1]
            continue
        if c.iloc[j] > supertrend.iloc[j-1]:
            supertrend.iloc[j] = lower_band.iloc[j]
            direction.iloc[j] = 1
        else:
            supertrend.iloc[j] = upper_band.iloc[j]
            direction.iloc[j] = -1
    df["supertrend"] = supertrend
    df["supertrend_dir"] = direction

    # 43. Coppock Curve = WMA(10, ROC(14) + ROC(11))
    roc_14 = c.pct_change(14) * 100
    roc_11 = c.pct_change(11) * 100
    coppock_raw = roc_14 + roc_11
    df["coppock"] = ta_lib.trend.wma_indicator(coppock_raw, window=10)

    # ═══════════════════════════════════════════════
    # MOMENTUM İNDİKATÖRLERİ (20 hesaplama)
    # ═══════════════════════════════════════════════

    # 44. RSI
    df["rsi"] = ta_lib.momentum.rsi(c, window=14)

    # 45-46. Stochastic
    stoch = ta_lib.momentum.StochasticOscillator(h, l, c, window=14, smooth_window=3)
    df["stoch_k"] = stoch.stoch()
    df["stoch_d"] = stoch.stoch_signal()

    # 47-48. Stochastic RSI
    stoch_rsi = ta_lib.momentum.StochRSIIndicator(c, window=14, smooth1=3, smooth2=3)
    df["stochrsi_k"] = stoch_rsi.stochrsi_k()
    df["stochrsi_d"] = stoch_rsi.stochrsi_d()

    # 49. Williams %R
    df["williams_r"] = ta_lib.momentum.williams_r(h, l, c, lbp=14)

    # 50. ROC
    df["roc"] = ta_lib.momentum.roc(c, window=12)

    # 51. TSI
    df["tsi"] = ta_lib.momentum.tsi(c, window_slow=25, window_fast=13)

    # 52. Ultimate Oscillator
    df["uo"] = ta_lib.momentum.ultimate_oscillator(h, l, c, window1=7, window2=14, window3=28)

    # 53. Awesome Oscillator
    df["ao"] = ta_lib.momentum.awesome_oscillator(h, l, window1=5, window2=34)

    # 54. KAMA
    df["kama"] = ta_lib.momentum.kama(c, window=10, pow1=2, pow2=30)

    # 55-57. PPO
    ppo = ta_lib.momentum.PercentagePriceOscillator(c, window_slow=26, window_fast=12, window_sign=9)
    df["ppo"] = ppo.ppo()
    df["ppo_signal"] = ppo.ppo_signal()
    df["ppo_hist"] = ppo.ppo_hist()

    # 58-59. PVO
    pvo = ta_lib.momentum.PercentageVolumeOscillator(v, window_slow=26, window_fast=12, window_sign=9)
    df["pvo"] = pvo.pvo()
    df["pvo_signal"] = pvo.pvo_signal()

    # 60. MFI
    df["mfi"] = ta_lib.volume.money_flow_index(h, l, c, v, window=14)

    # 61-62. Elder Ray (Bull Power / Bear Power)
    ema_13 = ta_lib.trend.ema_indicator(c, window=13)
    df["elder_bull"] = h - ema_13
    df["elder_bear"] = l - ema_13

    # 63. Chande Momentum Oscillator (CMO)
    gains = (c - c.shift(1)).clip(lower=0)
    losses = (c.shift(1) - c).clip(lower=0)
    sum_gains = gains.rolling(14).sum()
    sum_losses = losses.rolling(14).sum()
    denom = sum_gains + sum_losses
    df["cmo"] = ((sum_gains - sum_losses) / denom.replace(0, np.nan)) * 100

    # 64. Balance of Power
    df["bop"] = ((c - o) / (h - l).replace(0, np.nan)).rolling(14).mean()

    # 65. Relative Vigor Index (RVI)
    rvi_num = ((c - o) + 2*(c.shift(1) - o.shift(1)) + 2*(c.shift(2) - o.shift(2)) + (c.shift(3) - o.shift(3))) / 6
    rvi_den = ((h - l) + 2*(h.shift(1) - l.shift(1)) + 2*(h.shift(2) - l.shift(2)) + (h.shift(3) - l.shift(3))) / 6
    df["rvi"] = (rvi_num / rvi_den.replace(0, np.nan)).rolling(10).mean()

    # 66. Connors RSI = (RSI(3) + RSI_streak(2) + Percentile_Rank(100)) / 3
    rsi_3 = ta_lib.momentum.rsi(c, window=3)
    streak = pd.Series(0.0, index=df.index)
    for j in range(1, n):
        if c.iloc[j] > c.iloc[j-1]:
            streak.iloc[j] = streak.iloc[j-1] + 1 if streak.iloc[j-1] > 0 else 1
        elif c.iloc[j] < c.iloc[j-1]:
            streak.iloc[j] = streak.iloc[j-1] - 1 if streak.iloc[j-1] < 0 else -1
        else:
            streak.iloc[j] = 0
    rsi_streak = ta_lib.momentum.rsi(streak, window=2)
    pct_rank = c.pct_change().rolling(100).apply(lambda x: (x < x.iloc[-1]).sum() / len(x) * 100 if len(x) > 0 else 50, raw=False)
    df["connors_rsi"] = (rsi_3 + rsi_streak + pct_rank) / 3

    # ═══════════════════════════════════════════════
    # VOLATİLİTE İNDİKATÖRLERİ (8 hesaplama)
    # ═══════════════════════════════════════════════

    # 67-71. Bollinger Bands
    bb = ta_lib.volatility.BollingerBands(c, window=20, window_dev=2)
    df["bb_upper"] = bb.bollinger_hband()
    df["bb_mid"] = bb.bollinger_mavg()
    df["bb_lower"] = bb.bollinger_lband()
    df["bb_width"] = bb.bollinger_wband()
    df["bb_pband"] = bb.bollinger_pband()

    # 72-76. Keltner Channel
    kc = ta_lib.volatility.KeltnerChannel(h, l, c, window=20, window_atr=10)
    df["kc_upper"] = kc.keltner_channel_hband()
    df["kc_mid"] = kc.keltner_channel_mband()
    df["kc_lower"] = kc.keltner_channel_lband()
    df["kc_width"] = kc.keltner_channel_wband()
    df["kc_pband"] = kc.keltner_channel_pband()

    # 77-81. Donchian Channel
    dc = ta_lib.volatility.DonchianChannel(h, l, c, window=20)
    df["dc_upper"] = dc.donchian_channel_hband()
    df["dc_mid"] = dc.donchian_channel_mband()
    df["dc_lower"] = dc.donchian_channel_lband()
    df["dc_width"] = dc.donchian_channel_wband()
    df["dc_pband"] = dc.donchian_channel_pband()

    # 82. ATR
    df["atr"] = ta_lib.volatility.average_true_range(h, l, c, window=14)

    # 83. Ulcer Index
    df["ulcer"] = ta_lib.volatility.ulcer_index(c, window=14)

    # 84. Historical Volatility
    df["hist_vol"] = c.pct_change().rolling(window=20).std() * np.sqrt(365)

    # 85. Chaikin Volatility
    hl_diff = h - l
    ema_hl = hl_diff.ewm(span=10).mean()
    df["chaikin_vol"] = ((ema_hl - ema_hl.shift(10)) / ema_hl.shift(10).replace(0, np.nan)) * 100

    # 86. Choppiness Index
    atr_1 = ta_lib.volatility.average_true_range(h, l, c, window=1)
    atr_sum = atr_1.rolling(14).sum()
    hh = h.rolling(14).max()
    ll = l.rolling(14).min()
    denom_chop = (hh - ll).replace(0, np.nan)
    df["choppiness"] = 100 * np.log10(atr_sum / denom_chop) / np.log10(14)

    # ═══════════════════════════════════════════════
    # HACİM İNDİKATÖRLERİ (10 hesaplama)
    # ═══════════════════════════════════════════════

    # 87. OBV
    df["obv"] = ta_lib.volume.on_balance_volume(c, v)

    # 88. CMF
    df["cmf"] = ta_lib.volume.chaikin_money_flow(h, l, c, v, window=20)

    # 89. EMV
    df["emv"] = ta_lib.volume.ease_of_movement(h, l, v, window=14)

    # 90. Force Index
    df["force_index"] = ta_lib.volume.force_index(c, v, window=13)

    # 91. VPT
    df["vpt"] = ta_lib.volume.volume_price_trend(c, v)

    # 92. ADL
    df["adl"] = ta_lib.volume.acc_dist_index(h, l, c, v)

    # 93. NVI
    df["nvi"] = ta_lib.volume.negative_volume_index(c, v)

    # 94. VWAP
    typical_price = (h + l + c) / 3
    cum_vol = v.cumsum()
    cum_tp_vol = (typical_price * v).cumsum()
    df["vwap"] = cum_tp_vol / cum_vol.replace(0, np.nan)

    # 95. Volume SMA + Ratio
    df["vol_sma_20"] = v.rolling(window=20).mean()
    df["vol_ratio"] = v / df["vol_sma_20"].replace(0, np.nan)

    # 96. Klinger Volume Oscillator (KVO)
    trend_kl = pd.Series(0, index=df.index)
    hlc = h + l + c
    for j in range(1, n):
        trend_kl.iloc[j] = 1 if hlc.iloc[j] > hlc.iloc[j-1] else -1
    dm = h - l
    cm = pd.Series(0.0, index=df.index)
    for j in range(1, n):
        if trend_kl.iloc[j] == trend_kl.iloc[j-1]:
            cm.iloc[j] = cm.iloc[j-1] + dm.iloc[j]
        else:
            cm.iloc[j] = dm.iloc[j-1] + dm.iloc[j]
    vf = v * abs(2 * dm / cm.replace(0, np.nan) - 1) * trend_kl * 100
    df["klinger"] = vf.ewm(span=34).mean() - vf.ewm(span=55).mean()
    df["klinger_signal"] = df["klinger"].ewm(span=13).mean()

    return df


# ═══════════════════════════════════════════════════
# İNDİKATÖR PUANLAMA (45 kriter)
# ═══════════════════════════════════════════════════

# Module-level weight dictionary (used by score_all_indicators and score_selected_indicators)
INDICATOR_WEIGHTS = {
    # Trend (ağırlık yüksek)
    "EMA Ribbon": 1.5, "SMA Cross": 1.4, "Fiyat/EMA200": 1.5, "HMA": 1.0, "McGinley": 0.8,
    "MACD": 1.5, "ADX/DI": 1.5, "Ichimoku": 1.3, "PSAR": 1.2, "Supertrend": 1.4,
    "Aroon": 1.0, "Vortex": 0.8, "TRIX": 0.7, "KST": 0.8, "STC": 0.9,
    "Coppock": 0.9, "DPO": 0.6, "Mass Index": 0.5,
    # Momentum
    "RSI": 1.3, "RSI Divergence": 1.6, "Stochastic": 1.0, "StochRSI": 0.9,
    "Williams %R": 0.8, "CCI": 0.9, "ROC": 0.7, "TSI": 0.8, "UO": 0.7,
    "AO": 0.7, "PPO": 0.8, "Elder Ray": 1.1, "CMO": 0.8, "BOP": 0.7,
    "Connors RSI": 0.9, "RVI": 0.7,
    # Volatilite
    "BB Position": 1.0, "Squeeze": 1.3, "Keltner": 0.7, "Donchian": 0.8, "Choppiness": 0.8,
    # Hacim
    "OBV": 1.2, "CMF": 1.1, "Force Index": 0.8, "MFI": 1.0,
    "Volume Spike": 1.0, "PVO": 0.6, "Klinger": 0.9,
}

def score_all_indicators(df: pd.DataFrame) -> dict:
    """
    67 indikatörden 45 puanlama kriteri üretir.
    Her kriter -1 ile +1 arası, ağırlıklı birleştirilir.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    scores = {}

    def _s(val):
        return val if pd.notna(val) else None

    # ── TREND (17 kriter) ──

    # 1. EMA Ribbon (9/21/50/200 sıralama)
    emas = [_s(last.get(f"ema_{w}")) for w in [9, 21, 50, 200]]
    if all(e is not None for e in emas):
        bullish_order = sum(1 for j in range(len(emas)-1) if emas[j] > emas[j+1])
        scores["EMA Ribbon"] = round((bullish_order - 1.5) / 1.5, 2)
    else:
        scores["EMA Ribbon"] = 0

    # 2. SMA Cross (50/200 Golden/Death Cross)
    sma50 = _s(last.get("sma_50"))
    sma200 = _s(last.get("sma_200"))
    if sma50 is not None and sma200 is not None:
        scores["SMA Cross"] = 0.9 if sma50 > sma200 else -0.9
    else:
        scores["SMA Cross"] = 0

    # 3. Fiyat vs EMA200
    ema200 = _s(last.get("ema_200"))
    if ema200 and ema200 > 0:
        dist = (last["close"] - ema200) / ema200
        scores["Fiyat/EMA200"] = round(np.clip(dist * 10, -1, 1), 2)
    else:
        scores["Fiyat/EMA200"] = 0

    # 4. HMA yönü
    hma = _s(last.get("hma_20"))
    hma_prev = _s(prev.get("hma_20"))
    if hma is not None and hma_prev is not None:
        if hma > hma_prev:
            scores["HMA"] = 0.7 if last["close"] > hma else 0.3
        else:
            scores["HMA"] = -0.7 if last["close"] < hma else -0.3
    else:
        scores["HMA"] = 0

    # 5. McGinley Dynamic
    mcg = _s(last.get("mcginley"))
    if mcg is not None:
        scores["McGinley"] = 0.6 if last["close"] > mcg else -0.6
    else:
        scores["McGinley"] = 0

    # 6. MACD
    macd = _s(last.get("macd"))
    macd_sig = _s(last.get("macd_signal"))
    hist = _s(last.get("macd_hist"))
    prev_hist = _s(prev.get("macd_hist"))
    if macd is not None and macd_sig is not None:
        s = 0
        s += 0.3 if macd > macd_sig else -0.3
        s += 0.2 if macd > 0 else -0.2
        if hist is not None and prev_hist is not None:
            s += 0.2 if hist > prev_hist else -0.2
            s += 0.15 if hist > 0 else -0.15
        scores["MACD"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["MACD"] = 0

    # 7. ADX/DI
    adx = _s(last.get("adx"))
    dip = _s(last.get("di_plus"))
    dim = _s(last.get("di_minus"))
    if adx is not None and dip is not None and dim is not None:
        if adx > 25:
            strength = min(adx / 50, 1)
            scores["ADX/DI"] = round(strength if dip > dim else -strength, 2)
        else:
            scores["ADX/DI"] = 0
    else:
        scores["ADX/DI"] = 0

    # 8. Ichimoku (4 alt sinyal birleşik)
    ich_s = 0
    ia, ib = _s(last.get("ichi_a")), _s(last.get("ichi_b"))
    ic, ib2 = _s(last.get("ichi_conv")), _s(last.get("ichi_base"))
    if ia is not None and ib is not None:
        cloud_top, cloud_bot = max(ia, ib), min(ia, ib)
        if last["close"] > cloud_top: ich_s += 0.35
        elif last["close"] < cloud_bot: ich_s -= 0.35
        ich_s += 0.15 if ia > ib else -0.15
        if ic is not None and ib2 is not None:
            ich_s += 0.25 if ic > ib2 else -0.25
            ich_s += 0.15 if last["close"] > ib2 else -0.15
    scores["Ichimoku"] = round(np.clip(ich_s, -1, 1), 2)

    # 9. Parabolic SAR
    psar_up = _s(last.get("psar_up"))
    if psar_up is not None and pd.notna(psar_up):
        scores["PSAR"] = 0.8
    elif _s(last.get("psar_down")) is not None and pd.notna(last.get("psar_down")):
        scores["PSAR"] = -0.8
    else:
        scores["PSAR"] = 0

    # 10. Aroon
    au, ad = _s(last.get("aroon_up")), _s(last.get("aroon_down"))
    if au is not None and ad is not None:
        scores["Aroon"] = round(np.clip((au - ad) / 100, -1, 1), 2)
    else:
        scores["Aroon"] = 0

    # 11. Vortex
    vp, vn = _s(last.get("vortex_pos")), _s(last.get("vortex_neg"))
    if vp is not None and vn is not None:
        scores["Vortex"] = round(np.clip((vp - vn) * 3, -1, 1), 2)
    else:
        scores["Vortex"] = 0

    # 12. TRIX
    trix = _s(last.get("trix"))
    scores["TRIX"] = round(np.clip(trix * 50, -1, 1), 2) if trix is not None else 0

    # 13. KST
    kst, kst_sig = _s(last.get("kst")), _s(last.get("kst_signal"))
    if kst is not None and kst_sig is not None:
        s = (0.5 if kst > kst_sig else -0.5) + (0.5 if kst > 0 else -0.5)
        scores["KST"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["KST"] = 0

    # 14. STC
    stc = _s(last.get("stc"))
    if stc is not None:
        scores["STC"] = round(np.clip((stc - 50) / 50, -1, 1), 2)
    else:
        scores["STC"] = 0

    # 15. Supertrend
    st_dir = _s(last.get("supertrend_dir"))
    scores["Supertrend"] = (0.9 if st_dir > 0 else -0.9) if st_dir is not None else 0

    # 16. Coppock Curve
    cop = _s(last.get("coppock"))
    cop_prev = _s(prev.get("coppock"))
    if cop is not None and cop_prev is not None:
        s = 0.5 if cop > 0 else -0.5
        s += 0.4 if cop > cop_prev else -0.4
        scores["Coppock"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["Coppock"] = 0

    # 17. DPO + Mass Index
    dpo = _s(last.get("dpo"))
    scores["DPO"] = round(np.clip(dpo / (last["close"] * 0.02), -1, 1), 2) if dpo is not None else 0
    mi = _s(last.get("mass_index"))
    scores["Mass Index"] = (-0.5 if mi and mi > 27 else (0.3 if mi and 25 < mi < 26.5 else 0))

    # ── MOMENTUM (15 kriter) ──

    # 18. RSI
    rsi = _s(last.get("rsi"))
    if rsi is not None:
        if rsi > 80: scores["RSI"] = -1.0
        elif rsi > 70: scores["RSI"] = -0.7
        elif rsi > 60: scores["RSI"] = 0.3
        elif rsi > 50: scores["RSI"] = 0.5
        elif rsi > 40: scores["RSI"] = -0.3
        elif rsi > 30: scores["RSI"] = -0.5
        elif rsi > 20: scores["RSI"] = 0.7
        else: scores["RSI"] = 1.0
    else:
        scores["RSI"] = 0

    # 19. RSI Divergence
    rsi_div = 0
    if len(df) >= 14:
        rsi_now = _s(last.get("rsi"))
        rsi_prev14 = _s(df.iloc[-14].get("rsi"))
        pt = last["close"] - df["close"].iloc[-14]
        if rsi_now is not None and rsi_prev14 is not None:
            rt = rsi_now - rsi_prev14
            if pt > 0 and rt < -5: rsi_div = -0.8
            elif pt < 0 and rt > 5: rsi_div = 0.8
    scores["RSI Divergence"] = rsi_div

    # 20. Stochastic
    sk, sd = _s(last.get("stoch_k")), _s(last.get("stoch_d"))
    if sk is not None and sd is not None:
        s = (0.35 if sk > sd else -0.35)
        if sk > 80: s -= 0.55
        elif sk < 20: s += 0.55
        elif sk > 50: s += 0.2
        else: s -= 0.2
        scores["Stochastic"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["Stochastic"] = 0

    # 21. StochRSI
    srk, srd = _s(last.get("stochrsi_k")), _s(last.get("stochrsi_d"))
    if srk is not None and srd is not None:
        s = (0.4 if srk > srd else -0.4)
        if srk > 0.8: s -= 0.5
        elif srk < 0.2: s += 0.5
        scores["StochRSI"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["StochRSI"] = 0

    # 22. Williams %R
    wr = _s(last.get("williams_r"))
    if wr is not None:
        if wr > -20: scores["Williams %R"] = -0.8
        elif wr > -50: scores["Williams %R"] = 0.3
        elif wr > -80: scores["Williams %R"] = -0.3
        else: scores["Williams %R"] = 0.8
    else:
        scores["Williams %R"] = 0

    # 23. CCI
    cci = _s(last.get("cci"))
    if cci is not None:
        if cci > 200: scores["CCI"] = -0.8
        elif cci > 100: scores["CCI"] = -0.4
        elif cci > 0: scores["CCI"] = 0.4
        elif cci > -100: scores["CCI"] = -0.4
        elif cci > -200: scores["CCI"] = 0.4
        else: scores["CCI"] = 0.8
    else:
        scores["CCI"] = 0

    # 24. ROC
    roc = _s(last.get("roc"))
    scores["ROC"] = round(np.clip(roc / 10, -1, 1), 2) if roc is not None else 0

    # 25. TSI
    tsi = _s(last.get("tsi"))
    scores["TSI"] = round(np.clip(tsi / 30, -1, 1), 2) if tsi is not None else 0

    # 26. Ultimate Oscillator
    uo = _s(last.get("uo"))
    if uo is not None:
        if uo > 70: scores["UO"] = -0.6
        elif uo > 50: scores["UO"] = 0.5
        elif uo > 30: scores["UO"] = -0.5
        else: scores["UO"] = 0.6
    else:
        scores["UO"] = 0

    # 27. Awesome Oscillator
    ao = _s(last.get("ao"))
    prev_ao = _s(prev.get("ao"))
    if ao is not None:
        s = 0.4 if ao > 0 else -0.4
        if prev_ao is not None: s += 0.3 if ao > prev_ao else -0.3
        scores["AO"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["AO"] = 0

    # 28. PPO
    ppo_val, ppo_sig = _s(last.get("ppo")), _s(last.get("ppo_signal"))
    if ppo_val is not None and ppo_sig is not None:
        s = (0.5 if ppo_val > ppo_sig else -0.5) + (0.3 if ppo_val > 0 else -0.3)
        scores["PPO"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["PPO"] = 0

    # 29. Elder Ray
    eb, ebr = _s(last.get("elder_bull")), _s(last.get("elder_bear"))
    if eb is not None and ebr is not None:
        s = 0
        if eb > 0: s += 0.4
        else: s -= 0.4
        if ebr < 0: s -= 0.2
        else: s += 0.2
        if eb > 0 and ebr > 0: s = 0.8  # Çok güçlü bullish
        elif eb < 0 and ebr < 0: s = -0.8  # Çok güçlü bearish
        scores["Elder Ray"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["Elder Ray"] = 0

    # 30. CMO
    cmo = _s(last.get("cmo"))
    if cmo is not None:
        if cmo > 50: scores["CMO"] = 0.8
        elif cmo > 0: scores["CMO"] = 0.4
        elif cmo > -50: scores["CMO"] = -0.4
        else: scores["CMO"] = -0.8
    else:
        scores["CMO"] = 0

    # 31. Balance of Power
    bop = _s(last.get("bop"))
    scores["BOP"] = round(np.clip(bop * 3, -1, 1), 2) if bop is not None else 0

    # 32. Connors RSI
    crsi = _s(last.get("connors_rsi"))
    if crsi is not None:
        if crsi > 80: scores["Connors RSI"] = -0.7
        elif crsi > 50: scores["Connors RSI"] = 0.5
        elif crsi > 20: scores["Connors RSI"] = -0.5
        else: scores["Connors RSI"] = 0.7
    else:
        scores["Connors RSI"] = 0

    # 33. RVI
    rvi = _s(last.get("rvi"))
    if rvi is not None:
        scores["RVI"] = round(np.clip(rvi * 3, -1, 1), 2)
    else:
        scores["RVI"] = 0

    # ── VOLATİLİTE (5 kriter) ──

    # 34. BB pozisyonu
    bb_p = _s(last.get("bb_pband"))
    if bb_p is not None:
        if bb_p > 1.0: scores["BB Position"] = -0.8
        elif bb_p > 0.8: scores["BB Position"] = -0.4
        elif bb_p < 0.0: scores["BB Position"] = 0.8
        elif bb_p < 0.2: scores["BB Position"] = 0.4
        else: scores["BB Position"] = round((0.5 - bb_p) * 1.5, 2)
    else:
        scores["BB Position"] = 0

    # 35. BB Squeeze (BB width < Keltner width)
    bb_w, kc_w = _s(last.get("bb_width")), _s(last.get("kc_width"))
    if bb_w is not None and kc_w is not None and kc_w > 0:
        if bb_w < kc_w:  # Squeeze aktif
            mom = _s(last.get("macd_hist"))
            scores["Squeeze"] = (0.7 if mom and mom > 0 else -0.7) if mom is not None else 0
        else:
            scores["Squeeze"] = 0
    else:
        scores["Squeeze"] = 0

    # 36. Keltner
    kc_p = _s(last.get("kc_pband"))
    if kc_p is not None:
        if kc_p > 1.0: scores["Keltner"] = -0.6
        elif kc_p < 0.0: scores["Keltner"] = 0.6
        else: scores["Keltner"] = round((0.5 - kc_p) * 1.2, 2)
    else:
        scores["Keltner"] = 0

    # 37. Donchian
    dc_p = _s(last.get("dc_pband"))
    if dc_p is not None:
        if dc_p > 0.9: scores["Donchian"] = 0.6
        elif dc_p < 0.1: scores["Donchian"] = -0.6
        else: scores["Donchian"] = round((dc_p - 0.5) * 1.2, 2)
    else:
        scores["Donchian"] = 0

    # 38. Choppiness Index (düşük = trend, yüksek = range)
    chop = _s(last.get("choppiness"))
    if chop is not None:
        if chop > 61.8:
            scores["Choppiness"] = 0  # Range, sinyal verme
        elif chop < 38.2:
            # Güçlü trend - yönü diğer indikatörlerden al
            scores["Choppiness"] = 0.5 if scores.get("MACD", 0) > 0 else -0.5
        else:
            scores["Choppiness"] = 0
    else:
        scores["Choppiness"] = 0

    # ── HACİM (7 kriter) ──

    # 39. OBV Trend
    if len(df) >= 20 and "obv" in df.columns:
        obv_sma = df["obv"].rolling(20).mean()
        if pd.notna(obv_sma.iloc[-1]) and _s(last.get("obv")) is not None:
            scores["OBV"] = 0.6 if last["obv"] > obv_sma.iloc[-1] else -0.6
        else:
            scores["OBV"] = 0
    else:
        scores["OBV"] = 0

    # 40. CMF
    cmf = _s(last.get("cmf"))
    scores["CMF"] = round(np.clip(cmf * 4, -1, 1), 2) if cmf is not None else 0

    # 41. Force Index
    fi = _s(last.get("force_index"))
    scores["Force Index"] = (0.6 if fi > 0 else -0.6) if fi is not None else 0

    # 42. MFI
    mfi = _s(last.get("mfi"))
    if mfi is not None:
        if mfi > 80: scores["MFI"] = -0.7
        elif mfi > 50: scores["MFI"] = 0.4
        elif mfi > 20: scores["MFI"] = -0.4
        else: scores["MFI"] = 0.7
    else:
        scores["MFI"] = 0

    # 43. Volume Spike
    vr = _s(last.get("vol_ratio"))
    if vr is not None:
        price_up = last["close"] > prev["close"]
        if vr > 2.0: scores["Volume Spike"] = 0.7 if price_up else -0.7
        elif vr > 1.5: scores["Volume Spike"] = 0.3 if price_up else -0.3
        else: scores["Volume Spike"] = 0
    else:
        scores["Volume Spike"] = 0

    # 44. PVO
    pvo_val, pvo_sig = _s(last.get("pvo")), _s(last.get("pvo_signal"))
    scores["PVO"] = (0.5 if pvo_val > pvo_sig else -0.5) if pvo_val is not None and pvo_sig is not None else 0

    # 45. Klinger
    kl, kl_sig = _s(last.get("klinger")), _s(last.get("klinger_signal"))
    if kl is not None and kl_sig is not None:
        s = 0.5 if kl > kl_sig else -0.5
        s += 0.3 if kl > 0 else -0.3
        scores["Klinger"] = round(np.clip(s, -1, 1), 2)
    else:
        scores["Klinger"] = 0

    # ── AĞIRLIKLI TOPLAM ──
    weighted_sum = 0
    weight_total = 0
    for name, val in scores.items():
        w = INDICATOR_WEIGHTS.get(name, 1.0)
        weighted_sum += val * w
        weight_total += w

    normalized = round((weighted_sum / weight_total) * 10, 1) if weight_total > 0 else 0

    if normalized >= 2.5:
        bias = "LONG"
    elif normalized <= -2.5:
        bias = "SHORT"
    else:
        bias = "NÖTR"

    return {
        "scores": scores,
        "total_raw": round(weighted_sum, 2),
        "total_normalized": normalized,
        "bias": bias,
        "indicator_count": len(scores),
    }


def score_selected_indicators(df: pd.DataFrame, keys: list[str]) -> dict:
    """
    Score only the selected indicator keys from a strategy variant.
    Returns the same structure as score_all_indicators but only considers
    the given keys for the weighted sum.

    Args:
        df: DataFrame with all indicators computed
        keys: List of scoring key names (e.g. ["EMA Ribbon", "RSI", "OBV"])

    Returns:
        dict with scores, total_raw, total_normalized, bias, indicator_count
    """
    full = score_all_indicators(df)
    all_scores = full["scores"]

    selected_scores = {k: all_scores.get(k, 0) for k in keys}

    weighted_sum = 0
    weight_total = 0
    for name, val in selected_scores.items():
        w = INDICATOR_WEIGHTS.get(name, 1.0)
        weighted_sum += val * w
        weight_total += w

    normalized = round((weighted_sum / weight_total) * 10, 1) if weight_total > 0 else 0

    if normalized >= 2.5:
        bias = "LONG"
    elif normalized <= -2.5:
        bias = "SHORT"
    else:
        bias = "NÖTR"

    return {
        "scores": selected_scores,
        "all_scores": all_scores,
        "total_raw": round(weighted_sum, 2),
        "total_normalized": normalized,
        "bias": bias,
        "indicator_count": len(selected_scores),
    }
