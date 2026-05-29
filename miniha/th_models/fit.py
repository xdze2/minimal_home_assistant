"""Grey-box single-zone thermal fit.

Model:
    C · dT_in/dt = (T_out - T_in) / R  +  Q0  +  a · I_solar

Discretised on a uniform grid of step Δt:
    ΔT_in = α · (T_out - T_in)  +  β  +  γ · I_solar
        α = Δt / τ          (τ = R·C)
        β = Δt · Q0 / C
        γ = Δt · a / C

OLS for (α, β, γ). Identifiable quantities:
    τ        = Δt / α                      thermal time constant
    ΔT_eq    = β / α  =  Q0 · R            steady-state lift from constant gain
    g_solar  = γ / α  =  a · R             steady-state lift per (W/m²) of solar

R, C, Q0, a remain individually coupled by a scale.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


GRID = "15min"


@dataclass
class FitResult:
    tau_hours: float
    tau_stderr_hours: float
    dT_eq: float                # °C, Q0·R
    dT_eq_stderr: float
    g_solar: float              # °C per (W/m²), a·R
    g_solar_stderr: float
    n_samples: int
    rmse: float                 # residual RMSE on the regression target (°C)


def prepare(
    indoor: pd.Series,
    outdoor: pd.Series,
    solar: pd.Series,
    grid: str = GRID,
) -> pd.DataFrame:
    """Align indoor + outdoor + solar onto a uniform grid.

    Indoor: mean within each bucket.
    Outdoor & solar: time-interpolated onto bucket starts (hourly sources).
    Rows with any NaN are dropped.
    """
    indoor = indoor.dropna().sort_index()
    outdoor = outdoor.dropna().sort_index()
    solar = solar.dropna().sort_index()
    if indoor.empty or outdoor.empty or solar.empty:
        return pd.DataFrame(columns=["T_in", "T_out", "I_solar"])

    t0 = max(indoor.index.min(), outdoor.index.min(), solar.index.min()).ceil(grid)
    t1 = min(indoor.index.max(), outdoor.index.max(), solar.index.max()).floor(grid)
    if t1 <= t0:
        return pd.DataFrame(columns=["T_in", "T_out", "I_solar"])

    grid_idx = pd.date_range(t0, t1, freq=grid)

    t_in = indoor.resample(grid).mean().reindex(grid_idx)

    out_union = outdoor.reindex(outdoor.index.union(grid_idx)).interpolate(method="time")
    t_out = out_union.reindex(grid_idx)

    sol_union = solar.reindex(solar.index.union(grid_idx)).interpolate(method="time")
    i_solar = sol_union.reindex(grid_idx).clip(lower=0.0)

    df = pd.DataFrame({"T_in": t_in, "T_out": t_out, "I_solar": i_solar}).dropna()
    return df


def fit_thermal(df: pd.DataFrame) -> FitResult:
    """OLS for (α, β, γ) on:  ΔT_in = α · (T_out - T_in) + β + γ · I_solar.

    df must come from `prepare` (uniform grid, no NaN, columns T_in/T_out/I_solar).
    """
    if len(df) < 4:
        raise ValueError(f"not enough samples to fit ({len(df)})")

    dt = (df.index[1] - df.index[0]).total_seconds()
    t_in = df["T_in"].to_numpy()
    t_out = df["T_out"].to_numpy()
    i_sol = df["I_solar"].to_numpy()

    x_dt = (t_out[:-1] - t_in[:-1])
    x_sol = i_sol[:-1]
    y = (t_in[1:] - t_in[:-1])
    n = y.size

    X = np.column_stack([x_dt, np.ones_like(x_dt), x_sol])
    coef, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    alpha, beta, gamma = float(coef[0]), float(coef[1]), float(coef[2])
    if alpha <= 0:
        raise ValueError(f"non-physical fit: α={alpha:.3g} (expected > 0)")

    resid = y - X @ coef
    dof = max(n - 3, 1)
    sigma2 = float(np.dot(resid, resid) / dof)
    cov = sigma2 * np.linalg.inv(X.T @ X)
    var_a = float(cov[0, 0])
    var_b = float(cov[1, 1])
    var_g = float(cov[2, 2])
    cov_ab = float(cov[0, 1])
    cov_ag = float(cov[0, 2])

    tau_s = dt / alpha
    tau_stderr_s = dt * np.sqrt(var_a) / (alpha * alpha)

    # σ(r/α)² ≈ var_r/α² + r²·var_α/α⁴ − 2·r·cov(α,r)/α³
    dT_eq = beta / alpha
    var_dT_eq = (
        var_b / (alpha ** 2)
        + (beta ** 2) * var_a / (alpha ** 4)
        - 2 * beta * cov_ab / (alpha ** 3)
    )

    g_solar = gamma / alpha
    var_g_solar = (
        var_g / (alpha ** 2)
        + (gamma ** 2) * var_a / (alpha ** 4)
        - 2 * gamma * cov_ag / (alpha ** 3)
    )

    rmse = float(np.sqrt(np.dot(resid, resid) / n))

    return FitResult(
        tau_hours=tau_s / 3600.0,
        tau_stderr_hours=abs(tau_stderr_s) / 3600.0,
        dT_eq=dT_eq,
        dT_eq_stderr=float(np.sqrt(max(var_dT_eq, 0.0))),
        g_solar=g_solar,
        g_solar_stderr=float(np.sqrt(max(var_g_solar, 0.0))),
        n_samples=n,
        rmse=rmse,
    )


def simulate(
    df: pd.DataFrame,
    tau_hours: float,
    dT_eq: float = 0.0,
    g_solar: float = 0.0,
) -> pd.Series:
    """Forward-integrate with T_in[0] taken from observations.

    Same discretisation as the fit:
        T_in[k+1] = T_in[k] + α · (T_out[k] - T_in[k] + ΔT_eq + g_solar · I_solar[k])
    """
    if df.empty:
        return pd.Series(dtype="float64", name="T_in_model")

    dt = (df.index[1] - df.index[0]).total_seconds()
    alpha = dt / (tau_hours * 3600.0)

    t_in = df["T_in"].to_numpy()
    t_out = df["T_out"].to_numpy()
    i_sol = df["I_solar"].to_numpy()
    n = t_in.size

    sim = np.empty(n)
    sim[0] = t_in[0]
    for k in range(n - 1):
        sim[k + 1] = sim[k] + alpha * (t_out[k] - sim[k] + dT_eq + g_solar * i_sol[k])

    return pd.Series(sim, index=df.index, name="T_in_model")
