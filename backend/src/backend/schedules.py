"""Repositories and helpers for managing device lock schedules."""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from collections import defaultdict
from functools import lru_cache
from typing import Iterable, Literal, Protocol

from sqlalchemy import delete, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session

from .database import get_engine, get_session_factory, is_database_configured
from .db_models import (
    ScheduleGroupMembershipModel,
    ScheduleGroupModel,
    ScheduleMetadataModel,
    ScheduleModel,
)
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
        group_id=schedule.group_ids[0] if schedule.group_ids else None,
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


def _model_to_schedule(model: ScheduleModel, group_ids: list[str] | None = None) -> DeviceSchedule:
    resolved_group_ids: list[str] = []
    if group_ids is not None:
        resolved_group_ids = group_ids
    elif model.group_id:
        resolved_group_ids = [model.group_id]
    return DeviceSchedule(
        id=model.id,
        scope=model.scope,
        owner_key=model.owner_key,
        group_ids=resolved_group_ids,
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
        group_id=model.group_id,
    )


def _clone_for_owner(schedule: DeviceSchedule, owner_key: str) -> DeviceSchedule:
    cloned = DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))
    cloned.id = str(uuid.uuid4())
    cloned.scope = "owner"
    cloned.owner_key = owner_key.lower()
    cloned.group_ids = []
    cloned.enabled = True
    timestamp = _now()
    cloned.created_at = timestamp
    cloned.updated_at = timestamp
    return cloned


@dataclass
class ScheduleGroupRecord:
    id: str
    name: str
    owner_key: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


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

    def list_groups(
        self, owner_key: str | None = None
    ) -> list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]]:
        ...

    def get_group(self, group_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        ...

    def create_group(
        self,
        name: str,
        *,
        owner_key: str | None,
        description: str | None,
        schedule_ids: list[str],
        is_active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]]:
        ...

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        schedule_ids: list[str] | None = None,
        is_active: bool | None = None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        ...

    def delete_group(self, group_id: str) -> bool:
        ...

    def set_group_active(
        self,
        group_id: str,
        active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        ...

    def set_group_active(self, group_id: str, schedule_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        ...


# In-memory repository --------------------------------------------------------


class InMemoryScheduleRepository(ScheduleRepository):
    def __init__(self) -> None:
        self._config = ScheduleConfig.model_validate(DEFAULT_SCHEDULE_CONFIG)
        self._groups: dict[str, ScheduleGroupRecord] = {}

    def _clone_schedule(self, schedule: DeviceSchedule) -> DeviceSchedule:
        return DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))

    def _find_schedule_index(self, schedule_id: str) -> int | None:
        for index, schedule in enumerate(self._config.schedules):
            if schedule.id == schedule_id:
                return index
        return None

    def _find_schedule(self, schedule_id: str) -> DeviceSchedule | None:
        index = self._find_schedule_index(schedule_id)
        if index is None:
            return None
        return self._config.schedules[index]

    def _set_schedule(self, schedule: DeviceSchedule) -> None:
        index = self._find_schedule_index(schedule.id)
        if index is None:
            self._config.schedules.append(schedule)
        else:
            self._config.schedules[index] = schedule

    def _group_schedules(self, group_id: str) -> list[DeviceSchedule]:
        return [
            schedule
            for schedule in self._config.schedules
            if schedule.group_id == group_id
        ]

    def _set_group_active(self, group: ScheduleGroupRecord, schedule_id: str | None) -> None:
        for schedule in self._config.schedules:
            if schedule.group_id != group.id:
                continue
            schedule.enabled = schedule.id == schedule_id
            schedule.updated_at = _now()
        group.active_schedule_id = schedule_id
        group.updated_at = _now()
        if schedule_id:
            self._deactivate_other_groups(group)

    def _deactivate_other_groups(self, active_group: ScheduleGroupRecord) -> None:
        for group in self._groups.values():
            if group.id == active_group.id:
                continue
            same_owner = (
                (active_group.owner_key is None and group.owner_key is None)
                or (active_group.owner_key is not None and group.owner_key == active_group.owner_key)
            )
            if not same_owner:
                continue
            if group.active_schedule_id:
                self._set_group_active(group, None)

    def _remove_schedule_from_group(self, schedule: DeviceSchedule) -> None:
        if not schedule.group_id:
            return
        group = self._groups.get(schedule.group_id)
        schedule.group_id = None
        schedule.enabled = schedule.enabled  # no change
        schedule.updated_at = _now()
        if group:
            if group.active_schedule_id == schedule.id:
                self._set_group_active(group, None)

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
            group_id=payload.group_id,
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
        if schedule.group_id:
            group = self._groups.get(schedule.group_id)
            if group is None:
                raise ValueError(f"Schedule group {schedule.group_id} not found.")
            if group.owner_key and schedule.owner_key and group.owner_key != schedule.owner_key:
                raise ValueError("Schedule owner does not match group owner.")
            if group.active_schedule_id is None:
                self._set_group_active(group, schedule.id)
                schedule.enabled = True
            else:
                schedule.enabled = group.active_schedule_id == schedule.id
                if schedule.enabled:
                    self._set_group_active(group, schedule.id)
                else:
                    schedule.updated_at = _now()
        self._config.metadata.generated_at = _now()
        return self._clone_schedule(schedule)

    def update(
        self, schedule_id: str, payload: ScheduleUpdateRequest
    ) -> DeviceSchedule | None:
        for index, schedule in enumerate(self._config.schedules):
            if schedule.id == schedule_id:
                updated = _apply_update(self._clone_schedule(schedule), payload)
                updated.updated_at = _now()
                old_group = schedule.group_id
                new_group = updated.group_id
                if old_group != new_group:
                    # detach from old group
                    if old_group:
                        existing_group = self._groups.get(old_group)
                        if existing_group:
                            if existing_group.active_schedule_id == schedule.id:
                                self._set_group_active(existing_group, None)
                    schedule.group_id = None
                    if new_group:
                        group = self._groups.get(new_group)
                        if group is None:
                            raise ValueError(f"Schedule group {new_group} not found.")
                        if group.owner_key and updated.owner_key and group.owner_key != updated.owner_key:
                            raise ValueError("Schedule owner does not match group owner.")
                        # attach to new group
                        if group.active_schedule_id is None:
                            self._set_group_active(group, updated.id)
                            updated.enabled = True
                        else:
                            updated.enabled = group.active_schedule_id == updated.id
                            if updated.enabled:
                                self._set_group_active(group, updated.id)
                            else:
                                updated.updated_at = _now()
                else:
                    # still in same group; ensure enabled consistency if group exists
                    if updated.group_id:
                        group = self._groups.get(updated.group_id)
                        if group:
                            updated.enabled = group.active_schedule_id == updated.id
                self._config.schedules[index] = updated
                self._config.metadata.generated_at = _now()
                return self._clone_schedule(updated)
        return None

    def delete(self, schedule_id: str) -> bool:
        for index, schedule in enumerate(self._config.schedules):
            if schedule.id == schedule_id:
                group_id = schedule.group_id
                self._config.schedules.pop(index)
                if group_id:
                    group = self._groups.get(group_id)
                    if group:
                        remaining = self._group_schedules(group_id)
                        if group.active_schedule_id == schedule_id:
                            new_active = remaining[0].id if remaining else None
                            self._set_group_active(group, new_active)
                        if not remaining:
                            group.updated_at = _now()
                self._config.metadata.generated_at = _now()
                return True
        return False

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        for schedule in self._config.schedules:
            if schedule.id == schedule_id:
                if schedule.group_id:
                    group = self._groups.get(schedule.group_id)
                    if group:
                        if enabled:
                            self._set_group_active(group, schedule.id)
                        else:
                            if group.active_schedule_id == schedule.id:
                                self._set_group_active(group, None)
                            schedule.enabled = False
                            schedule.updated_at = _now()
                        self._config.metadata.generated_at = _now()
                        return self._clone_schedule(self._find_schedule(schedule_id) or schedule)
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

    def list_groups(
        self, owner_key: str | None = None
    ) -> list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]]:
        groups = []
        for group in self._groups.values():
            if owner_key is None:
                groups.append(group)
            elif group.owner_key == owner_key:
                groups.append(group)
        result: list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]] = []
        for group in groups:
            schedules = [
                self._clone_schedule(schedule)
                for schedule in self._group_schedules(group.id)
            ]
            result.append((group, schedules))
        return result

    def get_group(self, group_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        schedules = [
            self._clone_schedule(schedule)
            for schedule in self._group_schedules(group.id)
        ]
        return group, schedules

    def create_group(
        self,
        name: str,
        *,
        owner_key: str | None,
        description: str | None,
        schedule_ids: list[str],
        active_schedule_id: str | None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]]:
        group_id = str(uuid.uuid4())
        now = _now()
        record = ScheduleGroupRecord(
            id=group_id,
            name=name.strip(),
            owner_key=owner_key.lower() if owner_key else None,
            description=description.strip() if description else None,
            active_schedule_id=None,
            created_at=now,
            updated_at=now,
        )
        self._groups[group_id] = record

        schedules: list[DeviceSchedule] = []
        for schedule_id in schedule_ids:
            schedule = self._find_schedule(schedule_id)
            if schedule is None:
                raise ValueError(f"Schedule {schedule_id} not found.")
            if record.owner_key and schedule.owner_key and schedule.owner_key != record.owner_key:
                raise ValueError("Schedule owner does not match group owner.")
            self._remove_schedule_from_group(schedule)
            schedule.group_id = group_id
            schedule.updated_at = _now()
            schedules.append(schedule)

        if active_schedule_id and active_schedule_id not in schedule_ids:
            raise ValueError("activeScheduleId must be included in scheduleIds.")

        selected_active = active_schedule_id or (schedule_ids[0] if schedule_ids else None)
        self._set_group_active(record, selected_active)
        self._config.metadata.generated_at = _now()
        return record, [self._clone_schedule(s) for s in schedules]

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        schedule_ids: list[str] | None = None,
        active_schedule_id: str | None = None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        if name is not None:
            group.name = name.strip()
        if description is not None:
            group.description = description.strip() or None

        if schedule_ids is not None:
            current_ids = {schedule.id for schedule in self._group_schedules(group_id)}
            desired_ids = set(schedule_ids)

            # remove schedules not in desired set
            for schedule_id in current_ids - desired_ids:
                schedule = self._find_schedule(schedule_id)
                if schedule:
                    self._remove_schedule_from_group(schedule)

            # add new schedules
            for schedule_id in desired_ids:
                schedule = self._find_schedule(schedule_id)
                if schedule is None:
                    raise ValueError(f"Schedule {schedule_id} not found.")
                if schedule.group_id != group_id:
                    if group.owner_key and schedule.owner_key and schedule.owner_key != group.owner_key:
                        raise ValueError("Schedule owner does not match group owner.")
                    self._remove_schedule_from_group(schedule)
                    schedule.group_id = group_id
                    schedule.updated_at = _now()

            if active_schedule_id and active_schedule_id not in desired_ids:
                raise ValueError("activeScheduleId must be included in scheduleIds.")
            group.updated_at = _now()

        if active_schedule_id is not None:
            if active_schedule_id:
                schedule = self._find_schedule(active_schedule_id)
                if schedule is None or schedule.group_id != group_id:
                    raise ValueError("Active schedule must belong to the group.")
                self._set_group_active(group, active_schedule_id)
            else:
                self._set_group_active(group, None)

        self._config.metadata.generated_at = _now()
        schedules = [
            self._clone_schedule(schedule)
            for schedule in self._group_schedules(group_id)
        ]
        return group, schedules

    def delete_group(self, group_id: str) -> bool:
        group = self._groups.pop(group_id, None)
        if group is None:
            return False
        for schedule in self._config.schedules:
            if schedule.group_id == group_id:
                schedule.group_id = None
                schedule.updated_at = _now()
        self._config.metadata.generated_at = _now()
        return True

    def set_group_active(
        self, group_id: str, schedule_id: str
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        schedule = self._find_schedule(schedule_id)
        if schedule is None or schedule.group_id != group_id:
            raise ValueError("Schedule must belong to the group.")
        self._set_group_active(group, schedule_id)
        self._config.metadata.generated_at = _now()
        schedules = [
            self._clone_schedule(schedule)
            for schedule in self._group_schedules(group_id)
        ]
        return group, schedules


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

    def _model_to_group_record(self, model: ScheduleGroupModel) -> ScheduleGroupRecord:
        return ScheduleGroupRecord(
            id=model.id,
            name=model.name,
            owner_key=model.owner_key,
            description=model.description,
            active_schedule_id=model.active_schedule_id,
            created_at=datetime.fromisoformat(model.created_at),
            updated_at=datetime.fromisoformat(model.updated_at),
        )

    def _group_schedules_sql(self, session: Session, group_id: str) -> list[ScheduleModel]:
        return (
            session.execute(
                select(ScheduleModel).where(ScheduleModel.group_id == group_id)
            )
            .scalars()
            .all()
        )

    def _set_group_active_sql(
        self,
        session: Session,
        group_model: ScheduleGroupModel,
        schedule_id: str | None,
    ) -> None:
        now = _now().isoformat()
        for row in self._group_schedules_sql(session, group_model.id):
            row.enabled = row.id == schedule_id
            row.updated_at = now
        group_model.active_schedule_id = schedule_id
        group_model.updated_at = now
        if schedule_id:
            self._deactivate_other_groups_sql(session, group_model)

    def _deactivate_other_groups_sql(
        self,
        session: Session,
        active_group: ScheduleGroupModel,
    ) -> None:
        owner_key = active_group.owner_key
        stmt = select(ScheduleGroupModel).where(ScheduleGroupModel.id != active_group.id)
        if owner_key is None:
            stmt = stmt.where(ScheduleGroupModel.owner_key.is_(None))
        else:
            stmt = stmt.where(ScheduleGroupModel.owner_key == owner_key)
        other_groups = session.execute(stmt).scalars().all()
        for group in other_groups:
            if group.active_schedule_id:
                self._set_group_active_sql(session, group, None)

    def _remove_schedule_from_group_sql(
        self,
        session: Session,
        schedule_model: ScheduleModel,
    ) -> None:
        if not schedule_model.group_id:
            return
        group_model = session.get(ScheduleGroupModel, schedule_model.group_id)
        schedule_model.group_id = None
        schedule_model.updated_at = _now().isoformat()
        if group_model and group_model.active_schedule_id == schedule_model.id:
            self._set_group_active_sql(session, group_model, None)

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
            group_id=payload.group_id,
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
            if schedule.group_id:
                group_model = session.get(ScheduleGroupModel, schedule.group_id)
                if group_model is None:
                    raise ValueError(f"Schedule group {schedule.group_id} not found.")
                if group_model.owner_key and schedule.owner_key and group_model.owner_key != schedule.owner_key:
                    raise ValueError("Schedule owner does not match group owner.")
                persisted = session.get(ScheduleModel, schedule.id)
                assert persisted is not None
                if group_model.active_schedule_id is None:
                    self._set_group_active_sql(session, group_model, persisted.id)
                else:
                    self._set_group_active_sql(session, group_model, group_model.active_schedule_id)
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
            updated = _apply_update(schedule, payload)
            updated.updated_at = _now()

            old_group = existing.group_id
            new_group = updated.group_id

            if old_group != new_group:
                if old_group:
                    self._remove_schedule_from_group_sql(session, existing)
                if new_group:
                    group_model = session.get(ScheduleGroupModel, new_group)
                    if group_model is None:
                        raise ValueError(f"Schedule group {new_group} not found.")
                    if group_model.owner_key and updated.owner_key and group_model.owner_key != updated.owner_key:
                        raise ValueError("Schedule owner does not match group owner.")
                    existing.group_id = new_group
            existing.scope = updated.scope
            existing.owner_key = updated.owner_key
            existing.label = updated.label
            existing.description = updated.description
            existing.targets_json = json.dumps(
                updated.targets.model_dump(mode="json", by_alias=True)
            )
            existing.action = updated.action
            existing.end_action = updated.end_action
            existing.window_start = updated.window.start.isoformat()
            existing.window_end = updated.window.end.isoformat()
            existing.recurrence_json = json.dumps(
                updated.recurrence.model_dump(mode="json", by_alias=True)
            )
            existing.exceptions_json = json.dumps(
                [exception.model_dump(mode="json", by_alias=True) for exception in updated.exceptions]
            )
            existing.updated_at = updated.updated_at.isoformat()

            if existing.group_id:
                group_model = session.get(ScheduleGroupModel, existing.group_id)
                if group_model:
                    if group_model.active_schedule_id == existing.id or group_model.active_schedule_id is None:
                        self._set_group_active_sql(
                            session,
                            group_model,
                            group_model.active_schedule_id or existing.id,
                        )
                    else:
                        self._set_group_active_sql(session, group_model, group_model.active_schedule_id)
            else:
                existing.enabled = updated.enabled
            self._set_generated_at(session)
            session.commit()
            refreshed = session.get(ScheduleModel, schedule_id)
            assert refreshed is not None
            return _model_to_schedule(refreshed)

    def delete(self, schedule_id: str) -> bool:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return False
            group_id = existing.group_id
            session.delete(existing)
            session.flush()
            if group_id:
                group_model = session.get(ScheduleGroupModel, group_id)
                if group_model:
                    remaining = self._group_schedules_sql(session, group_id)
                    new_active = (
                        remaining[0].id if remaining else None
                    )
                    if group_model.active_schedule_id == schedule_id:
                        self._set_group_active_sql(session, group_model, new_active)
                    else:
                        group_model.updated_at = _now().isoformat()
            self._set_generated_at(session)
            session.commit()
            return True

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return None
            if existing.group_id:
                group_model = session.get(ScheduleGroupModel, existing.group_id)
                if group_model:
                    if enabled:
                        self._set_group_active_sql(session, group_model, existing.id)
                    else:
                        if group_model.active_schedule_id == existing.id:
                            self._set_group_active_sql(session, group_model, None)
                        else:
                            existing.enabled = False
                            existing.updated_at = _now().isoformat()
                else:
                    existing.enabled = enabled
                    existing.updated_at = _now().isoformat()
            else:
                existing.enabled = enabled
                existing.updated_at = _now().isoformat()
            self._set_generated_at(session)
            session.commit()
            refreshed = session.get(ScheduleModel, schedule_id)
            assert refreshed is not None
            return _model_to_schedule(refreshed)

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

    def list_groups(
        self, owner_key: str | None = None
    ) -> list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]]:
        with self._session() as session:
            stmt = select(ScheduleGroupModel)
            if owner_key is None:
                stmt = stmt.where(ScheduleGroupModel.owner_key.is_(None))
            else:
                stmt = stmt.where(ScheduleGroupModel.owner_key == owner_key)
            rows = session.execute(stmt).scalars().all()
            result: list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]] = []
            for row in rows:
                group = self._model_to_group_record(row)
                schedules = [
                    _model_to_schedule(schedule)
                    for schedule in self._group_schedules_sql(session, row.id)
                ]
                result.append((group, schedules))
            return result

    def get_group(self, group_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        with self._session() as session:
            model = session.get(ScheduleGroupModel, group_id)
            if model is None:
                return None
            group = self._model_to_group_record(model)
            schedules = [
                _model_to_schedule(schedule)
                for schedule in self._group_schedules_sql(session, group_id)
            ]
            return group, schedules

    def create_group(
        self,
        name: str,
        *,
        owner_key: str | None,
        description: str | None,
        schedule_ids: list[str],
        active_schedule_id: str | None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]]:
        with self._session() as session:
            now = _now().isoformat()
            group_id = str(uuid.uuid4())
            record = ScheduleGroupModel(
                id=group_id,
                owner_key=owner_key.lower() if owner_key else None,
                name=name.strip(),
                description=description.strip() if description else None,
                active_schedule_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.flush()

            for schedule_id in schedule_ids:
                schedule = session.get(ScheduleModel, schedule_id)
                if schedule is None:
                    raise ValueError(f"Schedule {schedule_id} not found.")
                if record.owner_key and schedule.owner_key and schedule.owner_key != record.owner_key:
                    raise ValueError("Schedule owner does not match group owner.")
                self._remove_schedule_from_group_sql(session, schedule)
                schedule.group_id = record.id

            if active_schedule_id and active_schedule_id not in schedule_ids:
                raise ValueError("activeScheduleId must be included in scheduleIds.")

            selected_active = active_schedule_id or (schedule_ids[0] if schedule_ids else None)
            self._set_group_active_sql(session, record, selected_active)
            self._set_generated_at(session)
            session.commit()

            refreshed = session.get(ScheduleGroupModel, group_id)
            assert refreshed is not None
            group = self._model_to_group_record(refreshed)
            schedules = [
                _model_to_schedule(schedule)
                for schedule in self._group_schedules_sql(session, group_id)
            ]
            return group, schedules

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        schedule_ids: list[str] | None = None,
        active_schedule_id: str | None = None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        with self._session() as session:
            group_model = session.get(ScheduleGroupModel, group_id)
            if group_model is None:
                return None
            if name is not None:
                group_model.name = name.strip()
            if description is not None:
                group_model.description = description.strip() or None

            if schedule_ids is not None:
                current_ids = {row.id for row in self._group_schedules_sql(session, group_id)}
                desired_ids = set(schedule_ids)

                for schedule_id in current_ids - desired_ids:
                    schedule = session.get(ScheduleModel, schedule_id)
                    if schedule:
                        self._remove_schedule_from_group_sql(session, schedule)

                for schedule_id in desired_ids:
                    schedule = session.get(ScheduleModel, schedule_id)
                    if schedule is None:
                        raise ValueError(f"Schedule {schedule_id} not found.")
                    if schedule.group_id != group_id:
                        if group_model.owner_key and schedule.owner_key and schedule.owner_key != group_model.owner_key:
                            raise ValueError("Schedule owner does not match group owner.")
                        self._remove_schedule_from_group_sql(session, schedule)
                        schedule.group_id = group_id

                if active_schedule_id and active_schedule_id not in desired_ids:
                    raise ValueError("activeScheduleId must be included in scheduleIds.")

            if active_schedule_id is not None:
                if active_schedule_id:
                    schedule = session.get(ScheduleModel, active_schedule_id)
                    if schedule is None or schedule.group_id != group_id:
                        raise ValueError("Active schedule must belong to the group.")
                    self._set_group_active_sql(session, group_model, active_schedule_id)
                else:
                    self._set_group_active_sql(session, group_model, None)

            group_model.updated_at = _now().isoformat()
            self._set_generated_at(session)
            session.commit()

            refreshed = session.get(ScheduleGroupModel, group_id)
            assert refreshed is not None
            group = self._model_to_group_record(refreshed)
            schedules = [
                _model_to_schedule(schedule)
                for schedule in self._group_schedules_sql(session, group_id)
            ]
            return group, schedules

    def delete_group(self, group_id: str) -> bool:
        with self._session() as session:
            group_model = session.get(ScheduleGroupModel, group_id)
            if group_model is None:
                return False
            schedules = self._group_schedules_sql(session, group_id)
            for schedule in schedules:
                schedule.group_id = None
                schedule.updated_at = _now().isoformat()
            session.delete(group_model)
            self._set_generated_at(session)
            session.commit()
            return True

    def set_group_active(
        self, group_id: str, schedule_id: str
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        with self._session() as session:
            group_model = session.get(ScheduleGroupModel, group_id)
            if group_model is None:
                return None
            schedule = session.get(ScheduleModel, schedule_id)
            if schedule is None or schedule.group_id != group_id:
                raise ValueError("Schedule must belong to the group.")
            self._set_group_active_sql(session, group_model, schedule_id)
            self._set_generated_at(session)
            session.commit()
            refreshed = session.get(ScheduleGroupModel, group_id)
            assert refreshed is not None
            group = self._model_to_group_record(refreshed)
            schedules = [
                _model_to_schedule(row)
                for row in self._group_schedules_sql(session, group_id)
            ]
            return group, schedules


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
