"""Static device inventory definitions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Device:
    """Represents a known network device."""

    name: str
    mac: str
    type: str
    owner: str


DEVICES: list[Device] = [
    Device(
        name="Kade's Xbox Wired", mac="28:16:a8:ae:27:57", type="xbox", owner="kade"
    ),
    Device(
        name="Kade's Xbox Wi-Fi", mac="28:16:a8:ae:27:59", type="xbox", owner="kade"
    ),
    Device(
        name="Kade's Xbox Series X Wired",
        mac="c4:cb:76:74:4d:b8",
        type="xbox",
        owner="kade",
    ),
    Device(
        name="Kade's Xbox Series X Wi-Fi",
        mac="c4:cb:76:74:4d:b5",
        type="xbox",
        owner="kade",
    ),
    Device(
        name="Kade's Computer", mac="18:c0:4d:a9:97:48", type="computer", owner="kade"
    ),
    Device(
        name="Kade's Chromebook",
        mac="e0:2b:e9:0b:0f:3b",
        type="computer",
        owner="kade",
    ),
    Device(name="Kade's Phone", mac="62:09:2e:93:22:38", type="phone", owner="kade"),
    Device(name="Kade's TV", mac="38:c8:04:a3:4e:85", type="tv", owner="kade"),
    Device(
        name="Kade's Display", mac="d8:eb:46:8c:f8:2d", type="display", owner="kade"
    ),
    Device(name="Kade's LG TV", mac="78:45:58:f1:54:94", type="tv", owner="kade"),
    Device(
        name="Jayce's Xbox Wired", mac="bc:83:85:6f:38:01", type="xbox", owner="jayce"
    ),
    Device(
        name="Jayce's Xbox Wi-Fi", mac="bc:83:85:6f:38:03", type="xbox", owner="jayce"
    ),
    Device(
        name="Jayce's Computer", mac="04:7c:16:7e:ea:d0", type="computer", owner="jayce"
    ),
    Device(
        name="Jayce's New Computer",
        mac="10:ff:e0:32:2d:5e",
        type="computer",
        owner="jayce",
    ),
    Device(name="Jayce's TV", mac="44:d8:78:14:8c:c0", type="tv", owner="jayce"),
    Device(
        name="Jayce's Tablet", mac="e0:d0:83:73:ec:49", type="tablet", owner="jayce"
    ),
    Device(
        name="Kailah's Xbox Wired",
        mac="84:57:33:70:c7:cb",
        type="xbox",
        owner="kailah",
    ),
    Device(
        name="Kailah's Xbox Wi-Fi",
        mac="84:57:33:70:c7:cd",
        type="xbox",
        owner="kailah",
    ),
    Device(
        name="Kailah's Computer",
        mac="54:04:a6:3d:33:b7",
        type="computer",
        owner="kailah",
    ),
    Device(name="Kailah's TV", mac="44:d8:78:64:02:1e", type="tv", owner="kailah"),
    Device(
        name="Kailah's Tablet", mac="ea:13:79:bb:30:d0", type="tablet", owner="kailah"
    ),
    Device(name="House Switch", mac="74:f9:ca:ed:d2:70", type="switch", owner="house"),
    Device(name="Pink Switch", mac="74:f9:ca:f2:6f:df", type="switch", owner="house"),
    Device(
        name="Guest Bedroom TV",
        mac="00:bf:af:ad:20:6b",
        type="tv",
        owner="house",
    ),
    Device(
        name="Living Room Roku Wireles",
        mac="8c:49:62:14:a0:d5",
        type="roku",
        owner="house",
    ),
    Device(name="Oculus", mac="2c:26:17:f5:b7:00", type="oculus", owner="house"),
    Device(name="Playroom Roku", mac="10:59:32:c8:ef:92", type="roku", owner="house"),
    Device(
        name="Living Room Roku Wired",
        mac="8c:49:62:14:a0:d4",
        type="roku",
        owner="house",
    ),
]


def devices_by_owner(owner: str) -> Iterable[Device]:
    """Yield all devices belonging to a given owner."""
    lower_owner = owner.lower()
    return (device for device in DEVICES if device.owner == lower_owner)


_DEVICE_BY_MAC: dict[str, Device] = {device.mac.lower(): device for device in DEVICES}


def device_by_mac(mac: str | None) -> Device | None:
    """Return the registered device for the given MAC address, if any."""
    if not mac:
        return None
    return _DEVICE_BY_MAC.get(mac.lower())


__all__ = ["Device", "DEVICES", "devices_by_owner", "device_by_mac"]
