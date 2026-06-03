# Workflow — the project as a four-stage research loop

What the project is, *organisationally*. Refer to [NEXT.md](NEXT.md) for
where the thermal model itself could go, [SEGMENTER.md](SEGMENTER.md) for
the segmenter design, and [README.md](README.md) for the current state.

## Framing

This is a **research workflow**, not a software product with a single
"fit" button. The artefacts are for someone *thinking* (the homeowner,
a building consultant, future-you), not for an end-user clicking
buttons. That distinction drives every design choice below.

The North Star ([NEXT.md §North star](NEXT.md)) — "which intervention
has the highest comfort payoff for this specific room?" — is reached
by going through four stages, each with a different tempo, a different
primary artefact, and a different user activity.

## The four stages

| Stage | Tempo | Artefact | User activity |
|---|---|---|---|
| 1. **Building description** | Once per building, evolves slowly | `building.yaml`, `rooms/*.yaml` | Describe what you have |
| 2. **Measurement campaign** | Weeks–months of acquisition | `campaigns/*.yaml` | Install sensors, monitor coverage |
| 3. **Analysis** | Hours–days per plan, iterative | `plans/*.yaml` → `results/` | Author plans, review fits |
| 4. **Insights** | Per analysis, accumulating | `insights/*.md` | Read, decide, act |

The arrows go both ways. Insights from analysis often demand a new
campaign (add a ceiling sensor) or refine the building description
(thermal mass suggests brick, not stone). The loop matters more than
any single pass through it.

```
building description ←──┐
        ↓               │
    campaign  ←────┐    │
        ↓          │    │
    analysis ──────┤    │
        ↓          │    │
    insights ──────┴────┘
```

## Stage 1 — Building description

Facts about the world that don't depend on what question is being asked.
Building geometry, sensor identities, occupant schedule, construction
materials. Authored once per building, evolves slowly.

Splits naturally into **building-level** and **room-level**:

- `building.yaml`: location (lat/lon), shared roof, walls, materials,
  construction era, exterior environment.
- `rooms/<name>.yaml`: per-room geometry, sensor roles, usage hints
  (cooking hours, occupancy patterns), connection to building.

Rationale for the split: priors on `R_roof` come from the *building*,
not the room. Multiple rooms share the roof, the walls, the location.

## Stage 2 — Measurement campaign

The bridge between "what the building is" and "what the data can tell
us". Currently implicit ("there's a Sonoff in chambre"). Should be
explicit:

```yaml
# campaigns/2026-winter-ceiling.yaml
intent: "test whether 2R2C with ceiling node beats 1R1C for chambre"
period: [2026-01-15, 2026-04-15]
sensors_added:
  - role: ceiling_temp_chambre
    hardware: DS18B20
    location: "taped to ceiling, centre of room"
hypothesis: |
  If diurnal residual lags solar by 2–4h (NEXT.md §6), a measured
  ceiling temp turns the latent 2R2C state into an observed one and
  fits collapse to plain regression.
success_criteria:
  - "2R2C fit RMSE < 1R1C fit RMSE by > 0.2 °C"
  - "fitted R_roof_int within 2× of handbook prior"
```

What recording the campaign explicitly buys you:

- **Justifies why a sensor exists** (the hypothesis it was added to test).
- **Bounds the analyses that depend on it** (plans using ceiling temp
  are only valid in this window).
- **Enables ex-post evaluation** of the campaign ("did this sensor
  actually disambiguate the model?").

This makes [NEXT.md Axis 4](NEXT.md) operational: every sensor is added
*for a reason*, that reason is *a campaign*, the campaign produces data
that *feeds plans* that produce *insights* that might *trigger the next
campaign*. The workflow closes the loop.

## Stage 3 — Analysis

The toolbox stage. Multiple analyses per (room, period) is *normal* —
they ask different questions of the same data. Winter cuisine has at
least two natural plans: "fit free-decay segments to get τ" and "fit
heating cycles to get Φ_heat/C". Each is a plan, each gets a result.

### The plan-as-document keystone

A plan is the **union of every decision the pipeline needs to make**,
captured as a reviewable file:

```yaml
# plans/cuisine_winter_2026_decay.yaml
target: { room: cuisine, period: [2026-01-15, 2026-02-12] }
intent: "estimate τ from free-decay segments"

context_refs:
  building: buildings/home/building.yaml
  room:     buildings/home/rooms/cuisine.yaml

segmenter:
  method: sliding_exponential
  window_hours: 4
  step_minutes: 30
  accept:
    r2_min: 0.98
    tau_range_hours: [2, 50]
  merge:
    method: greedy_grow
    tau_log_tol: 0.2
    Tinf_tol_C: 0.5
  gates:
    exclude_hours: [[11:30, 14:00], [18:30, 21:00]]    # cooking
    require_phi_heat: 0

model:
  variant: r1c1
  fit: penalised_ls
  priors:
    tau_hours:   { value: 8, sigma: 4 }
    Tinf_offset: { value: 0, sigma: 5 }

outputs:
  - tau_distribution_plot
  - Tinf_vs_Iout_regression
  - segment_table
  - parameter_posterior

provenance:
  generated_by: human          # or "llm:claude-opus-4-7@2026-05-30"
  reviewed_by:   xdze2
  reviewed_at:   2026-05-30
```

### Why the plan being an input document matters

The shift is from *the tool decides* to *the user (or LLM) decides,
the decision is recorded, the tool executes*. Consequences:

- **Auditability**: every fit reproducible from `(data snapshot, plan)`.
  No "what version of the code was this?" archaeology.
- **Disagreement is cheap**: user reads the plan, edits one field,
  re-runs. They never have to argue with the code.
- **The LLM is optional**: plans can be hand-written, scaffolded by an
  LLM and edited, or fully generated. Same execution path. The LLM is
  a *productivity* tool, not a *correctness* dependency.
- **Plans diff cleanly**: "what changed between January's analysis and
  June's?" is `git diff` on a YAML file.
- **Per-room, per-period scoping is natural**: a plan covers
  `(room, time window, intent)`. Winter and summer of the same room
  are two plans, both valid, both committed.

### Context vs plan — the boundary

If changing a field would invalidate *other* analyses too, it belongs
in context. If changing it only affects *this* fit, it belongs in the
plan.

`R_walls_prior_value` is borderline: it's a fact about the world
(context) but you might want to test the fit under a different prior
(plan). Resolution: **default lives in context, plan can override**.
Override is recorded as part of provenance ("this plan deviates from
context priors because…").

### The executor

Drastically simple, conceptually:

```python
def run_plan(plan_path: Path) -> Result:
    plan = load_plan(plan_path)
    context = load_context(plan.context_refs)
    data = load_timeseries(context, plan.target)
    segments = SEGMENTERS[plan.segmenter.method](data, plan.segmenter, context)
    fit = MODELS[plan.model.variant].fit(segments, plan.model, context)
    return render_outputs(plan.outputs, segments, fit, context)
```

`SEGMENTERS` and `MODELS` are dict-of-callables. Adding a new method =
add a key + write the callable + document its plan schema. No core
changes.

### Plan-schema bloat — the failure mode to watch

Every new feature wants a new field; soon plans are 300 lines, half of
which nobody understands. Two disciplines:

1. **Every field has a default**. A minimal valid plan is ~10 lines:
   target, intent, segmenter.method, model.variant.
2. **Each segmenter/model variant owns its own sub-schema**. The
   top-level plan schema is small; variant-specific fields live with
   the variant (Pydantic discriminated unions). Adding a feature to
   one variant doesn't pollute plans for the others.

## Stage 4 — Insights

The numerical fit is not the insight. The insight is the *interpreted,
human-readable conclusion*:

> τ for cuisine is ~9 h in winter, dropping to ~4 h when the window
> is cracked, suggesting roof/wall insulation rather than ventilation
> control is the high-leverage intervention.

That sentence belongs in a markdown file alongside the plan that
produced it. Insights compound; numerical fits don't.

```
insights/
  chambre_overheating.md
  cuisine_thermal_mass.md
  interventions_ranked.md      # the actual deliverable
```

`interventions_ranked.md` is the closest thing to "the product". It
references the plans and insights that justify each ranking, with
uncertainty bands.

## Where the LLM fits

**Put the LLM where the inputs are unstructured and the outputs are
structured, not the other way around.**

Two LLM uses in this workflow, both as *draft generators for
human-reviewed artefacts*:

1. **Plan generator** (`context/planner.py`): given building + room +
   campaign + intent, draft a plan YAML. Output is reviewed,
   committed, executed deterministically.
2. **Insight writer**: given (plan, result), draft a one-paragraph
   insight + intervention implications. Output is reviewed Markdown.

Neither is in the hot loop. Both close the workflow without becoming
load-bearing. The numerical pipeline (segmenter + model + fit) stays
100% deterministic, pure-Python, fully testable.

### Why not an LLM agent at runtime

Tempting because "expert decides which tool fits". But:

- The decision space is small and enumerable (3–5 segmenters, 3–4
  models). That's a decision table, not open-ended reasoning.
- Reproducibility breaks: same data + same code today gives a
  different answer next month because the model drifted.
- Failure modes are bad: a wrong agent decision produces a
  plausible-looking fit with wrong parameters, discovered months
  later when the intervention recommendation didn't pan out.
- The "expertise" being invoked is statistical, not linguistic. Use
  a classifier.

Agent-at-runtime is appealing because it feels like it dissolves the
"I have to decide the architecture" anxiety. But the architecture
decisions don't go away — they get hidden inside a prompt, which is
the worst place to put them because you can't unit-test a prompt.

## Repo layout this implies

```
buildings/
  home/
    building.yaml                           # stage 1
    rooms/
      chambre.yaml
      cuisine.yaml
    campaigns/
      2025-summer-baseline.yaml             # stage 2
      2026-winter-ceiling.yaml
    plans/
      chambre_summer_2025_overheating.yaml  # stage 3 input
      cuisine_winter_2026_decay.yaml
    results/
      chambre_summer_2025_overheating/      # stage 3 output
        fit.json
        segments.parquet
        diagnostics.html
    insights/
      chambre_overheating.md                # stage 4
      cuisine_thermal_mass.md
      interventions_ranked.md
miniha/
  th_models/                # tool 1: models + fit
  segmenter/                # tool 2 (see SEGMENTER.md)
  context/                  # tool 3: building/room/campaign loading + planner
  inspector/                # stage 3/4 UI
```

Multi-building scales by adding sibling dirs under `buildings/`.

## What "done" looks like for each stage

Different stages succeed differently:

- **Stage 1**: building is described in enough detail to support the
  next campaign. Not "complete" — there's no such thing.
- **Stage 2**: data exists for the declared period with acceptable
  coverage. `flags.py`-style gap detection is the validator.
- **Stage 3**: plan executed, result artefacts exist, plan + result
  committed.
- **Stage 4**: insights file exists, references its plan, contains
  at least one actionable claim with confidence.

## Build order — the smallest end-to-end slice

Because the workflow is the product, **a thin vertical slice through
all four stages beats a deep, sophisticated single tool**. A working
pipeline that does:

1. Read `chambre.yaml` (stage 1, ~exists).
2. Acknowledge `campaign_2025_summer.yaml` (stage 2, one sensor, one
   window).
3. Execute `plan_chambre_summer_overheating.yaml` (stage 3, simplest:
   1R1C OLS, no segmentation).
4. Produce `insights/chambre_overheating.md` (stage 4, auto-drafted,
   manually edited).

…is more valuable than a perfect 2R2C fit with no workflow around it.
Because (a) it validates the workflow design before you commit to it,
(b) it gives every future improvement a slot to land in, and (c) it's
the smallest demonstration of the project's actual thesis.

## What this framing is *not*

- Not a project-management process. Stages aren't gates; you don't
  "finish stage 1 before starting stage 2". They're tempos.
- Not a UI prescription. Streamlit / CLI / Jupyter all work; the
  artefacts are plain files.
- Not opposed to ad-hoc exploration. The inspector exists for that.
  Plans formalise what's worth keeping.
