# Modeling pipeline

How a physical description of a house becomes a fittable RC model.

This is a **design document** for the layered pipeline. Current code implements
parts of it (notably layer 1 + a degenerate version of layers 2–3); the goal
here is to spell out the target architecture, the data objects at each layer,
and the function signatures that connect them.

For the high-level project overview see [project_description.md](project_description.md).

---

## The four layers

```
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 1 — Full physical model                                        │
│   user-facing: rooms, walls, layers, materials, geometry             │
│   data:        house JSON                                            │
└──────────────────────────────────────────────────────────────────────┘
                              │  expand()
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 2a — Full RC graph                                             │
│   internal:    every R, every C produced by expand()                 │
│   data:        FullRCGraph (one R per wall layer, etc.)              │
└──────────────────────────────────────────────────────────────────────┘
                              │  reduce()        (lossless rewrites)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 2b — Reduced RC graph                                          │
│   internal:    minimal equivalent graph (series/parallel merged,     │
│                pure-resistor junctions eliminated)                   │
│   data:        ReducedRCGraph, with provenance back to FullRCGraph   │
└──────────────────────────────────────────────────────────────────────┘
                              │  compile_mapping(reduction_spec)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 3 — Reduced physical model (φ-space)                           │
│   user-facing: physical parameters with priors                       │
│   data:        ReductionSpec + Mapping                               │
│                e.g. (R_wall_SE, C_wall_SE) or one R_ext_chambre      │
└──────────────────────────────────────────────────────────────────────┘
                              │  forward (φ → values for ReducedRCGraph)
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Layer 4 — Solver (θ-space)                                           │
│   internal:    AssembledSystem (A, B matrices), simulate, fit        │
└──────────────────────────────────────────────────────────────────────┘
```

The crucial distinction: **layer 2b (reduced RC graph) and layer 3 (reduced
physical model) are not the same object.**

- Layer 2b is a *graph* — what the solver sees after lossless simplification.
- Layer 3 is a *set of physical parameters with priors* — what the user
  declares as "the things I want to fit." A heavy wall in layer 2b is one
  R + one C; in layer 3 it might be 2 physical params `(R_wall, C_wall)`, or
  1 effective param `R_ext_room` shared with other elements, or 0 (fixed).

Layer 3 is a **modeling choice** that sits on top of layer 2b. The same
reduced graph can be parameterized many ways.

---

## Layer 1 — Full physical model

**Source of truth.** All other layers are derived.

Already documented in [project_description.md](project_description.md). House JSON
with `elements` (rooms, walls, windows, air exchanges) and material references.

```python
# Data: data/houses/<name>.json
# Loaded as: dict (or future House dataclass)
```

---

## Layer 2a — Full RC graph

Pure function from the full physical model. No I/O, no priors, no fit concerns.

### Function

```python
def expand(house: dict, materials: MaterialLibrary) -> tuple[FullRCGraph, ExpansionMap]:
    """
    Translate physical elements into the full RC graph.

    Each element produces a fixed set of nodes/edges with provenance
    annotations so later layers can trace reduced quantities back to
    their physical origin.
    """
```

### Data

```python
@dataclass
class FullRCEdge:
    id: str
    u: NodeId
    v: NodeId
    kind: Literal["R"]
    value: float                      # initial / prior-mean value
    source: ElementRef                # which house element produced this
    role: Literal["surface", "layer", "glazing", "air_exchange"]
    # for layer edges:
    layer_index: int | None = None    # which layer of the wall
    material: str | None = None

@dataclass
class FullRCNode:
    id: NodeId
    kind: Literal["mass", "boundary"]
    C: float | None                   # mass nodes only
    source: ElementRef
    role: Literal["room_air", "wall_internal", "outdoor", "ground"]

@dataclass
class FullRCGraph:
    nodes: list[FullRCNode]
    edges: list[FullRCEdge]

# ExpansionMap: house_element_id → list of (node_id | edge_id) it produced
ExpansionMap = dict[str, list[str]]
```

### Example

A 2-layer opaque wall with chain_n = 5 produces:
- 2 boundary surface R's (R_se, R_si)
- 5 internal layer R's (one per lump, value depends on which layer it falls in)
- 5 internal C's (one per lump)
- 4 internal mass nodes between adjacent R's (the two end nodes are room/outdoor)

Each carries provenance: `source = ElementRef("mur_SE")`, layer index, material.

---

## Layer 2b — Reduced RC graph

Lossless graph rewrites. Output is the minimal equivalent network for the
solver. Provenance is preserved so layer 3 knows how to recompute each reduced
quantity from the originals.

### Function

```python
def reduce_graph(full: FullRCGraph) -> ReducedRCGraph:
    """
    Apply lossless rewrites until no more rules fire:
      1. series-R:        eliminate pure-junction node between two R's
      2. parallel-R:      merge parallel R's between same node pair
      3. mass-R-cluster:  collapse a chain of R's flanking a single C
                          (heavy wall: N internal C's → 1 C, surrounding R's
                          → 1 R) — only if all C's share the same φ scope

    Returns a ReducedRCGraph where each edge/node carries the formula and
    contributor list from the original FullRCGraph.
    """
```

### Data

```python
@dataclass
class ReducedEdge:
    id: str
    u: NodeId
    v: NodeId
    kind: Literal["R"]
    contributors: list[str]           # FullRCEdge ids
    formula: ReductionFormula         # how to recompute value from contributors
    value: float                      # current value (filled by Mapping)

@dataclass
class ReducedNode:
    id: NodeId
    kind: Literal["mass", "boundary"]
    contributors: list[str]           # FullRCNode ids (mass) or single boundary id
    formula: ReductionFormula | None  # e.g. "sum(C_i)" for merged mass
    C: float | None

@dataclass
class ReductionFormula:
    op: Literal["series", "parallel", "sum", "identity"]
    # The actual recompute is a small closure built at reduce time.
    apply: Callable[[list[float]], float]

@dataclass
class ReducedRCGraph:
    nodes: list[ReducedNode]
    edges: list[ReducedEdge]
```

### Algorithm (pseudo)

```python
def reduce_graph(full):
    g = to_working_graph(full)        # mutable view; each edge/node = singleton contributor list
    while True:
        changed = False
        changed |= apply_series_R(g)
        changed |= apply_parallel_R(g)
        changed |= apply_mass_chain_collapse(g)
        if not changed:
            break
    return freeze(g)
```

Rewrites combine contributor lists and compose formulas:

```python
# series-R between edges e1 (R_a) and e2 (R_b):
new_edge.contributors = e1.contributors + e2.contributors
new_edge.formula      = ReductionFormula("series", lambda vs: sum(vs))

# parallel-R between edges e1, e2:
new_edge.contributors = e1.contributors + e2.contributors
new_edge.formula      = ReductionFormula("parallel", lambda vs: 1 / sum(1/v for v in vs))
```

A 5-lump heavy wall with uniform material reduces to **one R edge + one C
node** between the two zone nodes, with the R edge carrying all 6 original R
ids as contributors and a series-sum formula.

---

## Layer 3 — Reduced physical model

The user-facing layer. Declares the physical parameters φ to fit, their
priors, and how each φ relates to the underlying full physical quantities.

### Concepts

A **physical parameter** φ_i has:
- A **name** (e.g. `mur_SE.R`, `R_ext_chambre`, `lambda_brick`).
- A **mode**:
  - `"derived"` — value computed from layer-1 quantities by a known formula
    (e.g. `R_wall = R_se + Σ d_i/(λ_i·A) + R_si`). The user may fit it or fix it.
  - `"effective"` — declared as a single number standing in for an aggregate
    (e.g. one R for a whole room envelope). Layer 1 provides only a prior.
  - `"fixed"` — held constant during fit.
- A **scope**: which full-graph edges/nodes it controls.
- A **prior** (required if free): log-normal, uniform, or improper-flat.
- A **target**: which reduced-graph edge/node values it contributes to.

### Data

```python
@dataclass(frozen=True)
class Prior:
    kind: Literal["fixed", "lognormal", "uniform", "flat"]
    value: float | None = None
    mu: float | None = None        # lognormal: log-space mean
    sigma: float | None = None
    low: float | None = None
    high: float | None = None

@dataclass(frozen=True)
class PhiSpec:
    name: str
    mode: Literal["derived", "effective", "fixed"]
    scope: list[str]               # FullRC edge/node ids covered by this φ
    target: list[str]              # ReducedRC edge/node ids it contributes to
    prior: Prior | None
    derive: str | None             # formula reference, e.g. "wall_R_from_layers"

@dataclass(frozen=True)
class ReductionSpec:
    phis: tuple[PhiSpec, ...]

    @property
    def free(self) -> tuple[PhiSpec, ...]:
        return tuple(p for p in self.phis if p.mode != "fixed")
```

`ReductionSpec` is persisted in the study (it can vary per fit). The full
physical model lives in the house and does not change with the spec.

### Default reduction (no user customization)

When a study is first created, the system proposes a "fully detailed"
reduction:

```python
def default_reduction_spec(full: FullRCGraph, house: dict) -> ReductionSpec:
    """
    - one φ per opaque element:   (R, C),  derived, free, prior from layer 1
    - one φ per glazing:           U·A,    derived, free
    - one φ per air_exchange:      R,      derived, free
    - one φ per room:              C,      derived, fixed (volume known)
    - surface resistances R_se, R_si: fixed at standard values
    """
```

Identifiability analysis then suggests **transforms** on the spec (lump
correlated φ's into one effective param, fix uninformative ones).

### Function: compile mapping

```python
def compile_mapping(
    full: FullRCGraph,
    reduced: ReducedRCGraph,
    spec: ReductionSpec,
    materials: MaterialLibrary,
) -> Mapping:
    """
    Build the φ → reduced-graph-values function.

    For each reduced edge/node:
      1. Look at its contributors (full-graph ids).
      2. Group contributors by which φ in spec covers them.
      3. Compose:  reduced_value = formula(   [phi_to_full(c) for c in contributors]  )
         where phi_to_full(c) substitutes the relevant φ via the mode-specific rule:
           - derived:    full_value = derive_fn(φ, layer-1 quantities)
           - effective:  full_value = φ / share   (the φ is split across its scope)
           - fixed:      full_value = layer-1 default

    Result: an array of closures, one per reduced edge/node, taking a φ vector
    and returning the reduced value.
    """
```

```python
@dataclass
class Mapping:
    phi_names: tuple[str, ...]                           # canonical order
    phi_priors: tuple[Prior, ...]
    target_names: tuple[str, ...]                        # reduced edge/node ids
    forward: Callable[[np.ndarray], dict[str, float]]    # φ_vec → reduced values
    inverse: Callable[[dict[str, float]], np.ndarray]    # best-effort
    jacobian: Callable[[np.ndarray], np.ndarray] | None  # optional, analytical
```

### Pseudo: forward

```python
def forward(phi_vec):
    # 1. Update each full-graph value from its controlling φ
    full_values = {}
    for full_id, (phi_name, rule) in phi_to_full_index.items():
        phi_val = phi_vec[phi_index[phi_name]]
        full_values[full_id] = rule(phi_val)

    # 2. Apply each reduced edge/node's formula over its contributors
    reduced_values = {}
    for r in reduced.edges + reduced.nodes:
        vals = [full_values[c] for c in r.contributors]
        reduced_values[r.id] = r.formula.apply(vals)

    return reduced_values
```

### Pseudo: identifiability-driven suggestion

```python
def suggest_reductions(spec: ReductionSpec, mapping: Mapping,
                       sample_residuals: Callable) -> list[SpecTransform]:
    """
    Compute Jacobian of residuals w.r.t. φ (FD or analytical).
    Group correlated φ's (SVD or correlation matrix).
    For each group, propose a SpecTransform: merge into one effective φ
    with a combined prior, or fix one and free the others.
    """
```

The user accepts or rejects each transform; the spec is rewritten.

---

## Layer 4 — Solver (θ-space)

Numerical layer. `AssembledSystem` is built from the **reduced** graph (small
matrices). The fit loop only ever sees φ and residuals.

### Functions

```python
def assemble(reduced: ReducedRCGraph) -> AssembledSystem:
    """
    reduced graph + current values → (A, B_boundary, B_source) matrices.
    Topology is fixed; only edge/node values change between iterations.
    """

def patch_values(sys: AssembledSystem, reduced_values: dict[str, float]) -> AssembledSystem:
    """
    Cheap update: fill A and B entries by precomputed (i, j) indices.
    Avoids rebuilding the node/edge index on every fit iteration.
    """

def simulate_zoh(sys: AssembledSystem, inputs, y0) -> np.ndarray:
    """Pure numerics — unchanged from current implementation."""
```

### The fit loop

```python
def build_forward(house, study, spec):
    full      = expand(house, materials)
    reduced   = reduce_graph(full)
    mapping   = compile_mapping(full, reduced, spec, materials)
    sys_proto = assemble(reduced)         # topology only

    def residuals(phi_log):
        phi   = np.exp(phi_log)
        vals  = mapping.forward(phi)
        sys   = patch_values(sys_proto, vals)
        y     = simulate_zoh(sys, study.inputs, study.y0)
        r_obs = (y - study.obs).ravel()
        r_pr  = prior_residuals(phi, mapping.phi_priors)
        return np.concatenate([r_obs, r_pr])

    return residuals, mapping
```

Log-space is a fit-layer concern (keeps φ > 0), not a mapping concern. The
mapping speaks in physical units.

---

## What gets persisted

| Object | Where | Recomputed when |
|---|---|---|
| House JSON | `data/houses/<name>.json` | user-edited |
| FullRCGraph | not stored | every run/fit |
| ReducedRCGraph | not stored | every run/fit |
| ReductionSpec | embedded in study | user-edited; suggestions on demand |
| Mapping | not stored | every run/fit |
| AssembledSystem | not stored (held in fit closure) | every run/fit |
| Fit result (φ values, std, cov) | embedded in study | each fit completes |

Nothing derived is persisted. The house JSON + study (with `ReductionSpec`)
fully determine the model.

---

## Module layout

```
solver/
  physics.py          # layer 1 → 2a:  expand(house) → FullRCGraph
  reduce.py           # layer 2a → 2b: reduce_graph(full) → ReducedRCGraph    [NEW]
  reduction_spec.py   # layer 3 spec:  data model + default builder            [NEW]
  mapping.py          # layer 3 fn:    compile_mapping(...) → Mapping          [NEW]
  assemble.py         # layer 4:       reduced → AssembledSystem (topology)
  simulate.py         # layer 4:       simulate_ivp + simulate_zoh
  fit.py              # layer 4:       build_forward + fit_nls + fit_mcmc
  identifiability.py  # layer 3 tool:  suggest_reductions(spec, mapping, ...)
```

Three new modules: `reduce.py`, `reduction_spec.py`, `mapping.py`. The
existing `physics.py` shrinks to just expand (no implicit reduction).
`assemble.py` simplifies (input is already reduced; no internal Schur).
`fit.py` becomes a thin wrapper around `Mapping`.

---

## UI consequences

A new pane is needed between the house editor and the study tab: the
**Reduced physical model** view. Shows the `ReductionSpec` as:

- a table of φ (name, mode, prior, current value, free/fixed badge)
- the reduced-graph topology drawn underneath, with edges/nodes labeled
  by the φ(s) that control them
- a "suggest reductions" button → calls `identifiability` → presents
  transforms the user can accept

The existing "RC Graph" tab continues to show the **reduced** RC graph
(layer 2b) for solver-level inspection. The new view is layer 3 and is the
primary place the user adjusts what to fit.
