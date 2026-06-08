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
      "date_range": ["2024-01-01", "2024-02-28"],
      "inputs": {
        "solar_signal": "...",
        "obs_signal": "..."
      },
      "run": {
        "settings": { ... },
        "model_hash": "a3f9bc...",
        "output_file": "my_house_<study_id>_run_20240115T143022.parquet"
      },
      "fit": {
        "settings": { ... },
        "model_hash": "a3f9bc...",
        "output_file": "my_house_<study_id>_fit_20240115T143022.parquet",
        "result_params": { ... }
      }
    }
  ]
}
```

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

- **Chain-N detail level** for thick walls.
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
