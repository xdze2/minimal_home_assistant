# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: schema + data library + Svelte graph editor done; solver assembly done

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
    simulate.py                  IVP + ZOH (TODO step 3b)
    inputs.py                    stub inputs generator (TODO step 3c, optional)
    tests/
      test_assemble.py           assembly unit tests (passing)
  api/
    config.py                    env-based config (MINIHA_INFLUX_* vars, same as miniha)
    influx.py                    InfluxDB client + parse_signal + list_signals + fetch_series
    main.py                      FastAPI app: GET /signals, GET /series
  ui/
    src/
      routes/+page.svelte        app shell — model picker, load/save JSON
      lib/GraphView.svelte       SvelteFlow canvas
      lib/PropertiesPanel.svelte node/edge inspector + add/delete; signal autocomplete
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

This string is stored verbatim in the model JSON:
- boundary node: `"T_source": "open_meteo/temperature_2m"`
- source node:   `"signal": "poa/irradiance?face=SE"`

The API parses it with `parse_signal()` in `api/influx.py`. All data is resampled to
15 min uniform grid.

**TODO**: standardise signal names across the three example files (currently inconsistent
— see step 3c).

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
    mass_ids: list[str]      # node ids in row/col order
    boundary_ids: list[str]
    source_ids: list[str]
```

**Gap:** `AssembledSystem` stores node *ids* but not the signal names from the schema
(`boundary.T_source`, `source.signal`). The IVP solver needs these to index into
`inputs`. Fix in step 3b: add `boundary_signals` and `source_signals` parallel lists
(see step 3b notes).

Verified: τ for `chambre_1r1c` matches R·C; eigenvalues for `chambre_v1` give
τ_fast ≈ 7 h, τ_slow ≈ 38 h (ratio > 5×).

### 3c — Stub inputs for demo (`solver/inputs.py`) — DO THIS FIRST

**Signal name convention** — settle this before writing the IVP solver.
Current examples are inconsistent:

| file             | boundary T_source             | source signal         |
|------------------|-------------------------------|-----------------------|
| chambre_1r1c     | `open_meteo/temperature_2m`   | `poa/window_south`    |
| chambre_2r2c     | `open_meteo/temperature_2m`   | `poa/window_south`    |
| chambre_v1       | `outdoor_temp`                | `poa/window_SE`, `poa/window_NE` |

Decision needed: standardise on `open_meteo/temperature_2m` (or a simpler name like
`T_ext`) across all examples before writing `make_stub_inputs`.
`make_stub_inputs` must produce keys that match the signal names in the examples.

- [ ] Decide and apply a consistent signal name scheme to all three example files.
- [ ] `make_stub_inputs(start, end, dt_minutes) -> dict[str, tuple[np.ndarray, np.ndarray]]`
  - Returns `{signal_name: (t_seconds_array, values_array)}`.
  - Synthesises plausible outdoor temperature (sinusoidal daily + seasonal offset)
    and solar irradiance (clear-sky flat-plate model).
  - Covers at least 2 months; no InfluxDB / Open-Meteo dependency.
  - Must cover all signal names referenced by `chambre_v1.json` and `chambre_1r1c.json`.
- [ ] **Verify**: print min/max/mean of each signal; check T_ext range ≈ 0–25 °C,
      solar ≥ 0 and peaks ≈ 600–900 W/m².

### 3b — Forward simulation (`solver/simulate.py`)

**Pre-requisite:** fix `AssembledSystem` to carry signal names:

```python
@dataclass
class AssembledSystem:
    ...
    boundary_signals: list[str]   # parallel to boundary_ids; values of node.T_source
    source_signals:   list[str]   # parallel to source_ids;   values of node.signal
```

Add extraction in `assemble()`:
```python
boundary_signals = [nodes[nid]["T_source"] for nid in boundary_ids]
source_signals   = [nodes[nid]["signal"]   for nid in source_ids]
```

**Integrator choice:**

- `scipy.integrate.solve_ivp(method='BDF')` — handles stiffness from the ~30× C
  ratio (mur_SE ≈ 8 MJ/K vs chambre ≈ 270 kJ/K). Good for exploration.
- **ZOH (matrix exponential)** — exact for piecewise-constant inputs on a uniform
  grid: `x[k+1] = Ad @ x[k] + Bd @ u[k]` where `Ad = expm(A·dt)`,
  `Bd = A⁻¹·(Ad − I)·B`. O(n³) once to precompute, O(n²) per step. Required for
  optimisation / MCMC (step 6). Reference impl: `miniha/th_models/fit_2r2c.py`.

Inputs format for both:
```python
# inputs dict keys = signal names (must match boundary_signals / source_signals)
inputs: dict[str, tuple[np.ndarray, np.ndarray]]  # (t_seconds, values)
```

- [ ] `simulate_ivp(system, inputs, t_eval) -> SimResult`
  - Builds `u(t)` by interpolating each signal via `scipy.interpolate.interp1d`.
  - Column order: `[boundary_signals..., source_signals...]` → `u` vector.
  - Calls `solve_ivp(fun, t_span, y0, method='BDF', t_eval=t_eval)`.
  - Returns `SimResult(t, temps)` where `temps: dict[mass_id, np.ndarray]`.
- [ ] `simulate_zoh(system, inputs_uniform, dt) -> SimResult`
  - `inputs_uniform`: same dict but values on a uniform grid of step `dt` seconds.
  - Precomputes `Ad = expm(A·dt)`, `Bd = inv(A) @ (Ad − I) @ B_full`.
  - Returns same `SimResult` format.
- [ ] **Verify** (unit test): `chambre_1r1c.json`, step T_ext 0→10 °C, zero solar,
      IVP and ZOH both match `T(t) = 10·(1 − exp(−t/τ))` to < 0.01 °C at t=τ.
- [ ] **Verify** (unit test): `chambre_v1.json`, T_ext=0, zero solar, T0=[20,20],
      both methods → T=0 with two exponential modes; τ values match eigenvalues of A.

---

## Step 4 — FastAPI backend (`api/main.py`)

Run: `uv run uvicorn thermalnodes.api.main:app --reload --port 8001`

The Svelte UI is blocked on this for real simulation and for saving models server-side.

### Done
- [x] `GET /signals` — lists all `measurement/field?tag=val` from InfluxDB
- [x] `GET /series?signal=...&start=...&end=` — fetch + resample to 15 min
- [x] CORS for Svelte dev server (localhost:5173 and :4173)

### TODO
- [ ] `POST /simulate` — body: `{model: {...}, start: str, end: str}`,
      fetches inputs from InfluxDB internally, runs `simulate_ivp`,
      returns `{t: [...], nodes: {mass_id: [...]}}`
- [ ] `POST /model/save` — persist model JSON to `data/user/` (separate from examples)
- [ ] `GET /model/list` — list available model files (examples + user)
- [ ] `GET /model/{id}` — return model JSON
- [ ] `GET /materials` — list available material ids + names

---

## Step 5 — Svelte UI (`ui/`)

Stack: SvelteKit + `@xyflow/svelte`.

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

### Simulation panel (blocked on step 4 backend)

- [ ] Install uPlot
- [ ] Date range picker (start / end)
- [ ] "Simulate" button → `POST /simulate`
- [ ] uPlot: temperature timeseries per mass node + outdoor temperature overlay

### Server-backed model persistence (blocked on step 4 backend)

- [ ] Replace bundled `MODELS` import with `GET /model/list` + `GET /model/{id}`
- [ ] "Save to server" button → `POST /model/save`
- [ ] Reload model list after save

### Nice to have (post-MVP)

- [ ] Construction picker dropdown on edges (populates R from material library)
- [ ] Material library browser panel
- [ ] Signal name autocomplete (from backend `/inputs/signals` list)

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
- **boundary node**: `T_source` field = signal name string (or a fixed float)
- **source node**: `signal` field = signal name string; `gain` = scalar multiplier
- **resistance nodes**: eliminated during assembly — not in state vector

## Decisions made

- **Solver**: two-track: `solve_ivp(BDF)` for correctness, ZOH for optimisation/MCMC.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
- **R and C**: direct numeric values only; compute from material properties externally.
- **Boundaries**: fixed-temperature forcing nodes (not solved).
- **Heat sources**: explicit edge source→mass in graph (dependency is structural, not metadata).
- **Thick walls / MVP**: 2R1C block (R_ext, mass, R_int). Already in `chambre_v1`.
- **Fitting / Bayesian**: Step 6. ZOH chosen from the start to support this.
- **Streamlit app** (`miniha/th_models/inspector.py`): prototype, reference only.
  Svelte UI (`thermalnodes/ui/`) is the target frontend.
