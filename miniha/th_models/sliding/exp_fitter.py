"""Free-decay exponential fitter.

Fits y(t) = (T_0 - T_inf) * exp(-t / tau) + T_inf on windows where
T_in is decaying freely (no heating, no solar driving needed).

This is the same physics as the original sliding_exp.py, re-expressed
behind the Fitter protocol so it can be used with the generic scan/merge.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .protocol import Fitter, WindowResult


@dataclass
class ExpFitterConfig:
    tau_min_h: float = 2.0
    tau_max_h: float = 50.0
    tau_log_tol: float = 0.2    # merge: |log τ_a - log τ_b| < tol
    Tinf_tol_C: float = 0.5     # merge: |T∞_a - T∞_b| < tol (°C)


def _fit_fixed_Tinf(
    t: np.ndarray, y: np.ndarray, T_inf: float
) -> tuple[float, float, float] | None:
    """OLS on log(y - T_inf). Returns (tau_s, T_0, r2) or None."""
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
    tau_s = -1.0 / slope
    A = float(np.exp(intercept))
    T_0 = A + T_inf

    y_pred = A * np.exp(-t / tau_s) + T_inf
    ss_res = float(np.sum((y - y_pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return tau_s, T_0, r2


class ExpFitter:
    """Fitter protocol implementation for free-decay exponential windows."""

    def __init__(self, config: ExpFitterConfig | None = None) -> None:
        self.config = config or ExpFitterConfig()

    def fit(
        self,
        t_sec: np.ndarray,
        inputs: dict[str, np.ndarray],
    ) -> WindowResult | None:
        y = inputs.get("T_in")
        if y is None or y.size < 6:
            return None

        y_min = float(y.min())
        y_max = float(y.max())
        span = y_max - y_min
        if span <= 0:
            return None
        # Pre-filter: window must be net-decreasing.
        if y[-1] >= y[0] - 0.2 * span:
            return None

        # Grid-search T_inf below the window minimum.
        Tinf_grid = y_min - np.linspace(0.05 * span, 1.5 * span, 6)
        best: tuple[float, float, float, float] | None = None  # (r2, tau_s, T_0, T_inf)
        for Tinf in Tinf_grid:
            out = _fit_fixed_Tinf(t_sec, y, float(Tinf))
            if out is None:
                continue
            tau_s, T_0, r2 = out
            if best is None or r2 > best[0]:
                best = (r2, tau_s, T_0, float(Tinf))

        if best is None:
            return None

        r2, tau_s, T_0, T_inf = best
        tau_h = tau_s / 3600.0
        cfg = self.config
        if not (cfg.tau_min_h <= tau_h <= cfg.tau_max_h):
            return None

        params = {"tau_h": tau_h, "T_inf": T_inf, "T_0": T_0}

        def curve_fn(times: pd.DatetimeIndex, _t0=t_sec[0], _T0=T_0, _Ti=T_inf, _tau=tau_s) -> np.ndarray:
            # times is absolute; compute seconds relative to window start
            # (caller must pass times within [t_start, t_end])
            t_rel = np.array([(ts - times[0]).total_seconds() for ts in times], dtype=float)
            return (_T0 - _Ti) * np.exp(-t_rel / _tau) + _Ti

        result = WindowResult(
            t_start=pd.NaT,
            t_end=pd.NaT,
            params=params,
            quality=r2,
            n=int(y.size),
        )
        result._curve_fn = curve_fn
        return result

    def params_close(self, a: WindowResult, b: WindowResult) -> bool:
        cfg = self.config
        tau_a = max(a.params["tau_h"], 1e-6)
        tau_b = max(b.params["tau_h"], 1e-6)
        return (
            abs(np.log(tau_a) - np.log(tau_b)) < cfg.tau_log_tol
            and abs(a.params["T_inf"] - b.params["T_inf"]) < cfg.Tinf_tol_C
        )
