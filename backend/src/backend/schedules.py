"""Repositories and helpers for managing device lock schedules."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from functools import lru_cache
from typing import Iterable, Literal, Protocol

from sqlalchemy import select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from .database import get_engine, get_session_factory, is_database_configured
from .db_models import ScheduleMetadataModel, ScheduleModel
from .defaults import DEFAULT_SCHEDULE_CONFIG
from .schemas import (
    DeviceSchedule,
    ScheduleConfig,
    ScheduleCreateRequest,
    ScheduleException,
    ScheduleMetadata,
    ScheduleRecurrence,
    ScheduleTarget,
    ScheduleUpdateRequest,
    ScheduleWindow,
)

# Utility ---------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _schedule_to_model(schedule: DeviceSchedule) -> ScheduleModel:
    return ScheduleModel(
        id=schedule.id,
        scope=schedule.scope,
        owner_key=schedule.owner_key,
        label=schedule.label,
        description=schedule.description,
        targets_json=json.dumps(
            schedule.targets.model_dump(mode="json", by_alias=True)
        ),
        action=schedule.action,
        end_action=schedule.end_action,
        window_start=schedule.window.start.isoformat(),
        window_end=schedule.window.end.isoformat(),
        recurrence_json=json.dumps(
            schedule.recurrence.model_dump(mode="json", by_alias=True)
        ),
        exceptions_json=json.dumps(
            [
                exception.model_dump(mode="json", by_alias=True)
                for exception in schedule.exceptions
            ]
        ),
        enabled=schedule.enabled,
        created_at=schedule.created_at.isoformat(),
        updated_at=schedule.updated_at.isoformat(),
    )


def _model_to_schedule(model: ScheduleModel) -> DeviceSchedule:
    return DeviceSchedule(
        id=model.id,
        scope=model.scope,
        owner_key=model.owner_key,
        label=model.label,
        description=model.description,
        targets=ScheduleTarget.model_validate_json(model.targets_json),
        action=model.action,
        end_action=model.end_action,
        window=ScheduleWindow(
            start=datetime.fromisoformat(model.window_start),
            end=datetime.fromisoformat(model.window_end),
        ),
        recurrence=ScheduleRecurrence.model_validate_json(model.recurrence_json),
        exceptions=[
            ScheduleException.model_validate(exception)
            for exception in json.loads(model.exceptions_json or "[]")
        ],
        enabled=bool(model.enabled),
        created_at=datetime.fromisoformat(model.created_at),
        updated_at=datetime.fromisoformat(model.updated_at),
    )


def _clone_for_owner(schedule: DeviceSchedule, owner_key: str) -> DeviceSchedule:
    cloned = DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))
    cloned.id = str(uuid.uuid4())
    cloned.scope = "owner"
    cloned.owner_key = owner_key.lower()
    cloned.enabled = True
    timestamp = _now()
    cloned.created_at = timestamp
    cloned.updated_at = timestamp
    return cloned


def _metadata_to_model(metadata: ScheduleMetadata) -> ScheduleMetadataModel:
    return ScheduleMetadataModel(
        id=1,
        timezone=metadata.timezone,
        generated_at=metadata.generated_at.isoformat(),
    )


def _model_to_metadata(model: ScheduleMetadataModel) -> ScheduleMetadata:
    return ScheduleMetadata(
        timezone=model.timezone,
        generated_at=datetime.fromisoformat(model.generated_at),
    )


def _apply_update(schedule: DeviceSchedule, update: ScheduleUpdateRequest) -> DeviceSchedule:
    data = update.model_dump(exclude_unset=True, by_alias=True)
    if "scope" in data:
        schedule.scope = data["scope"]
    if "ownerKey" in data:
        schedule.owner_key = data["ownerKey"]
    if "label" in data:
        schedule.label = data["label"]
    if "description" in data:
        schedule.description = data["description"]
    if "targets" in data:
        schedule.targets = ScheduleTarget.model_validate(data["targets"])
    if "action" in data:
        schedule.action = data["action"]
    if "endAction" in data:
        schedule.end_action = data["endAction"]
    if "window" in data:
        schedule.window = ScheduleWindow.model_validate(data["window"])
    if "recurrence" in data:
        schedule.recurrence = ScheduleRecurrence.model_validate(data["recurrence"])
    if "exceptions" in data:
        schedule.exceptions = [
            ScheduleException.model_validate(exception)
            for exception in data["exceptions"]
        ]
    if "enabled" in data:
        schedule.enabled = data["enabled"]
    return schedule


# Repository protocol ---------------------------------------------------------


class ScheduleRepository(Protocol):
    """Abstraction used by routers/services to manage schedules."""

    def list(
        self,
        *,
        scope: str | None = None,
        owner: str | None = None,
        enabled: bool | None = None,
    ) -> list[DeviceSchedule]:
        ...

    def get(self, schedule_id: str) -> DeviceSchedule | None:
        ...

    def create(self, payload: ScheduleCreateRequest) -> DeviceSchedule:
        ...

    def update(
        self, schedule_id: str, payload: ScheduleUpdateRequest
    ) -> DeviceSchedule | None:
        ...

    def delete(self, schedule_id: str) -> bool:
        ...

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        ...

    def list_for_owner(self, owner_key: str) -> tuple[list[DeviceSchedule], list[DeviceSchedule]]:
        ...

    def get_metadata(self) -> ScheduleMetadata:
        ...

    def sync_from_config(self, config: ScheduleConfig, *, replace: bool) -> None:
        ...

    def clone(self, schedule_id: str, target_owner: str) -> DeviceSchedule | None:
        ...

    def copy_owner_schedules(
        self,
        source_owner: str,
        target_owner: str,
        *,
        mode: Literal["merge", "replace"],
    ) -> tuple[list[DeviceSchedule], int]:
        ...


# In-memory repository --------------------------------------------------------


class InMemoryScheduleRepository(ScheduleRepository):
    def __init__(self) -> None:
        self._config = ScheduleConfig.model_validate(DEFAULT_SCHEDULE_CONFIG)

    def _clone_schedule(self, schedule: DeviceSchedule) -> DeviceSchedule:
        return DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))

    def list(
        self,
        *,
        scope: str | None = None,
        owner: str | None = None,
        enabled: bool | None = None,
    ) -> list[DeviceSchedule]:
        schedules = [
            self._clone_schedule(schedule) for schedule in self._config.schedules
        ]
        if scope:
            schedules = [s for s in schedules if s.scope == scope]
        if owner:
            schedules = [s for s in schedules if s.owner_key == owner]
        if enabled is not None:
            schedules = [s for s in schedules if s.enabled is enabled]
        return schedules

    def get(self, schedule_id: str) -> DeviceSchedule | None:
        for schedule in self._config.schedules:
            if schedule.id == schedule_id:
                return self._clone_schedule(schedule)
        return None

    def create(self, payload: ScheduleCreateRequest) -> DeviceSchedule:
        schedule = DeviceSchedule(
            id=str(uuid.uuid4()),
            scope=payload.scope,
            owner_key=payload.owner_key,
            label=payload.label,
            description=payload.description,
            targets=payload.targets,
            action=payload.action,
            end_action=payload.end_action,
            window=payload.window,
            recurrence=payload.recurrence,
            exceptions=list(payload.exceptions or []),
            enabled=payload.enabled if payload.enabled is not None else True,
            created_at=_now(),
            updated_at=_now(),
        )
        self._config.schedules.append(schedule)
        self._config.metadata.generated_at = _now()
        return self._clone_schedule(schedule)

    def update(
        self, schedule_id: str, payload: ScheduleUpdateRequest
    ) -> DeviceSchedule | None:
        for index, schedule in enumerate(self._config.schedules):
            if schedule.id == schedule_id:
                updated = _apply_update(self._clone_schedule(schedule), payload)
                updated.updated_at = _now()
                self._config.schedules[index] = updated
                self._config.metadata.generated_at = _now()
                return self._clone_schedule(updated)
        return None

    def delete(self, schedule_id: str) -> bool:
        for index, schedule in enumerate(self._config.schedules):
            if schedule.id == schedule_id:
                self._config.schedules.pop(index)
                self._config.metadata.generated_at = _now()
                return True
        return False

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        for schedule in self._config.schedules:
            if schedule.id == schedule_id:
                schedule.enabled = enabled
                schedule.updated_at = _now()
                self._config.metadata.generated_at = _now()
                return self._clone_schedule(schedule)
        return None

    def list_for_owner(
        self, owner_key: str
    ) -> tuple[list[DeviceSchedule], list[DeviceSchedule]]:
        owner_schedules = [
            self._clone_schedule(schedule)
            for schedule in self._config.schedules
            if schedule.scope == "owner" and schedule.owner_key == owner_key
        ]
        global_schedules = [
            self._clone_schedule(schedule)
            for schedule in self._config.schedules
            if schedule.scope == "global"
        ]
        return owner_schedules, global_schedules

    def get_metadata(self) -> ScheduleMetadata:
        return ScheduleMetadata.model_validate(
            self._config.metadata.model_dump(by_alias=True)
        )

    def sync_from_config(self, config: ScheduleConfig, *, replace: bool) -> None:
        if replace:
            self._config = ScheduleConfig.model_validate(
                config.model_dump(by_alias=True)
            )
        else:
            existing_ids = {schedule.id for schedule in self._config.schedules}
            for schedule in config.schedules:
                if schedule.id in existing_ids:
                    continue
                self._config.schedules.append(
                    DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))
                )
        self._config.metadata = ScheduleMetadata.model_validate(
            config.metadata.model_dump(by_alias=True)
        )

    def clone(self, schedule_id: str, target_owner: str) -> DeviceSchedule | None:
        target_owner = target_owner.lower()
        for schedule in self._config.schedules:
            if schedule.id == schedule_id:
                new_schedule = _clone_for_owner(schedule, target_owner)
                self._config.schedules.append(new_schedule)
                self._config.metadata.generated_at = _now()
                return self._clone_schedule(new_schedule)
        return None

    def copy_owner_schedules(
        self,
        source_owner: str,
        target_owner: str,
        *,
        mode: Literal["merge", "replace"],
    ) -> tuple[list[DeviceSchedule], int]:
        source_owner = source_owner.lower()
        target_owner = target_owner.lower()
        source_schedules = [
            schedule
            for schedule in self._config.schedules
            if schedule.scope == "owner" and schedule.owner_key == source_owner
        ]
        if not source_schedules:
            return [], 0

        replaced_count = 0
        if mode == "replace":
            remaining: list[DeviceSchedule] = []
            for schedule in self._config.schedules:
                if schedule.scope == "owner" and schedule.owner_key == target_owner:
                    replaced_count += 1
                    continue
                remaining.append(schedule)
            self._config.schedules = remaining

        created: list[DeviceSchedule] = []
        for schedule in source_schedules:
            clone = _clone_for_owner(schedule, target_owner)
            self._config.schedules.append(clone)
            created.append(self._clone_schedule(clone))

        if created or replaced_count:
            self._config.metadata.generated_at = _now()

        return created, replaced_count


# SQLAlchemy repository -------------------------------------------------------


class SqlScheduleRepository(ScheduleRepository):
    def __init__(self) -> None:
        self._session_factory = get_session_factory()

    def _session(self) -> Session:
        return self._session_factory()

    def _get_metadata(self, session: Session) -> ScheduleMetadata:
        metadata_row = session.execute(select(ScheduleMetadataModel)).scalar_one_or_none()
        if metadata_row is None:
            metadata = ScheduleMetadata.model_validate(DEFAULT_SCHEDULE_CONFIG["metadata"])
            session.merge(_metadata_to_model(metadata))
            session.commit()
            return metadata
        return _model_to_metadata(metadata_row)

    def _set_generated_at(self, session: Session) -> None:
        metadata = self._get_metadata(session)
        metadata.generated_at = _now()
        session.merge(_metadata_to_model(metadata))

    def list(
        self,
        *,
        scope: str | None = None,
        owner: str | None = None,
        enabled: bool | None = None,
    ) -> list[DeviceSchedule]:
        with self._session() as session:
            stmt = select(ScheduleModel)
            if scope:
                stmt = stmt.where(ScheduleModel.scope == scope)
            if owner:
                stmt = stmt.where(ScheduleModel.owner_key == owner)
            if enabled is not None:
                stmt = stmt.where(ScheduleModel.enabled == enabled)
            rows = session.execute(stmt).scalars().all()
            return [_model_to_schedule(row) for row in rows]

    def get(self, schedule_id: str) -> DeviceSchedule | None:
        with self._session() as session:
            row = session.get(ScheduleModel, schedule_id)
            return _model_to_schedule(row) if row else None

    def create(self, payload: ScheduleCreateRequest) -> DeviceSchedule:
        schedule = DeviceSchedule(
            id=str(uuid.uuid4()),
            scope=payload.scope,
            owner_key=payload.owner_key,
            label=payload.label,
            description=payload.description,
            targets=payload.targets,
            action=payload.action,
            end_action=payload.end_action,
            window=payload.window,
            recurrence=payload.recurrence,
            exceptions=list(payload.exceptions or []),
            enabled=payload.enabled if payload.enabled is not None else True,
            created_at=_now(),
            updated_at=_now(),
        )
        model = _schedule_to_model(schedule)
        with self._session() as session:
            session.merge(model)
            self._set_generated_at(session)
            session.commit()
        return schedule

    def update(
        self, schedule_id: str, payload: ScheduleUpdateRequest
    ) -> DeviceSchedule | None:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return None
            schedule = _model_to_schedule(existing)
            schedule = _apply_update(schedule, payload)
            schedule.updated_at = _now()
            session.merge(_schedule_to_model(schedule))
            self._set_generated_at(session)
            session.commit()
            return schedule

    def delete(self, schedule_id: str) -> bool:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return False
            session.delete(existing)
            self._set_generated_at(session)
            session.commit()
            return True

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return None
            schedule = _model_to_schedule(existing)
            schedule.enabled = enabled
            schedule.updated_at = _now()
            session.merge(_schedule_to_model(schedule))
            self._set_generated_at(session)
            session.commit()
            return schedule

    def list_for_owner(
        self, owner_key: str
    ) -> tuple[list[DeviceSchedule], list[DeviceSchedule]]:
        with self._session() as session:
            owner_rows = (
                session.execute(
                    select(ScheduleModel).where(
                        ScheduleModel.scope == "owner",
                        ScheduleModel.owner_key == owner_key,
                    )
                )
                .scalars()
                .all()
            )
            global_rows = (
                session.execute(
                    select(ScheduleModel).where(ScheduleModel.scope == "global")
                )
                .scalars()
                .all()
            )
            return (
                [_model_to_schedule(row) for row in owner_rows],
                [_model_to_schedule(row) for row in global_rows],
            )

    def get_metadata(self) -> ScheduleMetadata:
        with self._session() as session:
            return self._get_metadata(session)

    def sync_from_config(self, config: ScheduleConfig, *, replace: bool) -> None:
        with self._session() as session:
            if replace:
                session.query(ScheduleModel).delete()
            existing_ids = {
                row.id
                for row in session.execute(select(ScheduleModel.id)).scalars().all()
            }
            for schedule in config.schedules:
                if not replace and schedule.id in existing_ids:
                    continue
                session.merge(_schedule_to_model(schedule))
            session.merge(_metadata_to_model(config.metadata))
            session.commit()

    def clone(self, schedule_id: str, target_owner: str) -> DeviceSchedule | None:
        target_owner = target_owner.lower()
        with self._session() as session:
            source = session.get(ScheduleModel, schedule_id)
            if source is None:
                return None
            schedule = _model_to_schedule(source)
            clone = _clone_for_owner(schedule, target_owner)
            session.merge(_schedule_to_model(clone))
            self._set_generated_at(session)
            session.commit()
            return clone

    def copy_owner_schedules(
        self,
        source_owner: str,
        target_owner: str,
        *,
        mode: Literal["merge", "replace"],
    ) -> tuple[list[DeviceSchedule], int]:
        source_owner = source_owner.lower()
        target_owner = target_owner.lower()
        with self._session() as session:
            source_rows = (
                session.execute(
                    select(ScheduleModel).where(
                        ScheduleModel.scope == "owner",
                        ScheduleModel.owner_key == source_owner,
                    )
                )
                .scalars()
                .all()
            )
            if not source_rows:
                return [], 0

            replaced_count = 0
            if mode == "replace":
                target_rows = (
                    session.execute(
                        select(ScheduleModel).where(
                            ScheduleModel.scope == "owner",
                            ScheduleModel.owner_key == target_owner,
                        )
                    )
                    .scalars()
                    .all()
                )
                replaced_count = len(target_rows)
                for row in target_rows:
                    session.delete(row)

            created: list[DeviceSchedule] = []
            for row in source_rows:
                schedule = _model_to_schedule(row)
                clone = _clone_for_owner(schedule, target_owner)
                session.merge(_schedule_to_model(clone))
                created.append(clone)

            self._set_generated_at(session)
            session.commit()
            return created, replaced_count


# Repository factory ----------------------------------------------------------


@lru_cache
def _default_schedule_repository() -> InMemoryScheduleRepository:
    return InMemoryScheduleRepository()


@lru_cache
def _sql_schedule_repository() -> SqlScheduleRepository:
    return SqlScheduleRepository()


def get_schedule_repository() -> ScheduleRepository:
    """Return the configured schedule repository."""
    if is_database_configured() and get_engine() is not None:
        return _sql_schedule_repository()
    return _default_schedule_repository()
