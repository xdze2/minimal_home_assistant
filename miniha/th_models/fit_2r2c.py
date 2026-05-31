"""Grey-box 2R2C thermal fit (air node + wall/mass node).

Topology:

    T_out ──R_ext── T_wall ──R_int── T_in ─── (observation)
                      │                │
                      │                └── a_in · I_solar     (instant gain on air)
                      └── a_wall · I_solar  (lagged gain on mass)

State-space form (continuous):

    C_in   dT_in/dt   = (T_wall - T_in)/R_int + (T_out - T_in)/R_inf
                        + Q0 + a_in   · I_solar
    C_wall dT_wall/dt = (T_in - T_wall)/R_int + (T_out - T_wall)/R_ext
                        + a_wall · I_solar

`R_inf` is an optional direct air↔outside leak (windows, infiltration). Kept
fixed at +∞ in the default parameterisation (set to a large number); the
"all heat through the wall" cartoon. Easy to enable later.

Fit: output-error nonlinear least squares. Forward-simulate the trajectory
with `scipy.integrate` (exponential / matrix-exponential ZOH on the linear
system), minimise the residual `T_in_sim - T_in_obs` with
`scipy.optimize.least_squares` (TRF). Warm-started from the 1R1C OLS fit:

    τ_init       = τ_1R1C
    R_int_init   = 0.5 · R_total          (split 50/50)
    R_ext_init   = 0.5 · R_total
    C_in_init    = τ_1R1C / R_total · 0.3 (smaller, fast air node)
    C_wall_init  = τ_1R1C / R_total · 0.7 (larger, slow mass node)
    a_in_init    = 0.5 · g_solar / R_total
    a_wall_init  = 0.5 · g_solar / R_total
    Q0_init      = dT_eq / R_total

Reparameterised in log-space for positivity (`log R_int`, `log R_ext`,
`log C_in`, `log C_wall`); `Q0`, `a_in`, `a_wall` left linear.

The latent `T_wall[0]` initial state is co-fit. `T_in[0]` is pinned to
observation (matches the 1R1C `simulate`).

Identifiable scalars reported back (mirroring 1R1C):
    τ_fast, τ_slow  — eigen-time-constants of the A matrix
    dT_eq           — steady-state lift from Q0 alone
    g_solar         — steady-state lift per (W/m²) of solar (both inputs)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.linalg import expm
from scipy.optimize import least_squares


@dataclass
class Fit2R2CResult:
    tau_fast_h: float
    tau_slow_h: float
    R_int: float        # K/W (per unit C scale; see model_theory for ambiguity)
    R_ext: float
    C_in: float         # J/K
    C_wall: float
    Q0: float           # W
    a_in: float         # m² (effective)
    a_wall: float
    T_wall0: float      # °C, fitted initial wall temperature
    dT_eq: float        # °C, steady-state lift from Q0
    g_solar: float      # °C per (W/m²)
    n_samples: int
    rmse: float         # trajectory RMSE on T_in (°C)
    success: bool
    message: str


def _build_AB(
    R_int: float, R_ext: float,
    C_in: float, C_wall: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Continuous-time A, B for state x = [T_in, T_wall], input u = [T_out, I_solar, 1]."""
    A = np.array([
        [-1.0 / (R_int * C_in),                  1.0 / (R_int * C_in)],
        [ 1.0 / (R_int * C_wall),               -(1.0 / R_int + 1.0 / R_ext) / C_wall],
    ])
    # B columns: T_out, I_solar, constant (for Q0 · 1/C_in)
    B = np.array([
        [0.0,                  1.0 / C_in,    1.0 / C_in],
        [1.0 / (R_ext * C_wall), 1.0 / C_wall, 0.0],
    ])
    return A, B


def _simulate_states(
    theta: dict,
    t_out: np.ndarray, i_sol: np.ndarray,
    dt: float,
    T_in0: float,
) -> np.ndarray:
    """Forward-simulate the 2-state system. Returns array shape (n, 2): [T_in, T_wall]."""
    R_int = theta["R_int"]; R_ext = theta["R_ext"]
    C_in  = theta["C_in"];  C_wall = theta["C_wall"]
    Q0    = theta["Q0"]
    a_in  = theta["a_in"];  a_wall = theta["a_wall"]
    T_wall0 = theta["T_wall0"]

    A, B_phys = _build_AB(R_int, R_ext, C_in, C_wall)

    # Recompose B so input is u = [T_out, I_solar, 1] with physical mixing of a_in/a_wall.
    # Heat-source-on-node entries: divide by C_node.
    B = np.array([
        [0.0,             a_in  / C_in,   Q0 / C_in],
        [1.0 / (R_ext * C_wall), a_wall / C_wall, 0.0],
    ])

    n = t_out.size
    x = np.empty((n, 2))
    x[0, 0] = T_in0
    x[0, 1] = T_wall0

    # ZOH discretisation: x[k+1] = Ad x[k] + Bd u[k]
    # Augmented exponential trick: M = [[A, B], [0, 0]] of size (nx+nu, nx+nu).
    nx, nu = 2, B.shape[1]
    M = np.zeros((nx + nu, nx + nu))
    M[:nx, :nx] = A * dt
    M[:nx, nx:] = B * dt
    eM = expm(M)
    Ad = eM[:nx, :nx]
    Bd = eM[:nx, nx:]

    ones = np.ones(n)
    U = np.column_stack([t_out, i_sol, ones])  # (n, 3)
    for k in range(n - 1):
        x[k + 1] = Ad @ x[k] + Bd @ U[k]
    return x


def _unpack(p: np.ndarray) -> dict:
    """p = [logR_int, logR_ext, logC_in, logC_wall, Q0, a_in, a_wall, T_wall0]."""
    return {
        "R_int":   float(np.exp(p[0])),
        "R_ext":   float(np.exp(p[1])),
        "C_in":    float(np.exp(p[2])),
        "C_wall":  float(np.exp(p[3])),
        "Q0":      float(p[4]),
        "a_in":    float(p[5]),
        "a_wall":  float(p[6]),
        "T_wall0": float(p[7]),
    }


def _pack(theta: dict) -> np.ndarray:
    return np.array([
        np.log(theta["R_int"]),
        np.log(theta["R_ext"]),
        np.log(theta["C_in"]),
        np.log(theta["C_wall"]),
        theta["Q0"],
        theta["a_in"],
        theta["a_wall"],
        theta["T_wall0"],
    ])


def _init_from_1r1c(
    tau_hours: float, dT_eq: float, g_solar: float,
    T_in0: float,
) -> dict:
    """Warm-start: split a notional R_total = 1 (K/W per arbitrary C-scale)."""
    # We don't observe R individually from 1R1C, so we pick R_total = 1 K/W as a
    # gauge. C is then set so that τ = R·C is preserved (averaged across the
    # two nodes).
    R_total = 1.0
    tau_s = tau_hours * 3600.0
    # Approximate τ ≈ R_int · C_in + R_ext · C_wall (rough; the actual modes
    # are eigenvalues — this is just a warm start).
    C_total = tau_s / R_total
    return {
        "R_int":   0.5 * R_total,
        "R_ext":   0.5 * R_total,
        "C_in":    0.3 * C_total,
        "C_wall":  0.7 * C_total,
        "Q0":      dT_eq / R_total,
        "a_in":    0.5 * g_solar / R_total,
        "a_wall":  0.5 * g_solar / R_total,
        "T_wall0": T_in0,
    }


def _eigen_taus(R_int: float, R_ext: float, C_in: float, C_wall: float) -> tuple[float, float]:
    A, _ = _build_AB(R_int, R_ext, C_in, C_wall)
    eigs = np.linalg.eigvals(A).real
    # Negative real parts expected; τ = -1/λ.
    taus = sorted(-1.0 / e for e in eigs if e < 0)  # ascending: fast first
    if len(taus) < 2:
        return float("nan"), float("nan")
    return taus[0] / 3600.0, taus[1] / 3600.0


def _steady_state_gains(theta: dict) -> tuple[float, float]:
    """Steady-state T_in lift from Q0 (per W) and per (W/m²) of I_solar."""
    A, _ = _build_AB(theta["R_int"], theta["R_ext"], theta["C_in"], theta["C_wall"])
    # B columns for inputs that are zero at "rest": Q0 enters T_in only;
    # I_solar enters both nodes via a_in / a_wall.
    # Steady state: x_ss = -A^{-1} B u, with T_out = 0 reference.
    Ainv = np.linalg.inv(A)
    # Unit Q0:
    bQ = np.array([1.0 / theta["C_in"], 0.0])
    xQ = -Ainv @ bQ
    dT_eq = float(xQ[0])  # per W of Q0; multiply by Q0 outside
    # Unit I_solar:
    bS = np.array([theta["a_in"] / theta["C_in"], theta["a_wall"] / theta["C_wall"]])
    xS = -Ainv @ bS
    g_solar = float(xS[0])
    return dT_eq * theta["Q0"], g_solar


def fit_2r2c(
    df: pd.DataFrame,
    warm: tuple[float, float, float] | None = None,
    max_nfev: int = 200,
) -> Fit2R2CResult:
    """Output-error NLS fit of 2R2C.

    df: from `prepare` — columns T_in, T_out, I_solar on a uniform grid.
    warm: optional (tau_hours, dT_eq, g_solar) from a 1R1C fit on the same df.
          If None, fallback to crude defaults.
    """
    if len(df) < 8:
        raise ValueError(f"not enough samples to fit ({len(df)})")

    dt = (df.index[1] - df.index[0]).total_seconds()
    t_in_obs = df["T_in"].to_numpy()
    t_out = df["T_out"].to_numpy()
    i_sol = df["I_solar"].to_numpy()
    T_in0 = float(t_in_obs[0])

    if warm is None:
        warm = (10.0, 0.0, 0.005)
    tau_h, dT_eq_init, g_solar_init = warm
    theta0 = _init_from_1r1c(tau_h, dT_eq_init, g_solar_init, T_in0)
    p0 = _pack(theta0)

    def residuals(p: np.ndarray) -> np.ndarray:
        theta = _unpack(p)
        try:
            x = _simulate_states(theta, t_out, i_sol, dt, T_in0)
        except (np.linalg.LinAlgError, FloatingPointError, ValueError):
            return np.full(t_in_obs.size, 1e6)
        sim = x[:, 0]
        if not np.all(np.isfinite(sim)):
            return np.full(t_in_obs.size, 1e6)
        return sim - t_in_obs

    # Loose bounds; log-params can range widely. Q0 / a_* / T_wall0 in physical.
    lb = np.array([np.log(1e-4), np.log(1e-4), np.log(1e2), np.log(1e2),
                   -1e4, -10.0, -10.0, -50.0])
    ub = np.array([np.log(1e4),  np.log(1e4),  np.log(1e10), np.log(1e10),
                    1e4,  10.0,  10.0, 100.0])

    res = least_squares(
        residuals, p0, bounds=(lb, ub),
        method="trf", max_nfev=max_nfev,
        x_scale="jac",
    )

    theta = _unpack(res.x)
    sim = _simulate_states(theta, t_out, i_sol, dt, T_in0)[:, 0]
    resid = sim - t_in_obs
    rmse = float(np.sqrt(np.mean(resid * resid)))

    tau_fast, tau_slow = _eigen_taus(theta["R_int"], theta["R_ext"],
                                     theta["C_in"], theta["C_wall"])
    dT_eq, g_solar = _steady_state_gains(theta)

    return Fit2R2CResult(
        tau_fast_h=tau_fast,
        tau_slow_h=tau_slow,
        R_int=theta["R_int"], R_ext=theta["R_ext"],
        C_in=theta["C_in"], C_wall=theta["C_wall"],
        Q0=theta["Q0"], a_in=theta["a_in"], a_wall=theta["a_wall"],
        T_wall0=theta["T_wall0"],
        dT_eq=dT_eq,
        g_solar=g_solar,
        n_samples=int(t_in_obs.size),
        rmse=rmse,
        success=bool(res.success),
        message=str(res.message),
    )


def simulate_2r2c(df: pd.DataFrame, result: Fit2R2CResult) -> pd.DataFrame:
    """Replay the fitted trajectory. Returns DataFrame with T_in_model, T_wall_model."""
    if df.empty:
        return pd.DataFrame(columns=["T_in_model", "T_wall_model"])
    dt = (df.index[1] - df.index[0]).total_seconds()
    theta = {
        "R_int": result.R_int, "R_ext": result.R_ext,
        "C_in": result.C_in, "C_wall": result.C_wall,
        "Q0": result.Q0,
        "a_in": result.a_in, "a_wall": result.a_wall,
        "T_wall0": result.T_wall0,
    }
    x = _simulate_states(theta,
                         df["T_out"].to_numpy(), df["I_solar"].to_numpy(),
                         dt, float(df["T_in"].iloc[0]))
    return pd.DataFrame(
        {"T_in_model": x[:, 0], "T_wall_model": x[:, 1]},
        index=df.index,
    )
