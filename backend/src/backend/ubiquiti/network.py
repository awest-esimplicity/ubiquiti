"""Helpers for querying UniFi device and client information."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Sequence

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

    def get_client_detail(self, mac: str) -> dict[str, Any] | None:
        """Return detailed information for a specific client device."""
        if not mac:
            return None
        suppress_insecure_request_warning(self._client.verify_ssl)
        response = self._client.request(
            "get", self._path(f"stat/user/{mac.lower()}")
        )
        data = self._extract_data(response)
        return data[0] if data else None

    def get_client_traffic(
        self,
        mac: str,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        resolution: Literal["5minutes", "hourly"] = "5minutes",
        attrs: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Return historical traffic samples for a client device."""
        if not mac:
            return []

        resolution_value = resolution if resolution in {"5minutes", "hourly"} else "5minutes"

        end_dt = (end or datetime.now(tz=UTC)).astimezone(UTC)
        start_dt = (start or end_dt - (timedelta(hours=12) if resolution_value == "5minutes" else timedelta(days=7))).astimezone(UTC)
        if start_dt >= end_dt:
            start_dt = end_dt - (timedelta(minutes=5) if resolution_value == "5minutes" else timedelta(hours=1))

        payload_attrs = ["time", "rx_bytes", "tx_bytes"]
        if attrs:
            payload_attrs = ["time"] + [value for value in attrs if value != "time"]

        payload = {
            "mac": mac.lower(),
            "start": int(start_dt.timestamp() * 1000),
            "end": int(end_dt.timestamp() * 1000),
            "attrs": payload_attrs,
        }

        suppress_insecure_request_warning(self._client.verify_ssl)
        response = self._client.request(
            "post",
            self._path(f"stat/report/{resolution_value}.user"),
            json=payload,
        )
        samples = self._extract_data(response)
        logger.bind(
            site=self._site,
            mac=mac.lower(),
            sample_count=len(samples),
            resolution=resolution_value,
        ).debug("Fetched UniFi traffic samples for client")
        return samples

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
