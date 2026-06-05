"""Forward simulation for thermalnodes.

Real solvers (IVP + ZOH) are TODO. This module currently exports only
simulate_mock(), which returns plausible-looking sinusoidal temperatures
so the UI can be developed without a working solver.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .assemble import AssembledSystem


@dataclass
class SimResult:
    t: np.ndarray                  # Unix timestamps [seconds], shape (n_steps,)
    temps: dict[str, np.ndarray]   # mass_id → temperature array [°C]


def simulate_mock(
    system: AssembledSystem,
    start: str,
    end: str,
    dt_minutes: int = 15,
) -> SimResult:
    """Return fake sinusoidal temperatures for every mass node.

    Does not use the model matrices at all — purely for UI development.
    Each mass gets a slightly different phase and amplitude so the chart
    shows distinct, non-trivial curves.
    """
    import datetime

    t0 = datetime.datetime.fromisoformat(start).timestamp()
    t1 = datetime.datetime.fromisoformat(end).timestamp()
    dt = dt_minutes * 60
    t = np.arange(t0, t1, dt, dtype=float)

    temps: dict[str, np.ndarray] = {}
    for idx, mass_id in enumerate(system.mass_ids):
        phase = idx * math.pi / max(len(system.mass_ids), 1)
        # daily cycle (period 24 h) + slow drift (period 10 days)
        daily = 3.0 * np.sin(2 * math.pi * (t - t0) / 86400 + phase)
        slow  = 2.0 * np.sin(2 * math.pi * (t - t0) / (10 * 86400) + phase)
        temps[mass_id] = 18.0 + daily + slow

    return SimResult(t=t, temps=temps)
