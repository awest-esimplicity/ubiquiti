"""Tests for the static device catalog."""

from __future__ import annotations

from backend.ubiquiti.devices import DEVICES, Device, devices_by_owner


def test_device_count_matches_inventory():
    assert len(DEVICES) == 28


def test_devices_are_dataclasses():
    first = DEVICES[0]
    assert isinstance(first, Device)
    assert first.name
    assert first.mac.count(":") == 5


def test_devices_by_owner_filters_case_insensitively():
    jayce_devices = list(devices_by_owner("JAYCE"))
    assert all(device.owner == "jayce" for device in jayce_devices)
    assert len(jayce_devices) == 6
