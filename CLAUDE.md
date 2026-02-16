# CLAUDE.md - Phalidae Trading System

## Project Context

Phalidae is a self-learning crypto futures trading bot targeting Binance USDM Perpetual Futures (`ccxt.binanceusdm`). It automatically generates, backtests, and ranks strategy variants using 67 technical indicators across 4 categories, then executes the best strategies via paper trading.

**Tech stack:** Python 3.10+ · Streamlit · SQLAlchemy (SQLite WAL) · APScheduler · ccxt · pandas · plotly

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Enable pre-commit hook (protects patterns.py & levels.py)
git config core.hooksPath .hooks

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
│   ├── mcp.json                        # MCP: SQLite server → phalidae.db
│   ├── agents/                         # 7 specialized sub-agents
│   │   ├── backtest-analyst.md         # Backtest quality & overfitting analysis (read-only)
│   │   ├── bug-debugger.md             # Scheduler, data pipeline & concurrency debugging
│   │   ├── code-reviewer.md            # Code review for trading logic & project rules (read-only)
│   │   ├── db-manager.md              # Schema changes, data integrity, query optimization
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

These files are protected by a pre-commit hook (see [Hooks](#hooks) section). Any commit touching them will be rejected.

### Development Workflows

**Adding a new indicator:**
1. Add calculation to `scripts/indicators.py` → `compute_all_indicators()`
2. Add scoring criterion to `scripts/indicators.py` → `score_all_indicators()`
3. Register in `scripts/strategy/catalog.py` under the appropriate category
4. Use the `indicator-developer` agent for guided implementation

**Adding a new page:**
1. Create `scripts/pages/page_xxx.py` with a `render()` function
2. Add to the radio list in `scripts/app.py`
3. Import and call `render()` in the page routing block
4. Use the `page-builder` agent for convention-compliant pages

**Changing DB schema:**
1. Update `scripts/db/models.py`
2. Delete `phalidae.db` at project root
3. Restart the application (tables are auto-created)
4. Use the `db-manager` agent for safe schema migrations

**Debugging issues:**
1. Use the `bug-debugger` agent for scheduler, data pipeline, and concurrency problems
2. Check `references/technical-reference.md` for function signatures and job intervals

**Reviewing code changes:**
1. Use the `code-reviewer` agent before merging — validates trading logic and project rules
2. Use the `backtest-analyst` agent to validate strategy performance claims

**Researching strategies:**
1. Use the `strategy-researcher` agent to analyze performance data and suggest improvements

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

## Sub-Agents

Seven specialized agents are available in `.claude/agents/`:

| Agent | Access Level | When to Use |
|-------|-------------|-------------|
| `backtest-analyst` | Read-only | Validating backtest results, detecting overfitting, checking statistical significance |
| `bug-debugger` | Read & Write | Diagnosing scheduler failures, data gaps, SQLite locking, signal NaN errors |
| `code-reviewer` | Read-only | Pre-merge review of trading logic, project rule compliance, Python best practices |
| `db-manager` | Read & Write | Adding tables/columns, fixing data integrity issues, optimizing slow queries |
| `indicator-developer` | Read & Write | Adding new indicators (3-step pipeline: compute → score → catalog) |
| `page-builder` | Read & Write | Creating new Streamlit pages with correct conventions and routing |
| `strategy-researcher` | Read-only | Analyzing strategy performance, comparing regime-specific scores, suggesting combinations |

**Least Privilege**: Read-only agents (backtest-analyst, code-reviewer, strategy-researcher) cannot modify files — they analyze and report only.

## Hooks

### Pre-commit: Immutable File Protection

A pre-commit hook guards `scripts/patterns.py` and `scripts/levels.py` from accidental modification. If a commit includes changes to either file, the commit is rejected with an error message.

**Hook file:** `.hooks/pre-commit` (git-tracked, shared across team)

**Setup (one-time per clone):**
```bash
git config core.hooksPath .hooks
```

**Protected files:**
- `scripts/patterns.py` — 60 candlestick pattern functions
- `scripts/levels.py` — 12 S/R detection methods + chart patterns

**Bypass:** Only with explicit user approval and `--no-verify` flag (discouraged).

## MCP Servers

### SQLite (phalidae.db)

Configured in `.claude/mcp.json`. Provides direct SQL access to the runtime database for:
- Querying `strategy_performance` to find top strategies per symbol
- Inspecting `paper_trades` history and P&L distribution
- Checking `ohlcv_data` coverage and gaps
- Analyzing `signals` with their `score_breakdown` JSON

**Prerequisite:** `npx` must be available (Node.js installed). The DB file is created after first `streamlit run`.

## Technical Reference

For detailed documentation see:

- **`references/technical-reference.md`** — DB schema (11 tables), scheduler jobs, function signatures, composite score formula, strategy variant composition
- **`references/analysis-methods.md`** — 67 indicators (sources, formulas, parameters), 60 candlestick patterns (detection rules), 12 S/R methods (algorithms), 6 market regimes (decision tree), scoring system (45 criteria with weights)
