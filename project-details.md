# Phalidae v2 - Proje Detayları & Çalışma Mantığı

## Vizyon

Mevcut v1 sistemi **stateless bir sinyal tarayıcısıydı**: butona bas → son 200 mumu çek → 67 indikatör + 60 formasyon + 12 S/R yöntemiyle analiz et → sinyal ver → unut.

v2 bunu **kendi kendine öğrenen, sürekli çalışan, strateji optimize eden** bir bota dönüştürüyor. Bot aylarca veri biriktirip, binlerce indikatör kombinasyonunu test edip, her coin için en iyi stratejiyi keşfedecek. Paper trading ile simüle işlem açıp sonuçları takip edecek.

---

## Çekirdek Felsefe: Confluence (Kesişim) Hiyerarşisi

Her strateji varyantı bir "ordu" gibi düşünülür:

| Rol | Kategori | Sayı | Görev |
|-----|----------|------|-------|
| **Kral** | Trend | 1-2 | Ana yönü belirler (EMA Ribbon, MACD, Supertrend...) |
| **Vezir** | Entry (Momentum) | 1-2 | Giriş zamanlamasını ayarlar (RSI, Stochastic, CCI...) |
| **Asker** | Hacim | 1 | Hacim onayı verir (OBV, CMF, MFI...) |
| **Opsiyonel** | Volatilite | 0-1 | Filtreleme yapar (BB Squeeze, Choppiness...) |

Bir sinyal ancak **tüm katmanlar aynı yönü onayladığında** tetiklenir:
- Kral "yukarı" derse VE Vezir "al" derse VE Asker "hacim var" derse → **LONG**
- Kral "aşağı" derse VE Vezir "sat" derse VE Asker "hacim var" derse → **SHORT**
- Herhangi biri uyuşmazsa → **sinyal yok**

---

## Sistem Akışı (7/24 Döngü)

### 1. Veri Toplama (Her 5 dakikada)
```
Binance USDM → Top 50 coin × 4 timeframe (15m, 1h, 4h, 1d)
  → ohlcv_data tablosuna INSERT OR IGNORE
  → İlk çalışmada 1000 mum backfill (4h = ~166 gün geçmiş)
```

### 2. Sinyal Analizi (Her 15 dakikada)
```
Her coin için:
  1. coin_config'dan best_strategy_id oku
  2. strategy_variants'tan composition al
  3. ohlcv_data'dan 4h verisini çek
  4. 67 indikatörü hesapla (compute_all_indicators)
  5. Sadece strateji'nin seçtiği indikatörleri puanla (score_selected_indicators)
  6. 60 mum formasyonunu tara
  7. 12 S/R yöntemiyle TP/SL hesapla
  8. Sinyal koşulları sağlanıyorsa → signals tablosuna kaydet
  9. Güven YÜKSEK veya ORTA ise → paper trade aç
```

### 3. Trade Kontrolü (Her 5 dakikada)
```
Açık paper trade'ler için:
  1. Binance'ten güncel fiyat çek
  2. Snapshot kaydet (fiyat + unrealized P&L)
  3. TP hit mi? → Kapat, status=TP_HIT
  4. SL hit mi? → Kapat, status=SL_HIT
  5. Liquidation mu? → Kapat, status=LIQUIDATED
  6. Kapandıysa → strategy_performance paper istatistiklerini güncelle
```

### 4. Strateji Optimizasyonu (Her 6 saatte)
```
1. 10 yeni rastgele varyant üret (keşif)
2. En iyi varyantlardan 10 genetik çocuk üret (evrim)
3. Tüm varyantları × top 30 coin backtest et:
   a. 4h verisini DB'den çek (1000 mum)
   b. 67 indikatörü bir kez hesapla
   c. Her varyant için walk-forward backtest:
      - 200 mum warmup
      - Her mumda sinyal kontrolü
      - Sinyal varsa: ileriye doğru TP/SL simülasyonu
      - Trade sonucunu kaydet
   d. Metrikleri hesapla (win rate, profit factor, sharpe, drawdown)
   e. Composite score hesapla
4. Her coin için varyantları sırala (rank)
5. coin_config'a en iyi stratejiyi ata
```

### 5. Sembol Yenileme (Her 24 saatte)
```
Binance'ten tüm USDT perpetual pairları çek
  → Hacme göre sırala
  → Top 50'yi tracked_symbols'a ekle/güncelle
  → Düşenleri deaktive et
```

---

## Composite Score Formülü

Bir strateji varyantının bir coin üzerindeki performansı şu formülle puanlanır:

```
composite_score = 0.30 × win_rate           (0-1 arası)
                + 0.25 × profit_factor/3     (PF 3'te cap, 0-1 normalize)
                + 0.20 × sharpe/3            (Sharpe 3'te cap, 0-1 normalize)
                + 0.15 × (1 - max_dd/100)    (Drawdown az = iyi)
                + 0.10 × trade_count/100     (100 trade'de cap)
```

**Minimum 20 trade** gerekli, yoksa skor 0.

Neden bu ağırlıklar:
- **Win rate (%30)**: En önemli metrik, tutarlılık göstergesi
- **Profit factor (%25)**: Kazanç/kayıp oranı, kârlılık kalitesi
- **Sharpe (%20)**: Risk-ayarlı getiri, volatilite hesaba katar
- **Drawdown (%15)**: Sermaye koruma, en büyük düşüş
- **Trade count (%10)**: Yeterli veri (az trade = güvenilmez skor)

---

## Backtest Detayları

### Walk-Forward Yöntemi
- İlk 200 mum → warmup (indikatörlerin stabilize olması için)
- 201. mumdan itibaren her mumda sinyal kontrolü
- Sinyal varsa → ileriye doğru mum mum TP/SL kontrolü
- Max 100 mum hold süresi (aşarsa EXPIRED olarak kapanır)
- Trade kapandıktan sonra 2 mum cooldown (üst üste trade açmayı önler)

### Trade Simülasyonu
- **TP**: Entry + 2.5 × ATR (LONG) veya Entry - 2.5 × ATR (SHORT)
- **SL**: Entry - 1.5 × ATR (LONG) veya Entry + 1.5 × ATR (SHORT)
- **Leverage**: 5x (sabit)
- **P&L**: `((exit - entry) / entry) × leverage × 100`

### Metrik Hesaplama
- **Win Rate**: Kazanan trade / toplam trade
- **Profit Factor**: Brüt kâr / brüt zarar (cap: 10)
- **Sharpe Ratio**: (ortalama P&L / std P&L) × √(min(trade_count, 365))
- **Max Drawdown**: Kümülatif P&L'nin peak'ten en büyük düşüşü

---

## Strateji Evrim Mekanizması

### Aşama 1: Seed (İlk Çalıştırma)
~300 varyant üretilir. Kanıtlanmış yüksek ağırlıklı indikatörlerden kombinasyonlar:
- Top trend: EMA Ribbon, MACD, ADX/DI, Supertrend, Ichimoku, SMA Cross, Fiyat/EMA200, PSAR
- Top entry: RSI, RSI Divergence, Stochastic, StochRSI, Elder Ray, CCI, Connors RSI
- Top volume: OBV, CMF, MFI, Klinger
- Top volatility: Squeeze, BB Position, Choppiness

### Aşama 2: Rastgele Keşif (Her Optimizer Döngüsünde)
Her 6 saatte 10 yeni rastgele varyant. Tüm 43 indikatörden rastgele seçim. Beklenmedik iyi kombinasyonları keşfetmek için.

### Aşama 3: Genetik Evrim (Yeterli Veri Sonrası)
En iyi 10 varyantın componentlerini karıştırarak 10 "çocuk" üretir:
- Baba'nın trend'i + Anne'nin entry'si + rastgele volume
- %20 mutasyon şansı: bir kategorideki indikatörler tamamen değiştirilir

Zamanla: **iyi çalışanlar hayatta kalır, kötüler elenir, yenileri denenir**.

---

## TP/SL Hesaplama Mantığı

`calculate_optimal_tp_sl()` fonksiyonu 6 farklı yöntemin sonuçlarını birleştirir:

### LONG İşlem İçin:
**SL Adayları:**
1. ATR 1.5x (entry - 1.5 × ATR) → ağırlık: 2
2. ATR 2.0x (entry - 2.0 × ATR) → ağırlık: 1.5
3. Yakın destek seviyeleri (max %10 uzakta) → ağırlık: S/R gücü

**TP Adayları:**
1. ATR 2.0x, 3.0x, 4.0x → ağırlık: 1-2
2. Direnç seviyeleri → ağırlık: S/R gücü
3. Fibonacci extension seviyeleri → ağırlık: 2
4. Chart pattern hedefleri → ağırlık: pattern gücü

### Seçim Yöntemi:
- Her kategori için en güçlü 5 aday seçilir
- Ağırlıklı ortalama hesaplanır
- R:R oranı ≥ 1.5 zorunlu, yoksa sinyal iptal

---

## Paper Trading Kuralları

- **Pozisyon büyüklüğü**: $1000 (sabit simüle sermaye)
- **Kaldıraç**: 5x
- **Maksimum**: Coin başına 1 açık trade, toplamda 20 açık trade
- **Otomatik açılma**: `coin_config.auto_trade = True` VE güven YÜKSEK veya ORTA
- **Liquidation**: Entry × (1 - 1/leverage × 0.95) (LONG) veya Entry × (1 + 1/leverage × 0.95) (SHORT)
- **Snapshot**: Her 5 dakikada güncel fiyat + unrealized P&L kaydedilir
- **Kapanma**: TP_HIT, SL_HIT, LIQUIDATED veya EXPIRED (manuel kapanma henüz yok)

---

## İndikatör Puanlama Sistemi

Her 45 scoring kriteri **-1 ile +1** arası puan verir.
Her puanın bir **ağırlığı** vardır (0.5 ile 1.6 arası).

### Ağırlıklı Toplam:
```
normalized_score = (Σ score_i × weight_i) / (Σ weight_i) × 10
```
Sonuç **-10 ile +10** arası.

### Bias Belirleme:
- normalized ≥ 2.5 → **LONG**
- normalized ≤ -2.5 → **SHORT**
- arası → **NÖTR** (sinyal yok)

### Güven Seviyesi:
- |skor| ≥ 6 → **YÜKSEK**
- |skor| ≥ 4 → **ORTA**
- |skor| < 4 → **DÜŞÜK**

---

## UI Sayfaları Mantığı

### Dashboard
Tek bakışta sistemin sağlığı: veri ne kadar birikti, kaç strateji test edildi, açık tradeler nasıl gidiyor, hangi coin'de hangi strateji kazanıyor.

### Sinyaller
İki mod var:
1. **Otomatik**: Arka planda analyzer'ın ürettiği sinyaller (DB'den). Strateji adı, reasoning, zaman bilgisi ile.
2. **Legacy**: Eski butona-bas-tara sistemi. Anlık piyasa taraması, exchange'den canlı veri.

### Paper Trades
Botun simüle trade performansı. Equity curve trendin yukarı mı aşağı mı gittiğini gösterir. Her trade'in neden açıldığı (reasoning) ve fiyat hareketinin zaman grafiği (snapshot'lardan).

### Strategy Lab
Hangi strateji hangi coin'de iyi çalışıyor? Global leaderboard: tüm coin'lerde ortalama en iyi strateji hangisi? Varyant detayında composition (hangi indikatörler) ve her coin'deki performansı.

### Data Explorer
Ham veri kalite kontrolü. Kapsam matrisi: hangi coin'de hangi TF'de ne kadar veri var. Yeşil = 500+, sarı = 100-500, kırmızı = <100.

---

## Coin-Specific Öğrenme

Bu sistemin en önemli özelliği: **her coin kendi en iyi stratejisini bulur**.

BTC için EMA Ribbon + RSI iyi çalışabilir ama SOL için MACD + Stochastic daha iyi olabilir. Optimizer her coin için ayrı backtest yapıp ayrı sıralama üretir. `coin_config` tablosu her coin'in kendi best_strategy_id'sini tutar.

Zamanla:
1. İlk günler: Seed stratejiler backtest edilir
2. İlk hafta: İlk sıralamalar oluşur, paper trade başlar
3. İlk ay: Paper trade sonuçları birikir, composite score'a paper_win_rate de katılır
4. Sürekli: Genetik evrim yeni kombinasyonlar dener, piyasa koşulları değiştikçe farklı stratejiler öne çıkar

---

## Veri Akışı Diyagramı

```
Binance API
    │
    ▼
[Collector - 5dk]──────────► ohlcv_data (SQLite)
    │                              │
[Symbol Refresh - 24s]             │
    │                              ▼
    ▼                     [Optimizer - 6s]
tracked_symbols            compute_all_indicators() (bir kez)
                           ├── Variant 1: backtest → score
                           ├── Variant 2: backtest → score
                           └── Variant N: backtest → score
                                   │
                                   ▼
                           strategy_performance (rank per coin)
                                   │
                                   ▼
                           coin_config (best_strategy_id)
                                   │
                                   ▼
                          [Analyzer - 15dk]
                           score_selected_indicators()
                           detect_all_patterns()
                           calculate_optimal_tp_sl()
                                   │
                                   ▼
                              signals (DB)
                                   │
                                   ▼
                          [Auto Paper Trade]
                                   │
                                   ▼
                            paper_trades (OPEN)
                                   │
                          [Trade Checker - 5dk]
                           fetch current price
                           TP/SL/liquidation check
                                   │
                                   ▼
                          paper_trades (CLOSED)
                          trade_snapshots (P&L history)
                                   │
                                   ▼
                          strategy_performance (paper stats update)
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

## Gelecek İyileştirmeler (Henüz Yapılmadı)

- [ ] Alembic migration desteği (DB şema değişikliği için)
- [ ] Regime detection (trending/ranging piyasa tespiti)
- [ ] Multi-timeframe strateji desteği (şu an sadece 4h backtest)
- [ ] Manuel trade kapatma (UI'dan)
- [ ] Webhook / Telegram bildirim
- [ ] Real trading entegrasyonu (API key ile gerçek işlem)
- [ ] Streamlit `use_container_width` → `width` migration
- [ ] .gitignore dosyası (phalidae.db, __pycache__, .env)
