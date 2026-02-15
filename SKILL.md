---
name: phalidae-trading
description: Automated crypto futures trading system with strategy optimization, backtesting, and paper trading. Use when setting up, running, or managing the Phalidae trading system, analyzing crypto markets, or working with trading strategies.
metadata:
  author: Phalidae
  version: 1.0.0
  category: trading
---

# Phalidae Trading System

Self-learning crypto futures trading bot with automated strategy optimization, backtesting, and paper trading on Binance USDM Perpetual Futures.

## Setup

```bash
pip install -r requirements.txt
streamlit run scripts/app.py
```

On first run: DB is created, 300 seed strategies are generated, and 6 background jobs start.

## Project Structure

```
phalidae-trading/
├── SKILL.md                        # This file - skill definition
├── requirements.txt                # Dependencies
├── scripts/
│   ├── app.py                      # Streamlit entry point, DB init, scheduler
│   ├── indicators.py               # 67 technical indicators + 45 scoring criteria
│   ├── patterns.py                 # 60 candlestick pattern detection (stable)
│   ├── levels.py                   # 12 S/R methods + chart patterns (stable)
│   ├── regime.py                   # Market regime detection
│   ├── signal_generator.py         # Legacy + strategy-based signal generator
│   ├── charting.py                 # Plotly charts
│   ├── db/                         # SQLAlchemy models & engine (SQLite WAL)
│   ├── worker/                     # APScheduler background jobs
│   ├── strategy/                   # Strategy variants, backtester, optimizer
│   ├── paper_trader/               # Paper trading engine
│   └── pages/                      # Streamlit pages
├── references/
│   └── technical-reference.md      # Detailed technical documentation
└── assets/                         # Templates, icons (future use)
```

## Key Commands

| Command | Description |
|---------|-------------|
| `streamlit run scripts/app.py` | Start the trading system |
| `pip install -r requirements.txt` | Install dependencies |

## Background Jobs

| Job | Interval | Description |
|-----|----------|-------------|
| OHLCV Collector | 5 min | Collect candle data from Binance |
| Signal Analyzer | 15 min | Generate signals using best strategies |
| Trade Checker | 5 min | Monitor open paper trades (TP/SL/liquidation) |
| Strategy Optimizer | 6 hours | Generate, backtest, and rank strategy variants |
| Market Data Collector | 15 min | Funding rate, OI, spread + regime detection |
| Symbol Refresh | 24 hours | Update tracked symbols by volume ranking |

## Development Rules

- **DO NOT** modify `scripts/patterns.py` or `scripts/levels.py` (stable, tested)
- New indicator: add to `scripts/indicators.py` → `score_all_indicators()` → `scripts/strategy/catalog.py`
- New page: create `scripts/pages/page_xxx.py` → add to radio list in `scripts/app.py`
- DB schema change: update `scripts/db/models.py` → delete `phalidae.db` → restart

## Technical Reference

See `references/technical-reference.md` for detailed documentation on:
- Database schema (11 tables)
- Strategy variant composition
- Indicator categories (43 indicators across 4 categories)
- Constants and configuration values
- Critical function signatures
