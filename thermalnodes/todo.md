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

### ~~M1 — House view: flat list~~ ✓ done

`HousePanel.svelte` rewritten as a flat list. `house.json` migrated.

### ~~M1b — House view: grid layout + icon toolbar + split view~~ ✓ done

- CSS grid aligned columns: kind icon, label, connectivity, key figures,
  include checkbox, chevron.
- Add toolbar at top (room / opaque / glazing / air_exchange buttons).
- Save button moved from sidenav into toolbar (right-aligned).
- "Create study" button in toolbar; fires `oncreatestudy(selectedIds)`.
- Include checkbox column per row (outdoor excluded); selection is local state.
- Click entire row header to expand/collapse (no separate button).
- Delete moved into expanded editor.
- Split view: house pane (left, fills space) + simulation pane (right, 340px,
  placeholder for now).
- Key figures computed client-side: volume (rooms), area + UA (walls/glazing),
  ACH (air exchange).

~~UUID + label rename deferred to M1c (lower priority than M3).~~ ✓ done (M1c)

### ~~M2 — Periods~~ → replaced by element signals ✓ done

Predefined periods dropped in favour of attaching signals directly to house
elements. Each room gets optional `input_signal` (heat source, W) and
`obs_signal` (T° sensor); `outdoor` gets optional `obs_signal` (T° override).
Signals use the existing InfluxDB URI format (`measurement/field?tag=val`).
Collapsed row shows `⤵` / `◉` icons when signals are set; expanded editor
shows autocomplete fields backed by `GET /signals`.

### ~~M3 — Selection + `expand()` + study spawning~~ ✓ done (partial)

1. `element.modeling: { detail: "lumped" | "2R1C" | "chain-N", n?: int }`
   field on house schema (persistent). ← deferred
2. Simulate mode on the house list: checkboxes per row for selection;
   detail-level chip per element row. Selecting a room auto-selects its
   connected elements (opt-out per element). ← deferred
3. ~~**`solver/physics.py` — `expand(house, selection) → (rc_model,
   expansion_map)`**. First pass: `opaque` (lumped + 2R1C), `glazing`
   (lumped), `room` (single C), `air_exchange` (single R), `outdoor`
   (boundary node, pulls `lat`/`lon`/`weather_source` from element).
   - ISO 6946 `R_total = 1/h_i + Σ d/λ + 1/h_e`.
   - `C = ρ·cp·thickness·area` for lumped wall mass.~~ ✓ done
   - Signature: `expand(house, selection)` — full house + selected UUIDs.
   - Selected rooms → mass nodes; unselected rooms / outdoor / ground → boundary.
   - Global material library from `data/materials/`; house-local overrides on top.
   - Room `input_signal` → source node; `outdoor.obs_signal` → boundary `T_source`.
   - 18 tests in `solver/tests/test_physics.py`, all passing.
4. ~~`POST /house/expand` — preview (returns rc_model + expansion_map,
   no persist).~~ ✓ done
5. ~~`POST /studies/from_house` — body: `{ house, selection, label, study_id }`
   → new study JSON with embedded model + expansion_map, persisted under
   `data/user/studies/`.~~ ✓ done
6. ~~`[Create study]` button in house toolbar → modal: name + optional ID →
   POST → open study in Topology tab.~~ ✓ done

**Next in M3:**
- Switch study IDs to UUID; `label` becomes the display name. Study cards
  show label prominently, UUID as small monospace. Save dialog drops manual
  ID entry (auto-generates UUID). Consistent with house element UUID scheme.
- `element.modeling` detail field + detail-level chip per row.
- Auto-select connected elements when a room is checked.

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

- **2026-06** — M3 partial: study spawning — `POST /house/expand` (preview),
  `POST /studies/from_house` (expand + persist); house toolbar "Create study"
  button opens modal (name + optional ID) → calls backend → opens new study.
- **2026-06** — Element signals (M2 replacement) — `input_signal` / `obs_signal`
  fields on rooms and outdoor (schema v0.2 extension); house row shows `⤵` / `◉`
  icons when set; expanded editor has signal fields with InfluxDB autocomplete.
- **2026-06** — UUID + label (M1c) — schema v0.2: all element and room `id`s are
  UUIDs, `label` is a free-editable string separate from the key; `outdoor` and
  `ground` are proper typed elements (no magic strings in `between`); toolbar
  buttons create a skeleton + expand immediately (single unified edit form, no
  separate add form); `house.json` rewritten from scratch.
- **2026-06** — House view: grid + split view — CSS grid columns (icon, label,
  connectivity, key figures, include checkbox); toolbar with add buttons, Save,
  Create study; split layout with placeholder simulation pane; row-click to
  expand; delete in editor; key figures client-side.
- **2026-06** — House view: flat list (`HousePanel.svelte` rewrite) — rooms,
  elements, and `outdoor` as peer rows; inline expansion; `outdoor` element
  with `location` + `weather_source`; `house.json` migrated.
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
