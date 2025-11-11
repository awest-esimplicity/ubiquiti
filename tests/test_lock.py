"""Tests for device locking helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from ubiquiti.devices import DEVICES, Device
from ubiquiti.lock import DEFAULT_RULESET, DeviceLocker, LockOptions


class DummyFirewall:
    def __init__(self, response: Mapping[str, Any] | None = None) -> None:
        self.created: list[Mapping[str, Any]] = []
        self.deleted: list[str] = []
        self.response = response
        self.rules: list[Mapping[str, Any]] = []
        self.wan_group_id = "wan-group"

    def create_rule(self, rule: Mapping[str, Any]) -> Mapping[str, Any]:
        self.created.append(rule)
        stored_rule = dict(rule)
        stored_rule.setdefault("_id", f"rule-{len(self.rules) + 1}")
        self.rules.append(stored_rule)
        if self.response is not None:
            return self.response
        return {"data": [stored_rule]}

    def list_rules(self) -> list[Mapping[str, Any]]:
        return list(self.rules)

    def delete_rule(self, rule_id: str) -> bool:
        self.deleted.append(rule_id)
        self.rules = [
            rule for rule in self.rules if str(rule.get("_id")) != str(rule_id)
        ]
        return True

    def get_wan_group_id(self) -> str | None:
        return self.wan_group_id


DEVICE = Device(
    name="Test Device",
    mac="aa:bb:cc:dd:ee:ff",
    type="computer",
    owner="user",
)


def test_build_rule_uses_defaults():
    locker = DeviceLocker(DummyFirewall())

    rule = locker.build_rule(DEVICE)

    assert rule["action"] == "drop"
    assert rule["ruleset"] == DEFAULT_RULESET
    assert rule["protocol"] == "all"
    assert rule["src_mac_address"] == DEVICE.mac
    assert rule["name"].startswith("Block ")
    assert "comments" in rule
    assert rule["dst_firewallgroup_ids"] == ["wan-group"]


def test_lock_device_invokes_firewall():
    firewall = DummyFirewall()
    locker = DeviceLocker(firewall, options=LockOptions(logging=True))

    response = locker.lock_device(DEVICE)

    assert response["data"][0]["_id"] == "rule-1"
    assert len(firewall.created) == 1
    created_rule = firewall.created[0]
    assert created_rule["logging"] is True
    assert created_rule["src_mac_address"] == DEVICE.mac
    assert created_rule["rule_index"] == 20000
    assert created_rule["dst_firewallgroup_ids"] == ["wan-group"]


def test_lock_devices_handles_multiple():
    firewall = DummyFirewall()
    locker = DeviceLocker(firewall)
    devices: Iterable[Device] = [
        DEVICE,
        Device("Another", "00:11:22:33:44:55", "phone", "user"),
    ]

    results = list(locker.lock_devices(devices))

    assert len(results) == 2
    assert len(firewall.created) == 2
    macs = [rule["src_mac_address"] for rule in firewall.created]
    assert macs == [DEVICE.mac, "00:11:22:33:44:55"]
    indexes = [rule["rule_index"] for rule in firewall.created]
    assert indexes == [20000, 20001]


def test_lock_owner_uses_devices_by_owner(monkeypatch):
    subset = [dev for dev in DEVICES if dev.owner == "jayce"][:2]

    def fake_devices_by_owner(owner: str):
        assert owner == "jayce"
        return subset

    monkeypatch.setattr("ubiquiti.lock.devices_by_owner", fake_devices_by_owner)

    firewall = DummyFirewall()
    locker = DeviceLocker(firewall)

    results = list(locker.lock_owner("jayce"))

    assert len(results) == len(subset)
    assert len(firewall.created) == len(subset)


def test_is_device_locked_detects_by_mac():
    firewall = DummyFirewall()
    locker = DeviceLocker(firewall)
    rules = [{"src_mac_address": DEVICE.mac}]

    assert locker.is_device_locked(DEVICE, rules) is True


def test_lock_device_respects_existing_rule_index():
    firewall = DummyFirewall()
    firewall.rules = [{"_id": "existing", "rule_index": 20050}]
    locker = DeviceLocker(firewall)

    locker.lock_device(DEVICE)

    assert firewall.created[0]["rule_index"] == 20051


def test_unlock_device_removes_matching_rules():
    firewall = DummyFirewall()
    locker = DeviceLocker(firewall)
    locker_rule_name = locker._rule_name(DEVICE)
    firewall.rules = [
        {"_id": "rule-1", "src_mac_address": DEVICE.mac, "name": locker_rule_name},
        {"_id": "rule-2", "src_mac_address": "00:11:22:33:44:55"},
    ]

    removed = locker.unlock_device(DEVICE)

    assert removed == 1
    assert firewall.deleted == ["rule-1"]
    assert all(rule["src_mac_address"] != DEVICE.mac for rule in firewall.rules)


def test_unlock_owner_uses_devices_by_owner(monkeypatch):
    firewall = DummyFirewall()
    locker = DeviceLocker(firewall)
    devices = [
        DEVICE,
        Device("Other Device", "00:11:22:33:44:55", "phone", "jayce"),
    ]
    firewall.rules = [
        {
            "_id": "rule-1",
            "src_mac_address": DEVICE.mac,
            "name": locker._rule_name(DEVICE),
        },
        {
            "_id": "rule-2",
            "src_mac_address": "00:11:22:33:44:55",
            "name": locker._rule_name(devices[1]),
        },
    ]

    monkeypatch.setattr("ubiquiti.lock.devices_by_owner", lambda owner: devices)

    removed = locker.unlock_owner("jayce")

    assert removed == 2
    assert set(firewall.deleted) == {"rule-1", "rule-2"}
