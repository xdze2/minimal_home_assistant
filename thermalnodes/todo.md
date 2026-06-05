# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: schema + data library + Svelte graph viewer done

---

## Step 1 — Examples (validate the schema)

- [x] `data/examples/chambre_1r1c.json` — single room node, one resistance to exterior boundary,
      one solar heat source.
- [ ] `data/examples/chambre_2r2c.json` — add a ceiling_mass node between the room air and exterior
      (roof node). Two resistances, two capacitances.
- [ ] Validate examples against the schemas:
      ```bash
      uv run check-jsonschema --schemafile schema/model.schema.json data/examples/chambre_1r1c.json
      ```

---

## Step 2 — Material library

- [x] `data/materials/` — 7 materials (stone_calcaire, brick_full, concrete_heavy, wood_frame,
      plaster, air_gap, glass_wool)

---

## Step 3 — Python solver

Use `uv` for all Python package management:
```bash
uv add scipy fastapi uvicorn
uv run pytest
uv run uvicorn api.main:app --reload
```

`solver/assemble.py`
- [ ] `assemble(model) -> (A, B, node_ids)` — build state-space matrices:
      - A [NxN]: weighted graph Laplacian × C⁻¹
      - B [NxM]: input matrix for boundary temps + heat sources
- [ ] Unit test: 1R1C analytical solution — step change in T_ext, verify τ = R·C

`solver/simulate.py`
- [ ] `simulate(model, inputs, t_eval) -> dict[node_id, array]`
      - `inputs`: dict of signal_name → interpolated timeseries
      - calls `scipy.integrate.solve_ivp(method='BDF')`
- [ ] Unit test: 1R1C step response matches analytical e^(-t/RC)
- [ ] Unit test: 2R2C two-node system, verify equilibrium temperature

---

## Step 4 — FastAPI backend

`api/main.py`
- [ ] `POST /simulate` — body: `{model: {...}, inputs: {...}}`, returns `{t: [...], nodes: {id: [...]}}`
- [ ] `GET /materials` — list available material ids + names
- [ ] `GET /assemblies` — list available assembly ids + names
- [ ] `GET /assembly/{id}/compute?area=12.0` — return computed R and C for a given area
- [ ] CORS enabled (Svelte dev server on different port)
- [ ] Serve static inputs (Open-Meteo CSV stub) for demo

---

## Step 5 — Svelte UI

`ui/` — SvelteKit + `@xyflow/svelte`.

### Graph viewer (done)
- [x] Scaffold SvelteKit project, install `@xyflow/svelte`
- [x] Node types: Room (air/mass), Boundary, HeatSource — custom Svelte components
- [x] Resistance edges + animated heat-flow arrows
- [x] `modelToFlow.js` — converts model JSON → Svelteflow nodes/edges
- [x] Loads `chambre_1r1c.json` and renders it with fitView, Controls, MiniMap

### Graph editor (next)
- [ ] Click node/edge → side panel showing properties
- [ ] Edit label, numeric R/C values in the side panel
- [ ] Add node from palette (Room, Boundary, HeatSource)
- [ ] Draw edge by dragging between handles
- [ ] Delete selected node/edge (keyboard Delete)
- [ ] Serialize canvas state → model JSON
- [ ] Load model JSON from file (drag-and-drop or file picker)

### Simulation panel
- [ ] Install uPlot
- [ ] Date range picker (start / end)
- [ ] "Simulate" button → POST /simulate
- [ ] uPlot: temperature timeseries per room node + outdoor temperature overlay

### Nice to have (post-MVP)
- [ ] Construction picker dropdown on edges (populates R from `/assembly/{id}/compute`)
- [ ] Material library browser panel
- [ ] Export model JSON button
- [ ] "Open in Falstad" button — generate Falstad URL from netlist

---

## Schema

- **material**: bulk physical constants (λ, ρ, cp) — used for reference, not loaded by solver
- **model**: R and C are direct numeric values [K/W] and [J/K] — compute them from material
  properties outside the model file (e.g. R = (R_si + e/λ + R_se) / area)

## Decisions made

- **Solver**: `scipy.integrate.solve_ivp` (BDF method for stiffness). Not ngspice.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
  Each physical block maps to circuit primitives under the hood.
- **R and C**: direct numeric values only. Compute from material properties before writing the model.
- **Boundaries**: fixed-temperature nodes (exterior air, deep soil at 12°C). Not solved,
  used as forcing inputs only.
- **Heat sources**: arrow from HeatSourceNode → Room node in the graph (not just side-panel
  metadata), to make the signal→node dependency explicit.
- **Thick walls / MVP**: not in scope. A wall is a single R edge. Internal mass node (2R1C
  wall) is v2.
- **Fitting / Bayesian inference**: out of scope for thermalnodes. Lives in parent miniha
  project. thermalnodes models will be consumed as topology descriptions there.

---

## Context for next session

- Schema files: `thermalnodes/schema/`
- Data library: `thermalnodes/data/` (materials, examples)
- UI entry point: `thermalnodes/ui/src/routes/+page.svelte`
- `@data` alias in `ui/vite.config.js` resolves to `thermalnodes/data/` — import any JSON directly
- Next UI task: side panel for editing selected node/edge properties (Step 5 graph editor)
- Parent project `miniha` has existing solver code in `miniha/th_models/` — reuse physics
  intuition, don't couple code directly
- For the MVP demo use Open-Meteo CSV for forcing inputs — avoid InfluxDB dependency
