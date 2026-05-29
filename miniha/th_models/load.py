"""Pull each series' segments from InfluxDB and stitch them together."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from ..config import config
from ..influx_interface import InfluxInterface
from .config import RoomConfig, Segment, SeriesSpec


def make_client() -> InfluxInterface:
    return InfluxInterface(host=config.INFLUX_HOST, port=config.INFLUX_PORT, database=config.INFLUX_DB)


def _segment_window(seg: Segment, win_start: datetime, win_end: datetime) -> tuple[datetime, datetime] | None:
    start = max(seg.from_, win_start) if seg.from_ else win_start
    end = min(seg.to, win_end) if seg.to else win_end
    if start >= end:
        return None
    return start, end


def load_segment(
    client: InfluxInterface,
    seg: Segment,
    start: datetime,
    end: datetime,
) -> pd.Series:
    wheres = [(k, v) for k, v in seg.tags.items()]
    raw = client.query_df(
        measurement=seg.measurement,
        field_list=[seg.field_name],
        start=start.isoformat(),
        end=end.isoformat(),
        wheres=wheres,
    )
    if not raw:
        return pd.Series(dtype="float64", name=seg.field_name)
    # raw is dict[tuple, DataFrame]; with no group_by there is one entry.
    df = next(iter(raw.values()))
    s = df[seg.field_name]
    s.index = pd.to_datetime(s.index, utc=True)
    return s


def load_series(client: InfluxInterface, spec: SeriesSpec, window_start: datetime, window_end: datetime) -> pd.Series:
    parts: list[pd.Series] = []
    for seg in spec.segments:
        w = _segment_window(seg, window_start, window_end)
        if w is None:
            continue
        s = load_segment(client, seg, w[0], w[1])
        if not s.empty:
            parts.append(s)
    if not parts:
        return pd.Series(dtype="float64", name=spec.role)
    out = pd.concat(parts).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    out.name = spec.role
    return out


def load_room(config: RoomConfig) -> dict[str, pd.Series]:
    client = make_client()
    out: dict[str, pd.Series] = {}
    for role, spec in config.series.items():
        out[role] = load_series(client, spec, config.window.start, config.window.end)
    return out
