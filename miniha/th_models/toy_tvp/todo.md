# Toy TVP — implementation plan

A minimal Streamlit app that fits a **time-varying-parameter (TVP)**
version of the energy bilan on **synthetic** data, using **PyStan**
(cmdstanpy) as the sampler. The point is to verify the framework end to
end on a known ground truth before touching real measurements.

Theoretical context lives in
[../model_theory_tvp.md](../model_theory_tvp.md). This file is the
practical plan.

## Scope of v1 (kept small on purpose)

**Time-varying:**
- $h_e(t)$ — outdoor conductance (per 15-min step)
- $\alpha(t)$ — solar coupling (per 15-min step)

**Fixed constants** (pinned, not inferred):
- $m$ — air thermal mass, set from "geometry"
- $h_i, m_\text{wall}$ — wall coupling and wall mass (set to plausible values)
- $T_\text{wall}(t)$ — driven by the wall ODE, not a free state

**Deferred** (NOT in v1):
- $Q(t)$ — heating power. Either set to 0 in synthetic data, or treated
  as an observed input. No spike-and-slab priors yet.
- Heavy-tailed priors. Use Gaussian random walks only. The smearing
  failure mode is the lesson.
- Real data. Synthetic only.
- Hierarchical / cross-room priors.

The simplified bilan in v1:

$$
m\,(T_{k+1} - T_k) = \Delta t\Big[-h_{e,k}(T_k - T_{\text{ext},k}) - h_i(T_k - T_{\text{wall},k}) + \alpha_k I_{\text{rad},k}\Big] + \eta_k
$$

with the wall ODE:

$$
m_\text{wall}(T_{\text{wall},k+1} - T_{\text{wall},k}) = \Delta t \cdot h_i (T_k - T_{\text{wall},k})
$$

## Stack

- **PyStan via cmdstanpy** (`cmdstanpy>=1.2`). Stan handles the
  correlated TVP posterior well with NUTS; `.stan` files are
  self-documenting.
- **Streamlit** for the UI, matching the existing
  [../inspector.py](../inspector.py) and
  [../daily.py](../daily.py) pattern.
- **Plotly** for plots, matching the existing app style.
- **ArviZ** (`arviz`) for posterior diagnostics — converts the Stan fit
  to an `InferenceData` object and provides trace plots, R̂, ESS.
- **NumPy / pandas** for data wrangling.

Add to `pyproject.toml`:
```
"cmdstanpy>=1.2",
"arviz>=0.18",
```

After install, run once (offline-friendly):
```
UV_PROJECT_ENVIRONMENT=venv uv run python -c "import cmdstanpy; cmdstanpy.install_cmdstan()"
```

## File layout

```
miniha/th_models/toy_tvp/
  __init__.py
  todo.md            # this file
  synth.py           # synthetic data generator with known ground truth
  priors.py          # prior hyperparameters (one dataclass)
  model.stan         # the Stan model
  fit.py             # cmdstanpy wrapper: data → arviz InferenceData
  plots.py           # Plotly traces of priors / posteriors / decomposition
  app.py             # the Streamlit entry point
```

## Step-by-step instructions

### Step 1 — Synthetic data generator (`synth.py`)

Function `generate(seed=0, n_days=5, dt_min=15) -> pd.DataFrame`:

- Build a UTC `DatetimeIndex` at `dt_min` resolution
- `T_ext(t)` = 8 + 5·sin(2π·t/24h − π/2) + slow drift over the week
- `I_rad(t)` = max(0, 600·sin(π·t_local_hour/12)) clipped to daylight,
  with one cloudy day (multiplier 0.2) at day 3
- True $h_e(t)$ = baseline 6 W/K, **with a known bump to 30 W/K for 2
  hours on day 3** (window-open event)
- True $\alpha(t)$ = baseline 0.4 m²-equivalent, with a slow seasonal
  drift of ±0.05 across the week
- True $m$ = 30 000 J/K (a small room's air mass × cp + a bit of sensor)
- True $h_i$ = 50 W/K, $m_\text{wall}$ = 5 × 10⁶ J/K
- Initialise $T(0) = T_\text{wall}(0)$ = 17 °C
- Simulate forward with the energy bilan (forward Euler), $Q = 0$
- Add Gaussian observation noise σ = 0.05 °C to $T$

Return a DataFrame with columns `T_in, T_ext, I_rad` and **also** the
ground-truth columns `h_e_true, alpha_true, T_wall_true`. Keep ground
truth separately so plotting can overlay it but the fit never sees it.

**Sanity-check it first.** Plot $T_\text{in}, T_\text{ext}, I_\text{rad}$
and see whether the window event is visible to the eye. If not, the
event is too small relative to noise — bump it up.

### Step 2 — Prior dataclass (`priors.py`)

A frozen dataclass `Priors` exposing all hyperparameters as a single
object. Default values for v1:

| Field | Value | Meaning |
|-------|-------|---------|
| `m` | 30000.0 | pinned air mass [J/K] |
| `h_i` | 50.0 | pinned wall coupling [W/K] |
| `m_wall` | 5e6 | pinned wall mass [J/K] |
| `h_e_init_mu`, `h_e_init_sigma` | 6.0, 4.0 | prior on $h_e$ at $k=0$ |
| `h_e_walk_sigma` | 0.3 | Gaussian increment std [W/K per step] |
| `alpha_init_mu`, `alpha_init_sigma` | 0.4, 0.2 | prior on $\alpha$ at $k=0$ |
| `alpha_walk_sigma` | 0.01 | Gaussian increment std per step |
| `T_wall_init_mu`, `T_wall_init_sigma` | 17.0, 2.0 | prior on $T_\text{wall}$ at $k=0$ |
| `obs_sigma` | 0.05 | observation noise std [°C] |

Expose these in the Streamlit sidebar so the user can play with them.

### Step 3 — The Stan model (`model.stan`)

```stan
data {
  int<lower=1> N;              // number of steps (observations)
  real dt;                     // step size [s]
  vector[N] T_obs;             // observed indoor temperature
  vector[N] T_ext;             // outdoor temperature
  vector[N] I_rad;             // solar irradiance
  real m;                      // pinned air mass
  real h_i;                    // pinned wall coupling
  real m_wall;                 // pinned wall mass
  real h_e_init_mu;
  real<lower=0> h_e_init_sigma;
  real<lower=0> h_e_walk_sigma;
  real alpha_init_mu;
  real<lower=0> alpha_init_sigma;
  real<lower=0> alpha_walk_sigma;
  real T_wall_init_mu;
  real<lower=0> T_wall_init_sigma;
  real<lower=0> obs_sigma;
}
parameters {
  vector<lower=0>[N] h_e;       // outdoor conductance trajectory
  vector<lower=0>[N] alpha;     // solar coupling trajectory
  real T_wall0;                 // initial wall temperature
}
transformed parameters {
  vector[N] T_wall;
  vector[N] T_pred;
  T_wall[1] = T_wall0;
  T_pred[1] = T_obs[1];
  for (k in 2:N) {
    // wall ODE (deterministic given h_i, m_wall, T)
    T_wall[k] = T_wall[k-1]
      + dt * h_i * (T_obs[k-1] - T_wall[k-1]) / m_wall;
    // air bilan
    T_pred[k] = T_obs[k-1]
      + dt * (
          -h_e[k-1] * (T_obs[k-1] - T_ext[k-1])
          -h_i      * (T_obs[k-1] - T_wall[k-1])
          + alpha[k-1] * I_rad[k-1]
        ) / m;
  }
}
model {
  // priors at k=0
  h_e[1]   ~ normal(h_e_init_mu,   h_e_init_sigma);
  alpha[1] ~ normal(alpha_init_mu, alpha_init_sigma);
  T_wall0  ~ normal(T_wall_init_mu, T_wall_init_sigma);

  // random-walk priors on increments
  for (k in 2:N) {
    h_e[k]   ~ normal(h_e[k-1],   h_e_walk_sigma);
    alpha[k] ~ normal(alpha[k-1], alpha_walk_sigma);
  }

  // observation likelihood
  T_obs[2:N] ~ normal(T_pred[2:N], obs_sigma);
}
```

Notes:
- `T_obs` is used inside `T_pred` (one-step-ahead prediction view). For a
  v1 this is acceptable; it's the same forward-Euler one-step OLS view
  that `fit.py` already uses. The full state-space version would replace
  `T_obs[k-1]` with a latent $T_\text{in}[k-1]$ at the cost of one more
  trajectory.
- `vector<lower=0>` enforces non-negativity. If sampler complains about
  initialisation, switch to a log parameterisation (`log_h_e ~ normal(...)`)
  later — not in v1.
- `transformed parameters` recomputes $T_\text{wall}$ and $T_\text{pred}$
  for each sample, so they are saved in the trace and ready to plot.

### Step 4 — Fit wrapper (`fit.py`)

Function signature:

```python
def fit_toy(
    df: pd.DataFrame,
    priors: Priors,
    chains: int = 4,
    iter_sampling: int = 1000,
    iter_warmup: int = 1000,
    seed: int = 0,
) -> az.InferenceData
```

Body:
1. Build the `data` dict for Stan from `df` and `priors`.
2. Compile the model on first call (`CmdStanModel(stan_file=...)`,
   cached by file mtime — cmdstanpy handles caching).
3. Run NUTS.
4. Convert to ArviZ: `az.from_cmdstanpy(fit)`.
5. Return.

Cache the compiled model and the fit with `@st.cache_resource` /
`@st.cache_data` in the Streamlit layer so the user can iterate on plots
without refitting.

### Step 5 — Plots (`plots.py`)

Three Plotly figures, each takes the InferenceData and the synthetic
ground truth (optional):

**A. `plot_trajectory(idata, df, var)`** — for `h_e` or `alpha` or
`T_wall`:
- Median + 90% CI ribbon over time
- Ground truth as a dashed line if present
- Vertical shaded band on the known window-open event

**B. `plot_bilan(idata, df)`** — energy decomposition:
- One stacked area per term: conduction
  $-h_e(T-T_\text{ext})$, wall coupling $-h_i(T-T_\text{wall})$, solar
  $\alpha I_\text{rad}$
- Median values, with light CI band on the conduction term (it's the
  noisy one)
- Sum line on top, residual vs. observed in a sub-panel

**C. `plot_fit(idata, df)`** — sanity:
- Observed $T$, predicted $T$ with 90% CI, residual sub-panel

### Step 6 — Streamlit app (`app.py`)

Single-page layout, sidebar + main area.

**Sidebar:**
- "Generate data" expander: `seed`, `n_days`, button to regenerate
- "Priors" expander: every field of `Priors` as a `number_input`
- "Sampler" expander: `chains`, `iter_warmup`, `iter_sampling`, `seed`
- "Fit" button (gates the expensive call)

**Main area:**
- Tab 1 *Data*: synthetic series plot ($T_\text{in}$, $T_\text{ext}$,
  $I_\text{rad}$); summary stats
- Tab 2 *Posteriors*: the three trajectory plots from `plot_trajectory`
- Tab 3 *Bilan*: the energy-decomposition plot
- Tab 4 *Diagnostics*: ArviZ summary table (R̂, ESS, divergences),
  trace plots for a few representative `h_e[k]` and `alpha[k]`

Run:
```
UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/toy_tvp/app.py
```

## Acceptance criteria (when v1 is "done")

1. The synthetic generator's output, plotted, contains a visible window
   event.
2. The Stan model compiles and samples without divergences on default
   priors (≤ 5% divergence rate is tolerable for v1; investigate if
   above).
3. R̂ < 1.01 and bulk ESS > 200 for every `h_e[k]` and `alpha[k]`.
4. **The posterior median of $h_e(t)$ shows a visible bump at the
   window-open time** — possibly smeared (Gaussian-RW limitation, this is
   expected and motivates v2).
5. **The posterior median of $\alpha(t)$ is approximately constant** at
   the true value, and does NOT show a spurious bump at the window-open
   time (i.e. the model correctly attributes the event to $h_e$, not
   $\alpha$).
6. The bilan decomposition plot sums to within the observation noise of
   the observed $\Delta T$.

If criterion 4 fails, the window event is being absorbed by $\alpha$ or
$T_\text{wall}$ — identifiability is broken, time to revisit priors.

If criterion 5 fails, $\alpha$ is too flexible — tighten
`alpha_walk_sigma`.

## v2 ideas (after v1 works)

In rough order of value:

- **Add $Q(t)$ with a spike-and-slab prior** for heating events.
- **Switch $h_e$ random walk to a horseshoe-on-increments** prior;
  observe whether the window event becomes sharply localised instead of
  smeared.
- **Replace one-step-ahead with a fully latent $T_\text{in}(t)$ state**
  (proper state-space form, not pseudo-OLS).
- **Add a fit-on-real-data tab** using the existing `load.py` loader,
  picking one room.
- **Hierarchical layer** across multiple rooms — shared prior on
  $h_e$-baseline, room-specific deviations.
- **Compare to a Kalman smoother baseline** on the same data (dynamax).
  Should agree on the Gaussian-RW model, diverge on the heavy-tailed
  one.

## Open questions to revisit during implementation

- **Should the wall ODE use $T_\text{obs}$ or a latent $T_\text{in}$?**
  v1 uses $T_\text{obs}$ for simplicity; this couples observation noise
  into the wall trajectory. Worth checking the impact on posteriors.
- **Are `h_e_walk_sigma = 0.3` and `alpha_walk_sigma = 0.01` the right
  scales?** Eyeball from the prior predictive (sample from prior, plot
  trajectories) before fitting.
- **One-step ahead in 15-min steps** means the model assumes the wall and
  outdoor are quasi-constant within each 15-min step. Likely fine; flag
  if residuals show structure at sub-15-min scales.
