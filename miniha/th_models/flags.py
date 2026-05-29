"""Flag gaps in a series.

Requirement: data should be at least hourly. Anything longer than 1h between
consecutive samples is flagged as a gap. No forward-fill, no value correction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd

MAX_GAP = timedelta(hours=1)


@dataclass
class Gap:
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def duration(self) -> timedelta:
        return (self.end - self.start).to_pytimedelta()


def _align_tz(ts: pd.Timestamp | None, tz) -> pd.Timestamp | None:
    if ts is None:
        return None
    if tz is None:
        return ts.tz_convert(None) if ts.tz is not None else ts
    return ts.tz_localize(tz) if ts.tz is None else ts.tz_convert(tz)


def find_gaps(
    series: pd.Series,
    max_gap: timedelta = MAX_GAP,
    window_start: pd.Timestamp | None = None,
    window_end: pd.Timestamp | None = None,
) -> list[Gap]:
    """Gaps > max_gap inside [window_start, window_end].

    When window bounds are given, missing data at the edges (before the first
    sample or after the last) counts as a gap too — otherwise an empty series
    on a configured window would look gap-free.
    """
    ws = pd.Timestamp(window_start) if window_start is not None else None
    we = pd.Timestamp(window_end) if window_end is not None else None

    idx = series.dropna().index.sort_values() if not series.empty else pd.DatetimeIndex([])
    idx_tz = getattr(idx, "tz", None)
    ws = _align_tz(ws, idx_tz)
    we = _align_tz(we, idx_tz)
    if ws is not None and we is not None:
        idx = idx[(idx >= ws) & (idx < we)]

    gaps: list[Gap] = []

    if ws is not None and (len(idx) == 0 or idx[0] - ws > max_gap):
        gaps.append(Gap(start=ws, end=idx[0] if len(idx) else we))

    if len(idx) >= 2:
        deltas = idx.to_series().diff()
        for i, d in enumerate(deltas):
            if pd.isna(d):
                continue
            if d > max_gap:
                gaps.append(Gap(start=idx[i - 1], end=idx[i]))

    if we is not None and len(idx) and we - idx[-1] > max_gap:
        gaps.append(Gap(start=idx[-1], end=we))

    return gaps


def coverage(series: pd.Series, window_start, window_end, max_gap: timedelta = MAX_GAP) -> float:
    """Fraction of the window covered by samples spaced ≤ max_gap apart."""
    total = (window_end - window_start).total_seconds()
    if total <= 0:
        return 0.0
    gaps = find_gaps(series, max_gap, window_start=window_start, window_end=window_end)
    gap_total = sum(g.duration.total_seconds() for g in gaps)
    return max(0.0, 1.0 - gap_total / total)
