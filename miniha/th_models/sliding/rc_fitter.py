"""1R1C sliding-window fitter with weak physical priors.

Model (same as fit.py):
    C dT_in/dt = (T_out - T_in)/R + Q0 + a * I_solar

Discretised (forward Euler, step dt):
    ΔT_in = α(T_out - T_in) + β + γ I_solar
        α = dt/τ      τ = RC
        β = dt Q0/C   ΔT_eq = β/α = Q0 R
        γ = dt a/C    g_solar = γ/α = a R

OLS for (α, β, γ). Identifiable parameters: (τ, ΔT_eq, g_solar).

Priors are implemented as penalised least squares (ridge with non-zero
target), following NEXT.md Axis 3 §1:

    J(θ) = ||y - Xθ||² + Σ_i λ_i ((θ_i - θ_i_prior) / σ_i)²

This is still a closed-form linear solve — no iteration needed.
λ_i = 1 gives σ_i the same weight as one data residual of unit variance;
scale the data term by 1/n for a prior-strength that is independent of
window length.

Priors are expressed on the *identifiable* parameters (τ, ΔT_eq, g_solar),
then converted to (α, β, γ) space for the penalised solve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .protocol import Fitter, WindowResult


@dataclass
class Prior:
    value: float
    sigma: float    # std of the Gaussian prior; large = weak


@dataclass
class RcFitterConfig:
    # Priors on identifiable parameters.
    # Set sigma=inf (or a very large number) to disable a prior.
    tau_prior: Prior = field(default_factory=lambda: Prior(value=8.0, sigma=4.0))
    dT_eq_prior: Prior = field(default_factory=lambda: Prior(value=2.0, sigma=5.0))
    g_solar_prior: Prior = field(default_factory=lambda: Prior(value=0.005, sigma=0.01))

    # Plausibility gates (applied after the fit).
    tau_min_h: float = 1.0
    tau_max_h: float = 100.0
    g_solar_min: float = 0.0    # solar gain must be non-negative

    # Merge tolerances.
    tau_log_tol: float = 0.3
    dT_eq_tol: float = 1.5      # °C
    g_solar_tol: float = 0.02   # °C per W/m²

    # Minimum samples for a valid fit (α, β, γ = 3 params).
    min_samples: int = 12


class RcFitter:
    """1R1C windowed fitter with penalised OLS priors."""

    def __init__(self, config: RcFitterConfig | None = None) -> None:
        self.config = config or RcFitterConfig()

    def fit(
        self,
        t_sec: np.ndarray,
        inputs: dict[str, np.ndarray],
    ) -> WindowResult | None:
        T_in = inputs.get("T_in")
        T_out = inputs.get("T_out")
        I_solar = inputs.get("shortwave_radiation")
        if I_solar is None:
            I_solar = inputs.get("I_solar")

        if T_in is None or T_out is None:
            return None
        n = len(T_in)
        if n < self.config.min_samples + 1:
            return None

        dt = float(t_sec[1] - t_sec[0]) if len(t_sec) > 1 else 0.0
        if dt <= 0:
            return None

        # Regression targets and regressors (equation-error, same as fit.py).
        y = T_in[1:] - T_in[:-1]
        x_dt = T_out[:-1] - T_in[:-1]
        x_ones = np.ones(n - 1)

        if I_solar is not None:
            x_sol = I_solar[:-1].clip(min=0.0)
            X = np.column_stack([x_dt, x_ones, x_sol])
            n_params = 3
        else:
            X = np.column_stack([x_dt, x_ones])
            n_params = 2

        cfg = self.config

        # Build penalised normal equations: (X'X + P) θ = X'y + p_rhs
        # Prior on α: α_prior = dt / (τ_prior * 3600)
        # Prior on β: β_prior = α_prior * ΔT_eq_prior  (since ΔT_eq = β/α)
        # Prior on γ: γ_prior = α_prior * g_solar_prior
        # λ_i = (1/n) / σ_i²  — normalised by window size so prior strength
        # is independent of window length.
        alpha_prior = dt / (cfg.tau_prior.value * 3600.0)
        beta_prior = alpha_prior * cfg.dT_eq_prior.value
        theta_prior = np.array([alpha_prior, beta_prior])

        # σ for α: propagate σ_τ → σ_α = dt * σ_τ / τ² (first-order, all in hours)
        sigma_alpha = dt * cfg.tau_prior.sigma / (cfg.tau_prior.value ** 2 * 3600.0)
        # σ for β: σ_β ≈ α_prior * σ_ΔT_eq  (dominant term)
        sigma_beta = alpha_prior * cfg.dT_eq_prior.sigma

        lambdas = np.array([
            1.0 / (n * sigma_alpha ** 2),
            1.0 / (n * sigma_beta ** 2),
        ])

        if n_params == 3:
            sigma_gamma = alpha_prior * cfg.g_solar_prior.sigma
            theta_prior = np.append(theta_prior, alpha_prior * cfg.g_solar_prior.value)
            lambdas = np.append(lambdas, 1.0 / (n * sigma_gamma ** 2))

        XtX = X.T @ X
        Xty = X.T @ y
        P = np.diag(lambdas)
        p_rhs = P @ theta_prior

        try:
            theta = np.linalg.solve(XtX + P, Xty + p_rhs)
        except np.linalg.LinAlgError:
            return None

        alpha = float(theta[0])
        beta = float(theta[1])
        gamma = float(theta[2]) if n_params == 3 else 0.0

        if alpha <= 0:
            return None

        tau_h = (dt / alpha) / 3600.0
        dT_eq = beta / alpha
        g_solar = gamma / alpha

        if not (cfg.tau_min_h <= tau_h <= cfg.tau_max_h):
            return None
        if g_solar < cfg.g_solar_min:
            return None

        resid = y - X @ theta
        rmse = float(np.sqrt(np.dot(resid, resid) / (n - 1)))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r2 = 1.0 - float(np.dot(resid, resid)) / ss_tot if ss_tot > 0 else 0.0
        # Use -RMSE as quality so higher = better, consistent with the protocol.
        quality = -rmse

        params = {"tau_h": tau_h, "dT_eq": dT_eq, "g_solar": g_solar, "r2": r2, "rmse": rmse}

        def curve_fn(
            times: pd.DatetimeIndex,
            _T_in0=float(T_in[0]),
            _T_out=T_out,
            _I_sol=I_solar,
            _t_sec=t_sec,
            _alpha=alpha, _dT_eq=dT_eq, _g_solar=g_solar,
        ) -> np.ndarray:
            # Forward-integrate from T_in[0] on the original window grid,
            # then interpolate to requested times if different.
            sim = np.empty(len(_t_sec))
            sim[0] = _T_in0
            for k in range(len(_t_sec) - 1):
                sol = _I_sol[k] if _I_sol is not None else 0.0
                sim[k + 1] = sim[k] + _alpha * (
                    _T_out[k] - sim[k] + _dT_eq + _g_solar * sol
                )
            # t_sec always starts at 0 (seconds from window start).
            # Use t_sec[0] as origin so this stays correct even if t_sec
            # does not start at 0 (e.g. a future caller passes a non-zero base).
            t_req = np.array(
                [(ts - times[0]).total_seconds() + _t_sec[0] for ts in times], dtype=float
            )
            return np.interp(t_req, _t_sec, sim)

        result = WindowResult(
            t_start=pd.NaT,
            t_end=pd.NaT,
            params=params,
            quality=quality,
            n=n,
        )
        result._curve_fn = curve_fn
        return result

    def params_close(self, a: WindowResult, b: WindowResult) -> bool:
        cfg = self.config
        tau_a = max(a.params["tau_h"], 1e-6)
        tau_b = max(b.params["tau_h"], 1e-6)
        return (
            abs(np.log(tau_a) - np.log(tau_b)) < cfg.tau_log_tol
            and abs(a.params["dT_eq"] - b.params["dT_eq"]) < cfg.dT_eq_tol
        )
