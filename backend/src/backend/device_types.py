"""Utility helpers for managing known device types."""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock

_DEVICE_TYPES_LOCK = Lock()
_DEVICE_TYPES: dict[str, str] = {}
_INITIALIZED = False

_DEFAULT_DEVICE_TYPES = [
    "computer",
    "tv",
    "switch",
    "streaming",
    "console",
    "phone",
    "tablet",
    "unknown",
]


def _project_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "app").exists():
            return parent
    return Path(__file__).resolve().parents[2]


_DEVICE_TYPES_FILE = _project_root() / "app" / "data" / "device_types.json"


def _load() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    values = list(_DEFAULT_DEVICE_TYPES)
    if _DEVICE_TYPES_FILE.exists():
        try:
            payload = json.loads(_DEVICE_TYPES_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                values.extend(str(item) for item in payload if isinstance(item, str))
        except json.JSONDecodeError:
            pass
    with _DEVICE_TYPES_LOCK:
        for item in values:
            normalized = item.strip()
            if not normalized:
                continue
            canonical = normalized.lower()
            _DEVICE_TYPES.setdefault(canonical, normalized)
        _INITIALIZED = True


def _save() -> None:
    _DEVICE_TYPES_FILE.parent.mkdir(parents=True, exist_ok=True)
    sorted_values = sorted(_DEVICE_TYPES.values(), key=lambda value: value.lower())
    _DEVICE_TYPES_FILE.write_text(
        json.dumps(sorted_values, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def list_device_types() -> list[str]:
    """Return all known device types sorted alphabetically."""
    _load()
    with _DEVICE_TYPES_LOCK:
        return sorted(_DEVICE_TYPES.values(), key=lambda value: value.lower())


def _normalise_label(label: str) -> str:
    text = label.strip()
    if not text:
        raise ValueError("Device type must not be empty.")
    text = re.sub(r"\s+", " ", text)
    return text


def add_device_type(label: str) -> str:
    """Register a new device type, returning the stored label."""
    _load()
    normalized = _normalise_label(label)
    canonical = normalized.lower()
    with _DEVICE_TYPES_LOCK:
        updated = canonical not in _DEVICE_TYPES
        _DEVICE_TYPES.setdefault(canonical, normalized)
        if updated:
            _save()
    return _DEVICE_TYPES[canonical]


def remove_device_type(label: str) -> bool:
    """Remove a device type entry; returns True if it existed."""
    _load()
    canonical = label.strip().lower()
    if not canonical or canonical in {item.lower() for item in _DEFAULT_DEVICE_TYPES}:
        return False
    with _DEVICE_TYPES_LOCK:
        if canonical not in _DEVICE_TYPES:
            return False
        del _DEVICE_TYPES[canonical]
        _save()
        return True


__all__ = ["list_device_types", "add_device_type"]
