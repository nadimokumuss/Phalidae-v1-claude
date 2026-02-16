# Phalidae - Analiz Yöntemleri Referansı

Bu doküman Phalidae'nin teknik analiz bilgisini nereden aldığını, nasıl uyguladığını ve hangi formüllerle puanladığını detaylı olarak açıklar.

---

## Bilgi Kaynakları Özeti

Phalidae üç katmandan teknik analiz bilgisi alır:

| Katman | Kaynak | Yöntem | Dosya |
|--------|--------|--------|-------|
| 67 Teknik İndikatör | `ta` Python kütüphanesi + elle kodlanmış formüller | Hazır akademik formüller | `scripts/indicators.py` |
| 60 Mum Formasyonu | Elle kodlanmış deterministik kurallar | Japon mum analizi kitaplarından çeviri | `scripts/patterns.py` |
| 12 S/R Yöntemi | Elle kodlanmış algoritmalar + `scipy.stats` | Matematik (clustering, regresyon, Fibonacci) | `scripts/levels.py` |
| 6 Market Rejimi | Elle kodlanmış sınıflandırma | İndikatör eşik değerleri ile karar ağacı | `scripts/regime.py` |
| 45 Puanlama Kriteri | Elle kodlanmış skoring mantığı | İndikatör → [-1, +1] skor dönüşümü | `scripts/indicators.py` |
| 4 Kategori Haritası | Elle tanımlanmış sabit sözlük | Trend/Entry/Volume/Volatility grupları | `scripts/strategy/catalog.py` |

**Önemli:** Proje hiçbir makine öğrenmesi modeli kullanmaz. Tüm analiz kuralları deterministiktir — aynı girdiye her zaman aynı çıktıyı verir. "Öğrenme" yalnızca strateji optimizer'ında gerçekleşir: farklı indikatör kombinasyonlarını backtest ederek en iyi performans gösterenleri seçer.

---

## 1. Teknik İndikatörler (67 adet)

**Dosya:** `scripts/indicators.py` → `compute_all_indicators(df)`
**Bağımlılık:** `ta` kütüphanesi (v0.11+) — [github.com/bukosabino/ta](https://github.com/bukosabino/ta)

`ta` kütüphanesi, akademik kaynaklarda tanımlanan teknik analiz formüllerini Python'a implementasyon olarak sunar. Phalidae bunları doğrudan çağırır — formülleri kendisi icat etmez.

### 1.1 Trend İndikatörleri (32 hesaplama → 16 puanlama kriteri)

| # | İndikatör | Parametre | Kaynak | Formül Özeti |
|---|-----------|-----------|--------|--------------|
| 1-7 | EMA ailesi | 9, 12, 21, 26, 50, 100, 200 | `ta.trend.ema_indicator()` | Üstel hareketli ortalama. Yeni veriye daha fazla ağırlık verir. |
| 8-12 | SMA ailesi | 10, 20, 50, 100, 200 | `ta.trend.sma_indicator()` | Basit hareketli ortalama. Tüm verilere eşit ağırlık. |
| 13 | WMA | 20 | `ta.trend.wma_indicator()` | Ağırlıklı hareketli ortalama. Yakın veriye lineer artan ağırlık. |
| 14 | DEMA | 20 | Elle: `2*EMA - EMA(EMA)` | Çift üstel ortalama. EMA'nın gecikmesini azaltır. |
| 15 | TEMA | 20 | Elle: `3*EMA1 - 3*EMA2 + EMA3` | Üçlü üstel ortalama. DEMA'dan daha az gecikme. |
| 16 | HMA (Hull) | 20 | Elle: `WMA(2*WMA(n/2)-WMA(n), √n)` | Alan Hull'un formülü. En düşük gecikmeye sahip MA. |
| 17 | McGinley Dynamic | 20 | Elle: iteratif formül | Piyasa hızına otomatik uyum sağlayan ortalama. |
| 18-20 | MACD | 12/26/9 | `ta.trend.MACD()` | Gerald Appel'in momentum osilatörü. Sinyal + histogram. |
| 21-23 | ADX + DI | 14 | `ta.trend.ADXIndicator()` | Welles Wilder'ın trend gücü ölçümü. |
| 24-27 | Ichimoku | 9/26/52 | `ta.trend.IchimokuIndicator()` | Goichi Hosoda'nın 5 bileşenli bulut sistemi. |
| 28-29 | Parabolic SAR | 0.02/0.2 | `ta.trend.PSARIndicator()` | Wilder'ın stop-and-reverse sistemi. |
| 30-31 | Aroon | 25 | `ta.trend.AroonIndicator()` | Tushar Chande'nin trend başlangıcı tespiti. |
| 32-33 | Vortex | 14 | `ta.trend.VortexIndicator()` | Etienne Botes'in yön göstergesi. |
| 34 | TRIX | 15 | `ta.trend.trix()` | Üçlü EMA'nın yüzde değişimi. Gürültü filtresi. |
| 35 | Mass Index | 9/25 | `ta.trend.mass_index()` | Donald Dorsey'in trend dönüş tespiti. |
| 36 | CCI | 20 | `ta.trend.cci()` | Donald Lambert'in döngü tespiti. |
| 37 | DPO | 20 | `ta.trend.dpo()` | Detrended Price Oscillator. Trend kaldırılmış fiyat. |
| 38-39 | KST | varsayılan | `ta.trend.KSTIndicator()` | Martin Pring'in çoklu ROC birleşimi. |
| 40 | STC | 50/23/10 | `ta.trend.stc()` | Schaff Trend Cycle. MACD + Stochastic birleşimi. |
| 41-42 | Supertrend | ATR(10), çarpan=3 | Elle: iteratif band hesaplama | ATR tabanlı dinamik stop seviyesi. Yön bilgisi verir. |
| 43 | Coppock Curve | ROC(14)+ROC(11), WMA(10) | Elle + `ta.trend.wma_indicator()` | Edwin Coppock'un uzun vadeli dip tespiti. |

### 1.2 Momentum İndikatörleri (20 hesaplama → 15 puanlama kriteri)

| # | İndikatör | Parametre | Kaynak | Formül Özeti |
|---|-----------|-----------|--------|--------------|
| 44 | RSI | 14 | `ta.momentum.rsi()` | Wilder'ın göreceli güç endeksi. 0-100 arası. |
| 45-46 | Stochastic | 14/3 | `ta.momentum.StochasticOscillator()` | George Lane'in %K/%D osilatörü. |
| 47-48 | StochRSI | 14/3/3 | `ta.momentum.StochRSIIndicator()` | RSI'a uygulanan Stochastic. Daha hassas. |
| 49 | Williams %R | 14 | `ta.momentum.williams_r()` | Larry Williams'ın aşırı alım/satım göstergesi. |
| 50 | ROC | 12 | `ta.momentum.roc()` | Fiyat değişim hızı. |
| 51 | TSI | 25/13 | `ta.momentum.tsi()` | True Strength Index. Çift düzeltilmiş momentum. |
| 52 | Ultimate Oscillator | 7/14/28 | `ta.momentum.ultimate_oscillator()` | Larry Williams'ın çok periyotlu osilatörü. |
| 53 | Awesome Oscillator | 5/34 | `ta.momentum.awesome_oscillator()` | Bill Williams'ın momentum göstergesi. |
| 54 | KAMA | 10/2/30 | `ta.momentum.kama()` | Perry Kaufman'ın adaptif ortalaması. |
| 55-57 | PPO | 12/26/9 | `ta.momentum.PercentagePriceOscillator()` | MACD'nin yüzdelik versiyonu. |
| 58-59 | PVO | 12/26/9 | `ta.momentum.PercentageVolumeOscillator()` | Hacim osilatörü. |
| 60 | MFI | 14 | `ta.volume.money_flow_index()` | Hacim ağırlıklı RSI. |
| 61-62 | Elder Ray | EMA(13) | Elle: `High-EMA`, `Low-EMA` | Alexander Elder'ın boğa/ayı güç ölçümü. |
| 63 | CMO | 14 | Elle: `(gains-losses)/(gains+losses)*100` | Tushar Chande'nin momentum osilatörü. |
| 64 | BOP | 14 | Elle: `(close-open)/(high-low)` rolling avg | Balance of Power. Alıcı vs satıcı gücü. |
| 65 | RVI | 10 | Elle: OHLC tabanlı formül | Relative Vigor Index. Kapanış gücü ölçümü. |
| 66 | Connors RSI | 3/2/100 | Elle: `(RSI(3) + RSI_streak(2) + PctRank(100)) / 3` | Larry Connors'ın bileşik RSI'ı. |

### 1.3 Volatilite İndikatörleri (8 hesaplama → 5 puanlama kriteri)

| # | İndikatör | Parametre | Kaynak | Formül Özeti |
|---|-----------|-----------|--------|--------------|
| 67-71 | Bollinger Bands | 20/2σ | `ta.volatility.BollingerBands()` | John Bollinger'in standart sapma bantları. |
| 72-76 | Keltner Channel | 20/ATR(10) | `ta.volatility.KeltnerChannel()` | ATR tabanlı kanal. Squeeze tespitinde kullanılır. |
| 77-81 | Donchian Channel | 20 | `ta.volatility.DonchianChannel()` | Richard Donchian'ın yüksek/düşük kanalı. |
| 82 | ATR | 14 | `ta.volatility.average_true_range()` | Wilder'ın ortalama gerçek aralığı. |
| 83 | Ulcer Index | 14 | `ta.volatility.ulcer_index()` | Peter Martin'in düşüş riski ölçümü. |
| 84 | Historical Volatility | 20 | Elle: `pct_change().std() * √365` | Yıllıklaştırılmış tarihsel volatilite. |
| 85 | Chaikin Volatility | 10 | Elle: `(EMA(H-L) değişimi)` | Marc Chaikin'in volatilite ölçümü. |
| 86 | Choppiness Index | 14 | Elle: `100 * log10(ATR_sum / (HH-LL)) / log10(14)` | E.W. Dreiss'in trend/yatay piyasa ayrımı. |

### 1.4 Hacim İndikatörleri (10 hesaplama → 7 puanlama kriteri)

| # | İndikatör | Parametre | Kaynak | Formül Özeti |
|---|-----------|-----------|--------|--------------|
| 87 | OBV | — | `ta.volume.on_balance_volume()` | Joe Granville'in kümülatif hacim göstergesi. |
| 88 | CMF | 20 | `ta.volume.chaikin_money_flow()` | Chaikin'in para akışı. [-1, +1] arası. |
| 89 | EMV | 14 | `ta.volume.ease_of_movement()` | Richard Arms'ın hareket kolaylığı. |
| 90 | Force Index | 13 | `ta.volume.force_index()` | Alexander Elder'ın güç endeksi. |
| 91 | VPT | — | `ta.volume.volume_price_trend()` | Fiyat değişimine orantılı hacim. |
| 92 | ADL | — | `ta.volume.acc_dist_index()` | Chaikin'in birikim/dağılım çizgisi. |
| 93 | NVI | — | `ta.volume.negative_volume_index()` | Düşük hacimli günlerdeki fiyat hareketi. |
| 94 | VWAP | — | Elle: `cumsum(TP*V) / cumsum(V)` | Hacim ağırlıklı ortalama fiyat. |
| 95 | Volume SMA + Ratio | 20 | Elle: `V / SMA(V, 20)` | Hacim spike tespiti. |
| 96 | Klinger (KVO) | 34/55/13 | Elle: iteratif trend + hacim formül | Stephen Klinger'in hacim osilatörü. |

---

## 2. Puanlama Sistemi (45 kriter)

**Dosya:** `scripts/indicators.py` → `score_all_indicators(df)`

Her indikatör ham değerinden [-1.0, +1.0] arasında bir skora dönüştürülür:
- **+1.0** = Çok güçlü bullish sinyal
- **0.0** = Nötr / sinyal yok
- **-1.0** = Çok güçlü bearish sinyal

### Puanlama Yöntemleri

Dört farklı puanlama yaklaşımı kullanılır:

#### a) Eşik Bazlı (Threshold-Based)
İndikatör belirli seviyeleri aşınca skor atanır.
```
RSI > 80 → -1.0 (aşırı alım)
RSI 50-60 → +0.5 (bullish momentum)
RSI < 20 → +1.0 (aşırı satım, dönüş beklentisi)
```

#### b) Karşılaştırma Bazlı (Crossover-Based)
İki çizginin birbirine göre pozisyonu.
```
MACD > Signal → +0.3
MACD > 0 → +0.2 ek bonus
Histogram artan → +0.2 ek bonus
```

#### c) Pozisyon Bazlı (Position-Based)
Fiyatın bir bant veya seviyeye göre konumu.
```
BB %B > 1.0 → -0.8 (üst bandın üstünde)
BB %B < 0.0 → +0.8 (alt bandın altında)
```

#### d) Yön Bazlı (Direction-Based)
İndikatörün artıyor/azalıyor olması.
```
HMA yükseliyor & fiyat > HMA → +0.7
HMA düşüyor & fiyat < HMA → -0.7
```

### Ağırlık Sistemi

Her kriter bir ağırlığa sahiptir (`INDICATOR_WEIGHTS` dict):

| Kategori | Ağırlık Aralığı | En Yüksek Ağırlıklılar |
|----------|----------------|------------------------|
| Trend | 0.5 – 1.5 | EMA Ribbon (1.5), Fiyat/EMA200 (1.5), MACD (1.5), ADX/DI (1.5) |
| Momentum | 0.7 – 1.6 | RSI Divergence (1.6), RSI (1.3), Elder Ray (1.1) |
| Volatilite | 0.7 – 1.3 | Squeeze (1.3), BB Position (1.0) |
| Hacim | 0.6 – 1.2 | OBV (1.2), CMF (1.1) |

### Final Skor Hesaplama

```python
weighted_sum = Σ (skor_i × ağırlık_i)
weight_total = Σ ağırlık_i
normalized = (weighted_sum / weight_total) * 10

if normalized >= 2.5 → LONG
if normalized <= -2.5 → SHORT
else → NÖTR
```

---

## 3. Mum Formasyonları (60 adet)

**Dosya:** `scripts/patterns.py` → `detect_all_patterns(df)`
**Bağımlılık:** Yok — sadece `pandas` + `numpy`

Tüm formasyonlar elle kodlanmış if/else kurallarıdır. Temel kaynak: Steve Nison'un "Japanese Candlestick Charting Techniques" ve Gregory Morris'in "Candlestick Charting Explained" kitapları.

### Yardımcı Fonksiyonlar

Her formasyonda kullanılan temel ölçümler:

| Fonksiyon | Hesaplama | Kullanım |
|-----------|-----------|----------|
| `_body(o, c)` | `abs(close - open)` | Gövde büyüklüğü |
| `_upper_wick(o, h, c)` | `high - max(open, close)` | Üst fitil |
| `_lower_wick(o, l, c)` | `min(open, close) - low` | Alt fitil |
| `_range(h, l)` | `high - low` | Toplam menzil |
| `_body_pct(o, h, l, c)` | `body / range` | Gövdenin menzile oranı |
| `avg_body` | Son 20 mumun ortalama gövdesi | Referans büyüklük |

### 3.1 Tek Mum Formasyonları (16 adet)

| # | Formasyon | Yön | Güç | Tespit Kuralı |
|---|-----------|-----|-----|---------------|
| 1 | Doji | Nötr | 2 | body_pct < %5 |
| 2 | Dragonfly Doji | Bullish | 3 | body_pct < %5, alt fitil > %60 menzil, üst fitil < %10 |
| 3 | Gravestone Doji | Bearish | 3 | body_pct < %5, üst fitil > %60 menzil, alt fitil < %10 |
| 4 | Long-legged Doji | Nötr | 2 | body_pct < %10, her iki fitil > %30 menzil |
| 5 | Hammer | Bullish | 3 | Alt fitil > 2× gövde, üst fitil < 0.3× gövde, bullish |
| 6 | Inverted Hammer | Bullish | 2 | Üst fitil > 2× gövde, alt fitil < 0.3× gövde, bullish |
| 7 | Shooting Star | Bearish | 3 | Üst fitil > 2× gövde, alt fitil < 0.3× gövde, bearish |
| 8 | Hanging Man | Bearish | 3 | Alt fitil > 2× gövde, üst fitil < 0.3× gövde, bearish |
| 9 | Bullish Marubozu | Bullish | 4 | body_pct > %90, fitiller < %5 menzil, bullish |
| 10 | Bearish Marubozu | Bearish | 4 | body_pct > %90, fitiller < %5 menzil, bearish |
| 11 | Spinning Top | Nötr | 1 | body_pct %10-40, her iki fitil > 0.8× gövde |
| 12 | Bullish Pin Bar | Bullish | 4 | Alt fitil > %60 menzil, gövde < %25, üst fitil < %15 |
| 13 | Bearish Pin Bar | Bearish | 4 | Üst fitil > %60 menzil, gövde < %25, alt fitil < %15 |
| 14 | High Wave | Nötr | 2 | body_pct < %20, fitiller > %35, menzil > 1.5× avg_body |
| 15 | Belt Hold Bullish | Bullish | 2 | Alt fitil < %2 menzil, gövde > 1.5× avg_body, bullish |
| 16 | Belt Hold Bearish | Bearish | 2 | Üst fitil < %2 menzil, gövde > 1.5× avg_body, bearish |

### 3.2 İki Mum Formasyonları (14 adet)

| # | Formasyon | Yön | Güç | Tespit Kuralı |
|---|-----------|-----|-----|---------------|
| 17 | Bullish Engulfing | Bullish | 4 | Bearish → Bullish, mevcut gövde öncekini tamamen yutar |
| 18 | Bearish Engulfing | Bearish | 4 | Bullish → Bearish, mevcut gövde öncekini tamamen yutar |
| 19 | Bullish Harami | Bullish | 2 | Bearish → küçük Bullish (önceki mumun içinde, < %50) |
| 20 | Bearish Harami | Bearish | 2 | Bullish → küçük Bearish (önceki mumun içinde, < %50) |
| 21 | Harami Cross | Yöne bağlı | 3 | Büyük mum → Doji (body_pct < %5), mumun içinde |
| 22 | Piercing Line | Bullish | 3 | Bearish → Bullish, önceki mumun ortasını geçer ama kapanışı aşmaz |
| 23 | Dark Cloud Cover | Bearish | 3 | Bullish → Bearish, önceki mumun ortasını geçer |
| 24 | Tweezer Top | Bearish | 3 | İki mumun tepeleri aynı (%2 tolerans), Bullish→Bearish |
| 25 | Tweezer Bottom | Bullish | 3 | İki mumun dipleri aynı (%2 tolerans), Bearish→Bullish |
| 26 | On Neck | Bearish | 2 | Bearish→Bullish, kapanış önceki dibi test eder |
| 27 | In Neck | Bearish | 2 | Bearish→Bullish, kapanış önceki kapanışa yakın |
| 28 | Thrusting | Bearish | 1 | Bearish→Bullish, kapanış ortayı geçemez |
| 29 | Separating Lines Bullish | Bullish | 2 | Aynı açılış, Bearish→Bullish, büyük gövde |
| 30 | Separating Lines Bearish | Bearish | 2 | Aynı açılış, Bullish→Bearish, büyük gövde |

### 3.3 Üç Mum Formasyonları (20 adet)

| # | Formasyon | Yön | Güç | Tespit Kuralı |
|---|-----------|-----|-----|---------------|
| 31 | Morning Star | Bullish | 5 | Büyük bearish + küçük gövde + büyük bullish (orta geçer) |
| 32 | Evening Star | Bearish | 5 | Büyük bullish + küçük gövde + büyük bearish (orta geçer) |
| 33 | Morning Doji Star | Bullish | 5 | Morning Star ama ortadaki mum Doji |
| 34 | Evening Doji Star | Bearish | 5 | Evening Star ama ortadaki mum Doji |
| 35 | Three White Soldiers | Bullish | 4-5 | Ardışık 3 bullish, artan kapanış/açılış, büyük gövdeler |
| 36 | Three Black Crows | Bearish | 4-5 | Ardışık 3 bearish, azalan kapanış/açılış, büyük gövdeler |
| 37 | Three Inside Up | Bullish | 4 | Bullish Harami + teyit (3. mum 1. mumun açılışını aşar) |
| 38 | Three Inside Down | Bearish | 4 | Bearish Harami + teyit |
| 39 | Three Outside Up | Bullish | 4 | Bullish Engulfing + teyit |
| 40 | Three Outside Down | Bearish | 4 | Bearish Engulfing + teyit |
| 41 | Abandoned Baby Bullish | Bullish | 5 | Bearish + Gap'li Doji + Bullish (çok nadir) |
| 42 | Abandoned Baby Bearish | Bearish | 5 | Bullish + Gap'li Doji + Bearish (çok nadir) |
| 43 | Tri Star Bullish | Bullish | 4 | Üç ardışık Doji, ortadaki en düşük |
| 44 | Tri Star Bearish | Bearish | 4 | Üç ardışık Doji, ortadaki en yüksek |
| 45 | Advance Block | Bearish | 2 | 3 bullish ama gövdeler küçülüyor (momentum kaybı) |
| 46 | Identical Three Crows | Bearish | 5 | 3 bearish, her biri öncekinin kapanışında açılıyor |

### 3.4 Devam Formasyonları (4+ mum, 5 adet)

| # | Formasyon | Yön | Güç | Tespit Kuralı |
|---|-----------|-----|-----|---------------|
| 47 | Rising Three Methods | Bullish | 4 | Büyük bullish + 3 küçük bearish (içeride) + büyük bullish |
| 48 | Falling Three Methods | Bearish | 4 | Büyük bearish + 3 küçük bullish (içeride) + büyük bearish |
| 49 | Mat Hold Bullish | Bullish | 5 | Rising Three'nin güçlü versiyonu (gap ile) |

### 3.5 Tasuki Gap ve Ek Formasyonlar (11 adet)

| # | Formasyon | Yön | Güç | Tespit Kuralı |
|---|-----------|-----|-----|---------------|
| 50 | Upside Tasuki Gap | Bullish | 3 | 2 bullish (gap) + bearish düzeltme (gap'i kapatmaz) |
| 51 | Downside Tasuki Gap | Bearish | 3 | 2 bearish (gap) + bullish düzeltme (gap'i kapatmaz) |
| 52 | Kicking Bullish | Bullish | 5 | Bearish Marubozu → Bullish Marubozu (gap ile) |
| 53 | Kicking Bearish | Bearish | 5 | Bullish Marubozu → Bearish Marubozu (gap ile) |
| 54 | Counterattack Bullish | Bullish | 3 | Aynı kapanışta karşıt büyük mumlar |
| 55 | Counterattack Bearish | Bearish | 3 | Aynı kapanışta karşıt büyük mumlar |
| 56 | Homing Pigeon | Bullish | 2 | İç içe bearish mumlar, satış baskısı azalıyor |
| 57 | Stick Sandwich | Bullish | 3 | Aynı kapanışlı 2 bearish arasında bullish |
| 58 | Unique Three River | Bullish | 3 | Nadir dip dönüş formasyonu |
| 59 | Breakaway Bullish | Bullish | 4 | Gap'li düşüşten güçlü geri dönüş (5 mum) |
| 60 | Breakaway Bearish | Bearish | 4 | Gap'li yükselişten güçlü geri dönüş (5 mum) |

### Formasyon Puanlama

`score_patterns(patterns)` fonksiyonu:
```
Bullish formasyonlar → +güç değeri
Bearish formasyonlar → -güç değeri
Toplam = Σ (tüm tespit edilen formasyonların puanları)
Sonuç [-5, +5] arasına normalize edilir
```

---

## 4. Destek/Direnç Yöntemleri (12 adet)

**Dosya:** `scripts/levels.py` → `get_all_levels(df)`
**Bağımlılık:** `scipy.stats` (sadece regresyon için)

### 4.1 Pivot Clustering S/R
Lokal min/max noktalarını bulur, yakın olanları %0.3 toleransla gruplar. Çok dokunulan seviyeler daha güçlü.

### 4.2 Fibonacci Retracement
Son 100 mumda en yüksek ve en düşük noktaları bulur. Aralarına standart Fibonacci seviyeleri yerleştirir: **0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0**

### 4.3 Fibonacci Extension
Aynı swing high/low noktalarından uzatma seviyeleri: **1.0, 1.272, 1.414, 1.618, 2.0, 2.618**

### 4.4 Classic (Floor) Pivot Points
```
PP = (H + L + C) / 3
R1 = 2×PP - L,  S1 = 2×PP - H
R2 = PP + (H-L), S2 = PP - (H-L)
R3 = H + 2×(PP-L), S3 = L - 2×(H-PP)
```

### 4.5 Camarilla Pivot Points
Nick Scott'un formülü. Close merkezli, H-L aralığının katsayıları: R/S1 = ±1.1/12, R/S2 = ±1.1/6, R/S3 = ±1.1/4, R/S4 = ±1.1/2

### 4.6 Woodie Pivot Points
```
PP = (H + L + 2×C) / 4  (Close'a daha fazla ağırlık)
```

### 4.7 DeMark Pivot Points
Open/Close ilişkisine göre farklı X değeri hesaplar, sonra R1 ve S1 türetir.

### 4.8 Psikolojik Seviyeler
Yuvarlak sayı seviyelerini otomatik tespit eder. Örnek: BTC 97500 → 95000, 96000, ..., 100000. Major seviyeler (5'in katları) daha ağırlıklı.

### 4.9 Volume Profile
Fiyat aralığını 50 bölgeye ayırır, her bölgedeki hacmi hesaplar:
- **POC** (Point of Control): En çok hacim gören fiyat → Ağırlık: 4
- **VAH** (Value Area High): Hacmin %70'inin üst sınırı → Ağırlık: 3
- **VAL** (Value Area Low): Hacmin %70'inin alt sınırı → Ağırlık: 3
- **HVN** (High Volume Node): Ortalama hacmin 1.5 katından fazla olan bölgeler

### 4.10 Order Blocks
ICT (Inner Circle Trader) konseptinden:
- **Bullish OB**: Güçlü yükseliş öncesindeki son bearish mum → Destek
- **Bearish OB**: Güçlü düşüş öncesindeki son bullish mum → Direnç
- Güçlü hareket kriteri: `gövde > 2× ortalama gövde`

### 4.11 Fair Value Gaps (FVG)
3 mumlu boşluk tespiti:
- **Bullish FVG**: Mum 1'in high'ı < Mum 3'ün low'u (arada gap)
- **Bearish FVG**: Mum 1'in low'u > Mum 3'ün high'ı
- Sadece henüz kapatılmamış gap'ler raporlanır

### 4.12 Trend Çizgileri
Swing high/low noktalarına lineer regresyon uygular:
- **Yükselen trend çizgisi**: Swing low'ları birleştirir (en az 3 dokunma)
- **Alçalan trend çizgisi**: Swing high'ları birleştirir
- Tolerans: fiyatın %0.3'ü
- Çizgi güncel zamana uzatılır

### Bonus: Chart Pattern Tespiti
`detect_chart_patterns(df)` — geometrik formasyonları swing noktalarından tespit eder:
- Double Top / Double Bottom (güç: 4)
- Head & Shoulders / Inverse H&S (güç: 5)
- Ascending / Descending / Symmetric Triangle (güç: 3)
- Rising / Falling Wedge (güç: 3)
- Triple Top / Triple Bottom (güç: 5)
- Tolerans: %1.5

### S/R Birleştirme Ağırlıkları

`get_all_levels()` tüm yöntemlerin sonuçlarını toplar ve ağırlığa göre sıralar:

| Yöntem | Ağırlık |
|--------|---------|
| VP POC | 4 |
| Fibonacci 0.382/0.5/0.618 | 3 |
| Volume Profile VAH/VAL | 3 |
| Order Blocks | 3 |
| Pivot Cluster | dokunma_sayısı × 2 |
| FVG | 2.5 |
| Classic Pivot Points | 2 |
| Psychological (major) | 2 |
| Trend Line | dokunma_sayısı × 1.5 |
| Fibonacci (diğer) | 1.5 |
| Psychological (minor) | 1 |

---

## 5. Market Rejim Tespiti

**Dosya:** `scripts/regime.py` → `classify_regime(df)`, `get_regime_details(df)`
**Bağımlılık:** Yok — `indicators.py`'den hesaplanmış değerleri kullanır

### Rejim Etiketleri

| Rejim | Koşul | Açıklama |
|-------|-------|----------|
| `BREAKOUT` | BB width < KC width AND ADX > 20 | Squeeze sıkışması çözülüyor |
| `LOW_VOLATILITY` | BB width < KC width AND ADX ≤ 20 | Squeeze aktif, henüz kırılım yok |
| `HIGH_VOLATILITY` | ATR percentile > 80 | Son 100 bardaki ATR'nin %80 üstünde |
| `TRENDING_UP` | ADX > 25 AND EMA50 slope > +0.1% | Güçlü yükseliş trendi |
| `TRENDING_DOWN` | ADX > 25 AND EMA50 slope < -0.1% | Güçlü düşüş trendi |
| `RANGING` | Choppiness > 61.8 VEYA hiçbir koşul sağlanmıyor | Yatay/kararsız piyasa |

### Karar Ağacı Öncelik Sırası

```
1. Squeeze aktif mi? (BB < KC)
   ├── ADX > 20 → BREAKOUT
   └── ADX ≤ 20 → LOW_VOLATILITY
2. ATR percentile > 80? → HIGH_VOLATILITY
3. ADX > 25?
   ├── EMA slope > +0.1% → TRENDING_UP
   └── EMA slope < -0.1% → TRENDING_DOWN
4. Choppiness > 61.8? → RANGING
5. EMA slope > +0.2% → TRENDING_UP (zayıf trend)
6. EMA slope < -0.2% → TRENDING_DOWN (zayıf trend)
7. Hiçbiri → RANGING
```

### Kullanılan Göstergeler

| Gösterge | Kaynak | Kullanım |
|----------|--------|----------|
| ADX | `indicators.py` → `ta.trend.ADXIndicator(14)` | Trend gücü eşiği (25) |
| Choppiness Index | `indicators.py` → elle hesaplama | Yatay piyasa eşiği (61.8) |
| EMA 50 slope | `indicators.py` → 5 bar değişim oranı | Trend yönü |
| ATR percentile | `indicators.py` → 100 bar rolling rank | Volatilite seviyesi |
| BB width vs KC width | `indicators.py` → `ta.volatility` | Squeeze tespiti |

---

## 6. Strateji Kategorileri

**Dosya:** `scripts/strategy/catalog.py`

İndikatörler 4 fonksiyonel kategoriye ayrılmıştır. Her strateji varyantı bu kategorilerden seçim yapar:

| Kategori | Rol | Sayı | Örnekler |
|----------|-----|------|----------|
| **Trend** | "Kral" — Yönü belirler | 16 | EMA Ribbon, MACD, ADX/DI, Supertrend, Ichimoku |
| **Entry** | "Vezir" — Zamanlama yapar | 15 | RSI, Stochastic, StochRSI, Elder Ray, Connors RSI |
| **Volume** | "Asker" — Teyit verir | 7 | OBV, CMF, MFI, Force Index, Klinger |
| **Volatility** | Opsiyonel filtre | 5 | BB Position, Squeeze, Keltner, Donchian, Choppiness |

### Sinyal Üretim Formülü

```
LONG sinyali:
  avg(trend skorları) >= trend_threshold
  AND avg(entry skorları) >= entry_threshold
  AND (avg(volume skorları) > 0 VEYA volume_required = False)

SHORT sinyali:
  avg(trend skorları) <= -trend_threshold
  AND avg(entry skorları) <= -entry_threshold
  AND (avg(volume skorları) < 0 VEYA volume_required = False)
```

---

## Akademik Referanslar

Bu formüllerin orijinal kaynakları:

| Kişi/Kaynak | Katkı |
|-------------|-------|
| J. Welles Wilder Jr. | RSI, ATR, ADX, Parabolic SAR (1978, "New Concepts in Technical Trading Systems") |
| Gerald Appel | MACD (1979) |
| John Bollinger | Bollinger Bands (1980'ler, "Bollinger on Bollinger Bands") |
| Steve Nison | Japon mum formasyonları Batı'ya tanıtımı (1991, "Japanese Candlestick Charting Techniques") |
| Goichi Hosoda | Ichimoku Kinko Hyo (1968, Japonca yayın) |
| George Lane | Stochastic Oscillator (1950'ler) |
| Joe Granville | On-Balance Volume (1963, "Granville's New Key to Stock Market Profits") |
| Alexander Elder | Elder Ray, Force Index (1993, "Trading for a Living") |
| Larry Williams | Williams %R, Ultimate Oscillator |
| Tushar Chande | CMO, Aroon Indicator |
| Marc Chaikin | CMF, Chaikin Volatility, ADL |
| Alan Hull | Hull Moving Average (2005) |
| Perry Kaufman | KAMA - Kaufman's Adaptive Moving Average |
| Larry Connors | Connors RSI |
| Martin Pring | KST Indicator |
| ICT (Inner Circle Trader) | Order Blocks, Fair Value Gaps konseptleri |
| Richard Donchian | Donchian Channel (1960'lar, "trend following'in babası") |
| `ta` kütüphanesi | Tüm klasik formüllerin Python implementasyonu — [github.com/bukosabino/ta](https://github.com/bukosabino/ta) |
