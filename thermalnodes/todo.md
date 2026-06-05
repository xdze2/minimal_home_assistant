# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: graph editor + solver assembly + FastAPI backend (mock) + data exploration UI + simulation run tab done

---

## Key file map

```
thermalnodes/
  schema/                        JSON schemas (v0.3)
  data/
    materials/                   7 materials (λ, ρ, cp)
    examples/
      chambre_1r1c.json          1 mass, 1 resistance, 1 boundary, 1 source
      chambre_v1.json            2 mass, 5 resistance, 1 boundary, 2 source
      chambre_2r2c.json          2 mass, 5 resistance, 1 boundary, 1 source
  solver/
    assemble.py                  graph → AssembledSystem (done)
    simulate.py                  SimResult + simulate_mock() (done); IVP + ZOH TODO
    inputs.py                    stub inputs generator (TODO step 3c, optional)
    tests/
      test_assemble.py           assembly unit tests (passing)
  api/
    config.py                    env-based config (MINIHA_INFLUX_* vars, same as miniha)
    influx.py                    InfluxDB client + parse_signal + list_signals + fetch_series
    main.py                      FastAPI app: GET /signals, GET /series, POST /simulate (mock)
  ui/
    src/
      routes/+page.svelte        app shell — left nav, page switcher
      lib/GraphView.svelte       SvelteFlow canvas
      lib/PropertiesPanel.svelte node/edge inspector + add/delete; signal autocomplete
      lib/DataExplorer.svelte    data exploration tab (signal list + uPlot preview)
      lib/modelToFlow.js         model JSON → SvelteFlow nodes/edges
    vite.config.js               @data alias → thermalnodes/data/

miniha/
  th_models/
    load.py                      InfluxDB loader (production, uses RoomConfig YAML)
    inspector.py                 Streamlit prototype (reference only)
    fit_2r2c.py                  ZOH + matrix-exp solver (reference impl for step 3b)
```

---

## Step 1 — Examples (done)

- [x] `chambre_1r1c.json` — 1 mass, 1 R→exterior boundary, 1 solar source
- [x] `chambre_v1.json`   — 2 mass (chambre + mur_SE), 5 R, 1 boundary, 2 solar sources
- [x] `chambre_2r2c.json` — 2 mass (chambre + mur), 5 R, 1 boundary, 1 solar source

---

## Step 2 — Material library (done)

- [x] `data/materials/` — 7 materials (stone_calcaire, brick_full, concrete_heavy,
      wood_frame, plaster, air_gap, glass_wool)

---

## Signal name convention

All inputs come from InfluxDB. Format: `measurement/field?tag_key=tag_value[&tag2=val2]`

Examples:
```
open_meteo/temperature_2m          # no tags
zigbee2mqtt/temperature?name=salon # with tag filter
poa/irradiance?face=SE
```

Signal names are **no longer stored in the model JSON**. They live in the simulation
config (`inputs: { node_id → signal_name }`), keeping model topology decoupled from
data sources. The existing example files still carry `T_source` / `signal` fields as
hints, but the solver and API ignore them.

**TODO**: clean up example files to remove or document the legacy `T_source` / `signal`
fields once the sim-config UI is in place.

---

## Step 3 — Python solver

Use `uv` for all Python package management:

```bash
uv add scipy numpy pytest
uv run pytest thermalnodes/solver/tests/
```

### 3a — Graph → state-space assembly (`solver/assemble.py`) — DONE

`assemble(model) -> AssembledSystem` where:

```python
@dataclass
class AssembledSystem:
    A: np.ndarray           # [n_mass × n_mass]   continuous-time
    B_boundary: np.ndarray  # [n_mass × n_boundary]
    B_source: np.ndarray    # [n_mass × n_source]
    mass_ids: list[str]
    boundary_ids: list[str]
    source_ids: list[str]
```

Verified: τ for `chambre_1r1c` matches R·C; eigenvalues for `chambre_v1` give
τ_fast ≈ 7 h, τ_slow ≈ 38 h (ratio > 5×).

### 3b — Forward simulation (`solver/simulate.py`) — mock done; real solver TODO

`SimResult` and `simulate_mock()` are implemented. Mock returns sinusoidal
temperatures (daily ±3 °C + slow 10-day drift, per-mass phase offset) without
using the model matrices — sufficient to develop and test the UI end-to-end.

**Real solver** (implement after UI is working):

- [ ] `simulate_ivp(system, inputs, t_eval) -> SimResult`
  - `inputs`: `dict[str, tuple[np.ndarray, np.ndarray]]` — `{signal_name: (t_sec, values)}`
    where keys match `inputs` from the sim config, mapped to node order via
    `system.boundary_ids` / `system.source_ids`.
  - Builds `u(t)` by interpolating each signal via `scipy.interpolate.interp1d`.
  - Calls `solve_ivp(fun, t_span, y0, method='BDF', t_eval=t_eval)`.
  - Returns `SimResult(t, temps)` where `temps: dict[mass_id, np.ndarray]`.
- [ ] `simulate_zoh(system, inputs_uniform, dt) -> SimResult`
  - `inputs_uniform`: same dict but values on a uniform grid of step `dt` seconds.
  - Precomputes `Ad = expm(A·dt)`, `Bd = inv(A) @ (Ad − I) @ B_full`.
  - Returns same `SimResult` format. Reference: `miniha/th_models/fit_2r2c.py`.
- [ ] **Verify** (unit test): `chambre_1r1c.json`, step T_ext 0→10 °C, zero solar,
      IVP and ZOH both match `T(t) = 10·(1 − exp(−t/τ))` to < 0.01 °C at t=τ.
- [ ] **Verify** (unit test): `chambre_v1.json`, T_ext=0, zero solar, T0=[20,20],
      both methods → T=0 with two exponential modes; τ values match eigenvalues of A.

**Integrator choice:**

- `scipy.integrate.solve_ivp(method='BDF')` — handles stiffness from the ~30× C
  ratio (mur_SE ≈ 8 MJ/K vs chambre ≈ 270 kJ/K). Good for exploration.
- **ZOH (matrix exponential)** — exact for piecewise-constant inputs on a uniform
  grid: `x[k+1] = Ad @ x[k] + Bd @ u[k]`. O(n³) once to precompute, O(n²) per step.
  Required for optimisation / MCMC (step 6).

### 3c — Stub inputs for offline demo (`solver/inputs.py`) — optional

May not be needed now that the UI uses a sim-config with explicit signal→InfluxDB
mapping. Keep as a fallback for unit tests or offline runs.

---

## Step 4 — FastAPI backend (`api/main.py`)

Run: `uv run uvicorn thermalnodes.api.main:app --reload --port 8001`

### Done
- [x] `GET /signals` — lists all `measurement/field?tag=val` from InfluxDB
- [x] `GET /series?signal=...&start=...&end=` — fetch + resample to 15 min
- [x] `POST /simulate` — body: `{model, start, end, inputs: {node_id → signal}}`,
      currently runs `simulate_mock`; swap for `simulate_ivp` once real solver is done
- [x] CORS for Svelte dev server (localhost:5173 and :4173)

### TODO
- [ ] Wire `POST /simulate` to InfluxDB: fetch each signal in `inputs`, pass to real solver
- [ ] `POST /model/save` — persist model JSON to `data/user/` (separate from examples)
- [ ] `GET /model/list` — list available model files (examples + user)
- [ ] `GET /model/{id}` — return model JSON
- [ ] `GET /materials` — list available material ids + names

---

## Step 5 — Svelte UI (`ui/`)

Stack: SvelteKit + `@xyflow/svelte` + uPlot.

### Graph editor (done)

- [x] Scaffold SvelteKit, install `@xyflow/svelte`
- [x] Node types: mass (Room), boundary, source, resistance — custom Svelte components
- [x] Resistance edges + animated heat-flow arrows
- [x] `modelToFlow.js` — model JSON → SvelteFlow nodes/edges
- [x] Model picker (dropdown), load JSON from file, save JSON to file
- [x] Properties panel: edit label, R, C, T_source, signal, gain; delete node/edge
- [x] Add node from palette (mass, boundary, source, resistance)
- [x] Draw edge by dragging between handles; delete with Delete/Backspace
- [x] Signal name autocomplete on boundary/source inputs (via `GET /signals`; shows ⚠ if API unreachable)

### Data exploration tab (done)

- [x] Signal list panel from `GET /signals`, filterable
- [x] uPlot time-series preview for selected signal via `GET /series`
- [x] Date range pickers (default: last 7 days)
- [x] Metadata row: date range, sample count, gap count, min/max/mean

### Simulation run tab (done)

The sim config decouples model topology from data sources:

```json
{
  "model": { "...": "..." },
  "start": "2024-01-01",
  "end":   "2024-02-01",
  "inputs": {
    "exterior":            "open_meteo/temperature_2m",
    "apport_fenetre_sud":  "poa/window_south"
  }
}
```

- [x] Model picker (reuse existing dropdown)
- [x] Date range pickers (start / end)
- [x] Inputs table: one row per boundary/source node in the selected model,
      signal autocomplete on each row (reuse signal list from data exploration)
- [x] "Run" button → `POST /simulate` with assembled config
- [x] uPlot: temperature timeseries per mass node (all masses on one shared chart)

### Sim-config save / load (next)

Allow saving and reloading a full simulation config (`model + start/end + inputs`) so
runs can be reproduced without re-entering signal names each time.

- [ ] "Save config" button in the simulation run tab → downloads a JSON file
      `{ model_id, start, end, inputs }` (store model by id, not inline, to keep it compact)
- [ ] "Load config" file picker → restores model selection, date range, and inputs map
- [ ] (later) server-side persistence via `POST /simconfig/save` + `GET /simconfig/list`

### Server-backed model persistence (after simulation tab)

- [ ] Replace bundled `MODELS` import with `GET /model/list` + `GET /model/{id}`
- [ ] "Save to server" button → `POST /model/save`
- [ ] Reload model list after save

### Nice to have (post-MVP)

- [ ] Construction picker dropdown on edges (populates R from material library)
- [ ] Material library browser panel

---

## Step 6 — Parameter optimisation and Bayesian MCMC (parent project)

Lives in `miniha/`, consumes `thermalnodes` models as topology. ZOH (step 3b) is
the critical building block.

- [ ] Wrap `simulate_zoh` as `f(params) -> T_chambre_array` for fixed topology;
      params = log-space {R values, C values, gain values}.
- [ ] `scipy.optimize.least_squares` output-error NLS; warm-start from nominal values.
- [ ] MCMC: `blackjax` or `emcee` on the same log-likelihood.
      Prior: log-normal ±50% of nominal on each R and C, flat on gains.

---

## Schema

- **material**: bulk physical constants (λ, ρ, cp) — reference only, not loaded by solver
- **model**: R [K/W] and C [J/K] are direct numeric values
- **boundary node**: `T_source` field — legacy hint only; solver uses sim-config `inputs`
- **source node**: `signal` field — legacy hint only; solver uses sim-config `inputs`
- **resistance nodes**: eliminated during assembly — not in state vector

## Decisions made

- **Solver**: two-track: `solve_ivp(BDF)` for correctness, ZOH for optimisation/MCMC.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
- **R and C**: direct numeric values only; compute from material properties externally.
- **Boundaries**: fixed-temperature forcing nodes (not solved).
- **Heat sources**: explicit edge source→mass in graph (dependency is structural, not metadata).
- **Thick walls / MVP**: 2R1C block (R_ext, mass, R_int). Already in `chambre_v1`.
- **Sim config**: signal→node binding lives in a separate sim config object, not in the
  model JSON. Keeps topology reusable across different datasets and time ranges.
- **Fitting / Bayesian**: Step 6. ZOH chosen from the start to support this.
- **Streamlit app** (`miniha/th_models/inspector.py`): prototype, reference only.
  Svelte UI (`thermalnodes/ui/`) is the target frontend.
