# Time-varying parameter model — energy bilan with structured drift

Third theory note, alongside [model_theory_1r1c.md](model_theory_1r1c.md)
(the static grey-box currently fitted) and
[model_families.md](model_families.md) (the broader taxonomy).

This file documents a **unified formulation** in which *every* parameter
of the energy balance is a time-varying random variable at every 15-min
step, with structured priors that distinguish what can drift fast, slow,
or not at all.

The headline claim:

> The "state vs. parameter" distinction is conventional, not
> mathematical. In a state-space formulation, latent temperatures and
> latent coefficients live in **the same vector**, distinguished only by
> the structure of their priors. The modelling decision is the **prior
> on each one's dynamics**, not the label.

## 1. The energy bilan

Over a 15-min interval $\Delta t$ on the indoor air control volume:

$$
m_k\,(T_{k+1} - T_k) \;=\;
\Big[-h_{e,k}\,(T_k - T_{\text{ext},k})
\;-\; h_{i,k}\,(T_k - T_{\text{wall},k})
\;+\; Q_k
\;+\; \alpha_k\, I_{\text{rad},k}\Big]\,\Delta t \;+\; \eta_k
$$

Each term is a **power [W]** integrated over $\Delta t$; the LHS is
energy stored in the air + sensor inertia. $\eta_k$ absorbs measurement
noise and any unmodelled physics.

**Unknowns at each step $k$:**
- $m_k$ — air + sensor thermal mass
- $h_{e,k}$ — outdoor conductance (walls + leaks + windows + ventilation)
- $h_{i,k}$ — air-to-wall coupling
- $T_{\text{wall},k}$ — envelope temperature
- $Q_k$ — net injected power (heating − cooling)
- $\alpha_k$ — solar coupling

**Knowns at each step $k$:**
- $T_{k}$, $T_{\text{ext},k}$, $I_{\text{rad},k}$ — observed inputs

## 2. The fundamental problem: one equation, six unknowns

At each step the energy bilan gives **one** equation. The unknowns are
**six**.

Without further constraints, the posterior is "any combination that
explains $\Delta T_k$". That's algebra, not inference.

**Identifiability comes from priors that link timesteps** — i.e. from
structure on *how each parameter is allowed to change*.

This is the central modelling decision of the framework.

## 3. The state-space view

Promote every unknown to a state. Stack:

$$
\boldsymbol{\theta}_k =
\begin{bmatrix} m_k \\ h_{e,k} \\ h_{i,k} \\ T_{\text{wall},k} \\ Q_k \\ \alpha_k \end{bmatrix}
$$

**Observation equation** (the bilan, rearranged):

$$
T_{k+1} = T_k + \frac{\Delta t}{m_k}\Big[-h_{e,k}(T_k - T_{\text{ext},k}) - h_{i,k}(T_k - T_{\text{wall},k}) + Q_k + \alpha_k I_{\text{rad},k}\Big] + \eta_k
$$

**State transition** (parameter dynamics):

$$
\boldsymbol{\theta}_{k+1} = \boldsymbol{\theta}_k + \boldsymbol{\epsilon}_k,
\quad \boldsymbol{\epsilon}_k \sim \mathcal{N}(\mathbf{0}, \Sigma_\theta)
$$

The structure of $\Sigma_\theta$ — and the choice of Gaussian vs.
heavy-tailed vs. spike-and-slab — *is* the model.

This is family **E** of [model_families.md](model_families.md) (random-walk
parameters) applied to *every* parameter simultaneously. In the
econometric literature it is called a **Dynamic Linear Model (DLM)** or
**Time-Varying Parameter (TVP) state-space model**. In building physics
it is rare; most published work fixes parameters (static grey-box) or
uses discrete regimes (SLDS).

## 4. Why this resolves "is $T_{\text{wall}}$ a state or a parameter?"

It is **both, and the distinction does not exist** in this framework.

- A *state* is a quantity whose dynamics come from physics
  (the wall ODE: $m_\text{wall}\dot T_\text{wall} = h_i(T - T_\text{wall})$).
- A *time-varying parameter* is a quantity whose dynamics come from a
  "best guess" prior (slow random walk).

Mathematically, they go into the same state vector and are inferred by
the same filter. The only difference is the prior on their dynamics.

In our case:
- $T_{\text{wall},k}$ gets a **physics-based prior** (its own ODE)
- $h_{e,k}, \alpha_k, \dots$ get **random-walk priors**

Same machinery, different priors.

## 5. The structured-prior catalogue

A flat random walk on all six is unidentifiable: the framework cannot
distinguish "window opened" from "wall heated up" from "solar
coefficient changed" — they all explain $\Delta T_k$ equally well. The
prior structure is what makes parameters interpretable.

Practical assignment of priors:

| Parameter | Physical truth | Recommended prior | Typical $\sigma_\epsilon$ |
|-----------|----------------|-------------------|---------------------------|
| $m_k$ | Constant — room mass does not change | Delta (pin from geometry) or $\sigma_m \approx 0$ | 0 |
| $h_{i,k}$ | Constant — wall surface coupling | Constant or very slow Gaussian | very small |
| $m_{\text{wall}}$ | Constant — envelope mass | Constant or very slow Gaussian | very small |
| $T_{\text{wall},k}$ | Fast smooth — driven by wall ODE | **Physics-driven** (not random walk) | from ODE |
| $\alpha_k$ | Slow seasonal — sun angle, foliage | Slow Gaussian random walk | small |
| $h_{e,k}^{\text{baseline}}$ | Slow — slow envelope effects | Slow Gaussian random walk | small |
| $h_{e,k}^{\text{open}}$ | Sparse jumps — window events | **Horseshoe / spike-and-slab on increments** | bimodal |
| $Q_k$ | Sparse spikes — heating events | **Horseshoe / spike-and-slab on increments**, or observed | bimodal |

The key insight: **different physical phenomena need different prior
shapes.**
- Gaussian random walks → smooth slow drift
- Heavy-tailed (Student-t, horseshoe) → occasional jumps
- Spike-and-slab → mostly zero with rare spikes

Forcing everything into a Gaussian random walk is the mistake.

## 6. Identifiability in this framework

Even with structured priors, three soft constraints are mandatory:

### 6.1 Pin one absolute scale

The bilan is invariant under simultaneous rescaling of
$(m, h_e, h_i, Q, \alpha)$. **Pin $m$ from room geometry**
($m = \rho V c_p + $ sensor inertia) to fix the scale. Without this,
posteriors are over *ratios*, not absolute values.

### 6.2 Separate envelope from indoor

The terms $h_{e,k}(T_k - T_{\text{ext},k})$ and
$h_{i,k}(T_k - T_{\text{wall},k})$ are nearly collinear when
$T_\text{wall}$ slowly tracks $T_\text{ext}$. Identifiability of $h_e$
vs. $h_i$ relies on:
- the **wall ODE prior** (constrains $T_\text{wall}$ trajectory) and
- **periods of high $|T - T_\text{ext}|$ contrast** (cold nights, warm
  days)

A free-floating $T_\text{wall}$ with no ODE constraint kills $h_i$
identifiability.

### 6.3 Pre-allocate sparsity budgets

The horseshoe / spike-and-slab priors on $Q_k$ and $h_e^\text{open}$ each
imply a *prior expected event rate*. Set these from domain knowledge
("heating is on about 1h/day", "windows open maybe twice a week"). If
the priors expect more events than the data show, the model will
manufacture spurious events to fit noise.

## 7. Computational reality

For 1 year × 15 min = **35,040 steps × 6 parameters ≈ 210,000 latent
variables**.

Tractable options:

- **Extended Kalman Smoother** (linearise the bilinear terms
  $h_{e,k} T_k$, $h_{i,k} T_k$). Fastest, point estimate + Gaussian
  uncertainty. Available in `filterpy`, `dynamax`. Doesn't handle
  spike-and-slab priors cleanly.
- **Particle Filter / Smoother**. Handles non-Gaussian priors. Scales
  badly with state dimension; 6D may be borderline.
- **Variational Inference** in NumPyro / Pyro. Best balance for
  non-Gaussian priors at scale.
- **Full HMC / NUTS** (PyMC, NumPyro, Stan). Most honest, slowest.
  Feasible on a year of data with good parameterisation (non-centred,
  Kalman-marginalised latents).

None of these are off-the-shelf for building physics. Expect to roll the
model.

## 8. The two practical risks

### Risk 1: prior-dominated posteriors

One equation cannot pin six time-varying quantities. What you read out
is mostly what you assumed. The danger is reporting *"the posterior says
the window contributed X kWh"* when really the prior said the window
contributes approximately X kWh.

**Mitigation:** sensitivity analysis on every prior. Diagnostic plot:
prior vs. posterior overlay for each parameter trajectory. If posterior
≈ prior, the data did not inform that parameter and you cannot report
it.

### Risk 2: research-grade, not ship-grade

Months of prior tuning, identifiability diagnostics, and DLM literature
before the model produces stable, interpretable outputs.

## 9. Pragmatic middle path

Rather than committing to the fully time-varying formulation immediately,
the recommended progression is:

1. **Pin $m$ from geometry.** No inference needed.
2. **Pin $h_i$ and $m_\text{wall}$ from a static 2R2C fit** on a clean
   free-float week. Treat as known constants thereafter.
3. **Make $T_{\text{wall},k}$ a state** with physics dynamics.
4. **Keep $\alpha_k$ constant per season**, or piecewise constant per
   month — recover it from clean sunny days with no heating.
5. **Make $h_{e,k}$ and $Q_k$ time-varying with sparse-jump priors.**
   These are the *only* truly fast-varying physical quantities, and
   their jumps correspond to window and heating events.

This keeps the "time-varying parameter" story for the two things that
actually vary in regimes, and converts the rest to either constants or
slow-smooth states. It is well-posed, computationally tractable, and
keeps the interpretability that motivated the framework.

The full-TVP formulation in section 3 becomes the **theoretical
reference**; the pragmatic version in this section becomes the
**implementation target**.

## 10. Relation to the regime-switching family

In the limit where the random-walk variance is large but increments
concentrate on $\{0, \text{jump}\}$ (sparse priors), the time-varying
parameter model **converges to a regime-switching model**.

Specifically:
- $h_e(t)$ with horseshoe-on-increments prior ≈ SLDS with closed/open
  modes
- $Q(t)$ with spike-and-slab prior ≈ SLDS with heating off/on modes

The TVP framework and the SLDS framework of
[model_families.md](model_families.md) are therefore **two
parameterisations of the same physical assumption**:
- TVP says "this parameter is mostly constant but can jump"
- SLDS says "this parameter takes one of $K$ values, with Markov
  transitions"

Choose TVP if jump magnitude varies continuously (envelope leakage drifts
with wind on top of window events). Choose SLDS if jumps are well
quantised (heating is either off or at nominal power).

## 11. References

- West & Harrison, *Bayesian Forecasting and Dynamic Models* (1997) —
  canonical reference for Dynamic Linear Models with time-varying
  coefficients.
- Petris, Petrone & Campagnoli, *Dynamic Linear Models with R* (2009) —
  practical reference.
- Carvalho, Polson & Scott, *The horseshoe estimator for sparse signals*
  (Biometrika 2010) — heavy-tailed prior used for sparse jumps.
- Kitagawa, *Non-Gaussian state-space modeling of nonstationary time
  series* (JASA 1987) — foundational for non-Gaussian DLMs.
- Madsen & Holst, CTSM and CTSM-R papers — continuous-time stochastic
  grey-box for buildings; closest building-physics analogue (without
  spike priors).
