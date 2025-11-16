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


def test_clone_schedule_to_owner():
    source_response = client.get("/api/owners/kade/schedules")
    assert source_response.status_code == 200
    source_data = source_response.json()
    source_schedule = source_data["ownerSchedules"][0]

    target_before = client.get("/api/owners/jayce/schedules").json()
    before_count = len(target_before["ownerSchedules"])

    clone_response = client.post(
        f"/api/schedules/{source_schedule['id']}/clone",
        json={"targetOwner": "jayce"},
    )
    assert clone_response.status_code == 201
    clone_data = clone_response.json()["schedule"]
    assert clone_data["id"] != source_schedule["id"]
    assert clone_data["ownerKey"] == "jayce"

    target_after = client.get("/api/owners/jayce/schedules").json()
    after_ids = {item["id"] for item in target_after["ownerSchedules"]}
    assert clone_data["id"] in after_ids
    assert len(target_after["ownerSchedules"]) == before_count + 1


def test_copy_owner_schedules_replace():
    source_owner = "kade"
    target_owner = "kailah"

    source_data = client.get(f"/api/owners/{source_owner}/schedules").json()
    source_count = len(source_data["ownerSchedules"])

    target_data_before = client.get(f"/api/owners/{target_owner}/schedules").json()
    target_before_count = len(target_data_before["ownerSchedules"])

    copy_response = client.post(
        f"/api/owners/{source_owner}/schedules/copy",
        json={"targetOwner": target_owner, "mode": "replace"},
    )
    assert copy_response.status_code == 200
    payload = copy_response.json()
    assert payload["sourceOwner"] == source_owner
    assert payload["targetOwner"] == target_owner
    assert payload["mode"] == "replace"
    assert payload["replacedCount"] == target_before_count
    assert len(payload["created"]) == source_count

    target_data_after = client.get(f"/api/owners/{target_owner}/schedules").json()
    assert len(target_data_after["ownerSchedules"]) == source_count


def test_create_schedule_requires_owner_key():
    payload = _build_schedule_payload("jayce")
    payload.pop("ownerKey")
    response = client.post("/api/schedules", json=payload)
    assert response.status_code == 422


def test_schedule_group_lifecycle():
    owner_key = "kade"
    payload_one = _build_schedule_payload(owner_key)
    payload_one["label"] = "Temporary Window A"
    payload_one["window"]["start"] = "2025-12-02T10:00:00Z"
    payload_one["window"]["end"] = "2025-12-02T12:00:00Z"
    payload_two = _build_schedule_payload(owner_key)
    payload_two["label"] = "Temporary Window B"
    payload_two["window"]["start"] = "2025-12-03T10:00:00Z"
    payload_two["window"]["end"] = "2025-12-03T12:00:00Z"

    schedule_one = client.post("/api/schedules", json=payload_one).json()
    schedule_two = client.post("/api/schedules", json=payload_two).json()

    group_create = client.post(
        "/api/schedule-groups",
        json={
            "name": "Kade Study Windows",
            "ownerKey": owner_key,
            "description": "Selectable study windows",
            "scheduleIds": [schedule_one["id"], schedule_two["id"]],
            "activeScheduleId": schedule_one["id"],
        },
    )
    assert group_create.status_code == 201
    group_payload = group_create.json()
    group_id = group_payload["id"]
    assert group_payload["activeScheduleId"] == schedule_one["id"]

    groups_response = client.get(f"/api/owners/{owner_key}/schedule-groups")
    assert groups_response.status_code == 200
    groups_data = groups_response.json()
    owner_groups = groups_data["ownerGroups"]
    assert any(group["id"] == group_id for group in owner_groups)

    activate_response = client.post(
        f"/api/schedule-groups/{group_id}/activate",
        json={"scheduleId": schedule_two["id"]},
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["activeScheduleId"] == schedule_two["id"]

    delete_response = client.delete(f"/api/schedule-groups/{group_id}")
    assert delete_response.status_code == 204

    groups_after_delete = client.get(f"/api/owners/{owner_key}/schedule-groups").json()
    assert all(group["id"] != group_id for group in groups_after_delete["ownerGroups"])

    schedule_after = client.get(f"/api/schedules/{schedule_one['id']}").json()
    assert schedule_after["groupId"] is None
