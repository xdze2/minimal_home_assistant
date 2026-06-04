# Model families — a classification for grey-box identification

Companion to [model_theory_1r1c.md](model_theory_1r1c.md). That file
documents the specific 1R1C model fitted in `fit.py`. This file zooms out:
where does that model sit in the broader landscape of grey-box / state-space
identification, and what families of model are candidates when "boundary
conditions" (window open, heating on, occupancy, …) vary over time.

The headline claim:

> Model identification is not a single axis. It is **three orthogonal
> axes** — state type, time type, parameter type — and most "named"
> approaches (HMM, EKF, SLDS, ctsmr, …) are just specific cells in this 3D
> grid.

## 1. The three axes

| Axis | Options |
|------|---------|
| **State space** | continuous / discrete / **hybrid** |
| **Time** | continuous / discrete |
| **Parameters** | fixed / continuous drift / discrete regimes / random |

A 1R1C model is `continuous state × continuous time × fixed params`.
An HMM is `discrete state × discrete time × per-mode params`.
An SLDS is `hybrid state × discrete time × per-mode learned params`.
Everything else is somewhere in between.

## 2. The families, ordered by power

### A. Continuous state, deterministic ODE — *the current 1R1C fit*

$$\frac{dx}{dt} = f(x, u, \theta)$$

Parameters $\theta$ fixed. Inference by least squares, MLE, or
**Bayesian → posterior $p(\theta \mid \text{data})$** (PyMC, Stan, NumPyro).
Output: point estimate or distribution over $\theta$.

**Limit:** one regime, no process noise, parameters assumed constant for
the whole fit window.

### B. Continuous state, stochastic ODE (SDE) — *grey-box proper*

$$dx = f(x, u, \theta)\,dt + \sigma\, dW$$

Adds process noise. This is the **Madsen / ctsmr** framework. Inference:
Extended Kalman Filter for state, ML or Bayesian for $\theta$.

Process noise absorbs unmodeled physics — the residuals become honest,
parameter uncertainty becomes credible.

### C. Pure discrete state — HMM

$s_t \in \{1..K\}$ Markov chain, observation $y_t \mid s_t$.

Inference: forward-backward, Viterbi, Baum-Welch. Output: mode
probabilities + transition matrix.

**Limit:** no continuous dynamics. Observations are i.i.d. *within* a mode.
Wrong for thermal data — temperature has memory.

### D. Hybrid: continuous state + discrete regime — *the rich family*

Three named members, in increasing power:

**D1. Jump Markov Linear System / Switching State-Space Model**
- $s_t$ Markov chain over $K$ modes
- Each mode has its own linear dynamics
  $x_{t+1} = A_{s_t} x_t + B_{s_t} u_t + w_t$
- Mode transitions independent of $x$ (exogenous regime)
- Exact inference intractable; approximations:
  - **IMM** (Interacting Multiple Model) — Gaussian mixture collapsed at
    each step. Online, cheap. (`filterpy`)
  - **GPB** — same idea, different collapse
  - **Variational / Gibbs** offline — the "SLDS" formulation (`dynamax`,
    `ssm`)

**D2. Recurrent SLDS (rSLDS)**
- Same as D1, but $P(s_{t+1} = k \mid s_t, x_t)$ — regime depends on
  continuous state
- Models **endogenous** switching: "the heating turns on when $T <$
  setpoint" is exactly this
- Linderman et al. 2017, implemented in `ssm`

**D3. General Hybrid System / Stochastic Hybrid System**
- Continuous-time, both jumps and flows. Control-theory framework
- Most general, least off-the-shelf software

### E. Continuous state, parameters as slow random walk

Not regime-switching at all — parameters drift continuously.

$$\theta_t = \theta_{t-1} + \epsilon_t$$

with small variance. Implemented by augmenting the state vector with
parameters and running EKF/UKF on $[x_t, \theta_t]$.

Good for gradual change (insulation aging, sensor drift). Wrong for abrupt
change (window opens).

## 3. Where the named approaches sit

| Label | State | Time | Params | Regime | Tool |
|-------|-------|------|--------|--------|------|
| **Static grey-box** | continuous | continuous | fixed | none | scipy, current `fit_2r2c.py` |
| **Bayesian grey-box** | continuous | continuous | distribution | none | PyMC, ctsmr |
| **Stochastic grey-box** | continuous + noise | continuous | distribution | none | ctsmr / CTSM-R |
| **Sliding-window grey-box** | continuous | continuous | slow drift | implicit | current `sliding/` scan |
| **Joint state-param EKF** | continuous (incl. $\theta$) | discrete | random walk | none | filterpy, custom |
| **HMM** | discrete | discrete | per-mode | exogenous | hmmlearn, pomegranate |
| **IMM** | hybrid | discrete | per-mode, fixed | exogenous | filterpy |
| **SLDS** | hybrid | discrete | per-mode, learned | exogenous | dynamax, ssm |
| **rSLDS** | hybrid | discrete | per-mode, learned | endogenous | ssm |
| **Stochastic hybrid system** | hybrid | continuous | any | any | research code only |

Current `th_models` lives on the **Sliding-window grey-box** row.
The natural next step is **SLDS** or **rSLDS** (row 8–9).

## 4. How to choose, in practice

Two questions to ask about each nuisance variable (window, heating,
occupancy, …):

**Q1. Is it observed?**

- Yes (heating power readout, window contact sensor) → put it in $u$ as a
  known input. You stay in family A or B. **Do this first, always** — it
  buys more than any inference upgrade.
- No → you need a hidden regime → family D.

**Q2. How does the regime change?**

- Exogenously (someone opens a window) → **D1 / SLDS / IMM**
- As a function of continuous state (thermostat reacts to $T$) → **D2 /
  rSLDS**
- Smoothly over months (envelope aging) → **family E**

Real buildings are a mix. Occupancy is exogenous, thermostats are
endogenous, envelope drift is slow. Clean papers handle one cleanly; real
implementations stitch.

## 5. One concept worth internalising

The distinction between **"parameters that change"** and **"inputs you
forgot to measure"** is mostly philosophical. A window opening can be
modelled as:

- a hidden discrete regime that changes $R$ — **SLDS view**
- a hidden continuous input that subtracts heat — **disturbance Kalman
  filter / input-augmentation view**
- a time-varying parameter $R(t)$ — **random-walk view**

All three are mathematically near-equivalent given enough data. They
differ in the **prior structure** they impose:

- window opening = "rare jumps" → SLDS
- envelope aging = "slow drift" → random walk
- diffuse occupancy heat = "smooth continuous unknown" → disturbance KF

Picking the prior that matches reality *is* the modelling decision. The
library is just plumbing.

## 6. Implication for `th_models`

- The current sliding-window RC fit implicitly assumes "slow drift" — it
  is the random-walk view, done by re-fitting on overlapping windows
  instead of by an explicit augmented EKF.
- The likely next steps, roughly in order of effort / reward:
  1. **Input augmentation** — get heating power and window state into $u$.
     Cheapest win, biggest impact, no new framework.
  2. **Changepoint segmentation on residuals** — keep the existing fitter,
     add a regime layer on top. Still no new framework.
  3. **Bayesian 2R2C** (PyMC or ctsmr) — gives parameter uncertainty.
     Honest error bars on "what is the window contribution?".
  4. **IMM toy on one room** (filterpy) — first taste of hybrid
     state/regime inference; per-mode params hand-picked, not learned.
  5. **SLDS / rSLDS with learned params** (dynamax or `ssm`) — the
     research-grade destination.

## 7. References worth reading

- Madsen & Holst, *grey-box building thermal models* — the CTSM-R papers.
- Bacher & Madsen, *Identifying suitable models for the heat dynamics of
  buildings* (2011) — the canonical RC identification paper.
- Linderman et al., *Bayesian learning and inference in recurrent
  switching linear dynamical systems* (AISTATS 2017) — the rSLDS paper.
- Murphy, *Probabilistic Machine Learning: Advanced Topics* — chapters on
  state-space models, switching SSMs, and parameter learning.
- Roger Labbe, *Kalman and Bayesian Filters in Python* — IMM chapter is
  the gentlest entry point.
