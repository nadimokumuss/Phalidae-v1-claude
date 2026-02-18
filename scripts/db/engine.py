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


def _run_migrations():
    """Add missing columns to existing tables. Safe to run multiple times."""
    import logging
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
    ]

    engine = get_engine()
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                conn.execute(
                    __import__("sqlalchemy").text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                    )
                )
            except Exception as e:
                logger.warning(f"Migration skip {table}.{column}: {e}")
        conn.commit()
    logger.info(f"Migrations checked: {len(migrations)} columns")
