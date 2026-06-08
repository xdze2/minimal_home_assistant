# thermalnodes — todo

---

## Data model

### House file (`houses/<name>.json`)

One file per house. The RC model is derived deterministically from elements on
load — not stored. Studies are embedded in the house file.

```json
{
  "name": "my_house",
  "elements": [ ... ],
  "studies": [
    {
      "id": "<uuid4>",
      "label": "Winter 2024",
      "type": "run",
      "date_range": ["2024-01-01", "2024-02-28"],
      "inputs": {
        "solar_signal": "...",
        "obs_signal": "..."
      },
      "result": {
        "settings": { ... },
        "model_hash": "a3f9bc...",
        "output_file": "my_house_<study_id>_run_20240115T143022.parquet",
        "result_params": { ... }
      }
    }
  ]
}
```

Each study is either `"type": "run"` (forward simulation) or `"type": "fit"` (parameter estimation) — not both. `result_params` is only populated for fit results.

### RC model (derived, not stored)

`expand(elements) → rc_model` — pure function, called on load and after any
element edit. No selection mechanism: all elements are always used.

### Model hash

SHA-256 of the canonical JSON serialization of `elements` (keys sorted,
no whitespace), first 12 hex chars. Stored on each run/fit result. On load,
recompute and compare — flag study as stale if they differ.

```python
def model_hash(elements):
    canonical = json.dumps(elements, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
```

### Parquet files

Stored alongside house files. Named automatically:
`<house_name>_<study_id>_<type>_<timestamp>.parquet`
where `<type>` is `run` or `fit`. Referenced by filename in the study JSON.

---

## Milestones

### ~~M1 — House view: flat list~~ ✓ done
### ~~M1b — House view: grid layout + icon toolbar + split view~~ ✓ done
### ~~M1c — UUID + label rename~~ ✓ done
### ~~M2 — Element signals~~ ✓ done
### ~~M3 — `expand()` + study spawning~~ ✓ done

### ~~M4 — New data model migration~~ ✓ done

Migrate from the current study-centric layout to the house-centric model
described above.

1. **Backend**: `houses/` directory, `GET /houses`, `GET /houses/{name}`,
   `PUT /houses/{name}`. Studies embedded in house JSON.
2. **`expand(elements)`** — drop the `selection` argument; always expand all
   elements.
3. **Model hash** — compute on every save; store on run/fit results; expose
   stale flag on load.
4. **Parquet naming** — `<house>_<study_id>_<type>_<timestamp>.parquet`.
5. **UI** — house picker / list on home screen; study list inside house view.

### M5 — Results projected back on house

1. `GET /houses/{name}/studies/{id}/results_by_element` — projects run output
   through expansion map, returns `{ element_id: { Q_mean, Q_peak, T_mean? } }`.
2. House rows show `Q_mean` / `Q_peak` badges after a run, color-tinted by
   magnitude.
3. Click a row → filter study charts to that element's traces.

### M6 — Working Fit

1. Fit runs correctly end-to-end (NLS + optional MCMC).
2. Fit result saved: parquet for time-series output, `result_params` in JSON.
3. Model hash stored on fit result; stale flag shown if elements changed.
4. Post-fit `λ ± σ` badges per layer on house rows, color-coded by posterior
   shift vs prior.
5. **Promote to priors** — write `result_params` back as tightened priors on
   elements.

---

## Backlog

### Heavy wall — chain-N discretization

For dense materials (concrete, brick, stone), a thick wall has significant
thermal lag at the 24h period. The penetration depth criterion determines
whether a wall needs chain discretization:

```
δ = sqrt(2·α/ω)    with α = λ/(ρ·c),  ω = 2π/86400 rad/s
```

Typical values at 24h period: concrete ~17 cm, brick ~15 cm, stone ~24 cm,
insulation ~2 cm (but negligible mass anyway).

**Design decisions:**
- `chain_n = max(1, ceil(thickness / δ))` computed inside `expand()` from
  element material properties — never stored, never a user input.
- Thin layers and insulation stay lumped (`chain_n = 1`).
- `_expand_opaque()` emits N nodes in series when `chain_n > 1`, splitting
  R and C evenly: `r_i = R_wall/N`, `c_i = C_wall/N`.
- Node IDs: `mur_sud_0`, `mur_sud_1`, … — internal, never exposed to the fit.

**Fit reparametrization:**
- Fit params remain `(R_wall, C_wall)` per element — 2 DOF regardless of N.
- `_patch_model()` maps `(R_wall, C_wall)` → N node values inside the loop;
  the expansion map (already built by `expand()`) records which nodes belong
  to each element.
- No performance regression: `expand()` still runs once; `assemble()` and
  `simulate_zoh()` are called every iteration as before; matrix grows by
  `N-1` state variables per chained wall (negligible).
- Fit config schema: params named after elements (`"mur_sud.R"`, `"mur_sud.C"`),
  not after internal nodes.

**UI:**
- Element row shows a small chain badge (e.g. `×3`) when `chain_n > 1`.
- RC graph renders the N resistors/capacitors in series for chained walls.
- Penetration depth is recomputed on every element edit (cheap).

### Parallel/series resistance identifiability

Parallel resistors sharing the same node pair: only the effective parallel R
is observable from temperature data. Series resistors between the same two
zones: only the sum is observable.

**Design decisions:**
- Keep individual element params with their own priors. The prior encodes
  construction knowledge (material, thickness) and can resolve elements when
  priors are sufficiently different.
- `group_params()` in `identifiability.py` already handles parallel grouping:
  collapses to one scale multiplier, freezes the nominal ratio.
- **To add:** same grouping logic for series resistors — detect chains where
  only the sum is identifiable, collapse to one multiplier.
- Do not reparametrize to effective values by default; let tight priors
  separate individual elements when the information is there.

### Other

- **Material library extension** — `brique_creuse`, `stone_rubble`,
  `lime_plaster`, `wood_floor`, `tile_clay`, `concrete_slab`.
- **Materials panel** (left-nav) — browser/editor for the library.
- **Copy elements between houses** — select elements from one house, paste
  into another.
- **House UI v2** — 2D floor-plan canvas.
- **LLM-assisted model builder** — house description → LLM → initial house.
- **MCMC corner plot** — marginal histograms per param.

---

## Changelog

- **2026-06** — Right pane rework — 3 fixed tabs: RC Graph (per-house, read-only),
  Studies (table with label/start/end/type/status columns; "+ Run" and "+ Fit" buttons),
  Simulation (study detail: time range, solver, run/fit action, charts); study type is now
  set at creation (`type: "run"|"fit"`) — a study is one or the other, not both; "Create
  study" removed from HousePanel toolbar.

- **2026-06** — House UI improvements — inline house label editor in HousePanel toolbar;
  delete house button (with confirm) + `DELETE /houses/{name}` backend endpoint; Studies
  section removed from left nav — all study navigation (Studies list, Simulation,
  Topology, Inputs, Run, Fit, RC, JSON tabs) moved into the right pane of the house split
  view; study save bar with back button replaces left-nav Save.

- **2026-06** — M4: New data model — `houses/` directory replaces single `house.json`; houses
  have embedded studies; `GET /houses`, `GET /houses/{name}`, `PUT /houses/{name}`,
  `POST /houses/{name}/studies`, `PUT/DELETE /houses/{name}/studies/{id}` endpoints;
  `expand()` drops `selection` arg — room/element `role` field (`mass`|`boundary`|`fixed`)
  controls node type; `model_hash()` (SHA-256 of elements, 12 hex chars) computed on every
  save and stored on run/fit results with stale flag; `house_name`+`study_id` context on
  `/simulate/run` and `/fit/run` persists result record into house JSON; UI: multi-house
  picker home screen, studies embedded in house, role badge + role selector in HousePanel.

- **2026-06** — House split view UI — simulation pane reworked: 1/3 house + 2/3
  sim split; toolbar add-buttons on own row; "Create study" fires immediately
  (no name dialog); sim pane has two tabs: *Simulation* (date range picker with
  duration presets + solver radios + Run/Fit/Show-inputs bar + charts) and *RC
  graph*; `SimulationRun` gains `hideControls` / `onready` props so the pane
  owns the control bar while the component owns chart state.
- **2026-06** — Study UUID (M3) — study IDs are now UUID4; `label` is the
  display name; save goes in-place for user studies, forks a new UUID for
  examples; duplicate auto-generates UUID.
- **2026-06** — M3 partial: study spawning — `POST /house/expand` (preview),
  `POST /studies/from_house` (expand + persist); house toolbar "Create study"
  button opens modal → calls backend → opens new study.
- **2026-06** — Element signals (M2) — `input_signal` / `obs_signal` on rooms
  and outdoor; house row icons; signal fields with InfluxDB autocomplete.
- **2026-06** — UUID + label (M1c) — schema v0.2: all element/room ids are
  UUIDs, `label` free-editable; `outdoor` and `ground` as typed elements;
  `house.json` rewritten.
- **2026-06** — House view: grid + split view — CSS grid columns; toolbar;
  split layout; row-click to expand; key figures client-side.
- **2026-06** — House view: flat list (`HousePanel.svelte` rewrite).
- **2026-06** — Fit charts: temperatures with observed overlay, inputs, residuals.
- **2026-06** — Identifiability module (parameter correlation analysis).
- **2026-06** — Parameter estimation: `solver/fit.py` (NLS + MCMC) +
  `POST /fit/run` + Fit tab UI.
- **2026-06** — Stale/save cycle (dirty Save badge, stale Run banner).
- **2026-05** — UI layout refactor: Home / Topology / Inputs / Run / Fit tabs.
- **2026-05** — Study persistence: `GET/POST /studies`, duplicate, `house.json`.
- **2026-05** — ZOH solver (`scipy.signal.cont2discrete` + `dlsim`).
- **2026-04** — `simulate_ivp` (BDF); `assemble()` — graph → `AssembledSystem`.
- **2026-03** — Svelte graph editor, FastAPI backend, material library.
