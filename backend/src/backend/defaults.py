"""Default in-memory data sets for the backend."""

from __future__ import annotations

# Default schedule configuration shared by the in-memory repositories and seeding.
DEFAULT_SCHEDULE_CONFIG: dict[str, object] = {
    "metadata": {
        "timezone": "America/Chicago",
        "generatedAt": "2025-11-12T10:00:00-06:00",
    },
    "schedules": [
        {
            "id": "global-school-night",
            "scope": "global",
            "label": "School Night Quiet Hours",
            "description": "Lock all streaming devices across the network after 9 PM on school nights.",
            "targets": {
                "devices": [],
                "tags": ["streaming"],
            },
            "action": "lock",
            "endAction": "unlock",
            "window": {
                "start": "2025-11-12T21:00:00",
                "end": "2025-11-13T06:00:00",
            },
            "recurrence": {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": ["Sun", "Mon", "Tue", "Wed", "Thu"],
                "until": None,
            },
            "exceptions": [
                {
                    "date": "2025-11-27",
                    "reason": "Thanksgiving break",
                    "skip": True,
                }
            ],
            "enabled": True,
            "createdAt": "2025-09-15T08:12:00-05:00",
            "updatedAt": "2025-11-10T09:05:00-06:00",
        },
        {
            "id": "kade-weekend-gaming",
            "scope": "owner",
            "ownerKey": "kade",
            "label": "Weekend Gaming Window",
            "description": "Unlock Kade’s Xbox every Saturday/Sunday afternoon.",
            "targets": {
                "devices": ["28:16:a8:ae:27:57"],
                "tags": [],
            },
            "action": "unlock",
            "endAction": "lock",
            "window": {
                "start": "2025-11-15T14:00:00",
                "end": "2025-11-15T18:00:00",
            },
            "recurrence": {
                "type": "weekly",
                "interval": 1,
                "daysOfWeek": ["Sat", "Sun"],
                "until": None,
            },
            "exceptions": [],
            "enabled": True,
            "createdAt": "2025-09-18T12:32:00-05:00",
            "updatedAt": "2025-10-02T09:12:00-05:00",
        },
        {
            "id": "jayce-exam-week",
            "scope": "owner",
            "ownerKey": "jayce",
            "label": "Exam Week Lock",
            "description": "Lock Jayce’s devices during final exams.",
            "targets": {
                "devices": [],
                "tags": ["jayce-all"],
            },
            "action": "lock",
            "endAction": "unlock",
            "window": {
                "start": "2025-12-09T07:00:00",
                "end": "2025-12-16T18:00:00",
            },
            "recurrence": {
                "type": "one_shot",
            },
            "exceptions": [],
            "enabled": False,
            "createdAt": "2025-11-05T11:00:00-05:00",
            "updatedAt": "2025-11-05T11:00:00-05:00",
        },
        {
            "id": "house-movie-night",
            "scope": "owner",
            "ownerKey": "house",
            "label": "Family Movie Night",
            "description": "Unlock living room Roku Friday nights.",
            "targets": {
                "devices": ["8c:49:62:14:a0:d4", "8c:49:62:14:a0:d5"],
                "tags": [],
            },
            "action": "unlock",
            "endAction": "lock",
            "window": {
                "start": "2025-11-15T19:00:00",
                "end": "2025-11-16T22:30:00",
            },
            "recurrence": {
                "type": "weekly",
                "daysOfWeek": ["Fri"],
                "interval": 1,
                "until": None,
            },
            "exceptions": [
                {
                    "date": "2025-12-20",
                    "reason": "Holiday travel",
                    "skip": True,
                }
            ],
            "enabled": True,
            "createdAt": "2025-10-01T15:10:22-05:00",
            "updatedAt": "2025-11-11T08:45:10-06:00",
        },
        {
            "id": "nightly-network-reset",
            "scope": "global",
            "label": "Nightly Network Reset",
            "description": "Lock all devices for 10 minutes every night to recycle network sessions.",
            "targets": {
                "devices": [],
                "tags": ["all-devices"],
            },
            "action": "lock",
            "endAction": "unlock",
            "window": {
                "start": "2025-11-12T03:00:00",
                "end": "2025-11-12T03:10:00",
            },
            "recurrence": {
                "type": "daily",
                "interval": 1,
                "until": None,
            },
            "exceptions": [],
            "enabled": True,
            "createdAt": "2025-08-01T06:00:00-05:00",
            "updatedAt": "2025-11-07T12:00:00-06:00",
        },
    ],
}

__all__ = ["DEFAULT_SCHEDULE_CONFIG"]
