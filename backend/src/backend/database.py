"""Database utilities for configuring optional SQLAlchemy sessions."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from threading import Lock

from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


class DatabaseSettings(BaseModel):
    """Configuration values for the database connection."""

    url: str | None = Field(default=None)
    echo: bool = Field(default=False)
    mode: str = Field(default="memory")

    @classmethod
    def load(cls) -> DatabaseSettings:
        return cls(
            url=os.getenv("UBIQUITI_DB_URL"),
            echo=os.getenv("UBIQUITI_DB_ECHO", "false").lower()
            in {"1", "true", "yes", "on"},
            mode=os.getenv("UBIQUITI_DB_MODE", "memory").lower(),
        )


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Return cached database settings."""
    return DatabaseSettings.load()


_engine_lock = Lock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def is_database_configured() -> bool:
    """Return True when the environment selects the database repository."""
    settings = get_database_settings()
    if settings.mode == "memory":
        return False
    if not settings.url:
        return False
    return settings.mode in {"auto", "database"}


def _ensure_sqlite_directory(url: str) -> None:
    if url.startswith("sqlite:///"):
        db_path = Path(url.replace("sqlite:///", "", 1))
        db_path.parent.mkdir(parents=True, exist_ok=True)


def _prepare_schema(engine: Engine) -> None:
    """Ensure tables exist and apply simple migrations for legacy databases."""
    from .db_models import Base, ScheduleGroupModel  # Local import to avoid circular deps

    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    if "schedules" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("schedules")}
        if "group_id" not in columns:
            with engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE schedules ADD COLUMN group_id VARCHAR(64)")
                )

    if "schedule_groups" not in inspector.get_table_names():
        ScheduleGroupModel.__table__.create(bind=engine, checkfirst=True)


def get_engine() -> Engine | None:
    """Return the configured SQLAlchemy engine, if any."""
    global _engine

    if not is_database_configured():
        return None

    settings = get_database_settings()
    if settings.url is None:
        return None

    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _ensure_sqlite_directory(settings.url)
                _engine = create_engine(
                    settings.url,
                    echo=settings.echo,
                    future=True,
                )
                _prepare_schema(_engine)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return a session factory for creating SQLAlchemy sessions."""
    global _session_factory
    engine = get_engine()
    if engine is None:
        raise RuntimeError(
            "Database is not configured. Set UBIQUITI_DB_URL and "
            "UBIQUITI_DB_MODE=database (or auto) to enable SQL storage."
        )

    if _session_factory is None:
        with _engine_lock:
            if _session_factory is None:
                _session_factory = sessionmaker(
                    bind=engine,
                    autoflush=False,
                    autocommit=False,
                    future=True,
                )
    return _session_factory


def create_session() -> Session:
    """Create a new SQLAlchemy session."""
    return get_session_factory()()
