from __future__ import annotations

import os
from contextlib import contextmanager
from urllib.parse import quote

from fastapi.testclient import TestClient

# Ensure we operate in memory-backed repositories for API tests.
os.environ["UBIQUITI_DB_MODE"] = "memory"
os.environ["UBIQUITI_DB_URL"] = ""

from backend.app import app  # noqa: E402
from backend.ubiquiti.devices import Device, InMemoryDeviceRepository  # noqa: E402


client = TestClient(app)


class DummyNetworkService:
    def __init__(self, *_args, **_kwargs) -> None:
        self.detail_payload: dict[str, object] | None = None
        self.active_clients: list[dict[str, object]] = []
        self.traffic_samples: list[dict[str, object]] = []
        self.observed_traffic_args: tuple[str, str] | None = None
        self.dpi_rows: list[dict[str, object]] = []

    def get_client_detail(self, mac: str) -> dict[str, object] | None:
        self.observed_detail_mac = mac  # type: ignore[attr-defined]
        return self.detail_payload

    def list_active_clients(self) -> list[dict[str, object]]:
        return list(self.active_clients)

    def get_client_traffic(
        self,
        mac: str,
        *,
        start,
        end,
        resolution,
        attrs,
    ) -> list[dict[str, object]]:
        self.observed_traffic_args = (mac, resolution)  # type: ignore[assignment]
        return list(self.traffic_samples)

    def get_dpi_applications(self) -> list[dict[str, object]]:
        return list(self.dpi_rows)


@contextmanager
def _fake_locker_context(locked: bool = False):
    class FakeFirewall:
        def __init__(self) -> None:
            self.client = object()

        def list_rules(self) -> list[str]:
            return []

    class FakeLocker:
        def is_device_locked(self, _device: Device, _rules: list[str]) -> bool:
            return locked

    yield FakeFirewall(), FakeLocker()


def test_device_detail_returns_enriched_payload(monkeypatch):
    repo = InMemoryDeviceRepository(
        [Device(name="Gaming Laptop", mac="aa:bb:cc:dd:ee:ff", type="computer", owner="kade")]
    )
    monkeypatch.setattr("backend.services.get_device_repository", lambda: repo)
    monkeypatch.setattr("backend.services.lookup_mac_vendor", lambda mac: "VendorCo")

    service = DummyNetworkService()
    service.detail_payload = {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "10.0.0.42",
        "hostname": "gamebox",
        "last_seen": 1_700_000_000_000,
        "is_wired": False,
        "signal": -38,
        "ap_mac": "00:11:22:33:44:55",
    }
    service.traffic_samples = [
        {"time": 1_700_000_000_000, "rx_bytes": 1024, "tx_bytes": 2048},
        {"time": 1_700_000_300_000, "rx_bytes": 512, "tx_bytes": 1024},
    ]
    service.dpi_rows = [
        {
            "client_mac": "aa:bb:cc:dd:ee:ff",
            "app": "YouTube",
            "cat": "Streaming Media",
            "rx_bytes": 5_000_000,
            "tx_bytes": 1_000_000,
        },
        {
            "client_mac": "aa:bb:cc:dd:ee:ff",
            "app": "Instagram",
            "cat": "Social Networks",
            "rx_bytes": 2_000_000,
            "tx_bytes": 500_000,
        },
    ]

    monkeypatch.setattr("backend.services.NetworkDeviceService", lambda _client: service)
    monkeypatch.setattr(
        "backend.services.locker_context",
        lambda: _fake_locker_context(locked=True),
    )

    encoded_mac = quote("aa:bb:cc:dd:ee:ff", safe="")
    response = client.get(f"/api/devices/{encoded_mac}/detail", params={"lookback_minutes": 60})
    assert response.status_code == 200
    data = response.json()

    assert data["mac"] == "aa:bb:cc:dd:ee:ff"
    assert data["locked"] is True
    assert data["vendor"] == "VendorCo"
    assert data["ip"] == "10.0.0.42"
    assert data["connection"] == "wireless"
    assert data["online"] is True
    assert data["network_name"] == "gamebox"
    assert "00:11:22:33:44:55" in data["destinations"]
    traffic = data["traffic"]
    assert traffic["interval_minutes"] == 60
    assert traffic["total_rx_bytes"] == 1536
    assert traffic["total_tx_bytes"] == 3072
    assert len(traffic["samples"]) == 2
    assert len(data["dpi_applications"]) == 2
    assert data["dpi_applications"][0]["application"] == "YouTube"


def test_device_detail_unknown_mac_returns_404(monkeypatch):
    repo = InMemoryDeviceRepository([])
    monkeypatch.setattr("backend.services.get_device_repository", lambda: repo)

    encoded_mac = quote("11:22:33:44:55:66", safe="")
    response = client.get(f"/api/devices/{encoded_mac}/detail")
    assert response.status_code == 404
