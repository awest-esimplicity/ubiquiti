"""Pydantic models for the UniFi FastAPI backend."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DeviceStatus(BaseModel):
    name: str
    owner: str
    type: str
    mac: str
    locked: bool
    vendor: str | None = None


class DeviceListResponse(BaseModel):
    devices: list[DeviceStatus]


class DeviceTrafficSample(BaseModel):
    timestamp: datetime
    rx_bytes: int = Field(..., ge=0)
    tx_bytes: int = Field(..., ge=0)
    total_bytes: int = Field(..., ge=0)


class DeviceTrafficSummary(BaseModel):
    interval_minutes: int = Field(..., ge=1)
    start: datetime | None = None
    end: datetime | None = None
    total_rx_bytes: int = Field(..., ge=0)
    total_tx_bytes: int = Field(..., ge=0)
    samples: list[DeviceTrafficSample] = Field(default_factory=list)


class DeviceDetail(BaseModel):
    name: str
    owner: str
    type: str
    mac: str
    locked: bool
    vendor: str | None = None
    ip: str | None = None
    last_seen: datetime | None = None
    connection: Literal["wired", "wireless", "unknown"] = "unknown"
    access_point: str | None = None
    signal: float | None = None
    online: bool = False
    network_name: str | None = None
    traffic: DeviceTrafficSummary | None = None
    destinations: list[str] = Field(default_factory=list)
    dpi_applications: list["DeviceDPIEntry"] = Field(default_factory=list)


class DeviceDPIEntry(BaseModel):
    application: str
    category: str | None = None
    rx_bytes: int = Field(..., ge=0)
    tx_bytes: int = Field(..., ge=0)


class DeviceRegistrationRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    mac: str = Field(..., min_length=1)
    actor: str | None = None
    reason: str | None = None


class DashboardSummary(BaseModel):
    total_devices: int = Field(..., ge=0)
    locked_devices: int = Field(..., ge=0)
    unlocked_devices: int = Field(..., ge=0)
    owner_count: int = Field(..., ge=0)
    unknown_vendors: int = Field(..., ge=0)
    generated_at: datetime


class OwnerSummary(BaseModel):
    key: str
    display_name: str
    total_devices: int
    locked_devices: int
    unlocked_devices: int


class OwnersResponse(BaseModel):
    owners: list[OwnerSummary]


class VerifyPinRequest(BaseModel):
    pin: str = Field(..., min_length=1, max_length=64)


class VerifyPinResponse(BaseModel):
    valid: bool


class DeviceTarget(BaseModel):
    mac: str = Field(..., min_length=1)
    name: str | None = None
    owner: str | None = None
    type: str | None = None


class DeviceActionRequest(BaseModel):
    targets: list[DeviceTarget] = Field(..., min_length=1)
    unlock: bool = False
    actor: str | None = None
    reason: str | None = None


class DeviceActionResult(BaseModel):
    mac: str
    locked: bool
    status: Literal["success", "skipped", "error"]
    message: str | None = None


class DeviceActionResponse(BaseModel):
    results: list[DeviceActionResult]


class OwnerLockRequest(BaseModel):
    unlock: bool = False
    actor: str | None = None
    reason: str | None = None


class OwnerLockResponse(BaseModel):
    owner: str
    processed: int
    results: list[DeviceActionResult]


class UnregisteredClient(BaseModel):
    name: str
    mac: str
    ip: str | None = None
    vendor: str | None = None
    last_seen: datetime | None = None
    locked: bool


class UnregisteredClientsResponse(BaseModel):
    clients: list[UnregisteredClient]


class SingleClientLockRequest(BaseModel):
    mac: str
    name: str | None = None
    owner: str | None = None
    type: str | None = None
    unlock: bool = False
    actor: str | None = None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Schedule models


def _to_camel(string: str) -> str:
    first, *rest = string.split("_")
    return first + "".join(word.capitalize() for word in rest)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class OwnerInfo(CamelModel):
    key: str
    display_name: str


class OwnerListResponse(CamelModel):
    owners: list[OwnerInfo]


class OwnerCreateRequest(CamelModel):
    display_name: str = Field(..., min_length=1, max_length=255)
    pin: str = Field(..., min_length=1, max_length=64)


class DeviceTypesResponse(CamelModel):
    types: list[str]


class DeviceTypeCreateRequest(CamelModel):
    name: str = Field(..., min_length=1, max_length=255)


class AuditEvent(BaseModel):
    id: int | None = None
    timestamp: datetime
    action: str
    actor: str | None = None
    subject_type: str
    subject_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EventListResponse(BaseModel):
    events: list[AuditEvent] = Field(default_factory=list)


class WhoAmIResponse(CamelModel):
    ip: str | None = None
    forwarded_for: list[str] = Field(default_factory=list)
    probable_clients: list[UnregisteredClient] = Field(default_factory=list)


class ScheduleWindow(CamelModel):
    start: datetime
    end: datetime


class ScheduleRecurrence(CamelModel):
    type: Literal["one_shot", "daily", "weekly", "monthly"]
    interval: int = Field(default=1)
    days_of_week: list[str] | None = Field(default=None, alias="daysOfWeek")
    day_of_month: int | None = Field(default=None, alias="dayOfMonth")
    until: datetime | None = None


class ScheduleException(CamelModel):
    date: date
    reason: str | None = None
    skip: bool | None = None
    override_window: ScheduleWindow | None = Field(
        default=None, alias="overrideWindow"
    )


class ScheduleTarget(CamelModel):
    devices: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class DeviceSchedule(CamelModel):
    id: str
    scope: Literal["owner", "global"]
    owner_key: str | None = Field(default=None, alias="ownerKey")
    label: str
    description: str | None = None
    targets: ScheduleTarget
    action: Literal["lock", "unlock"]
    end_action: Literal["lock", "unlock"] | None = Field(default=None, alias="endAction")
    window: ScheduleWindow
    recurrence: ScheduleRecurrence
    exceptions: list[ScheduleException] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ScheduleMetadata(CamelModel):
    timezone: str
    generated_at: datetime = Field(alias="generatedAt")


class ScheduleConfig(CamelModel):
    metadata: ScheduleMetadata
    schedules: list[DeviceSchedule]


class ScheduleCreateRequest(CamelModel):
    scope: Literal["owner", "global"]
    owner_key: str | None = Field(default=None, alias="ownerKey")
    label: str
    description: str | None = None
    targets: ScheduleTarget
    action: Literal["lock", "unlock"]
    end_action: Literal["lock", "unlock"] | None = Field(default=None, alias="endAction")
    window: ScheduleWindow
    recurrence: ScheduleRecurrence
    exceptions: list[ScheduleException] | None = None
    enabled: bool | None = True


class ScheduleUpdateRequest(CamelModel):
    scope: Literal["owner", "global"] | None = None
    owner_key: str | None = Field(default=None, alias="ownerKey")
    label: str | None = None
    description: str | None = None
    targets: ScheduleTarget | None = None
    action: Literal["lock", "unlock"] | None = None
    end_action: Literal["lock", "unlock"] | None = Field(default=None, alias="endAction")
    window: ScheduleWindow | None = None
    recurrence: ScheduleRecurrence | None = None
    exceptions: list[ScheduleException] | None = None
    enabled: bool | None = None


class ScheduleListResponse(CamelModel):
    metadata: ScheduleMetadata
    schedules: list[DeviceSchedule]


class OwnerScheduleResponse(CamelModel):
    metadata: ScheduleMetadata
    owner_schedules: list[DeviceSchedule] = Field(alias="ownerSchedules")
    global_schedules: list[DeviceSchedule] = Field(alias="globalSchedules")


class ScheduleCloneRequest(CamelModel):
    target_owner: str = Field(alias="targetOwner", min_length=1)


class ScheduleCloneResponse(CamelModel):
    schedule: DeviceSchedule


class OwnerScheduleCopyRequest(CamelModel):
    target_owner: str = Field(alias="targetOwner", min_length=1)
    mode: Literal["merge", "replace"] = "merge"


class OwnerScheduleCopyResponse(CamelModel):
    source_owner: str = Field(alias="sourceOwner")
    target_owner: str = Field(alias="targetOwner")
    mode: Literal["merge", "replace"]
    created: list[DeviceSchedule] = Field(default_factory=list)
    replaced_count: int = Field(default=0, alias="replacedCount")


__all__ = [
    "DeviceStatus",
    "DeviceListResponse",
    "DeviceTrafficSample",
    "DeviceTrafficSummary",
    "DeviceDetail",
    "DeviceDPIEntry",
    "DeviceRegistrationRequest",
    "DashboardSummary",
    "OwnerSummary",
    "OwnersResponse",
    "VerifyPinRequest",
    "VerifyPinResponse",
    "DeviceTarget",
    "DeviceActionRequest",
    "DeviceActionResult",
    "DeviceActionResponse",
    "OwnerLockRequest",
    "OwnerLockResponse",
    "UnregisteredClient",
    "UnregisteredClientsResponse",
    "SingleClientLockRequest",
    "ScheduleWindow",
    "ScheduleRecurrence",
    "ScheduleException",
    "ScheduleTarget",
    "DeviceSchedule",
    "ScheduleMetadata",
    "ScheduleConfig",
    "ScheduleCreateRequest",
    "ScheduleUpdateRequest",
    "ScheduleListResponse",
    "OwnerScheduleResponse",
    "AuditEvent",
    "EventListResponse",
]
