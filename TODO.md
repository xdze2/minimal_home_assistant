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

### RcFitter wired into the inspector UI
- **Fitter selector** added to `_render_decay_scan`: "Exponential (free decay)"
  / "1R1C (T_out + solar)".
- When 1R1C is selected, `scan()` receives `{T_in, T_out, shortwave_radiation}`;
  quality slider shifts to −RMSE range; τ prior value and σ controls are shown.
- Scan and merge now go through `sliding/scan.py` for both fitters (the old
  `sliding_exp.py` path is still imported but no longer used by the UI).
- Overlay plot for 1R1C forward-simulates each segment via `_rc_sim_segment`
  using the stored (τ, ΔT_eq, g_solar) params and the outdoor/solar series.
- (τ, T∞) and T∞−T_out scatter plots are hidden when 1R1C is selected (they
  need T∞ which RcFitter doesn't produce).

### RcFitter curve_fn origin fix
- `curve_fn` in `rc_fitter.py` now anchors interpolation to `t_sec[0]`, not
  `times[0]`, so it stays correct if a caller passes times that don't start
  at the window origin.
- Two new tests in `TestRcFitterCurveFn` cover the initial condition and
  finite-output invariants (44 tests total, all passing).

### Tests (`tests/`, 44 tests, all passing)
- `tests/th_models/test_exp_fitter.py` — ExpFitter: recovery, rejections, noise, params_close
- `tests/th_models/test_rc_fitter.py` — RcFitter: recovery, rejections, prior effect, params_close, curve_fn
- `tests/th_models/test_scan.py` — generic scan/merge: resample, scan with both fitters, merge properties

---

## Next steps (priority order)

### 1. Verify RcFitter overlay visually
The 1R1C overlay is computed from stored params + outdoor/solar series (not
from `_curve_fn`). Check visually that it aligns with the observed indoor
temperature. If there is drift, suspect the initial condition (`T_0` fallback
in `_rc_sim_segment`) or the resampling step.

### 2. (τ, T∞) scatter — identify the two regimes
The bedroom data shows a clear bimodal τ distribution (≈4h and ≈10h
clusters). Add a **regime split** to the scatter plots:
- Add a "τ threshold" slider to `_render_decay_scan`.
- Color the decay overlay segments by regime (fast = orange, slow = blue)
  instead of a single colour.
- This visually identifies which nights had the window open without any
  reed switch.

### 3. Segment-level solar regression
The `T∞ − T_out` vs solar plot shows a negative slope in winter (collinearity:
sunny days → higher T_out → smaller gap). Fix this with a **2D regression**
across segments:

```python
# Regress T_inf on (1, T_out_mean, I_solar_mean) per segment
# Then plot the partial residual: (T_inf - b0 - b1*T_out) vs I_solar
```

This recovers the solar gain coefficient free of the T_out correlation.
Add this as a third scatter plot (or replace the current one).

### 4. 2R2C fitter
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

### 5. Backward-compat: deprecate `sliding_exp.py`
The inspector no longer uses `sliding_exp.py` for scan/merge (it now goes
through `sliding/scan.py`), but still imports `WindowFit` and the old
functions. Once the visual overlay is confirmed working, the old imports can
be dropped and `sliding_exp.py` reduced to a thin shim or removed.

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
