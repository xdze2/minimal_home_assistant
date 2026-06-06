"""Parameter estimation for thermalnodes — NLS and MCMC.

Param keys use the uniform format  node_id.field_name, e.g.:
  "R_ext.R"                 → resistance node R_ext, field R
  "chambre.C"               → mass node chambre, field C
  "apport_fenetre_sud.gain" → source node apport_fenetre_sud, field gain

All optimisation is done in log-space so parameters stay positive.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .assemble import assemble
from .simulate import simulate_zoh


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class FitResult:
    method: str                         # 'nls'
    params_nominal: dict[str, float]    # input nominals
    params_fitted: dict[str, float]     # best-fit values
    params_std: dict[str, float]        # 1-sigma uncertainty (from covariance)
    cost: float                         # final sum-of-squares / 2
    success: bool
    message: str
    elapsed_s: float
    n_evals: int


@dataclass
class MCMCResult:
    method: str                         # 'mcmc'
    params_nominal: dict[str, float]
    params_mean: dict[str, float]
    params_std: dict[str, float]
    samples: dict[str, np.ndarray]      # param_key → thinned chain [n_samples]
    acceptance_rate: float
    elapsed_s: float


# ---------------------------------------------------------------------------
# Model patching helpers
# ---------------------------------------------------------------------------

def _parse_key(key: str) -> tuple[str, str]:
    """Split 'node_id.field_name' → (node_id, field_name)."""
    parts = key.split(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Param key must be 'node_id.field_name', got: {key!r}"
        )
    return parts[0], parts[1]


def _patch_model(model: dict, params: dict[str, float]) -> dict:
    """Return a deep copy of model with param values applied."""
    m = copy.deepcopy(model)
    nodes_by_id = {n["id"]: n for n in m["nodes"]}
    for key, value in params.items():
        node_id, field_name = _parse_key(key)
        if node_id not in nodes_by_id:
            raise ValueError(f"Node '{node_id}' not found in model")
        nodes_by_id[node_id][field_name] = value
    return m


# ---------------------------------------------------------------------------
# Forward model builder
# ---------------------------------------------------------------------------

def build_forward(
    model: dict,
    inputs: dict[str, tuple[np.ndarray, np.ndarray]],
    observations: dict[str, tuple[np.ndarray, np.ndarray]],
    fit_config: dict,
    start: str,
    end: str,
    dt_minutes: int = 15,
    y0: np.ndarray | None = None,
) -> tuple[
    Callable[[np.ndarray], np.ndarray],
    np.ndarray,
    list[str],
]:
    """Build a forward function for optimisation.

    Inputs and observations must already be fetched (slow I/O done outside).

    Parameters
    ----------
    model:
        Model dict (topology stays fixed; only the param fields are patched).
    inputs:
        {node_id: (t_sec, values)} for boundary/source nodes.
    observations:
        {mass_node_id: (t_sec, values)} for observed temperatures.
    fit_config:
        Dict with keys: params, obs_sigma, method.
    start, end:
        ISO-8601 simulation window.
    dt_minutes:
        ZOH time step.
    y0:
        Initial temperatures [°C] for each mass node.  If None, defaults to
        the first boundary value (same as simulate_zoh default).  Pass an
        explicit array when observations start from a known initial condition.

    Returns
    -------
    forward_fn:
        Callable(log_params_vec) → residuals_vec.
        log_params_vec: log-space parameter vector, same order as param_keys.
        residuals_vec: (T_pred − T_obs) / obs_sigma, concatenated over all
                       observed mass nodes and time steps.
    log_params0:
        Initial log-space parameter vector (log of nominals).
    param_keys:
        Ordered list of parameter keys matching the vector positions.
    """
    import datetime
    from scipy.interpolate import interp1d

    params_cfg: dict[str, dict] = fit_config["params"]
    obs_sigma: float = float(fit_config.get("obs_sigma", 0.5))
    param_keys = list(params_cfg.keys())
    log_params0 = np.array([np.log(params_cfg[k]["nominal"]) for k in param_keys])

    # Pre-build observation interpolators on the ZOH output grid
    t0 = datetime.datetime.fromisoformat(start).timestamp()
    t1 = datetime.datetime.fromisoformat(end).timestamp()
    dt = dt_minutes * 60.0
    t_grid = np.arange(t0, t1, dt)

    obs_on_grid: dict[str, np.ndarray] = {}
    for mass_id, (t_obs, vals_obs) in observations.items():
        fn = interp1d(
            t_obs, vals_obs,
            kind="linear",
            bounds_error=False,
            fill_value=(vals_obs[0], vals_obs[-1]),
        )
        obs_on_grid[mass_id] = fn(t_grid)

    obs_ids = list(obs_on_grid.keys())

    def forward_fn(log_params_vec: np.ndarray) -> np.ndarray:
        params = {k: float(np.exp(v)) for k, v in zip(param_keys, log_params_vec)}
        patched = _patch_model(model, params)
        system = assemble(patched)
        result = simulate_zoh(system, inputs, start, end, dt_minutes=dt_minutes, y0=y0)

        residuals = []
        for mass_id in obs_ids:
            T_pred = result.temps[mass_id]
            T_obs = obs_on_grid[mass_id]
            n = min(len(T_pred), len(T_obs))
            residuals.append((T_pred[:n] - T_obs[:n]) / obs_sigma)
        return np.concatenate(residuals)

    return forward_fn, log_params0, param_keys


# ---------------------------------------------------------------------------
# NLS
# ---------------------------------------------------------------------------

def fit_nls(
    forward_fn: Callable[[np.ndarray], np.ndarray],
    log_params0: np.ndarray,
    param_keys: list[str],
    fit_config: dict,
) -> FitResult:
    """Nonlinear least squares in log-space via scipy.optimize.least_squares.

    Log-normal priors are folded in as extra residual terms so that
    least_squares minimises:
        Σ (T_pred − T_obs)²/σ²  +  Σ (log p − log p_nom)²/σ_log²
    """
    from scipy.optimize import least_squares

    params_cfg: dict[str, dict] = fit_config["params"]
    log_nominals = np.array([np.log(params_cfg[k]["nominal"]) for k in param_keys])
    sigma_logs = np.array([params_cfg[k].get("sigma_log", 0.5) for k in param_keys])

    def residuals_with_prior(log_p: np.ndarray) -> np.ndarray:
        data_res = forward_fn(log_p)
        prior_res = (log_p - log_nominals) / sigma_logs
        return np.concatenate([data_res, prior_res])

    t0 = time.perf_counter()
    result = least_squares(
        residuals_with_prior,
        log_params0,
        method="lm",
        ftol=1e-8,
        xtol=1e-8,
        gtol=1e-8,
    )
    elapsed = time.perf_counter() - t0

    params_fitted = {k: float(np.exp(v)) for k, v in zip(param_keys, result.x)}
    params_nominal = {k: params_cfg[k]["nominal"] for k in param_keys}

    # Covariance from Jacobian (J^T J)^{-1} * cost / dof
    try:
        J = result.jac
        n_res = len(result.fun)
        n_par = len(param_keys)
        dof = max(n_res - n_par, 1)
        s_sq = 2.0 * result.cost / dof
        cov = np.linalg.pinv(J.T @ J) * s_sq
        # std in log-space → propagate to linear space via delta method
        std_log = np.sqrt(np.diag(cov))
        params_std = {k: float(np.exp(v) * s) for k, v, s in zip(param_keys, result.x, std_log)}
    except Exception:
        params_std = {k: float("nan") for k in param_keys}

    return FitResult(
        method="nls",
        params_nominal=params_nominal,
        params_fitted=params_fitted,
        params_std=params_std,
        cost=float(result.cost),
        success=result.success,
        message=result.message,
        elapsed_s=elapsed,
        n_evals=result.nfev,
    )


# ---------------------------------------------------------------------------
# MCMC (emcee)
# ---------------------------------------------------------------------------

def fit_mcmc(
    forward_fn: Callable[[np.ndarray], np.ndarray],
    log_params0: np.ndarray,
    param_keys: list[str],
    fit_config: dict,
    n_samples: int = 2000,
    n_walkers: int | None = None,
) -> MCMCResult:
    """Ensemble MCMC sampler (emcee) in log-space.

    Log-posterior = Gaussian log-likelihood + log-normal log-prior per param.
    Walkers are initialised around log_params0 (NLS result or nominals).
    """
    import emcee

    params_cfg: dict[str, dict] = fit_config["params"]
    log_nominals = np.array([np.log(params_cfg[k]["nominal"]) for k in param_keys])
    sigma_logs = np.array([params_cfg[k].get("sigma_log", 0.5) for k in param_keys])

    n_dim = len(param_keys)
    if n_walkers is None:
        n_walkers = max(2 * n_dim, 8)
    # Ensure even number of walkers (emcee requirement)
    if n_walkers % 2 != 0:
        n_walkers += 1

    def log_posterior(log_p: np.ndarray) -> float:
        # Log-normal prior
        log_prior = -0.5 * np.sum(((log_p - log_nominals) / sigma_logs) ** 2)
        # Gaussian log-likelihood from residuals
        res = forward_fn(log_p)
        log_like = -0.5 * float(res @ res)
        return log_prior + log_like

    # Initialise walkers with small scatter around starting point
    rng = np.random.default_rng(42)
    p0 = log_params0 + rng.normal(0, 0.05, size=(n_walkers, n_dim))

    sampler = emcee.EnsembleSampler(n_walkers, n_dim, log_posterior)

    t0 = time.perf_counter()
    # Burn-in: 20% of total
    n_burn = max(n_samples // 5, 50)
    sampler.run_mcmc(p0, n_burn, progress=False)
    sampler.reset()
    sampler.run_mcmc(None, n_samples, progress=False)
    elapsed = time.perf_counter() - t0

    # Thin by autocorrelation time (fall back to thin=1 if estimation fails)
    try:
        tau = sampler.get_autocorr_time(quiet=True)
        thin = max(int(np.max(tau) / 2), 1)
    except Exception:
        thin = 1

    flat = sampler.get_chain(flat=True, thin=thin)  # (n_thinned, n_dim)
    acceptance_rate = float(np.mean(sampler.acceptance_fraction))

    params_mean = {k: float(np.exp(np.mean(flat[:, i]))) for i, k in enumerate(param_keys)}
    params_std = {k: float(np.exp(np.mean(flat[:, i])) * np.std(flat[:, i])) for i, k in enumerate(param_keys)}
    samples = {k: np.exp(flat[:, i]) for i, k in enumerate(param_keys)}

    return MCMCResult(
        method="mcmc",
        params_nominal={k: params_cfg[k]["nominal"] for k in param_keys},
        params_mean=params_mean,
        params_std=params_std,
        samples=samples,
        acceptance_rate=acceptance_rate,
        elapsed_s=elapsed,
    )
