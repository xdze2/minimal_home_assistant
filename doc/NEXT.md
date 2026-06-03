# th_models — ideas and directions

Brain-dump of where the model could go next. Not a roadmap — a menu.
Refer to [model_theory_1r1c.md](model_theory_1r1c.md) for the physics
context; refer to [README.md](README.md) for the current state.

## North star

The real question isn't "what's the best thermal model" — it's
**"which intervention has the highest comfort payoff for this specific
room?"**. External shutters vs roof insulation vs night ventilation vs
internal blinds. The model is a means; the answer is a ranked list of
interventions with magnitude estimates ("shutters: −3 °C peak; roof
insulation: −1 °C; everything else in the noise").

This goal sharpens every choice below:

- The model must distinguish heat-input *pathways* (window solar ≠ roof
  solar ≠ south-wall solar ≠ infiltration), because interventions act on
  different pathways.
- Parameters must be expressible in **physical units** at least
  approximately, because interventions are physical perturbations
  ("halve U_roof"), not perturbations to `g_solar`.
- Uncertainty matters: a payoff estimate of "−2 °C" is worthless if the
  confidence interval is "[−5, +1]".

This is the gap in existing tools (see [../../doc/vision.md](../../doc/vision.md)):
declarative-input tools work for new builds with known materials;
black-box ML works for big buildings with lots of sensors. **A grey-box
with weak physical priors** sits in the middle, and that's exactly the
under-served regime for old / heterogeneous European houses.

---

## The specific room

Top-floor bedroom, **two windows + south wall + roof**. This geometry
changes the modelling priorities versus a generic interior room:

- **Three solar entry paths with three different time signatures**:
  windows (fast, transmitted through glass, instant), south wall (slow,
  conducted+radiated, 4–8 h lag depending on thickness), roof (medium-slow,
  conducted from above, dominates per m² because of near-normal incidence
  and dark surface).
- A single `I_solar` regressor smears these together. The negative
  `g_solar` artefact is partly this.
- Top-floor + roof = the **summer overheating** regime is where this
  room matters most. Winter U-value losses are dull; "how hot is it on
  July 15 and does opening windows at 3 AM help?" is the live question.
- The roof argues for a 2-node structure where the **ceiling/roof mass**
  is the second node (not the textbook "wall"). Solar lands on the
  ceiling node, leaks into the air node over hours.

---

## Axis 1 — Model structure

Ordered by payoff *for the intervention-ranking goal*. This is a
re-ordering of the textbook ladder in theory doc §3.

### Multi-aperture solar (do first)

Split `I_solar` into one signal per surface:

$$
G(t) = Q_0 + a_\text{win1} I_\text{poa,win1} + a_\text{win2} I_\text{poa,win2} + a_\text{wall,S} I_\text{poa,wall} + a_\text{roof} I_\text{poa,roof}
$$

Plane-of-array (POA) irradiance computed from sun position
(time + lat/lon + surface azimuth/tilt) and Open-Meteo broadband
shortwave. The four POA curves have **different daily phases**, so OLS
can separate the coefficients — no longer collinear the way one
`I_solar` was with `T_out`.

**Still linear in parameters → still OLS-compatible.** Bigger regressor
matrix, that's it.

Caveat: identifying four solar coefficients needs sky-condition variety
(sunny, cloudy, partly-cloudy days mixed). A week of identical sunny
days won't disambiguate them.

### Ceiling/roof mass as a second node

The right 2-node cartoon for *this* room:

```
T_out ──R_roof_ext── T_ceiling ──R_roof_int── T_in (air)
                          ↑                       ↑
                     I_solar_roof          I_solar_windows
                     I_solar_wallS         (instant)
                     (lagged)
```

Solar gain lands on `T_ceiling` (where it physically goes), feeds the
air over hours. Fixes the phase lag that 1R1C structurally cannot
represent (§2.4). `T_ceiling` is latent → forces a state-space fit
(Axis 2).

**Decision rule** (§6): build this if the residual after multi-aperture
1R1C still shows a diurnal ripple lagging the solar peak by 2–4 h.

### Sol-air temperature (lower-effort 1R1C patch)

Collapse `T_out + α·I_solar/h` into one driving signal. **Important
clarification**: just rewriting the model with `T_sa` is algebraically
identical to the current 1R1C+solar — same OLS, same collinearity, same
negative `g_solar`. The patch only helps if you **fix or pre-fit** the
sol-air coefficient from an external source (handbook value, or fit it
once on a sunny cold spell where `T_out` and `I_solar` are not
correlated, then freeze).

Worth knowing about, probably not worth doing given that multi-aperture
solar is cheap and strictly better.

### Window-open / ventilation regime

Let R vary with a binary "window open" signal: `R = R_sealed` normally,
`R = R_open` when reed switch reports open (or CO₂ drops sharply, see
Axis 4). Makes night ventilation a *first-class input* the model can
counterfactually simulate.

### Wind-driven infiltration

`R_eff` varies continuously with wind speed. Add `v_wind · (T_out − T_in)`
to G(t). Cheap if Open-Meteo wind is pulled. Probably small effect
unless the house is draughty.

### Better integrator

FE → exponential / ZOH. At Δt = 15 min the schemes differ by < 1 % (§4.1).
Worth doing if we ever want coarser Δt. Not for accuracy at current Δt.

---

## Axis 2 — Fit procedure

### Equation-error OLS (current) vs output-error simulation (next)

Two genuinely different questions of the data:

- **Equation error** (current OLS): minimises one-step jump residuals,
  re-anchored on observed `T_in[k]` at every step. Implicit noise
  model: random forcing on the ODE itself, observations taken as truth.
  Errors don't accumulate.
- **Output error** (simulation-based): minimises trajectory residuals,
  with the model integrated forward from `T_in[0]`. Implicit noise
  model: ODE is deterministic, sensor adds noise. Errors accumulate.

Same model, different preferred parameters. The negative `g_solar` is
partly an equation-error symptom: per-step the misallocation looks fine
because `T_out` and `I_solar` are correlated at 15 min; cumulatively
it drifts. Output-error fitting sees the drift.

Both are special cases of the Kalman filter (process + measurement
noise jointly). That's not a coincidence — when 2R2C makes `T_ceiling`
latent, the Kalman filter falls out naturally.

### Simulation-based (output-error) NLS

Already laid out in §4.2. Warm-start from OLS. `scipy.optimize.least_squares`,
TRF method. ~30 lines.

### Multiple-shooting

Chop the fit window into chunks (weekly), re-anchor each chunk's
initial state on observation, share global parameters. Robust for long
windows. ~10 extra lines.

### Kalman filter / EKF

The principled fit when there are latent states (2R2C: `T_ceiling`
unobserved). Handles mixed process + measurement noise correctly.
Worth it once Axis 1 forces it.

### Sliding-window fits → parameter drift plots

Re-fit per week, plot `τ(t)`, `ΔT_eq(t)`, etc. Surfaces "curtains
closed for a month", "window open all summer" as visible drift. Already
on the original NEXT list. Most useful **after** multi-aperture solar,
because then drift in a specific `a_*` is physically meaningful.

### Regime detection / segmentation

Three options, increasing cleverness:

1. **Manual YAML exclusions** — already the documented path (§6,
   original NEXT.md). Cheapest, most honest.
2. **Residual-driven change-point detection** — auto-flag windows where
   residual mean shifts. Human labels them.
3. **Latent-state HMM** — two regimes (sealed / leaky), data
   self-segments. Principled, lots of moving parts. Last resort.

If reed switches or CO₂ are available (Axis 4), all of this becomes
unnecessary — the events are observed.

### Frequency-domain fit

FFT of `T_in`, `T_out`, `I_solar`, fit transfer function `H(ω) = T_in/T_out`.
Thermal lag is the phase of H at the diurnal frequency — read τ off the
Bode plot directly. Robust to slow drift. Speaks the vision doc's
language (lag, hysteresis) natively.

### ARX / black-box diagnostic

Fit `T_in[k] = a₁T_in[k-1] + a₂T_in[k-2] + b·T_out + c·I_solar` with
statsmodels. Two poles = two time constants. Tells you whether a second
time constant is actually present in the data **before** committing to
2R2C. Diagnostic only, ~5 lines.

### GP residual diagnostic

After fitting 1R1C, model the residual as `r[k] ~ GP(0, kernel)` with
feature vector `x[k] =` (hour of day, T_out, I_solar lagged by 0/1/2/3 h).
Use an **additive kernel** so the fit attributes residual variance to
each feature group separately.

What it tells you:

- **Kernel amplitudes** quantify "how much residual variance is
  explained by hour-of-day vs lagged solar vs T_out". A variance budget.
- **The learned mean function `f(x)`** plotted against lagged solar:
  if it peaks on `I_solar[k−3h]`, not `I_solar[k]`, that's the wall mass
  releasing heat after the sun has set, made numerical. Quantitative
  version of the §6 "diurnal ripple lagging solar by 2–4 h" diagnostic.

`scikit-learn`'s `GaussianProcessRegressor` with an additive kernel does
this in ~20 lines. **Diagnostic, not a forecaster.** The GP will find
*something*; discipline is to use features tied to physical hypotheses
you'd act on (lagged solar → 2R2C; hour-of-day with no T_out dependence
→ unmodelled occupancy / heater; T_out · v_wind → infiltration term).

---

## Axis 3 — Priors / physical-value estimation

**This is probably the most distinctive thing the project can do.**
Existing tools split into two camps:

- **Declarative-input** (RT2012, RE2020, EPC, DesignBuilder): user
  specifies materials, areas, U-values; tool computes loads. Works for
  new builds with known materials. Useless for old heterogeneous
  buildings where the "true" U-value is anyone's guess.
- **Black-box ML / pure data fits**: enough sensors + enough data →
  predict whatever. Works for big buildings; doesn't scale down to one
  room with a Sonoff thermometer; doesn't give you physical
  interpretation.

**A grey-box with weak physical priors sits exactly in the gap.** Old
European houses have *roughly* known construction (you can see the
walls, you know the rough age, you can put plausible bounds on U-values
and thermal mass even without measurement). These priors are
order-of-magnitude correct (±30–50 %), which is much better than flat
and much worse than data — exactly the regime Bayesian inference is
designed for.

### Why this matters for the comfort tool

The identifiability ceiling (theory doc §5) is real but **soft**. Data
fixes `τ`, `ΔT_eq`, `g_solar`. A weak prior on R breaks the `R ↔ Q_0`
and `R ↔ a` degeneracies enough to report parameters in **physical
units with honest uncertainty bands**. This is the prerequisite for
intervention simulation: shutters perturb `a_win`, roof insulation
perturbs `R_roof`, and the perturbation magnitudes are physical
("U_roof goes from 1.5 to 0.3 W/m²K"), not identifiable
combinations.

### Where the priors come from

- Wall construction → R per m² from handbook (stone 40 cm: U ≈ 1.7
  W/m²K; brick 22 cm + plaster: U ≈ 1.4; modern insulated: U ≈ 0.3).
  × surface area = conductance.
- Window: count × area × glazing type → R_window from handbook.
- Roof: construction → R_roof.
- Floor area × ceiling height × volumetric heat capacity of furnished
  room (~30–50 kJ/m³K for furnished, ~1.2 for air alone) → C_air-node.
- Wall + floor + ceiling area × thickness × ρ·c of materials →
  C_mass-node. Stone room: 10⁴–10⁵ kJ/K easily.

The user supplies these in the YAML, with explicit uncertainty bands:

```yaml
priors:
  R_walls:   { value: 0.45, sigma: 0.20, units: "K/W" }
  R_roof:    { value: 0.30, sigma: 0.15, units: "K/W" }
  C_mass:    { value: 8.0e4, sigma: 2.0e4, units: "kJ/K" }
  a_win_S:   { value: 1.2, sigma: 0.4, units: "m²" }
```

### Three implementations, increasing power

**1. Penalised least squares (cheapest, OLS-compatible).** Add a
quadratic penalty:

$$
J(\theta) = \sum_k r[k]^2 + \sum_i \lambda_i \left(\frac{\theta_i - \theta_i^\text{prior}}{\sigma_i^\text{prior}}\right)^2
$$

Ridge regression with a non-zero target. Still linear, still
closed-form, still subsecond. `σ_i^prior → ∞` recovers plain OLS;
`σ_i^prior → 0` makes the prior win. Directly fixes negative `g_solar`
with a prior "solar gain is non-negative, ~5 °C per kW/m²".

**Do this first**, before any structural changes. 10 lines on top of
the current OLS.

**2. MAP estimation with log-normal priors.** Positive quantities
(R, C, a) live on a log scale. Reparameterise (`log R`, `log C`) and
put Gaussian priors on log-parameters. Loss is non-linear, no closed
form, but `scipy.optimize.least_squares` handles it. Free once you've
moved to simulation-based fitting (Axis 2) anyway.

Lets you express "R is between 0.5× and 2× of my handbook estimate"
naturally as a symmetric log-Gaussian.

**3. Full Bayesian posterior (MCMC / VI).** `pymc` or `numpyro`.
Posterior distribution over all parameters → can compute **intervention
payoffs with uncertainty**: "external shutters: −2.4 °C peak [95 % CI:
−1.6 to −3.1]". This is the actual product feature for the comfort
tool, not a nice-to-have.

Cost: minutes-to-hours of compute per fit, jax/pytensor dependencies,
debugging is harder. Worth it once the deterministic fit is solid and
the model topology is settled.

### Footgun: priors interact with fit method

`σ_prior` is calibrated relative to the *data term*. The data term has
very different magnitudes in equation-error OLS (per-step jumps,
small) vs output-error fitting (trajectory residuals over long windows,
large). A `σ_prior` tuned for one is invisible or dominant in the
other. **Re-tune priors when you switch fit methods**, or normalise the
data term (divide by N, divide by residual variance) so the comparison
is apples-to-apples.

This is the kind of detail that should land as one paragraph in
[model_theory_1r1c.md](model_theory_1r1c.md) when the
simulation-based fit is implemented.

### Comfort-oriented derived quantities

Even without pinning R and C separately, the identifiable triplet
`(τ, ΔT_eq, g_solar)` supports comfort metrics:

- Effective thermal lag at the diurnal frequency (hours).
- Predicted indoor swing for a given outdoor swing (amplitude ratio).
- "Should I open my window tonight?" — driven by τ and current T_out
  forecast.

These are computable today and worth surfacing in the inspector.

---

## Axis 4 — Other measurements

The single highest-leverage axis. Ordered by bang-per-buck **for this
top-floor room**.

### Ceiling surface temperature — **#1 for this room**

One DS18B20 taped to the ceiling. Directly measures the roof-mass node
that solar lands on first and that radiates downward at night. Turns
the latent state in the 2-node model into an observed one → plain
regression, no Kalman needed. Single sensor that most changes what
models are even possible.

Also: roof-insulation interventions partly act through radiant comfort
(ceiling stops being hot at night). An air-temperature-only model
underestimates their benefit; a ceiling sensor catches this.

€5, two weeks of data, possibly the only Axis-4 sensor you need.

### South interior wall surface temperature

DS18B20 on the south wall interior surface. Same logic as the ceiling
but for the wall-mass node. If both ceiling and wall surface temps are
measured, the 3-node model (air / ceiling / wall) is *fully observed*.

### Daikin power readout

Already wired per `config/sensors.yaml`. Measured Φ_heat breaks the
R ↔ C degeneracy (§5), pins parameters to physical units, enables COP
estimation. **Heating-side; less relevant for the summer overheating
question** that drives this room — demoted from where it was before.

### CO₂

Drops sharply on window-open, rises with occupancy. Free event
detection — replaces manual YAML exclusions. Vision doc flags it as
comfort-relevant.

### Door / window reed switches

Home Assistant territory. Binary inputs straight into G(t) as known
events. Strictly better than HMM inference if hardware is there.
Directly feeds the "ventilation regime" Axis-1 extension.

### Humidity gradient (indoor − outdoor RH)

Proxy for ventilation / infiltration rate. Combined with ΔT, gives
an estimate of the wind/infiltration term.

### Floor or ceiling air temperature — stratification check

If floor and ceiling *air* diverge by > 2 °C, the "one T_in"
assumption (§2.1) is broken and no model improvement helps until
nodes are split vertically. Diagnostic, not part of the production
model.

### MRT proxy (globe thermometer)

Ping-pong ball + sensor ≈ €2. Mean radiant temperature is what comfort
actually depends on. Almost never measured in homes. Genuine
differentiator if the comfort tool ships.

---

## Axis 5 — Intervention simulation

This is what turns the model from a curve-fit into the answer to the
real question.

### The workflow

1. **Reference week**: pick a representative hot week from history
   (sunny, real heatwave).
2. **Comfort metrics**: hours above 26 °C, peak indoor temperature,
   day-night swing, time in discomfort zone. **Not** kWh/year.
3. **Per-intervention input perturbation**:
   - External shutters on south windows → multiply `I_poa,win_S` by
     ~0.15 during daylight.
   - Reflective film → multiply `I_poa,win` by ~0.5.
   - Roof insulation (U: 1.5 → 0.3) → divide `1/R_roof` by 5.
   - Ceiling insulation from below → similar, but roof mass moves
     *outside* the insulation envelope (different `C_mass` placement).
   - South wall ITE → divide `1/R_wall_S` by some factor.
   - Night ventilation → set `R_vent` low between 23:00 and 06:00 if
     `T_out < T_in`.
   - Thermal mass activation → shutters during day + night vent;
     gain is the *interaction*, captured for free by the model.
4. **Re-simulate** the same week with perturbed inputs. Compute the
   comfort metrics. Δ = intervention payoff.
5. **Rank** with uncertainty bands from the posterior (Axis 3).

### Honest caveats to surface in the UI

- Absolute payoffs probably wrong by 20–50 %. Ranking and order of
  magnitude are robust; precise numbers aren't.
- Interventions interact non-linearly (shutters + night vent ≫ sum of
  each alone). Model captures this for free; don't average individual
  payoffs to estimate combinations.
- Behaviour-dependent interventions ("night ventilation") show the
  *upper bound* (perfect execution), not what the user will actually do.
- Without ceiling surface measurement, the model is blind to radiant
  asymmetry → underestimates payoff of roof / ceiling interventions.

### API sketch

```python
sim = simulate_intervention(
  model=fitted_model,
  week=ref_week,
  perturbations={
    "I_poa_win_S": lambda t, v: 0.15 * v if is_daylight(t) else v,
    "R_vent":      lambda t, v: 0.1 if 23 <= hour(t) < 6 and T_out < T_in else v,
  },
)
metrics = comfort_metrics(sim)  # peak_T, hours_above_26, swing, ...
```

A small Streamlit page that lets the user toggle interventions and see
metrics + uncertainty bands shift live = the tool the vision doc
describes.

---

## Axis 6 — Implementation strategy: generic solver vs hard-coded

Real engineering tradeoff, not a textbook one.

### The hard-coded path (where we are)

Each model — 1R1C, 2R2C, 3R2C-with-roof — is its own ODE, its own
discretisation, its own regressor matrix. ~100 lines per variant.

Pros: every line inspectable, linear algebra explicit, debugging is
"read the code", theory doc maps 1:1 onto implementation.

Cons: 4 model variants = 4 parallel implementations of the same physics
that **will drift apart** as features are added. Adding a "ceiling node"
to 2R2C is another rewrite.

### The generic-solver path (thermal network as electrical circuit)

Model = graph: nodes (capacitances), edges (resistances),
heat sources, boundary temperatures.

```python
nodes = {
  "air":     Node(C=C_air, T0=...),
  "ceiling": Node(C=C_ceiling, T0=...),
}
edges = [
  Resistor("air", "ceiling", R=R_int),
  Resistor("ceiling", "T_out", R=R_roof),
  Resistor("air", "T_out", R=R_walls),
  HeatSource("air", signal=I_win),
  HeatSource("ceiling", signal=I_roof),
  ConstantGain("air", Q=Q0),
]
```

Generic `assemble()` builds the state-space matrices:
`C dT/dt = −L T + B u(t)`, where `L` is the weighted graph Laplacian.
Literally nodal analysis from circuit theory.

Pros: **new topology = new dict, not new code**. Discretisation in one
place; swapping integrators is a one-line change benefiting every
model. Jacobian for output-error fit from autodiff over the assembled
matrices. Topologies serialisable to YAML alongside `chambre.yaml`
(`models/chambre_2r2c_with_roof.yaml`) — natural extension of the
current config-driven design.

Cons: harder upfront. Debugging shifts to "read the assembled matrix" →
need a `print_system()` method. Performance irrelevant at N ≤ 10 nodes.

### Recommendation

**Don't build the generic solver yet.** Build the second model
(multi-aperture 1R1C, then 2R2C with roof) by hand, suffer the
duplication consciously, and **then** extract the common structure.
Building the abstraction before the second concrete case = textbook
trap.

**Intermediate path**: write the second model as explicit `(A, B, C, D)`
state-space matrices, by hand, in `fit.py`. Captures most of the
integrator-independence and autodiff benefits without committing to a
graph DSL. If a third model also fits cleanly into `(A, B, C, D)`,
*then* generalise to the graph form.

The Python building-physics ecosystem is sparse: Modelica /
EnergyPlus / TRNSYS are heavy and inappropriate; `sippy` is for system
ID generally, not thermal networks specifically. Rolling our own on
scipy is the right call.

---

## Concrete first moves

Two cheap, high-information moves before committing to anything
structural:

### 1. Plot before modelling

Take last summer's hottest week. **Just plot**:

- Indoor temp vs outdoor temp, time series.
- Day-night swing of indoor vs outdoor.
- Lag between outdoor peak and indoor peak.
- Plane-of-array irradiance for each window, the south wall, the roof,
  all on the same axes.

If indoor tracks roof POA with a 3 h lag → roof insulation is the
answer. If indoor tracks window POA instantaneously → shutters are.
**Possibly the answer is in the raw data before any fit.**

### 2. Stick a DS18B20 on the ceiling for two weeks

The single input that most changes what models are possible. €5 of
hardware, biggest information gain for the summer overheating
question.

Everything else follows from what these two tell us.

### 3. Add penalised LS with weak priors to the current OLS

Independently of (1) and (2). 10 lines, fixes negative `g_solar`,
makes the YAML config the place where user knowledge enters the fit.
The smallest possible step in the direction of the project's
distinctive contribution.
