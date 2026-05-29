# Grey-box thermal model — theory

This file documents the model behind `fit.py` and `simulate` in
[miniha/th_models](.). The headline claim:

> The model is **1R1C + G(t)** — one effective thermal resistance, one
> effective thermal capacitance, and a sum of heat-input terms. Everything
> else (which fields we pull, which integrator we use, how we minimise the
> loss) is downstream of that single modelling choice.

## 1. The physical assumption

We treat the room as a single **control volume** with one bulk temperature
$T_\text{in}$, exchanging heat with the outside through one effective
resistance $R$, with one effective heat capacity $C$ storing the energy.

**Energy balance over the control volume:**

$$
C \, \frac{dT_\text{in}}{dt} \;=\; \underbrace{\frac{T_\text{out}(t) - T_\text{in}(t)}{R}}_{\text{conduction (Fourier)}} \;+\; G(t)
$$

with $G(t)$ collecting all heat sources / sinks the model knows about:

$$
G(t) \;=\; Q_0 \;+\; a \, I_\text{solar}(t) \;+\; \dots
$$

In the current implementation:
- $Q_0$ — a constant lift covering internal gains, adjacent-room coupling,
  steady occupancy, etc.
- $a \cdot I_\text{solar}$ — solar shortwave gain, $a$ being an effective
  aperture (window area × shading × transmittance, m²-equivalent).

Future terms slot into $G(t)$ without changing the rest:
- $\Phi_\text{heat}(t)$ — heater / Daikin power readout (when wired).
- $(T_\text{adj}(t) - T_\text{in}(t)) / R_\text{adj}$ — coupling to corridor
  / adjacent rooms.
- Wind-driven infiltration $\propto v_\text{wind} \cdot (T_\text{out} - T_\text{in})$.

The form of the conduction term is fixed; the form of $G(t)$ is open.

## 2. What 1R1C is *really* assuming

This is the part that matters more than any integrator choice.

### 2.1 One temperature for the whole room

We collapse the room into a single $T_\text{in}$. In reality the air
near a window in the sun is hotter than the air in the opposite corner,
the floor is colder than the ceiling, the walls have their own temperature
profile through their thickness. The single-state model is a **spatial
average**. It is reasonable when:
- The room is well-mixed (open volume, no strong stratification).
- The sensor location is representative (or you treat the sensor as
  measuring some weighted average that happens to be roughly constant).

It breaks down for: large open-plan rooms with sunny corners, rooms with
strong stratification (cathedral ceilings), or sensors placed in atypical
spots (against a cold outside wall).

### 2.2 Air temperature ≠ thermal mass temperature

This is the deepest assumption. The Sonoff sensor measures the **air
temperature**. But the **energy is mostly stored in the building's solid
mass** — walls, floor, furniture — not in the air. The air capacity of
a 12 m² × 2.5 m bedroom is around $C_\text{air} \approx 40$ kJ/K. The
walls + furniture + floor are easily $10^4$ kJ/K. So the $C$ we fit is
**not the air capacity** — it's the effective capacity of the whole zone,
and what we're really doing is *pretending* the air, the walls, and the
furniture all sit at the same temperature $T_\text{in}$ and exchange heat
instantly.

In reality the air responds to changes in minutes, while the walls
respond in hours-to-days. The 1R1C model has only **one time constant**
$\tau = R \cdot C$, so it cannot represent both. The fit picks a $\tau$
somewhere between the two — usually closer to the wall time constant
because that's where most of the energy goes.

**Symptoms** of this lumping in the residual:
- The model *under*-responds to fast forcing (a quick opening of the
  window). The air drops fast, the model — bound to a multi-hour $\tau$
  — drops slowly.
- The model *over*-shoots on long sunny / cold spells, then over-corrects
  on the way back, because the wall mass is lagging differently from
  the air.

### 2.3 Linear conduction

$\Phi_\text{cond} = (T_\text{out} - T_\text{in})/R$ assumes the heat
flux is linear in the temperature difference, with constant $R$. In
practice $R$ may vary with wind (infiltration), humidity (latent heat
through walls), and curtain/blind position. We've ignored these.

### 2.4 Steady-state $G(t)$ decomposition

We assume the heat input decomposes as $Q_0 + a \cdot I_\text{solar}$,
with both terms acting *instantly* on the air. In reality solar gain
heats the **floor and furniture first**, and that heat then leaks into
the air over hours — i.e. the solar input has its own RC chain. With
only one $C$, we can't represent that delay; it shows up as a phase
error in the residual.

This is the strongest argument for moving from 1R1C to **2R2C** (next
section).

## 3. When to go beyond 1R1C

A 2R2C model adds a separate thermal mass for the walls/furniture:

```
         R_ext            R_int
T_out ─────/\/\───── T_wall ─────/\/\───── T_in
                       |                     |
                      C_wall                C_air
```

Two coupled ODEs:
$$
C_\text{air} \, \dot T_\text{in} = \frac{T_\text{wall} - T_\text{in}}{R_\text{int}} + G_\text{air}(t)
$$
$$
C_\text{wall} \, \dot T_\text{wall} = \frac{T_\text{out} - T_\text{wall}}{R_\text{ext}} + \frac{T_\text{in} - T_\text{wall}}{R_\text{int}} + G_\text{wall}(t)
$$

This decouples the fast air dynamics (small $C_\text{air} R_\text{int}$,
minutes) from the slow wall dynamics (large $C_\text{wall} R_\text{ext}$,
days). It also lets you put solar gain on the **wall** node (where it
physically lands) rather than directly on the air — which fixes the phase
lag that 1R1C can't model.

The cost:
- $T_\text{wall}$ is **unobserved** — you have to estimate it as a latent
  state at fit time. That kills the OLS-style closed-form fit; you need
  a Kalman filter or a state-space optimisation.
- Four parameters instead of two ($R_\text{ext}, R_\text{int},
  C_\text{air}, C_\text{wall}$), but only three are identifiable from the
  data we have. Same identifiability issue as 1R1C, one dimension worse.

**Heuristic for when to upgrade:** if after fitting 1R1C with solar +
constant gain the residual still shows a **systematic time-of-day shape**
that *lags* the solar peak by 2–4 hours, that's the 2R2C signal — the
wall mass releasing heat after the sun has set. Then 2R2C will pay off.
If the residual is mostly noise or driven by clearly external events
(window open, vacation), 1R1C is doing as well as it can.

Common extensions, roughly in order of payoff for a home thermal model:
1. **2R2C** (separate wall mass) — fixes solar phase lag.
2. **3R2C** with internal wall to neighbour room — captures adjacent-room
   coupling explicitly.
3. **Per-window plane-of-array solar** — uses sun position + window
   orientation, lets `a` be physically interpretable.
4. **Wind-driven infiltration term** — $R_\text{eff}$ varies with wind.

## 4. From physics to discrete fit

Given the continuous model above, fitting it to discrete samples is a
**two-step** choice:

1. **Quadrature / integrator choice** — how do we approximate the time
   integral of the flux balance over a sample interval $\Delta t$?
2. **Loss / fit choice** — once we have a discrete model, how do we
   measure misfit against the observations?

These two are *independent*. You can swap either without touching the
other, as long as you stay self-consistent (fit and simulate with the
same discretisation if you want clean diagnostics).

### 4.1 Finite-volume view of the integration step

Multiply the energy balance by $dt$ and integrate over
$[t_k,\, t_{k+1}]$:

$$
C \cdot (T_\text{in}[k+1] - T_\text{in}[k]) \;=\; \int_{t_k}^{t_{k+1}} \!\!\Bigl( \tfrac{T_\text{out}(t) - T_\text{in}(t)}{R} + G(t) \Bigr) \, dt
$$

The LHS is **exact** — it's the change in stored energy. All the
discretisation choice lives in how we evaluate the RHS integral.
Common choices:

| Quadrature rule | Resulting scheme | Local error | Solvable as OLS? |
|---|---|---|---|
| Left rectangle: flux at $t_k$ × $\Delta t$ | **Forward Euler** | $O(\Delta t^2)$ | Yes — all RHS terms known at $t_k$ |
| Right rectangle: flux at $t_{k+1}$ × $\Delta t$ | **Backward Euler** | $O(\Delta t^2)$ | Yes — `T_in[k+1]` is also an observation at fit time |
| Trapezoidal: avg of endpoints | **Crank–Nicolson** | $O(\Delta t^3)$ | Yes — average of two known regressors |
| Exact for piecewise-constant forcing | **Exponential / ZOH** | $O(\Delta t^2)$ from input shape only | Yes, but the regressor is $(1 - e^{-\Delta t / \tau})$, which is nonlinear in $\tau$ → no closed form, needs nonlinear least squares |

**Numerical note.** At our typical step ($\Delta t = 15$ min, $\tau =
18$–120 h), $\Delta t / \tau \approx 0.002$–0.014. The Taylor expansion
$1 - e^{-x} = x - x^2/2 + \dots$ tells us forward Euler and the
exponential integrator differ by $\sim x/2 \approx 0.7\%$ at the largest.
The schemes are practically indistinguishable. The reason to prefer one
over another at this scale is **not accuracy** — it's:
- conservation properties (FE perspective: every scheme above conserves
  total energy by construction),
- robustness to larger $\Delta t$ (the exponential integrator stays exact
  even at $\Delta t \sim \tau$),
- cleanness of the residual interpretation.

### 4.2 Fit methods

#### One-step (equation-error) OLS — current

After discretisation with **forward Euler**, the model reads (defining
$\alpha = \Delta t / \tau$, $\beta = \Delta t \cdot Q_0 / C$, $\gamma =
\Delta t \cdot a / C$):

$$
\Delta T_\text{in}[k] \;=\; \alpha \, (T_\text{out}[k] - T_\text{in}[k]) \;+\; \beta \;+\; \gamma \, I_\text{solar}[k]
$$

This is **linear in $(\alpha, \beta, \gamma)$**, with all regressors and
target observed. Stack over $k$, solve by OLS. What we do now.

**Pros:**
- Closed form, sub-millisecond, deterministic, no local minima.
- Standard-error covariance via $\sigma^2 (X^\top X)^{-1}$.

**Cons:**
- Predicts only **one step ahead**, always re-anchored on the observed
  previous value. Does not penalise drift over hours/days.
- Sensitive to correlated regressors. In our data, `T_out` and `I_solar`
  both peak in the afternoon → the fit can split heat input between
  $\beta$ and $\gamma$ in physically wrong ways without the loss
  complaining. (This is what we observed: $g_\text{solar}$ came out
  negative.)
- Implicitly assumes the measurement noise enters as additive noise on
  $\Delta T_\text{in}$, which is a strong assumption.

The OLS form is also available for backward Euler and trapezoidal
(both linear in parameters); only the regressor definitions change.

#### Simulation-based (output-error) fit — proposed next

Integrate the discretised ODE forward from $T_\text{in}^\text{sim}[0] =
T_\text{in}^\text{obs}[0]$ using only the parameters and the inputs.
Compare the *simulated trajectory* to the observations:

$$
J(\tau, \Delta T_\text{eq}, g_\text{solar}) \;=\; \sum_k \bigl( T_\text{in}^\text{sim}[k] - T_\text{in}^\text{obs}[k] \bigr)^2
$$

Minimise with a nonlinear least-squares solver (e.g.
`scipy.optimize.least_squares` with the TRF method, warm-started from
the OLS estimate).

**Pros:**
- Penalises *cumulative* drift, not just one-step prediction error. A
  wrong $g_\text{solar}$ sign causes the sim to drift hours later — the
  loss catches it.
- Decouples the fit objective from the noise model: we score the model
  on what we actually care about (trajectory).
- Naturally handles the integrator-independence story: you can swap
  forward Euler for the exponential integrator without changing the
  optimiser.

**Cons:**
- Non-convex (the simulation is recursive), so needs a starting point.
  The OLS fit is a good warm start.
- Each loss evaluation is $O(N)$ instead of $O(1)$ — but still ms-scale
  for our problem.
- Uncertainty estimates come from the Jacobian at the optimum, not from
  a closed-form covariance.
- Sensitive to large gaps in observations (you have to be careful to
  only score where you have measurements).

For long windows the single-shot version drifts; a **multiple-shooting**
variant chops the window into chunks (e.g. weekly), re-anchors each
chunk's initial state on observation, and shares one set of global
parameters. Best of both worlds, adds maybe 10 lines.

### 4.3 Why this separation matters

We can — and probably will — change the integrator (FE → exponential)
and the fit (OLS → simulation-based) independently. The **model itself
doesn't change**. The 1R1C+G physical assumption is what bounds how well
we can ever do, regardless of which numerical scheme we put underneath.
If after both upgrades the residual still has structure, the next step
is not a better integrator or a better optimiser — it's **a different
model** (2R2C, or adding a term to $G(t)$).

## 5. Identifiability

From temperature observations alone (no measured heat flux), the four
physical parameters $R, C, Q_0, a$ are not separately identifiable.
There's a common scale: multiply $R$ by $\lambda$ and divide $Q_0, a$
by $\lambda$, the trajectory $T_\text{in}(t)$ is unchanged. So the data
fixes only **three combinations** of the four physical parameters:

$$
\tau = R \cdot C, \qquad \Delta T_\text{eq} = Q_0 \cdot R, \qquad g_\text{solar} = a \cdot R
$$

Interpretation:
- $\tau$ — thermal time constant of the room (how fast indoor relaxes
  toward $T_\text{out} + \Delta T_\text{eq} + g_\text{solar} \cdot
  I_\text{solar}$).
- $\Delta T_\text{eq}$ — the steady-state lift above outdoor produced
  by the constant gain $Q_0$. Read directly off the data: average
  indoor − average outdoor − $g_\text{solar} \cdot$ average $I_\text{solar}$.
- $g_\text{solar}$ — the steady-state lift per W/m² of incident solar.
  An effective "°C per sun" coefficient.

To separate $R$ from $C$ (and thus pin $Q_0$ and $a$ to physical
units), we'd need to **measure a heat flow** — e.g. read the Daikin
power consumption while it's heating. That's a future extension.

## 6. What the residual is telling us, physically

Under the finite-volume form, the residual

$$
r[k] \;=\; T_\text{in}^\text{obs}[k] - T_\text{in}^\text{sim}[k]
$$

multiplied by $C$ is, to first order, **the energy unaccounted for by
the model** between $t_0$ and $t_k$. Sign convention used in the app
(observed − model):
- $r > 0$ → real room hotter than the model expected → unmodelled
  heat input (heater on, sun stronger than assumed, occupants present).
- $r < 0$ → real room colder than expected → unmodelled heat sink, or
  the constant-gain term $Q_0$ over-predicting baseline.

Shape diagnostics:
- **Diurnal ripple** in $r$ → unmodelled (or wrongly-modelled) solar
  gain. Fix: better solar term.
- **Diurnal ripple that *lags* the solar peak by hours** → 1R1C can't
  represent the wall mass dynamics. Fix: 2R2C.
- **Week-scale lobes** → unmodelled slow input (heater on for a week,
  cloudy week not captured by the solar term) or parameter drift
  (curtains closed, window open). Fix: add the missing input to $G(t)$,
  or move to sliding-window fits.
- **Spikes** → window opened, door left ajar, occupant change. Best
  handled as **manual exclusions in the YAML** (kept on the plot for
  diagnosis but dropped from the fit).

## References / further reading

- Bacher & Madsen, *Identifying suitable models for the heat dynamics
  of buildings*, Energy and Buildings 43 (2011) — the canonical 1R1C
  → 2R2C → 3R2C ladder for residential buildings.
- Reynders et al., *Quality of grey-box models and identified
  parameters as function of the accuracy of input and observation
  signals*, Energy and Buildings 82 (2014) — what goes wrong with grey
  boxes in practice.
- Madsen, *Time Series Analysis*, ch. 8 — state-space view of the
  same problem, basis for the Kalman-filter approach to 2R2C.
