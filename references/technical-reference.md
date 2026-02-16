# Phalidae v2 - Technical Reference

## Quick Start
```bash
pip install -r requirements.txt
streamlit run app.py
```
İlk çalıştırmada: DB oluşur → 300 seed strateji üretilir → 6 background job başlar.

---

## Proje Yapısı

```
Phalidae v1/
├── app.py                      # Streamlit entry point, DB init, scheduler, sayfa yönlendirme
├── indicators.py               # 67 teknik indikatör hesaplama + 45 puanlama kriteri
├── patterns.py                 # 60 mum formasyonu tespiti (DEĞİŞMEDİ)
├── levels.py                   # 12 S/R yöntemi + chart patterns (DEĞİŞMEDİ)
├── regime.py                   # Market regime detection (trending/ranging/volatile/breakout)
├── signal_generator.py         # Legacy + strategy-based sinyal üretici
├── charting.py                 # Plotly grafikler (candlestick, equity curve, P&L timeline)
├── requirements.txt            # streamlit, ccxt, pandas, numpy, ta, plotly, scipy, sqlalchemy, apscheduler
│
├── db/
│   ├── __init__.py             # Exports: get_engine, get_session, create_all, tüm modeller
│   ├── engine.py               # SQLAlchemy engine (PostgreSQL, connection pooling), session factory
│   └── models.py               # 11 ORM model
│
├── worker/
│   ├── __init__.py             # Exports: start_scheduler, get_scheduler_status
│   ├── scheduler.py            # APScheduler BackgroundScheduler, 6 job tanımı
│   ├── collector.py            # OHLCV + market data + regime veri toplama
│   └── analyzer.py             # Sinyal analiz döngüsü + açık trade kontrolü
│
├── strategy/
│   ├── __init__.py             # Exports: catalog, variants
│   ├── catalog.py              # 45 indikatörü 4 kategoriye ayıran harita + weight dict
│   ├── variants.py             # Strateji varyant üretimi (seed/random/genetic)
│   ├── backtester.py           # Walk-forward backtest motoru
│   └── optimizer.py            # Optimizasyon döngüsü, skor, sıralama, best strategy
│
├── paper_trader/
│   ├── __init__.py             # Exports: open/close trade, calculate_pnl, generate_reasoning
│   ├── trader.py               # Paper trade açma/kapama, snapshot, paper stat güncelleme
│   └── position.py             # P&L hesaplama, liquidation price, reasoning metni
│
└── pages/
    ├── __init__.py
    ├── page_dashboard.py       # Sistem durumu, veri kapsamı, best stratejiler, açık tradeler
    ├── page_signals.py         # DB sinyaller + legacy canlı tarama (iki mod)
    ├── page_paper_trades.py    # Açık/kapalı işlemler, equity curve, trade detay
    ├── page_strategy_lab.py    # Coin bazlı sıralama, global leaderboard, varyant detay
    └── page_data_explorer.py   # Kapsam matrisi, ham veri, indikatör grafik
```

---

## Veritabanı (PostgreSQL + SQLAlchemy)

### 11 Tablo ve İlişkileri

| Tablo | PK | Önemli Kolonlar | Unique Constraint |
|-------|----|-----------------|----|
| `ohlcv_data` | id | symbol, timeframe, timestamp, OHLCV | (symbol, timeframe, timestamp) |
| `tracked_symbols` | id | symbol, rank, is_active, data_since | symbol |
| `strategy_variants` | id | name, composition(JSON), trend/entry_threshold, volume_required | - |
| `strategy_performance` | id | strategy_variant_id(FK), symbol, backtest metrics, paper metrics, regime_trending/ranging/volatile_score, composite_score, rank | (strategy_variant_id, symbol) |
| `signals` | id | symbol, bias, entry/tp/sl_price, strategy_variant_id(FK), score_breakdown(JSON), indicator_scores(JSON), detected_patterns(JSON), reasoning, regime, alternative_signals(JSON), rejection_reasons(JSON) | - |
| `paper_trades` | id | signal_id(FK), symbol, bias, entry/tp/sl/exit_price, leverage, liquidation_price, status, pnl_usd/pnl_percent, max_drawdown/max_profit, reasoning, mfe_pct, mae_pct, exit_reason, trailing_stop_price, regime_at_entry | - |
| `trade_snapshots` | id | paper_trade_id(FK), timestamp, current_price, unrealized_pnl | - |
| `coin_config` | id | symbol, best_strategy_id(FK), auto_trade, leverage, max_position_size, daily_drawdown_limit, trailing_stop_enabled, time_stop_bars | symbol |
| `funding_data` | id | symbol, timestamp, funding_rate, open_interest, spread_pct | (symbol, timestamp) |
| `market_regime_records` | id | symbol, timeframe, timestamp, regime_label, adx_value, choppiness_value, atr_percentile, ema_slope | (symbol, timeframe, timestamp) |
| `correlation_cache` | id | symbol_a, symbol_b, correlation, computed_at | (symbol_a, symbol_b) |

### İlişkiler
- `StrategyVariant` → has_many → `StrategyPerformance`
- `Signal` → has_many → `PaperTrade`
- `PaperTrade` → has_many → `TradeSnapshot`
- `CoinConfig.best_strategy_id` → FK → `StrategyVariant`

### Connection Pooling
`engine.py` PostgreSQL bağlantı havuzu kullanır (`pool_size=10`, `max_overflow=20`, `pool_pre_ping=True`). Bağlantı bilgisi `.env` dosyasındaki `DATABASE_URL` değişkeninden okunur.

---

## Scheduler Job'ları

| Job | Interval | Fonksiyon Zinciri | Max Instances |
|-----|----------|-------------------|---------------|
| OHLCV Collector | 5 dk | `_job_collect()` → `collect_incremental()` | 1 |
| Signal Analyzer | 15 dk | `_job_analyze()` → `run_analysis_cycle()` → `_analyze_single()` | 1 |
| Trade Checker | 5 dk | `_job_check_trades()` → `check_open_trades()` | 1 |
| Strategy Optimizer | 6 saat | `_job_optimize()` → `run_optimization()` | 1 |
| Market Data Collector | 15 dk | `_job_market_data()` → `collect_market_data()` + `collect_regime_data()` | 1 |
| Symbol Refresh | 24 saat | `_job_refresh_symbols()` → `refresh_tracked_symbols(top_n=50)` | 1 |

---

## Kritik Fonksiyonlar

### indicators.py
- `compute_all_indicators(df)` → 67 indikatörü DataFrame'e ekler
- `score_all_indicators(df)` → 45 kriteri puanlar, tüm indikatörleri kullanır
- `score_selected_indicators(df, keys)` → Sadece verilen key listesini puanlar (strateji bazlı)
- `INDICATOR_WEIGHTS` → Modül seviyesi dict, her scoring key'in ağırlığı

### signal_generator.py
- `analyze_symbol(exchange, symbol, timeframes)` → Legacy: exchange'den çek, tam analiz, sinyal döndür
- `analyze_symbol_with_strategy(df, symbol, composition, ...)` → Yeni: DB'den okunan df + strateji ile analiz
- `calculate_optimal_tp_sl(entry, atr, bias, all_levels, fib_data)` → Çoklu yöntem TP/SL
- `get_recent_signals_from_db(limit)` → DB'den son sinyalleri çek
- `scan_market(top_n, timeframes)` → Legacy: piyasa tarama

### strategy/backtester.py
- `backtest_variant(df, composition, trend_threshold, entry_threshold, volume_required)` → Walk-forward backtest
- `_check_signal(df, bar_idx, keys, ...)` → Belirli bar'da sinyal var mı kontrol
- `_simulate_trade(df, entry_idx, bias, atr)` → İleriye doğru TP/SL simülasyonu

### strategy/optimizer.py
- `run_optimization()` → Ana döngü: random+genetic üret → backtest → skorla → sırala → best seç
- `compute_composite_score(metrics)` → Ağırlıklı skor formülü
- `get_top_strategies(symbol, limit)` → Coin için en iyi stratejiler

### worker/collector.py
- `refresh_tracked_symbols(top_n)` → Binance'ten hacim sıralaması güncelle
- `collect_incremental()` → Tüm aktif semboller için son mumları çek
- `backfill_symbol(symbol)` → Geçmiş veri doldur (1000 mum/TF)
- `get_ohlcv_df(symbol, timeframe, limit)` → DB'den DataFrame oku
- `collect_market_data()` → Funding rate, open interest, spread toplama (15dk)
- `collect_regime_data()` → Market regime hesapla ve kaydet (4h TF)

### regime.py
- `get_regime_details(df)` → ADX, choppiness, ATR percentile, EMA slope ile rejim tespiti
- Rejim etiketleri: TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY, BREAKOUT

### worker/analyzer.py
- `run_analysis_cycle()` → Her coin_config için best strateji ile sinyal üret
- `check_open_trades()` → Açık tradeleri kontrol et (TP/SL/liquidation)

---

## Sabit Değerler (Constants)

### Veri Toplama
```python
TIMEFRAMES = ["15m", "1h", "4h", "1d"]
BACKFILL_LIMITS = {"15m": 1000, "1h": 1000, "4h": 1000, "1d": 1000}
```

### Backtest
```python
DEFAULT_LEVERAGE = 5.0
DEFAULT_POSITION_SIZE = 1000.0  # USD
WARMUP_BARS = 200
TP_ATR_MULT = 2.5
SL_ATR_MULT = 1.5
```

### Composite Score Ağırlıkları
```python
W_WIN_RATE = 0.30
W_PROFIT_FACTOR = 0.25
W_SHARPE = 0.20
W_DRAWDOWN = 0.15
W_TRADE_COUNT = 0.10
MIN_TRADES = 20
```

### Paper Trading
```python
MAX_OPEN_TRADES_PER_SYMBOL = 1
MAX_TOTAL_OPEN_TRADES = 20
DEFAULT_LEVERAGE = 5.0
DEFAULT_POSITION_SIZE = 1000.0
```

### Multi-Timeframe Ağırlıkları (legacy analyze_symbol)
```python
{"5m": 0.05, "15m": 0.15, "1h": 0.25, "4h": 0.35, "1d": 0.20}
```

---

## Strateji Varyant Yapısı

Her varyant JSON composition:
```json
{
  "trend": ["EMA Ribbon", "MACD"],       // 1-2 trend indikatörü (Kral)
  "entry": ["RSI", "Stochastic"],         // 1-2 momentum indikatörü (Vezir)
  "volume": ["OBV"],                      // 1 hacim indikatörü (Asker)
  "volatility": ["Squeeze"]              // 0-1 volatilite filtresi (Opsiyonel)
}
```

### Sinyal Koşulu
- **LONG**: avg(trend_scores) >= trend_threshold AND avg(entry_scores) >= entry_threshold AND (volume > 0 OR volume_required=False)
- **SHORT**: avg(trend_scores) <= -trend_threshold AND avg(entry_scores) <= -entry_threshold AND (volume < 0 OR volume_required=False)

### Üretim Yöntemleri
1. **Seed** (~300): Top indikatör kombinasyonları (ilk çalıştırmada)
2. **Random** (10/döngü): Rastgele keşif (her optimizer çalışmasında)
3. **Genetic** (10/döngü): En iyi varyantların crossover'ı (yeterli veri sonrası)

---

## İndikatör Kategorileri (strategy/catalog.py)

### Trend (16 key)
EMA Ribbon, SMA Cross, Fiyat/EMA200, HMA, McGinley, MACD, ADX/DI, Ichimoku, PSAR, Supertrend, Aroon, Vortex, TRIX, KST, STC, Coppock

### Entry (15 key)
RSI, RSI Divergence, Stochastic, StochRSI, Williams %R, CCI, ROC, TSI, UO, AO, PPO, Elder Ray, CMO, BOP, Connors RSI

### Volume (7 key)
OBV, CMF, Force Index, MFI, Volume Spike, PVO, Klinger

### Volatility (5 key)
BB Position, Squeeze, Keltner, Donchian, Choppiness

---

## Bilinen Sorunlar / Notlar

- Streamlit `use_container_width` → `width='stretch'` geçişi tamamlandı
- Exchange: Sadece `ccxt.binanceusdm` (Binance USDM Perpetual Futures) destekleniyor
- `patterns.py` ve `levels.py` v1'den değiştirilmeden taşındı
- İlk backfill uzun sürebilir (50 coin × 4 TF × 1000 mum)
- `phalidae.db` gitignore'a eklenmeli (runtime artifact)

---

## Geliştirme Kuralları

- `patterns.py` ve `levels.py` core dosyalarına dokunma (kararlı, test edilmiş)
- Yeni indikatör eklerken: `indicators.py`'de hesapla → `score_all_indicators()`'a kriter ekle → `catalog.py`'ye kategori ata
- Yeni sayfa eklerken: `pages/page_xxx.py` oluştur → `app.py`'de radio listesine ekle → import + render()
- DB şema değişikliğinde: `models.py` güncelle → `phalidae.db` sil → yeniden oluştur (migration yok henüz)
