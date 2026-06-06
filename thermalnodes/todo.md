# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: graph editor + solver + FastAPI backend + ZOH solver + study persistence + UI layout refactor (step 5c) + UI polish done. Stale-result tracking (5d) next.

---

## Key file map

```
thermalnodes/
  schema/                        JSON schemas (v0.3)
  data/
    house.json                   house metadata + sensor defaults
    materials/                   7 materials (λ, ρ, cp)
    examples/                    read-only seed studies
      chambre_1r1c.json
      chambre_v1.json
      chambre_2r2c.json
    user/
      studies/                   {id}.json per user study (created at runtime)
  solver/
    assemble.py                  graph → AssembledSystem (done)
    simulate.py                  simulate_ivp + simulate_zoh + simulate_mock (done)
    inputs.py                    stub inputs generator (optional)
    tests/
      test_assemble.py           assembly unit tests (passing)
      test_simulate.py           IVP + ZOH unit tests (passing)
  api/
    config.py                    env-based config (MINIHA_INFLUX_* vars)
    influx.py                    InfluxDB client + parse_signal + list_signals + fetch_series
    main.py                      FastAPI app — all routes (see Step 4)
  ui/
    src/
      routes/+page.svelte        app shell — home view + left nav (Home + study tabs + Save)
      lib/GraphView.svelte       SvelteFlow canvas
      lib/PropertiesPanel.svelte node/edge inspector + add/delete; signal autocomplete
      lib/InputsPanel.svelte     date range + solver + signal assignment + inline uPlot preview
      lib/SimulationRun.svelte   fetch/run buttons + results charts (no config sidebar)
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

**Simulation is split into three stages** (each independently testable):

1. **`prepare_inputs(sim_config, influx_client) -> dict[str, (t, values)]`** —
   fetches each signal from InfluxDB, resamples to a uniform grid. Slow, I/O-bound.
   Exposed via `POST /simulate/inputs` so the UI can show input signals before solving.
2. **`assemble(model) -> AssembledSystem`** — already in `assemble.py`.
3. **`simulate_ivp(system, inputs, t_eval) -> SimResult`** — pure numerics, no I/O.

**Real solver** (implement after UI is working):

- [x] `simulate_ivp(system, inputs, start, end, y0=None) -> SimResult`
  - `inputs`: `dict[str, tuple[np.ndarray, np.ndarray]]` — `{node_id: (t_sec, values)}`
    mapped to matrix columns via `system.boundary_ids` / `system.source_ids`.
  - Builds `u(t)` by ZOH-interpolating each signal via `scipy.interpolate.interp1d`.
  - Calls `solve_ivp(fun, t_span, y0, method='BDF', t_eval=t_eval)`.
  - `y0` defaults to first boundary value (warm start); can be overridden.
  - `SimResult` carries solver metadata: `solver`, `elapsed_s`, `n_steps`, `n_rhs_evals`,
    `success`, `message`.
- [x] **Verify** (unit test): `chambre_1r1c.json`, step T_ext 0→10 °C, zero solar,
      IVP matches `T(t) = 10·(1 − exp(−t/τ))` to < 0.01 °C at t=τ. ✓
- [x] **Verify** (unit test): `chambre_v1.json`, T_ext=0, zero solar, T0=20 °C,
      IVP → T < 0.5 °C after 5τ_slow; metadata fields present. ✓
- [x] `simulate_zoh(system, inputs, start, end, dt_minutes) -> SimResult`
  - Use `scipy.signal.cont2discrete((A, B_full, I, 0), dt, method='zoh')` to get `Ad`, `Bd`.
    `B_full` = `[B_boundary | B_source]` concatenated column-wise.
  - Use `scipy.signal.dlsim((Ad, Bd, I, 0, dt), u, x0=y0)` for the time-stepping loop.
    `u` = input matrix, shape `(n_steps, n_boundary + n_source)`, assembled from `inputs` dict.
  - Returns same `SimResult` format (`solver='zoh'`).
- [x] **Verify** ZOH against IVP: same step-response test, both agree to < 0.01 °C. ✓

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
- [x] `POST /simulate` — mock endpoint (kept for offline use)
- [x] CORS for Svelte dev server (localhost:5173 and :4173)
- [x] `POST /simulate/inputs` — fetch + resample all signals in config; returns
      `{node_id: {signal, t, values}}` for UI preview before running the solver
- [x] `POST /simulate/run` — fetches inputs from InfluxDB, calls `simulate_ivp`;
      returns `{t, nodes, meta}` where `meta` carries solver stats
      (elapsed_s, n_rhs_evals, success, message)
- [x] `POST /simulate/run` — `solver` field (`"ivp"` | `"zoh"`, default `"ivp"`)

### Also done (Step 5a)
- [x] `GET  /studies` — list all studies: examples + user, each `{id, label, room, source}`
- [x] `GET  /studies/{id}` — return full study JSON
- [x] `POST /studies/{id}` — save to `data/user/studies/{id}.json`
- [x] `POST /studies/{id}/duplicate` — copy to new id; body `{new_id}`
- [x] `GET  /house` — return `house.json`
- [x] `POST /house` — save `house.json`

### TODO
- [ ] `POST /fit/run` — accept `{ sim_config, fit_config }`, return fit results (see step 6)
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
- [x] "Run" button → `POST /simulate/run` with assembled config
- [x] uPlot: temperature timeseries per mass node (all masses on one shared chart)
- [x] "Fetch inputs" button → `POST /simulate/inputs`; plots resampled input signals
      (boundary temperatures, heat sources) above the simulation results chart
- [x] Solver selector: `ivp` (default) / `zoh` radio; passed as `solver` field to `POST /simulate/run`
- [x] Metadata display: show `meta` block from response (elapsed_s, n_steps, solver, message)
- [ ] (later) skip re-fetch if inputs unchanged — server-side cache, transparent to UI

### Backend-backed persistence — revised design

**Use case**: parameter estimation on a house, room by room. The atomic unit of work
is a **study**: one room, one model topology, one time range, one sensor selection,
one set of priors → one fit result / analysis report.

**Design principles:**
- Keep it as flat and simple as possible — single-user local tool, 4-5 rooms
- Topology is embedded in the study (not a shared reference) — you iterate on topology
  per study, trying 1R1C vs 2R1C on the same room/period
- Duplicate a study to make a small variation (different topology, different period,
  tighter priors)
- `house.json` is a defaults bag and future LLM input, not a runtime dependency

**File layout:**
```
thermalnodes/data/
  house.json               — house metadata + sensor defaults (UI pre-fill, LLM input)
  examples/                — read-only seed studies
  user/
    studies/               — {id}.json per study
```

**`house.json` schema:**
```json
{
  "label": "Maison Machin",
  "rooms": ["chambre", "salon", "cuisine", "bureau", "cave"],
  "defaults": {
    "inputs": {
      "exterior": "open_meteo/temperature_2m"
    },
    "solver": "zoh"
  }
}
```

**Study schema** (self-contained, fully resolved — no inheritance at runtime):
```json
{
  "id":           "chambre_jan_2024_2r1c",
  "label":        "Chambre — jan 2024 — modèle 2R1C",
  "room":         "chambre",
  "model":        { "...full topology..." },
  "start":        "2024-01-01",
  "end":          "2024-02-01",
  "inputs":       { "exterior": "open_meteo/temperature_2m" },
  "observations": { "chambre": "zigbee2mqtt/temperature?name=chambre" },
  "priors":       { "R_ext": { "nominal": 0.02, "sigma_log": 0.5 } },
  "solver":       "zoh",
  "result":       null
}
```

IDs are user-supplied filename stems. Saving with an existing ID overwrites.

#### Step 5a — Backend API

- [ ] `GET  /studies` — list all studies: examples + user, each `{id, label, room, source}`
- [ ] `GET  /studies/{id}` — return full study JSON
- [ ] `POST /studies/{id}` — save to `data/user/studies/{id}.json`, body = full study JSON
- [ ] `POST /studies/{id}/duplicate` — copy to new id; body `{new_id}`
- [ ] `GET  /house` — return `house.json`
- [ ] `POST /house` — save `house.json`

#### Step 5b — Wire UI: study picker replaces model picker — DONE

- [x] Drop `MODELS` static import (`models.js`); replace with `GET /studies` on mount
- [x] Study picker dropdown (shared in `+page.svelte`): label + room tag + source badge
- [x] Selecting a study restores graph topology + signals + dates + solver
- [x] "Save study" button: inline ID prompt, `POST /studies/{id}`; picker reloads
- [x] "Duplicate" button: prompts for new id, calls duplicate endpoint, loads copy
- [ ] Load `house.json` on mount; use `defaults` to pre-fill inputs on new studies

#### Step 5c — UI layout refactor — DONE

**Layout:**
```
┌──────────────┬──────────────────────────────────────────┐
│ miniha       │                                          │
│ Home         │  Home: card grid of all studies          │
│ ──────────── │  or active tab content                   │
│ study_id     │                                          │
│   Topology   │                                          │
│   Inputs     │                                          │
│   Run        │                                          │
│   Fit        │                                          │
│  [Save]      │                                          │
└──────────────┴──────────────────────────────────────────┘
```

- [x] **Home view** — card grid, two groups (examples/ + user/), ⎘ duplicate per card
- [x] **Topology** — GraphView + PropertiesPanel (internals unchanged)
- [x] **Inputs** — `InputsPanel.svelte`: date range + solver selector + signal assignment
      table with inline uPlot preview per row (▾ toggle). `DataExplorer.svelte` deleted.
- [x] **Run** — slimmed `SimulationRun.svelte`: action bar (Fetch + Run + solver badge)
      + results charts. No config sidebar — config lives in Inputs.
- [x] **Fit** — placeholder
- [x] No top bar — Save pinned at bottom of left nav (fixed, not pushed by flex spacer); study nav only shown when a study is loaded
- [x] Model notes moved to PropertiesPanel (shown when nothing is selected, above the hint)
- [x] Topology tab-header bar removed — full vertical space given to canvas

#### Step 5d — Stale-result tracking — TODO (pass 2, after layout)

When study inputs change after a run, results are silently outdated. Track this with
dirty flags and make it visible without blocking the user.

**Dependency rules:**

| Change | Invalidates |
|---|---|
| Signal assignment or date range | fetch result + sim result |
| Topology (R, C, add/remove node) | sim result only |
| Solver choice | sim result only |

**Implementation:**
- `studyDirty: { fetch: bool, sim: bool }` in `+page.svelte`
- `$effect` watchers on `simInputs`/`simRange` → set both flags; on `model`/`simSolver` → set sim flag only
- Pass flags as props to Run panel
- Run panel shows a `⚠ stale` banner over old results when dirty; run button shows `Re-run`
- On run: if `fetch` dirty → re-fetch first; if only `sim` dirty → skip re-fetch

#### Step 5e — Nice to have (post-MVP)

- [ ] Construction picker dropdown on edges (populates R from material library)
- [ ] Material library browser panel

---

### LLM-assisted model builder (future)

- User fills `house.json` with room descriptions and known materials
- LLM reads `house.json` + material library → generates an initial study JSON
  (topology + R/C estimates + suggested priors)
- User refines in the graph editor and saves as a study

`house.json` is the document you hand to the LLM; the study is what comes back.

---

## Step 6 — Parameter estimation (NLS + MCMC)

Lives in `thermalnodes/solver/fit.py` + `api/main.py`. ZOH (step 3b) is the critical
building block — implement it first.

### Fit config

Extends the sim config with two new fields:

```json
{
  "model": { "...": "..." },
  "start": "2024-01-01",
  "end":   "2024-02-01",
  "inputs": { "exterior": "open_meteo/temperature_2m", "...": "..." },
  "observations": {
    "chambre": "zigbee2mqtt/temperature?name=chambre"
  }
}
```

```json
{
  "params": {
    "R_ext":                   { "nominal": 0.0178, "sigma_log": 0.5 },
    "R_int":                   { "nominal": 0.0234, "sigma_log": 0.5 },
    "mur_sud.C":               { "nominal": 9504000, "sigma_log": 0.5 },
    "chambre.C":               { "nominal": 8640000, "sigma_log": 0.5 },
    "apport_fenetre_sud.gain": { "nominal": 1.2,     "sigma_log": 0.5 }
  },
  "obs_sigma": 0.5,
  "method": "nls"
}
```

- `observations`: mass node id → signal name (same format as `inputs`).
  Lives in the sim config, not the model — keeps topology reusable.
- `params`: node id (for R/C on resistance/mass nodes) or `node_id.field` (for gains).
  `sigma_log` = log-normal prior width (0.5 ≈ ±50% at 1σ). Params not listed are fixed.
- `obs_sigma`: observation noise [°C], assumed Gaussian.
- `method`: `"nls"` or `"mcmc"`.

### Python (`solver/fit.py`)

- [ ] `build_forward(sim_config, fit_config, influx_client) -> Callable[[params_vec], T_pred]`
  - Fetches inputs + observations once (slow I/O step).
  - Returns a pure function `params_vec → predicted temperatures array` using ZOH.
  - Params encoded in log-space; function patches the model dict, re-assembles, re-discretises.
- [ ] `fit_nls(forward_fn, fit_config) -> FitResult`
  - `scipy.optimize.least_squares` in log-space; residuals = `(T_pred − T_obs) / obs_sigma`.
  - Warm-start from nominal values. Returns best-fit params + cost + covariance estimate.
- [ ] `fit_mcmc(forward_fn, fit_config, n_samples=2000) -> MCMCResult`
  - Log-posterior = Gaussian log-likelihood + log-normal log-prior per param.
  - Use `emcee` (no JAX dependency). Warm-start walkers around NLS result.
  - Returns `{ params_mean, params_std, samples (thinned), acceptance_rate }`.

### API (`api/main.py`)

- [ ] `POST /fit/run` — accepts `{ sim_config, fit_config }`, calls `build_forward` then
      `fit_nls` or `fit_mcmc` based on `fit_config.method`.
      Returns Pydantic `FitResult` (OpenAPI docs auto-generated).

### UI — Parameter fit tab (new tab)

- [ ] New "Fit" tab in the left nav (after "Simulate")
- [ ] Sim config section: reuse model picker + date range + inputs table
- [ ] Observations table: one row per mass node, signal autocomplete
- [ ] Params table: one row per free parameter — node id, nominal value, sigma_log;
      pre-populated from model node values, editable
- [ ] `obs_sigma` field + method selector (`nls` / `mcmc`)
- [ ] "Run fit" button → `POST /fit/run`
- [ ] Results panel:
  - NLS: table of fitted vs nominal param values + % change; residual plot (T_pred vs T_obs)
  - MCMC: same table with ± uncertainty; marginal histograms per param (or corner plot)

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
- **Fitting / Bayesian**: Step 6. ZOH is the prerequisite (fast enough for MCMC).
- **Observations**: live in sim config alongside `inputs`, not in model topology.
- **Fit config**: separate object `{ params, obs_sigma, method }`. Params keyed by node id
  or `node_id.field`; log-normal priors. NLS first, MCMC warm-started from NLS result.
- **ZOH implementation**: via `scipy.signal.cont2discrete(..., method='zoh')` +
  `scipy.signal.dlsim` — no custom matrix exponential needed.
- **Streamlit app** (`miniha/th_models/inspector.py`): prototype, reference only.
  Svelte UI (`thermalnodes/ui/`) is the target frontend.
