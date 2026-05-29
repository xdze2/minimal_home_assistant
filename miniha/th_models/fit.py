"""1R1C baseline fit.

Model:
    C · dT_in/dt = (T_out - T_in) / R

Discretised on a uniform grid of step Δt:
    (T_in[k+1] - T_in[k]) / Δt = (1 / (R·C)) · (T_out[k] - T_in[k])

Let α = Δt / (R·C). OLS on:
    y = α · x        where  x = T_out - T_in,  y = ΔT_in / Δt · Δt = ΔT_in

We fit  ΔT_in  vs  Δt · (T_out - T_in)  — slope = 1/(R·C) = 1/τ.

Only τ = R·C is identifiable from temperatures alone (no heat-flux input
means R and C are coupled by a scale). We report τ. R and C will become
separable once a power input is added.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


GRID = "15min"


@dataclass
class FitResult:
    tau_hours: float          # R·C, in hours
    tau_stderr_hours: float
    n_samples: int
    rmse: float               # residual RMSE on the regression target (°C)


def prepare(
    indoor: pd.Series,
    outdoor: pd.Series,
    grid: str = GRID,
) -> pd.DataFrame:
    """Align indoor + outdoor onto a uniform grid.

    Indoor: mean within each bucket.
    Outdoor: time-interpolated onto bucket starts (source is hourly).
    Rows with any NaN are dropped.
    """
    indoor = indoor.dropna().sort_index()
    outdoor = outdoor.dropna().sort_index()
    if indoor.empty or outdoor.empty:
        return pd.DataFrame(columns=["T_in", "T_out"])

    t0 = max(indoor.index.min(), outdoor.index.min()).ceil(grid)
    t1 = min(indoor.index.max(), outdoor.index.max()).floor(grid)
    if t1 <= t0:
        return pd.DataFrame(columns=["T_in", "T_out"])

    grid_idx = pd.date_range(t0, t1, freq=grid)

    t_in = indoor.resample(grid).mean().reindex(grid_idx)

    out_union = outdoor.reindex(outdoor.index.union(grid_idx)).interpolate(method="time")
    t_out = out_union.reindex(grid_idx)

    df = pd.DataFrame({"T_in": t_in, "T_out": t_out}).dropna()
    return df


def fit_1r1c(df: pd.DataFrame) -> FitResult:
    """OLS for slope α = Δt / τ on:  ΔT_in  =  α · (T_out - T_in).

    df must come from `prepare` (uniform grid, no NaN).
    """
    if len(df) < 3:
        raise ValueError(f"not enough samples to fit ({len(df)})")

    dt = (df.index[1] - df.index[0]).total_seconds()  # uniform grid
    t_in = df["T_in"].to_numpy()
    t_out = df["T_out"].to_numpy()

    x = (t_out[:-1] - t_in[:-1])
    y = (t_in[1:] - t_in[:-1])
    n = x.size

    # OLS through origin: slope = sum(xy)/sum(x²).
    sxx = float(np.dot(x, x))
    sxy = float(np.dot(x, y))
    if sxx <= 0:
        raise ValueError("degenerate regressor (T_out ≡ T_in)")
    alpha = sxy / sxx

    resid = y - alpha * x
    dof = max(n - 1, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    alpha_var = sigma2 / sxx

    tau_s = dt / alpha
    # σ(τ) via 1/α: σ(1/α) ≈ σ(α)/α²  →  σ(τ) = dt · σ(α) / α²
    tau_stderr_s = dt * float(np.sqrt(alpha_var)) / (alpha * alpha)
    rmse = float(np.sqrt(np.dot(resid, resid) / n))

    return FitResult(
        tau_hours=tau_s / 3600.0,
        tau_stderr_hours=abs(tau_stderr_s) / 3600.0,
        n_samples=n,
        rmse=rmse,
    )


def simulate(df: pd.DataFrame, tau_hours: float) -> pd.Series:
    """Forward-integrate the 1R1C ODE with T_in[0] taken from observations.

    Uses the same discretisation as the fit:
        T_in[k+1] = T_in[k] + α · (T_out[k] - T_in[k])
    """
    if df.empty:
        return pd.Series(dtype="float64", name="T_in_model")

    dt = (df.index[1] - df.index[0]).total_seconds()
    alpha = dt / (tau_hours * 3600.0)

    t_in = df["T_in"].to_numpy()
    t_out = df["T_out"].to_numpy()
    n = t_in.size

    sim = np.empty(n)
    sim[0] = t_in[0]
    for k in range(n - 1):
        sim[k + 1] = sim[k] + alpha * (t_out[k] - sim[k])

    return pd.Series(sim, index=df.index, name="T_in_model")
