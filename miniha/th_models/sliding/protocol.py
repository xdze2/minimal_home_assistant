"""Shared types and Fitter protocol for sliding-window model fitting.

The sliding-window machinery (scan + merge_grow) is model-agnostic.
A Fitter knows how to:
  - fit a model to a short window of aligned timeseries data
  - reconstruct the fitted curve from its parameters
  - decide whether two WindowResults are close enough to merge

Any model (free-decay exponential, 1R1C, 2R2C, ...) can be plugged in
by implementing the Fitter protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd


@dataclass
class WindowResult:
    """Output of fitting one window."""
    t_start: pd.Timestamp
    t_end: pd.Timestamp
    params: dict[str, float]   # model-specific: tau_h, T_inf, dT_eq, g_solar, ...
    quality: float             # primary quality metric (higher = better); e.g. R² or -RMSE
    n: int                     # number of samples in the window

    def curve(self, times: pd.DatetimeIndex) -> np.ndarray:
        """Reconstruct the fitted curve at arbitrary timestamps.

        Delegated to the fitter that produced this result via the stored
        _curve_fn. Set by the fitter before returning — callers treat it
        as a method but fitters inject it as a callable.
        """
        return self._curve_fn(times)

    # Injected by the fitter; not part of the public constructor.
    _curve_fn: object = field(default=None, repr=False, compare=False)


class Fitter(Protocol):
    """Protocol every sliding-window fitter must satisfy."""

    def fit(
        self,
        t_sec: np.ndarray,
        inputs: dict[str, np.ndarray],
    ) -> WindowResult | None:
        """Fit the model to one window.

        Args:
            t_sec: seconds from window start, shape (n,), uniform grid.
            inputs: dict of aligned arrays, same length as t_sec.
                    Must include at least "T_in". Fitter declares which
                    keys it needs; scan() passes all available series.

        Returns:
            WindowResult, or None if the window is inadmissible
            (too few points, non-physical fit, pre-filter failed).
        """
        ...

    def params_close(self, a: WindowResult, b: WindowResult) -> bool:
        """Return True if a and b have compatible parameters for merging."""
        ...
