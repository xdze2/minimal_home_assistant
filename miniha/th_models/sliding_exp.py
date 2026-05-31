"""Sliding-window exponential fit for free-decay segment detection.

Fits y(t) = (T_0 - T_inf) * exp(-(t-t0)/tau) + T_inf in fixed-length
windows stepped across an indoor-temperature series. Windows where the
fit is good (high R², plausible tau, decreasing trend) are candidate
free-decay segments — the room drifting toward an equilibrium with no
heating.

Method 4 from SEGMENTER.md. No merge step in this POC: each accepted
window is reported independently.

Fit strategy: T_inf is grid-searched a few values below the window's
final point; for each candidate the residual is linear in log-space
and solved by OLS. The best (highest R²) candidate is kept.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class WindowFit:
    t_start: pd.Timestamp
    t_end: pd.Timestamp
    tau_h: float
    T_inf: float
    T_0: float
    r2: float
    n: int


def _fit_fixed_Tinf(t: np.ndarray, y: np.ndarray, T_inf: float) -> tuple[float, float, float] | None:
    """OLS on log(y - T_inf) = log(A) - t/tau. Returns (tau, T_0, r2) or None."""
    d = y - T_inf
    if np.any(d <= 0):
        return None
    z = np.log(d)
    t_mean = t.mean()
    z_mean = z.mean()
    dt = t - t_mean
    denom = float(np.dot(dt, dt))
    if denom <= 0:
        return None
    slope = float(np.dot(dt, z - z_mean) / denom)
    if slope >= 0:
        return None
    intercept = z_mean - slope * t_mean
    tau = -1.0 / slope
    A = float(np.exp(intercept))
    T_0 = A + T_inf  # A = T_0 - T_inf at t=0

    y_pred = A * np.exp(-t / tau) + T_inf
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return tau, T_0, r2


def fit_exp_window(t_seconds: np.ndarray, y: np.ndarray) -> WindowFit | None:
    """Fit y(t) = (T_0 - T_inf) exp(-t/tau) + T_inf. t is seconds from window start.

    Grid-searches T_inf below the window's minimum value (the asymptote must be
    below all observed points for a decaying signal). Returns the best R² fit,
    or None if no candidate is admissible.
    """
    if y.size < 6:
        return None
    y_min = float(y.min())
    y_max = float(y.max())
    span = y_max - y_min
    if span <= 0:
        return None
    # Cheap pre-filter: window must be net-decreasing. Skips ~all heating/flat windows.
    if y[-1] >= y[0] - 0.2 * span:
        return None
    # Asymptote candidates: a small grid below the window minimum.
    Tinf_grid = y_min - np.linspace(0.05 * span, 1.5 * span, 6)

    best: tuple[float, float, float, float] | None = None  # (r2, tau, T_0, T_inf)
    for Tinf in Tinf_grid:
        out = _fit_fixed_Tinf(t_seconds, y, float(Tinf))
        if out is None:
            continue
        tau, T_0, r2 = out
        if best is None or r2 > best[0]:
            best = (r2, tau, T_0, float(Tinf))
    if best is None:
        return None
    r2, tau, T_0, T_inf = best
    return WindowFit(
        t_start=pd.NaT,  # filled by scan
        t_end=pd.NaT,
        tau_h=tau / 3600.0,
        T_inf=T_inf,
        T_0=T_0,
        r2=r2,
        n=int(y.size),
    )


def resample_series(series: pd.Series, resample: str) -> pd.Series:
    """Same resampling scan() uses, exposed so merge_grow can work on the
    identical uniform grid."""
    s = series.dropna().sort_index()
    if s.empty:
        return s
    return s.resample(resample).mean().interpolate(method="time", limit=3).dropna()


def scan(
    series: pd.Series,
    window_h: float,
    step_min: float,
    resample: str = "5min",
    progress: Callable[[float, str], None] | None = None,
) -> list[WindowFit]:
    """Slide a window across `series` and fit an exponential at every step.

    Returns every window where a fit was found (no quality filter — apply
    thresholds downstream so the UI can re-filter without re-scanning).
    `progress(fraction, message)` is called periodically if provided.
    """
    t0 = time.perf_counter()
    log.info("scan start: window_h=%s step_min=%s resample=%s in=%d points",
             window_h, step_min, resample, len(series))

    s = resample_series(series, resample)
    if s.empty:
        log.info("scan: empty after resample")
        return []

    grid_sec = pd.Timedelta(resample).total_seconds()
    win_n = max(int(window_h * 3600 // grid_sec), 6)
    step_n = max(int(step_min * 60 // grid_sec), 1)

    values = s.to_numpy()
    index = s.index
    t_sec = np.arange(win_n) * grid_sec  # same for every window
    n_iters = max((len(values) - win_n + 1 + step_n - 1) // step_n, 0)

    log.info("scan: grid=%d points  win_n=%d  step_n=%d  iters=%d",
             len(values), win_n, step_n, n_iters)
    if progress:
        progress(0.0, f"scanning {n_iters} windows…")

    fits: list[WindowFit] = []
    last_tick = time.perf_counter()
    for k, i in enumerate(range(0, len(values) - win_n + 1, step_n)):
        y = values[i : i + win_n]
        fit = fit_exp_window(t_sec, y)
        if fit is not None:
            fit.t_start = index[i]
            fit.t_end = index[i + win_n - 1]
            fits.append(fit)
        now = time.perf_counter()
        if progress and (now - last_tick) > 0.2:
            progress((k + 1) / max(n_iters, 1),
                     f"window {k+1}/{n_iters}  accepted={len(fits)}")
            last_tick = now

    elapsed = time.perf_counter() - t0
    log.info("scan done: %d/%d windows accepted in %.2fs (%.0f wins/s)",
             len(fits), n_iters, elapsed, n_iters / elapsed if elapsed > 0 else 0)
    if progress:
        progress(1.0, f"done: {len(fits)} accepted in {elapsed:.1f}s")
    return fits


def merge_grow(
    fits: list[WindowFit],
    series: pd.Series,
    resample: str,
    r2_min: float = 0.98,
    tau_log_tol: float = 0.2,
    Tinf_tol_C: float = 0.5,
) -> list[WindowFit]:
    """Greedy-grow merge from SEGMENTER.md §"The merge step".

    Sort accepted windows by R² (best first). Take the best as seed; extend
    one grid step at a time in each direction; accept the extension if the
    re-fit stays above r2_min and parameters don't drift more than the
    tolerances. Stop when no direction extends. Consume any windows that
    overlap the grown segment. Repeat on the remaining fits.

    `series` must be the same resampled series scan() used (call
    `resample_series` to get it). Operates on the resampled grid for speed:
    extension steps are one grid cell.
    """
    if not fits:
        return []
    s = resample_series(series, resample) if series.index.freq is None else series
    if s.empty:
        return []
    values = s.to_numpy()
    index = s.index
    grid_sec = pd.Timedelta(resample).total_seconds()

    # Map fit boundaries → integer grid positions for fast index math.
    pos_start = index.searchsorted(pd.DatetimeIndex([f.t_start for f in fits]))
    pos_end = index.searchsorted(pd.DatetimeIndex([f.t_end for f in fits]))
    remaining = sorted(
        range(len(fits)),
        key=lambda k: fits[k].r2,
        reverse=True,
    )
    consumed: set[int] = set()
    merged: list[WindowFit] = []

    def fit_range(lo: int, hi: int) -> WindowFit | None:
        if hi - lo + 1 < 6:
            return None
        t = np.arange(hi - lo + 1) * grid_sec
        return fit_exp_window(t, values[lo : hi + 1])

    for idx in remaining:
        if idx in consumed:
            continue
        seed = fits[idx]
        lo, hi = int(pos_start[idx]), int(pos_end[idx])
        tau_ref, Tinf_ref = seed.tau_h, seed.T_inf

        while True:
            extended = False
            for direction in (-1, +1):
                new_lo = lo - 1 if direction < 0 else lo
                new_hi = hi if direction < 0 else hi + 1
                if new_lo < 0 or new_hi >= len(values):
                    continue
                f = fit_range(new_lo, new_hi)
                if (
                    f is not None
                    and f.r2 >= r2_min
                    and abs(np.log(max(f.tau_h, 1e-6)) - np.log(max(tau_ref, 1e-6))) < tau_log_tol
                    and abs(f.T_inf - Tinf_ref) < Tinf_tol_C
                ):
                    lo, hi = new_lo, new_hi
                    extended = True
            if not extended:
                break

        final = fit_range(lo, hi)
        if final is None:
            continue
        final.t_start = index[lo]
        final.t_end = index[hi]
        merged.append(final)

        # Consume every remaining fit whose range overlaps [lo, hi] at all.
        for j in remaining:
            if j in consumed:
                continue
            if int(pos_start[j]) <= hi and int(pos_end[j]) >= lo:
                consumed.add(j)

    merged.sort(key=lambda f: f.t_start)
    return merged


def to_dataframe(fits: list[WindowFit]) -> pd.DataFrame:
    if not fits:
        return pd.DataFrame(
            columns=["t_start", "t_end", "tau_h", "T_inf", "T_0", "r2", "n"]
        )
    return pd.DataFrame(
        [
            {
                "t_start": f.t_start,
                "t_end": f.t_end,
                "tau_h": f.tau_h,
                "T_inf": f.T_inf,
                "T_0": f.T_0,
                "r2": f.r2,
                "n": f.n,
            }
            for f in fits
        ]
    )
