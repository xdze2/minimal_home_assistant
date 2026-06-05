# thermalnodes

A fun demo tool for building and simulating thermal RC networks of buildings.

Draw rooms, walls, windows and boundaries on a node-graph canvas — the tool
assembles the equivalent RC circuit and runs a forward thermal simulation.

## Concept

A building is modelled as an electrical circuit:

| Building | Circuit |
|----------|---------|
| Room air mass | Capacitor (C) |
| Wall / insulation | Resistor (R) |
| Outdoor temperature | Voltage source |
| Solar gain | Current source |
| Infinite soil | Fixed voltage source |

The user places **physical blocks** (rooms, walls, windows) on a canvas.
Under the hood each block maps to circuit primitives. The assembled system
is a linear ODE solved by `scipy.integrate.solve_ivp`.

## Stack

| Layer | Choice |
|-------|--------|
| Model format | JSON + JSON Schema |
| Solver | Python — `scipy.integrate.solve_ivp` (BDF) |
| API | FastAPI |
| UI | Svelte + Svelteflow (node-graph canvas) |
| Plots | uPlot |

## Usage

### UI (graph editor)

```bash
cd ui
npm install       # first time only
npm run dev       # dev server at http://localhost:5173
```

### API (Python solver) — not yet implemented

```bash
uv run uvicorn api.main:app --reload   # http://localhost:8000
```

### Validate a model against the schema

```bash
uv add check-jsonschema
uv run check-jsonschema --schemafile schema/model.schema.json data/examples/chambre_1r1c.json
```

## Project structure

```
thermalnodes/
  schema/
    material.schema.json      # physical constants for one material
    model.schema.json         # full topology: nodes, edges, boundaries, sources
  data/
    materials/                # curated material library (λ, ρ, cp)
    examples/
      chambre_1r1c.json       # single room, 1 resistance, 1 solar source
  solver/
    assemble.py               # graph → (A, B) state-space matrices
    simulate.py               # solve_ivp wrapper → timeseries
  api/
    main.py                   # FastAPI /simulate endpoint
  ui/
    src/
      lib/
        modelToFlow.js        # model JSON → Svelteflow nodes/edges
        nodes/                # RoomNode, BoundaryNode, HeatSourceNode
      routes/
        +page.svelte          # main canvas page
```

## MVP scope

- Forward simulation only (no parameter fitting, no Bayesian inference)
- Physical node vocabulary: Room, Wall, Window, Boundary, HeatSource
- Time-varying forcing: outdoor temperature + solar irradiance timeseries
- Result: indoor temperature timeseries per room node

Fitting and Bayesian inference live in the parent `miniha` project and will
consume thermalnodes models as their topology description.
