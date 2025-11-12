"""Service helpers backing the FastAPI endpoints."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, TypedDict

from .owners import get_owner_repository
from .ubiquiti.config import settings
from .ubiquiti.devices import Device, get_device_repository
from .ubiquiti.firewall import FirewallManager
from .ubiquiti.lock import DeviceLocker
from .ubiquiti.network import NetworkDeviceService
from .ubiquiti.unifi import UniFiAPIError, UniFiClient
from .ubiquiti.utils import lookup_mac_vendor, suppress_insecure_request_warning

if TYPE_CHECKING:
    from .schemas import DeviceTarget


class DeviceRecord(TypedDict):
    name: str
    owner: str
    type: str
    mac: str
    locked: bool
    vendor: str | None


class ClientRecord(TypedDict):
    name: str
    mac: str
    ip: str | None
    vendor: str | None
    last_seen: datetime | None
    locked: bool


class ActionResult(TypedDict):
    mac: str
    locked: bool
    status: Literal["success", "skipped", "error"]
    message: str | None


class OwnerSummaryRecord(TypedDict):
    key: str
    display_name: str
    total_devices: int
    locked_devices: int
    unlocked_devices: int


@contextmanager
def locker_context() -> Iterator[tuple[FirewallManager, DeviceLocker]]:
    """Yield a configured FirewallManager and DeviceLocker pair."""
    client = UniFiClient(
        settings.unifi_base_url,
        api_key=settings.unifi_api_key,
        verify_ssl=settings.verify_ssl,
    )
    suppress_insecure_request_warning(client.verify_ssl)
    firewall = FirewallManager(client)
    locker = DeviceLocker(firewall)
    try:
        yield firewall, locker
    finally:
        client.close()


def _timestamp_to_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        ts = float(value)
    elif isinstance(value, str):
        try:
            ts = float(value)
        except ValueError:
            return None
    else:
        return None
    try:
        return datetime.fromtimestamp(ts, tz=UTC).astimezone()
    except (OverflowError, OSError):
        return None


def get_registered_device_records() -> list[DeviceRecord]:
    """Return the current status of every registered device."""
    device_repo = get_device_repository()
    with locker_context() as (firewall, locker):
        rules = firewall.list_rules()
        records: list[DeviceRecord] = []
        for device in device_repo.list_all():
            locked = locker.is_device_locked(device, rules)
            vendor = lookup_mac_vendor(device.mac)
            records.append(
                {
                    "name": device.name,
                    "owner": device.owner,
                    "type": device.type,
                    "mac": device.mac,
                    "locked": locked,
                    "vendor": vendor,
                }
            )
        return records


def summarize_owner_records(records: list[DeviceRecord]) -> list[OwnerSummaryRecord]:
    """Aggregate device counts by owner."""
    owner_repo = get_owner_repository()
    grouped: dict[str, list[DeviceRecord]] = {}
    for record in records:
        grouped.setdefault(record["owner"], []).append(record)

    summaries: list[OwnerSummaryRecord] = []
    for owner_key in sorted(grouped):
        rows = grouped[owner_key]
        locked_count = sum(1 for row in rows if row["locked"])
        owner_entry = owner_repo.get(owner_key)
        display_name = (
            owner_entry.display_name if owner_entry is not None else owner_key.title()
        )
        summaries.append(
            {
                "key": owner_key,
                "display_name": display_name,
                "total_devices": len(rows),
                "locked_devices": locked_count,
                "unlocked_devices": len(rows) - locked_count,
            }
        )
    return summaries


def build_device_from_target(target: DeviceTarget) -> Device:
    """Return a Device dataclass instance for locking operations."""
    mac = target.mac.strip()
    device_repo = get_device_repository()
    registered = device_repo.get_by_mac(mac)
    if registered is not None:
        return registered

    name = target.name.strip() if target.name else mac
    owner = (target.owner or "unregistered").strip().lower()
    device_type = (target.type or "unknown").strip().lower()
    return Device(name=name, mac=mac, owner=owner, type=device_type)


def apply_lock_action(devices: Iterable[Device], *, unlock: bool) -> list[ActionResult]:
    """Lock or unlock the provided devices and return per-device results."""
    results: list[ActionResult] = []
    with locker_context() as (firewall, locker):
        rules = firewall.list_rules()
        for device in devices:
            try:
                locked_before = locker.is_device_locked(device, rules)
            except UniFiAPIError as exc:
                results.append(
                    {
                        "mac": device.mac,
                        "locked": False,
                        "status": "error",
                        "message": str(exc),
                    }
                )
                continue

            if unlock:
                if not locked_before:
                    results.append(
                        {
                            "mac": device.mac,
                            "locked": False,
                            "status": "skipped",
                            "message": "Device already unlocked.",
                        }
                    )
                    continue
                try:
                    locker.unlock_device(device)
                except UniFiAPIError as exc:
                    results.append(
                        {
                            "mac": device.mac,
                            "locked": locked_before,
                            "status": "error",
                            "message": str(exc),
                        }
                    )
                    continue
                rules = firewall.list_rules()
                locked_after = locker.is_device_locked(device, rules)
                results.append(
                    {
                        "mac": device.mac,
                        "locked": locked_after,
                        "status": "success",
                        "message": "Unlocked device.",
                    }
                )
            else:
                if locked_before:
                    results.append(
                        {
                            "mac": device.mac,
                            "locked": True,
                            "status": "skipped",
                            "message": "Device already locked.",
                        }
                    )
                    continue
                try:
                    locker.lock_device(device)
                except UniFiAPIError as exc:
                    results.append(
                        {
                            "mac": device.mac,
                            "locked": locked_before,
                            "status": "error",
                            "message": str(exc),
                        }
                    )
                    continue
                rules = firewall.list_rules()
                locked_after = locker.is_device_locked(device, rules)
                results.append(
                    {
                        "mac": device.mac,
                        "locked": locked_after,
                        "status": "success",
                        "message": "Locked device.",
                    }
                )
    return results


def get_unregistered_client_records() -> list[ClientRecord]:
    """Return active clients that are not registered in devices.py."""
    device_repo = get_device_repository()
    with locker_context() as (firewall, locker):
        service = NetworkDeviceService(firewall.client)
        clients = service.list_active_clients()
        rules = firewall.list_rules()
        records: list[ClientRecord] = []

        for client in clients:
            mac_value = client.get("mac")
            if not isinstance(mac_value, str):
                continue
            if device_repo.get_by_mac(mac_value):
                continue

            vendor = lookup_mac_vendor(mac_value)
            device = Device(
                name=client.get("hostname")
                or client.get("name")
                or mac_value,
                mac=mac_value,
                type="unknown",
                owner="unregistered",
            )
            locked = locker.is_device_locked(device, rules)
            records.append(
                {
                    "name": device.name,
                    "mac": mac_value,
                    "ip": client.get("ip") or client.get("network"),
                    "vendor": vendor,
                    "last_seen": _timestamp_to_datetime(client.get("last_seen")),
                    "locked": locked,
                }
            )

        records.sort(
            key=lambda item: item["last_seen"] or datetime.fromtimestamp(0, tz=UTC),
            reverse=True,
        )
        return records
