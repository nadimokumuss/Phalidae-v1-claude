# Phalidae v2 - Technical Reference

## Quick Start
```bash
pip install -r requirements.txt
streamlit run scripts/app.py
```
İlk çalıştırmada: DB oluşur → 300 seed strateji üretilir → 12 background job başlar → bootstrap pipeline veri toplar.

---

## Proje Yapısı

```
scripts/
├── app.py                      # Streamlit entry point, DB init, scheduler, sayfa yönlendirme
├── indicators.py               # 67 teknik indikatör hesaplama + 45 puanlama kriteri
├── patterns.py                 # 60 mum formasyonu tespiti (DEĞİŞTİRME)
├── levels.py                   # 12 S/R yöntemi + chart patterns (DEĞİŞTİRME)
├── regime.py                   # Market regime detection (6 rejim etiketi)
├── signal_generator.py         # Manuel canlı tarama (multi-TF, tüm indikatörler)
├── charting.py                 # Plotly grafikler (candlestick, equity curve, P&L)
│
├── db/
│   ├── engine.py               # SQLAlchemy engine (PostgreSQL, connection pooling)
│   └── models.py               # 16 ORM model
│
├── worker/
│   ├── scheduler.py            # APScheduler BackgroundScheduler, 12 job tanımı + bootstrap
│   ├── collector.py            # OHLCV + market data + regime + symbol refresh + backfill
│   ├── analyzer.py             # Multi-TF sinyal analiz + trade checker + smart dedup
│   └── news_collector.py       # CryptoCompare haber toplama + sentiment + risk skoru
│
├── strategy/
│   ├── catalog.py              # 43 indikatörü 4 kategoriye ayıran harita + weight dict
│   ├── variants.py             # Strateji varyant üretimi (seed/random/genetic)
│   ├── backtester.py           # Walk-forward backtest motoru
│   └── optimizer.py            # Optimizasyon döngüsü, skor, sıralama, korelasyon
│
├── paper_trader/
│   ├── trader.py               # Paper trade açma/kapama, snapshot, korelasyon kontrolü
│   ├── position.py             # P&L hesaplama, liquidation price, reasoning metni
│   └── portfolio.py            # Portföy equity, pozisyon büyüklüğü, risk yönetimi
│
└── views/
    ├── page_dashboard.py       # Sistem durumu, best stratejiler, açık tradeler
    ├── page_signals.py         # DB sinyaller + canlı tarama (iki mod)
    ├── page_paper_trades.py    # Açık/kapalı işlemler, equity curve, trade detay
    ├── page_strategy_lab.py    # Coin bazlı sıralama, global leaderboard, varyant detay
    └── page_data_explorer.py   # Kapsam matrisi, ham veri, indikatör grafik
```

---

## Veritabanı (PostgreSQL + SQLAlchemy)

### 16 Tablo ve İlişkileri

| Tablo | PK | Önemli Kolonlar | Unique Constraint |
|-------|----|-----------------|----|
| `ohlcv_data` | id | symbol, timeframe, timestamp, open, high, low, close, volume | (symbol, timeframe, timestamp) |
| `tracked_symbols` | id | symbol, rank, is_active, data_since | symbol |
| `strategy_variants` | id | name, composition(JSON), trend/entry_threshold, volume_required | - |
| `strategy_performance` | id | strategy_variant_id(FK), symbol, total_trades, win_rate, profit_factor, sharpe_ratio, max_drawdown, total_pnl_pct, composite_score, rank, regime_trending/ranging/volatile_score, paper_total, paper_wins, paper_win_rate, paper_pnl_pct | (strategy_variant_id, symbol) |
| `signals` | id | symbol, bias, entry/tp/sl_price, rr_ratio, confidence, score, strategy_variant_id(FK), score_breakdown(JSON), indicator_scores(JSON), detected_patterns(JSON), reasoning, regime, alternative_signals(JSON), rejection_reasons(JSON), confidence_score, confidence_breakdown(JSON), eta_hours_low/high, news_risk_score, invalidation_note | - |
| `paper_trades` | id | signal_id(FK), symbol, bias, entry/tp/sl/exit_price, leverage, liquidation_price, position_size_usd, status, pnl_usd/pnl_percent, max_drawdown/max_profit, mfe_pct/mae_pct, trailing_stop_price, partial_tp_taken, partial_tp_price, partial_tp_pnl, tp2_price, tp3_price, risk_pct, regime_at_entry, exit_reason, reasoning | - |
| `trade_snapshots` | id | paper_trade_id(FK), timestamp, current_price, unrealized_pnl | - |
| `coin_config` | id | symbol, best_strategy_id(FK), auto_trade, leverage, max_position_size, daily_drawdown_limit, trailing_stop_enabled, time_stop_bars | symbol |
| `funding_data` | id | symbol, timestamp, funding_rate, open_interest, spread_pct | (symbol, timestamp) |
| `market_regime_records` | id | symbol, timeframe, timestamp, regime_label, adx_value, choppiness_value, atr_percentile, ema_slope | (symbol, timeframe, timestamp) |
| `correlation_cache` | id | symbol_a, symbol_b, correlation, computed_at | (symbol_a, symbol_b) |
| `agent_jobs` | id | job_name, status, started_at, completed_at, duration_sec, records_affected, error_message, context(JSON) | - |
| `portfolio_snapshots` | id | timestamp, total_equity, cash_balance, open_positions, unrealized_pnl, daily_pnl | - |
| `trade_management_log` | id | paper_trade_id(FK), timestamp, event_type, old_value, new_value, reason, current_price, current_pnl_pct | - |
| `news_events` | id | source, external_id, title, body, url, symbols(JSON), published_at, sentiment, impact_score, is_important, total_votes | (source, external_id) |
| `external_analyses` | id | source_type, author, symbol, bias_claimed, target_price, timestamp, content_summary, outcome | - |

### İlişkiler
```
StrategyVariant ──1:N──→ StrategyPerformance
StrategyVariant ──1:N──→ Signal (via strategy_variant_id)
Signal ──1:N──→ PaperTrade (via signal_id)
PaperTrade ──1:N──→ TradeSnapshot (via paper_trade_id)
PaperTrade ──1:N──→ TradeManagementLog (via paper_trade_id)
CoinConfig.best_strategy_id ──FK──→ StrategyVariant
```

### Connection Pooling
```python
# db/engine.py
pool_size=10          # Sabit bağlantı sayısı
max_overflow=20       # Ek bağlantı (toplam max: 30)
pool_timeout=30       # Havuz dolu ise 30s bekle, sonra hata ver
pool_recycle=1800     # 30dk'dan eski bağlantıları yenile
pool_pre_ping=True    # Kullanmadan önce bağlantıyı test et
```

---

## Scheduler Job'ları (12 Toplam)

### Sürekli Job'lar (Recurring)

| Job | Interval | İlk Çalışma | Fonksiyon Zinciri |
|-----|----------|-------------|-------------------|
| Symbol Refresh | 24 saat | Hemen | `refresh_tracked_symbols(top_n=50)` |
| OHLCV Collector | 5 dk | +30s | `collect_incremental()` — 55 coin × 5 TF, limit=200 |
| Market Data | 15 dk | +45s | `collect_market_data()` + `collect_regime_data()` |
| Signal Analyzer | 5 dk | +2m | `run_analysis_cycle()` → `_analyze_single()` |
| Trade Checker | 5 dk | +2m 30s | `check_open_trades()` → TP/SL/trailing/partial TP |
| Strategy Optimizer | 6 saat | +10m | `run_optimization()` → backtest + rank + correlations |
| News Collector | 15 dk | +15s | `collect_news()` — CryptoCompare API |
| Portfolio Snapshot | 5 dk | +1m | `record_portfolio_snapshot()` |

### Tek Seferlik Job'lar (One-time)

| Job | Tetikleme | Fonksiyon |
|-----|-----------|-----------|
| Bootstrap Pipeline | +5s | `_bootstrap()` — symbols → collect → market data → news → news backfill |
| Quick Optimizer | +3m | `run_quick_optimization(top_symbols=10, top_variants=50)` |
| Backfill Underfilled | +1m | `_job_backfill_underfilled()` — <200 bar olan coinleri doldur |

Tüm job'lar `max_instances=1` ve `replace_existing=True` ile yapılandırılmış.

---

## Multi-Timeframe Analiz Sistemi

### Veri Toplama (collector.py)

```python
TIMEFRAMES = ["5m", "15m", "30m", "1h", "4h"]

BACKFILL_LIMITS = {
    "5m": 500,     # ~1.7 gün
    "15m": 1000,   # ~10 gün
    "30m": 1000,   # ~20 gün
    "1h": 1000,    # ~41 gün
    "4h": 1000,    # ~166 gün
}

# Incremental fetch: her 5 dk'da coin başına 200 mum/TF
# Backfill: yeni/eksik coinlere 1000 mum/TF (startup'ta otomatik)
# Deep backfill: günlük 02:00 UTC, 5000 mum/TF hedef
```

### Performans Optimizasyonu
- **Bulk dedup**: `_fetch_and_store()` tek sorgu ile mevcut timestamp'leri kontrol eder (`IN()` query), satır-satır yerine
- **Otomatik backfill**: `refresh_tracked_symbols()` yeni eklenen coinleri otomatik backfill eder
- **Bootstrap backfill**: Ayrı scheduler job olarak çalışır, bootstrap'ı bloklamaz

### TF Ağırlıkları (analyzer.py + signal_generator.py)

```python
tf_weights = {
    "5m":  0.05,   # Çok kısa vadeli gürültü, düşük ağırlık
    "15m": 0.10,   # Kısa vadeli momentum
    "30m": 0.15,   # Orta-kısa vadeli
    "1h":  0.25,   # Ana referans (trend)
    "4h":  0.35,   # En güçlü sinyal (ana karar verici)
}
```

### Sinyal Üretim Akışı (_analyze_single)

```
Her coin için:
  1. 5 TF'de veri yükle (DB'den get_ohlcv_df)
  2. Her TF'de compute_all_indicators() → score_all_indicators()
  3. Her TF'de detect_all_patterns() → score_patterns()
  4. Ağırlıklı ortalama: final_ind_score, final_pat_score
  5. 4h verisinden get_all_levels() → chart_pattern_bonus (±3 max)
  6. 4h verisinden trend_line_bonus (±2 max)
  7. total_score = ind + pat + chart_pattern + trend_line
  8. Bias: ≥+2.0 → LONG, ≤-2.0 → SHORT, arası → skip
  9. Smart Dedup kontrolü
  10. Confidence scoring (7 bileşen, 100 puan)
  11. Sinyal kaydet → auto paper trade (ORTA/YUKSEK ise)
```

---

## Smart Signal Deduplication

Analyzer'da pozisyon-bilinçli sinyal filtreleme:

```python
# 1. Aynı coin+bias için açık paper trade var → skip
open_trade = session.query(PaperTrade).filter(
    symbol=symbol, bias=bias, status="OPEN"
).first()

# 2. Son sinyal aynı bias ve fiyat <3% değiştiyse → skip
if last_signal.bias == bias:
    price_change = abs(entry - last_signal.entry) / last_signal.entry
    if price_change < 0.03:  # %3'ten az → skip
        return False

# 3. Bias flip (LONG→SHORT veya tersi) → her zaman izin ver
```

---

## Güven Skoru (Confidence Scoring)

### 7 Bileşen, 100 Puan Ölçeği

| Bileşen | Maks Puan | Kaynak |
|---------|-----------|--------|
| Confluence (indikatör uyumu) | 25 | Kaç indikatör aynı yönü gösteriyor |
| Regime Fit | 20 | Strateji bu rejimde başarılı mı |
| R:R Quality | 15 | Risk/ödül oranı kalitesi |
| Pattern Support | 10 | Mum formasyonu desteği |
| Volume Confirmation | 10 | Hacim indikatörleri onaylıyor mu |
| Backtest History | 10 | Strateji backtest win rate'i |
| News Risk | 10 | Haber risk skoru (düşük = iyi) |

### Normalizasyon (Backtest Verisi Yokken)

Optimizer henüz çalışmadıysa `regime_fit` (20) ve `backtest_history` (10) = 0. Bu durumda mevcut 70 puanı 100'e normalize et:

```python
if backtest_wr == 0:
    available_max = 25 + 15 + 10 + 10 + 10  # = 70
    conf_score = conf_score / available_max * 100
```

### Etiketler ve Auto-Trade Gate

```python
YUKSEK = conf_score >= 75   # Yüksek güven → auto trade
ORTA   = conf_score >= 50   # Orta güven → auto trade
DUSUK  = conf_score < 50    # Düşük güven → sadece kaydet, trade açma
```

### Hacim Onayı (Volume Confirmation)

Doğrudan tüm hacim indikatörlerini kontrol eder:
```python
vol_indicators = ["obv_trend", "vwap_position", "mfi_signal",
                  "volume_sma_ratio", "cmf_signal", "adl_trend",
                  "volume_momentum"]
# LONG: pozitif olanların oranı
# SHORT: negatif olanların oranı
```

---

## Haber Sistemi (News)

### CryptoCompare API (news_collector.py)

```python
# Her 15 dk: son 50 haber çek
collect_news()  # GET /data/v2/news/?lang=EN

# Sayfalama: lTs parametresi ile geçmişe git
backfill_news(pages=5)  # Cold-start: 250 haber çek

# Bootstrap: news tablosu < 50 kayıt → otomatik backfill
```

### Sentiment Analizi
- **Bullish**: positive_votes > negative_votes × 2
- **Bearish**: negative_votes > positive_votes × 2
- **Neutral**: diğer

### News Risk Skoru (0.0 - 1.0)
```python
get_news_risk_score(symbol)
# Son 24 saat haberleri
# Önemli haberler 3× ağırlık, 10+ oy 1.5× ağırlık
# Bearish tam ağırlık, neutral 0.3× ağırlık
# risk = negative_weight / total_weight
```

### Analyzer Entegrasyonu
- `news_risk > 0.9` → sinyal tamamen skip
- `news_risk > 0.7` → pozisyon boyutu %50 azaltılır

---

## Paper Trading Sistemi

### Sabit Değerler (trader.py)
```python
DEFAULT_LEVERAGE = 5.0
DEFAULT_POSITION_SIZE = 1000.0  # USD
MAX_OPEN_TRADES_PER_SYMBOL = 1
MAX_TOTAL_OPEN_TRADES = 20
MAX_CORRELATION = 0.95  # Açık tradelarle korelasyon limiti
```

### İşlem Açma Kontrolleri
1. **Portföy kontrolü**: `can_open_trade()` + `calculate_position_size()`
2. **Coin başına limit**: Max 1 açık trade/coin
3. **Toplam limit**: Max 20 açık trade
4. **Günlük drawdown**: Coin bazlı (varsayılan -%10, CoinConfig'den ayarlanabilir)
5. **Korelasyon**: Açık trade'lerle korelasyon > 0.95 ise reddet
6. **Güven skoru**: Sadece ORTA/YUKSEK güvenle auto-trade

### Multi-TP (Phase 2)
```
TP1 (partial_tp_price) → Pozisyonun %50'si kapatılır
  → SL breakeven'a taşınır
  → Kalan %50 devam eder

TP2 (tp2_price) → Kalan pozisyon kapatılır

TP3 (tp3_price) → Opsiyonel trailing hedef
```

### Trailing Stop Mantığı
```python
# Kar mesafesine göre dinamik SL:
0.5×ATR kâr  → SL = entry (breakeven)
1.0×ATR kâr  → SL = entry + 0.3×ATR (küçük kâr garantisi)
2.0×ATR kâr  → SL = fiyat - 1×ATR (trailing)
```

### Trade Kapanış Nedenleri
`TP_HIT`, `SL_HIT`, `TRAILING_STOP`, `LIQUIDATED`, `TIME_EXPIRED`, `PARTIAL_TP`

### Paper Stats Feedback Loop
Trade kapandığında `_update_paper_stats()`:
- `strategy_performance` tablosunda paper_total, paper_wins, paper_win_rate, paper_pnl_pct güncellenir
- Optimizer bir sonraki döngüde bu verileri kullanır

---

## Strateji Optimizasyon Sistemi

### Composite Score Formülü
```python
composite = 0.30 × win_rate                    # %30 kazanma oranı
          + 0.25 × min(profit_factor / 3, 1)    # %25 kar faktörü (max 3)
          + 0.20 × min(sharpe_ratio / 3, 1)     # %20 Sharpe oranı (max 3)
          + 0.15 × max(1 - max_dd/100, 0)       # %15 düşük drawdown
          + 0.10 × min(total_trades / 100, 1)    # %10 yeterli trade sayısı

MIN_TRADES = 20  # Bunun altında composite_score = 0
```

### Optimizasyon Döngüsü (6 saatte 1)
```
1. generate_random_variants(count=10)      # Keşif
2. generate_genetic_variants(top_n=10, children=10)  # Evrim
3. Her coin (top 30) × Her varyant (300+):
   → get_ohlcv_df(symbol, "4h", limit=3000)
   → compute_all_indicators(df)
   → backtest_variant(df, composition, ...)
   → compute_composite_score(metrics)
   → Upsert StrategyPerformance
4. _update_ranks(session, symbol)          # rank=1 = en iyi
5. _update_best_strategies()               # CoinConfig.best_strategy_id güncelle
6. _compute_correlations(symbol_list)      # Sembol arası korelasyon
```

### Quick Optimizer (Startup - +3 dk)
- Top 10 coin × 50 varyant × 500 bar
- ~12 dk sürer (vs full optimizer ~60 dk)
- Hızlı başlangıç için best_strategy_id atar

### Fallback Mekanizma
Optimizer çalışmadan sinyal üretebilmek için:
```python
_assign_fallback_strategies()
# best_strategy_id=NULL olan coinlere en yüksek
# composite_score'lu varyantı ata (her analiz döngüsünde)
```

### Rejim-Spesifik Strateji Seçimi
```python
_get_regime_best_strategy(session, symbol, regime)
# Trending rejim → regime_trending_score en yüksek strateji
# Volatile rejim → regime_volatile_score en yüksek strateji
# Ranging rejim → regime_ranging_score en yüksek strateji
```

---

## Strateji Varyant Yapısı

Her varyant JSON composition:
```json
{
  "trend": ["ema_ribbon", "macd_signal"],       // 1-2 trend (Kral)
  "entry": ["rsi_signal", "stoch_rsi"],         // 1-2 momentum (Vezir)
  "volume": ["obv_trend"],                      // 1 hacim (Asker)
  "volatility": ["squeeze_signal"]              // 0-1 volatilite (Opsiyonel)
}
```

### Backtest Sinyal Koşulu
```python
LONG:  avg(trend_scores) >= trend_threshold
       AND avg(entry_scores) >= entry_threshold
       AND (avg(volume) > 0 OR NOT volume_required)

SHORT: avg(trend_scores) <= -trend_threshold
       AND avg(entry_scores) <= -entry_threshold
       AND (avg(volume) < 0 OR NOT volume_required)
```

### Üretim Yöntemleri
1. **Seed** (~300): Top indikatör kombinasyonları (ilk çalıştırmada)
2. **Random** (10/döngü): Rastgele keşif
3. **Genetic** (10/döngü): En iyi varyantların crossover'ı

---

## İndikatör Kategorileri (strategy/catalog.py)

### Trend (16 key)
EMA Ribbon (1.5×), SMA Cross (1.0×), Fiyat/EMA200 (1.2×), HMA (0.8×), McGinley (0.7×), MACD (1.5×), ADX/DI (1.5×), Ichimoku (1.3×), PSAR (1.0×), Supertrend (1.2×), Aroon (0.8×), Vortex (0.7×), TRIX (0.6×), KST (0.8×), STC (0.7×), Coppock (0.5×)

### Entry (15 key)
RSI (1.3×), RSI Divergence (1.6×), Stochastic (1.0×), StochRSI (1.2×), Williams %R (0.8×), CCI (1.0×), ROC (0.7×), TSI (0.9×), UO (0.6×), AO (0.7×), PPO (0.8×), Elder Ray (0.7×), CMO (0.6×), BOP (0.5×), Connors RSI (0.8×)

### Volume (7 key)
OBV (1.3×), CMF (1.2×), Force Index (0.8×), MFI (1.3×), Volume Spike (1.0×), PVO (0.7×), Klinger (0.8×)

### Volatility (5 key)
BB Position (1.2×), Squeeze (1.4×), Keltner (0.8×), Donchian (0.7×), Choppiness (1.0×)

---

## Kritik Fonksiyonlar

### indicators.py
- `compute_all_indicators(df)` → 67 indikatörü DataFrame'e ekler
- `score_all_indicators(df)` → 45 kriteri puanlar, `{"scores": {...}, "total_normalized": float}` döner
- `score_selected_indicators(df, keys)` → Seçili key'leri puanlar (strateji bazlı)
- `INDICATOR_WEIGHTS` → Her scoring key'in ağırlığı (0.5-1.6)

### signal_generator.py
- `analyze_symbol(exchange, symbol, timeframes)` → Manuel canlı tarama
- `calculate_optimal_tp_sl(entry, atr, bias, all_levels, fib_data)` → 6-yöntemli TP/SL
- `calculate_confidence_score(indicator_scores, pattern_count, regime, rr_ratio, news_risk, backtest_win_rate, volume_confirmation)` → 7-bileşenli güven skoru
- `calculate_multi_tp(entry, atr, bias)` → TP1/TP2/TP3 hesapla
- `estimate_time_to_target(symbol, bias, entry, tp)` → ETA tahmini (saat)

### worker/analyzer.py
- `run_analysis_cycle()` → Her coin için multi-TF analiz + sinyal üret
- `_analyze_single(config, variant)` → Tek coin analizi (5 TF, 45 indikatör, 4 bonus katmanı)
- `check_open_trades()` → Açık tradeleri kontrol (TP/SL/trailing/partial/time)
- `_get_regime_best_strategy(session, symbol, regime)` → Rejim-spesifik strateji

### worker/collector.py
- `refresh_tracked_symbols(top_n)` → Binance'ten hacim sıralaması güncelle + yeni coinleri backfill
- `collect_incremental()` → 55 coin × 5 TF, her birinden 200 mum çek
- `backfill_symbol(symbol)` → Geçmiş veri doldur (BACKFILL_LIMITS'e göre)
- `deep_backfill_job()` → Günlük derin backfill (5000 mum/TF hedef, 5 coin/çalışma)
- `get_ohlcv_df(symbol, timeframe, limit)` → DB'den DataFrame oku
- `_fetch_and_store(symbol, timeframe, bars)` → Bulk dedup ile veri kaydet

### worker/news_collector.py
- `collect_news()` → CryptoCompare'dan son 50 haber çek
- `backfill_news(pages)` → lTs ile sayfalama, geçmiş haberleri çek
- `get_news_risk_score(symbol)` → Son 24 saat haber risk skoru (0.0-1.0)

### strategy/optimizer.py
- `run_optimization()` → Ana döngü: random+genetic üret → backtest → skorla → sırala
- `run_quick_optimization(top_symbols, top_variants)` → Hızlı başlangıç optimizasyonu
- `compute_composite_score(metrics)` → 5-bileşenli ağırlıklı skor
- `_compute_correlations(symbol_list)` → Sembol arası korelasyon matrisi

### strategy/backtester.py
- `backtest_variant(df, composition, ...)` → Walk-forward backtest (200 bar warmup, max 100 bar hold)
- `_check_signal(df, bar_idx, keys, ...)` → Belirli bar'da sinyal var mı
- `_simulate_trade(df, entry_idx, bias, atr)` → TP/SL simülasyonu (trailing stop dahil)
- `_compute_regime_scores(trades)` → Rejim bazlı win rate

### paper_trader/trader.py
- `open_paper_trade(...)` → Portföy-bilinçli trade açma (6 kontrol katmanı)
- `close_paper_trade(trade_id, exit_price, status)` → Trade kapama + paper stats güncelle
- `record_snapshot(trade_id, current_price)` → MFE/MAE güncelle
- `_check_daily_drawdown(session, symbol)` → Günlük zarar limiti
- `_check_correlation(session, symbol)` → Korelasyon kontrolü

### regime.py
- `get_regime_details(df)` → ADX, choppiness, ATR percentile, EMA slope ile rejim tespiti
- `classify_regime(df)` → Tek rejim etiketi döndür
- `classify_regime_series(df)` → Her bar için rejim serisi
- Rejim etiketleri: `TRENDING_UP`, `TRENDING_DOWN`, `RANGING`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `BREAKOUT`

---

## Deployment (Railway)

- **Platform**: Railway (EU-West bölgesi — Binance US IP'leri engelliyor)
- **URL**: web-production-69d3c.up.railway.app
- **DB**: Railway PostgreSQL addon, `DATABASE_URL` env variable ile bağlantı
- **Auto-deploy**: `git push` → Railway otomatik build + deploy (~3-5 dk)
- **ccxt timeout**: 15s (EU-West'ten Binance API'ye yüksek latency olabilir)

---

## Geliştirme Kuralları

- `patterns.py` ve `levels.py` core dosyalarına dokunma (pre-commit hook koruyor)
- Yeni indikatör: `indicators.py`'de hesapla → `score_all_indicators()`'a kriter ekle → `catalog.py`'ye kategori ata
- Yeni sayfa: `views/page_xxx.py` oluştur → `app.py`'de radio listesine ekle → import + render()
- DB şema: `models.py` güncelle → `engine.py/_run_migrations()`'a `ADD COLUMN IF NOT EXISTS` ekle
- Exchange: Sadece `ccxt.binanceusdm` — başka exchange ekleme
- NumPy/Pandas türlerini PostgreSQL'e yazmadan önce `float()`/`int()` ile dönüştür
- ccxt instance'larına her zaman `timeout: 15000` ekle
- SQLAlchemy session'ları `try/finally` bloğunda kapat
