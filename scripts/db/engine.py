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
if not _DB_URL:
    raise RuntimeError(
        "No database URL found. Set DATABASE_URL, DATABASE_PRIVATE_URL, "
        "or DATABASE_PUBLIC_URL as an environment variable."
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
