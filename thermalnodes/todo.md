# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: schema done, nothing else built yet

---

## Step 1 — Examples (validate the schema)

- [ ] `examples/chambre_1r1c.json` — single room node, one resistance to exterior boundary,
      one solar heat source. The minimal working model. Use this to shake out schema issues.
- [ ] `examples/chambre_2r2c.json` — add a ceiling_mass node between the room air and exterior
      (roof node). Two resistances, two capacitances.

Validate examples against the schemas:
```bash
uv add check-jsonschema
uv run check-jsonschema --schemafile schema/model.schema.json examples/chambre_1r1c.json
```

---

## Step 2 — Material + assembly library

Small hand-curated library for common French old-building materials.

- [ ] `materials/stone_calcaire.json` — λ=1.7, ρ=2200, cp=900 (ISO 10456)
- [ ] `materials/brick_full.json` — λ=0.8, ρ=1800, cp=840
- [ ] `materials/concrete_heavy.json` — λ=2.0, ρ=2400, cp=880
- [ ] `materials/wood_frame.json` — λ=0.13, ρ=500, cp=1600
- [ ] `materials/plaster.json` — λ=0.57, ρ=1200, cp=1000
- [ ] `materials/air_gap.json` — λ=0.18 (unventilated, ISO 6946), ρ=1.2, cp=1005
- [ ] `materials/glass_wool.json` — λ=0.035, ρ=15, cp=840 (thickness is set per assembly layer)

- [ ] `assemblies/wall_pierre_40cm.json`
- [ ] `assemblies/wall_brique_22cm.json`
- [ ] `assemblies/roof_beton_sous_tuile.json`
- [ ] `assemblies/dalle_beton_sol.json` (slab on grade)
- [ ] `assemblies/fenetre_double_vitrage.json` — no layers, direct U=1.4 W/m²K (glass is opaque to IR, different physics)

### Construction library (assembly + orientation + surface films)

Sits between assembly and model edges. R_si / R_se defaults from ISO 6946 by orientation.

- [ ] `constructions/wall_vertical_pierre_40cm.json` — assembly: wall_pierre_40cm, orientation: vertical
- [ ] `constructions/wall_vertical_brique_22cm.json`
- [ ] `constructions/roof_horizontal_up_beton.json` — orientation: horizontal_up (R_si=0.10)
- [ ] `constructions/floor_horizontal_down_dalle.json` — orientation: horizontal_down (R_si=0.17)
- [ ] `constructions/window_vertical_double.json`

---

## Step 3 — Python solver

Use `uv` for all Python package management (consistent with parent miniha project):
```bash
uv add scipy fastapi uvicorn
uv run pytest
uv run uvicorn api.main:app --reload
```

`solver/assemble.py`
- [ ] Load and resolve a model JSON: replace `{assembly_id, area}` references with computed R or C values
      (requires loading the referenced assembly + material files)
- [ ] `assemble(model) -> (A, B, node_ids)` — build state-space matrices from the graph:
      - A [NxN]: weighted graph Laplacian × C⁻¹  (conductances between nodes)
      - B [NxM]: input matrix mapping boundary temps + heat sources into each node equation
- [ ] Unit test: 1R1C analytical solution — step change in T_ext, verify τ = R·C

`solver/simulate.py`
- [ ] `simulate(model, inputs, t_eval) -> dict[node_id, array]`
      - `inputs`: dict of signal_name → interpolated timeseries (pandas Series or numpy array)
      - calls `scipy.integrate.solve_ivp(method='BDF')`
      - returns temperature trajectory per node
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
- [ ] Serve static inputs (Open-Meteo CSV / InfluxDB stub) for demo

---

## Step 5 — Svelte UI

`ui/` — Svelte app with Svelteflow for the graph canvas.

- [ ] Scaffold Svelte project (`npm create svelte@latest ui`)
- [ ] Install Svelteflow (`npm install @xyflow/svelte`)
- [ ] Install uPlot

### Graph editor
- [ ] Node types: Room (capacitance node), Boundary (fixed T), HeatSource
- [ ] Edge type: Wall/resistance (R value or assembly picker)
- [ ] Side panel: edit selected node/edge properties
- [ ] Serialize canvas state → model JSON (matching model.schema.json)
- [ ] Load model JSON → restore canvas state

### Simulation panel
- [ ] Date range picker (start / end)
- [ ] "Simulate" button → POST /simulate
- [ ] uPlot result: temperature timeseries per node, one series per room
- [ ] Show outdoor temperature on the same plot (secondary axis or overlay)

### Nice to have (post-MVP)
- [ ] Assembly picker dropdown (populates R from `/assembly/{id}/compute`)
- [ ] Material library browser
- [ ] Export model JSON button
- [ ] "Open in Falstad" button — generate Falstad URL from netlist for circuit debugging

---

## Schema hierarchy

```
material  →  assembly  →  construction  →  edge (in model)
(λ,ρ,cp)    (layer stack)  (assembly +      (construction_id +
                            orientation +    area + from/to)
                            R_si, R_se)
```

- **material**: bulk physical constants only, no geometry
- **assembly**: ordered layer stack, purely `sum(e/λ)` — no surface films, no area
- **construction**: assembly + orientation + R_si/R_se (ISO 6946 defaults by orientation).
  This is what an edge references.
- **edge**: construction_id + area → R [K/W] = (R_si + sum(e/λ) + R_se) / area
- Node C derivation uses `assembly_id` directly (areal mass is orientation-independent)

## Decisions made

- **Solver**: `scipy.integrate.solve_ivp` (BDF method for stiffness). Not ngspice.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
  Each physical block maps to circuit primitives under the hood.
- **R and C**: accept either a direct numeric value or `{assembly_id, area}` — derived from
  material stack at solve time. Both paths supported by the schema.
- **Boundaries**: fixed-temperature nodes (exterior air, deep soil at 12°C). Not solved,
  used as forcing inputs only.
- **Thick walls / MVP**: not in scope. A wall is a single R edge. Internal mass node (2R1C
  wall) is v2.
- **Fitting / Bayesian inference**: out of scope for thermalnodes. Lives in parent miniha
  project. thermalnodes models will be consumed as topology descriptions there.

---

## Context for next session

- Schema files are in `thermalnodes/schema/`
- Parent project `miniha` has existing solver code in `miniha/th_models/` (1R1C, sliding
  window fits) — reuse physics intuition, don't couple code directly
- Existing sensor data is in InfluxDB; for the MVP demo use Open-Meteo CSV or a stub JSON
  for forcing inputs — avoid InfluxDB dependency in thermalnodes
