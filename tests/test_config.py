"""Tests for the configuration helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

MODULE_NAME = "ubiquiti.config"


def _reload_config(
    monkeypatch: pytest.MonkeyPatch, env_file: Path, *, preserve_env: bool = False
) -> object:
    monkeypatch.setenv("UBIQUITI_ENV_FILE", str(env_file))
    if not preserve_env:
        monkeypatch.delenv("UNIFI_API_KEY", raising=False)
    sys.modules.pop(MODULE_NAME, None)
    return importlib.import_module(MODULE_NAME)


def test_settings_loaded_from_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("UNIFI_API_KEY=test-key\n", encoding="utf-8")

    config = _reload_config(monkeypatch, env_file)

    assert config.settings.unifi_api_key == "test-key"
    assert config.settings.unifi_base_url == "https://10.0.0.1/proxy/network"
    assert config.settings.verify_ssl is False


def test_environment_variable_overrides_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "UNIFI_API_KEY=file-value\nUNIFI_BASE_URL=https://controller\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("UNIFI_API_KEY", "env-value")
    monkeypatch.setenv("UNIFI_VERIFY_SSL", "true")
    config = _reload_config(monkeypatch, env_file, preserve_env=True)

    assert config.settings.unifi_api_key == "env-value"
    assert config.settings.unifi_base_url == "https://controller"
    assert config.settings.verify_ssl is True


def test_missing_api_key_raises_runtime_error(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# empty on purpose\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="UNIFI_API_KEY is not set"):
        _reload_config(monkeypatch, env_file)
