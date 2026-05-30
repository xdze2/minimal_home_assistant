# th_models — current state

Grey-box thermal model of one room, fit from real sensor data. Plots
residuals, supports inspecting parameter behaviour over time.

Theory and modelling choices are documented separately in
[model_theory_1r1c.md](model_theory_1r1c.md). Directions for future work
live in [NEXT.md](NEXT.md).

## What's in place

- Project uses `uv` (existing `venv/` reused via `UV_PROJECT_ENVIRONMENT=venv`).
  `requires-python = ">=3.12"`.
- Code lives in [miniha/th_models/](.) as a normal subpackage.
- User configs (one YAML per room) live in [user_models/](../../user_models/).
- Streamlit + Plotly are deps.
- **Inspector** is wired end-to-end: reads every YAML in `user_models/`,
  queries InfluxDB through `miniha.influx_interface`, plots each role,
  shades >1h gaps in red, does no value correction.
- **Fitter** ([fit.py](fit.py)) implements the 1R1C + constant-gain + solar
  model via forward-Euler one-step OLS. Returns
  `(τ, ΔT_eq, g_solar)` — the three identifiable combinations described in
  §5 of the theory doc. Solar shortwave radiation is pulled from
  Open-Meteo.

## Layout

```
miniha/
  th_models/
    __init__.py
    config.py             # YAML → dataclasses (RoomConfig, SeriesSpec, Segment)
    load.py               # config → dict[role, pd.Series] (UTC index)
    flags.py              # find_gaps(): consecutive samples > 1h apart
    fit.py                # 1R1C + G(t) one-step OLS fit
    inspector.py          # Streamlit entry point
    model_theory_1r1c.md  # theory, identifiability, residual diagnostics
    README.md             # this file
    NEXT.md               # ideas and directions for what to do next
user_models/
  chambre.yaml            # user data, one file per room
```

## Run the inspector

```
UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
```

Sidebar lists every YAML found in `user_models/` (read-only — no file
picker). The main area renders one section per config, with one Plotly
chart per series role and a small per-role table (n, NaN, min/max, gap count).

## Design choices in force

- **No data correction in the inspector.** No forward-fill, no resampling,
  no clipping. Just plot what InfluxDB returned.
- **Gap rule = 1 hour.** Any interval > 1h between consecutive samples is
  shaded red. (Open-Meteo writes hourly, so its "normal" cadence sits right
  at the edge — expect lots of tight reds on outdoor unless we relax the
  threshold to `> 1h + ε`. Adjust in [flags.py](flags.py) if noisy.)
- **Stuck-value detection dropped.** Sonoff legitimately repeats values when
  the room is stable.
- **InfluxDB connection** comes from `miniha.config.config` (loaded from
  `.env` at the repo root, see `.env.example`).
- **Time grid**: indices are converted to UTC at load time. No resampling.
- **Fit method**: forward-Euler one-step OLS — closed form, deterministic.
  Pros/cons spelled out in §4.2 of the theory doc.
- **Identifiable parameters only**: we report `τ`, `ΔT_eq`, `g_solar`, not
  `R`, `C`, `Q_0`, `a` separately (§5 of the theory doc).

## Data sources (verified from the codebase)

- Indoor temp: `sonoff_thermometer`, tag `name=sensors/thE`, field
  `temperature`. (chambre is `thE` per `config/sensors.yaml`.)
- Outdoor temp: `open_meteo_historic`, tag `location=home`, field
  `temperature_2m`. Written daily by `miniha/open_meteo_feed.py`.
- Solar: Open-Meteo `shortwave_radiation`.
- Also available for later: Daikin `outside_temperature`,
  `cloud_cover`, `rain`, `wind_speed_10m`, `relative_humidity_2m`.

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
