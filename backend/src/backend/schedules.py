"""Repositories and helpers for managing device lock schedules."""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Iterable, Literal, Protocol

from sqlalchemy import delete, select
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

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _schedule_to_model(schedule: DeviceSchedule) -> ScheduleModel:
    primary_group = schedule.group_ids[0] if schedule.group_ids else None
    return ScheduleModel(
        id=schedule.id,
        scope=schedule.scope,
        owner_key=schedule.owner_key,
        group_id=primary_group,
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


def _model_to_schedule(
    model: ScheduleModel,
    group_ids: Iterable[str] | None = None,
) -> DeviceSchedule:
    resolved_group_ids = list(group_ids or ([] if model.group_id is None else [model.group_id]))
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
        schedule.owner_key = data["ownerKey"].lower() if data["ownerKey"] else None
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
    if "groupIds" in data:
        schedule.group_ids = list(data["groupIds"] or [])
    return schedule


# ---------------------------------------------------------------------------
# Repository protocol
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# In-memory repository (used for mock mode/tests)
# ---------------------------------------------------------------------------


class InMemoryScheduleRepository(ScheduleRepository):
    def __init__(self) -> None:
        self._config = ScheduleConfig.model_validate(DEFAULT_SCHEDULE_CONFIG)
        self._groups: dict[str, ScheduleGroupRecord] = {}
        self._memberships: dict[str, set[str]] = defaultdict(set)
        self._schedule_memberships: dict[str, set[str]] = defaultdict(set)
        self._initialise_from_config()

    def _initialise_from_config(self) -> None:
        self._memberships.clear()
        self._schedule_memberships.clear()
        for schedule in self._config.schedules:
            schedule.group_ids = list(schedule.group_ids or [])
            for group_id in schedule.group_ids:
                self._memberships[group_id].add(schedule.id)
                self._schedule_memberships[schedule.id].add(group_id)
        self._enforce_activation()

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

    def _touch_generated(self) -> None:
        self._config.metadata.generated_at = _now()

    def _collect_group_schedules(self, group_id: str) -> list[DeviceSchedule]:
        return [
            self._clone_schedule(schedule)
            for schedule in self._config.schedules
            if group_id in self._schedule_memberships.get(schedule.id, set())
        ]

    def _add_membership(self, group: ScheduleGroupRecord, schedule_id: str) -> None:
        schedule = self._find_schedule(schedule_id)
        if schedule is None:
            raise ValueError(f"Schedule {schedule_id} not found.")
        if group.owner_key and schedule.owner_key and schedule.owner_key != group.owner_key:
            raise ValueError("Schedule owner does not match group owner.")
        if group.id not in schedule.group_ids:
            schedule.group_ids.append(group.id)
            schedule.updated_at = _now()
        self._memberships[group.id].add(schedule.id)
        self._schedule_memberships[schedule.id].add(group.id)

    def _remove_membership(self, group: ScheduleGroupRecord, schedule_id: str) -> None:
        schedule = self._find_schedule(schedule_id)
        if schedule is None:
            return
        if group.id in schedule.group_ids:
            schedule.group_ids.remove(group.id)
            schedule.updated_at = _now()
        self._memberships[group.id].discard(schedule_id)
        if schedule.id in self._schedule_memberships:
            self._schedule_memberships[schedule.id].discard(group.id)
            if not self._schedule_memberships[schedule.id]:
                del self._schedule_memberships[schedule.id]

    def _activate_group(self, target: ScheduleGroupRecord) -> None:
        now = _now()
        for group in self._groups.values():
            same_owner = (
                (group.owner_key is None and target.owner_key is None)
                or (group.owner_key is not None and group.owner_key == target.owner_key)
            )
            if not same_owner:
                continue
            was_active = group.is_active
            group.is_active = group.id == target.id
            if was_active != group.is_active:
                group.updated_at = now
        self._enforce_activation()

    def _enforce_activation(self) -> None:
        now = _now()
        active_groups = {gid for gid, group in self._groups.items() if group.is_active}
        active_schedule_ids: set[str] = set()
        for group_id in active_groups:
            active_schedule_ids.update(self._memberships.get(group_id, set()))
        managed_schedule_ids = set(self._schedule_memberships.keys())
        for schedule in self._config.schedules:
            if schedule.id not in managed_schedule_ids:
                continue
            should_enable = schedule.id in active_schedule_ids
            if schedule.enabled != should_enable:
                schedule.enabled = should_enable
                schedule.updated_at = now

    # Schedule CRUD ---------------------------------------------------

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
        schedule = self._find_schedule(schedule_id)
        return self._clone_schedule(schedule) if schedule else None

    def create(self, payload: ScheduleCreateRequest) -> DeviceSchedule:
        owner = payload.owner_key.lower() if payload.owner_key else None
        schedule = DeviceSchedule(
            id=str(uuid.uuid4()),
            scope=payload.scope,
            owner_key=owner,
            group_ids=[],
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
        group_ids = list(payload.group_ids or [])
        for group_id in group_ids:
            group = self._groups.get(group_id)
            if group is None:
                raise ValueError(f"Schedule group {group_id} not found.")
            self._add_membership(group, schedule.id)
        self._touch_generated()
        self._enforce_activation()
        return self._clone_schedule(schedule)

    def update(
        self, schedule_id: str, payload: ScheduleUpdateRequest
    ) -> DeviceSchedule | None:
        schedule = self._find_schedule(schedule_id)
        if schedule is None:
            return None
        updated = _apply_update(self._clone_schedule(schedule), payload)
        updated.updated_at = _now()
        if payload.group_ids is not None:
            desired = set(payload.group_ids)
            current = self._schedule_memberships.get(schedule_id, set()).copy()
            for removed in current - desired:
                group = self._groups.get(removed)
                if group:
                    self._remove_membership(group, schedule_id)
            for added in desired - current:
                group = self._groups.get(added)
                if group is None:
                    raise ValueError(f"Schedule group {added} not found.")
                self._add_membership(group, schedule_id)
            updated.group_ids = list(desired)
        self._set_schedule(updated)
        self._touch_generated()
        self._enforce_activation()
        return self._clone_schedule(updated)

    def delete(self, schedule_id: str) -> bool:
        index = self._find_schedule_index(schedule_id)
        if index is None:
            return False
        self._config.schedules.pop(index)
        for group_id in list(self._schedule_memberships.get(schedule_id, set())):
            group = self._groups.get(group_id)
            if group:
                self._remove_membership(group, schedule_id)
        self._schedule_memberships.pop(schedule_id, None)
        self._touch_generated()
        self._enforce_activation()
        return True

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        schedule = self._find_schedule(schedule_id)
        if schedule is None:
            return None
        schedule.enabled = enabled
        schedule.updated_at = _now()
        self._touch_generated()
        self._enforce_activation()
        return self._clone_schedule(schedule)

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
            self._groups.clear()
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
        self._initialise_from_config()

    def clone(self, schedule_id: str, target_owner: str) -> DeviceSchedule | None:
        schedule = self._find_schedule(schedule_id)
        if schedule is None:
            return None
        clone = _clone_for_owner(schedule, target_owner.lower())
        self._config.schedules.append(clone)
        self._touch_generated()
        return self._clone_schedule(clone)

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
                    for group_id in list(self._schedule_memberships.get(schedule.id, set())):
                        group = self._groups.get(group_id)
                        if group:
                            self._remove_membership(group, schedule.id)
                    continue
                remaining.append(schedule)
            self._config.schedules = remaining

        created: list[DeviceSchedule] = []
        for schedule in source_schedules:
            clone = _clone_for_owner(schedule, target_owner)
            self._config.schedules.append(clone)
            created.append(self._clone_schedule(clone))

        if created or replaced_count:
            self._touch_generated()

        return created, replaced_count

    # Group management ------------------------------------------------

    def list_groups(
        self, owner_key: str | None = None
    ) -> list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]]:
        groups = [
            group
            for group in self._groups.values()
            if owner_key is None or group.owner_key == owner_key
        ]
        return [
            (group, self._collect_group_schedules(group.id))
            for group in groups
        ]

    def get_group(self, group_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        return group, self._collect_group_schedules(group_id)

    def create_group(
        self,
        name: str,
        *,
        owner_key: str | None,
        description: str | None,
        schedule_ids: list[str],
        is_active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]]:
        group_id = str(uuid.uuid4())
        now = _now()
        record = ScheduleGroupRecord(
            id=group_id,
            name=name.strip(),
            owner_key=owner_key.lower() if owner_key else None,
            description=description.strip() if description else None,
            is_active=False,
            created_at=now,
            updated_at=now,
        )
        self._groups[group_id] = record
        for schedule_id in schedule_ids:
            self._add_membership(record, schedule_id)
        if is_active and schedule_ids:
            self._activate_group(record)
        else:
            self._enforce_activation()
        self._touch_generated()
        return record, self._collect_group_schedules(group_id)

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        schedule_ids: list[str] | None = None,
        is_active: bool | None = None,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        if name is not None:
            group.name = name.strip()
        if description is not None:
            group.description = description.strip() or None
        if schedule_ids is not None:
            desired = set(schedule_ids)
            current = self._memberships.get(group_id, set()).copy()
            for removed in current - desired:
                self._remove_membership(group, removed)
            for added in desired - current:
                self._add_membership(group, added)
            group.updated_at = _now()
        if is_active is not None:
            if is_active:
                self._activate_group(group)
            else:
                if group.is_active:
                    group.is_active = False
                    group.updated_at = _now()
                    self._enforce_activation()
        else:
            self._enforce_activation()
        self._touch_generated()
        return group, self._collect_group_schedules(group_id)

    def delete_group(self, group_id: str) -> bool:
        group = self._groups.pop(group_id, None)
        if group is None:
            return False
        for schedule_id in list(self._memberships.get(group_id, set())):
            self._remove_membership(group, schedule_id)
        self._memberships.pop(group_id, None)
        self._touch_generated()
        self._enforce_activation()
        return True

    def set_group_active(
        self,
        group_id: str,
        active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        group = self._groups.get(group_id)
        if group is None:
            return None
        if active:
            self._activate_group(group)
        else:
            if group.is_active:
                group.is_active = False
                group.updated_at = _now()
                self._enforce_activation()
        self._touch_generated()
        return group, self._collect_group_schedules(group_id)


# ---------------------------------------------------------------------------
# SQLAlchemy repository (database-backed mode)
# ---------------------------------------------------------------------------


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
            is_active=bool(model.is_active),
            created_at=datetime.fromisoformat(model.created_at),
            updated_at=datetime.fromisoformat(model.updated_at),
        )

    def _schedule_group_map(
        self, session: Session, schedule_ids: Iterable[str]
    ) -> dict[str, list[str]]:
        schedule_ids = list(schedule_ids)
        if not schedule_ids:
            return {}
        rows = session.execute(
            select(
                ScheduleGroupMembershipModel.schedule_id,
                ScheduleGroupMembershipModel.group_id,
            ).where(ScheduleGroupMembershipModel.schedule_id.in_(schedule_ids))
        ).all()
        mapping: dict[str, list[str]] = defaultdict(list)
        for schedule_id, group_id in rows:
            mapping[schedule_id].append(group_id)
        for group_list in mapping.values():
            group_list.sort()
        return mapping

    def _group_schedule_ids(self, session: Session, group_id: str) -> list[str]:
        rows = session.execute(
            select(ScheduleGroupMembershipModel.schedule_id).where(
                ScheduleGroupMembershipModel.group_id == group_id
            )
        ).scalars()
        return list(rows)

    def _add_membership_sql(
        self,
        session: Session,
        group: ScheduleGroupModel,
        schedule: ScheduleModel,
    ) -> None:
        if group.owner_key and schedule.owner_key and group.owner_key != schedule.owner_key:
            raise ValueError("Schedule owner does not match group owner.")
        membership = ScheduleGroupMembershipModel(
            group_id=group.id,
            schedule_id=schedule.id,
            created_at=_now().isoformat(),
        )
        session.merge(membership)
        session.flush()
        self._refresh_primary_group(session, schedule.id)

    def _remove_membership_sql(
        self,
        session: Session,
        group_id: str,
        schedule_id: str,
    ) -> None:
        session.execute(
            delete(ScheduleGroupMembershipModel).where(
                ScheduleGroupMembershipModel.group_id == group_id,
                ScheduleGroupMembershipModel.schedule_id == schedule_id,
            )
        )
        self._refresh_primary_group(session, schedule_id)

    def _refresh_primary_group(self, session: Session, schedule_id: str) -> None:
        schedule = session.get(ScheduleModel, schedule_id)
        if schedule is None:
            return
        group_ids = self._group_schedule_ids(session, schedule_id)
        schedule.group_id = group_ids[0] if group_ids else None
        schedule.updated_at = _now().isoformat()

    def _enforce_activation_sql(self, session: Session) -> None:
        stmt = select(ScheduleGroupModel.id).where(
            ScheduleGroupModel.is_active.is_(True)
        )
        active_group_ids = session.execute(stmt).scalars().all()
        active_schedule_ids: set[str] = set()
        if active_group_ids:
            rows = session.execute(
                select(ScheduleGroupMembershipModel.schedule_id).where(
                    ScheduleGroupMembershipModel.group_id.in_(active_group_ids)
                )
            ).scalars()
            active_schedule_ids.update(rows)
        managed_schedule_ids = set(
            session.execute(
                select(ScheduleGroupMembershipModel.schedule_id).distinct()
            ).scalars()
        )
        if not managed_schedule_ids:
            return
        schedules = session.execute(
            select(ScheduleModel).where(ScheduleModel.id.in_(managed_schedule_ids))
        ).scalars()
        now_iso = _now().isoformat()
        for schedule in schedules:
            should_enable = schedule.id in active_schedule_ids
            if bool(schedule.enabled) != should_enable:
                schedule.enabled = should_enable
                schedule.updated_at = now_iso

    def _activate_group_sql(self, session: Session, group: ScheduleGroupModel) -> None:
        now_iso = _now().isoformat()
        owner_key = group.owner_key
        stmt = select(ScheduleGroupModel).where(ScheduleGroupModel.id != group.id)
        if owner_key is None:
            stmt = stmt.where(ScheduleGroupModel.owner_key.is_(None))
        else:
            stmt = stmt.where(ScheduleGroupModel.owner_key == owner_key)
        for other in session.execute(stmt).scalars():
            if other.is_active:
                other.is_active = False
                other.updated_at = now_iso
        if not group.is_active:
            group.is_active = True
            group.updated_at = now_iso
        self._enforce_activation_sql(session)

    # Schedule CRUD ---------------------------------------------------

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
            memberships = self._schedule_group_map(session, [row.id for row in rows])
            return [_model_to_schedule(row, memberships.get(row.id, [])) for row in rows]

    def get(self, schedule_id: str) -> DeviceSchedule | None:
        with self._session() as session:
            row = session.get(ScheduleModel, schedule_id)
            if row is None:
                return None
            memberships = self._schedule_group_map(session, [row.id])
            return _model_to_schedule(row, memberships.get(row.id, []))

    def create(self, payload: ScheduleCreateRequest) -> DeviceSchedule:
        owner = payload.owner_key.lower() if payload.owner_key else None
        schedule = DeviceSchedule(
            id=str(uuid.uuid4()),
            scope=payload.scope,
            owner_key=owner,
            group_ids=list(payload.group_ids or []),
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
            session.flush()
            for group_id in schedule.group_ids:
                group_model = session.get(ScheduleGroupModel, group_id)
                if group_model is None:
                    raise ValueError(f"Schedule group {group_id} not found.")
                self._add_membership_sql(session, group_model, model)
            self._set_generated_at(session)
            self._enforce_activation_sql(session)
            session.commit()
        return self.get(schedule.id)  # type: ignore[return-value]

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
            if payload.group_ids is not None:
                desired = set(payload.group_ids)
                current = set(self._group_schedule_ids(session, schedule_id))
                for removed in current - desired:
                    self._remove_membership_sql(session, removed, schedule_id)
                for added in desired - current:
                    group_model = session.get(ScheduleGroupModel, added)
                    if group_model is None:
                        raise ValueError(f"Schedule group {added} not found.")
                    self._add_membership_sql(session, group_model, existing)
                updated.group_ids = list(desired)
            self._set_generated_at(session)
            self._enforce_activation_sql(session)
            session.commit()
        return self.get(schedule_id)

    def delete(self, schedule_id: str) -> bool:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return False
            session.delete(existing)
            session.execute(
                delete(ScheduleGroupMembershipModel).where(
                    ScheduleGroupMembershipModel.schedule_id == schedule_id
                )
            )
            self._set_generated_at(session)
            self._enforce_activation_sql(session)
            session.commit()
            return True

    def set_enabled(self, schedule_id: str, enabled: bool) -> DeviceSchedule | None:
        with self._session() as session:
            existing = session.get(ScheduleModel, schedule_id)
            if existing is None:
                return None
            existing.enabled = enabled
            existing.updated_at = _now().isoformat()
            self._set_generated_at(session)
            self._enforce_activation_sql(session)
            session.commit()
        return self.get(schedule_id)

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
            memberships = self._schedule_group_map(
                session,
                [row.id for row in owner_rows + global_rows],
            )
            return (
                [_model_to_schedule(row, memberships.get(row.id, [])) for row in owner_rows],
                [_model_to_schedule(row, memberships.get(row.id, [])) for row in global_rows],
            )

    def get_metadata(self) -> ScheduleMetadata:
        with self._session() as session:
            return self._get_metadata(session)

    def sync_from_config(self, config: ScheduleConfig, *, replace: bool) -> None:
        with self._session() as session:
            if replace:
                session.query(ScheduleGroupMembershipModel).delete()
                session.query(ScheduleGroupModel).delete()
                session.query(ScheduleModel).delete()
                for schedule in config.schedules:
                    model = _schedule_to_model(
                        DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))
                    )
                    session.merge(model)
            else:
                existing_ids = {
                    row.id for row in session.execute(select(ScheduleModel.id)).scalars()
                }
                for schedule in config.schedules:
                    if schedule.id in existing_ids:
                        continue
                    model = _schedule_to_model(
                        DeviceSchedule.model_validate(schedule.model_dump(by_alias=True))
                    )
                    session.merge(model)
            session.merge(_metadata_to_model(ScheduleMetadata.model_validate(
                config.metadata.model_dump(by_alias=True)
            )))
            session.commit()

    def clone(self, schedule_id: str, target_owner: str) -> DeviceSchedule | None:
        with self._session() as session:
            source = session.get(ScheduleModel, schedule_id)
            if source is None:
                return None
            schedule = _model_to_schedule(source)
            clone = _clone_for_owner(schedule, target_owner.lower())
            model = _schedule_to_model(clone)
            session.merge(model)
            self._set_generated_at(session)
            session.commit()
        return self.get(clone.id)

    def copy_owner_schedules(
        self,
        source_owner: str,
        target_owner: str,
        *,
        mode: Literal["merge", "replace"],
    ) -> tuple[list[DeviceSchedule], int]:
        source_owner = source_owner.lower()
        target_owner = target_owner.lower()
        created: list[DeviceSchedule] = []
        replaced_count = 0
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
                    session.execute(
                        delete(ScheduleGroupMembershipModel).where(
                            ScheduleGroupMembershipModel.schedule_id == row.id
                        )
                    )
                    session.delete(row)
            for row in source_rows:
                schedule = _model_to_schedule(row)
                clone = _clone_for_owner(schedule, target_owner)
                model = _schedule_to_model(clone)
                session.merge(model)
                created.append(clone)
            self._set_generated_at(session)
            session.commit()
        return [self.get(item.id) for item in created if item.id], replaced_count  # type: ignore[list-item]

    # Group management ------------------------------------------------

    def list_groups(
        self, owner_key: str | None = None
    ) -> list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]]:
        with self._session() as session:
            stmt = select(ScheduleGroupModel)
            if owner_key is None:
                stmt = stmt.where(ScheduleGroupModel.owner_key.is_(None))
            else:
                stmt = stmt.where(ScheduleGroupModel.owner_key == owner_key)
            groups = session.execute(stmt).scalars().all()
            result: list[tuple[ScheduleGroupRecord, list[DeviceSchedule]]] = []
            for group in groups:
                records = self._group_schedule_ids(session, group.id)
                schedule_rows = (
                    session.execute(
                        select(ScheduleModel).where(ScheduleModel.id.in_(records))
                    )
                    .scalars()
                    .all()
                )
                memberships = self._schedule_group_map(session, records)
                result.append(
                    (
                        self._model_to_group_record(group),
                        [
                            _model_to_schedule(row, memberships.get(row.id, []))
                            for row in schedule_rows
                        ],
                    )
                )
            return result

    def get_group(self, group_id: str) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        with self._session() as session:
            group = session.get(ScheduleGroupModel, group_id)
            if group is None:
                return None
            records = self._group_schedule_ids(session, group.id)
            schedule_rows = (
                session.execute(
                    select(ScheduleModel).where(ScheduleModel.id.in_(records))
                )
                .scalars()
                .all()
            )
            memberships = self._schedule_group_map(session, records)
            return (
                self._model_to_group_record(group),
                [
                    _model_to_schedule(row, memberships.get(row.id, []))
                    for row in schedule_rows
                ],
            )

    def create_group(
        self,
        name: str,
        *,
        owner_key: str | None,
        description: str | None,
        schedule_ids: list[str],
        is_active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]]:
        now_iso = _now().isoformat()
        owner = owner_key.lower() if owner_key else None
        group_model = ScheduleGroupModel(
            id=str(uuid.uuid4()),
            owner_key=owner,
            name=name.strip(),
            description=description.strip() if description else None,
            active_schedule_id=None,
            is_active=False,
            created_at=now_iso,
            updated_at=now_iso,
        )
        with self._session() as session:
            session.merge(group_model)
            session.flush()
            for schedule_id in schedule_ids:
                schedule_model = session.get(ScheduleModel, schedule_id)
                if schedule_model is None:
                    raise ValueError(f"Schedule {schedule_id} not found.")
                self._add_membership_sql(session, group_model, schedule_model)
            if is_active and schedule_ids:
                self._activate_group_sql(session, group_model)
            else:
                self._enforce_activation_sql(session)
            self._set_generated_at(session)
            session.commit()
        return self.get_group(group_model.id)  # type: ignore[return-value]

    def update_group(
        self,
        group_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        schedule_ids: list[str] | None = None,
        is_active: bool | None = None,
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
                desired = set(schedule_ids)
                current = set(self._group_schedule_ids(session, group_id))
                for removed in current - desired:
                    self._remove_membership_sql(session, group_id, removed)
                for added in desired - current:
                    schedule_model = session.get(ScheduleModel, added)
                    if schedule_model is None:
                        raise ValueError(f"Schedule {added} not found.")
                    self._add_membership_sql(session, group_model, schedule_model)
            if is_active is not None:
                if is_active:
                    self._activate_group_sql(session, group_model)
                else:
                    if group_model.is_active:
                        group_model.is_active = False
                        group_model.updated_at = _now().isoformat()
                        self._enforce_activation_sql(session)
            else:
                self._enforce_activation_sql(session)
            self._set_generated_at(session)
            session.commit()
        return self.get_group(group_id)

    def delete_group(self, group_id: str) -> bool:
        with self._session() as session:
            group_model = session.get(ScheduleGroupModel, group_id)
            if group_model is None:
                return False
            session.execute(
                delete(ScheduleGroupMembershipModel).where(
                    ScheduleGroupMembershipModel.group_id == group_id
                )
            )
            session.delete(group_model)
            self._set_generated_at(session)
            self._enforce_activation_sql(session)
            session.commit()
            return True

    def set_group_active(
        self,
        group_id: str,
        active: bool,
    ) -> tuple[ScheduleGroupRecord, list[DeviceSchedule]] | None:
        with self._session() as session:
            group_model = session.get(ScheduleGroupModel, group_id)
            if group_model is None:
                return None
            if active:
                self._activate_group_sql(session, group_model)
            else:
                if group_model.is_active:
                    group_model.is_active = False
                    group_model.updated_at = _now().isoformat()
                    self._enforce_activation_sql(session)
            self._set_generated_at(session)
            session.commit()
        return self.get_group(group_id)


# ---------------------------------------------------------------------------
# Repository factories
# ---------------------------------------------------------------------------


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
