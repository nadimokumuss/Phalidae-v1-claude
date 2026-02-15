# AGENTS.md - Phalidae Trading System

This file provides vendor-agnostic instructions for AI coding assistants (Claude Code, Cursor, Copilot, etc.).

## Project Overview

Phalidae is an automated crypto futures trading system for Binance USDM Perpetual Futures. It uses 67 technical indicators to generate, backtest, and rank strategy variants, then paper trades the best strategies.

## Architecture

- **Runtime:** Python 3.10+ with Streamlit as the UI framework
- **Database:** SQLite with WAL mode via SQLAlchemy ORM (11 tables)
- **Scheduler:** APScheduler runs 6 background jobs in the same process as Streamlit
- **Exchange:** Binance USDM Perpetual Futures via `ccxt.binanceusdm` (the only supported exchange)
- **Entry point:** `streamlit run scripts/app.py`

## Immutable Files

The following files are stable, fully tested, and must NOT be modified:

- `scripts/patterns.py` — 60 candlestick pattern detection functions
- `scripts/levels.py` — 12 support/resistance methods + chart pattern detection

Any AI tool that modifies these files is violating project rules.

## Code Conventions

- PEP 8 style, 4-space indentation
- `snake_case` for functions and variables, `PascalCase` for classes
- Type hints encouraged but not enforced
- Exchange API calls must be wrapped in try/except
- SQLAlchemy sessions must be properly closed after use
- No hardcoded API keys or secrets — use `.env` file

## Key Workflows

### Adding an Indicator
1. `scripts/indicators.py` → add computation in `compute_all_indicators()`
2. `scripts/indicators.py` → add scoring in `score_all_indicators()`
3. `scripts/strategy/catalog.py` → register under correct category (Trend/Entry/Volume/Volatility)

### Adding a UI Page
1. Create `scripts/pages/page_xxx.py` with `render()` function
2. Add entry to radio navigation in `scripts/app.py`

### Changing DB Schema
1. Modify `scripts/db/models.py`
2. Delete `phalidae.db` (runtime artifact at project root)
3. Restart application — tables auto-create

## Constants Reference

| Parameter | Value |
|-----------|-------|
| Default leverage | 5x |
| Position size | 1000 USD |
| TP ATR multiplier | 2.5x |
| SL ATR multiplier | 1.5x |
| Warmup bars | 200 |
| Min trades for valid score | 20 |
| Tracked timeframes | 15m, 1h, 4h, 1d |

## Detailed Documentation

See `references/technical-reference.md` for complete DB schema, function signatures, composite score formula, and strategy variant structure.
