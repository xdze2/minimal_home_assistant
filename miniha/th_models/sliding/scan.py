"""Generic sliding-window scan and greedy-grow merge.

Model-agnostic: the Fitter protocol supplies fitting and merge logic.
Series alignment and window slicing live here; physics lives in the fitter.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import numpy as np
import pandas as pd

from .protocol import Fitter, WindowResult

log = logging.getLogger(__name__)


def resample_inputs(
    inputs: dict[str, pd.Series],
    resample: str,
) -> dict[str, pd.Series]:
    """Resample and align all input series onto a common uniform grid.

    Each series is resampled to `resample` frequency, then interpolated
    (time method, limit=3 buckets) to fill small gaps. Rows where *any*
    series is NaN after interpolation are dropped from all series, so the
    returned dict always has identically-indexed series.
    """
    resampled = {}
    for name, s in inputs.items():
        s = s.dropna().sort_index()
        if s.empty:
            resampled[name] = s
            continue
        resampled[name] = (
            s.resample(resample).mean()
            .interpolate(method="time", limit=3)
        )

    if not resampled:
        return resampled

    # Align to common index (intersection after dropna).
    df = pd.DataFrame(resampled).dropna()
    return {name: df[name] for name in resampled}


def scan(
    inputs: dict[str, pd.Series],
    fitter: Fitter,
    window_h: float,
    step_min: float,
    resample: str = "5min",
    progress: Callable[[float, str], None] | None = None,
) -> list[WindowResult]:
    """Slide a window across all input series and fit the model at every step.

    Returns every window where the fitter returned a result (no quality
    filter — apply thresholds downstream so the UI can re-filter without
    re-scanning).

    Args:
        inputs: dict of series, must include "T_in". All are aligned together.
        fitter: any object satisfying the Fitter protocol.
        window_h: window length in hours.
        step_min: step between window starts in minutes.
        resample: pandas frequency string for the uniform grid.
        progress: optional callback(fraction, message) for UI spinners.
    """
    t0 = time.perf_counter()

    aligned = resample_inputs(inputs, resample)
    if not aligned or "T_in" not in aligned or aligned["T_in"].empty:
        log.info("scan: empty after resample")
        return []

    ref = aligned["T_in"]
    grid_sec = pd.Timedelta(resample).total_seconds()
    win_n = max(int(window_h * 3600 // grid_sec), 6)
    step_n = max(int(step_min * 60 // grid_sec), 1)
    n_pts = len(ref)
    n_iters = max((n_pts - win_n + 1 + step_n - 1) // step_n, 0)

    log.info(
        "scan: grid=%d pts  win_n=%d  step_n=%d  iters=%d  fitter=%s",
        n_pts, win_n, step_n, n_iters, type(fitter).__name__,
    )
    if progress:
        progress(0.0, f"scanning {n_iters} windows…")

    # Pre-extract numpy arrays for speed.
    arrays = {name: s.to_numpy() for name, s in aligned.items()}
    index = ref.index
    t_sec = np.arange(win_n) * grid_sec  # same relative time for every window

    results: list[WindowResult] = []
    last_tick = time.perf_counter()

    for k, i in enumerate(range(0, n_pts - win_n + 1, step_n)):
        window_inputs = {name: arr[i : i + win_n] for name, arr in arrays.items()}
        result = fitter.fit(t_sec, window_inputs)
        if result is not None:
            result.t_start = index[i]
            result.t_end = index[i + win_n - 1]
            results.append(result)

        now = time.perf_counter()
        if progress and (now - last_tick) > 0.2:
            progress(
                (k + 1) / max(n_iters, 1),
                f"window {k+1}/{n_iters}  accepted={len(results)}",
            )
            last_tick = now

    elapsed = time.perf_counter() - t0
    log.info(
        "scan done: %d/%d accepted in %.2fs (%.0f wins/s)",
        len(results), n_iters, elapsed, n_iters / elapsed if elapsed > 0 else 0,
    )
    if progress:
        progress(1.0, f"done: {len(results)} accepted in {elapsed:.1f}s")

    return results


def merge_grow(
    results: list[WindowResult],
    inputs: dict[str, pd.Series],
    fitter: Fitter,
    resample: str,
    quality_min: float = 0.98,
) -> list[WindowResult]:
    """Greedy-grow merge.

    Sort by quality (best first). Take the best as seed; extend one grid
    step at a time in each direction; accept the extension if the re-fit
    quality stays above r2_min and fitter.params_close() agrees. Stop when
    no direction extends. Consume overlapping windows. Repeat.
    """
    if not results:
        return []

    aligned = resample_inputs(inputs, resample)
    if not aligned or "T_in" not in aligned:
        return []

    ref = aligned["T_in"]
    if ref.empty:
        return []

    arrays = {name: s.to_numpy() for name, s in aligned.items()}
    index = ref.index
    grid_sec = pd.Timedelta(resample).total_seconds()

    pos_start = index.searchsorted(pd.DatetimeIndex([r.t_start for r in results]))
    pos_end = index.searchsorted(pd.DatetimeIndex([r.t_end for r in results]))

    remaining = sorted(range(len(results)), key=lambda k: results[k].quality, reverse=True)
    consumed: set[int] = set()
    merged: list[WindowResult] = []

    def fit_range(lo: int, hi: int) -> WindowResult | None:
        n = hi - lo + 1
        if n < 6:
            return None
        t_sec = np.arange(n) * grid_sec
        window_inputs = {name: arr[lo : hi + 1] for name, arr in arrays.items()}
        return fitter.fit(t_sec, window_inputs)

    for idx in remaining:
        if idx in consumed:
            continue
        lo, hi = int(pos_start[idx]), int(pos_end[idx])
        seed = results[idx]

        while True:
            extended = False
            for direction in (-1, +1):
                new_lo = lo - 1 if direction < 0 else lo
                new_hi = hi if direction < 0 else hi + 1
                if new_lo < 0 or new_hi >= len(ref):
                    continue
                f = fit_range(new_lo, new_hi)
                if f is not None and f.quality >= quality_min and fitter.params_close(seed, f):
                    lo, hi = new_lo, new_hi
                    seed = f
                    extended = True
            if not extended:
                break

        final = fit_range(lo, hi)
        if final is None:
            continue
        final.t_start = index[lo]
        final.t_end = index[hi]
        merged.append(final)

        for j in remaining:
            if j not in consumed and int(pos_start[j]) <= hi and int(pos_end[j]) >= lo:
                consumed.add(j)

    merged.sort(key=lambda r: r.t_start)
    return merged


def to_dataframe(results: list[WindowResult]) -> pd.DataFrame:
    if not results:
        return pd.DataFrame(columns=["t_start", "t_end", "quality", "n"])
    rows = []
    for r in results:
        row = {"t_start": r.t_start, "t_end": r.t_end, "quality": r.quality, "n": r.n}
        row.update(r.params)
        rows.append(row)
    return pd.DataFrame(rows)
