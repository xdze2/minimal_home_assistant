# Segmenter — design notes

The temporal layer of the project. Given timeseries, produce labelled
intervals that each carry a contract about which physical assumptions
hold. Models consume segments + contracts.

Refer to [WORKFLOW.md](WORKFLOW.md) for how this fits into the
four-stage workflow, and [NEXT.md](NEXT.md) for the model-side
counterpart.

## What problem the segmenter solves

The 1R1C model (and its descendants) only describes the room when the
inputs it knows about are the *only* things driving the temperature.
Whole-series fitting averages over heating events, cooking spikes,
window openings — situations the model wasn't given and can't
represent. The result is biased parameters and unphysical artefacts
(the negative `g_solar`).

The segmenter's job: **find intervals where the model's assumption set
holds**. Then fit only on those.

This generalises the cuisine-specific question ("where are the
exponential decays?") to a workflow primitive: every model variant has
an assumption set; the segmenter finds windows compatible with it.

## The conceptual upgrade

The earlier framing — "segment where an exponential fits well" — is
**output-based segmentation**: classify by the response shape.

The right framing is **input-based segmentation**: classify by the
boundary conditions. A segment is a window where the *driving
conditions* are stable, whatever the response looks like:

- Constant-heating: input regime is stable (heat on, exterior slow).
- Free decay: input regime is stable (no heat, exterior slow).
- Window-open: input regime is stable (open, exterior slow).
- Cooking spike: input is *not* stable — should not be a segment, or
  should be a segment with the assertion "internal source unmodelled".

Output-based segmentation is the special case where you have no input
signals and have to infer them from the response. That's the cuisine
situation today.

## Segments carry contracts, not labels

This is the load-bearing design decision.

The segmenter doesn't output `"free_decay"` as a free-text label. It
outputs a *set of assertions* about which boundary conditions hold:

```python
@dataclass
class Segment:
    t_start: datetime
    t_end:   datetime
    assertions: dict[str, Any]
    confidence: float
    method:     str        # which segmenter produced this
    provenance: dict       # parameters used, version, …

# example
Segment(
  t_start=..., t_end=...,
  assertions={
    "phi_heat":               0,         # heating off
    "window_open":            False,     # sealed
    "no_internal_disturbance": True,     # no cooking, no big occupancy
    "T_out_slow_varying":     True,      # |dT_out/dt| < threshold
  },
  confidence=0.92,
  method="sliding_exponential",
)
```

Models read assertions and pick a compatible variant:

- 1R1C accepts `{phi_heat: 0}` → fits as homogeneous response.
- 2R2C accepts the same → fits with ceiling node still active.
- 1R1C with heating accepts `{window_open: False}` → fits with `Φ_heat`
  as a free regressor.

**Assertions are a contract between segmenter and model.** New
regimes = new assertion keys, agreed across both tools. The vocabulary
should live in one shared file (`regimes.py` or similar).

## The ladder of methods, ranked

Methods, cheapest to fanciest, with opinions about when each is right.

### 1. Hand-coded rules on the raw signal

Walk the series, accept points where `dT/dt < −ε` continuously,
`d²T/dt² > 0` (concave up), gap < threshold. ~20 lines.

**When right**: prototyping, single-room sanity checks.
**When wrong**: noise in finite differences forces smoothing; thresholds
need tuning per room; brittle on borderline cases.

### 2. Hand-coded rules + side channels (gated)

Same as (1) but use *known events* to gate:

- Time-of-day masks ("only 22:00–06:00, no cooking").
- Reed switches, CO₂, Daikin power → kill segments where heating > 0
  or CO₂ spikes.
- Cross-check `T_out` change across the window.

**When right**: when side channels exist. Dramatically more robust
than (1), still simple.
**When wrong**: cuisine doesn't have them → degenerates to (1).

This is the starting point for any new room. Combine with method 4.

### 3. Residual-from-baseline detection

Fit a coarse baseline model, segment where residuals are small and
stable.

**When right**: when you already have a fit you trust on similar data.
**When wrong**: circular for a new room. You need a model to find
segments to fit a model.

### 4. Direct exponential-fit scanning (sliding window) — **recommended**

Skip explicit segmentation. Slide a fixed-length window across the
series, fit an exponential at every position, keep windows where the
fit quality is high (R² > 0.98, residual std < threshold, `τ` in
plausible range).

The fit quality *is* the segmentation criterion — RANSAC-like. No
separate "is this a decay?" classifier to tune.

**When right**: for free-decay detection in any room without `Φ_heat`
data. **This is the cuisine recommendation.**
**When wrong**: only finds free-decay regimes; doesn't generalise to
heating cycles or ventilation events.

#### The merge step

Sliding-window fitting produces overlapping accepted windows. Merge
overlapping windows that **agree on parameters**:

- `|log τ_i − log τ_j| < 0.2` (within ~20%).
- `|T∞_i − T∞_j| < 0.5 °C`.

Three merge strategies:

- **A. Agreement test on parameters**: pairwise overlap check, merge
  if both agree. Cheap.
- **B. Re-fit on the union and check**: most rigorous version of "the
  merged fit should also be good".
- **C. Greedy growing (recommended)**: sort windows by R²; take the
  best as seed; extend left/right one step at a time; accept extension
  if re-fitted R² stays above threshold and `τ` doesn't drift > 20%.
  Stop when extension fails. Consume overlapping windows. Repeat.

Pseudocode:

```python
def grow(seed, series):
    lo, hi = seed.t_start, seed.t_end
    τ_ref, T∞_ref = seed.τ, seed.T∞
    while True:
        extended = False
        for direction in (-1, +1):
            new_lo, new_hi = extend(lo, hi, direction)
            fit = exp_fit(series[new_lo:new_hi])
            if (fit.r2 > 0.98
                and abs(log(fit.τ) - log(τ_ref)) < 0.2
                and abs(fit.T∞ - T∞_ref) < 0.5):
                lo, hi = new_lo, new_hi
                extended = True
        if not extended:
            return Segment(lo, hi, τ_ref, T∞_ref)
```

**R² on its own is weak**: a straight line through an exponential
window gets R² > 0.95 easily. Use parameter-consistency as the
primary criterion, R² as sanity filter.

### 5. Change-point detection (`ruptures`)

Statistical detection of regime shifts in mean/variance/slope of
`dT/dt`. Returns change points; segments are the intervals between
them.

**When right**: when you want non-overlapping coverage of the whole
series and don't know a priori what regimes exist.
**When wrong**: change points ≠ "this segment fits assumption set X".
Post-filter still needed.

Probably the right tool **once you go beyond free-decay** — gives you
a partition that other methods can classify.

### 6. HMM with hand-designed states

Hidden states like {heating, free-decay, disturbed}, emission
distributions on `dT/dt` and `T_in − T_out`, fit with `hmmlearn`,
Viterbi for state sequence.

**When right**: rich multivariate features, real signal to extract.
**When wrong**: with only 2–3 states and tiny features, usually
rediscovers what rules give you.

### 7. Unsupervised representation learning + clustering

Windowed features → embed (PCA/UMAP/autoencoder) → cluster.

**When right**: you genuinely don't know what regimes exist.
**When wrong**: a sledgehammer when you already know what an
exponential looks like.

### 8. Deep learning (sequence models)

1D CNN / Transformer on labelled segments, or self-supervised
contrastive on time-series patches.

**Wrong tool here.** The ground truth is "does a 3-parameter
exponential fit well" — *just fit the exponential*. Don't train a
neural net to predict that. Worth knowing it's an option only to
confidently rule it out.

## What the recommended path actually looks like

For a new room with no side channels (cuisine today):

1. **Method 4 (sliding exponential)** with greedy-grow merge, gated by
   method 2 (time-of-day mask for cooking).
2. Output: a set of `{phi_heat: 0, ...}` segments with `τ`, `T∞`, R²,
   and confidence.
3. Hand off to model for fitting.

For a room with `Φ_heat` available:

1. **Method 5 (change-point)** on the heating signal to partition into
   {heating, no-heating} intervals.
2. **Method 4** inside the no-heating intervals to find clean decays.
3. **Direct linear fit** on heating intervals to estimate `Φ_heat/C`.
4. Different segments, different assertions, different fits.

## Per-segment fit outputs and what they tell you

For free-decay segments, the per-segment exponential gives `(τ, T∞,
T_0)`:

- **`τ`**: median across segments = the room's characteristic time
  constant. Distribution shape diagnoses regimes (bimodal = two states;
  heavy tail = disturbed decays). Plotted vs date = seasonal drift.
- **`T∞`**: the equilibrium the room is drifting toward. Plotting
  `T∞ − T_out` against avg `I_solar` per segment is a **direct
  regression on solar gain and base gain** — recovers `ΔT_eq` and
  `g_solar` from theory §5 without OLS machinery, without
  regressor-collinearity (each segment is one independent observation).
- **`T_0`**: per-segment starting value. Not physically meaningful
  individually; distribution = operating range of the room.

Bonus: scatter all segments in the `(τ, T∞)` plane, colour by date or
avg `I_solar`. Probably the single most informative diagnostic of
"does 1R1C work for this room?" — tight cloud = yes, diffuse =
multiple regimes hidden.

## Plan-schema sketch for the segmenter

Segmenter config lives in the plan ([WORKFLOW.md](WORKFLOW.md)):

```yaml
segmenter:
  method: sliding_exponential       # or: changepoint, gated_rules, …
  # method-specific fields below; schema discriminated by `method`
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
    exclude_hours: [[11:30, 14:00], [18:30, 21:00]]
    require_phi_heat: 0
  emits:
    assertions:
      phi_heat: 0
      no_internal_disturbance: true
```

`emits.assertions` is the contract this segmenter promises. Downstream
models read it to decide compatibility.

## File layout

```
miniha/segmenter/
  __init__.py
  base.py           # Segment dataclass, Segmenter protocol
  regimes.py        # the shared assertion vocabulary
  features.py       # per-window feature extraction (slope, R², …)
  sliding_exp.py    # method 4
  changepoint.py    # method 5 (later)
  gated_rules.py    # method 2 helpers
  fit_exp.py        # the 3-param exponential fit, vectorised
```

`regimes.py` should land first — it's the shared vocabulary that
segmenter and model both speak. ~30 lines, all dataclasses.

## What's deliberately *not* in the segmenter

- **Choosing which segmenter to use**: that's the plan. The segmenter
  module exposes a library of methods; the plan picks one.
- **Interpreting why a segment failed**: that's diagnostics, surfaced
  in the inspector.
- **Multi-segment statistics** (τ-distribution plots, `(τ, T∞)`
  scatter): those are the *fit/output* layer consuming segments.
  Segmenter produces segments; it doesn't analyse them.

## First implementation — narrowest possible slice

Smallest end-to-end commit that proves the design:

1. `regimes.py`: `Segment` dataclass + assertion-key constants.
2. `fit_exp.py`: 3-param exponential fit, vectorised over a batch of
   windows.
3. `sliding_exp.py`: window scan + R² filter + greedy-grow merge.
4. A single plan (`plans/cuisine_winter_2026_decay.yaml`) that uses
   it.
5. Inspector view that overlays accepted segments on the timeseries.

~200 lines total. Validates the segment-contract idea on the simplest
useful regime, then everything else (change-point, gated rules,
heating-cycle fits) lands as additional methods following the same
interface.
