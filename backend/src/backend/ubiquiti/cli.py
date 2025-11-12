"""Command-line helpers for device, client, and firewall management."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from datetime import UTC, datetime

from .config import settings
from .devices import Device, get_device_repository
from .firewall import FirewallManager
from .lock import DeviceLocker
from .network import NetworkDeviceService
from .unifi import UniFiAPIError, UniFiClient
from .utils import (
    configure_logging,
    logger,
    lookup_mac_vendor,
    suppress_insecure_request_warning,
)

configure_logging()


def _format_status(device: Device, locked: bool) -> str:
    state = "LOCKED" if locked else "UNLOCKED"
    return f" - {device.name}: {state}"


def _format_timestamp(timestamp: float | int | None) -> str:
    if not timestamp:
        return "unknown"
    try:
        dt = datetime.fromtimestamp(float(timestamp), tz=UTC).astimezone()
    except (ValueError, OSError):
        return "unknown"
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def _create_client() -> UniFiClient:
    return UniFiClient(
        settings.unifi_base_url,
        api_key=settings.unifi_api_key,
        verify_ssl=settings.verify_ssl,
    )


def run(
    owner: str | None = None,
    *,
    unlock: bool = False,
    input_fn=input,
    print_fn=print,
) -> None:
    """Prompt for an owner, display device status, then apply locks."""
    if owner is None:
        owner = input_fn("Enter owner: ").strip()

    if not owner:
        logger.error("No owner provided for lock operation")
        raise SystemExit("Owner is required.")

    action = "unlock" if unlock else "lock"
    logger.bind(owner=owner, action=action).info("Starting {} flow", action)

    client = _create_client()
    manager = FirewallManager(client)
    locker = DeviceLocker(manager)

    suppress_insecure_request_warning(client.verify_ssl)

    try:
        device_repo = get_device_repository()
        devices = device_repo.list_by_owner(owner)
        if not devices:
            logger.bind(owner=owner).warning("No devices found to process")
            print_fn(f"No devices found for owner '{owner}'.")
            return

        print_fn(f"Found {len(devices)} device(s) for '{owner}':")
        logger.bind(owner=owner, device_count=len(devices)).info(
            "Loaded devices for owner"
        )
        existing_rules = manager.list_rules()
        for device in devices:
            print_fn(
                _format_status(
                    device,
                    locker.is_device_locked(device, existing_rules),
                )
            )

        if unlock:
            print_fn("Unlocking devices...")
            removed = locker.unlock_devices(devices)
            logger.bind(owner=owner, removed=removed).info("Unlock operation complete")
            if removed == 0:
                print_fn("No existing lock rules were found.")
                logger.bind(owner=owner).warning("No lock rules found to remove")
        else:
            print_fn("Locking devices...")
            for _ in locker.lock_devices(devices):
                pass
            logger.bind(owner=owner).info("Lock operation complete")

        updated_rules = manager.list_rules()
        print_fn("Updated status:")
        for device in devices:
            print_fn(
                _format_status(
                    device,
                    locker.is_device_locked(device, updated_rules),
                )
            )
    except UniFiAPIError as exc:
        logger.exception("UniFi API error encountered during {} flow", action)
        raise SystemExit(f"UniFi API error: {exc}") from exc
    finally:
        logger.bind(owner=owner, action=action).debug("Closing UniFi client session")
        client.close()
        logger.bind(owner=owner, action=action).info("Finished {} flow", action)


def _dump_json(data: object, *, print_fn=print) -> None:
    formatted = json.dumps(data, indent=2, sort_keys=True, default=str)
    print_fn(formatted)


def list_devices(*, print_fn=print) -> None:
    """List all UniFi network devices."""
    client = _create_client()
    service = NetworkDeviceService(client)

    try:
        devices = service.list_devices()
        if not devices:
            print_fn("No UniFi devices found.")
            logger.warning("No UniFi devices returned by controller")
            return

        _dump_json(
            {
                "total": len(devices),
                "devices": [
                    {
                        "name": d.get("name") or d.get("hostname") or "Unknown device",
                        "model": d.get("model") or d.get("type"),
                        "mac": d.get("mac") or d.get("device_id"),
                        "ip": d.get("ip") or d.get("lan_ip"),
                        "status": d.get("state"),
                    }
                    for d in devices
                ],
            },
            print_fn=print_fn,
        )
    except UniFiAPIError as exc:
        logger.exception("Failed to list UniFi devices")
        raise SystemExit(f"UniFi API error: {exc}") from exc
    finally:
        client.close()


def list_active_devices(*, print_fn=print) -> None:
    """List all active client devices with their last seen timestamp."""
    client = _create_client()
    service = NetworkDeviceService(client)

    try:
        clients = service.list_active_clients()
        if not clients:
            print_fn("No active client devices found.")
            logger.info("No active client devices returned by controller")
            return

        clients = sorted(clients, key=lambda c: c.get("last_seen", 0), reverse=True)
        _dump_json(
            {
                "total": len(clients),
                "clients": [_format_client_record(ci) for ci in clients],
            },
            print_fn=print_fn,
        )
    except UniFiAPIError as exc:
        logger.exception("Failed to list active client devices")
        raise SystemExit(f"UniFi API error: {exc}") from exc
    finally:
        client.close()


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Manage UniFi devices, clients, and firewall rules."
    )
    parser.add_argument(
        "-o",
        "--owner",
        help="Owner whose devices should be locked. Prompts if omitted.",
    )
    parser.add_argument(
        "--unlock",
        action="store_true",
        help="Remove lock rules instead of creating them.",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List all devices managed by the UniFi controller.",
    )
    parser.add_argument(
        "--list-active",
        action="store_true",
        help="List currently active client devices with last seen time.",
    )
    parser.add_argument(
        "--list-non-registered-active",
        action="store_true",
        help="List active client devices not registered in devices.py.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.list_devices:
        list_devices(print_fn=print)
        return
    if args.list_active:
        list_active_devices(print_fn=print)
        return
    if args.list_non_registered_active:
        list_non_registered_active_devices(print_fn=print)
        return
    run(args.owner, unlock=args.unlock)


def _format_client_record(client_info: dict[str, object]) -> dict[str, object]:
    mac = client_info.get("mac")
    device_repo = get_device_repository()
    registered = bool(device_repo.get_by_mac(mac if isinstance(mac, str) else None))
    mac_value = mac if isinstance(mac, str) else None
    matched_device = device_repo.get_by_mac(mac_value)
    vendor = lookup_mac_vendor(mac_value)
    raw_last_seen = client_info.get("last_seen")
    if isinstance(raw_last_seen, (int, float)):
        last_seen_value: float | int | None = raw_last_seen
    elif isinstance(raw_last_seen, str):
        try:
            last_seen_value = float(raw_last_seen)
        except ValueError:
            last_seen_value = None
    else:
        last_seen_value = None
    record: dict[str, object] = {
        "name": client_info.get("hostname")
        or client_info.get("name")
        or client_info.get("mac")
        or "Unknown client",
        "mac": mac_value,
        "ip": client_info.get("ip") or client_info.get("network"),
        "last_seen": _format_timestamp(last_seen_value),
        "access_point": client_info.get("ap_mac") or client_info.get("assoc_wlan"),
        "registered": registered,
    }
    if vendor:
        record["vendor"] = vendor
    if matched_device:
        record["registered_device"] = {
            "name": matched_device.name,
            "owner": matched_device.owner,
            "type": matched_device.type,
        }
    return record


def list_non_registered_active_devices(*, print_fn=print) -> None:
    """List only active clients that are not registered in devices.py."""
    client = _create_client()
    service = NetworkDeviceService(client)

    try:
        clients = service.list_active_clients()
        device_repo = get_device_repository()
        unknown_clients = [
            ci for ci in clients if not device_repo.get_by_mac(ci.get("mac"))
        ]
        if not unknown_clients:
            print_fn("No non-registered active client devices found.")
            logger.info("All active clients are registered")
            return
        unknown_clients = sorted(
            unknown_clients, key=lambda c: c.get("last_seen", 0), reverse=True
        )
        _dump_json(
            {
                "total": len(unknown_clients),
                "clients": [_format_client_record(ci) for ci in unknown_clients],
            },
            print_fn=print_fn,
        )
    except UniFiAPIError as exc:
        logger.exception("Failed to list non-registered active clients")
        raise SystemExit(f"UniFi API error: {exc}") from exc
    finally:
        client.close()


__all__ = [
    "run",
    "main",
    "list_devices",
    "list_active_devices",
    "list_non_registered_active_devices",
]
