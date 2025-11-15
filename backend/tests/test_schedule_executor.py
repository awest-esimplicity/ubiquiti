from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.schedule_executor import ScheduleExecutor, is_schedule_active
from backend.schemas import (
    DeviceSchedule,
    ScheduleMetadata,
    ScheduleRecurrence,
    ScheduleTarget,
    ScheduleWindow,
)
from backend.ubiquiti.devices import Device


def _make_schedule(
    *,
    recurrence: ScheduleRecurrence,
    start: datetime,
    end: datetime,
) -> DeviceSchedule:
    return DeviceSchedule(
        id="schedule-1",
        scope="global",
        owner_key=None,
        label="Test Schedule",
        description=None,
        targets=ScheduleTarget(devices=["aa:bb:cc:dd:ee:ff"], tags=[]),
        action="lock",
        end_action="unlock",
        window=ScheduleWindow(start=start, end=end),
        recurrence=recurrence,
        exceptions=[],
        enabled=True,
        created_at=start,
        updated_at=start,
    )


def test_is_schedule_active_daily_cross_midnight():
    tz = ZoneInfo("America/Chicago")
    schedule = _make_schedule(
        recurrence=ScheduleRecurrence(type="daily", interval=1),
        start=datetime(2025, 1, 1, 21, 0, 0),
        end=datetime(2025, 1, 2, 6, 0, 0),
    )
    now = datetime(2025, 1, 5, 22, 30, 0, tzinfo=tz)
    assert is_schedule_active(schedule, now, tz)

    outside = datetime(2025, 1, 5, 10, 0, 0, tzinfo=tz)
    assert not is_schedule_active(schedule, outside, tz)


def test_is_schedule_active_weekly_specific_day():
    tz = ZoneInfo("America/Chicago")
    schedule = _make_schedule(
        recurrence=ScheduleRecurrence(
            type="weekly",
            interval=1,
            days_of_week=["Fri"],
        ),
        start=datetime(2025, 2, 7, 19, 0, 0),
        end=datetime(2025, 2, 7, 22, 30, 0),
    )
    now = datetime(2025, 2, 14, 20, 0, 0, tzinfo=tz)
    assert is_schedule_active(schedule, now, tz)

    outside = datetime(2025, 2, 15, 10, 0, 0, tzinfo=tz)
    assert not is_schedule_active(schedule, outside, tz)


def test_schedule_executor_triggers_actions(monkeypatch):
    tz = ZoneInfo("UTC")
    schedule = _make_schedule(
        recurrence=ScheduleRecurrence(type="daily", interval=1),
        start=datetime(2025, 1, 1, 21, 0, 0),
        end=datetime(2025, 1, 2, 6, 0, 0),
    )
    metadata = ScheduleMetadata(timezone="UTC", generated_at=datetime.now(tz))

    class Repo:
        def list(self, *, enabled: bool | None = None, **_: object):
            return [schedule]

        def get_metadata(self):
            return metadata

    device = Device(
        name="Test Device",
        mac="aa:bb:cc:dd:ee:ff",
        type="computer",
        owner="house",
    )

    class DeviceRepo:
        def list_all(self):
            return [device]

        def list_by_owner(self, owner: str):
            if owner == "house":
                return [device]
            return []

        def get_by_mac(self, mac: str):
            if mac.lower() == device.mac:
                return device
            return None

    calls: list[dict[str, object]] = []
    events: list[dict[str, object]] = []

    def fake_apply(devices, *, unlock: bool, actor: str | None, reason: str | None):
        calls.append(
            {
                "unlock": unlock,
                "devices": [item.mac for item in devices],
                "actor": actor,
                "reason": reason,
            }
        )
        return []

    def fake_record_event(**payload):
        events.append(payload)

    from backend import schedule_executor as module

    monkeypatch.setattr(module, "get_schedule_repository", lambda: Repo())
    monkeypatch.setattr(module, "get_device_repository", lambda: DeviceRepo())
    monkeypatch.setattr(module, "apply_lock_action", fake_apply)
    monkeypatch.setattr(module, "record_event", fake_record_event)

    executor = ScheduleExecutor()
    start_time = datetime(2025, 1, 3, 22, 0, 0, tzinfo=tz)
    executor.evaluate_once(now=start_time)
    assert calls == [
        {
            "unlock": False,
            "devices": [device.mac],
            "actor": "schedule:schedule-1",
            "reason": "Test Schedule",
        }
    ]

    executor.evaluate_once(now=start_time + timedelta(minutes=30))
    assert len(calls) == 1  # still active; no duplicate action

    executor.evaluate_once(now=start_time + timedelta(hours=10))
    assert calls[-1]["unlock"] is True
    assert calls[-1]["devices"] == [device.mac]
    assert events  # end/start events recorded
