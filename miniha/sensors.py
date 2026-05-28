"""Sensor registry: loads `config/sensors.yaml` and exposes rooms + sensors.

The webapp uses this to translate raw Influx tag values (e.g. `sensors/thE`,
`C0E434E6AA1C`) into user-facing labels ("Living room – thE") and to know
which sensors provide outdoor temperature.

Hot-reloads in dev when the YAML file's mtime changes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


DEFAULT_PATH = "config/sensors.yaml"


@dataclass(frozen=True)
class Room:
    id: str
    label: str


@dataclass(frozen=True)
class Sensor:
    id: str
    source: str
    match: dict[str, str]
    room: str | None
    kind: str
    provides_outdoor: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class SensorRegistry:
    def __init__(self, rooms: list[Room], sensors: list[Sensor]) -> None:
        self.rooms: list[Room] = rooms
        self.sensors: list[Sensor] = sensors
        self._room_by_id: dict[str, Room] = {r.id: r for r in rooms}

    def room(self, room_id: str) -> Room | None:
        return self._room_by_id.get(room_id)

    def sensors_for_source(self, source: str) -> list[Sensor]:
        return [s for s in self.sensors if s.source == source]

    def outdoor_sensors(self) -> list[Sensor]:
        return [s for s in self.sensors if s.provides_outdoor]

    def find_sensor(self, source: str, tags: dict[str, str]) -> Sensor | None:
        """Find the sensor whose `match` is a subset of the given tags."""
        for s in self.sensors:
            if s.source != source:
                continue
            if all(tags.get(k) == v for k, v in s.match.items()):
                return s
        return None

    def label_for(self, sensor: Sensor) -> str:
        """User-facing label combining room + sensor id."""
        room = self.room(sensor.room) if sensor.room else None
        return f"{room.label} – {sensor.id}" if room else sensor.id


_CACHE: dict[str, tuple[float, SensorRegistry]] = {}


def load_sensors(path: str | None = None) -> SensorRegistry:
    """Load (and cache) the sensor registry. Reloads on file mtime change."""
    p = Path(path or os.environ.get("MINIHA_SENSORS") or DEFAULT_PATH)
    mtime = p.stat().st_mtime
    cached = _CACHE.get(str(p))
    if cached and cached[0] == mtime:
        return cached[1]

    with p.open("r") as f:
        raw = yaml.safe_load(f) or {}

    rooms = [Room(id=r["id"], label=r.get("label", r["id"])) for r in raw.get("rooms", [])]
    room_ids = {r.id for r in rooms}

    sensors: list[Sensor] = []
    seen_ids: set[str] = set()
    for entry in raw.get("sensors", []):
        sid = entry["id"]
        if sid in seen_ids:
            raise ValueError(f"Duplicate sensor id in {p}: {sid}")
        seen_ids.add(sid)

        room_id = entry.get("room")
        if room_id and room_id not in room_ids:
            print(f"[sensors] WARN {sid}: room '{room_id}' not declared; treating as unmapped")
            room_id = None

        known = {"id", "source", "match", "room", "kind", "provides_outdoor"}
        extra = {k: v for k, v in entry.items() if k not in known}

        sensors.append(Sensor(
            id=sid,
            source=entry["source"],
            match=dict(entry.get("match") or {}),
            room=room_id,
            kind=entry.get("kind", "unknown"),
            provides_outdoor=bool(entry.get("provides_outdoor", False)),
            extra=extra,
        ))

    unmapped = [s.id for s in sensors if s.room is None]
    if unmapped:
        print(f"[sensors] WARN unmapped (will be skipped in queries): {unmapped}")

    registry = SensorRegistry(rooms=rooms, sensors=sensors)
    _CACHE[str(p)] = (mtime, registry)
    return registry
