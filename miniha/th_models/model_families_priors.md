# Model families — classified by their priors

Companion to [model_families.md](model_families.md). That file classifies
identification methods along three axes (state, time, parameters). This
file zooms in on what is, in retrospect, the *real* modelling decision:

> Every grey-box approach is defined by the **prior** it puts on the
> unknown quantities — parameters, hidden states, unmeasured inputs. The
> machinery (Kalman, MCMC, EM, …) is just plumbing for the same
> mathematics. The prior is what encodes the physical assumption.

Two unknown quantities recur:

- `θ` — the static parameters (`R`, `C`, `α`, …)
- `Q(t)` — the time-varying unknown input (or, equivalently, the
  time-varying residual / disturbance / unmeasured forcing)

What follows is a taxonomy of priors, in increasing order of structure.

## 1. Priors on Q(t) — the unknown time-varying input

### P1. Constant offset

```
Q(t) = Q0,    Q0 ~ N(μ_Q0, σ_Q0²)   or   improper flat
```

The current `fit_2r2c.py` `Q0` term. Captures steady internal gains. Zero
time-resolution. *Cheapest, weakest.*

### P2. Independent Gaussian noise per timestep

```
Q[t] ~ N(0, σ_Q²)    i.i.d.
```

No temporal structure. Equivalent to saying "the unknown source is white
noise." Almost never physically right (heat doesn't decorrelate in 15
minutes), but a useful straw-man baseline.

### P3. Random walk

```
Q[t+1] = Q[t] + w[t],    w ~ N(0, σ_Q²)
```

Encodes: "smooth, no preferred level, no preferred sign." One knob
(`σ_Q`) sets the bandwidth.

Use when: aggregate slow disturbances (occupancy drift, average heat
from electronics, slow envelope drift).

Closed-form inference via Kalman filter + RTS smoother on the augmented
state. This is the proposal in
[model_2r2c_kalman_q.md](model_2r2c_kalman_q.md).

### P4. Integrated random walk (locally linear)

```
Q'[t+1] = Q'[t] + w[t]
Q[t+1]  = Q[t]  + Q'[t] · Δt
```

`Q` itself can drift linearly; only its *derivative* is constrained.
Gives smoother trajectories than P3. Good when the unknown source ramps
up and down (heating warming up over an hour).

Still linear Gaussian → still Kalman.

### P5. Ornstein-Uhlenbeck (mean-reverting)

```
Q[t+1] = Q[t] + κ · (μ - Q[t]) · Δt + w[t]
```

Two knobs: mean `μ` and reversion rate `κ`. Encodes: "Q tends to return
to a baseline." Useful when you have a prior expectation
("on average there is no unknown source") and want to prevent drift
during sensor gaps.

Still linear Gaussian → still Kalman.

### P6. Gaussian Process

```
Q(t) ~ GP(0, k(t, t'))
```

The kernel `k` encodes the smoothness, periodicity, lengthscale,
amplitude. Most flexible smooth prior. Subsumes P3-P5 (specific kernels
recover them).

Closed-form posterior for Gaussian observations, but O(N³) cost — painful
above ~3000 points. Sparse approximations (inducing points), or
equivalent state-space rewrites for Matérn kernels (Hartikainen &
Särkkä) recover linear scaling.

### P7. Basis expansion

```
Q(t) = Σ_k β_k · φ_k(t),    β_k ~ N(0, σ_β²)
```

Pick basis `φ_k` — B-splines, Fourier, wavelets, daily/weekly
indicators. Drops dimension from "one Q per timestep" to "~20 β
coefficients." MCMC-friendly because few parameters.

Use when you have prior knowledge of which frequencies / shapes matter
(diurnal cycle → daily Fourier basis; sharp transitions → wavelets).

### P8. Sparse spike-and-slab

```
Q[t] = 0          with prob (1 - p)
Q[t] ~ N(0, σ²)   with prob p
```

Encodes: "most of the time nothing is happening, occasionally something
big does." Matches reality for door/window events, instantaneous
appliance turn-on.

Non-Gaussian → breaks closed-form Kalman. Needs MCMC, particle
filtering, or Expectation Propagation.

### P9. Jump-Markov (regime-switching)

```
mode s[t] ∈ {off, heating, window_open, ...}    Markov chain
Q[t] | s[t]=k  ~  N(μ_k, σ_k²)
```

The prior on `Q` *switches* depending on a hidden discrete regime. Most
physically honest representation of "different things happen at
different times." This is the SLDS world (D1-D2 in
[model_families.md](model_families.md)).

Hardest to fit. Requires either approximate inference (IMM, variational
SLDS) or MCMC with discrete-state sampling.

### P10. Conditional on observed covariates

```
Q(t) = g(weather, time-of-day, day-of-week, ...) + ε(t),  ε(t) ~ (any prior above)
```

A regression layer absorbs the systematic part of `Q` from observed
inputs, leaving a smaller residual for the stochastic prior. Bridges
"input augmentation" (model_families.md §4 Q1) and
"disturbance estimation."

### P11. Multi-component decomposition

```
Q(t) = Q_baseline(t) + Q_solar_extra(t) + Q_occupancy(t) + Q_heating(t)
```

Each component gets its own prior with its own structure:
- `Q_baseline` — slow random walk (P3)
- `Q_solar_extra` — proportional to measured solar with unknown gain (P10)
- `Q_occupancy` — daily-periodic Fourier (P7) + sparse spikes (P8)
- `Q_heating` — jump-Markov on-off (P9)

This is where domain knowledge actually lives. Maximally informative,
hardest to fit, most rewarding when it works. The destination, not the
starting point.

## 2. Priors on θ — the static parameters

### θ.1 Fixed point estimate

```
θ = θ_fixed   (no prior, no posterior)
```

What `model_2r2c_kalman_q.md` does in v0. θ comes from building geometry
or a prior deterministic fit. Pre-empts identifiability questions but
folds any θ-bias into Q(t).

### θ.2 Improper flat prior (= MLE)

```
θ ~ Uniform(−∞, +∞)
```

What `fit.py` / `fit_2r2c.py` do, with positivity enforced by log
reparameterisation. Equivalent to point-estimate MLE.

### θ.3 Weakly informative Gaussian / LogNormal

```
log R ~ N(log R_phys, σ_R²)
log C ~ N(log C_phys, σ_C²)
α     ~ N(α_phys, σ_α²)
```

Centred on physical estimates, with widths reflecting how confident you
are in those estimates. Light Bayesian. Resolves identifiability
ambiguities (e.g. Q-offset vs R-bias) by anchoring to physics.

### θ.4 Hierarchical

```
log R_room_k  ~ N(μ_R_building, τ_R²)    for each room k
μ_R_building  ~ Hyperprior
τ_R           ~ Hyperprior
```

Multiple rooms share a building-level prior. Borrowing strength: a room
with few data points still gets a sensible estimate via the population
prior. Standard in multilevel modelling.

### θ.5 Slow random walk (time-varying parameters)

```
log R[t+1] = log R[t] + w_R[t],    w_R ~ N(0, σ_R²)
```

Parameters drift. Different from Q(t) varying: here the *physics
constants* themselves change (envelope degradation, sensor drift).
Implemented by augmenting the state with `(log R, log C, ...)` and
running EKF/UKF, or by sliding-window refits (the current `sliding/`
scan).

Risk: if Q(t) and θ(t) both drift, they trade off in identification —
need strong priors on one to recover the other.

### θ.6 Regime-dependent θ

```
θ | s[t]=k ~ θ_k_prior
```

Different parameter values per discrete regime. Matches "window open"
(different R) explicitly via a discrete state. This is SLDS with
learned per-mode dynamics (D1-D2 in
[model_families.md](model_families.md)).

## 3. Cross-product: which combinations have names

| Prior on θ | Prior on Q(t) | Common name | Tool |
|------------|--------------|-------------|------|
| Fixed (θ.1) | None — Q absent | 2R2C forward sim | `thermalnodes/solver` |
| MLE (θ.2) | Constant (P1) | Output-error fit | `fit_2r2c.py` |
| MLE (θ.2) | Independent (P2) | Maximum-likelihood with white process noise | rarely used by itself |
| Fixed (θ.1) | Random walk (P3) | **Disturbance Kalman filter** | `model_2r2c_kalman_q.md` (proposal) |
| Weak Gaussian (θ.3) | Random walk (P3) | Bayesian disturbance filter | NumPyro + Kalman scan |
| Weak Gaussian (θ.3) | Constant (P1) | Bayesian static grey-box | PyMC, ctsmr |
| Weak Gaussian (θ.3) | Integrated RW (P4) | Bayesian local-linear-trend | `statsmodels.tsa.statespace` |
| Weak Gaussian (θ.3) | GP (P6) | GP regression with mechanistic mean | rare in buildings, common in climate |
| Slow random walk (θ.5) | Constant (P1) | Joint state-param EKF | filterpy, custom |
| Regime-dependent (θ.6) | Regime-dependent (P9) | SLDS / rSLDS | dynamax, ssm |
| Hierarchical (θ.4) | Random walk (P3) | Multilevel disturbance model | PyMC |
| Weak Gaussian (θ.3) | Multi-component (P11) | Structural time series | `tfp.sts`, BSTS, Prophet |

## 4. How to read this table

The current code lives on row 2 (output-error fit). The proposal in
[model_2r2c_kalman_q.md](model_2r2c_kalman_q.md) is row 4. The natural
progression is then:

```
row 4   →   row 5    →   row 7 or row 11    →   row 10
fix θ       relax θ      richer Q prior        regime structure
```

Each step adds one degree of structure on top of the previous. None
require throwing the previous code away — the forward solver is shared,
the Kalman/likelihood layer changes, and the prior structure on `(θ, Q)`
changes with it.

## 5. The takeaway

Pick your work program by deciding which **prior** is the next bottleneck
on physical realism, not by which inference algorithm sounds fancy:

- Residual has structure at the diurnal frequency? → daily-Fourier
  component on Q (P7).
- Residual has rare spikes? → sparse / jump-Markov (P8-P9).
- Multiple rooms have similar envelope? → hierarchical θ (θ.4).
- Envelope degrades over months? → slow random walk on θ (θ.5).
- Solar gain looks underestimated at midday only? → covariate-dependent
  Q (P10) with a solar-proportional component.

The Kalman + random-walk-Q model is the *minimum viable* Bayesian step
above a deterministic fit: one extra knob (`σ_Q`), one extra time series
out (`Q(t)`), no new framework. Once it's running, the residual
structure tells you which row of the table to climb to next.
