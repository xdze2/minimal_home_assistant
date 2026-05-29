# th_models — POC handoff

Grey-box thermal model POC: fit a simple RC model of one room from real
sensor data, plot residuals, look at parameter behaviour over time.

## Where we are

- Project uses `uv` (existing `venv/` reused via `UV_PROJECT_ENVIRONMENT=venv`).
  `requires-python = ">=3.12"`.
- Code lives in [miniha/th_models/](miniha/th_models/) as a normal subpackage.
- User configs (one YAML per room) live in [user_models/](user_models/).
- Streamlit + Plotly are added as deps.
- Inspector is wired end-to-end: reads every YAML in `user_models/`, queries
  InfluxDB through `miniha.influx_interface`, plots each role, shades >1h
  gaps in red, no value correction.

## Layout

```
miniha/
  th_models/
    __init__.py
    config.py         # YAML → dataclasses (RoomConfig, SeriesSpec, Segment)
    load.py           # config → dict[role, pd.Series] (UTC index)
    flags.py          # find_gaps(): consecutive samples > 1h apart
    inspector.py      # Streamlit entry point
    NEXT.md           # this file
user_models/
  chambre.yaml        # user data, one file per room
```

## Run the inspector

```
UV_PROJECT_ENVIRONMENT=venv uv run streamlit run miniha/th_models/inspector.py
```

Sidebar lists every YAML found in `user_models/` (read-only — no file
picker). The main area renders one section per config, with one Plotly
chart per series role and a small per-role table (n, NaN, min/max, gap count).

## Design notes (decided)

- **No data correction in the inspector.** No forward-fill, no resampling,
  no clipping. Just plot what InfluxDB returned.
- **Gap rule = 1 hour.** Any interval > 1h between consecutive samples is
  shaded red. (Open-Meteo writes hourly, so its "normal" cadence sits right
  at the edge — expect lots of tight reds on outdoor unless we relax the
  threshold to `> 1h + ε`. Adjust in [flags.py](miniha/th_models/flags.py) if noisy.)
- **Stuck-value detection dropped.** Sonoff legitimately repeats values when
  the room is stable.
- **InfluxDB connection** comes from `miniha.config.config` (loaded from
  `.env` at the repo root, see `.env.example`).
- **Time grid**: indices are converted to UTC at load time. No resampling.

## Data sources (verified from the codebase)

- Indoor temp: `sonoff_thermometer`, tag `name=sensors/thE`, field
  `temperature`. (chambre is `thE` per `config/sensors.yaml`.)
- Outdoor temp: `open_meteo_historic`, tag `location=home`, field
  `temperature_2m`. Written daily by `miniha/open_meteo_feed.py`.
- Also available for later: Daikin `outside_temperature`, Open-Meteo
  `shortwave_radiation`, `cloud_cover`, `rain`, `wind_speed_10m`,
  `relative_humidity_2m`.

## Config schema

See [user_models/chambre.yaml](user_models/chambre.yaml). Each role under
`series:` is a list of segments; each segment points at one
`(measurement, tags, field)` with optional `from`/`to` (left-closed,
right-open). Sensor swaps → append a segment with a `from:` date.

## After the inspector

1. **1R1C baseline fit** on quiet night windows (gains ≈ 0).
   Linear regression on the discretised ODE `C dT/dt = (T_out - T_in) / R`.
   Returns R, C; uncertainty from residual covariance.
2. **Residual plot**: `model(t) - observed(t)`. This is the headline.
   Daytime positive bumps → solar gain. Sharp drops → window open. Etc.
3. **Sliding-window fit**: re-fit on each week separately. Plot R(t), C(t).
   This is where "dynamic parameters" (window/curtain/occupancy) start
   to show up as visible drift.
4. **Add solar term**: `C dT/dt = (T_out - T_in)/R + a · I_solar`. Pulls
   the daytime bump out of the residual. Effective aperture × shading
   coefficient.

When wiring the fitter:
- Add manual exclusions in YAML (vacations, window-open events) — kept on
  the plot but dropped from the fit. Suggested top-level key:
  ```yaml
  exclude:
    - { reason: vacation, start: ..., end: ... }
  ```
- Decide on a common time grid (likely 15 min) and how to align hourly
  outdoor with sub-hourly indoor. Forward-filling an hourly signal
  inflates effective sample count — be careful with residual stats.

## Open TODOs

- Confirm Sonoff pipeline writes UTC (Open-Meteo does).
- Acceptance criterion for "inspector done": all configured series render
  for the default window, gap shading looks sensible, table coverage > 95%
  for indoor / > 99% for outdoor.

## Stuff worth glancing at

- [user_models/chambre.yaml](user_models/chambre.yaml) — config schema in use.
- [miniha/open_meteo_feed.py](miniha/open_meteo_feed.py) — meteo writer,
  shows the influx schema and connection details.
- [miniha/webapp.py](miniha/webapp.py) — existing influx query patterns.
- [miniha/influx_interface.py](miniha/influx_interface.py) — the client
  wrapper used by `load.py`.
