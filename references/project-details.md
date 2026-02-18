# Phalidae v2 - Proje Detayları & Çalışma Mantığı

## Vizyon

Mevcut v1 sistemi **stateless bir sinyal tarayıcısıydı**: butona bas → son 200 mumu çek → 67 indikatör + 60 formasyon + 12 S/R yöntemiyle analiz et → sinyal ver → unut.

v2 bunu **kendi kendine öğrenen, sürekli çalışan, strateji optimize eden** bir bota dönüştürdü. Bot 24/7 çalışıp, 5 zaman diliminde veri toplayıp, 300+ strateji varyantını her coin için ayrı ayrı backtest edip, en iyi stratejiyi seçip, paper trade açıp sonuçları takip ediyor. Genetik evrimle sürekli yeni stratejiler deniyor.

**Felsefe: Ne kadar çok sinyal test edilirse, sistem o kadar hızlı öğrenir.**

---

## Çekirdek Felsefe: Confluence (Kesişim) Hiyerarşisi

Her strateji varyantı bir "ordu" gibi düşünülür:

| Rol | Kategori | Sayı | Görev |
|-----|----------|------|-------|
| **Kral** | Trend | 1-2 | Ana yönü belirler (EMA Ribbon, MACD, Supertrend...) |
| **Vezir** | Entry (Momentum) | 1-2 | Giriş zamanlamasını ayarlar (RSI, Stochastic, CCI...) |
| **Asker** | Hacim | 1 | Hacim onayı verir (OBV, CMF, MFI...) |
| **Opsiyonel** | Volatilite | 0-1 | Filtreleme yapar (BB Squeeze, Choppiness...) |

Bir sinyal ancak **tüm katmanlar aynı yönü onayladığında** tetiklenir. Ancak **sinyal kararı** artık tek strateji varyantıyla değil, **tüm 45 indikatörün ağırlıklı ortalamasıyla** yapılıyor. Strateji varyantı sadece optimizer'ın öğrenmesi için referans olarak kullanılıyor.

---

## Sistem Akışı (7/24 Döngü)

### 1. Veri Toplama (Her 5 dakikada)
```
Binance USDM → 55 coin × 5 timeframe (5m, 15m, 30m, 1h, 4h)
  → Incremental fetch: her TF'den 200 mum
  → Bulk dedup: tek sorgu ile mevcut timestamp'leri kontrol
  → İlk çalışmada ve yeni coin eklendiğinde otomatik backfill
  → Deep backfill: günlük 02:00 UTC, 5000 mum/TF hedef
```

### 2. Sinyal Analizi (Her 5 dakikada)
```
Her coin için:
  1. coin_config'dan best_strategy_id oku (opsiyonel)
  2. 5 TF'de veri yükle: 5m(0.05), 15m(0.10), 30m(0.15), 1h(0.25), 4h(0.35)
  3. Her TF'de: compute_all_indicators → score_all_indicators → detect_all_patterns
  4. Ağırlıklı ortalama: final_ind_score + final_pat_score
  5. 4h verisinden chart pattern bonus (±3) + trend line bonus (±2)
  6. total_score = ind + pat + chart_pattern + trend_line
  7. Bias: ≥+2.0 → LONG, ≤-2.0 → SHORT, arası → skip
  8. Smart Dedup: açık trade var mı? aynı sinyal? fiyat %3 değişti mi?
  9. 7-bileşenli güven skoru (100 puan)
  10. News risk kontrolü (>0.9 → skip, >0.7 → pozisyon %50)
  11. Sinyal kaydet → ORTA/YÜKSEK güven → auto paper trade
```

### 3. Trade Kontrolü (Her 5 dakikada)
```
Açık paper trade'ler için:
  1. Binance'ten güncel fiyat çek (15s timeout)
  2. Snapshot kaydet (fiyat + unrealized P&L + MFE/MAE güncelle)
  3. Time stop: coin bazlı mum limiti aşıldıysa → TIME_EXPIRED
  4. Partial TP: TP1'e ulaştıysa → %50 kapat, SL breakeven'a taşı
  5. TP2: kalan %50 hedefi → TP_HIT
  6. Trailing stop: kâr mesafesine göre dinamik SL
     - 0.5×ATR kâr → SL = entry (breakeven)
     - 1.0×ATR kâr → SL = entry + 0.3×ATR
     - 2.0×ATR kâr → SL = fiyat - 1×ATR (trailing)
  7. Ana TP/SL/Liquidation kontrolü
  8. Kapandıysa → strategy_performance paper stats güncelle
```

### 4. Strateji Optimizasyonu (Her 6 saatte)
```
1. 10 yeni rastgele varyant üret (keşif)
2. En iyi varyantlardan 10 genetik çocuk üret (evrim)
3. Tüm varyantları (300+) × top 30 coin backtest et:
   a. 4h verisini DB'den çek (3000 mum'a kadar)
   b. 67 indikatörü bir kez hesapla
   c. Her varyant için walk-forward backtest:
      - 200 mum warmup
      - Her mumda sinyal kontrolü
      - Sinyal varsa: ileriye doğru TP/SL simülasyonu (trailing stop dahil)
      - Max 100 mum hold, sonra TIME_EXPIRED
   d. Rejim-spesifik win rate hesapla (trending/ranging/volatile)
   e. Composite score hesapla
4. Her coin için varyantları sırala (rank=1 en iyi)
5. coin_config'a en iyi stratejiyi ata
6. Sembol arası korelasyon matrisi hesapla
```

### 5. Sembol Yenileme (Her 24 saatte)
```
Binance'ten tüm USDT perpetual pairları çek
  → 24h hacme göre sırala
  → Top 50'yi tracked_symbols'a ekle/güncelle
  → Düşenleri deaktive et
  → Yeni eklenen coinleri otomatik backfill et
```

### 6. Haber Toplama (Her 15 dakikada)
```
CryptoCompare API'den son 50 haber çek
  → Sentiment analizi (bullish/bearish/neutral)
  → Önem tespiti (oy sayısı, majör coinler)
  → Coin bazlı risk skoru hesapla (son 24 saat)
  → Bootstrap'ta haber tablosu < 50 ise 5 sayfa backfill
```

### 7. Portföy Snapshot (Her 5 dakikada)
```
Toplam equity hesapla (cash + unrealized P&L)
  → portfolio_snapshots tablosuna kaydet
  → Equity curve için tarihsel veri biriktir
```

---

## Composite Score Formülü

```
composite_score = 0.30 × win_rate           (0-1 arası)
                + 0.25 × profit_factor/3     (PF 3'te cap, 0-1 normalize)
                + 0.20 × sharpe/3            (Sharpe 3'te cap, 0-1 normalize)
                + 0.15 × (1 - max_dd/100)    (Drawdown az = iyi)
                + 0.10 × trade_count/100     (100 trade'de cap)
```

**Minimum 20 trade** gerekli, yoksa skor 0.

---

## Güven Skoru Sistemi (Confidence Scoring)

### 7 Bileşen, 100 Puan Ölçeği

| Bileşen | Maks Puan | Açıklama |
|---------|-----------|----------|
| Confluence | 25 | Kaç indikatör aynı yönü gösteriyor |
| Regime Fit | 20 | Strateji bu piyasa rejiminde başarılı mı |
| R:R Quality | 15 | Risk/ödül oranı ≥ 2.5 → tam puan |
| Pattern Support | 10 | Mum formasyonu sayısı ve gücü |
| Volume Confirmation | 10 | 7 hacim indikatörü onaylıyor mu |
| Backtest History | 10 | Strateji'nin backtest win rate'i |
| News Risk | 10 | Haber risk skoru (düşük risk = yüksek puan) |

### Normalizasyon

Optimizer henüz çalışmadığında regime_fit (20) + backtest_history (10) = 0 puan alınamaz. Bu durumda mevcut 70 puan 100'e normalize edilir:

```python
if backtest_win_rate == 0:
    conf_score = conf_score / 70 * 100
```

### Etiketler
- **YUKSEK** (≥75): Güçlü sinyal → auto paper trade
- **ORTA** (≥50): Orta güçte sinyal → auto paper trade
- **DUSUK** (<50): Zayıf sinyal → sadece kaydet, trade açma

---

## Smart Signal Deduplication

Aynı coin için tekrarlayan sinyal üretimini önler:

1. **Açık trade varsa**: Aynı coin+bias için OPEN paper trade varsa → skip
2. **Aynı sinyal**: Son sinyal aynı bias ve fiyat <%3 değiştiyse → skip
3. **Bias flip**: LONG→SHORT veya SHORT→LONG → her zaman izin ver
4. **Fiyat hareketi**: Aynı bias ama fiyat >%3 değiştiyse → yeni sinyal izin ver

---

## Paper Trading Kuralları

### Pozisyon Açma
- **Portföy-bilinçli boyutlandırma**: `calculate_position_size()` ile dinamik
- **Fallback**: CoinConfig.max_position_size veya $1000 varsayılan
- **Kaldıraç**: CoinConfig'den (varsayılan 5x)
- **İzole marjin** modeli (her pozisyon bağımsız likidasyon)

### Kontroller (6 katman)
1. Portföy kapasitesi (`can_open_trade()`)
2. Coin başına limit (max 1 açık trade)
3. Toplam limit (max 20 açık trade)
4. Günlük drawdown limiti (coin bazlı, varsayılan -%10)
5. Korelasyon kontrolü (açık trade'lerle > 0.95 ise reddet)
6. Güven skoru (ORTA veya YUKSEK gerekli)

### Multi-TP Sistemi
```
TP1 (partial_tp_price):
  → Pozisyonun %50'si kapatılır
  → SL otomatik breakeven'a taşınır
  → Kalan %50 devam eder

TP2 (tp2_price):
  → Kalan pozisyon tamamen kapatılır → TP_HIT

TP3 (tp3_price):
  → Opsiyonel trailing hedef
```

### Trade Kapanış Nedenleri
| Neden | Açıklama |
|-------|----------|
| TP_HIT | Take profit hedefine ulaşıldı |
| SL_HIT | Stop loss tetiklendi |
| TRAILING_STOP | Trailing stop tetiklendi |
| LIQUIDATED | Likidasyon fiyatına ulaşıldı |
| TIME_EXPIRED | Maksimum mum süresi aşıldı |
| PARTIAL_TP | Kısmi TP (TP1 - %50 kapatma) |

### Feedback Loop
Trade kapandığında `strategy_performance` tablosunda paper_total, paper_wins, paper_win_rate, paper_pnl_pct güncellenir. Optimizer sonraki döngüde bu verileri dikkate alır.

---

## TP/SL Hesaplama Mantığı

`calculate_optimal_tp_sl()` fonksiyonu 6 yöntemin sonuçlarını birleştirir:

### SL Adayları (LONG için):
1. ATR 1.5x (entry - 1.5 × ATR) → ağırlık: 2
2. ATR 2.0x (entry - 2.0 × ATR) → ağırlık: 1.5
3. Yakın destek seviyeleri (max %10 uzakta) → ağırlık: S/R gücü

### TP Adayları (LONG için):
1. ATR 2.0x, 3.0x, 4.0x → ağırlık: 1-2
2. Direnç seviyeleri → ağırlık: S/R gücü
3. Fibonacci extension seviyeleri → ağırlık: 2
4. Chart pattern hedefleri → ağırlık: pattern gücü

### Seçim:
- Her kategori için en güçlü 5 aday seçilir
- Ağırlıklı ortalama hesaplanır
- R:R oranı ≥ 1.8 zorunlu, yoksa sinyal iptal

### Multi-TP:
```python
calculate_multi_tp(entry, atr, bias)
# TP1: entry ± 1.5×ATR (ilk hedef, partial close)
# TP2: entry ± 2.5×ATR (ana hedef)
# TP3: entry ± 4.0×ATR (uzak hedef, trailing)
```

---

## Strateji Evrim Mekanizması

### Aşama 1: Seed (İlk Çalıştırma)
~300 varyant üretilir. Kanıtlanmış yüksek ağırlıklı indikatörlerden kombinasyonlar.

### Aşama 2: Quick Optimizer (Startup +3dk)
Top 10 coin × 50 varyant × 500 bar. ~12 dk'da ilk sıralama oluşturur. Sistem hemen sinyal üretmeye başlayabilir.

### Aşama 3: Rastgele Keşif (Her 6 saatte)
10 yeni rastgele varyant. Tüm 43 indikatörden rastgele seçim. Beklenmedik iyi kombinasyonları keşfetmek için.

### Aşama 4: Genetik Evrim (Her 6 saatte)
En iyi 10 varyantın componentlerini karıştırarak 10 "çocuk" üretir:
- Baba'nın trend'i + Anne'nin entry'si + rastgele volume
- %20 mutasyon şansı: bir kategorideki indikatörler tamamen değiştirilir

### Zamanla Evrim:
1. **İlk dakikalar**: Bootstrap → veri topla → quick optimize → ilk sinyaller
2. **İlk gün**: Paper trade'ler açılır, kapanır, feedback birikmeye başlar
3. **İlk hafta**: Optimizer hangi stratejilerin iyi çalıştığını keşfeder
4. **Sürekli**: Genetik evrim yeni kombinasyonlar dener, piyasa koşulları değiştikçe farklı stratejiler öne çıkar

---

## Coin-Specific Öğrenme

Bu sistemin en önemli özelliği: **her coin kendi en iyi stratejisini bulur**.

BTC için EMA Ribbon + RSI iyi çalışabilir ama SOL için MACD + Stochastic daha iyi olabilir. Optimizer her coin için ayrı backtest yapıp ayrı sıralama üretir. `coin_config` tablosu her coin'in kendi `best_strategy_id`'sini tutar.

Ayrıca **rejim-spesifik** strateji seçimi var: Piyasa trending ise trending'te en iyi stratejiyi, volatile ise volatile'da en iyi stratejiyi seçer.

---

## Veri Akışı Diyagramı

```
Binance API (ccxt.binanceusdm, 15s timeout)
    │
    ├──[Collector - 5dk]──► ohlcv_data (PostgreSQL)
    │   55 coin × 5 TF        │ 5m, 15m, 30m, 1h, 4h
    │   limit=200/fetch        │ Bulk dedup (IN query)
    │                          │
    ├──[Symbol Refresh - 24s]  │
    │   top_n=50               │
    │   + auto-backfill        │
    │                          ▼
    ├──[Market Data - 15dk]  [Optimizer - 6s]
    │   funding_rate            compute_all_indicators() (1x/coin)
    │   open_interest           ├── Variant 1: backtest → score
    │   regime detection        ├── Variant 2: backtest → score
    │                           └── Variant N: backtest → score
    ├──[News - 15dk]                   │
    │   CryptoCompare API              ▼
    │   sentiment + risk       strategy_performance (rank per coin)
    │                                  │
    │                                  ▼
    │                          coin_config (best_strategy_id)
    │                                  │
    │                                  ▼
    └──────────────────────► [Analyzer - 5dk]
                              5 TF × 45 indikatör × 60 pattern
                              Chart pattern bonus + trend line bonus
                              Smart dedup + confidence scoring
                                       │
                                       ▼
                                  signals (DB)
                                       │
                            ┌──────────┤
                            │          │
                            ▼          ▼
                    (DUSUK: kaydet)  (ORTA/YUKSEK: auto trade)
                                       │
                                       ▼
                                paper_trades (OPEN)
                                       │
                              [Trade Checker - 5dk]
                               ├── Partial TP (50% close)
                               ├── Trailing stop
                               ├── TP2/SL/Liquidation
                               └── Time stop
                                       │
                                       ▼
                              paper_trades (CLOSED)
                              trade_management_log
                              trade_snapshots
                                       │
                                       ▼
                              strategy_performance
                              (paper_win_rate güncelle → feedback loop)
                                       │
                                       ▼
                              ┌──── Streamlit UI ────┐
                              │ Dashboard            │
                              │ Signals              │
                              │ Paper Trades         │
                              │ Strategy Lab         │
                              │ Data Explorer        │
                              └──────────────────────┘
```

---

## Deployment (Railway)

- **Platform**: Railway (EU-West bölgesi)
- **Neden EU-West**: Binance US IP'leri engelliyor
- **URL**: web-production-69d3c.up.railway.app
- **DB**: Railway PostgreSQL addon, `DATABASE_URL` env variable
- **Auto-deploy**: `git push origin master` → Railway otomatik build + deploy (~3-5 dk)
- **Connection pool**: pool_size=10, max_overflow=20, pool_timeout=30s, pool_recycle=1800s

---

## Gelecek İyileştirmeler

### Tamamlananlar ✅
- ✅ Multi-timeframe analiz (5m, 15m, 30m, 1h, 4h)
- ✅ Tüm 45 indikatör ile sinyal üretimi (strateji subset'i yerine)
- ✅ Chart pattern + trend line bonusları
- ✅ Smart signal deduplication (pozisyon-bilinçli)
- ✅ 7-bileşenli güven skoru (100 puan)
- ✅ News engine (CryptoCompare + sentiment + risk)
- ✅ Multi-TP (partial close, breakeven, trailing)
- ✅ Trailing stop (dinamik 3-kademeli)
- ✅ Portfolio-aware position sizing
- ✅ Agent health monitoring (agent_jobs tablosu)
- ✅ Decision trace (zorunlu reasoning metni)
- ✅ ETA to target (tahmini süre)
- ✅ Deep historical backfill (günlük job)
- ✅ Auto-backfill yeni/eksik coinler
- ✅ Korelasyon-bazlı trade filtreleme
- ✅ Rejim-spesifik strateji seçimi
- ✅ Otomatik migration sistemi (ADD COLUMN IF NOT EXISTS)

### Henüz Yapılmayanlar
- [ ] Manuel trade kapatma (UI'dan)
- [ ] Webhook / Telegram bildirim
- [ ] Real trading entegrasyonu (API key ile gerçek işlem)
- [ ] External analysis learning notebook
- [ ] Always-on auto commentary
