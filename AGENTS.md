# AGENTS.md - Phalidae Trading System

This file provides vendor-agnostic instructions for AI coding assistants (Claude Code, Cursor, Copilot, etc.).

## Project Overview

Phalidae is an automated crypto futures trading system for Binance USDM Perpetual Futures. It uses 67 technical indicators to generate, backtest, and rank strategy variants, then paper trades the best strategies automatically.

## Architecture

- **Runtime:** Python 3.10+ with Streamlit as the UI framework
- **Database:** SQLite with WAL mode via SQLAlchemy ORM (11 tables, file: `phalidae.db` at project root)
- **Scheduler:** APScheduler runs 6 background jobs in the same process as Streamlit
- **Exchange:** Binance USDM Perpetual Futures via `ccxt.binanceusdm` (the only supported exchange)
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
- Exchange API calls (`ccxt`) must be wrapped in try/except
- SQLAlchemy sessions must be properly closed after use (try/finally or context manager)
- No hardcoded API keys or secrets — use `.env` file
- Thread safety: Streamlit + APScheduler share one process; WAL mode handles concurrent DB access

## Sub-Agents

Seven specialized agents are defined in `.claude/agents/`:

| Agent | Access | Responsibility |
|-------|--------|----------------|
| `backtest-analyst` | Read-only | Validate backtest statistical significance, detect overfitting, check composite score formula (0.30×WR + 0.25×PF + 0.20×Sharpe + 0.15×DD + 0.10×TC) |
| `bug-debugger` | Read & Write | Diagnose APScheduler job failures, OHLCV data gaps, SQLite locking under concurrent access, signal NaN propagation |
| `code-reviewer` | Read-only | Review trading logic correctness (TP/SL math, leverage handling), project rule compliance, Python best practices |
| `db-manager` | Read & Write | Schema changes in `models.py`, FK integrity validation, index optimization for 11 tables |
| `indicator-developer` | Read & Write | 3-step pipeline: `indicators.py` (compute) → `indicators.py` (score) → `catalog.py` (register category) |
| `page-builder` | Read & Write | Create Streamlit pages with `render()` pattern, register in `app.py` radio nav, follow existing UI conventions |
| `strategy-researcher` | Read-only | Analyze `strategy_performance` data, compare regime scores (trending/ranging/volatile), suggest non-redundant indicator combinations |

**Least Privilege:** Read-only agents (backtest-analyst, code-reviewer, strategy-researcher) cannot modify files.

## Key Workflows

### Adding an Indicator
1. `scripts/indicators.py` → add computation in `compute_all_indicators()`
2. `scripts/indicators.py` → add scoring in `score_all_indicators()` (output: -1.0 to +1.0)
3. `scripts/indicators.py` → add weight in `INDICATOR_WEIGHTS` dict
4. `scripts/strategy/catalog.py` → register under correct category (Trend/Entry/Volume/Volatility)

### Adding a UI Page
1. Create `scripts/pages/page_xxx.py` with `render()` function
2. Add entry to radio navigation in `scripts/app.py`
3. Import and call `render()` in the page routing block
4. DB access pattern: `session = get_session()` → try/finally → `session.close()`

### Changing DB Schema
1. Modify `scripts/db/models.py` (SQLAlchemy ORM)
2. Delete `phalidae.db` (runtime artifact at project root)
3. Restart application — tables auto-create on startup
4. No migration framework — destructive recreate only

### Debugging
1. Scheduler jobs: check `worker/scheduler.py` → `max_instances=1`, interval overlaps
2. Data pipeline: `collector.py` → `ccxt` rate limits, symbol refresh, incremental gaps
3. Signal errors: `signal_generator.py` → NaN from missing indicators, composition key mismatch
4. Concurrency: WAL mode should prevent locks; check `session.close()` in all paths

## Constants Reference

| Parameter | Value | File |
|-----------|-------|------|
| Default leverage | 5x | backtester.py, trader.py |
| Position size | 1000 USD | backtester.py, trader.py |
| TP ATR multiplier | 2.5x | backtester.py |
| SL ATR multiplier | 1.5x | backtester.py |
| Warmup bars | 200 | backtester.py |
| Min trades for valid score | 20 | optimizer.py |
| Tracked timeframes | 15m, 1h, 4h, 1d | collector.py |
| Max open trades/symbol | 1 | trader.py |
| Max total open trades | 20 | trader.py |

## Strategy Variant Structure

Each variant has a JSON composition:
```json
{
  "trend": ["EMA Ribbon", "MACD"],
  "entry": ["RSI", "Stochastic"],
  "volume": ["OBV"],
  "volatility": ["Squeeze"]
}
```

**Signal conditions:**
- LONG: avg(trend) >= threshold AND avg(entry) >= threshold AND (volume > 0 OR not required)
- SHORT: avg(trend) <= -threshold AND avg(entry) <= -threshold AND (volume < 0 OR not required)

**Generation methods:** Seed (~300 initial), Random (10/cycle), Genetic crossover (10/cycle)

## Detailed Documentation

See `references/technical-reference.md` for complete DB schema (11 tables with FK relationships), all 6 scheduler job chains, critical function signatures, and indicator category mappings (Trend:16, Entry:15, Volume:7, Volatility:5).
