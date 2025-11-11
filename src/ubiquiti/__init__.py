"""Public package interface for the UniFi helper library."""

from __future__ import annotations

from .cli import (
    list_active_devices,
    list_devices,
    list_non_registered_active_devices,
)
from .cli import (
    main as _cli_main,
)
from .cli import (
    run as run_cli,
)
from .config import Settings, settings
from .devices import DEVICES, Device, devices_by_owner
from .firewall import FirewallManager
from .lock import DEFAULT_RULESET, DeviceLocker, LockOptions
from .unifi import UniFiAPIError, UniFiClient
from .utils import suppress_insecure_request_warning

__all__ = [
    "Settings",
    "UniFiAPIError",
    "UniFiClient",
    "Device",
    "DEVICES",
    "devices_by_owner",
    "FirewallManager",
    "DeviceLocker",
    "LockOptions",
    "DEFAULT_RULESET",
    "run_cli",
    "list_devices",
    "list_active_devices",
    "list_non_registered_active_devices",
    "suppress_insecure_request_warning",
    "settings",
    "main",
]


def main(argv: None | list[str] = None) -> None:
    """Entrypoint for the command-line interface."""
    _cli_main(argv)
