"""Background scheduler that drives automatic lock/unlock actions."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Iterable as IterableType
from zoneinfo import ZoneInfo

from .events import record_event
from .owners import get_owner_repository
from .schedules import get_schedule_repository
from .schemas import DeviceSchedule, ScheduleException, ScheduleRecurrence
from .services import apply_lock_action
from .ubiquiti.devices import Device, get_device_repository
from .ubiquiti.utils import logger

DAY_NAME_TO_INDEX = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _ensure_timezone(dt: datetime, tz: ZoneInfo) -> datetime:
    """Attach a timezone to naive datetimes or convert to the provided zone."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _exception_window(
    occurrence_start: datetime,
    occurrence_end: datetime,
    exceptions: IterableType[ScheduleException],
    tz: ZoneInfo,
) -> tuple[datetime, datetime] | None:
    """Apply schedule exceptions for a specific occurrence window."""
    occ_date = occurrence_start.date()
    for exception in exceptions:
        if exception.date != occ_date:
            continue
        if exception.skip:
            return None
        if exception.override_window:
            override_start = _ensure_timezone(exception.override_window.start, tz)
            override_end = _ensure_timezone(exception.override_window.end, tz)
            if override_end <= override_start:
                override_end = override_start + (occurrence_end - occurrence_start)
            return override_start, override_end
    return occurrence_start, occurrence_end


def _duration(schedule: DeviceSchedule) -> timedelta:
    base_start = schedule.window.start
    base_end = schedule.window.end
    return base_end - base_start


def _adjust_for_until(
    recurrence: ScheduleRecurrence, occurrence_start: datetime, tz: ZoneInfo
) -> bool:
    if recurrence.until is None:
        return True
    until = recurrence.until
    if until.tzinfo is None:
        until = until.replace(tzinfo=tz)
    else:
        until = until.astimezone(tz)
    return occurrence_start <= until


def _iter_daily_occurrences(
    schedule: DeviceSchedule, now: datetime, tz: ZoneInfo
) -> IterableType[tuple[datetime, datetime]]:
    base_start = _ensure_timezone(schedule.window.start, tz)
    base_end = _ensure_timezone(schedule.window.end, tz)
    interval_days = max(schedule.recurrence.interval, 1)
    duration = base_end - base_start

    if now < base_start:
        candidates = [base_start]
    else:
        elapsed_days = (now - base_start).days
        cycles = max(elapsed_days // interval_days, 0)
        candidates = [
            base_start + timedelta(days=interval_days * offset)
            for offset in range(max(cycles - 1, 0), cycles + 2)
        ]
    for start in candidates:
        if not _adjust_for_until(schedule.recurrence, start, tz):
            continue
        yield start, start + duration


def _iter_weekly_occurrences(
    schedule: DeviceSchedule, now: datetime, tz: ZoneInfo
) -> IterableType[tuple[datetime, datetime]]:
    base_start = _ensure_timezone(schedule.window.start, tz)
    base_end = _ensure_timezone(schedule.window.end, tz)
    duration = base_end - base_start
    interval_weeks = max(schedule.recurrence.interval, 1)

    days = schedule.recurrence.days_of_week or []
    if not days:
        days = [base_start.strftime("%a")]

    day_indices: list[int] = []
    for day in days:
        index = DAY_NAME_TO_INDEX.get(day.lower())
        if index is not None:
            day_indices.append(index)

    if not day_indices:
        return []

    anchor_monday = base_start - timedelta(days=base_start.weekday())
    total_weeks = max(int((now - anchor_monday).days / 7) + 2, 2)
    start_week = 0
    if now < base_start:
        total_weeks = 2
    for week in range(start_week, total_weeks):
        if week % interval_weeks != 0:
            continue
        week_start = anchor_monday + timedelta(weeks=week)
        for index in day_indices:
            day_date = (week_start + timedelta(days=index)).date()
            start = datetime.combine(day_date, base_start.timetz())
            if start.tzinfo is None:
                start = start.replace(tzinfo=tz)
            else:
                start = start.astimezone(tz)
            end = start + duration
            if not _adjust_for_until(schedule.recurrence, start, tz):
                continue
            yield start, end


def _iter_one_shot_occurrence(
    schedule: DeviceSchedule, tz: ZoneInfo
) -> IterableType[tuple[datetime, datetime]]:
    start = _ensure_timezone(schedule.window.start, tz)
    end = _ensure_timezone(schedule.window.end, tz)
    yield start, end


def _iter_occurrences(
    schedule: DeviceSchedule, now: datetime, tz: ZoneInfo
) -> IterableType[tuple[datetime, datetime]]:
    recurrence = schedule.recurrence
    if recurrence.type == "one_shot":
        return _iter_one_shot_occurrence(schedule, tz)
    if recurrence.type == "daily":
        return _iter_daily_occurrences(schedule, now, tz)
    if recurrence.type == "weekly":
        return _iter_weekly_occurrences(schedule, now, tz)
    logger.warning(
        "Unsupported schedule recurrence encountered.",
        schedule_id=schedule.id,
        recurrence=recurrence.type,
    )
    return []


def _occurrence_active(
    occurrence: tuple[datetime, datetime],
    now: datetime,
    schedule: DeviceSchedule,
    tz: ZoneInfo,
) -> tuple[datetime, datetime] | None:
    start, end = occurrence
    if end <= start:
        end = start + _duration(schedule)
    candidate = _exception_window(start, end, schedule.exceptions, tz)
    if candidate is None:
        return None
    start, end = candidate
    if start <= now < end:
        return start, end
    return None


def is_schedule_active(schedule: DeviceSchedule, now: datetime, tz: ZoneInfo) -> bool:
    """Return True when the schedule should be active at the provided time."""
    for occurrence in _iter_occurrences(schedule, now, tz):
        active = _occurrence_active(occurrence, now, schedule, tz)
        if active:
            return True
    return False


def _resolve_devices(schedule: DeviceSchedule) -> list[Device]:
    repo = get_device_repository()
    devices = {device.mac: device for device in repo.list_all()}
    selected: dict[str, Device] = {}

    for mac in schedule.targets.devices:
        normalized = mac.strip().lower()
        device = devices.get(normalized)
        if device:
            selected[normalized] = device
        else:
            constructed = Device(
                name=normalized,
                mac=normalized,
                owner="unregistered",
                type="unknown",
            )
            selected[normalized] = constructed

    for tag in schedule.targets.tags:
        tag_norm = tag.strip().lower()
        if tag_norm == "all-devices":
            for device in devices.values():
                selected[device.mac] = device
            continue
        if tag_norm.endswith("-all"):
            owner_key = tag_norm[:-4]
            for device in repo.list_by_owner(owner_key):
                selected[device.mac] = device
            continue
        owner_repo = get_owner_repository()
        if owner_repo.get(tag_norm):
            for device in repo.list_by_owner(tag_norm):
                selected[device.mac] = device
            continue
        logger.warning(
            "Unknown schedule tag encountered; skipping.",
            tag=tag_norm,
            schedule_id=schedule.id,
        )
    return list(selected.values())


@dataclass
class ScheduleExecutor:
    interval_seconds: int = 60
    _task: asyncio.Task[None] | None = field(default=None, init=False)
    _active: dict[str, bool] = field(default_factory=dict, init=False)
    _running: bool = field(default=False, init=False)

    async def start(self) -> None:
        if self._task:
            return
        self._running = True
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._run())
        logger.info("Schedule executor started.")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("Schedule executor stopped.")

    async def _run(self) -> None:
        while self._running:
            try:
                await asyncio.to_thread(self.evaluate_once)
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Schedule executor iteration failed.", error=str(exc))
            await asyncio.sleep(self.interval_seconds)

    def evaluate_once(self, *, now: datetime | None = None) -> None:
        repo = get_schedule_repository()
        metadata = repo.get_metadata()
        tz_name = metadata.timezone or "UTC"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            logger.warning(
                "Invalid timezone for schedule metadata; defaulting to UTC.",
                timezone=tz_name,
            )
            tz = ZoneInfo("UTC")

        current = now or datetime.now(tz)
        schedules = repo.list(enabled=True)
        known_ids = {schedule.id for schedule in schedules}
        # Cleanup any removed schedules from state storage
        for schedule_id in list(self._active.keys()):
            if schedule_id not in known_ids:
                self._active.pop(schedule_id, None)

        for schedule in schedules:
            active = is_schedule_active(schedule, current, tz)
            previous = self._active.get(schedule.id, False)
            if active and not previous:
                self._apply_schedule_action(schedule, activate=True)
                self._active[schedule.id] = True
            elif not active and previous:
                self._apply_schedule_action(schedule, activate=False)
                self._active[schedule.id] = False

    def _apply_schedule_action(self, schedule: DeviceSchedule, *, activate: bool) -> None:
        devices = _resolve_devices(schedule)
        if not devices:
            logger.warning(
                "Schedule has no target devices; skipping.",
                schedule_id=schedule.id,
            )
            return
        action = schedule.action if activate else schedule.end_action
        if action is None:
            return

        unlock = action == "unlock"
        actor = f"schedule:{schedule.id}"
        reason = schedule.label
        logger.info(
            "Applying schedule action.",
            schedule_id=schedule.id,
            action=action,
            device_count=len(devices),
            activate=activate,
        )
        apply_lock_action(devices, unlock=unlock, actor=actor, reason=reason)
        record_event(
            action="schedule_triggered",
            subject_type="schedule",
            subject_id=schedule.id,
            actor=actor,
            reason=reason,
            metadata={
                "phase": "start" if activate else "end",
                "action": action,
                "device_count": len(devices),
            },
        )


executor = ScheduleExecutor()
