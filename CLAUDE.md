# CLAUDE.md - Phalidae Trading System

## Quick Start
```bash
pip install -r requirements.txt
streamlit run scripts/app.py
```

## Project Layout (Claude Skill Format)

```
phalidae-trading/
├── SKILL.md                        # Skill definition (YAML frontmatter + usage)
├── CLAUDE.md                       # This file
├── requirements.txt                # Python dependencies
├── scripts/                        # All executable code
│   ├── app.py                      # Streamlit entry point
│   ├── indicators.py               # 67 indicators + 45 scoring criteria
│   ├── patterns.py                 # 60 candlestick patterns (DO NOT MODIFY)
│   ├── levels.py                   # 12 S/R methods (DO NOT MODIFY)
│   ├── regime.py                   # Market regime detection
│   ├── signal_generator.py         # Signal generation
│   ├── charting.py                 # Plotly charts
│   ├── db/                         # SQLAlchemy engine + 11 ORM models
│   ├── worker/                     # APScheduler: 6 background jobs
│   ├── strategy/                   # Variants, backtester, optimizer
│   ├── paper_trader/               # Paper trade engine
│   └── pages/                      # Streamlit UI pages
├── references/
│   └── technical-reference.md      # Detailed technical docs (DB schema, functions, constants)
└── assets/                         # Future use
```

## Key Rules

- **DO NOT** modify `scripts/patterns.py` or `scripts/levels.py`
- New indicator: `scripts/indicators.py` → `score_all_indicators()` → `scripts/strategy/catalog.py`
- New page: `scripts/pages/page_xxx.py` → add to `scripts/app.py` radio list
- DB schema change: update `scripts/db/models.py` → delete `phalidae.db` → restart
- Exchange: Binance USDM Perpetual Futures only (`ccxt.binanceusdm`)
- DB file (`phalidae.db`) is created at project root at runtime

## Technical Details

See `references/technical-reference.md` for:
- Complete DB schema (11 tables with relationships)
- All scheduler jobs and intervals
- Critical function signatures
- Constants (leverage, position size, scoring weights, timeframes)
- Strategy variant composition and signal conditions
- Indicator categories (Trend/Entry/Volume/Volatility)
