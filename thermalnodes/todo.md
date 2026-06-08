# thermalnodes — todo

Open work and changelog. For architecture + current state, see
[project_description.md](project_description.md).

---

## Current focus

**Prototype the new split-view workflow end-to-end.** Goal: pick rooms on the
house → `expand()` → study spawned → forward run → results back on house. Get
the loop working with minimal polish, then iterate.

See *Prototype milestones* below. Architecture rationale in
[project_description.md](project_description.md).

---

## Prototype milestones

The loop we want working first:

> Open house → click rooms → pick period → run → see T_in + per-element Q
> projected back onto the house tiles → tweak detail level → re-run.

Fit comes after.

### M1 — Split-view shell + mode switches

1. Restructure `routes/+page.svelte` into split view: left nav + house pane +
   study pane. Stack vertically below ~1200px.
2. `HousePane.svelte` — `edit | simulate` mode switch at top. Edit mode = current
   `HousePanel.svelte` behavior. Simulate mode = same tiles, swap to detail-level
   chips + selection checkboxes (no results yet).
3. `StudyPane.svelte` — `run | fit` mode switch + study header (id, dirty,
   stale) + `[new] [load]` buttons. Run mode wraps existing `SimulationRun.svelte`;
   fit wraps `FitPanel.svelte`.
4. Left nav: Materials · House · Weather · Studies (the only items).
5. Drop the global "Home" study browser; "Studies" left-nav item opens a list
   that loads into the right pane.

### M2 — Weather / location

1. `house.json` schema additions: `location: {lat, lon, label}`,
   `weather_source: "open_meteo"`, `periods: [{id, start, end}]`.
2. `WeatherPanel.svelte` — location form + source picker + named-period editor.
3. `GET /weather?lat=&lon=&start=&end=` — backend wrapper around open-meteo,
   returns same shape as `/series`.
4. Period dropdown in study pane reads `house.periods`.

### M3 — Selection + `expand()` + study spawning

1. `element.modeling: { detail: "lumped" | "2R1C" | "chain-N", n?: int }` field
   on house schema (persistent, edited in Simulate mode).
2. Selection state in `HousePane` (transient): which rooms are selected; per-element
   opt-out. Selecting a room selects all its elements by default.
3. **`solver/physics.py` — `expand(house, selection) → (rc_model, expansion_map)`**.
   First pass: `opaque` (lumped + 2R1C), `glazing` (lumped), `room` (single C),
   `air_exchange` (single R). Chain-N later.
   - ISO 6946 `R_total = 1/h_i + Σ d/λ + 1/h_e`.
   - `C = ρ·cp·thickness·area` for the lumped mass of a layered wall.
   - Returns `expansion_map` keyed by element id (see project_description.md).
4. `POST /house/expand` — preview endpoint (returns rc_model + expansion_map
   without persisting).
5. `POST /studies/from_house` — body: `{ selection, period_id_or_range, signals?,
   priors? }` → writes a new study with embedded `model` + `expansion_map`.
6. **`[new]` button** in study pane → modal: confirm rooms (pre-filled from
   house selection), pick period, name the study → POST → load it.

### M4 — Results projected back on house

1. Persist last run result on the study JSON (already partially done for fit).
2. `GET /studies/{id}/results_by_element` — projects time series through
   `expansion_map`, returns `{element_id: {Q_mean, Q_peak, Q_series, T_mean?, ...}}`.
3. Simulate-mode tiles consume that endpoint: badges (`Q_mean`, `Q_peak`),
   color-tint by magnitude.
4. Click a tile → filter the right-pane charts to that element's traces.

### M5 — RC drawer + re-expand

1. Collapsible `[RC graph ▼]` at the bottom of the study pane — wraps existing
   `GraphView.svelte` on the embedded `model`.
2. **Re-expand from house** action on study header — re-runs `expand()` against
   the current house, replaces `model` + `expansion_map`, marks stale.
3. Diff/warn if the new expansion drops nodes that had fitted values.

### M6 — Fit polish

1. Fit-mode tile badges: post-fit `λ ± σ` per layer, color-coded by posterior
   shift vs prior.
2. Save fit result back into the study JSON under `fit_result`.
3. **Promote to priors** — write `fit_result.params` back as tightened priors.
4. API: `POST /studies/{id}/save_fit`, `POST /studies/{id}/promote_priors`.

---

## Carry-overs (do alongside or after M1–M6)

- **UA summary bar chart** in Simulate mode — per-element `UA = a*b/R_total`,
  horizontal bars, color by kind. Falls out of the `expand()` data naturally.
- **Material library extension** — add `category` field; add `brique_creuse`,
  `stone_rubble`, `lime_plaster`, `wood_floor`, `tile_clay`, `concrete_slab`.
- **Materials panel** (left-nav) — browser/editor for the library.
- **`GET /materials`** endpoint.
- **Chain-N detail level** for thick walls (phase-lag-sensitive fits).
- **Clean up legacy fields** in example study JSONs (`T_source`, `signal` on
  boundary/source nodes — solver ignores them).

---

## Backlog (not committed)

- **House UI v2** — 2D floor-plan-ish canvas (rooms as rectangles, walls as
  edges). Layer on top of v1 only if v1 proves too tedious.
- **LLM-assisted model builder** — house description → LLM → initial study.
- **MCMC corner plot** — marginal histograms per param.
- **Multi-house** — re-introduce a house selector if/when needed (deliberately
  out of scope for now).

---

## Changelog

- **2026-06** — Direction shift: split-view layout (house pane + study pane),
  `edit|simulate` and `run|fit` modes, single-house app, studies spawned from
  house via `expand()`, `expansion_map` for results-on-house projection. See
  *Prototype milestones* above.
- **2026-06** — House persistence: `GET /house` on mount, Save button + dirty indicator
  (mirrors study save pattern); room dimensions `a × b × c` replacing `volume`
- **2026-06** — House tab UI (`HousePanel.svelte`): room list, element cards
  (opaque/glazing/air_exchange), layer stack editor, `a × b` dimensions
- **2026-06** — `schema/house_model.schema.json` v0.1: rooms, elements, materials;
  `a`/`b` dims, `between` topology, `category` on material schema
- **2026-06** — Fit charts: temperatures with observed overlay, inputs, residuals
- **2026-06** — Identifiability module (parameter correlation analysis)
- **2026-06** — Group charts by unit (boundary temps on temperature chart,
  power separate); fix `SimulationRun` uPlot arg order
- **2026-06** — Parameter estimation: `solver/fit.py` (NLS + MCMC) + `POST /fit/run`
  + Fit tab UI
- **2026-06** — Stale/save cycle (dirty Save badge, stale Run banner)
- **2026-06** — Inputs panel rework
- **2026-05** — UI layout refactor: Home / Topology / Inputs / Run / Fit tabs;
  Save pinned bottom-left; model notes in PropertiesPanel
- **2026-05** — Study persistence: `GET/POST /studies`, duplicate, `house.json`
- **2026-05** — ZOH solver (`scipy.signal.cont2discrete` + `dlsim`); verified
  vs IVP < 0.01 °C
- **2026-04** — `simulate_ivp` (BDF); verified vs analytical `T(t) = 10·(1 − exp(−t/τ))`
- **2026-04** — `assemble()` — graph → `AssembledSystem`; τ matches R·C
- **2026-03** — Svelte graph editor: SvelteFlow canvas, custom node types,
  resistance edges, properties panel, signal autocomplete
- **2026-03** — FastAPI backend: `/signals`, `/series`, mock `/simulate`
- **2026-03** — Material library (7 entries) + example studies
  (`chambre_1r1c`, `chambre_v1`, `chambre_2r2c`)
