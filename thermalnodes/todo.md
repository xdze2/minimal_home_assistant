# thermalnodes — implementation todo

See README.md for project description and stack overview.

## Status: schema + data library + Svelte graph viewer done

---

## Step 1 — Examples (validate the schema)

- [x] `data/examples/chambre_1r1c.json` — single room node, one resistance to exterior boundary,
      one solar heat source.
- [x] `data/examples/chambre_v1.json` — full chambre: 2 mass nodes (chambre, mur_SE), 5 resistance
      nodes (R_wall_SE_ext/int, R_roof, R_walls_ins, R_win_SE/NE), 2 source nodes, 1 boundary.

---

## Step 2 — Material library

- [x] `data/materials/` — 7 materials (stone_calcaire, brick_full, concrete_heavy, wood_frame,
      plaster, air_gap, glass_wool)

---

## Step 3 — Python solver

Use `uv` for all Python package management:

```bash
uv add scipy numpy pytest
uv run pytest thermalnodes/solver/tests/
```

### 3a — Graph → state-space assembly (`solver/assemble.py`)

The schema stores resistance as _nodes_ connected by plain edges (schema v0.3).
Assembly eliminates resistance nodes by condensing the conductance network:
for each resistance node (exactly 2 edges), replace with a direct conductance
G = 1/R between its two neighbours.

- [x] `assemble(model) -> AssembledSystem`
  - Parse node kinds: `mass` (state), `boundary` (forced), `resistance` (wire),
    `source` (heat injection).
  - Build conductance adjacency: for each resistance node between nodes A and B,
    add G = 1/R to the weighted graph between A and B. Series resistances
    (R node → R node) fold transitively (sum of R values before inverting).
  - Build state-space matrices for mass nodes only:
    - `A` [n×n]: graph Laplacian weighted by G, scaled by C⁻¹
      `A[i,i] = -sum_j(G_ij) / C_i`, `A[i,j] = G_ij / C_i`
    - `B_boundary` [n×n_b]: coupling to boundary nodes
      `B[i,k] = G_{i,boundary_k} / C_i`
    - `B_source` [n×n_s]: heat source injection
      `B[i,s] = gain_s / C_i` if source s is wired to mass i
  - Returns: `AssembledSystem(A, B_boundary, B_source, mass_ids, boundary_ids, source_ids)`
- [x] **Verify**: for `chambre_1r1c.json` → 1×1 A matrix, τ = -1/A[0,0] matches R·C.
- [x] **Verify**: for `chambre_v1.json` → 2×2 A matrix (chambre + mur_SE).
      Check: eigenvalues give two τ values consistent with expected fast (~7 h) and
      slow (~38 h) modes, well-separated (ratio > 5×). Note: τ_slow ≈ 38 h (not
      ~112 h) because parallel paths through roof/windows/insulated walls also drain
      the wall node.

### 3b — Forward simulation (`solver/simulate.py`)

**Integrator choice:**

- `scipy.integrate.solve_ivp(method='BDF')` — general purpose, handles stiffness
  from the large C ratio (mur_SE ≈ 8 MJ/K vs chambre ≈ 270 kJ/K, ~30× stiffness).
  Good for exploratory use and non-uniform input signals.
- **ZOH (matrix exponential)** — exact solution for piecewise-constant inputs on
  a uniform grid: `x[k+1] = expm(A·dt)·x[k] + A⁻¹·(expm(A·dt)-I)·B·u[k]`.
  Preferred for optimisation / MCMC because it is O(n³) once per dt change
  (precompute `expm(A·dt)` and `A⁻¹·(expm(A·dt)-I)·B`), then O(n²) per step.
  No step-size tuning, differentiable w.r.t. parameters via `jax.scipy.linalg.expm`
  or finite differences.

Implement both; use BDF for first correctness tests, ZOH for optimisation.

- [ ] `simulate_ivp(system, inputs, t_eval) -> SimResult`
  - `inputs`: `dict[signal_name, (t_array, values_array)]` — interpolated at
    ODE evaluation times via `scipy.interpolate.interp1d`.
  - Calls `solve_ivp(fun, t_span, y0, method='BDF', t_eval=t_eval, ...)`.
  - Returns `SimResult(t, temps)` where `temps` is `dict[mass_id, array]`.
- [ ] `simulate_zoh(system, inputs_uniform, dt) -> SimResult`
  - `inputs_uniform`: `dict[signal_name, array]` on a uniform grid of step `dt`.
  - Precomputes `Ad = expm(A·dt)`, `Bd = A⁻¹·(Ad - I)·B`.
  - Loops: `x[k+1] = Ad @ x[k] + Bd @ u[k]`.
- [ ] **Verify** (unit test): `chambre_1r1c.json`, step change T_ext 0→10°C, zero solar,
      IVP and ZOH both match `T(t) = 10·(1 - exp(-t/τ))` to < 0.01 °C at t=τ.
- [ ] **Verify** (unit test): `chambre_v1.json`, constant T_ext=0, zero solar, T0=[20,20],
      both methods converge to T=0 with two exponential modes; check τ values match
      eigenvalues of A.

### 3c — Stub inputs for demo (`solver/inputs.py`)

- [ ] `make_stub_inputs(start, end, dt_minutes) -> dict[signal_name, (t, values)]`
  - Synthesises 2 months of plausible outdoor temperature (sinusoidal daily + seasonal)
    and solar irradiance (clear-sky model, flat-plate).
  - Used as a self-contained demo without Open-Meteo dependency.
- [ ] **Verify**: run `simulate_ivp` on `chambre_v1.json` with stub inputs for
      2026-03-29 to 2026-05-29; plot chambre and mur_SE temperatures; visually
      check chambre lags exterior by ~τ_fast, mur_SE by ~τ_slow.

---

## Step 4 — FastAPI backend

`api/main.py`

- [ ] `POST /simulate` — body: `{model: {...}, inputs: {...}}`, returns `{t: [...], nodes: {id: [...]}}`
- [ ] `GET /materials` — list available material ids + names
- [ ] CORS enabled (Svelte dev server on different port)
- [ ] Serve stub inputs (synthesised CSV) for demo

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
- [ ] uPlot: temperature timeseries per mass node + outdoor temperature overlay

### Nice to have (post-MVP)

- [ ] Construction picker dropdown on edges (populates R from `/assembly/{id}/compute`)
- [ ] Material library browser panel
- [ ] Export model JSON button

---

## Step 6 — Parameter optimisation and Bayesian MCMC (parent project)

These live in `miniha/` and consume `thermalnodes` models as topology descriptions.
The ZOH simulator (Step 3b) is the key building block.

- [ ] Wrap `simulate_zoh` as a callable `f(params) -> T_chambre_array` for a fixed
      model topology; params = log-space {R values, C values, gain values}.
- [ ] Scipy optimisation: `least_squares(f(params) - T_obs, ...)` — output-error NLS.
      Warm-start from `assemble` nominal values.
- [ ] MCMC: `blackjax` or `emcee` sampler on the same log-likelihood.
      Prior: log-normal on each R and C (±50% of nominal), flat on gains.
      **Why ZOH is critical here**: each likelihood evaluation integrates N timesteps;
      BDF would be 10–100× slower per call.

---

## Schema

- **material**: bulk physical constants (λ, ρ, cp) — used for reference, not loaded by solver
- **model**: R and C are direct numeric values [K/W] and [J/K] — compute them from material
  properties outside the model file (e.g. R = (R_si + e/λ + R_se) / area)
- **resistance nodes**: eliminated during assembly — they do not appear in the state vector

## Decisions made

- **Solver**: two-track: `scipy.integrate.solve_ivp(BDF)` for correctness/exploration,
  ZOH (matrix exponential, `scipy.linalg.expm`) for optimisation/MCMC.
  RK4 is not used: too slow for the ~30× stiffness ratio in `chambre_v1`.
- **Node vocabulary**: physical (Room, Wall, Boundary) not circuit primitives (R, C, V).
  Each physical block maps to circuit primitives under the hood.
- **R and C**: direct numeric values only. Compute from material properties before writing the model.
- **Boundaries**: fixed-temperature nodes (exterior air, deep soil at 12°C). Not solved,
  used as forcing inputs only.
- **Heat sources**: arrow from HeatSourceNode → Room node in the graph (not just side-panel
  metadata), to make the signal→node dependency explicit.
- **Thick walls / MVP**: a wall is a 2R1C block (R_ext, mass, R_int). Already in chambre_v1.
- **Fitting / Bayesian inference**: planned in Step 6. Solver design (ZOH) is chosen to
  support this from the start.

---

## Context for next session

- Schema files: `thermalnodes/schema/`
- Data library: `thermalnodes/data/` (materials, examples)
- UI entry point: `thermalnodes/ui/src/routes/+page.svelte`
- `@data` alias in `ui/vite.config.js` resolves to `thermalnodes/data/` — import any JSON directly
- Next solver task: implement `solver/assemble.py` (Step 3a)
- Parent project `miniha` has existing ZOH + matrix-exp solver in `miniha/th_models/fit_2r2c.py` —
  reuse the `_build_AB`, ZOH logic; don't couple code directly
- For the MVP demo use synthesised stub inputs — avoid InfluxDB / Open-Meteo dependency
