# CLAUDE.md - Phalidae Trading System

## Project Context

Phalidae is a self-learning crypto futures trading bot targeting Binance USDM Perpetual Futures (`ccxt.binanceusdm`). It runs 24/7 on Railway, automatically collecting market data across 5 timeframes, generating signals using 45 scoring criteria from 67 technical indicators, backtesting and ranking 300+ strategy variants per coin, and executing paper trades with portfolio-aware position sizing.

The system's core philosophy: **generate as many signals as possible so the optimizer learns faster**. Over time, genetic evolution and backtest feedback naturally identify which indicators and strategy combinations work best for each coin.

**Tech stack:** Python 3.10+ · Streamlit · SQLAlchemy (PostgreSQL) · APScheduler · ccxt · pandas · plotly

**Deployment:** Railway (EU-West region, required because Binance blocks US IPs)

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# PostgreSQL setup (one-time)
createdb phalidae
# Or: psql -c "CREATE DATABASE phalidae;"

# Configure .env (already provided with defaults)
# DATABASE_URL=postgresql://phalidae:phalidae@localhost:5432/phalidae

# Enable pre-commit hook (protects patterns.py & levels.py)
git config core.hooksPath .hooks

# Start the trading system (creates tables + seeds 300 strategies on first run)
streamlit run scripts/app.py
```

**Prerequisites:** PostgreSQL must be running locally. Connection string is read from `.env` (`DATABASE_URL`).

## Coding Standards

- **Language:** Python 3.10+, type hints encouraged
- **Formatting:** PEP 8, 4-space indentation
- **Naming:** `snake_case` for functions/variables, `PascalCase` for classes
- **Error handling:** Always wrap exchange API calls (`ccxt`) in try/except. SQLAlchemy sessions must be properly closed in `finally` blocks.
- **Thread safety:** Streamlit + APScheduler share the same process. PostgreSQL connection pooling is configured in `scripts/db/engine.py` (pool_size=10, max_overflow=20, pool_timeout=30s, pool_recycle=1800s).
- **ccxt timeout:** All exchange instances must use `{"enableRateLimit": True, "timeout": 15000}` to prevent hanging API calls.
- **NumPy/Pandas types:** Always convert to native Python types before writing to PostgreSQL (use `float()`, `int()`). The `_to_float()` helper exists in analyzer.py and trader.py.
- **No secrets in code:** API keys go in `.env` (gitignored), never hardcoded.

## Directory Structure

```
Phalidae-v1-master/
├── .claude/
│   ├── settings.json                   # Shared project permissions (in git)
│   ├── settings.local.json             # Local overrides (gitignored)
│   ├── mcp.json                        # MCP: PostgreSQL server → phalidae DB
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
│   ├── signal_generator.py             # Manual live scan (multi-TF, all indicators)
│   ├── charting.py                     # Plotly charts
│   ├── db/                             # SQLAlchemy engine + 16 ORM models
│   │   ├── engine.py                   # Engine config (PostgreSQL, connection pooling)
│   │   └── models.py                   # All 16 table definitions
│   ├── worker/                         # APScheduler: 12 background jobs
│   │   ├── scheduler.py                # Job definitions, intervals, bootstrap pipeline
│   │   ├── collector.py                # OHLCV + market data + regime + symbol refresh + backfill
│   │   ├── analyzer.py                 # Multi-TF signal analysis + trade checker + smart dedup
│   │   └── news_collector.py           # CryptoCompare news + sentiment + risk scoring
│   ├── strategy/                       # Strategy engine
│   │   ├── catalog.py                  # 43 indicators mapped to 4 categories + weights
│   │   ├── variants.py                 # Variant generation (seed/random/genetic)
│   │   ├── backtester.py               # Walk-forward backtest engine
│   │   └── optimizer.py                # Optimization loop, scoring, ranking, correlations
│   ├── paper_trader/                   # Paper trading engine
│   │   ├── trader.py                   # Open/close trades, snapshots, correlation check
│   │   ├── position.py                 # P&L, liquidation price, reasoning
│   │   └── portfolio.py                # Portfolio equity, position sizing, risk management
│   └── views/                          # Streamlit UI pages
│       ├── page_dashboard.py           # System status, best strategies, open trades
│       ├── page_signals.py             # DB signals + legacy live scan
│       ├── page_paper_trades.py        # Trade history, equity curve, details
│       ├── page_strategy_lab.py        # Strategy ranking, leaderboard, variant detail
│       └── page_data_explorer.py       # Coverage matrix, raw data, indicator charts
├── references/
│   ├── technical-reference.md          # DB schema, functions, constants, strategy docs
│   ├── analysis-methods.md             # 67 indicators, 60 patterns, 12 S/R methods, scoring
│   ├── project-details.md              # Detailed system architecture and working logic
│   ├── calisma-mantigi.md              # System philosophy (Turkish)
│   ├── detayli-calisma-mantigi.md      # Feature roadmap & priority list (Turkish)
│   └── v2-gelistirme.md               # V2 development guide (Turkish)
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
1. Create `scripts/views/page_xxx.py` with a `render()` function
2. Add to the radio list in `scripts/app.py`
3. Import and call `render()` in the page routing block
4. Use the `page-builder` agent for convention-compliant pages

**Changing DB schema:**
1. Update `scripts/db/models.py`
2. Add migration in `scripts/db/engine.py` → `_run_migrations()` (adds columns safely with `ADD COLUMN IF NOT EXISTS`)
3. Restart the application (tables are auto-created, migrations run automatically)
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
| Position size | 200 USD | backtester.py, trader.py |
| TP ATR multiplier | 2.5x (default, adaptive per variant) | backtester.py, models.py |
| SL ATR multiplier | 1.75x (default, adaptive per variant) | backtester.py, models.py |
| TP1 ATR multiplier | 0.48×tp_atr_mult (default 1.2x) | signal_generator.py |
| Warmup bars | 200 | backtester.py |
| Min trades for scoring | 20 | optimizer.py |
| Timeframes | 5m, 15m, 30m, 1h, 4h | collector.py |
| TF weights | 5m=0.05, 15m=0.10, 30m=0.15, 1h=0.25, 4h=0.35 | analyzer.py, signal_generator.py |
| Bias threshold | +/-1.5 total score | analyzer.py |
| Max open trades/symbol | 1 | trader.py |
| Max total open trades | 150 | trader.py, portfolio.py |
| Max correlation | 0.95 | trader.py |
| Daily drawdown limit | 10% (per coin, configurable) | trader.py |
| Initial capital | 100,000 USD (learning mode) | portfolio.py |
| Max risk per trade | 1% | portfolio.py |
| Max total exposure | 90% | portfolio.py |
| Max daily loss | 15% | portfolio.py |
| Confidence: YUKSEK | >= 75/100 | analyzer.py |
| Confidence: ORTA | >= 50/100 | analyzer.py |
| Confidence: DUSUK | < 50/100 | analyzer.py |
| Auto-trade gate | YUKSEK, ORTA, or DUSUK (50% size) | analyzer.py |
| Dedup price threshold | 1.5% price change | analyzer.py |
| News risk skip | > 0.9 | analyzer.py |
| News risk halve | > 0.7 | analyzer.py |
| ccxt timeout | 15 seconds | analyzer.py, collector.py |
| DB pool size | 10 + 20 overflow | engine.py |
| DB pool timeout | 30 seconds | engine.py |
| DB pool recycle | 1800 seconds (30 min) | engine.py |
| Min quote volume filter | $5M 24h | collector.py |
| Max spread filter | 0.15% | collector.py |
| Tracked coins | ~242 (filtered) | collector.py |

## System Architecture

### Signal Generation Flow (Analyzer - every 5 min)

```
For each of ~242 active coins (filtered):
  1. Load OHLCV data for 5 timeframes (5m, 15m, 30m, 1h, 4h)
  2. Compute all 67 indicators on each timeframe
  3. Score all 45 criteria on each timeframe
  4. Weighted average across timeframes → final_ind_score
  5. Detect patterns on each timeframe → final_pat_score
  6. Chart pattern bonus from 4h levels (±3 max)
  7. Trend line bonus from 4h levels (±2 max)
  8. total_score = indicators + patterns + chart_patterns + trend_lines
  9. Bias: >= +1.5 → LONG, <= -1.5 → SHORT, else skip
 10. Smart dedup check (open trade? same signal? price moved >1.5%?)
 11. Confidence scoring (7 components, 100-point scale, regime-specific WR)
 12. Save signal → auto paper trade (YUKSEK, ORTA, or DUSUK at 50% size)
```

### Strategy Optimization Flow (Optimizer - every 6h)

```
1. Generate 10 random exploration variants (with random TP/SL + optional weight perturbation)
2. Generate 10 genetic crossover variants (evolves composition + weights + TP/SL)
3. For each coin × each variant:
   → Walk-forward backtest on historical 4h data (up to 3000 bars)
   → Uses variant's custom_weights, tp_atr_mult, sl_atr_mult
   → Calculate: win_rate, profit_factor, sharpe, max_drawdown
   → Composite score = weighted sum of normalized metrics
4. Rank strategies per coin (rank=1 = best)
5. Update CoinConfig: best_strategy_id + best_trending/ranging/volatile_strategy_id
6. Compute pairwise correlations between symbols
```

### Paper Trade Lifecycle

```
Signal (ORTA/YUKSEK) → open_paper_trade()
  → Portfolio check (can_open_trade, calculate_position_size)
  → Limits check (per-symbol, total, daily drawdown, correlation)
  → Multi-TP setup: TP1 (partial), TP2 (main), TP3 (trailing)

Every 5 min: check_open_trades()
  → Record snapshot (unrealized P&L, MFE/MAE)
  → Trailing stop updates (0.5×ATR→BE, 1×ATR→+0.3ATR, 2×ATR→trail 1ATR)
  → Partial TP: close 50% at TP1, move SL to breakeven
  → TP2/SL/Liquidation/Time stop checks

Close → update paper_stats on strategy_performance (feedback loop)
```

## Sub-Agents

Seven specialized agents are available in `.claude/agents/`:

| Agent | Access Level | When to Use |
|-------|-------------|-------------|
| `backtest-analyst` | Read-only | Validating backtest results, detecting overfitting, checking statistical significance |
| `bug-debugger` | Read & Write | Diagnosing scheduler failures, data gaps, PostgreSQL connection issues, signal NaN errors |
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

### PostgreSQL (phalidae)

Configured in `.claude/mcp.json`. Provides direct SQL access to the runtime database for:
- Querying `strategy_performance` to find top strategies per symbol
- Inspecting `paper_trades` history and P&L distribution
- Checking `ohlcv_data` coverage and gaps
- Analyzing `signals` with their `score_breakdown` JSONB

**Prerequisite:** `npx` must be available (Node.js installed). PostgreSQL must be running with the `phalidae` database created.

## Technical Reference

For detailed documentation see:

- **`references/technical-reference.md`** — DB schema (16 tables), 12 scheduler jobs, function signatures, composite score formula, confidence scoring, smart dedup, multi-TF analysis
- **`references/analysis-methods.md`** — 67 indicators (sources, formulas, parameters), 60 candlestick patterns (detection rules), 12 S/R methods (algorithms), 6 market regimes (decision tree), scoring system (45 criteria with weights)
- **`references/project-details.md`** — Detailed system architecture, data flow, optimization pipeline, paper trading rules, strategy evolution
