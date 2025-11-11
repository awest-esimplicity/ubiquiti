"""Tests for the UniFi API client."""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

CONFIG_MODULE = "ubiquiti.config"
UNIFI_MODULE = "ubiquiti.unifi"


@dataclass
class DummyResponse:
    ok: bool
    status_code: int = 200
    text: str = "OK"


class DummySession:
    def __init__(self, response: DummyResponse) -> None:
        self._response = response
        self.headers: dict[str, str] = {}
        self.verify: bool | None = None
        self.calls = []
        self.closed = False

    def request(self, **kwargs: Any) -> DummyResponse:
        self.calls.append(kwargs)
        return self._response

    def close(self) -> None:
        self.closed = True


def _reload_unifi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, api_key: str):
    env_file = tmp_path / ".env"
    env_file.write_text(f"UNIFI_API_KEY={api_key}\n", encoding="utf-8")

    monkeypatch.setenv("UBIQUITI_ENV_FILE", str(env_file))
    monkeypatch.delenv("UNIFI_API_KEY", raising=False)

    sys.modules.pop(UNIFI_MODULE, None)
    sys.modules.pop(CONFIG_MODULE, None)

    config = importlib.import_module(CONFIG_MODULE)
    return importlib.import_module(UNIFI_MODULE), config


def test_establish_connection_configures_session(tmp_path, monkeypatch):
    unifi_module, _ = _reload_unifi(monkeypatch, tmp_path, api_key="abc123")

    session = DummySession(DummyResponse(ok=True))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: session)

    client = unifi_module.UniFiClient("https://controller.example")
    created_session = client.establish_connection()

    assert created_session is session
    assert session.verify is True
    assert session.headers["X-API-KEY"] == "abc123"
    assert session.headers["Accept"] == "application/json"
    assert session.headers["Content-Type"] == "application/json"
    # Session should be cached
    assert client.establish_connection() is session


def test_request_success(tmp_path, monkeypatch):
    unifi_module, _ = _reload_unifi(monkeypatch, tmp_path, api_key="xyz789")

    session = DummySession(DummyResponse(ok=True))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: session)

    client = unifi_module.UniFiClient("https://controller.example", timeout=5)
    response = client.request("get", "/sites/default", params={"limit": 10}, json=None)

    assert response.ok is True
    assert session.calls == [
        {
            "method": "GET",
            "url": "https://controller.example/sites/default",
            "params": {"limit": 10},
            "json": None,
            "timeout": 5,
        }
    ]


def test_request_failure_raises(tmp_path, monkeypatch):
    unifi_module, _ = _reload_unifi(monkeypatch, tmp_path, api_key="xyz789")

    session = DummySession(DummyResponse(ok=False, status_code=502, text="Bad gateway"))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: session)

    client = unifi_module.UniFiClient("https://controller.example", timeout=5)
    with pytest.raises(unifi_module.UniFiAPIError, match="502"):
        client.request("post", "sites/default", json={"foo": "bar"})


def test_close_cleans_up_session(tmp_path, monkeypatch):
    unifi_module, _ = _reload_unifi(monkeypatch, tmp_path, api_key="xyz789")

    session = DummySession(DummyResponse(ok=True))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: session)

    client = unifi_module.UniFiClient("https://controller.example")
    client.establish_connection()
    client.close()

    assert session.closed is True

    new_session = DummySession(DummyResponse(ok=True))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: new_session)

    assert client.establish_connection() is new_session


def test_custom_api_key_header(tmp_path, monkeypatch):
    unifi_module, _ = _reload_unifi(monkeypatch, tmp_path, api_key="token")
    session = DummySession(DummyResponse(ok=True))
    monkeypatch.setattr(unifi_module.requests, "Session", lambda: session)

    client = unifi_module.UniFiClient(
        "https://controller.example", api_key_header="Authorization"
    )
    client.establish_connection()

    assert session.headers["Authorization"] == "Bearer token"
