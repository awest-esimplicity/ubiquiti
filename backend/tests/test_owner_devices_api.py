from __future__ import annotations

import os
from contextlib import contextmanager

from fastapi.testclient import TestClient

# Ensure all API tests run against the in-memory repositories.
os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402
from backend.ubiquiti.devices import Device, InMemoryDeviceRepository  # noqa: E402


client = TestClient(app)


@contextmanager
def _fake_locker_context():
    class FakeFirewall:
        def list_rules(self) -> list[str]:
            return []

    class FakeLocker:
        def is_device_locked(self, device: Device, rules: list[str]) -> bool:
            return False

    yield FakeFirewall(), FakeLocker()


def test_register_owner_device_creates_and_updates(monkeypatch):
    repo = InMemoryDeviceRepository([])
    monkeypatch.setattr("backend.services.get_device_repository", lambda: repo)
    monkeypatch.setattr("backend.services.lookup_mac_vendor", lambda mac: "Acme Networks")
    monkeypatch.setattr("backend.services.locker_context", _fake_locker_context)

    payload = {
        "mac": "AA:BB:CC:DD:EE:FF",
        "name": "Gaming Laptop",
        "type": "Computer",
    }
    create_response = client.post("/api/owners/kade/devices", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner"] == "kade"
    assert created["locked"] is False
    assert created["vendor"] == "Acme Networks"
    stored = repo.get_by_mac(payload["mac"])
    assert stored is not None
    assert stored.owner == "kade"
    assert stored.type == "computer"

    # Re-register with a different owner while omitting optional fields.
    update_response = client.post("/api/owners/house/devices", json={"mac": payload["mac"]})
    assert update_response.status_code == 201
    updated = update_response.json()
    assert updated["owner"] == "house"
    assert updated["name"] == "Gaming Laptop"
    assert updated["type"] == "computer"
    assert repo.list_by_owner("house")[0].name == "Gaming Laptop"
    assert repo.list_by_owner("kade") == []


def test_register_owner_device_missing_owner_returns_404(monkeypatch):
    repo = InMemoryDeviceRepository([])
    monkeypatch.setattr("backend.services.get_device_repository", lambda: repo)
    monkeypatch.setattr("backend.services.lookup_mac_vendor", lambda mac: None)
    monkeypatch.setattr("backend.services.locker_context", _fake_locker_context)

    response = client.post("/api/owners/unknown-owner/devices", json={"mac": "00:11:22:33:44:55"})
    assert response.status_code == 404
