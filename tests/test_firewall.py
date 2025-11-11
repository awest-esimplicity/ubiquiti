"""Tests for the firewall manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ubiquiti.firewall import FirewallManager
from ubiquiti.unifi import UniFiAPIError


@dataclass
class DummyResponse:
    payload: Any

    def json(self) -> Any:
        return self.payload


class DummyClient:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.verify_ssl = True

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "path": path, **kwargs})
        if not self.responses:
            raise AssertionError("No more responses queued")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_create_rule_returns_created_entity():
    client = DummyClient(
        [DummyResponse({"data": [{"_id": "rule1", "name": "Allow SSH"}]})]
    )
    manager = FirewallManager(client, site="default")

    created = manager.create_rule({"name": "Allow SSH"})

    assert created == {"_id": "rule1", "name": "Allow SSH"}
    assert client.calls == [
        {
            "method": "post",
            "path": "/api/s/default/rest/firewallrule",
            "json": {"name": "Allow SSH"},
        }
    ]


def test_get_rule_returns_rule_when_present():
    client = DummyClient(
        [DummyResponse({"data": [{"_id": "rule1", "name": "Allow SSH"}]})]
    )
    manager = FirewallManager(client)

    rule = manager.get_rule("rule1")

    assert rule == {"_id": "rule1", "name": "Allow SSH"}
    assert client.calls[0]["path"] == "/api/s/default/rest/firewallrule/rule1"


def test_get_rule_returns_none_when_not_found():
    client = DummyClient([UniFiAPIError("404 Not Found")])
    manager = FirewallManager(client)

    rule = manager.get_rule("missing")

    assert rule is None


def test_rule_exists_delegates_to_get_rule(monkeypatch):
    client = DummyClient([DummyResponse({"data": []})])
    manager = FirewallManager(client)

    assert manager.rule_exists("rule") is False


def test_delete_rule_returns_true_on_ok_response():
    client = DummyClient([DummyResponse({"meta": {"rc": "ok"}, "data": []})])
    manager = FirewallManager(client)

    result = manager.delete_rule("rule1")

    assert result is True
    assert client.calls[0]["method"] == "delete"
    assert client.calls[0]["path"] == "/api/s/default/rest/firewallrule/rule1"


def test_delete_rule_without_meta_returns_true():
    client = DummyClient([DummyResponse({"data": []})])
    manager = FirewallManager(client)

    assert manager.delete_rule("rule1") is True


def test_list_rules_returns_list():
    client = DummyClient(
        [DummyResponse({"data": [{"_id": "rule1"}, {"_id": "rule2"}]})]
    )
    manager = FirewallManager(client)

    rules = manager.list_rules()

    assert [rule["_id"] for rule in rules] == ["rule1", "rule2"]
    assert client.calls[0]["method"] == "get"
