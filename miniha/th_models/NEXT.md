# th_models — ideas and directions

Brain-dump of where the model could go next. Not a roadmap — a menu.
Refer to [model_theory_1r1c.md](model_theory_1r1c.md) for the physics
context; refer to [README.md](README.md) for the current state.

The three obvious axes — and a fourth one (measurements) that's worth
its own column.

---

## Axis 1 — Model complexity / fineness

Ordered roughly by payoff per unit of work, following the theory doc §3.

### 2R2C (separate wall mass) — top of the ladder

Two coupled ODEs, splits fast air dynamics from slow wall dynamics. Fixes
the solar phase-lag that 1R1C structurally cannot represent (theory doc
§2.4, §3). `T_wall` is latent → forces a state-space fit (Kalman or NLS
on simulated trajectories), which conveniently also unlocks Axis 2.

**Decision rule** from §6: do it if the current residual shows a diurnal
ripple lagging the solar peak by 2–4 h. Otherwise, the wall mass isn't
the bottleneck.

### Sol-air temperature (lower effort, often 80% of the win)

Collapse `T_out + I_solar` into one effective driving temperature
`T_sa = T_out + α·I_solar/h`. Keeps the model 1R1C but removes the
`T_out`/`I_solar` correlation that made `g_solar` come out negative.
Worth trying before 2R2C as a sanity check on whether the problem is
"model structure" or just "regressor collinearity".

### Per-window astronomical solar

Sun position from time + lat/lon, project onto each window's
plane-of-array, sum the contributions. Makes `a` physically interpretable
(m² × shading × transmittance per window). **Don't do this before 2R2C** —
without a wall node to land the gain on, sharper solar input is wasted
(theory doc §3 ladder).

### Wind-driven infiltration term

`R_eff` varies with wind speed → add `v_wind · (T_out − T_in)` to G(t).
Cheap if Open-Meteo `wind_speed_10m` is already pulled. Probably small
effect unless the house is draughty.

### Better integrator

FE → exponential / ZOH. At Δt = 15 min and τ ~ days, the schemes differ
by < 1% (theory doc §4.1). Not worth doing for accuracy. Worth doing if
we ever want to support coarser Δt (hourly inputs without losing
exactness).

---

## Axis 2 — Fit procedure

### Simulation-based (output-error) fit

Already laid out in §4.2 of the theory doc. Penalises cumulative drift
instead of one-step error. Forced by 2R2C anyway. Warm-start from the
current OLS estimate. ~30 lines with `scipy.optimize.least_squares`.

### Multiple-shooting variant

Chop the fit window into chunks (weekly), re-anchor each chunk's initial
state on observation, share one global parameter set. Robust for long
windows. ~10 extra lines on top of single-shot.

### Sliding-window fits → parameter drift plots

Re-fit per week, plot `τ(t)`, `ΔT_eq(t)`, `g_solar(t)`. This is where
"curtains closed for a month", "vacation", "window open all summer" show
up as visible parameter drift. Already on the original NEXT list.

### Regime detection / segmentation

Three options, roughly in increasing cleverness:

1. **Manual YAML exclusions** — already the documented path (theory doc
   §6, original NEXT.md). Cheapest, most honest.
2. **Residual-driven change-point detection** — automatically flag windows
   where the residual mean shifts. Surfaces events for the human to label.
3. **Latent-state HMM** — two regimes (sealed / leaky), let the data
   segment itself. Principled but adds a lot of moving parts; only worth
   it if (1) and (2) become unworkable.

### Frequency-domain fit

Take FFT of `T_in`, `T_out`, `I_solar`, fit the transfer function
`H(ω) = T_in/T_out`. The thermal lag is the phase of H at the diurnal
frequency — read τ off the Bode plot directly. Robust to slow drift.
Speaks the vision doc's language (lag, hysteresis) natively.

### ARX / black-box diagnostic

Fit `T_in[k] = a₁T_in[k-1] + a₂T_in[k-2] + b·T_out + c·I_solar` with
statsmodels. Two poles = two time constants. Tells you whether a second
time constant is actually present in the data **before** you commit to
building 2R2C. Diagnostic only, ~5 lines.

### GP residual diagnostic

Fit 1R1C, then model the residual with a GP over (hour-of-day, T_out,
I_solar). The GP's learned structure quantifies what's missing — if it
picks up a strong hour-of-day kernel with a 3 h lag, that's the 2R2C
signal, made numerical.

---

## Axis 3 — Connect to physical values

Limited by the identifiability ceiling: from temperature alone, R and C
are not separately identifiable (theory doc §5). To pin parameters to
physical units we need **a measured heat flow** — see Axis 4.

That said, two directions exist even without new sensors:

### Material / geometry priors

User declares wall construction (stone 40 cm, brick 20 cm, …), glazing
area, orientation. Convert to prior distributions on `R` and `C`. Bayesian
fit instead of OLS. Removes the scale degeneracy by *prior*, not by
*data* — which is honest only if priors are well-calibrated.

### Comfort-oriented derived quantities

The vision doc reframes the project around comfort, not engineering
U-values. Derived metrics worth surfacing:
- Effective thermal lag at the diurnal frequency (hours).
- Predicted indoor swing for a given outdoor swing (amplitude ratio).
- "Should I open my window tonight?" — driven by τ and current
  T_out forecast, not by R and C individually.

These are computable from the identifiable triplet `(τ, ΔT_eq, g_solar)`
without ever pinning R and C separately.

---

## Axis 4 — Other measurements

The single most leverage-changing axis. Ordered by bang-per-buck.

### Wall surface temperature — highest leverage

One DS18B20 taped to an interior wall. Direct read of `T_wall` turns
2R2C from a latent-state problem into a plain regression. Also directly
tests the deepest 1R1C assumption (§2.2 — air ≠ thermal mass).

### Daikin power readout — kills the identifiability degeneracy

Already wired in the house per `config/sensors.yaml`. Measured Φ_heat is
what separates R from C (§5), pins parameters to physical units, enables
COP estimation, lets us compare measured vs predicted heating energy.

### CO₂

Drops sharply on window-open, rises with occupancy. Free event detection
— replaces manual YAML exclusions. Vision doc already flags it as
comfort-relevant.

### Door / window reed switches

Home Assistant territory. Binary inputs straight into G(t) as known
events. Strictly better than HMM inference if the hardware is there.

### Humidity gradient (indoor − outdoor RH)

Proxy for ventilation / infiltration rate. Combined with ΔT, gives an
estimate of the wind/infiltration term (Axis 1).

### Floor or ceiling temperature — stratification check

If floor and ceiling diverge by > 2 °C, the "one T_in" assumption (§2.1)
is broken and no model improvement will help until nodes are split
vertically.

### MRT proxy (globe thermometer)

Ping-pong ball + sensor ≈ €2. Mean radiant temperature is what comfort
*actually* depends on (vision doc table). Almost never measured in homes
— would be a genuine differentiator if this becomes a comfort product.

---

## Combinations worth thinking about

- **Wall surface temp + Daikin power** → fully observed 2R2C with
  physical units. The "everything unlocks" config.
- **CO₂ + reed switches** → kills the manual-exclusion workflow, makes
  sliding-window fits actually clean.
- **Frequency-domain fit + ARX diagnostic** → confirms (or rules out)
  that 2R2C is worth building, before building it.

---

## If forced to pick one next thing

Two cheap, high-information moves before committing to any model upgrade:

1. **Look at the current residual** through the §6 diagnostic checklist.
   Diurnal lag of 2–4 h → 2R2C is the answer. Week-scale lobes →
   exclusions + simulation-based fit. Spikes → manual events.
2. **Stick a DS18B20 on an interior wall for two weeks.** Single input
   that most changes what models are even possible.

Everything else follows from what those two tell us.
