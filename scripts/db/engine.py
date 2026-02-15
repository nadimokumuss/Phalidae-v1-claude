"""
Phalidae v2 - SQLAlchemy Engine & Session Factory
SQLite with WAL mode for concurrent read/write.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "phalidae.db")
_ENGINE = None
_SESSION_FACTORY = None


def _enable_wal(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            f"sqlite:///{_DB_PATH}",
            echo=False,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )
        event.listen(_ENGINE, "connect", _enable_wal)
    return _ENGINE


def get_session() -> Session:
    global _SESSION_FACTORY
    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(bind=get_engine())
    return _SESSION_FACTORY()


def create_all():
    from db.models import Base
    Base.metadata.create_all(get_engine())
