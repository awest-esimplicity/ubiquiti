"""Tests for the command-line interface."""

from __future__ import annotations

import json

import pytest

from backend.ubiquiti import run_cli
from backend.ubiquiti.cli import (
    list_active_devices,
    list_devices,
    list_non_registered_active_devices,
)
from backend.ubiquiti.cli import main as cli_main
from backend.ubiquiti.devices import Device


class StubDeviceRepository:
    def __init__(self, devices: list[Device]):
        self._devices = list(devices)
        self._by_mac = {device.mac.lower(): device for device in self._devices}

    def list_all(self) -> list[Device]:
        return list(self._devices)

    def list_by_owner(self, owner: str) -> list[Device]:
        owner_key = owner.lower()
        return [device for device in self._devices if device.owner == owner_key]

    def get_by_mac(self, mac: str | None) -> Device | None:
        if not mac:
            return None
        return self._by_mac.get(mac.lower())


class DummyClient:
    def __init__(
        self, base_url: str, *, api_key: str, verify_ssl: bool, **_: object
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.closed = False

    def close(self) -> None:
        self.closed = True


class DummyFirewallManager:
    initial_rules: list[dict] = []

    def __init__(self, client, site: str = "default") -> None:
        self.client = client
        self.site = site
        self.rules: list[dict] = [dict(rule) for rule in self.initial_rules]
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.wan_group_id = "wan-group"

    def list_rules(self):
        return list(self.rules)

    def create_rule(self, rule):
        self.created.append(rule)
        stored = dict(rule)
        stored.setdefault("_id", f"rule-{len(self.rules) + 1}")
        self.rules.append(stored)
        return {"data": [stored]}

    def delete_rule(self, rule_id: str):
        self.deleted.append(rule_id)
        self.rules = [rule for rule in self.rules if rule.get("_id") != rule_id]
        return True

    def get_wan_group_id(self):
        return self.wan_group_id


def test_cli_locks_devices(monkeypatch, capsys):
    devices = [
        Device(name="Device A", mac="00:11:22:33:44:55", type="phone", owner="jayce"),
        Device(name="Device B", mac="66:77:88:99:aa:bb", type="tablet", owner="jayce"),
    ]

    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository(devices),
    )
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    monkeypatch.setattr("backend.ubiquiti.cli.FirewallManager", DummyFirewallManager)

    DummyFirewallManager.initial_rules = []
    run_cli("jayce")
    captured = capsys.readouterr().out.splitlines()

    assert "Found 2 device(s) for 'jayce':" in captured[0]
    assert any("Device A" in line and "UNLOCKED" in line for line in captured)
    assert any("Device A" in line and "LOCKED" in line for line in captured)


def test_cli_requires_owner(monkeypatch):
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    monkeypatch.setattr("backend.ubiquiti.cli.FirewallManager", DummyFirewallManager)
    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository([]),
    )

    DummyFirewallManager.initial_rules = []
    with pytest.raises(SystemExit):
        run_cli(owner="")


def test_cli_handles_missing_devices(monkeypatch, capsys):
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    monkeypatch.setattr("backend.ubiquiti.cli.FirewallManager", DummyFirewallManager)
    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository([]),
    )

    DummyFirewallManager.initial_rules = []
    run_cli("nobody")
    captured = capsys.readouterr().out
    assert "No devices found for owner 'nobody'." in captured


def test_cli_unlocks_devices(monkeypatch, capsys):
    devices = [
        Device(name="Device A", mac="00:11:22:33:44:55", type="phone", owner="jayce"),
        Device(name="Device B", mac="66:77:88:99:aa:bb", type="tablet", owner="jayce"),
    ]

    initial_rules = [
        {
            "_id": "rule-1",
            "src_mac_address": "00:11:22:33:44:55",
            "name": "Block Device A",
        },
        {
            "_id": "rule-2",
            "src_mac_address": "66:77:88:99:aa:bb",
            "name": "Block Device B",
        },
    ]

    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository(devices),
    )
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    monkeypatch.setattr("backend.ubiquiti.cli.FirewallManager", DummyFirewallManager)

    DummyFirewallManager.initial_rules = initial_rules
    run_cli("jayce", unlock=True)
    captured = capsys.readouterr().out.splitlines()

    initial_status = []
    final_status = []
    section = "initial"
    for line in captured:
        if line.startswith("Unlocking devices..."):
            section = "action"
        elif line.startswith("Updated status:"):
            section = "final"
        elif line.startswith(" - "):
            if section == "initial":
                initial_status.append(line)
            elif section == "final":
                final_status.append(line)

    assert all("LOCKED" in line for line in initial_status)
    assert all("UNLOCKED" in line for line in final_status)
    DummyFirewallManager.initial_rules = []


class DummyNetworkService:
    def __init__(self, _client, *, site: str = "default") -> None:
        self.client = _client
        self.site = site
        self.devices: list[dict] = []
        self.clients: list[dict] = []

    def list_devices(self):
        return list(self.devices)

    def list_active_clients(self):
        return list(self.clients)


def test_cli_list_devices(monkeypatch, capsys):
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    service = DummyNetworkService(None)
    service.devices = [
        {"name": "Switch-1", "model": "USW-24", "mac": "aa:bb:cc", "ip": "10.0.0.2"},
        {"hostname": "AP-LR", "type": "uap", "mac": "dd:ee:ff", "state": "connected"},
    ]
    monkeypatch.setattr(
        "backend.ubiquiti.cli.NetworkDeviceService",
        lambda client: service,
    )

    list_devices(print_fn=print)
    output = capsys.readouterr().out.strip()
    data = json.loads(output)
    assert data["total"] == 2
    names = {d["name"] for d in data["devices"]}
    assert {"Switch-1", "AP-LR"} <= names


def test_cli_list_active_devices(monkeypatch, capsys):
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    service = DummyNetworkService(None)
    service.clients = [
        {
            "hostname": "Laptop",
            "mac": "11:22:33",
            "ip": "10.0.0.10",
            "last_seen": 1_700_000_000,
            "ap_mac": "aa:bb:cc",
        },
        {
            "name": "Phone",
            "mac": "44:55:66",
            "ip": "10.0.0.11",
            "last_seen": 1_699_999_999,
        },
    ]
    monkeypatch.setattr(
        "backend.ubiquiti.cli.NetworkDeviceService",
        lambda client: service,
    )
    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository(
            [Device("Laptop", "11:22:33", "computer", "owner")]
        ),
    )
    monkeypatch.setattr(
        "backend.ubiquiti.cli.lookup_mac_vendor",
        lambda mac: "VendorOne" if mac == "11:22:33" else None,
    )

    list_active_devices(print_fn=print)
    output = capsys.readouterr().out.strip()
    data = json.loads(output)
    assert data["total"] == 2
    names = [c["name"] for c in data["clients"]]
    assert names[0] == "Laptop"
    assert data["clients"][0]["registered"] is True
    assert data["clients"][1]["registered"] is False
    assert data["clients"][0]["vendor"] == "VendorOne"


def test_cli_main_list_devices(monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.ubiquiti.cli.list_devices",
        lambda print_fn=print: print_fn(json.dumps({"devices": []})),
    )
    cli_main(["--list-devices"])
    assert "devices" in capsys.readouterr().out


def test_cli_main_list_active(monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.ubiquiti.cli.list_active_devices",
        lambda print_fn=print: print_fn(json.dumps({"clients": []})),
    )
    cli_main(["--list-active"])
    assert "clients" in capsys.readouterr().out


def test_cli_main_list_non_registered(monkeypatch, capsys):
    monkeypatch.setattr(
        "backend.ubiquiti.cli.list_non_registered_active_devices",
        lambda print_fn=print: print_fn(json.dumps({"clients": []})),
    )
    cli_main(["--list-non-registered-active"])
    assert "clients" in capsys.readouterr().out


def test_cli_list_non_registered_active(monkeypatch, capsys):
    monkeypatch.setattr("backend.ubiquiti.cli.UniFiClient", DummyClient)
    service = DummyNetworkService(None)
    service.clients = [
        {
            "name": "Unknown",
            "mac": "77:88:99",
            "last_seen": 1_700_000_000,
        },
        {
            "name": "Registered",
            "mac": "aa:bb:cc",
            "last_seen": 1_700_000_100,
        },
    ]
    monkeypatch.setattr(
        "backend.ubiquiti.cli.NetworkDeviceService",
        lambda client: service,
    )
    monkeypatch.setattr(
        "backend.ubiquiti.cli.get_device_repository",
        lambda: StubDeviceRepository(
            [Device("Registered", "aa:bb:cc", "computer", "owner")]
        ),
    )
    monkeypatch.setattr(
        "backend.ubiquiti.cli.lookup_mac_vendor",
        lambda mac: "VendorUnknown" if mac == "77:88:99" else "VendorKnown",
    )

    list_non_registered_active_devices(print_fn=print)
    output = capsys.readouterr().out.strip()
    data = json.loads(output)
    assert data["total"] == 1
    assert data["clients"][0]["mac"] == "77:88:99"
    assert data["clients"][0]["vendor"] == "VendorUnknown"
