from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402
from backend.owners import InMemoryOwnerRepository, Owner  # noqa: E402
from backend.device_types import _DEVICE_TYPES_LOCK, _DEVICE_TYPES  # type: ignore[attr-defined]  # noqa: E402


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
