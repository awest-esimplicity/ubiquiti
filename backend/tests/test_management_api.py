from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402
from backend.owners import InMemoryOwnerRepository, Owner  # noqa: E402
from backend.device_types import (  # type: ignore[attr-defined]  # noqa: E402
    _DEVICE_TYPES_LOCK,
    _DEVICE_TYPES,
)
from backend import events  # noqa: E402


client = TestClient(app)


def test_create_owner_and_list(monkeypatch):
    repository = InMemoryOwnerRepository([])
    monkeypatch.setattr("backend.router.get_owner_repository", lambda: repository)
    monkeypatch.setattr("backend.owners.get_owner_repository", lambda: repository)

    response = client.post(
        "/api/owners",
        json={"displayName": "New Owner", "pin": "4321"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["displayName"] == "New Owner"
    assert body["key"] == "new-owner"

    list_response = client.get("/api/owners/all")
    assert list_response.status_code == 200
    owners = list_response.json()["owners"]
    assert any(owner["key"] == "new-owner" for owner in owners)

    delete_response = client.delete(f"/api/owners/{body['key']}")
    assert delete_response.status_code == 204
    owners_after = client.get("/api/owners/all").json()["owners"]
    assert all(owner["key"] != "new-owner" for owner in owners_after)


def test_create_device_type(monkeypatch, tmp_path):
    from backend import device_types  # noqa: E402

    temp_file = tmp_path / "device_types.json"
    monkeypatch.setattr(device_types, "_DEVICE_TYPES_FILE", temp_file)
    with _DEVICE_TYPES_LOCK:
        _DEVICE_TYPES.clear()
        device_types._INITIALIZED = False  # type: ignore[attr-defined]

    response = client.post("/api/device-types", json={"name": "Smart Speaker"})
    assert response.status_code == 201
    payload = response.json()
    assert "Smart Speaker" in payload["types"]

    list_response = client.get("/api/device-types")
    assert list_response.status_code == 200
    assert "Smart Speaker" in list_response.json()["types"]

    delete_response = client.delete("/api/device-types/Smart Speaker")
    assert delete_response.status_code == 204
    remaining = client.get("/api/device-types").json()["types"]
    assert "Smart Speaker" not in remaining


def test_owner_creation_logs_event(monkeypatch):
    owner_repo = InMemoryOwnerRepository([])
    monkeypatch.setattr("backend.router.get_owner_repository", lambda: owner_repo)
    monkeypatch.setattr("backend.owners.get_owner_repository", lambda: owner_repo)

    audit_repo = events.InMemoryEventRepository()
    monkeypatch.setattr("backend.events.get_event_repository", lambda: audit_repo)

    response = client.post(
        "/api/owners",
        json={"displayName": "Audit Owner", "pin": "1357"},
        headers={"X-Actor": "auditor"},
    )
    assert response.status_code == 201

    events_response = client.get("/api/events")
    assert events_response.status_code == 200
    entries = events_response.json()["events"]
    assert any(
        entry["action"] == "owner_created" and entry.get("actor") == "auditor"
        for entry in entries
    )
