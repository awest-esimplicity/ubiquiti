"""API router exposing the UniFi device management endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from . import schemas
from .owners import get_owner_repository
from .services import (
    DeviceRecord,
    apply_lock_action,
    build_device_from_target,
    get_registered_device_records,
    get_unregistered_client_records,
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
