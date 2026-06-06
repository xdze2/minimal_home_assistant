# thermalnodes

Tool for building and simulating thermal RC networks of buildings, room by room.
Draw the topology on a node-graph canvas, assign signals from InfluxDB, run the
forward simulation, and eventually fit model parameters to sensor data.

## Concept

A building room is modelled as an RC circuit:

| Building element | Circuit equivalent |
|---|---|
| Room air mass | Capacitor C [J/K] |
| Wall / insulation | Resistor R [K/W] |
| Outdoor temperature | Fixed-temperature boundary |
| Solar gain | Heat source (W) |

The assembled system is a linear ODE: `Ċ·dT/dt = A·T + B·u`.
Two solvers are available: `solve_ivp(BDF)` for exploration and ZOH (matrix
exponential) for speed-critical use cases like parameter fitting.

## Stack

| Layer | Choice |
|---|---|
| Model + study format | JSON |
| Solver | Python — `scipy` (IVP/BDF + ZOH) |
| Data source | InfluxDB (via `GET /signals`, `GET /series`) |
| API | FastAPI (port 8001) |
| UI | SvelteKit + `@xyflow/svelte` + uPlot |

## Running

### API

```bash
uv run uvicorn thermalnodes.api.main:app --reload --port 8001
```

### UI

```bash
cd thermalnodes/ui
npm install        # first time only
npm run dev        # http://localhost:5173
```

## UI layout

```
┌──────────────┬──────────────────────────────────────────┐
│ miniha       │                                          │
│ Home         │  Home: study browser (card grid)         │
│ ──────────── │  or active tab content                   │
│ study_id     │                                          │
│   Topology   │                                          │
│   Inputs     │                                          │
│   Run        │                                          │
│   Fit        │                                          │
│ ──────────── │                                          │
│  [Save]      │                                          │
└──────────────┴──────────────────────────────────────────┘
```

- **Home** — card grid of all studies (examples + user), click to open, ⎘ to duplicate
- **Topology** — node-graph editor (`@xyflow/svelte`) + properties panel (right); no top
  bar — model notes shown in the properties panel when nothing is selected
- **Inputs** — date range, solver selector, signal assignment per boundary/source node,
  inline uPlot preview per signal
- **Run** — Fetch inputs + Run simulation buttons, results charts (inputs + temperatures),
  solver metadata
- **Fit** — placeholder (step 6)

Save is always pinned at the bottom of the left nav, visible regardless of nav height.

## Study schema

Each study is a self-contained JSON file under `data/user/studies/{id}.json`:

```json
{
  "id":           "chambre_jan_2024_2r1c",
  "label":        "Chambre — jan 2024 — 2R1C",
  "room":         "chambre",
  "model":        { "...topology..." },
  "start":        "2024-01-01",
  "end":          "2024-02-01",
  "inputs":       { "exterior": "open_meteo/temperature_2m" },
  "observations": { "chambre": "zigbee2mqtt/temperature?name=chambre" },
  "solver":       "zoh"
}
```

Read-only seed studies live in `data/examples/`.

## Signal name convention

```
measurement/field               # e.g. open_meteo/temperature_2m
measurement/field?tag=value     # e.g. zigbee2mqtt/temperature?name=salon
```

Signals are stored in the study `inputs` map (node id → signal name), not in the
model topology. This keeps the graph reusable across different time ranges and sensors.

## Project structure

```
thermalnodes/
  schema/                       JSON schemas (v0.3)
  data/
    house.json                  house metadata + sensor defaults
    materials/                  7 materials (λ, ρ, cp)
    examples/                   read-only seed studies
    user/studies/               {id}.json per user study
  solver/
    assemble.py                 graph → AssembledSystem (A, B matrices)
    simulate.py                 simulate_ivp + simulate_zoh + simulate_mock
    tests/
  api/
    main.py                     FastAPI app (studies, signals, simulate/*)
    influx.py                   InfluxDB client
    config.py                   env-based config (MINIHA_INFLUX_* vars)
  ui/
    src/
      routes/+page.svelte       app shell — home view + left nav + tab content
      lib/GraphView.svelte      SvelteFlow canvas
      lib/PropertiesPanel.svelte node/edge inspector + add/delete
      lib/InputsPanel.svelte    date range + solver + signal assignment + preview
      lib/SimulationRun.svelte  fetch/run buttons + results charts
      lib/modelToFlow.js        model JSON → SvelteFlow nodes/edges
```
