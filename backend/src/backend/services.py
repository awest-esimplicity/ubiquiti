"""Service helpers backing the FastAPI endpoints."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from .owners import get_owner_repository
from .ubiquiti.config import settings
from .ubiquiti.devices import Device, get_device_repository
from .ubiquiti.firewall import FirewallManager
from .ubiquiti.lock import DeviceLocker
from .ubiquiti.network import NetworkDeviceService
from .ubiquiti.unifi import UniFiAPIError, UniFiClient
from .ubiquiti.utils import (
    logger,
    lookup_mac_vendor,
    suppress_insecure_request_warning,
)

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


class DeviceTrafficSample(TypedDict):
    timestamp: datetime
    rx_bytes: int
    tx_bytes: int
    total_bytes: int


class DeviceTrafficSummary(TypedDict):
    interval_minutes: int
    start: datetime | None
    end: datetime | None
    total_rx_bytes: int
    total_tx_bytes: int
    samples: list[DeviceTrafficSample]


class DeviceDetailRecord(TypedDict):
    name: str
    owner: str
    type: str
    mac: str
    locked: bool
    vendor: str | None
    ip: str | None
    last_seen: datetime | None
    connection: Literal["wired", "wireless", "unknown"]
    access_point: str | None
    signal: float | None
    online: bool
    network_name: str | None
    traffic: DeviceTrafficSummary | None
    destinations: list[str]


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
    if ts > 10**11:  # values returned in milliseconds
        ts /= 1000.0
    try:
        return datetime.fromtimestamp(ts, tz=UTC).astimezone()
    except (OverflowError, OSError):
        return None


def _safe_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def _safe_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _extract_string(payload: Mapping[str, Any] | None, key: str) -> str | None:
    if not payload:
        return None
    value = payload.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _infer_connection_type(payload: Mapping[str, Any] | None) -> Literal["wired", "wireless", "unknown"]:
    if not payload:
        return "unknown"
    is_wired = payload.get("is_wired")
    if isinstance(is_wired, bool):
        return "wired" if is_wired else "wireless"
    wired = payload.get("wired")
    if isinstance(wired, bool):
        return "wired" if wired else "wireless"
    radio = _extract_string(payload, "radio")
    if radio:
        return "wireless"
    return "unknown"


def _build_traffic_summary(
    entries: list[Mapping[str, Any]], lookback_minutes: int
) -> DeviceTrafficSummary | None:
    samples: list[DeviceTrafficSample] = []
    total_rx = 0
    total_tx = 0
    start_dt: datetime | None = None
    end_dt: datetime | None = None

    for entry in entries:
        timestamp = _timestamp_to_datetime(entry.get("time"))
        if timestamp is None:
            continue
        rx_value = max(_safe_int(entry.get("rx_bytes")), 0)
        tx_value = max(_safe_int(entry.get("tx_bytes")), 0)
        total_rx += rx_value
        total_tx += tx_value
        start_dt = timestamp if start_dt is None or timestamp < start_dt else start_dt
        end_dt = timestamp if end_dt is None or timestamp > end_dt else end_dt
        samples.append(
            {
                "timestamp": timestamp,
                "rx_bytes": rx_value,
                "tx_bytes": tx_value,
                "total_bytes": rx_value + tx_value,
            }
        )

    if not samples:
        return None

    samples.sort(key=lambda item: item["timestamp"])
    return {
        "interval_minutes": lookback_minutes,
        "start": start_dt,
        "end": end_dt,
        "total_rx_bytes": total_rx,
        "total_tx_bytes": total_tx,
        "samples": samples,
    }


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


def register_device_for_owner(
    owner_key: str,
    *,
    mac: str,
    name: str | None = None,
    device_type: str | None = None,
) -> DeviceRecord:
    """Register or update a device under the specified owner."""
    device_repo = get_device_repository()
    existing = device_repo.get_by_mac(mac)

    mac_normalized = mac.strip().lower()
    owner_normalized = owner_key.strip().lower()

    name_value = (name or (existing.name if existing else None) or mac_normalized).strip()
    type_value = (
        device_type
        or (existing.type if existing else None)
        or "unknown"
    ).strip()
    if not type_value:
        type_value = "unknown"

    device = Device(
        name=name_value,
        mac=mac_normalized,
        type=type_value.lower(),
        owner=owner_normalized,
    )
    saved = device_repo.register(device)

    with locker_context() as (firewall, locker):
        rules = firewall.list_rules()
        locked = locker.is_device_locked(saved, rules)

    vendor = lookup_mac_vendor(saved.mac)
    return {
        "name": saved.name,
        "owner": saved.owner,
        "type": saved.type,
        "mac": saved.mac,
        "locked": locked,
        "vendor": vendor,
    }


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


def get_device_detail_record(
    mac: str,
    *,
    lookback_minutes: int = 60,
) -> DeviceDetailRecord:
    """Return enriched metadata for a registered device."""
    mac_normalized = (mac or "").strip().lower()
    if not mac_normalized:
        raise KeyError("MAC address must be provided.")

    lookback = max(5, int(lookback_minutes))
    device_repo = get_device_repository()
    device = device_repo.get_by_mac(mac_normalized)
    if device is None:
        raise KeyError(mac_normalized)

    vendor = lookup_mac_vendor(mac_normalized)

    with locker_context() as (firewall, locker):
        rules = firewall.list_rules()
        locked = locker.is_device_locked(device, rules)
        service = NetworkDeviceService(firewall.client)

        detail_info: Mapping[str, Any] | None = None
        active_info: Mapping[str, Any] | None = None

        try:
            detail_info = service.get_client_detail(mac_normalized)
        except UniFiAPIError as exc:
            logger.warning("Failed to fetch UniFi detail for {}: {}", mac_normalized, exc)

        if detail_info:
            # If the device is currently active the detail payload often contains live stats.
            active_info = detail_info if detail_info.get("is_wired") is not None else None

        if active_info is None:
            try:
                active_clients = service.list_active_clients()
            except UniFiAPIError as exc:
                logger.warning(
                    "Failed to enumerate active clients for {}: {}", mac_normalized, exc
                )
                active_clients = []

            for entry in active_clients:
                entry_mac = entry.get("mac")
                if isinstance(entry_mac, str) and entry_mac.lower() == mac_normalized:
                    active_info = entry
                    break

        merged_info: Mapping[str, Any] | None = active_info or detail_info
        online = active_info is not None
        ip_address = (
            _extract_string(merged_info, "ip")
            or _extract_string(merged_info, "fixed_ip")
            or _extract_string(merged_info, "network")
        )
        last_seen = _timestamp_to_datetime(
            (merged_info or detail_info or {}).get("last_seen")
        )
        signal = _safe_float((merged_info or detail_info or {}).get("signal"))
        access_point = _extract_string(merged_info or detail_info, "ap_mac") or _extract_string(
            merged_info or detail_info, "sw_mac"
        )
        connection = _infer_connection_type(merged_info or detail_info)
        network_name = (
            _extract_string(merged_info or detail_info, "hostname")
            or _extract_string(merged_info or detail_info, "name")
        )

        now_dt = datetime.now(tz=UTC).astimezone()
        start_dt = now_dt - timedelta(minutes=lookback)
        traffic_summary: DeviceTrafficSummary | None = None
        try:
            traffic_entries = service.get_client_traffic(
                mac_normalized,
                start=start_dt,
                end=now_dt,
                resolution="5minutes",
                attrs=("rx_bytes", "tx_bytes"),
            )
        except UniFiAPIError as exc:
            logger.warning(
                "Failed to fetch UniFi traffic samples for {}: {}", mac_normalized, exc
            )
            traffic_entries = []

        if traffic_entries:
            traffic_summary = _build_traffic_summary(traffic_entries, lookback)

        destinations: list[str] = []
        destination_candidates: list[str] = []
        for payload in (merged_info, detail_info):
            if isinstance(payload, Mapping):
                destination_candidates.extend(
                    [
                        payload.get("essid"),
                        payload.get("ap_name"),
                        payload.get("ap_mac"),
                        payload.get("network"),
                        payload.get("sw_name"),
                        payload.get("sw_mac"),
                        payload.get("gw_name"),
                        payload.get("gw_mac"),
                        payload.get("site_name"),
                    ]
                )
        for value in destination_candidates:
            if isinstance(value, str):
                normalized = value.strip()
                if normalized and normalized.lower() not in {item.lower() for item in destinations}:
                    destinations.append(normalized)
        if access_point and access_point not in destinations:
            destinations.append(access_point)

    return {
        "name": device.name,
        "owner": device.owner,
        "type": device.type,
        "mac": device.mac,
        "locked": locked,
        "vendor": vendor,
        "ip": ip_address,
        "last_seen": last_seen,
        "connection": connection,
        "access_point": access_point,
        "signal": signal,
        "online": online,
        "network_name": network_name,
        "traffic": traffic_summary,
        "destinations": destinations,
    }
