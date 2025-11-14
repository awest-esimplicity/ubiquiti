"""Audit event repository abstractions and helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Protocol

from sqlalchemy.orm import Session, sessionmaker

from .database import get_engine, get_session_factory, is_database_configured
from .db_models import EventModel


@dataclass(frozen=True)
class Event:
    """Represents a recorded audit event."""

    id: int | None
    timestamp: datetime
    action: str
    actor: str | None
    subject_type: str
    subject_id: str | None
    reason: str | None
    metadata: dict[str, Any]


class EventRepository(Protocol):
    """Storage abstraction for audit events."""

    def record(self, event: Event) -> Event:
        ...

    def list_recent(self, limit: int = 100) -> list[Event]:
        ...


class InMemoryEventRepository(EventRepository):
    """Simple in-memory event store used when no database is configured."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._lock = Lock()
        self._counter = 0

    def record(self, event: Event) -> Event:
        with self._lock:
            self._counter += 1
            stored = replace(event, id=self._counter)
            self._events.append(stored)
            return stored

    def list_recent(self, limit: int = 100) -> list[Event]:
        with self._lock:
            return list(reversed(self._events[-limit:]))


class SQLEventRepository(EventRepository):
    """SQLAlchemy-backed event repository."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, event: Event) -> Event:
        metadata_json = json.dumps(event.metadata) if event.metadata else None
        model = EventModel(
            timestamp=event.timestamp.isoformat(),
            action=event.action,
            actor=event.actor,
            subject_type=event.subject_type,
            subject_id=event.subject_id,
            reason=event.reason,
            metadata_json=metadata_json,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            session.refresh(model)
            return Event(
                id=model.id,
                timestamp=datetime.fromisoformat(model.timestamp),
                action=model.action,
                actor=model.actor,
                subject_type=model.subject_type,
                subject_id=model.subject_id,
                reason=model.reason,
                metadata=json.loads(model.metadata_json or "{}"),
            )

    def list_recent(self, limit: int = 100) -> list[Event]:
        with self._session_factory() as session:
            rows = (
                session.query(EventModel)
                .order_by(EventModel.id.desc())
                .limit(limit)
                .all()
            )
        events = [
            Event(
                id=row.id,
                timestamp=datetime.fromisoformat(row.timestamp),
                action=row.action,
                actor=row.actor,
                subject_type=row.subject_type,
                subject_id=row.subject_id,
                reason=row.reason,
                metadata=json.loads(row.metadata_json or "{}"),
            )
            for row in rows
        ]
        return events


_DEFAULT_EVENT_REPOSITORY = InMemoryEventRepository()
_SQL_EVENT_REPOSITORY: SQLEventRepository | None = None


def _get_sql_event_repository() -> SQLEventRepository:
    global _SQL_EVENT_REPOSITORY
    if _SQL_EVENT_REPOSITORY is None:
        session_factory = get_session_factory()
        _SQL_EVENT_REPOSITORY = SQLEventRepository(session_factory)
    return _SQL_EVENT_REPOSITORY


def get_event_repository() -> EventRepository:
    """Return the configured event repository."""
    if is_database_configured() and get_engine() is not None:
        try:
            return _get_sql_event_repository()
        except RuntimeError:
            return _DEFAULT_EVENT_REPOSITORY
    return _DEFAULT_EVENT_REPOSITORY


def record_event(
    *,
    action: str,
    subject_type: str,
    subject_id: str | None = None,
    actor: str | None = None,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> Event:
    """Persist an audit event."""
    event = Event(
        id=None,
        timestamp=(timestamp or datetime.now(tz=UTC)).astimezone(),
        action=action,
        actor=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        reason=reason,
        metadata=metadata or {},
    )
    return get_event_repository().record(event)


def list_recent_events(limit: int = 100) -> list[Event]:
    """Return the most recent audit events."""
    return get_event_repository().list_recent(limit)


__all__ = [
    "Event",
    "EventRepository",
    "InMemoryEventRepository",
    "SQLEventRepository",
    "record_event",
    "list_recent_events",
    "get_event_repository",
]
