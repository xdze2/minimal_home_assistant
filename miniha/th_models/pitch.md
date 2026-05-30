# Comfort, not kilowatt-hours

## A diagnostic tool for thermal comfort in old European buildings

### The problem

Europe has tens of millions of pre-1948 buildings — stone, brick, timber, thick walls — that **fail on paper** under current energy regulations (RT2012, RE2020, EPC) yet are often genuinely comfortable to live in. The regulations were built for new construction and steady-state energy balance. They measure the wrong thing.

Meanwhile, summer overheating in these same buildings is a fast-growing crisis that **no regulation addresses**. Top-floor rooms under uninsulated roofs, south-facing stone walls absorbing heat all day — owners face a menu of expensive interventions (roof insulation, external shutters, ITE, A/C) with no honest way to compare them. The renovation market sells what's easy to install, not what most improves comfort.

### The gap

Two camps exist, neither serves old buildings well:

| | What it does | Where it works | Where it fails |
|---|---|---|---|
| **Declarative tools** (DesignBuilder, EnergyPlus, regulatory calculators) | User declares materials & U-values; tool computes loads | New builds with known specs | Old buildings — "true" U-value is anyone's guess |
| **Black-box ML** | Big data → predict | Commercial buildings with dense sensor grids | One-room, one-thermometer reality |

**Nothing sits in the middle.** That middle is exactly where European housing stock lives.

### What we're building

A **grey-box thermal model with weak physical priors**, fit on cheap sensor data (one indoor thermometer + free weather API), that does three things existing tools don't:

1. **Distinguishes heat-input pathways** — window solar, roof solar, south-wall solar, infiltration — so different interventions have different modelled effects.
2. **Combines partial physical knowledge with data** — user describes the building roughly ("stone walls ~40 cm, two south windows, slate roof"), we encode that as Bayesian priors. Data refines the priors; priors break the under-determination that plagues pure data fits.
3. **Outputs a ranked intervention list with uncertainty bands**, in *comfort units*, not energy units: *"external shutters: −2.4 °C peak [95 % CI: −1.6 to −3.1]; roof insulation: −1.1 °C [−0.4 to −1.8]; night ventilation: −1.8 °C if executed."*

That's the product — not a simulator, an **advisor**.

### Why now

- Cheap sensors (€5 thermometers, Home Assistant ecosystem) make per-room data collection trivial.
- Open weather APIs (Open-Meteo) give free hourly outdoor + solar irradiance per coordinates.
- The summer overheating crisis is genuinely accelerating; 2022/2023/2024 broke heat records repeatedly.
- LLM-assisted UX makes complex physical models legible to homeowners for the first time.

### Why this is defensible

The differentiator isn't the math (grey-box RC models are 50 years old) — it's the **prior elicitation + intervention ranking + honest uncertainty** wrapped around it. The intellectual barrier is knowing which priors matter, which interventions to model how, and how to communicate uncertainty without lying or paralysing the user. That's expert-system territory that compounds with use.

### What we have

- Working data pipeline (InfluxDB, sensor configs, weather feeds).
- 1R1C model fitting end-to-end on real room data.
- Theory documented; honest about limitations and identifiability.
- Inspector UI for diagnosing data quality and residuals.
- Clear, prioritised technical roadmap ([miniha/th_models/NEXT.md](miniha/th_models/NEXT.md)).

### What we need next

- Multi-aperture solar model + ceiling-mass node (handles top-floor summer case).
- Priors layer (the distinctive bit).
- Intervention-simulation UI — the actual product surface.
- A few pilot houses across construction types (stone farmhouse, Haussmann apartment, post-war brick) for calibration and validation.

### Market

- **Primary**: homeowners of pre-1970 European housing facing renovation decisions — France alone has ~12M pre-1948 dwellings.
- **Secondary**: renovation architects and *bureaux d'études thermiques* who need a comfort-side tool to complement regulatory compliance software.
- **Tertiary**: insurers, municipalities, and heritage bodies dealing with summer overheating risk in protected building stock.

### One-line pitch

> *We tell you whether to buy shutters or insulate the roof — in degrees of comfort, with honest error bars, from a €5 thermometer and a description of your house.*
