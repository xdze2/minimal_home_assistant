"""1R1C baseline fit with a constant heat-input term.

Model:
    C · dT_in/dt = (T_out - T_in) / R  +  Q0

Discretised on a uniform grid of step Δt:
    ΔT_in = α · (T_out - T_in)  +  β
        α = Δt / τ          (τ = R·C)
        β = Δt · Q0 / C

OLS on (slope α, intercept β). Identifiable quantities:
    τ        = Δt / α
    ΔT_eq    = β / α  =  Q0 · R        steady-state lift above outdoor

R, C, Q0 individually remain coupled by a scale until a measured input
(e.g. solar) is added.
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
    dT_eq: float              # steady-state lift above outdoor, Q0·R, in °C
    dT_eq_stderr: float
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
    """OLS for (α, β) on:  ΔT_in = α · (T_out - T_in) + β.

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

    X = np.column_stack([x, np.ones_like(x)])
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta = float(coef[0]), float(coef[1])
    if alpha <= 0:
        raise ValueError(f"non-physical fit: α={alpha:.3g} (expected > 0)")

    resid = y - (alpha * x + beta)
    dof = max(n - 2, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    var_alpha = float(cov[0, 0])
    var_beta = float(cov[1, 1])
    cov_ab = float(cov[0, 1])

    tau_s = dt / alpha
    tau_stderr_s = dt * np.sqrt(var_alpha) / (alpha * alpha)

    dT_eq = beta / alpha
    # σ(β/α)² ≈ (1/α)² var_β + (β/α²)² var_α − 2(β/α³) cov_αβ
    var_dT_eq = (
        var_beta / (alpha ** 2)
        + (beta ** 2) * var_alpha / (alpha ** 4)
        - 2 * beta * cov_ab / (alpha ** 3)
    )
    dT_eq_stderr = float(np.sqrt(max(var_dT_eq, 0.0)))

    rmse = float(np.sqrt(np.dot(resid, resid) / n))

    return FitResult(
        tau_hours=tau_s / 3600.0,
        tau_stderr_hours=abs(tau_stderr_s) / 3600.0,
        dT_eq=dT_eq,
        dT_eq_stderr=dT_eq_stderr,
        n_samples=n,
        rmse=rmse,
    )


def simulate(df: pd.DataFrame, tau_hours: float, dT_eq: float = 0.0) -> pd.Series:
    """Forward-integrate with T_in[0] taken from observations.

    Same discretisation as the fit, with β = α · ΔT_eq:
        T_in[k+1] = T_in[k] + α · (T_out[k] - T_in[k] + ΔT_eq)
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
        sim[k + 1] = sim[k] + alpha * (t_out[k] - sim[k] + dT_eq)

    return pd.Series(sim, index=df.index, name="T_in_model")
