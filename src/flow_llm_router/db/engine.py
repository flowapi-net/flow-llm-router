"""SQLite engine initialization and session management."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from sqlmodel import Session, SQLModel, create_engine

_engines: dict[str, Any] = {}


def get_engine(db_path: str = "./data.db"):
    """Return (and cache) the SQLAlchemy engine for *db_path*.

    Each unique path gets its own engine so tests using in-memory or
    temporary databases don't share state with the production database.
    """
    resolved = str(Path(db_path).resolve())
    if resolved not in _engines:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _engines[resolved] = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
    return _engines[resolved]


def init_db(db_path: str = "./data.db"):
    """Create all tables if they don't exist."""
    engine = get_engine(db_path)
    SQLModel.metadata.create_all(engine)
    _migrate_existing_schema(engine)


def _migrate_existing_schema(engine: Any) -> None:
    """Apply small additive migrations for existing SQLite databases."""
    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.exec_driver_sql("PRAGMA table_info(provider_models)").fetchall()
        }
        if "enabled" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE provider_models ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT 0"
            )


def get_session(db_path: str = "./data.db") -> Session:
    """Get a new database session."""
    return Session(get_engine(db_path))


@asynccontextmanager
async def get_async_session(db_path: str = "./data.db") -> AsyncGenerator[Session, None]:
    """Async context manager for database sessions."""
    session = Session(get_engine(db_path))
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
