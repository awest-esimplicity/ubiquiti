"""Configuration helpers for the UniFi client."""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

DEFAULT_BASE_URL = "https://10.0.0.1/proxy/network"


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _candidate_env_paths(start: Path) -> Iterable[Path]:
    """Yield plausible .env locations from closest to farthest."""
    override = os.environ.get("UBIQUITI_ENV_FILE")
    if override:
        yield Path(override).expanduser()

    for directory in (start, *start.parents):
        yield directory / ".env"


def _discover_env_path() -> Path | None:
    """Return the first .env path that exists, if any."""
    package_dir = Path(__file__).resolve().parent
    for candidate in _candidate_env_paths(package_dir):
        if candidate.exists():
            return candidate
    return None


def _load_env_file(path: Path | None = None) -> None:
    """Populate os.environ with values from a .env file if present."""
    env_path = path or _discover_env_path()
    if env_path is None or not env_path.exists():
        logger.debug("No .env file discovered for configuration")
        return

    logger.bind(path=str(env_path)).info("Loading environment variables from .env")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Respect existing environment variables so runtime overrides win.
        os.environ.setdefault(key, value)


_load_env_file()


@dataclass(frozen=True)
class Settings:
    """Typed accessors for configuration derived from the environment."""

    unifi_api_key: str
    unifi_base_url: str
    verify_ssl: bool

    @classmethod
    def from_env(cls) -> Settings:
        try:
            api_key = os.environ["UNIFI_API_KEY"]
        except KeyError as exc:  # pragma: no cover - exercised in tests
            raise RuntimeError(
                "UNIFI_API_KEY is not set; add it to .env or the environment."
            ) from exc

        base_url = os.environ.get("UNIFI_BASE_URL", DEFAULT_BASE_URL)
        verify_ssl_env = os.environ.get("UNIFI_VERIFY_SSL")
        verify_ssl = (
            _parse_bool(verify_ssl_env) if verify_ssl_env is not None else False
        )

        logger.bind(base_url=base_url, verify_ssl=verify_ssl).info(
            "Configuration loaded from environment"
        )

        return cls(
            unifi_api_key=api_key,
            unifi_base_url=base_url,
            verify_ssl=verify_ssl,
        )


settings = Settings.from_env()
