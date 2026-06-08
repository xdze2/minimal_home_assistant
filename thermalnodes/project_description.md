# thermalnodes — project description

Current state of the sub-project. Updated when architecture changes, not per-task.
For open work see [todo.md](todo.md). For setup see [README.md](README.md).

---

## What it does

Model a house room-by-room as a thermal RC network, simulate it against sensor
data from InfluxDB, and fit model parameters to identify unknown thermal properties
of an existing (often old, geometrically complex) building.

The atomic unit of work is a **study**: one room, one model topology, one time
range, one sensor selection, one set of priors → one fit result.

## Architecture

### Two-layer model

```
[house description]  →  physics layer  →  RC graph  →  assembler  →  ODE
 material, area, λ       expand walls       R, C, edges    A, B matrices
```

The current implementation works at the **RC mathematical level** (R, C numeric
values directly in the model JSON). A **physics layer** above it is the next
major addition: users describe buildings in physical terms (materials, thickness,
area, orientation), and the physics layer expands them into RC topology before
the solver sees them.

### Why the physics layer matters

Three problems with pure RC editing:

**Phase lag in thick walls.** A 40 cm brick wall needs ~5 RC nodes to capture
the 6–8 h thermal delay. That produces 9 free parameters (5×C, 4×R) that are
completely correlated along the chain — underdetermined fit even though the
physics only has 2 degrees of freedom (λ, ρ·cp).

**Parameter explosion in parallel paths.** Separate R for each wall surface
compounds the identifiability problem. Physically, one λ applies to all brick
walls; one SHGC applies to all windows of the same type. The physics layer
gives one knob per material, not one per surface.

**Order-of-magnitude analysis.** "Which surface dominates heat loss?" is
impossible to answer at the R/C level, natural at the physical level (U·A per
surface).

### Element vocabulary (physics layer, planned)

Four element types, distinguished by physics not by building part:

| Type | Models | Fit knobs |
|---|---|---|
| `room` | air + furniture mass | `furniture_factor` |
| `opaque` | thick layered stack (wall, roof, floor-above-cellar) | λ per material, α (solar), h_e, h_i |
| `glazing` | thin transparent (window, velux, glass door) | U, SHGC |
| `air_exchange` | infiltration + ventilation | ACH |

Roof/wall/slab differ by **properties** (`tilt`, `between: [..., "ground"]`),
not by kind. Keeps the code paths few and the expressive power high.

Air exchange is a separate element because for old houses it's often 30–50%
of the heat loss; a fit without it is badly biased.

## Solver pipeline

Three stages, each independently testable:

1. **`prepare_inputs(sim_config, influx_client)`** — fetches each signal from
   InfluxDB, resamples to a uniform grid. Slow, I/O-bound.
2. **`assemble(model) -> AssembledSystem`** — graph → `(A, B_boundary, B_source)`
   matrices. Resistance nodes are eliminated during assembly.
3. **`simulate_ivp` / `simulate_zoh`** — pure numerics, no I/O.

```python
@dataclass
class AssembledSystem:
    A: np.ndarray           # [n_mass × n_mass]
    B_boundary: np.ndarray  # [n_mass × n_boundary]
    B_source: np.ndarray    # [n_mass × n_source]
    mass_ids: list[str]
    boundary_ids: list[str]
    source_ids: list[str]
```

### Solver choice

Two solvers, used for different jobs:

- **`solve_ivp(BDF)`** — handles stiffness from the ~30× C ratio (thick wall
  vs room air). Good for exploration and verification.
- **ZOH (matrix exponential)** — exact for piecewise-constant inputs on a
  uniform grid: `x[k+1] = Ad @ x[k] + Bd @ u[k]`. O(n³) once to precompute,
  O(n²) per step. Required for optimisation / MCMC (fast enough for thousands
  of forward evaluations).

Implementation uses `scipy.signal.cont2discrete(..., method='zoh')` +
`scipy.signal.dlsim` — no custom matrix exponential.

## Parameter estimation

`solver/fit.py`. Workflow:

1. **`build_forward(model, inputs, observations, fit_config, start, end, ...)`**
   returns a pure `log_params_vec → residuals` closure. Params encoded in
   log-space; patches model dict, re-assembles, re-discretises per call.
2. **`fit_nls`** — `scipy.optimize.least_squares` (LM) in log-space. Log-normal
   priors folded in as extra residual terms. Returns best-fit params + covariance-
   derived std + cost.
3. **`fit_mcmc`** — `emcee` ensemble sampler, 20% burn-in, auto-thinning by
   autocorr time. Returns posterior samples + mean/std + acceptance rate.

Param key format: `node_id.field_name` (e.g. `R_ext.R`, `chambre.C`,
`apport.gain`). Once the physics layer ships, keys become physical:
`mur_SE.layers[0].lambda`, `materials.brick_full.lambda`.

## Data model

### Study (self-contained)

```json
{
  "id":           "chambre_jan_2024_2r1c",
  "label":        "Chambre — jan 2024 — 2R1C",
  "room":         "chambre",
  "model":        { "...topology..." },
  "start":        "2024-01-01",
  "end":          "2024-02-01",
  "inputs":       { "exterior": "open_meteo/temperature_2m" },
  "observations": { "chambre": "zigbee2mqtt/temperature?name=chambre" },
  "priors":       { "R_ext": { "nominal": 0.02, "sigma_log": 0.5 } },
  "solver":       "zoh",
  "result":       null
}
```

The study embeds its full topology — no inheritance at runtime. Duplicate a
study to make a variation (different topology, different period, tighter priors).

### Signal name convention

```
measurement/field               # e.g. open_meteo/temperature_2m
measurement/field?tag=value     # e.g. zigbee2mqtt/temperature?name=salon
```

Signals are stored in the study `inputs` map (node id → signal name), **not** in
the model topology. Keeps the graph reusable across time ranges and sensors.

### `house.json` — source of truth for physics

Single-house app: one `house.json` describes the building. Studies are spawned
from it (see "House → study" below) and embed the expanded RC topology at
creation time.

```json
{
  "label": "Maison Machin",
  "location": { "lat": 45.76, "lon": 4.83, "label": "Lyon" },
  "weather_source": "open_meteo",
  "materials": { "brick_full": { "lambda": 0.8, "rho": 1800, "cp": 840 } },
  "rooms": [
    { "id": "chambre", "a": 4.5, "b": 3.0, "c": 2.5 }
  ],
  "elements": [
    { "id": "mur_SE", "kind": "opaque", "between": ["chambre", "outdoor"],
      "a": 4.5, "b": 3.0, "orientation": "SE", "tilt": 90,
      "layers": [ { "material": "brick_full", "thickness": 0.40 } ],
      "modeling": { "detail": "2R1C" } }
  ],
  "periods": [
    { "id": "jan_2024_cold", "start": "2024-01-01", "end": "2024-02-01" }
  ],
  "defaults": {
    "inputs": { "exterior": "open_meteo/temperature_2m" },
    "solver": "zoh"
  }
}
```

- `location` + `weather_source` — single source of truth for `outdoor`. Studies
  inherit; no per-study re-picking.
- `element.modeling.detail` — persistent modeling choice (`lumped | 2R1C |
  chain-N`). Selection of which elements/rooms a study covers is transient
  (not saved on the house).
- `periods` — named time ranges, reusable across studies.

## House → study

The house is the **authoring surface**; the study is a self-contained snapshot
spawned from it. Flow:

1. In House/Simulate mode, user selects rooms (and per-element opt-out for edge
   cases) and confirms detail levels.
2. Picks a period (from `house.periods` or custom) and signals (defaults from
   `house.defaults`).
3. Backend runs `expand(house, selection, modeling_choices) → (rc_model,
   expansion_map)`.
4. Writes a new study JSON: `{ id, label, rooms, model: rc_model, expansion_map,
   start, end, inputs, observations, priors, result: null }`.
5. Opens the study in the right pane.

Editing the house **does not** retroactively change saved studies (studies are
reproducible snapshots). An explicit **Re-expand from house** action on a study
refreshes it from the current house description — surfaces drift instead of
hiding it.

### `expansion_map` — projection back to the house

Stored in the study JSON alongside the topology:

```json
"expansion_map": {
  "mur_SE": {
    "rc_nodes": ["mur_SE_c0"],
    "rc_edges": ["mur_SE_re", "mur_SE_ri"],
    "fit_params": ["mur_SE.layers[0].lambda"]
  }
}
```

Enables Results-on-house: backend `GET /studies/{id}/results_by_element`
projects time series + fit params through the map; UI tiles consume it.

### Files on disk

```
thermalnodes/data/
  house.json               house metadata + sensor defaults
  materials/               7 materials (λ, ρ, cp)
  examples/                read-only seed studies
  user/studies/            {id}.json per user study
```

## API surface

FastAPI on port 8001.

| Route | Purpose |
|---|---|
| `GET  /signals` | list all `measurement/field?tag=val` from InfluxDB |
| `GET  /series?signal=&start=&end=` | fetch + resample to 15 min |
| `GET  /studies` | list examples + user studies |
| `GET  /studies/{id}` | full study JSON |
| `POST /studies/{id}` | save to `data/user/studies/{id}.json` |
| `POST /studies/{id}/duplicate` | copy to new id |
| `GET  /house` / `POST /house` | read/write `house.json` |
| `POST /simulate/run` | fetch inputs, run ivp or zoh, return `{t, nodes, meta}` |
| `POST /fit/run` | fit NLS or MCMC, return fitted params + cost |
| `POST /house/expand` | `(selection, period) → (rc_model, expansion_map)`; preview before creating study |
| `POST /studies/from_house` | spawn a study from house selection + period |
| `POST /studies/{id}/re_expand` | re-run `expand()` against current house, replace topology |
| `GET  /studies/{id}/results_by_element` | project last run/fit through `expansion_map` |
| `GET  /weather?lat=&lon=&start=&end=` | fetch weather series from configured source |

## UI

SvelteKit + `@xyflow/svelte` + uPlot. Single-house app (no house selector;
`house.json` is *the* house).

### Layout — split view

```
┌─ left nav ──┐ ┌─ house ──── [edit|simulate] ─┐ ┌─ study ── [run|fit] [new][load] ─┐
│ Materials   │ │ ┌ location ─────────────────┐│ │ chambre_jan2024_2r1c  ● ⚠         │
│ House       │ │ │ Lyon · 45.7,4.8          ││ │ ─────────────────────────────────│
│ Weather     │ │ └───────────────────────────┘│ │ time range: Jan 1–Feb 1  [▼lib]  │
│ Studies     │ │ ┌ room A ───────────────────┐│ │ [run ▶]                          │
│             │ │ │ [wall S] [roof] [win]    ││ │ ─────────────────────────────────│
│             │ │ └───────────────────────────┘│ │ Weather  ▁▂▃▄▅                  │
│             │ │ ┌ room B ───────────────────┐│ │ T°       ──── (obs overlay)     │
│             │ │ │ [wall S] [slab]          ││ │ Energy   per-element stacked    │
│             │ │ └───────────────────────────┘│ │ Residuals (fit mode only)       │
│             │ │                              │ │ ─────────────────────────────────│
│             │ │                              │ │ [RC graph ▼]                    │
└─────────────┘ └──────────────────────────────┘ └──────────────────────────────────┘
```

Two panes side by side: **house** (left, the noun) + **study** (right, the verb).
Stacks vertically below ~1200px.

### Left nav

- **Materials** — library browser/editor
- **House** — split-view (default landing)
- **Weather** — location + weather source + period library
- **Studies** — saved studies list (open into split-view with that study loaded)

### House pane — modes

Mode switch at the top: `edit | simulate`. Same element tiles, different badges
and controls per mode.

- **Edit** — dimensions, materials, orientation. Click a tile to open editor.
- **Simulate** — detail-level chip (`lumped | 2R1C | chain-N`), computed `R_total`,
  `UA`. Tiles are selectable; selection scopes the next "new study". After a run,
  tiles show `Q_mean`, `Q_peak` badges (results projected back via the expansion map).

Element selection is **transient** (not saved on the house); detail level is
**persistent** (`element.modeling.detail` on the house JSON).

### Study pane — modes

Mode switch at the top: `run | fit`. Both modes show the same study header
(id, dirty `●`, stale `⚠`) and time-range/period selector.

- **Run** — forward-simulate, weather + T° + per-element energy charts.
- **Fit** — observations + priors tables, NLS/MCMC selector, residuals chart,
  fitted params overlaid back on house tiles.

`[new]` creates a study from the current house selection (rooms + elements) +
period; `[load]` opens the existing studies list. `[RC graph ▼]` expands a
collapsible pane showing the full expanded RC topology — debug / fine-control
view of what the solver sees.

### Results-on-house

After a run, the house pane projects results back onto element tiles via the
study's `expansion_map`:

- opaque/glazing/air_exchange → `Q_mean`, `Q_peak`, color-tinted by magnitude
- rooms → `T_mean`, `T_range`, observed-vs-modelled sparkline if Fit ran
- post-fit → `λ ± σ` badge per layer, color-coded by posterior shift vs prior

Clicking a tile filters the right-pane charts to that element's traces.

### Dirty / stale

Save lives in the study pane header. `●` amber when unsaved. `⚠ stale` on the
run button when sim config changed after the last run.

## Project structure

```
thermalnodes/
  schema/                       JSON schemas (v0.3)
  data/
    house.json                  house metadata + sensor defaults
    materials/                  7 materials (λ, ρ, cp)
    examples/                   read-only seed studies
    user/studies/               {id}.json per user study
  solver/
    assemble.py                 graph → AssembledSystem (A, B matrices)
    simulate.py                 simulate_ivp + simulate_zoh + simulate_mock
    fit.py                      NLS + MCMC parameter estimation
    identifiability.py          parameter correlation analysis
    tests/
  api/
    main.py                     FastAPI app (studies, signals, simulate/*, fit/*)
    influx.py                   InfluxDB client
    config.py                   env-based config (MINIHA_INFLUX_* vars)
  solver/
    physics.py                  expand(house, selection) → (rc_model, expansion_map)
  ui/
    src/
      routes/+page.svelte       app shell — left nav + split view
      lib/HousePane.svelte      house pane (edit|simulate modes, room/element tiles)
      lib/StudyPane.svelte      study pane (run|fit modes, charts, RC drawer)
      lib/WeatherPanel.svelte   location + weather source + period library
      lib/MaterialsPanel.svelte material library browser
      lib/GraphView.svelte      SvelteFlow canvas (used inside RC drawer)
      lib/PropertiesPanel.svelte  node/edge inspector
      lib/InputsPanel.svelte    date range + signal assignment + preview
      lib/SimulationRun.svelte  fetch/run + results charts
      lib/FitPanel.svelte       observations + params + fit results
      lib/modelToFlow.js        model JSON → SvelteFlow nodes/edges
```

## Design decisions

- **Solver split**: `solve_ivp(BDF)` for correctness, ZOH for optimisation/MCMC.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
- **R and C as raw numbers** at the model level; physics layer above will compute
  them from material properties.
- **Boundaries**: fixed-temperature forcing nodes, not solved.
- **Heat sources**: explicit edge `source → mass` in the graph (dependency is
  structural, not metadata).
- **Sim config separate from model**: signal→node binding lives in the study, not
  the topology. Topology stays reusable across datasets and time ranges.
- **Observations** live in the sim config alongside `inputs`, not in the model.
- **Fit config separate**: `{ params, obs_sigma, method }`. Log-normal priors.
  NLS first; MCMC can warm-start from NLS.
- **Studies are self-contained**: full topology embedded, no inheritance. Duplicate
  to vary. Spawned from the house via `expand()`; embed `expansion_map` for
  results-projection.
- **Single house**: no house selector, no `/houses` list. `house.json` is *the*
  house. Studies reference it implicitly via the embedded snapshot.
- **House = noun, study = verb**: split-view layout, two panes side by side.
  Modes (`edit|simulate`, `run|fit`) toggle controls/badges, not whole UIs.
- **Selection is transient, detail is persistent**: which elements a study
  covers belongs to the study; how each element is modeled belongs to the house.
- **Location on the house, not the study**: avoids re-picking weather per
  iteration.
- **ZOH via scipy**: `cont2discrete` + `dlsim`, no custom matrix exponential.
- **Thick walls at MVP**: 2R1C block (R_ext, mass, R_int). Already in
  `chambre_v1`.

## Reference implementations

- `miniha/th_models/load.py` — production InfluxDB loader using RoomConfig YAML
- `miniha/th_models/inspector.py` — Streamlit prototype (reference only;
  Svelte UI is the target)
- `miniha/th_models/fit_2r2c.py` — ZOH + matrix-exp reference implementation
