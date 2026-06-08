# thermalnodes — todo

Open work and changelog. For architecture + current state, see
[project_description.md](project_description.md).

---

## Current focus

Physics layer (`solver/physics.py` + house-builder UI). See *Next up* below.

---

## Next up — Physics layer

The pure RC model is sound but has known identifiability problems (phase lag
in thick walls, parameter explosion in parallel surfaces). Rationale in
[project_description.md](project_description.md#why-the-physics-layer-matters).

### Element vocabulary

Four kinds, distinguished by physics (not building part):

| Kind | Models | Fit knobs |
|---|---|---|
| `room` | air + furniture mass | `furniture_factor` |
| `opaque` | thick layered stack (wall, roof, floor) | λ per material, α (solar), h_e, h_i |
| `glazing` | thin transparent (window, velux) | U, SHGC |
| `air_exchange` | infiltration + ventilation | ACH |

Roof/wall/slab differ by `tilt` + `between: [room, "outdoor"|"ground"|other_room]`,
not by kind. `air_exchange` is its own kind because it dominates losses in old
houses and a fit without it is biased.

### House-model schema

Top-level `materials` dict for shared parameters; `rooms` + `elements` lists.
`between: [a, b]` is the topology — `a`, `b` are room ids or virtual zones
(`outdoor`, `ground`). Dimensions as `a × b` [m] instead of `area` — works
uniformly for walls (width × height), floors/roofs (width × depth or slope length),
and windows (width × height).

```json
{
  "materials": { "brick_full": { "lambda": 0.8, "rho": 1800, "cp": 840 } },
  "rooms":    [ { "id": "chambre", "volume": 75 } ],
  "elements": [
    { "id": "mur_SE", "kind": "opaque", "between": ["chambre", "outdoor"],
      "a": 4.5, "b": 3.0, "orientation": "SE", "tilt": 90,
      "layers": [ { "material": "brick_full", "thickness": 0.40 } ] },
    { "id": "win_SE", "kind": "glazing", "between": ["chambre", "outdoor"],
      "a": 1.2, "b": 1.4, "U": 2.8, "SHGC": 0.67 },
    { "id": "infil_chambre", "kind": "air_exchange", "between": ["chambre", "outdoor"],
      "ach": 0.4 }
  ]
}
```

### Implementation order

1. ~~**Schema** — JSON schema for house model (`schema/house_model.schema.json`)~~ ✓
2. ~~**House UI tab** — room list + element cards + add forms (`HousePanel.svelte`)~~ ✓
3. ~~**House persistence** — `GET /house` on mount, Save button + dirty indicator in nav~~ ✓
4. ~~**Room dimensions** — replace single `volume` field with `a × b × c` inputs; volume computed~~ ✓
5. **UA summary bar chart** — per-element `UA = a*b/R_total` [W/K] computed in JS
   (ISO 6946: `R = 1/h_i + Σ d/λ + 1/h_e`); horizontal bars, color by kind;
   shows which element dominates heat loss. No backend needed.
6. **Material library extension** — add `category` field; add `brique_creuse`,
   `stone_rubble`, `lime_plaster`, `wood_floor`, `tile_clay`, `concrete_slab`
7. **`solver/physics.py`** — `expand(house) -> (rc_model, expansion_map)`
   for `opaque` and `glazing` first; unit tests vs hand calcs
8. **Wire into `assemble()`** as transparent pre-pass; existing RC studies
   unchanged
9. **Add `room` + `air_exchange` kinds** — completes the physics
10. **Per-element heat-flow view** in Run tab — `Q_element(t) = ΔT / R_total`,
    bar chart "which surface dominates?". First payoff.
11. **Fit param keys in physical form** — `mur_SE.layers[0].lambda`,
    `materials.brick_full.lambda`. Update `_patch_model()` in `fit.py` to
    re-run `expand()` after patching.
12. **Per-element fit badges** — element cards show fitted λ ± σ, click for
    prior vs posterior.

### R/UA computation — JS vs Python

The `R_total` formula (`1/h_i + Σ d/λ + 1/h_e`, ISO 6946) is stable enough to
implement in JS for display without risk of meaningful drift from the Python
solver. A shared API endpoint only makes sense once `physics.py` handles
non-trivial cases (thermal bridges, non-uniform layers).

### Fit result persistence (folds in here)

Save fitted values back into the study JSON under `"fit_result"` (method,
timestamp, cost, `{param_key: {fitted, sigma}}`). "Promote to priors" action:
takes `fit_result.params`, sets `nominal = fitted`, tightens `sigma_log`,
writes into `params`. Lets you fit on summer data and reuse as tight priors
on winter data.

API additions:
- `POST /studies/{id}/save_fit`
- `GET  /studies/{id}/fit_result`
- `POST /studies/{id}/promote_priors`

---

## Backlog (not committed)

- **House UI v2** — 2D floor-plan-ish canvas (rooms as rectangles, walls as
  edges). Much more work, much more intuitive. Layer on top of v1 only if v1
  proves too tedious.
- **LLM-assisted model builder** — user fills `house.json` with room
  descriptions; LLM reads `house.json` + material library → generates an
  initial study JSON.
- **MCMC corner plot** — marginal histograms per param.
- **Construction picker on edges** — populate R from material library.
- **Material library browser panel.**
- **Cross-room studies** — currently each study is one room. Multi-room with
  shared `materials` is natural once the physics layer is in.
- **`GET /materials`** endpoint.
- **Clean up legacy fields** in example study JSONs (`T_source`, `signal` on
  boundary/source nodes — solver ignores them).

---

## Changelog

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
