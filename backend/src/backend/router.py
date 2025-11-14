"""API router exposing the UniFi device management endpoints."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from . import schemas
from .device_types import add_device_type, list_device_types, remove_device_type
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
def create_owner(payload: schemas.OwnerCreateRequest) -> schemas.OwnerInfo:
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
    return schemas.OwnerInfo(key=owner.key, display_name=owner.display_name)


@router.delete(
    "/owners/{owner_key}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["owners"],
)
def delete_owner_entry(owner_key: str) -> Response:
    if owner_key.lower() in {"master"}:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Cannot delete the master owner.",
        )
    if not delete_owner(owner_key):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")
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
    owner_key: str, payload: schemas.DeviceRegistrationRequest
) -> schemas.DeviceStatus:
    _require_owner(owner_key)
    try:
        record = register_device_for_owner(
            owner_key,
            mac=payload.mac,
            name=payload.name,
            device_type=payload.type,
        )
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

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
def lock_devices(payload: schemas.DeviceActionRequest) -> schemas.DeviceActionResponse:
    devices = [build_device_from_target(target) for target in payload.targets]
    try:
        results = apply_lock_action(devices, unlock=payload.unlock)
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
) -> schemas.OwnerLockResponse:
    owner_key_lower = owner_key.lower()
    owner_repo = get_owner_repository()
    device_repo = get_device_repository()
    devices = device_repo.list_by_owner(owner_key_lower)
    if not devices and owner_repo.get(owner_key_lower) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Owner not found.")

    try:
        results = apply_lock_action(devices, unlock=payload.unlock)
    except UniFiAPIError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

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
) -> schemas.DeviceActionResponse:
    target = schemas.DeviceTarget(
        mac=payload.mac,
        name=payload.name,
        owner=payload.owner or "unregistered",
        type=payload.type or "unknown",
    )
    try:
        results = apply_lock_action(
            [build_device_from_target(target)], unlock=payload.unlock
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


@router.post(
    "/schedules",
    response_model=schemas.DeviceSchedule,
    status_code=status.HTTP_201_CREATED,
    tags=["schedules"],
)
def create_schedule(payload: schemas.ScheduleCreateRequest) -> schemas.DeviceSchedule:
    if payload.scope == "owner":
        if not payload.owner_key:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="ownerKey is required when scope is 'owner'.",
            )
        _require_owner(payload.owner_key)
    schedule_repo = get_schedule_repository()
    return schedule_repo.create(payload)


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
    schedule_id: str, payload: schemas.ScheduleUpdateRequest
) -> schemas.DeviceSchedule:
    if not payload.model_dump(exclude_unset=True):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="No fields provided for update."
        )
    if payload.owner_key:
        _require_owner(payload.owner_key)
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.update(schedule_id, payload)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    return schedule


@router.delete(
    "/schedules/{schedule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["schedules"],
)
def delete_schedule(schedule_id: str) -> Response:
    schedule_repo = get_schedule_repository()
    deleted = schedule_repo.delete(schedule_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/enable",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def enable_schedule(schedule_id: str) -> schemas.DeviceSchedule:
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.set_enabled(schedule_id, True)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
    return schedule


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
def create_device_type(payload: schemas.DeviceTypeCreateRequest) -> schemas.DeviceTypesResponse:
    try:
        add_device_type(payload.name)
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return schemas.DeviceTypesResponse(types=list_device_types())


@router.delete(
    "/device-types/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["devices"],
)
def delete_device_type(name: str) -> Response:
    if not remove_device_type(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Device type not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/schedules/{schedule_id}/disable",
    response_model=schemas.DeviceSchedule,
    tags=["schedules"],
)
def disable_schedule(schedule_id: str) -> schemas.DeviceSchedule:
    schedule_repo = get_schedule_repository()
    schedule = schedule_repo.set_enabled(schedule_id, False)
    if schedule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Schedule not found.")
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
