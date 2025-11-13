from __future__ import annotations

import os

from fastapi.testclient import TestClient

# Ensure in-memory repositories during tests
os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402


client = TestClient(app)


def test_session_whoami_returns_probable_matches(monkeypatch):
    sample_clients = [
        {
            "name": "Living Room Tablet",
            "mac": "aa:bb:cc:dd:ee:ff",
            "ip": "10.0.0.5",
            "vendor": "Acme",
            "last_seen": None,
            "locked": False,
        },
        {
            "name": "Other Device",
            "mac": "11:22:33:44:55:66",
            "ip": "10.0.0.10",
            "vendor": "Other",
            "last_seen": None,
            "locked": False,
        },
    ]

    monkeypatch.setattr(
        "backend.router.get_unregistered_client_records",
        lambda: sample_clients,
    )

    response = client.get(
        "/api/session/whoami",
        headers={"x-forwarded-for": "10.0.0.5"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ip"] == "10.0.0.5"
    assert data["forwardedFor"] == ["10.0.0.5"]
    assert len(data["probableClients"]) == 1
    assert data["probableClients"][0]["mac"] == "aa:bb:cc:dd:ee:ff"


def test_session_whoami_handles_missing_matches(monkeypatch):
    monkeypatch.setattr(
        "backend.router.get_unregistered_client_records",
        lambda: [],
    )
    response = client.get("/api/session/whoami")
    assert response.status_code == 200
    data = response.json()
    assert data["probableClients"] == []
