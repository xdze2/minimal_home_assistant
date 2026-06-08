# thermalnodes — todo

Open work and changelog. For architecture + current state, see
[project_description.md](project_description.md).

---

## Current focus

**Prototype the house → expand() → study → run loop end-to-end.** Get it
working with minimal polish, then iterate.

See *Prototype milestones* below.

---

## Design decisions (updated)

### House view: flat list, no nesting

Elements and rooms are peers in a single flat list, ordered by `between`
topology. No room sidebar selecting a filtered sub-list. A shared wall between
two rooms appears once, not nested under either.

```
[room]    chambre       5 × 5 × 3 m
[room]    salon         4 × 6 × 3 m
[opaque]  mur_SE        chambre ↔ outdoor   SE 90°  brick 30cm
[glazing] win_SE        chambre ↔ outdoor   SE      U=2.8 SHGC=0.67
[opaque]  mur_shared    chambre ↔ salon     —       brick 20cm
[airexch] infil_chbr    chambre ↔ outdoor   0.4 ACH
[outdoor] outdoor       Lyon · 45.7,4.8     open-meteo
```

Clicking a row expands it inline for editing. One open at a time.

### outdoor as an explicit element

`outdoor` is no longer an implicit string sentinel — it is a first-class
element of kind `outdoor` on the house. It holds:
- `location: { lat, lon, label }`
- `weather_source: "open_meteo"`

This replaces the planned separate Weather panel and `house.location` /
`house.weather_source` top-level fields. The `between` field on other elements
still references `"outdoor"` by id; the `outdoor` element is just the record
that gives it a data source and coordinates.

There is at most one `outdoor` element per house. `ground` remains implicit
(no weather source needed).

### No split-view (for now)

The planned `HousePane` / `StudyPane` side-by-side layout is deferred.
The current left-nav + main-area shell stays. Studies section keeps its
existing Topology / Inputs / Run / Fit tabs.

The `edit | simulate` mode distinction on the house is kept — it's a useful
toggle on the same view, not a pane split.

---

## Prototype milestones

The loop we want working first:

> Open house → select elements → pick period → run → see T_in + per-element Q
> back on the house list → tweak detail level → re-run.

Fit comes after.

### M1 — House view: flat list

Refactor `HousePanel.svelte` from room-sidebar + filtered-elements to a single
flat list of all house items.

1. Render order: rooms and elements interleaved, grouped visually by proximity
   (rooms first, then their connected elements, but no nesting in the DOM).
2. Each row: `[kind badge]  id  summary  [▼ edit]  [×]`
3. Expanded inline editor — same fields as the current card editor.
4. **`outdoor` row** at the bottom of the list (or top — decide by feel).
   Expanded editor: `location.lat`, `location.lon`, `location.label`,
   `weather_source` dropdown (`open_meteo` only for now).
5. Add-element form: remove the room pre-selection requirement; `between[0]`
   is now a dropdown of all rooms + `outdoor` + `ground`.
6. Remove the rooms sidebar entirely. Rooms are just rows with kind `room`
   and inline `a × b × c` editing.
7. Migrate `house.json`: add `{ "id": "outdoor", "kind": "outdoor",
   "location": {...}, "weather_source": "open_meteo" }` to `elements`;
   remove top-level `location` / `weather_source` if present.

### M2 — Periods

Named time ranges, reusable across studies.

1. `house.periods: [{ id, start, end, label? }]` — add to schema and
   `house.json`.
2. Period editor in the house view (inline row or separate section below
   the element list).
3. Period dropdown in the study Inputs panel reads `house.periods`; custom
   range still possible.

### M3 — Selection + `expand()` + study spawning

1. `element.modeling: { detail: "lumped" | "2R1C" | "chain-N", n?: int }`
   field on house schema (persistent).
2. Simulate mode on the house list: checkboxes per row for selection;
   detail-level chip per element row. Selecting a room auto-selects its
   connected elements (opt-out per element).
3. **`solver/physics.py` — `expand(house, selection) → (rc_model,
   expansion_map)`**. First pass: `opaque` (lumped + 2R1C), `glazing`
   (lumped), `room` (single C), `air_exchange` (single R), `outdoor`
   (boundary node, pulls `lat`/`lon`/`weather_source` from element).
   - ISO 6946 `R_total = 1/h_i + Σ d/λ + 1/h_e`.
   - `C = ρ·cp·thickness·area` for lumped wall mass.
4. `POST /house/expand` — preview (returns rc_model + expansion_map,
   no persist).
5. `POST /studies/from_house` — body: `{ selection, period_id_or_range,
   signals?, priors? }` → new study JSON with embedded model +
   expansion_map.
6. `[New study]` button in Studies section → modal: confirm selection,
   pick period, name → POST → open study.

### M4 — Results projected back on house

1. Persist last run result on the study JSON.
2. `GET /studies/{id}/results_by_element` — projects through
   `expansion_map`, returns `{ element_id: { Q_mean, Q_peak, T_mean? } }`.
3. Simulate-mode house rows show `Q_mean` / `Q_peak` badges after a run,
   color-tinted by magnitude.
4. Click a row → filter study charts to that element's traces.

### M5 — RC drawer + re-expand

1. Collapsible `[RC graph ▼]` at the bottom of the study view — wraps
   existing `GraphView.svelte` on the embedded `model`.
2. **Re-expand from house** action on study header — re-runs `expand()`
   against current house, replaces `model` + `expansion_map`, marks stale.
3. Warn if new expansion drops nodes that had fitted values.

### M6 — Fit polish

1. Post-fit `λ ± σ` badges per layer on house rows, color-coded by
   posterior shift vs prior.
2. Save fit result into study JSON under `fit_result`.
3. **Promote to priors** — write `fit_result.params` back as tightened
   priors.
4. API: `POST /studies/{id}/save_fit`, `POST /studies/{id}/promote_priors`.

---

## Carry-overs (do alongside or after M1–M6)

- **UA summary bar** in Simulate mode — per-element `UA = a*b / R_total`,
  horizontal bars, color by kind. Falls out of `expand()` naturally.
- **Material library extension** — `category` field; add `brique_creuse`,
  `stone_rubble`, `lime_plaster`, `wood_floor`, `tile_clay`, `concrete_slab`.
- **Materials panel** (left-nav) — browser/editor for the library.
- **`GET /materials`** endpoint.
- **Chain-N detail level** for thick walls.
- **Clean up legacy fields** in example study JSONs (`T_source`, `signal`
  on boundary/source nodes — solver ignores them).

---

## Backlog (not committed)

- **House UI v2** — 2D floor-plan-ish canvas (rooms as rectangles, walls as
  edges). Layer on top of v1 only if v1 proves too tedious.
- **Split-view** — house pane + study pane side-by-side, `edit|simulate`
  and `run|fit` modes. Revisit once the flat-list house view is stable.
- **LLM-assisted model builder** — house description → LLM → initial study.
- **MCMC corner plot** — marginal histograms per param.
- **Multi-house** — re-introduce a house selector if/when needed.

---

## Changelog

- **2026-06** — Design update: flat element list (drop room-sidebar nesting),
  `outdoor` as explicit element with location + weather_source, split-view
  deferred to backlog.
- **2026-06** — Direction shift: split-view layout (house pane + study pane),
  `edit|simulate` and `run|fit` modes, single-house app, studies spawned from
  house via `expand()`, `expansion_map` for results-on-house projection.
- **2026-06** — House persistence: `GET /house` on mount, Save button + dirty
  indicator; room dimensions `a × b × c` replacing `volume`
- **2026-06** — House tab UI (`HousePanel.svelte`): room list, element cards
  (opaque/glazing/air_exchange), layer stack editor, `a × b` dimensions
- **2026-06** — `schema/house_model.schema.json` v0.1: rooms, elements,
  materials; `a`/`b` dims, `between` topology, `category` on material schema
- **2026-06** — Fit charts: temperatures with observed overlay, inputs,
  residuals
- **2026-06** — Identifiability module (parameter correlation analysis)
- **2026-06** — Group charts by unit; fix `SimulationRun` uPlot arg order
- **2026-06** — Parameter estimation: `solver/fit.py` (NLS + MCMC) +
  `POST /fit/run` + Fit tab UI
- **2026-06** — Stale/save cycle (dirty Save badge, stale Run banner)
- **2026-06** — Inputs panel rework
- **2026-05** — UI layout refactor: Home / Topology / Inputs / Run / Fit tabs
- **2026-05** — Study persistence: `GET/POST /studies`, duplicate, `house.json`
- **2026-05** — ZOH solver (`scipy.signal.cont2discrete` + `dlsim`)
- **2026-04** — `simulate_ivp` (BDF); `assemble()` — graph → `AssembledSystem`
- **2026-03** — Svelte graph editor, FastAPI backend, material library
