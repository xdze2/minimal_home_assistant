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


def find_gaps(series: pd.Series, max_gap: timedelta = MAX_GAP) -> list[Gap]:
    if series.empty or len(series) < 2:
        return []
    idx = series.dropna().index.sort_values()
    if len(idx) < 2:
        return []
    deltas = idx.to_series().diff()
    gaps: list[Gap] = []
    for i, d in enumerate(deltas):
        if pd.isna(d):
            continue
        if d > max_gap:
            gaps.append(Gap(start=idx[i - 1], end=idx[i]))
    return gaps


def coverage(series: pd.Series, window_start, window_end, max_gap: timedelta = MAX_GAP) -> float:
    """Fraction of the window covered by samples spaced ≤ max_gap apart."""
    total = (window_end - window_start).total_seconds()
    if total <= 0 or series.empty:
        return 0.0
    gap_total = sum(g.duration.total_seconds() for g in find_gaps(series, max_gap))
    return max(0.0, 1.0 - gap_total / total)
