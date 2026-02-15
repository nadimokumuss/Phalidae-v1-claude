---
name: phalidae-trading
description: Automated crypto futures trading system with strategy optimization, backtesting, and paper trading. Use when setting up, running, or managing the Phalidae trading system, analyzing crypto markets, or working with trading strategies.
metadata:
  author: Phalidae
  version: 1.1.0
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
Phalidae-v1-master/
├── .claude/
│   ├── settings.json                   # Shared permissions (git-tracked)
│   ├── settings.local.json             # Local overrides (gitignored)
│   ├── mcp.json                        # MCP: SQLite server for phalidae.db
│   ├── agents/                         # 7 specialized sub-agents
│   │   ├── backtest-analyst.md         # Backtest quality & overfitting detection
│   │   ├── bug-debugger.md             # Scheduler, pipeline & concurrency debugging
│   │   ├── code-reviewer.md            # Trading logic & project rule review
│   │   ├── db-manager.md               # Schema, integrity & query optimization
│   │   ├── indicator-developer.md      # Indicator addition pipeline
│   │   ├── page-builder.md             # Streamlit page creation
│   │   └── strategy-researcher.md      # Strategy performance research
│   └── skills/
│       └── phalidae-trading/
│           └── SKILL.md                # This file
├── CLAUDE.md                           # Claude Code project instructions
├── AGENTS.md                           # Vendor-agnostic AI tool instructions
├── requirements.txt                    # Python dependencies
├── scripts/                            # All executable source code
│   ├── app.py                          # Streamlit entry point, DB init, scheduler
│   ├── indicators.py                   # 67 technical indicators + 45 scoring criteria
│   ├── patterns.py                     # 60 candlestick patterns (DO NOT MODIFY)
│   ├── levels.py                       # 12 S/R methods (DO NOT MODIFY)
│   ├── regime.py                       # Market regime detection (6 labels)
│   ├── signal_generator.py             # Legacy + strategy-based signal generator
│   ├── charting.py                     # Plotly charts
│   ├── db/                             # SQLAlchemy engine + 11 ORM models
│   ├── worker/                         # APScheduler: 6 background jobs
│   ├── strategy/                       # Variants, backtester, optimizer
│   ├── paper_trader/                   # Paper trading engine
│   └── pages/                          # 5 Streamlit UI pages
├── references/
│   └── technical-reference.md          # Complete technical documentation
└── assets/                             # Future use
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

## Sub-Agents

| Agent | Access | Purpose |
|-------|--------|---------|
| backtest-analyst | Read-only | Overfitting detection, statistical validation of backtest results |
| bug-debugger | Read & Write | Diagnose scheduler, data pipeline, and concurrency issues |
| code-reviewer | Read-only | Review trading logic correctness and project rule compliance |
| db-manager | Read & Write | Schema changes, data integrity checks, query optimization |
| indicator-developer | Read & Write | End-to-end indicator pipeline (compute → score → catalog) |
| page-builder | Read & Write | Create Streamlit pages following project conventions |
| strategy-researcher | Read-only | Analyze strategy performance, suggest indicator combinations |

## Development Rules

- **DO NOT** modify `scripts/patterns.py` or `scripts/levels.py` (stable, tested)
- New indicator: `scripts/indicators.py` → `score_all_indicators()` → `scripts/strategy/catalog.py`
- New page: `scripts/pages/page_xxx.py` → add to radio list in `scripts/app.py`
- DB schema change: `scripts/db/models.py` → delete `phalidae.db` → restart

## Technical Reference

See `references/technical-reference.md` for:
- Database schema (11 tables with relationships)
- Strategy variant composition and signal conditions
- Indicator categories (43 indicators across 4 categories)
- Constants, composite score formula, and critical function signatures
