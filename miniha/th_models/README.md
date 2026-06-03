# th_models — current state

Grey-box thermal model of one room, fit from real sensor data. Plots
residuals, supports inspecting parameter behaviour over time.

Theory and modelling choices are documented separately in
[model_theory_1r1c.md](model_theory_1r1c.md).

## What's in place

- Project uses `uv` (existing `venv/` reused via `UV_PROJECT_ENVIRONMENT=venv`).
  `requires-python = ">=3.12"`.
- Code lives in [miniha/th_models/](.) as a normal subpackage.
- User configs (one YAML per room) live in [user_models/](../../user_models/).
- Streamlit + Plotly are deps.
- **Inspector** ([inspector.py](inspector.py)) is wired end-to-end: four tabs per
  room — Inspect, 1R1C model, 2R2C model, Decay scan.
- **1R1C Fitter** ([fit.py](fit.py)) implements the 1R1C + constant-gain + solar
  model via forward-Euler one-step OLS. Returns `(τ, ΔT_eq, g_solar)` — the
  three identifiable combinations. Solar shortwave radiation is pulled from
  Open-Meteo.
- **2R2C Fitter** ([fit_2r2c.py](fit_2r2c.py)) extends to a two-node model (air +
  wall/mass node) fitted via output-error nonlinear least squares (TRF,
  `scipy.optimize.least_squares`). Warm-started from the 1R1C OLS fit. Reports
  `(τ_fast, τ_slow, ΔT_eq, g_solar)`.
- **Daily view** ([daily.py](daily.py)) is a separate Streamlit app: one card per
  room in a 2-column grid, showing indoor/outdoor temperature and solar
  irradiance for a chosen day (±6h window, date picker in sidebar).
- **Sliding-window scan** identifies free-decay or 1R1C segments across the full
  time series. Two backends:
  - [sliding_exp.py](sliding_exp.py) — legacy standalone module (exponential
    free-decay only, used for reference/testing).
  - [sliding/](sliding/) — refactored model-agnostic engine:
    - [sliding/protocol.py](sliding/protocol.py) defines `WindowResult` and the
      `Fitter` protocol.
    - [sliding/scan.py](sliding/scan.py) — generic `scan()` + greedy-grow
      `merge_grow()`, model-agnostic.
    - [sliding/exp_fitter.py](sliding/exp_fitter.py) — `ExpFitter`: free-decay
      exponential behind the `Fitter` protocol.
    - [sliding/rc_fitter.py](sliding/rc_fitter.py) — `RcFitter`: 1R1C windowed
      fit with penalised OLS (Gaussian priors on τ, ΔT_eq, g_solar).

## Layout

```
miniha/
  th_models/
    __init__.py
    config.py             # YAML → dataclasses (RoomConfig, SeriesSpec, Segment)
    load.py               # config → dict[role, pd.Series] (UTC index)
    flags.py              # find_gaps(): consecutive samples > 1h apart
    fit.py                # 1R1C + G(t) one-step OLS fit + simulate()
    fit_2r2c.py           # 2R2C output-error NLS fit + simulate_2r2c()
    daily.py              # Streamlit daily-view app (2-column card grid)
    inspector.py          # Streamlit inspector app (4 tabs)
    sliding_exp.py        # legacy standalone sliding exponential scan
    sliding/
      __init__.py
      protocol.py         # WindowResult dataclass + Fitter protocol
      scan.py             # generic scan() + merge_grow() + to_dataframe()
      exp_fitter.py       # ExpFitter (free-decay)
      rc_fitter.py        # RcFitter (1R1C with priors)
    model_theory_1r1c.md  # theory, identifiability, residual diagnostics
    README.md             # this file
user_models/
  chambre.yaml            # user data, one file per room
```

## Run the inspector

```
UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
```

Sidebar lists every YAML found in `user_models/` (read-only — no file picker).
The main area shows four tabs per config:

- **Inspect** — one Plotly chart per series role, gap shading, per-role stats table.
- **1R1C model** — prepares data on a 15-min grid, runs OLS fit, shows metrics and
  residuals.
- **2R2C model** — same data, output-error NLS fit, shows `τ_fast`/`τ_slow` plus
  the latent wall temperature trajectory.
- **Decay scan** — sliding-window scan; choose fitter (Exp or 1R1C), window
  length, step, quality threshold, τ range, and optional greedy-grow merge.
  Plots accepted segments overlaid on the indoor series, τ-vs-time scatter,
  τ histogram, and (for Exp mode) τ–T∞ scatter and T∞–solar plot.

## Run the daily view

```
UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/daily.py
```

Date picker in the sidebar; one card per YAML in `user_models/`, 2 per row.
Each card shows indoor + outdoor temperature (top panel) and solar irradiance
(bottom panel) for a ±6h window around the selected day.

## Design choices in force

- **No data correction in the inspector.** No forward-fill, no resampling,
  no clipping. Just plot what InfluxDB returned.
- **Gap rule = 1 hour.** Any interval > 1h between consecutive samples is
  shaded red.
- **Stuck-value detection dropped.** Sonoff legitimately repeats values when
  the room is stable.
- **InfluxDB connection** comes from `miniha.config.config` (loaded from
  `.env` at the repo root, see `.env.example`).
- **Time grid**: indices are converted to UTC at load time. No resampling.
- **1R1C fit method**: forward-Euler one-step OLS — closed form, deterministic.
  Pros/cons in the theory doc.
- **2R2C fit method**: output-error NLS (ZOH integration + TRF optimiser).
  Log-parameterised for positivity; warm-started from 1R1C. `T_wall(0)`
  co-fitted; `T_in(0)` pinned to observation.
- **Identifiable parameters only**: we report `τ`, `ΔT_eq`, `g_solar` (and
  `τ_fast`/`τ_slow` for 2R2C), not `R`, `C`, `Q_0`, `a` separately —
  those share an unobservable scale.
- **Sliding scan quality metric**: `ExpFitter` uses R² (higher = better);
  `RcFitter` uses −RMSE (higher = better). Both stored as `quality` in
  `WindowResult` so the generic scan/merge machinery is model-agnostic.
- **Priors in RcFitter**: penalised OLS (ridge with non-zero target). Prior
  strength is normalised by window length so it is independent of window size.

## Data sources (verified from the codebase)

- Indoor temp: `sonoff_thermometer`, tag `name=sensors/thE`, field
  `temperature`. (chambre is `thE` per `config/sensors.yaml`.)
- Outdoor temp: `open_meteo_historic`, tag `location=home`, field
  `temperature_2m`. Written daily by `miniha/open_meteo_feed.py`.
- Solar: Open-Meteo `shortwave_radiation`.
- Also available for later: Daikin `outside_temperature`, `cloud_cover`,
  `rain`, `wind_speed_10m`, `relative_humidity_2m`.

## Config schema

See [user_models/chambre.yaml](../../user_models/chambre.yaml). Each role
under `series:` is a list of segments; each segment points at one
`(measurement, tags, field)` with optional `from`/`to` (left-closed,
right-open). Sensor swaps → append a segment with a `from:` date.

## Stuff worth glancing at

- [user_models/chambre.yaml](../../user_models/chambre.yaml) — config schema in use.
- [miniha/open_meteo_feed.py](../open_meteo_feed.py) — meteo writer,
  shows the influx schema and connection details.
- [miniha/webapp.py](../webapp.py) — existing influx query patterns.
- [miniha/influx_interface.py](../influx_interface.py) — the client
  wrapper used by `load.py`.
