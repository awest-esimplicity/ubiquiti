from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient

# Ensure we operate against the in-memory repositories during tests.
os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402


client = TestClient(app)


def _build_schedule_payload(owner_key: str) -> dict[str, object]:
    start = datetime(2025, 12, 1, 15, 0, tzinfo=timezone.utc)
    end = datetime(2025, 12, 1, 17, 0, tzinfo=timezone.utc)
    return {
        "scope": "owner",
        "ownerKey": owner_key,
        "label": "Test Event",
        "description": "Temporary unlock for testing.",
        "targets": {"devices": [], "tags": [f"{owner_key}-all"]},
        "action": "unlock",
        "endAction": "lock",
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "recurrence": {"type": "one_shot"},
        "exceptions": [],
        "enabled": True,
    }


def test_list_schedules():
    response = client.get("/api/schedules")
    assert response.status_code == 200
    data = response.json()
    assert data["metadata"]["timezone"] == "America/Chicago"
    assert len(data["schedules"]) >= 1


def test_create_update_and_delete_schedule():
    payload = _build_schedule_payload("kade")
    create_response = client.post("/api/schedules", json=payload)
    assert create_response.status_code == 201
    schedule = create_response.json()
    schedule_id = schedule["id"]
    assert schedule["ownerKey"] == "kade"
    assert schedule["enabled"] is True

    # Update label and disable
    update_response = client.patch(
        f"/api/schedules/{schedule_id}",
        json={"label": "Updated label"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Updated label"

    disable_response = client.post(f"/api/schedules/{schedule_id}/disable")
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False

    # Delete the schedule
    delete_response = client.delete(f"/api/schedules/{schedule_id}")
    assert delete_response.status_code == 204
    not_found_response = client.get(f"/api/schedules/{schedule_id}")
    assert not_found_response.status_code == 404


def test_get_owner_schedule_summary():
    response = client.get("/api/owners/kade/schedules")
    assert response.status_code == 200
    data = response.json()
    assert "ownerSchedules" in data
    assert "globalSchedules" in data


def test_create_schedule_requires_owner_key():
    payload = _build_schedule_payload("jayce")
    payload.pop("ownerKey")
    response = client.post("/api/schedules", json=payload)
    assert response.status_code == 422
