"""
Phalidae v2 - SQLAlchemy Engine & Session Factory
PostgreSQL with connection pooling.
"""

import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

load_dotenv()

_DB_URL = (
    os.environ.get("DATABASE_URL")
    or os.environ.get("DATABASE_PRIVATE_URL")
    or os.environ.get("DATABASE_PUBLIC_URL")
)

# Fallback: construct from Railway PG* variables
if not _DB_URL:
    pg_host = os.environ.get("PGHOST")
    pg_port = os.environ.get("PGPORT", "5432")
    pg_user = os.environ.get("PGUSER")
    pg_pass = os.environ.get("PGPASSWORD")
    pg_db = os.environ.get("PGDATABASE")
    if pg_host and pg_user and pg_db:
        _DB_URL = f"postgresql://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}"

if not _DB_URL:
    import logging
    logging.error(
        "ENV DUMP (DB-related): %s",
        {k: v[:20] + "..." for k, v in os.environ.items()
         if any(x in k.upper() for x in ["DATABASE", "PG", "POSTGRES"])}
    )
    raise RuntimeError(
        "No database URL found. Set DATABASE_URL or configure PGHOST/PGUSER/PGDATABASE."
    )
if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)
_ENGINE = None
_SESSION_FACTORY = None


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            _DB_URL,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,      # Fail fast if pool exhausted (default: 30s)
            pool_recycle=1800,    # Recycle connections every 30min (prevent stale)
        )
    return _ENGINE


def get_session() -> Session:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine())
    return _SESSION_FACTORY()


def create_all():
    from db.models import Base
    Base.metadata.create_all(get_engine())
    _run_migrations()
    _migrate_open_trade_tp_levels()


def _run_migrations():
    """Add missing columns to existing tables. Safe to run multiple times."""
    import logging
    from sqlalchemy import text, inspect

    logger = logging.getLogger("phalidae.migrations")

    migrations = [
        # Phase 2: PaperTrade new columns
        ("paper_trades", "partial_tp_taken", "BOOLEAN DEFAULT FALSE"),
        ("paper_trades", "partial_tp_price", "FLOAT"),
        ("paper_trades", "partial_tp_pnl", "FLOAT DEFAULT 0.0"),
        ("paper_trades", "tp2_price", "FLOAT"),
        ("paper_trades", "tp3_price", "FLOAT"),
        ("paper_trades", "risk_pct", "FLOAT"),
        # Phase 5: Signal new columns
        ("signals", "confidence_score", "FLOAT"),
        ("signals", "confidence_breakdown", "JSON"),
        ("signals", "eta_hours_low", "FLOAT"),
        ("signals", "eta_hours_high", "FLOAT"),
        ("signals", "news_risk_score", "FLOAT"),
        ("signals", "invalidation_note", "TEXT"),
        # Deep learning: custom weights + adaptive TP/SL on strategy_variants
        ("strategy_variants", "custom_weights", "JSON"),
        ("strategy_variants", "tp_atr_mult", "FLOAT DEFAULT 2.5"),
        ("strategy_variants", "sl_atr_mult", "FLOAT DEFAULT 1.75"),
        # Deep learning: regime-specific best strategies on coin_config
        ("coin_config", "best_trending_strategy_id", "INTEGER"),
        ("coin_config", "best_ranging_strategy_id", "INTEGER"),
        ("coin_config", "best_volatile_strategy_id", "INTEGER"),
    ]

    engine = get_engine()

    # Pre-check existing columns to skip unnecessary ALTER TABLEs
    inspector = inspect(engine)
    existing = {}
    for table_name in {m[0] for m in migrations}:
        try:
            cols = inspector.get_columns(table_name)
            existing[table_name] = {c["name"] for c in cols}
        except Exception:
            existing[table_name] = set()

    needed = [
        (t, c, ct) for t, c, ct in migrations
        if c not in existing.get(t, set())
    ]

    if not needed:
        logger.info("Migrations: all columns already exist, nothing to do")
        return

    with engine.connect() as conn:
        # Set lock timeout to 5s to prevent deadlocks on concurrent startup
        conn.execute(text("SET lock_timeout = '5s'"))
        for table, column, col_type in needed:
            try:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                    )
                )
                logger.info(f"Migration added: {table}.{column}")
            except Exception as e:
                logger.warning(f"Migration skip {table}.{column}: {e}")
        conn.commit()
    logger.info(f"Migrations applied: {len(needed)} columns")


def _migrate_open_trade_tp_levels():
    """One-time migration: recalculate TP levels for open trades using new multipliers.
    tp_atr_mult: 3.0 → 2.0, TP1 ratio: 0.48 → 0.6, TP3 ratio: 1.6 → 1.4.
    Post-TP1 SL: breakeven → entry + 0.25×ATR.
    Idempotent: marks migrated trades via management log to avoid re-running."""
    import logging
    logger = logging.getLogger("phalidae.migrations")

    session = get_session()
    try:
        from db.models import PaperTrade, TradeManagementLog
        from sqlalchemy import and_

        # Check if migration already ran (look for marker log entry)
        marker = (
            session.query(TradeManagementLog)
            .filter_by(event_type="TP_MIGRATION_V2")
            .first()
        )
        if marker:
            return  # Already migrated

        open_trades = session.query(PaperTrade).filter_by(status="OPEN").all()
        if not open_trades:
            return

        logger.info(f"Migrating TP levels for {len(open_trades)} open trades...")

        # Import ATR calculation
        try:
            from worker.collector import get_ohlcv_df
            from indicators import compute_all_indicators
        except ImportError:
            logger.warning("Cannot import indicators for TP migration, skipping")
            return

        import pandas as pd
        from datetime import datetime

        NEW_TP_MULT = 2.0
        NEW_TP1_RATIO = 0.6
        NEW_TP3_RATIO = 1.4

        migrated = 0
        for t in open_trades:
            try:
                # Get current ATR for this symbol
                df = get_ohlcv_df(t.symbol, "4h", limit=50)
                if df.empty or len(df) < 20:
                    continue
                df = compute_all_indicators(df)
                atr = float(df["atr"].iloc[-1]) if "atr" in df.columns and pd.notna(df["atr"].iloc[-1]) else 0.0
                if atr <= 0:
                    continue

                entry = float(t.entry_price)
                tp_mult = NEW_TP_MULT
                tp1_ratio = tp_mult * NEW_TP1_RATIO
                tp2_ratio = tp_mult
                tp3_ratio = tp_mult * NEW_TP3_RATIO

                if t.bias == "LONG":
                    new_tp1 = round(entry + tp1_ratio * atr, 6)
                    new_tp2 = round(entry + tp2_ratio * atr, 6)
                    new_tp3 = round(entry + tp3_ratio * atr, 6)
                else:
                    new_tp1 = round(entry - tp1_ratio * atr, 6)
                    new_tp2 = round(entry - tp2_ratio * atr, 6)
                    new_tp3 = round(entry - tp3_ratio * atr, 6)

                # Update TP levels
                t.partial_tp_price = new_tp1
                t.tp_price = new_tp2
                t.tp2_price = new_tp2
                t.tp3_price = new_tp3

                # If partial TP already taken, update SL to entry + 0.25×ATR
                if t.partial_tp_taken:
                    if t.bias == "LONG":
                        new_sl = round(entry + 0.25 * atr, 6)
                    else:
                        new_sl = round(entry - 0.25 * atr, 6)
                    t.sl_price = new_sl
                    t.trailing_stop_price = new_sl

                migrated += 1
            except Exception as e:
                logger.warning(f"TP migration skip #{t.id} ({t.symbol}): {e}")

        # Add marker to prevent re-running
        if migrated > 0:
            session.add(TradeManagementLog(
                paper_trade_id=open_trades[0].id,
                timestamp=datetime.utcnow(),
                event_type="TP_MIGRATION_V2",
                old_value=3.0,
                new_value=2.0,
                reason=f"Migrated {migrated} trades: tp_mult=2.0",
                current_price=0,
                current_pnl_pct=0,
            ))

        session.commit()
        logger.info(f"TP migration complete: {migrated}/{len(open_trades)} trades updated")
    except Exception as e:
        session.rollback()
        logger.error(f"TP migration error: {e}")
    finally:
        session.close()
