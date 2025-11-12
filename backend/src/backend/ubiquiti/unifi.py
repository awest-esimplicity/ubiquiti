"""UniFi API client utilities."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests  # type: ignore[import-untyped]
from requests import Response, Session

from .config import settings


class UniFiAPIError(RuntimeError):
    """Raised when an HTTP request to the UniFi API fails."""


class UniFiClient:
    """Minimal client for interacting with the UniFi Network application API."""

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        api_key_header: str = "X-API-KEY",
        verify_ssl: bool = True,
        timeout: int = 10,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or settings.unifi_api_key
        self.api_key_header = api_key_header
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._session: Session | None = None

    def establish_connection(self) -> Session:
        """Initialize (or reuse) a requests.Session configured for the UniFi API."""
        if self._session is not None:
            return self._session

        session = requests.Session()
        session.verify = self.verify_ssl
        header_value = self.api_key
        if (
            self.api_key_header.lower() == "authorization"
            and not header_value.lower().startswith("bearer ")
        ):
            header_value = f"Bearer {header_value}"

        session.headers.update(
            {
                self.api_key_header: header_value,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        self._session = session
        return session

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Any | None = None,
    ) -> Response:
        """Execute an HTTP request against the UniFi API."""
        session = self.establish_connection()
        url = f"{self.base_url}/{path.lstrip('/')}"

        response = session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json,
            timeout=self.timeout,
        )

        if not response.ok:
            raise UniFiAPIError(
                f"UniFi API request failed ({response.status_code}): {response.text}"
            )

        return response

    def close(self) -> None:
        """Close the underlying session if it was created."""
        if self._session is not None:
            self._session.close()
            self._session = None
