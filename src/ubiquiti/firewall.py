"""Helpers for managing UniFi firewall rules."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .unifi import UniFiAPIError, UniFiClient
from .utils import logger, suppress_insecure_request_warning


class FirewallManager:
    """High-level operations for UniFi firewall rules."""

    def __init__(self, client: UniFiClient, *, site: str = "default") -> None:
        self._client = client
        self._site = site
        self._wan_group_id: str | None = None

    @property
    def site(self) -> str:
        return self._site

    @property
    def client(self) -> UniFiClient:
        return self._client

    def create_rule(self, rule: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create a firewall rule and return the created entity."""
        logger.bind(site=self._site).debug("Creating firewall rule")
        response = self._client.request("post", self._base_endpoint(), json=dict(rule))
        created = self._extract_single(response)
        logger.bind(site=self._site, rule_id=(created or {}).get("_id")).info(
            "Firewall rule created"
        )
        return created

    def get_rule(self, rule_id: str) -> Mapping[str, Any] | None:
        """Fetch a firewall rule by identifier."""
        try:
            response = self._client.request("get", f"{self._base_endpoint()}/{rule_id}")
        except UniFiAPIError as exc:
            message = str(exc).lower()
            if "404" in message or "not found" in message:
                return None
            raise
        return self._extract_single(response)

    def rule_exists(self, rule_id: str) -> bool:
        """Return True if a firewall rule with the given id exists."""
        return self.get_rule(rule_id) is not None

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a firewall rule and return True when acknowledged."""
        logger.bind(site=self._site, rule_id=rule_id).debug("Deleting firewall rule")
        response = self._client.request("delete", f"{self._base_endpoint()}/{rule_id}")
        data = self._extract_payload(response)
        if isinstance(data, Mapping):
            rc = data.get("meta", {}).get("rc")
            if isinstance(rc, str):
                return rc.lower() == "ok"
        return True

    def list_rules(self) -> list[Mapping[str, Any]]:
        """Return all firewall rules for the configured site."""
        suppress_insecure_request_warning(self._client.verify_ssl)
        logger.bind(site=self._site).debug("Listing firewall rules")
        response = self._client.request("get", self._base_endpoint())
        data = self._extract_payload(response)
        if isinstance(data, list):
            return list(data)
        if data is None:
            return []
        return [data]

    def get_wan_group_id(self) -> str | None:
        """Return the firewall group ID representing WAN destinations."""
        if self._wan_group_id is not None:
            return self._wan_group_id

        try:
            response = self._client.request(
                "get", f"/api/s/{self._site}/list/firewallgroup"
            )
        except UniFiAPIError as exc:
            logger.warning("Unable to fetch firewall groups: {}", exc)
            return None

        payload = response.json()
        groups = payload.get("data", []) if isinstance(payload, dict) else []
        for group in groups:
            if group.get("name", "").lower() == "wan":
                self._wan_group_id = group.get("_id")
                break

        return self._wan_group_id

    def _base_endpoint(self) -> str:
        return f"/api/s/{self._site}/rest/firewallrule"

    @staticmethod
    def _extract_single(response: Any) -> Mapping[str, Any] | None:
        payload = FirewallManager._extract_payload(response)
        if payload is None:
            return None
        if isinstance(payload, list):
            return payload[0] if payload else None
        return payload

    @staticmethod
    def _extract_payload(response: Any) -> Any:
        try:
            body = response.json()
        except ValueError as exc:
            raise UniFiAPIError("Invalid JSON received from UniFi API") from exc

        if isinstance(body, Mapping):
            if "data" in body:
                return body["data"]
            return body
        return body
