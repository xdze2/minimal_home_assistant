"""Load and validate a room YAML config."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ..utils import normalize_to_datetime


@dataclass
class Segment:
    measurement: str
    tags: dict[str, str]
    field_name: str
    from_: datetime | None
    to: datetime | None


@dataclass
class SeriesSpec:
    role: str
    segments: list[Segment]


@dataclass
class Window:
    start: datetime
    end: datetime


@dataclass
class RoomConfig:
    path: Path
    room: str
    window: Window
    series: dict[str, SeriesSpec] = field(default_factory=dict)


def _parse_dt(val: Any) -> datetime | None:
    if val is None:
        return None
    return normalize_to_datetime(val)


def load_room_config(path: str | Path) -> RoomConfig:
    p = Path(path)
    with p.open() as f:
        raw = yaml.safe_load(f) or {}

    room = raw.get("room") or p.stem
    win = raw.get("window") or {}
    window = Window(start=_parse_dt(win.get("start")), end=_parse_dt(win.get("end")))

    series: dict[str, SeriesSpec] = {}
    for role, segs in (raw.get("series") or {}).items():
        parsed = []
        for s in segs:
            parsed.append(
                Segment(
                    measurement=s["measurement"],
                    tags=dict(s.get("tags") or {}),
                    field_name=s["field"],
                    from_=_parse_dt(s.get("from")),
                    to=_parse_dt(s.get("to")),
                )
            )
        series[role] = SeriesSpec(role=role, segments=parsed)

    return RoomConfig(path=p, room=room, window=window, series=series)


def discover_configs(user_models_dir: str | Path) -> list[Path]:
    d = Path(user_models_dir)
    if not d.exists():
        return []
    return sorted(p for p in d.glob("*.yaml") if p.is_file())
