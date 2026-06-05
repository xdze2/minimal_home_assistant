# 2R2C with Kalman filtering of an unknown heat source Q(t)

Companion to [model_theory_1r1c.md](model_theory_1r1c.md),
[model_families.md](model_families.md), and
[model_families_priors.md](model_families_priors.md). This file proposes a
specific implementation: a 2R2C thermal model with one *unknown* heat input
`Q(t)` reconstructed by a linear Kalman filter + RTS smoother under a
random-walk prior.

The headline claim:

> Instead of fitting `R, C, ...` to make the simulated `T_in` match the
> measured `T_in` as best as possible, **fix** `R, C, ...` from physical
> estimates and **back out** the unknown heat input `Q(t)` that explains
> the residual. The Kalman/RTS pair does this exactly when the prior on
> `Q(t)` is a random walk.

## 1. Physical model

Two thermal masses (air node + wall mass), two resistances, one measured
solar input `I_solar(t)`, one measured outdoor temperature `T_ext(t)`, and
one **unknown** lumped heat source `Q(t)` injected into the air node.

```
T_ext ──R_ext── T_wall ──R_int── T_in ── (measured)
                                  │
                                  ├── α · I_solar(t)   (measured input)
                                  └── Q(t)             (UNKNOWN — to estimate)
```

Continuous-time energy balance:

```
C_in   · dT_in/dt   = (T_wall - T_in)/R_int + α · I_solar(t) + Q(t)
C_wall · dT_wall/dt = (T_ext  - T_wall)/R_ext + (T_in - T_wall)/R_int
```

Measurement: `y = T_in + v`, `v ~ N(0, σ_obs²)`.

## 2. The trick: promote Q to a state with random-walk dynamics

Standard 2R2C has state `x = [T_in, T_wall]` and treats `Q` as a known
input. Here we don't know `Q`. The fix is to **augment** the state:

```
x_tilde = [T_in, T_wall, Q]
```

and give `Q` the simplest possible time-dynamics — a random walk:

```
Q[t+1] = Q[t] + w_Q,    w_Q ~ N(0, σ_Q²)
```

In English: *"the unknown source changes slowly; how slowly is set by
σ_Q."* That single hyperparameter is the entire prior on `Q(t)`. See
[model_families_priors.md](model_families_priors.md) for richer prior
choices.

The augmented system is **linear and Gaussian**, so the optimal estimate
of `Q(t)` is given in closed form by the Kalman filter (causal) and
Rauch-Tung-Striebel smoother (acausal, uses past + future). No MCMC, no
optimisation loop — just two matrix recursions through the data.

## 3. Discrete-time state-space form

Let `Δt` be the sample period (e.g. 15 min). Discretise with the matrix
exponential (`expm`) of the continuous system to get a zero-order-hold
state-space:

```
x_tilde[t+1] = A_d · x_tilde[t] + B_d · u[t] + w[t]
y[t]         = H   · x_tilde[t] + v[t]
```

with:

- `u[t] = [T_ext(t), I_solar(t)]ᵀ` — measured inputs
- `H = [1, 0, 0]` — we observe T_in only
- `Q_cov = diag(σ_Tin², σ_Twall², σ_Q²)` — process noise. The first two
  are small (the physics is mostly right); `σ_Q²` is the prior bandwidth
  knob for the unknown source.
- `R_obs = σ_obs²` — sensor noise variance.

The continuous A matrix (before discretisation):

```
A_c = [[ -1/(R_int·C_in),    1/(R_int·C_in),             1/C_in ],
       [  1/(R_int·C_wall), -(1/R_int + 1/R_ext)/C_wall, 0      ],
       [  0,                 0,                           0      ]]
```

The third row is zeros — `Q` has no deterministic dynamics; only the
random-walk noise drives it.

`B_c` couples `T_ext` and `I_solar` into the right rows.

## 4. Inference recipe

```
inputs:  T_ext(t), I_solar(t), T_in_measured(t)   — measured time series
fixed:   R_int, R_ext, C_in, C_wall, α            — from building geometry
priors:  σ_Q (random-walk bandwidth on Q),
         σ_Tin, σ_Twall (process noise on physics),
         σ_obs (sensor noise)

outputs: T_in_smoothed(t), T_wall_smoothed(t), Q_smoothed(t)
         + posterior covariance at each step (uncertainty bands)
```

Steps:

1. **Assemble** the continuous matrices `A_c, B_c` from fixed parameters.
2. **Discretise** to `A_d, B_d` via `expm(A_c · Δt)` and the standard
   B-side integral.
3. **Kalman filter** (forward pass): for each `t`, predict using `A_d, B_d`,
   then update against `y[t]` using gain `K_t`.
4. **RTS smoother** (backward pass): for each `t = T-1 ... 0`, refine
   `x_tilde[t]` using `x_tilde[t+1]` from the future. The third component
   of the smoothed state is the reconstructed `Q(t)`.
5. **Diagnostics**: innovation sequence should look like white noise with
   variance `σ_obs²`. If autocorrelated → tighten `σ_Q`. If `Q(t)` looks
   like noise → loosen.

## 5. Why this is interesting

- **Interpretable output**: `Q(t)` is in watts, not abstract residual
  units. You can plot it and recognise heating schedules, occupancy
  bursts, window events — *if* the prior bandwidth is set right.
- **Honest residual decomposition**: any structure faster than `1/σ_Q`
  stays in the innovation (sensor noise, fast unmodelled physics). Any
  structure slower is absorbed by `Q`. The split happens at a frequency
  you choose.
- **Uncertainty for free**: the smoother gives a covariance at each `t`.
  You know when `Q` is well-determined and when it's not (e.g. during
  sensor dropouts).
- **Stepping stone to MCMC**: once `Q(t)` looks reasonable with fixed θ,
  the same Kalman filter is the inner loop of a Bayesian fit over
  `(R, C, α)` — the marginal likelihood is a byproduct of the filter.

## 6. Limitations honest to oneself

- **One knob = one timescale**: random-walk prior assumes the unknown
  source varies smoothly. A window opening for 1 minute can't be
  captured — it shows up as an innovation spike. Bursty events need a
  sparse-spike or jump-Markov prior (see
  [model_families_priors.md](model_families_priors.md)).
- **Identifiability with R, C**: a constant offset in `Q` is
  indistinguishable from a wrong `R` (both shift steady-state `T_in`).
  Choose a clean window (night, no sun, no occupancy) for first
  calibration of `R`. Bayesian fit later disentangles by marginalising.
- **Fixed θ is a strong assumption**: if R degrades over weeks (envelope
  aging), the constant-θ Kalman attributes the slow drift to `Q`. To
  separate, move to a joint state-parameter EKF (family E in
  [model_families.md](model_families.md)) or MCMC.
- **σ_Q has to be chosen**: by ML on the data likelihood (the filter
  exposes it as a byproduct), or by eyeballing the innovation
  autocorrelation. Not free.

## 7. Implementation plan (todo)

### Step 1 — Reference toy (sanity check)

- [ ] `toy_tank_leak.py` — 1-state "tank with unknown leak" example. State
      `[volume, leak]`, leak as random walk, noisy volume measurement.
      Recover the leak trace from synthetic data. ~50 lines. Validates
      the recipe before touching real data.
- [ ] Plot: true vs estimated leak, with ±2σ band from the smoother
      covariance.

### Step 2 — 2R2C Kalman implementation

- [ ] `kalman_2r2c_q.py`:
  - [ ] `assemble_continuous(params) -> (A_c, B_c)` — pure function of
        `R_int, R_ext, C_in, C_wall, α`. Mirrors structure of
        `fit_2r2c.py` so the same parameter dict can drive both.
  - [ ] `discretise(A_c, B_c, dt) -> (A_d, B_d)` — `scipy.linalg.expm`.
  - [ ] `kalman_filter(y, u, A_d, B_d, H, Q_cov, R_obs, x0, P0)` —
        forward pass, returns `(x_filt, P_filt, innovation, S)`.
  - [ ] `rts_smoother(x_filt, P_filt, A_d, Q_cov)` — backward pass,
        returns `(x_smooth, P_smooth)`.
  - [ ] `fit_sigma_Q(y, u, params, sigma_obs)` — MLE over `log σ_Q` from
        the filter's data likelihood. `scipy.optimize.minimize_scalar`.

### Step 3 — Wire to real data

- [ ] Reuse `load.py` to pull `T_ext`, `I_solar`, `T_in_measured` for a
      chosen room and date range.
- [ ] Pull fixed `(R_int, R_ext, C_in, C_wall, α)` from a JSON config
      with physical estimates (consider using a thermalnodes JSON like
      `chambre_2r2c.json` as the topology+param source — same schema as
      the forward simulator).
- [ ] Run filter+smoother, save `(T_in_smoothed, T_wall_smoothed, Q_smoothed)`
      plus covariance per timestep.

### Step 4 — Diagnostics & plots

- [ ] `inspector` view (extending the existing `inspector.py` style):
  - [ ] Top: measured `T_in` vs smoothed `T_in` (should overlap).
  - [ ] Middle: estimated `Q(t)` with ±2σ band.
  - [ ] Bottom: innovation sequence + its autocorrelation. Flag if
        |ρ(lag>0)| stays large → σ_Q too tight.
- [ ] Energy summary: integrate `Q(t)` over a day to get total unknown
      energy injected — sanity-check against expected occupancy /
      heating energy.

### Step 5 — Comparison with deterministic fit

- [ ] Run `fit_2r2c.py` on the same window for reference parameters.
- [ ] Compare: residual of deterministic fit vs `Q(t)` from Kalman. The
      Kalman `Q(t)` should look like the structured part of the
      deterministic residual, divided by the deterministic system
      response (i.e. deconvolved into watts).

### Step 6 — Bridge to MCMC (separate doc, future)

- [ ] Wrap the Kalman log-likelihood as a function of `(R_int, R_ext,
      C_in, C_wall, α, σ_Q, σ_obs)`. With `Q(t)` marginalised by the
      filter, this is a small parameter vector — ready for NUTS/HMC in
      NumPyro or PyMC.
- [ ] Out of scope for this file. Lives in `model_2r2c_bayes_q.md` (to
      be written once the Kalman version is working and useful).

## 8. File layout proposal

```
miniha/th_models/
  kalman/
    __init__.py
    assemble.py            # continuous + discrete state-space matrices
    filter.py              # KF + RTS, pure-numpy
    likelihood.py          # MLE on σ_Q from filter byproduct
    config.py              # dataclass of fixed θ + noise hyperparams
  toy_tank_leak.py         # 50-line reference example
  fit_kalman_q.py          # CLI: load data, run filter+smoother, save outputs
  inspector_kalman.py      # plot smoothed T, Q, innovations
  model_2r2c_kalman_q.md   # this file
  model_families_priors.md # prior taxonomy (companion)
```

## 9. Dependencies

- `numpy`, `scipy` (already in `miniha`) — `expm`, `solve`, `minimize`.
- No new heavy deps. `statsmodels.tsa.statespace.MLEModel` is an option
  to bypass writing the KF by hand, at the cost of fitting the design
  into its API. Decision: write KF in numpy directly — it's ~80 lines,
  matches the math in this doc 1:1, and stays trivially differentiable
  if we later port to JAX for MCMC.

## 10. Open questions

- **Source of fixed θ**: first pass from building geometry (areas,
  U-values, masses). Second pass: warm-start from `fit_2r2c.py` on a
  clean night window. To decide whether the "physical estimate" is
  trustworthy enough to expose interpretable `Q(t)` — if θ is wrong by
  20 %, `Q(t)` absorbs the bias and stops being physically meaningful.
- **Where Q is injected**: assumed on the air node here. Could also live
  on the wall node (e.g. radiant heating). One bit of structure to keep
  configurable.
- **Multiple unknown sources**: a single scalar `Q(t)` lumps everything.
  If we want to separate "occupancy" from "extra solar" we'd need extra
  states with their own priors (basis expansion, multi-component
  decomposition). Out of scope for v0; flag for v1.
