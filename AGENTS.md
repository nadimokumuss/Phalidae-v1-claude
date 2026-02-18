# AGENTS.md - Phalidae Trading System

This file provides vendor-agnostic instructions for AI coding assistants (Claude Code, Cursor, Copilot, etc.).

## Project Overview

Phalidae is a self-learning crypto futures trading bot for Binance USDM Perpetual Futures. It runs 24/7 on Railway (EU-West), collecting data across 5 timeframes, generating signals using 45 scoring criteria from 67 technical indicators, backtesting 300+ strategy variants per coin, and paper trading with portfolio-aware position sizing. The system continuously evolves strategies through genetic algorithms and backtest feedback.

## Architecture

- **Runtime:** Python 3.10+ with Streamlit as the UI framework
- **Database:** PostgreSQL via SQLAlchemy ORM (16 tables, connection pooling: pool_size=10, max_overflow=20, pool_timeout=30s, pool_recycle=1800s)
- **Scheduler:** APScheduler runs 12 background jobs (10 recurring + 2 one-time startup) in the same process as Streamlit
- **Exchange:** Binance USDM Perpetual Futures via `ccxt.binanceusdm` (the only supported exchange, 15s timeout)
- **Deployment:** Railway (EU-West region, auto-deploy from git push)
- **Entry point:** `streamlit run scripts/app.py`

## Immutable Files

The following files are stable, fully tested, and must NOT be modified:

- `scripts/patterns.py` — 60 candlestick pattern detection functions
- `scripts/levels.py` — 12 support/resistance methods + chart pattern detection

Any AI tool that modifies these files is violating project rules. A pre-commit hook enforces this.

## Code Conventions

- PEP 8 style, 4-space indentation
- `snake_case` for functions and variables, `PascalCase` for classes
- Type hints encouraged but not enforced
- Exchange API calls (`ccxt`) must be wrapped in try/except with 15s timeout
- SQLAlchemy sessions must be properly closed after use (try/finally)
- NumPy/Pandas types must be converted to native Python (`float()`, `int()`) before writing to PostgreSQL
- No hardcoded API keys or secrets — use `.env` file
- Thread safety: Streamlit + APScheduler share one process; PostgreSQL connection pooling handles concurrent access

## Sub-Agents

Seven specialized agents are defined in `.claude/agents/`:

| Agent | Access | Responsibility |
|-------|--------|----------------|
| `backtest-analyst` | Read-only | Validate backtest statistical significance, detect overfitting, check composite score formula |
| `bug-debugger` | Read & Write | Diagnose APScheduler job failures, OHLCV data gaps, PostgreSQL connection issues, signal NaN propagation |
| `code-reviewer` | Read-only | Review trading logic correctness (TP/SL math, leverage handling), project rule compliance |
| `db-manager` | Read & Write | Schema changes in `models.py`, FK integrity, migration via `_run_migrations()` in engine.py |
| `indicator-developer` | Read & Write | 3-step pipeline: `indicators.py` (compute) → `indicators.py` (score) → `catalog.py` (register) |
| `page-builder` | Read & Write | Create Streamlit pages with `render()` pattern, register in `app.py` radio nav |
| `strategy-researcher` | Read-only | Analyze `strategy_performance` data, compare regime scores, suggest indicator combinations |

**Least Privilege:** Read-only agents cannot modify files.

## Key Workflows

### Adding an Indicator
1. `scripts/indicators.py` → add computation in `compute_all_indicators()`
2. `scripts/indicators.py` → add scoring in `score_all_indicators()` (output: -1.0 to +1.0)
3. `scripts/indicators.py` → add weight in `INDICATOR_WEIGHTS` dict
4. `scripts/strategy/catalog.py` → register under correct category (Trend/Entry/Volume/Volatility)

### Adding a UI Page
1. Create `scripts/views/page_xxx.py` with `render()` function
2. Add entry to radio navigation in `scripts/app.py`
3. Import and call `render()` in the page routing block

### Changing DB Schema
1. Modify `scripts/db/models.py` (SQLAlchemy ORM)
2. Add `ADD COLUMN IF NOT EXISTS` migration in `scripts/db/engine.py` → `_run_migrations()`
3. Restart application — tables auto-create, migrations run automatically

### Debugging
1. Scheduler jobs: check `worker/scheduler.py` → `max_instances=1`, stuck RUNNING jobs in `agent_jobs` table
2. Data pipeline: `collector.py` → `ccxt` rate limits, bulk dedup, backfill completion
3. Signal errors: `analyzer.py` → multi-TF data loading, confidence scoring, smart dedup
4. Connection pool: check pool_timeout=30s, pool_recycle=1800s in engine.py

## Constants Reference

| Parameter | Value | File |
|-----------|-------|------|
| Default leverage | 5x | backtester.py, trader.py |
| Position size | 1000 USD | backtester.py, trader.py |
| TP ATR multiplier | 2.5x | backtester.py |
| SL ATR multiplier | 1.5x | backtester.py |
| Warmup bars | 200 | backtester.py |
| Min trades for valid score | 20 | optimizer.py |
| Tracked timeframes | 5m, 15m, 30m, 1h, 4h | collector.py |
| TF weights | 5m=0.05, 15m=0.10, 30m=0.15, 1h=0.25, 4h=0.35 | analyzer.py |
| Bias threshold | +/-2.0 total score | analyzer.py |
| Max open trades/symbol | 1 | trader.py |
| Max total open trades | 20 | trader.py |
| Max correlation | 0.95 | trader.py |
| Confidence: YUKSEK/ORTA/DUSUK | >=75 / >=50 / <50 | analyzer.py |
| Auto-trade gate | YUKSEK or ORTA | analyzer.py |
| Dedup price threshold | 3% | analyzer.py |
| ccxt timeout | 15 seconds | analyzer.py, collector.py |
| DB pool | 10+20, timeout=30s, recycle=1800s | engine.py |

## System Flow Summary

```
Collector (5min) → OHLCV data (55 coins × 5 TFs)
                         ↓
Optimizer (6h) → Backtest all variants → Rank per coin → best_strategy_id
                         ↓
Analyzer (5min) → Multi-TF scoring (all 45 indicators) → Confidence → Signal
                         ↓
                   ORTA/YUKSEK → Auto paper trade (portfolio-aware)
                         ↓
Trade Checker (5min) → Partial TP → Trailing stop → TP2/SL → Close
                         ↓
                   Paper stats → Optimizer feedback loop
```

## Detailed Documentation

See `references/technical-reference.md` for complete DB schema (16 tables), all 12 scheduler jobs, critical function signatures, confidence scoring system, smart dedup logic, and multi-TF analysis details.
