"""API router exposing the UniFi device management endpoints."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from . import schemas
from .device_types import add_device_type, list_device_types, remove_device_type
from .events import Event, list_recent_events, record_event
from .owners import Owner, delete_owner, get_owner_repository, register_owner
from .services import (
    DeviceRecord,
    apply_lock_action,
    build_device_from_target,
    get_device_detail_record,
    get_registered_device_records,
    get_unregistered_client_records,
    register_device_for_owner,
    summarize_owner_records,
)
from .schedules import get_schedule_repository
from .ubiquiti.devices import get_device_repository
from .ubiquiti.unifi import UniFiAPIError

router = APIRouter(prefix="/api", tags=["devices"])


def _filter_device_records(
    records: list[DeviceRecord],
    owners: list[str] | None,
    locked: bool | None,
    search: str | None,
) -> list[DeviceRecord]:
    filtered = list(records)
    if owners:
        owner_set = {value.lower() for value in owners}
        filtered = [record for record in filtered if record["owner"] in owner_set]

    if locked is not None:
        filtered = [record for record in filtered if record["locked"] is locked]

    if search:
        needle = search.strip().lower()
        if needle:
            filtered = [
                record
                for record in filtered
                if any(
                    needle in str(value).lower()
                    for value in (
                        record["name"],
                        record["owner"],
                        record["type"],
                        record["mac"],
                        record["vendor"],
                    )
                    if value
                )
            ]
    return filtered


def _require_owner(owner_key: str) -> None:
    owner_repo = get_owner_repository()
    if owner_repo.get(owner_key) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")


def _group_to_schema(
    record_schedule_pair: tuple[schedules.ScheduleGroupRecord, list[schemas.DeviceSchedule]]
) -> schemas.ScheduleGroup:
    record, schedules_list = record_schedule_pair
    return schemas.ScheduleGroup(
        id=record.id,
        name=record.name,
        description=record.description,
        owner_key=record.owner_key,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
        schedules=schedules_list,
    )


def _generate_owner_key(name: str) -> str:
    owner_repo = get_owner_repository()
    existing = {owner.key for owner in owner_repo.list_all()}
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not base:
        base = "owner"
    candidate = base
    suffix = 2
    while candidate in existing:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _resolve_actor(request: Request, explicit: str | None = None) -> str:
    if explicit:
        candidate = explicit.strip()
        if candidate:
            return candidate
    header_actor = request.headers.get("x-actor")
    if header_actor:
        candidate = header_actor.strip()
        if candidate:
            return candidate
    return "system"


def _resolve_reason(request: Request, explicit: str | None = None) -> str | None:
    if explicit:
        candidate = explicit.strip()
        if candidate:
            return candidate
    header_reason = request.headers.get("x-reason")
    if header_reason:
        candidate = header_reason.strip()
        if candidate:
            return candidate
    return None


def _event_to_schema(event: Event) -> schemas.AuditEvent:
    return schemas.AuditEvent(
        id=event.id,
        timestamp=event.timestamp,
        action=event.action,
        actor=event.actor,
        subject_type=event.subject_type,
        subject_id=event.subject_id,
        reason=event.reason,
        metadata=event.metadata,
    )


@router.get("/dashboard/summary", response_model=schemas.DashboardSummary)
def get_dashboard_summary() -> schemas.DashboardSummary:
    try:
        records = get_registered_device_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    total_devices = len(records)
    locked_devices = sum(1 for record in records if record["locked"])
    unknown_vendors = sum(1 for record in records if not record["vendor"])

    return schemas.DashboardSummary(
        total_devices=total_devices,
        locked_devices=locked_devices,
        unlocked_devices=max(total_devices - locked_devices, 0),
        owner_count=len({record["owner"] for record in records}),
        unknown_vendors=unknown_vendors,
        generated_at=datetime.now(tz=UTC).astimezone(),
    )


@router.get("/devices", response_model=schemas.DeviceListResponse)
def list_devices(
    owner: Annotated[list[str] | None, Query()] = None,
    locked: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
) -> schemas.DeviceListResponse:
    try:
        records = get_registered_device_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    filtered = _filter_device_records(records, owner, locked, search)
    return schemas.DeviceListResponse(
        devices=[
            schemas.DeviceStatus(
                name=record["name"],
                owner=record["owner"],
                type=record["type"],
                mac=record["mac"],
                locked=record["locked"],
                vendor=record["vendor"],
            )
            for record in filtered
        ]
    )


@router.get(
    "/devices/{mac}/detail",
    response_model=schemas.DeviceDetail,
)
def get_device_detail(
    mac: str,
    lookback_minutes: Annotated[
        int,
        Query(
            ge=5,
            le=24 * 60,
            description="Number of minutes of traffic history to include in the summary.",
        ),
    ] = 60,
) -> schemas.DeviceDetail:
    try:
        record = get_device_detail_record(mac, lookback_minutes=lookback_minutes)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Device not found.")
    return schemas.DeviceDetail(**record)


@router.get(
    "/events",
    response_model=schemas.EventListResponse,
    tags=["events"],
)
def list_audit_events(
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=500,
            description="Maximum number of recent events to return.",
        ),
    ] = 100,
) -> schemas.EventListResponse:
    events = list_recent_events(limit)
    return schemas.EventListResponse(events=[_event_to_schema(event) for event in events])


@router.get("/owners", response_model=schemas.OwnersResponse)
def list_owner_summaries() -> schemas.OwnersResponse:
    try:
        records = get_registered_device_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    summaries = summarize_owner_records(records)
    return schemas.OwnersResponse(
        owners=[
            schemas.OwnerSummary(
                key=summary["key"],
                display_name=summary["display_name"],
                total_devices=summary["total_devices"],
                locked_devices=summary["locked_devices"],
                unlocked_devices=summary["unlocked_devices"],
            )
            for summary in summaries
        ]
    )


@router.get(
    "/owners/all",
    response_model=schemas.OwnerListResponse,
    tags=["owners"],
)
def list_all_owners() -> schemas.OwnerListResponse:
    repository = get_owner_repository()
    owners = [
        schemas.OwnerInfo(key=owner.key, display_name=owner.display_name)
        for owner in repository.list_all()
    ]
    owners.sort(key=lambda item: item.display_name.lower())
    return schemas.OwnerListResponse(owners=owners)


@router.post(
    "/owners",
    response_model=schemas.OwnerInfo,
    status_code=status.HTTP_201_CREATED,
    tags=["owners"],
)
def create_owner(
    payload: schemas.OwnerCreateRequest,
    request: Request,
) -> schemas.OwnerInfo:
    display_name = payload.display_name.strip()
    if not display_name:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="displayName must not be empty.",
        )
    pin = payload.pin.strip()
    if not pin:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pin must not be empty.",
        )

    key = _generate_owner_key(display_name)
    owner = Owner(key=key, display_name=display_name, pin=pin)
    register_owner(owner)
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="owner_created",
        subject_type="owner",
        subject_id=owner.key,
        actor=actor,
        reason=reason,
        metadata={"display_name": owner.display_name},
    )
    return schemas.OwnerInfo(key=owner.key, display_name=owner.display_name)


@router.delete(
    "/owners/{owner_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["owners"],
)
def delete_owner_entry(owner_key: str, request: Request) -> Response:
    if owner_key.lower() in {"master"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the master owner.",
        )
    owner_repo = get_owner_repository()
    existing = owner_repo.get(owner_key)
    if not delete_owner(owner_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="owner_deleted",
        subject_type="owner",
        subject_id=owner_key.lower(),
        actor=actor,
        reason=reason,
        metadata={"display_name": existing.display_name if existing else None},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/owners/{owner_key}/verify-pin",
    response_model=schemas.VerifyPinResponse,
    status_code=status.HTTP_200_OK,
)
def verify_owner(
    owner_key: str,
    payload: schemas.VerifyPinRequest,
) -> schemas.VerifyPinResponse:
    owner_repo = get_owner_repository()
    owner_entry = owner_repo.get(owner_key)
    if owner_entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")
    return schemas.VerifyPinResponse(
        valid=owner_repo.verify_pin(owner_key, payload.pin)
    )


@router.get(
    "/owners/{owner_key}/devices",
    response_model=schemas.DeviceListResponse,
)
def list_owner_devices(owner_key: str) -> schemas.DeviceListResponse:
    owner_key_lower = owner_key.lower()
    owner_repo = get_owner_repository()
    owner_entry = owner_repo.get(owner_key_lower)
    try:
        records = get_registered_device_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    filtered = [record for record in records if record["owner"] == owner_key_lower]
    if not filtered and owner_entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    return schemas.DeviceListResponse(
        devices=[
            schemas.DeviceStatus(
                name=record["name"],
                owner=record["owner"],
                type=record["type"],
                mac=record["mac"],
                locked=record["locked"],
                vendor=record["vendor"],
            )
            for record in filtered
        ]
    )


@router.post(
    "/owners/{owner_key}/devices",
    response_model=schemas.DeviceStatus,
    status_code=status.HTTP_201_CREATED,
)
def register_owner_device(
    owner_key: str,
    payload: schemas.DeviceRegistrationRequest,
    request: Request,
) -> schemas.DeviceStatus:
    _require_owner(owner_key)
    actor = _resolve_actor(request, payload.actor)
    reason = _resolve_reason(request, payload.reason)
    try:
        record = register_device_for_owner(
            owner_key,
            mac=payload.mac,
            name=payload.name,
            device_type=payload.type,
        )
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    record_event(
        action="device_registered",
        subject_type="device",
        subject_id=record["mac"],
        actor=actor,
        reason=reason,
        metadata={
            "owner": record["owner"],
            "type": record["type"],
            "name": record["name"],
        },
    )

    return schemas.DeviceStatus(
        name=record["name"],
        owner=record["owner"],
        type=record["type"],
        mac=record["mac"],
        locked=record["locked"],
        vendor=record["vendor"],
    )


@router.post(
    "/devices/lock",
    response_model=schemas.DeviceActionResponse,
    status_code=status.HTTP_200_OK,
)
def lock_devices(
    payload: schemas.DeviceActionRequest,
    request: Request,
) -> schemas.DeviceActionResponse:
    actor = _resolve_actor(request, payload.actor)
    reason = _resolve_reason(request, payload.reason)
    devices = [build_device_from_target(target) for target in payload.targets]
    try:
        results = apply_lock_action(
            devices,
            unlock=payload.unlock,
            actor=actor,
            reason=reason,
        )
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return schemas.DeviceActionResponse(
        results=[schemas.DeviceActionResult(**result) for result in results]
    )


@router.post(
    "/owners/{owner_key}/lock",
    response_model=schemas.OwnerLockResponse,
    status_code=status.HTTP_200_OK,
)
def lock_owner_devices(
    owner_key: str,
    payload: schemas.OwnerLockRequest,
    request: Request,
) -> schemas.OwnerLockResponse:
    owner_key_lower = owner_key.lower()
    owner_repo = get_owner_repository()
    device_repo = get_device_repository()
    devices = device_repo.list_by_owner(owner_key_lower)
    if not devices and owner_repo.get(owner_key_lower) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    actor = _resolve_actor(request, payload.actor)
    reason = _resolve_reason(request, payload.reason)
    try:
        results = apply_lock_action(
            devices,
            unlock=payload.unlock,
            actor=actor,
            reason=reason,
        )
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    record_event(
        action="owner_devices_unlocked" if payload.unlock else "owner_devices_locked",
        subject_type="owner",
        subject_id=owner_key_lower,
        actor=actor,
        reason=reason,
        metadata={
            "processed": len(devices),
            "unlock": payload.unlock,
        },
    )

    return schemas.OwnerLockResponse(
        owner=owner_key_lower,
        processed=len(devices),
        results=[schemas.DeviceActionResult(**result) for result in results],
    )


@router.get(
    "/clients/unregistered",
    response_model=schemas.UnregisteredClientsResponse,
)
def list_unregistered_clients() -> schemas.UnregisteredClientsResponse:
    try:
        clients = get_unregistered_client_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return schemas.UnregisteredClientsResponse(
        clients=[schemas.UnregisteredClient(**client) for client in clients]
    )


@router.post(
    "/clients/unregistered/lock",
    response_model=schemas.DeviceActionResponse,
    status_code=status.HTTP_200_OK,
)
def lock_unregistered_client(
    payload: schemas.SingleClientLockRequest,
    request: Request,
) -> schemas.DeviceActionResponse:
    target = schemas.DeviceTarget(
        mac=payload.mac,
        name=payload.name,
        owner=payload.owner or "unregistered",
        type=payload.type or "unknown",
    )
    actor = _resolve_actor(request, payload.actor)
    reason = _resolve_reason(request, payload.reason)
    try:
        results = apply_lock_action(
            [build_device_from_target(target)],
            unlock=payload.unlock,
            actor=actor,
            reason=reason,
        )
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return schemas.DeviceActionResponse(
        results=[schemas.DeviceActionResult(**result) for result in results]
    )


# ---------------------------------------------------------------------------
# Schedule endpoints


@router.get(
    "/schedules",
    response_model=schemas.ScheduleListResponse,
    tags=["schedules"],
)
def list_schedules(
    scope: Annotated[str | None, Query()] = None,
    owner: Annotated[str | None, Query()] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> schemas.ScheduleListResponse:
    schedule_repo = get_schedule_repository()
    metadata = schedule_repo.get_metadata()
    schedules = schedule_repo.list(scope=scope, owner=owner, enabled=enabled)
    return schemas.ScheduleListResponse(metadata=metadata, schedules=schedules)


@router.get(
    "/owners/{owner_key}/schedule-groups",
    response_model=schemas.ScheduleGroupListResponse,
    tags=["schedules"],
)
def list_schedule_groups(owner_key: str) -> schemas.ScheduleGroupListResponse:
    schedule_repo = get_schedule_repository()
    normalized = owner_key.lower()
    if normalized == "global":
        owner_groups: list[schemas.ScheduleGroup] = []
        global_groups = [
            _group_to_schema(group)
            for group in schedule_repo.list_groups(owner_key=None)
        ]
    else:
        _require_owner(normalized)
        owner_groups = [
            _group_to_schema(group)
            for group in schedule_repo.list_groups(owner_key=normalized)
        ]
        global_groups = [
            _group_to_schema(group)
            for group in schedule_repo.list_groups(owner_key=None)
        ]
    return schemas.ScheduleGroupListResponse(
        owner_groups=owner_groups,
        global_groups=global_groups,
    )


@router.post(
    "/schedules",
    response_model=schemas.DeviceSchedule,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
)
def create_schedule(
    payload: schemas.ScheduleCreateRequest,
    request: Request,
) -> schemas.DeviceSchedule:
    if payload.scope == "owner":
        if not payload.owner_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ownerKey is required when scope is 'owner'.",
            )
        _require_owner(payload.owner_key)
    schedule_repo = get_schedule_repository()
    try:
        schedule = schedule_repo.create(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_created",
        subject_type="schedule",
        subject_id=schedule.id,
        actor=actor,
        reason=reason,
        metadata={
            "scope": schedule.scope,
            "owner_key": schedule.owner_key,
            "label": schedule.label,
        },
    )
    return schedule


@router.get(
    "/schedules/{schedule_id}",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def get_schedule(schedule_id: str) -> schemas.DeviceSchedule:
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.get(schedule_id)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    return schedule


@router.patch(
    "/schedules/{schedule_id}",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def update_schedule(
    schedule_id: str,
    payload: schemas.ScheduleUpdateRequest,
    request: Request,
) -> schemas.DeviceSchedule:
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="No fields provided for update."
    )
    if payload.owner_key:
        _require_owner(payload.owner_key)
    schedule_repo = get_schedule_repository()
    try:
        schedule = schedule_repo.update(schedule_id, payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_updated",
        subject_type="schedule",
        subject_id=schedule_id,
        actor=actor,
        reason=reason,
        metadata={
            "changes": payload.model_dump(exclude_unset=True, by_alias=True),
        },
    )
    return schedule


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["schedules"],
)
def delete_schedule(schedule_id: str, request: Request) -> Response:
    schedule_repo = get_schedule_repository()
    existing = schedule_repo.get(schedule_id)
    deleted = schedule_repo.delete(schedule_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_deleted",
        subject_type="schedule",
        subject_id=schedule_id,
        actor=actor,
        reason=reason,
        metadata={
            "label": existing.label if existing else None,
            "owner_key": existing.owner_key if existing else None,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/enable",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def enable_schedule(schedule_id: str, request: Request) -> schemas.DeviceSchedule:
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.set_enabled(schedule_id, True)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_enabled",
        subject_type="schedule",
        subject_id=schedule.id,
        actor=actor,
        reason=reason,
        metadata={"owner_key": schedule.owner_key, "label": schedule.label},
    )
    return schedule


@router.post(
    "/schedules/{schedule_id}/clone",
    response_model=schemas.ScheduleCloneResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
)
def clone_schedule_entry(
    schedule_id: str,
    payload: schemas.ScheduleCloneRequest,
    request: Request,
) -> schemas.ScheduleCloneResponse:
    target_owner = payload.target_owner.strip().lower()
    _require_owner(target_owner)
    schedule_repo = get_schedule_repository()
    cloned = schedule_repo.clone(schedule_id, target_owner)
    if cloned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_cloned",
        subject_type="schedule",
        subject_id=cloned.id,
        actor=actor,
        reason=reason,
        metadata={
            "source_schedule": schedule_id,
            "target_owner": target_owner,
            "label": cloned.label,
        },
    )
    return schemas.ScheduleCloneResponse(schedule=cloned)


@router.post(
    "/owners/{source_owner}/schedules/copy",
    response_model=schemas.OwnerScheduleCopyResponse,
    tags=["schedules"],
)
def copy_owner_schedules_endpoint(
    source_owner: str,
    payload: schemas.OwnerScheduleCopyRequest,
    request: Request,
) -> schemas.OwnerScheduleCopyResponse:
    source_key = source_owner.strip().lower()
    target_owner = payload.target_owner.strip().lower()
    if source_key == target_owner:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Target owner must be different from source owner.",
        )
    _require_owner(source_key)
    _require_owner(target_owner)
    schedule_repo = get_schedule_repository()
    created, replaced = schedule_repo.copy_owner_schedules(
        source_key,
        target_owner,
        mode=payload.mode,
    )
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="owner_schedules_copied",
        subject_type="owner",
        subject_id=target_owner,
        actor=actor,
        reason=reason,
        metadata={
            "source_owner": source_key,
            "target_owner": target_owner,
            "mode": payload.mode,
            "created_count": len(created),
            "replaced_count": replaced,
        },
    )
    return schemas.OwnerScheduleCopyResponse(
        source_owner=source_key,
        target_owner=target_owner,
        mode=payload.mode,
        created=created,
        replaced_count=replaced,
    )


@router.post(
    "/schedule-groups",
    response_model=schemas.ScheduleGroup,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
)
def create_schedule_group(
    payload: schemas.ScheduleGroupCreateRequest,
    request: Request,
) -> schemas.ScheduleGroup:
    schedule_repo = get_schedule_repository()
    owner_key = payload.owner_key.lower() if payload.owner_key else None
    if owner_key:
        _require_owner(owner_key)
    try:
        group_record, schedules_list = schedule_repo.create_group(
            payload.name,
            owner_key=owner_key,
            description=payload.description,
            schedule_ids=payload.schedule_ids,
            is_active=payload.is_active or False,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_group_created",
        subject_type="schedule_group",
        subject_id=group_record.id,
        actor=actor,
        reason=reason,
        metadata={
            "name": group_record.name,
            "owner_key": group_record.owner_key,
            "schedule_count": len(schedules_list),
            "is_active": group_record.is_active,
        },
    )
    return _group_to_schema((group_record, schedules_list))


@router.patch(
    "/schedule-groups/{group_id}",
    response_model=schemas.ScheduleGroup,
    tags=["schedules"],
)
def update_schedule_group(
    group_id: str,
    payload: schemas.ScheduleGroupUpdateRequest,
    request: Request,
) -> schemas.ScheduleGroup:
    schedule_repo = get_schedule_repository()
    try:
        group = schedule_repo.update_group(
            group_id,
            name=payload.name,
            description=payload.description,
            schedule_ids=payload.schedule_ids,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule group not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_group_updated",
        subject_type="schedule_group",
        subject_id=group[0].id,
        actor=actor,
        reason=reason,
        metadata={
            "name": group[0].name,
            "owner_key": group[0].owner_key,
            "schedule_count": len(group[1]),
            "is_active": group[0].is_active,
        },
    )
    return _group_to_schema(group)


@router.delete(
    "/schedule-groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["schedules"],
)
def delete_schedule_group(group_id: str, request: Request) -> Response:
    schedule_repo = get_schedule_repository()
    existing = schedule_repo.get_group(group_id)
    deleted = schedule_repo.delete_group(group_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule group not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_group_deleted",
        subject_type="schedule_group",
        subject_id=group_id,
        actor=actor,
        reason=reason,
        metadata={
            "name": existing[0].name if existing else None,
            "owner_key": existing[0].owner_key if existing else None,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedule-groups/{group_id}/activate",
    response_model=schemas.ScheduleGroup,
    tags=["schedules"],
)
def activate_schedule_group(
    group_id: str,
    payload: schemas.ScheduleGroupActivateRequest,
    request: Request,
) -> schemas.ScheduleGroup:
    schedule_repo = get_schedule_repository()
    active_flag = payload.active
    if active_flag is None:
        active_flag = payload.schedule_id is not None
    try:
        group = schedule_repo.set_group_active(group_id, active_flag)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule group not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_group_activated",
        subject_type="schedule_group",
        subject_id=group_id,
        actor=actor,
        reason=reason,
        metadata={
            "active": active_flag,
            "schedule_id": payload.schedule_id,
            "owner_key": group[0].owner_key,
        },
    )
    return _group_to_schema(group)


@router.get(
    "/session/whoami",
    response_model=schemas.WhoAmIResponse,
    tags=["session"],
)
def get_session_identity(request: Request) -> schemas.WhoAmIResponse:
    forwarded_header = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For", ""
    )
    forwarded_values = [
        value.strip()
        for value in forwarded_header.split(",")
        if value.strip()
    ]
    if not forwarded_values and forwarded_header.strip():
        forwarded_values = [forwarded_header.strip()]
    client_ip = forwarded_values[0] if forwarded_values else None
    if client_ip is None and request.client:
        client_ip = request.client.host

    try:
        clients = get_unregistered_client_records()
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    probable = []
    if client_ip:
        normalized = client_ip.strip().lower()
        probable = [
            schemas.UnregisteredClient(**client)
            for client in clients
            if isinstance(client.get("ip"), str) and client["ip"].strip().lower() == normalized
        ]

    if not forwarded_values and client_ip:
        forwarded_values = [client_ip]

    return schemas.WhoAmIResponse(
        ip=client_ip,
        forwarded_for=forwarded_values,
        probable_clients=probable,
    )


@router.get(
    "/device-types",
    response_model=schemas.DeviceTypesResponse,
    tags=["devices"],
)
def list_device_types_api() -> schemas.DeviceTypesResponse:
    return schemas.DeviceTypesResponse(types=list_device_types())


@router.post(
    "/device-types",
    response_model=schemas.DeviceTypesResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["devices"],
)
def create_device_type(
    payload: schemas.DeviceTypeCreateRequest,
    request: Request,
) -> schemas.DeviceTypesResponse:
    try:
        add_device_type(payload.name)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="device_type_created",
        subject_type="device_type",
        subject_id=payload.name.lower(),
        actor=actor,
        reason=reason,
    )
    return schemas.DeviceTypesResponse(types=list_device_types())


@router.delete(
    "/device-types/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["devices"],
)
def delete_device_type(name: str, request: Request) -> Response:
    if not remove_device_type(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Device type not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="device_type_deleted",
        subject_type="device_type",
        subject_id=name.lower(),
        actor=actor,
        reason=reason,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/disable",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def disable_schedule(schedule_id: str, request: Request) -> schemas.DeviceSchedule:
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.set_enabled(schedule_id, False)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    actor = _resolve_actor(request)
    reason = _resolve_reason(request)
    record_event(
        action="schedule_disabled",
        subject_type="schedule",
        subject_id=schedule.id,
        actor=actor,
        reason=reason,
        metadata={"owner_key": schedule.owner_key, "label": schedule.label},
    )
    return schedule


@router.get(
    "/owners/{owner_key}/schedules",
    response_model=schemas.OwnerScheduleResponse,
    tags=["schedules"],
)
def get_owner_schedules(owner_key: str) -> schemas.OwnerScheduleResponse:
    _require_owner(owner_key)
    schedule_repo = get_schedule_repository()
    owner_schedules, global_schedules = schedule_repo.list_for_owner(owner_key)
    metadata = schedule_repo.get_metadata()
    return schemas.OwnerScheduleResponse(
        metadata=metadata,
        owner_schedules=owner_schedules,
        global_schedules=global_schedules,
    )
