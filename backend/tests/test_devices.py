"""Tests for the static device catalog."""

from __future__ import annotations

from backend.ubiquiti.devices import (
    DEVICES,
    Device,
    InMemoryDeviceRepository,
    devices_by_owner,
)


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


def test_in_memory_repository_registers_new_device():
    repo = InMemoryDeviceRepository([])
    device = Device(
        name="Living Room Console",
        mac="AA:BB:CC:DD:EE:FF",
        type="Console",
        owner="House",
    )
    saved = repo.register(device)

    assert saved.mac == "aa:bb:cc:dd:ee:ff"
    assert saved.owner == "house"
    assert saved.type == "console"
    assert repo.get_by_mac("aa:bb:cc:dd:ee:ff") == saved
    assert repo.list_by_owner("house") == [saved]


def test_in_memory_repository_updates_existing_device_owner():
    repo = InMemoryDeviceRepository([])
    mac = "11:22:33:44:55:66"
    original = Device(name="Tablet", mac=mac, type="tablet", owner="kade")
    repo.register(original)

    updated = repo.register(
        Device(name="Shared Tablet", mac=mac.upper(), type="Tablet", owner="Jayce")
    )

    assert updated.owner == "jayce"
    assert updated.name == "Shared Tablet"
    assert repo.get_by_mac(mac).owner == "jayce"
    assert repo.list_by_owner("jayce") == [updated]
    assert repo.list_by_owner("kade") == []
