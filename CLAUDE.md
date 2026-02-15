# CLAUDE.md - Phalidae Trading System

## Project Context

Phalidae is a self-learning crypto futures trading bot targeting Binance USDM Perpetual Futures (`ccxt.binanceusdm`). It automatically generates, backtests, and ranks strategy variants using 67 technical indicators across 4 categories, then executes the best strategies via paper trading.

**Tech stack:** Python 3.10+ · Streamlit · SQLAlchemy (SQLite WAL) · APScheduler · ccxt · pandas · plotly

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Start the trading system (creates DB + seeds 300 strategies on first run)
streamlit run scripts/app.py
```

**Runtime artifact:** `phalidae.db` is created at project root (gitignored).

## Coding Standards

- **Language:** Python 3.10+, type hints encouraged
- **Formatting:** PEP 8, 4-space indentation
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Error handling:** Always wrap exchange API calls (`ccxt`) in try/except. SQLAlchemy sessions must be properly closed.
- **Thread safety:** Streamlit + APScheduler share the same process. Use SQLAlchemy WAL mode (already configured in `scripts/db/engine.py`).
- **No secrets in code:** API keys go in `.env` (gitignored), never hardcoded.

## Directory Structure

```
Phalidae-v1-master/
├── .claude/
│   ├── settings.json                   # Shared project permissions (in git)
│   ├── settings.local.json             # Local overrides (gitignored)
│   ├── mcp.json                        # MCP server config (placeholder)
│   ├── agents/
│   │   ├── backtest-analyst.md         # Backtest quality & overfitting analysis (read-only)
│   │   ├── bug-debugger.md             # Scheduler, data pipeline & concurrency debugging
│   │   ├── code-reviewer.md            # Code review for trading logic & project rules (read-only)
│   │   ├── db-manager.md               # Schema changes, data integrity, query optimization
│   │   ├── indicator-developer.md      # End-to-end indicator addition pipeline
│   │   ├── page-builder.md             # Streamlit page creation with conventions
│   │   └── strategy-researcher.md      # Strategy performance research (read-only)
│   └── skills/
│       └── phalidae-trading/
│           └── SKILL.md                # Skill definition with YAML frontmatter
├── CLAUDE.md                           # This file
├── AGENTS.md                           # Vendor-agnostic agent instructions
├── requirements.txt                    # Python dependencies
├── scripts/                            # All executable source code
│   ├── app.py                          # Streamlit entry point, DB init, scheduler start
│   ├── indicators.py                   # 67 indicators + 45 scoring criteria
│   ├── patterns.py                     # 60 candlestick patterns ⚠️ DO NOT MODIFY
│   ├── levels.py                       # 12 S/R methods ⚠️ DO NOT MODIFY
│   ├── regime.py                       # Market regime detection (6 labels)
│   ├── signal_generator.py             # Signal generation (legacy + strategy-based)
│   ├── charting.py                     # Plotly charts
│   ├── db/                             # SQLAlchemy engine + 11 ORM models
│   │   ├── engine.py                   # Engine config (SQLite WAL, check_same_thread=False)
│   │   └── models.py                   # All 11 table definitions
│   ├── worker/                         # APScheduler: 6 background jobs
│   │   ├── scheduler.py                # Job definitions and intervals
│   │   ├── collector.py                # OHLCV + market data + regime collection
│   │   └── analyzer.py                 # Signal analysis + open trade checking
│   ├── strategy/                       # Strategy engine
│   │   ├── catalog.py                  # 43 indicators mapped to 4 categories + weights
│   │   ├── variants.py                 # Variant generation (seed/random/genetic)
│   │   ├── backtester.py               # Walk-forward backtest engine
│   │   └── optimizer.py                # Optimization loop, scoring, ranking
│   ├── paper_trader/                   # Paper trading engine
│   │   ├── trader.py                   # Open/close trades, snapshots
│   │   └── position.py                 # P&L, liquidation price, reasoning
│   └── pages/                          # Streamlit UI pages
│       ├── page_dashboard.py           # System status, best strategies, open trades
│       ├── page_signals.py             # DB signals + legacy live scan
│       ├── page_paper_trades.py        # Trade history, equity curve, details
│       ├── page_strategy_lab.py        # Strategy ranking, leaderboard, variant detail
│       └── page_data_explorer.py       # Coverage matrix, raw data, indicator charts
├── references/
│   └── technical-reference.md          # DB schema, functions, constants, strategy docs
└── assets/                             # Future use (templates, icons)
```

## Critical Rules

### Immutable Files
- **`scripts/patterns.py`** — 60 candlestick patterns. Stable and tested. **DO NOT MODIFY.**
- **`scripts/levels.py`** — 12 S/R methods + chart patterns. Stable and tested. **DO NOT MODIFY.**

### Development Workflows

**Adding a new indicator:**
1. Add calculation to `scripts/indicators.py` → `compute_all_indicators()`
2. Add scoring criterion to `scripts/indicators.py` → `score_all_indicators()`
3. Register in `scripts/strategy/catalog.py` under the appropriate category

**Adding a new page:**
1. Create `scripts/pages/page_xxx.py` with a `render()` function
2. Add to the radio list in `scripts/app.py`
3. Import and call `render()` in the page routing block

**Changing DB schema:**
1. Update `scripts/db/models.py`
2. Delete `phalidae.db` at project root
3. Restart the application (tables are auto-created)

### Exchange Constraint
- Only `ccxt.binanceusdm` (Binance USDM Perpetual Futures) is supported.
- Do not add support for other exchanges without explicit approval.

### Key Constants
| Constant | Value | Location |
|----------|-------|----------|
| Default leverage | 5x | backtester.py, trader.py |
| Position size | 1000 USD | backtester.py, trader.py |
| TP ATR multiplier | 2.5x | backtester.py |
| SL ATR multiplier | 1.5x | backtester.py |
| Warmup bars | 200 | backtester.py |
| Min trades for scoring | 20 | optimizer.py |
| Timeframes | 15m, 1h, 4h, 1d | collector.py |

## Technical Reference

For detailed documentation including complete DB schema (11 tables), all scheduler jobs, critical function signatures, composite score formula, strategy variant composition, and indicator category mappings, see:

**`references/technical-reference.md`**
