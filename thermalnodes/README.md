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

## Project structure

```
thermalnodes/
  schema/
    material.schema.json      # physical constants for one material
    assembly.schema.json      # layer stack → U-value, areal mass
    model.schema.json         # full topology: nodes, edges, boundaries, sources
  examples/
    chambre_1r1c.json         # single room, 1 resistance, 1 capacitance
    chambre_2r2c.json         # room + ceiling mass node
  solver/
    assemble.py               # graph → (A, B) state-space matrices
    simulate.py               # solve_ivp wrapper → timeseries
  api/
    main.py                   # FastAPI /simulate endpoint
  ui/
    ...                       # Svelte app
```

## MVP scope

- Forward simulation only (no parameter fitting, no Bayesian inference)
- Physical node vocabulary: Room, Wall, Window, Boundary, HeatSource
- Time-varying forcing: outdoor temperature + solar irradiance timeseries
- Result: indoor temperature timeseries per room node

Fitting and Bayesian inference live in the parent `miniha` project and will
consume thermalnodes models as their topology description.
