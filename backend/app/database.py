"""Database engine, session factory and schema bootstrap."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

# SQLite needs check_same_thread disabled for FastAPI's threaded requests, and
# a lock timeout so concurrent read/write requests wait instead of erroring
# with "database is locked" (which surfaces as HTTP 500 on read-back).
connect_args = {"check_same_thread": False, "timeout": 30}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def configure_engine(database_url: str) -> None:
    """Rebind the engine to a different database URL at runtime.

    Used by the benchmark harness to give each task a fully isolated database
    (avoids cross-task state contamination), and by tests to use a temp DB.
    """
    global engine, SessionLocal
    engine = create_engine(database_url, connect_args=connect_args)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables (idempotent)."""
    import app.models  # noqa: F401  (register models on the Base metadata)

    Base.metadata.create_all(bind=engine)
