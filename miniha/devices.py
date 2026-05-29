"""Device registry: loads `config/devices.yaml` (LAN-addressed hardware).

Currently covers Daikin air conditioners. Each entry maps a physical IP
to a room id (matching `config/sensors.yaml`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_PATH = "config/devices.yaml"


@dataclass(frozen=True)
class DaikinDevice:
    id: str
    ip: str
    room: str | None


@dataclass(frozen=True)
class DeviceRegistry:
    daikin: list[DaikinDevice]


def load_devices(path: str | None = None) -> DeviceRegistry:
    p = Path(path or os.environ.get("MINIHA_DEVICES") or DEFAULT_PATH)
    with p.open("r") as f:
        raw = yaml.safe_load(f) or {}

    daikin: list[DaikinDevice] = []
    seen: set[str] = set()
    for entry in raw.get("daikin", []):
        did = entry["id"]
        if did in seen:
            raise ValueError(f"Duplicate daikin id in {p}: {did}")
        seen.add(did)
        daikin.append(DaikinDevice(
            id=did,
            ip=entry["ip"],
            room=entry.get("room"),
        ))

    return DeviceRegistry(daikin=daikin)
