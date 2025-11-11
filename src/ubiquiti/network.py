"""Helpers for querying UniFi device and client information."""

from __future__ import annotations

from typing import Any

from .unifi import UniFiClient
from .utils import logger, suppress_insecure_request_warning


class NetworkDeviceService:
    """Interface for retrieving UniFi device and client metadata."""

    def __init__(self, client: UniFiClient, *, site: str = "default") -> None:
        self._client = client
        self._site = site

    @property
    def site(self) -> str:
        return self._site

    def list_devices(self) -> list[dict[str, Any]]:
        """Return all UniFi network devices."""
        suppress_insecure_request_warning(self._client.verify_ssl)
        response = self._client.request("get", self._path("stat/device"))
        devices = self._extract_data(response)
        logger.bind(site=self._site, device_count=len(devices)).info(
            "Fetched UniFi devices"
        )
        return devices

    def list_active_clients(self) -> list[dict[str, Any]]:
        """Return all currently connected client devices."""
        suppress_insecure_request_warning(self._client.verify_ssl)
        response = self._client.request("get", self._path("stat/sta"))
        clients = self._extract_data(response)
        logger.bind(site=self._site, client_count=len(clients)).info(
            "Fetched active clients"
        )
        return clients

    def _path(self, suffix: str) -> str:
        return f"/api/s/{self._site}/{suffix.lstrip('/')}"

    @staticmethod
    def _extract_data(response: Any) -> list[dict[str, Any]]:
        payload = response.json()
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return list(data)
        return []


__all__ = ["NetworkDeviceService"]
