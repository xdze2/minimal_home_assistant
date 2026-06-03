# TODO — th_models handoff

Run tests: `UV_PROJECT_ENVIRONMENT=venv uv run pytest tests/ -v`
Run inspector: `UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py`

---

## What was done this session

### Decay-scan inspector improvements
- Added **fit curve overlay** on the decay plot: each accepted segment now
  shows the reconstructed exponential in red (opacity 0.55) on top of the
  indoor temperature.
- Added two new diagnostic scatter plots below the τ histogram:
  - **(τ, T∞) scatter** — cloud shape diagnoses regime stability; bimodal
    = two states (likely window open vs closed).
  - **T∞ − T_out vs mean solar** — direct per-segment solar gain regression,
    free of time-series collinearity. OLS trendline with slope in legend.
  - Both plots use `outdoor_temp` and `shortwave_radiation` from the cached
    room data.

### Generic sliding-window framework (`miniha/th_models/sliding/`)
Extracted the scan/merge machinery from `sliding_exp.py` into a
model-agnostic package. Any thermal model can be plugged in as a `Fitter`.

| File | Role |
|------|------|
| `sliding/protocol.py` | `WindowResult`, `Fitter` protocol |
| `sliding/scan.py` | `scan()`, `merge_grow()`, `resample_inputs()`, `to_dataframe()` |
| `sliding/exp_fitter.py` | Free-decay exponential fitter (same physics as old `sliding_exp.py`) |
| `sliding/rc_fitter.py` | 1R1C fitter with penalised OLS priors on (τ, ΔT_eq, g_solar) |

`sliding_exp.py` is still in place and the inspector still uses it directly —
the new framework is not yet wired into the UI.

### Tests (`tests/`, 42 tests, all passing)
- `tests/th_models/test_exp_fitter.py` — ExpFitter: recovery, rejections, noise, params_close
- `tests/th_models/test_rc_fitter.py` — RcFitter: recovery, rejections, prior effect, params_close
- `tests/th_models/test_scan.py` — generic scan/merge: resample, scan with both fitters, merge properties

---

## Next steps (priority order)

### 1. Wire RcFitter into the inspector UI
The `RcFitter` exists and is tested but is not yet reachable from the
inspector. The decay-scan tab currently hardcodes `ExpFitter`.

- Add a **fitter selector** to the `_render_decay_scan` sidebar (selectbox:
  "Exponential (free decay)" / "1R1C (T_out + solar)").
- When 1R1C is selected, pass `{"T_in", "T_out", "shortwave_radiation"}` to
  `scan()` instead of just `{"T_in"}`.
- The fit curve overlay in `_plot_decay_overlay` already uses
  `result._curve_fn` — it will work for RcFitter without changes, but
  `RcFitter.curve_fn` currently forward-integrates on the original window
  grid and interpolates. Verify visually that the overlay looks right.
- Expose the `RcFitterConfig` priors as inspector controls (at minimum: τ
  prior value and sigma, g_solar prior sigma).

### 2. Fix RcFitter curve_fn for the overlay plot
The current `curve_fn` in `rc_fitter.py` closes over the original window
numpy arrays and interpolates to requested timestamps. This works but the
`times` argument is assumed to start at `t_start` — see the line:
```python
t_abs = np.array([(ts - times[0]).total_seconds() for ts in times], dtype=float)
```
This should instead use `t_start` as the origin, not `times[0]`, to be
consistent with how `_plot_decay_overlay` calls it. Add a test for this.

### 3. (τ, T∞) scatter — identify the two regimes
The bedroom data shows a clear bimodal τ distribution (≈4h and ≈10h
clusters). Add a **regime split** to the scatter plots:
- Add a "τ threshold" slider to `_render_decay_scan`.
- Color the decay overlay segments by regime (fast = orange, slow = blue)
  instead of a single colour.
- This visually identifies which nights had the window open without any
  reed switch.

### 4. Segment-level solar regression
The `T∞ − T_out` vs solar plot shows a negative slope in winter (collinearity:
sunny days → higher T_out → smaller gap). Fix this with a **2D regression**
across segments:

```python
# Regress T_inf on (1, T_out_mean, I_solar_mean) per segment
# Then plot the partial residual: (T_inf - b0 - b1*T_out) vs I_solar
```

This recovers the solar gain coefficient free of the T_out correlation.
Add this as a third scatter plot (or replace the current one).

### 5. 2R2C fitter
Following the same pattern as `RcFitter`, implement `Rc2Fitter` (2R2C with
ceiling/roof mass node). Key additions:
- State vector is `[T_air, T_ceiling]`; only `T_air` is observed.
- Fit is output-error (simulate forward, minimise trajectory residual) —
  the equation-error OLS used in 1R1C doesn't extend cleanly to latent
  states.
- `scipy.optimize.least_squares` warm-started from 1R1C fit.
- Priors on `R_roof`, `R_int`, `C_ceiling` (from NEXT.md Axis 3).
- Merge criterion: same as 1R1C but on `(τ_air, τ_ceiling)`.

Decision rule (from NEXT.md): build this if the 1R1C residual still shows
a diurnal ripple lagging the solar peak by 2–4h.

### 6. Backward-compat: deprecate `sliding_exp.py`
Once the inspector uses `sliding/exp_fitter.py`, the old `sliding_exp.py`
can be reduced to a thin import shim or removed. Don't do this until the
UI switch is confirmed working.

---

## Known limitations / design notes

- **RcFitter prior scaling**: the prior on α (= dt/τ) is derived from σ_τ
  via first-order propagation (`σ_α = dt/τ² * σ_τ`). This means prior
  strength depends on window length (via the `1/n` normalisation in
  `λ_i`). Re-tuning priors when changing window length is documented in
  NEXT.md Axis 3 "Footgun" section.

- **ExpFitter T_inf grid search**: the grid-search approach for T_inf is
  only reliable when the window covers >1τ of the decay. Short windows
  (< τ/2) produce noisy τ estimates. The test tolerances reflect this.
  A proper fix would use scipy.optimize to fit T_inf jointly.

- **merge_grow quality threshold**: currently uses `r2_min` for both
  `ExpFitter` (where quality = R²) and `RcFitter` (where quality = −RMSE).
  These are not on the same scale. The merge API should use a
  fitter-specific threshold, or quality should be normalised. For now,
  set `r2_min` to a negative value (e.g. −0.5) when using RcFitter to
  effectively disable the quality gate and rely on `params_close` alone.
