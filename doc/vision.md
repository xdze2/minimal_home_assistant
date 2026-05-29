## Thermal Comfort in Old European Buildings — Brainstorm

This is a genuinely interesting gap. Let me be honest about what's strong, what's weak, and what tools could be useful.

---

### The Real Problem You're Identifying

Current regulation (RT2012, RE2020 in France, similar elsewhere) is:

- **New-build centric** — retrofit is an afterthought
- **Static energy balance** — Uvalues, heating loads, annual kWh/m² → misses _experience_
- **Winter-biased** — summer overheating in old stone/masonry buildings is a growing crisis nobody regulates
- **Compliance-oriented** — not occupant-oriented

Old European houses (stone, brick, timber, thick walls) have **very different thermal physics** than what the norms model. High thermal mass, hysteresis, radiant asymmetry, infiltration patterns — a 1750s farmhouse "fails" on paper but can be genuinely comfortable if you understand how it actually works.

---

### The Conceptual Wedge: Efficiency ≠ Comfort

This is your strongest idea. They're not the same thing and the industry conflates them constantly.

|               | Thermal Efficiency | Thermal Comfort                 |
| ------------- | ------------------ | ------------------------------- |
| Metric        | kWh/m²/year        | PMV, operative temperature, MRT |
| Time          | Steady-state       | Transient, hourly               |
| Subject       | The building       | The occupant                    |
| Standard      | RE2020, EPC        | ISO 7730, ASHRAE 55             |
| Old buildings | Usually "fails"    | Often surprisingly good         |

Thick stone walls have a **thermal lag** of 8–12 hours. They're terrible at reducing _energy use_ but excellent at _stabilizing temperature swings_ — which is exactly what comfort needs. Nobody talks about this properly.

---

### Useful Tools & Methods

**Simulation side**

- **EnergyPlus / OpenStudio** — full transient simulation, but steep learning curve, overkill for most
- **TRNSYS** — better for dynamic/transient, used in research
- **DesignBuilder** — more accessible wrapper
- **thermal-comfort (Python lib by CBE Berkeley)** — PMV/PPD, adaptive comfort, direct comfort metrics, excellent and underused
- **ladybug-tools / Honeybee** — Grasshopper-based, good for solar/radiation analysis, MRT mapping

**Measurement side**

- **Temp/RH loggers** (Govee, Inkbird, SensorPush) — cheap, place in multiple rooms, reveal thermal lag, cold spots, humidity issues
- **Surface temperature** — IR thermometer or thermal camera (FLIR One ~€300) — find cold walls, thermal bridges, infiltration points instantly
- **Blower door test** — quantifies infiltration, often the #1 issue in old buildings
- **CO₂ logger** — proxy for ventilation quality, comfort-relevant

**The combination that's powerful:** a few weeks of cheap data loggers + one IR camera session → you can identify 80% of comfort issues without any simulation.

---

### Diagnostic Framework: Given a House, What To Do?

A structured approach could look like this:

**Step 1 — Declarative inputs** (no measurement needed)

- Wall/floor/roof construction type → estimate U-values and thermal mass
- Orientation, glazing ratio, shading
- Heating system type and location
- Occupancy pattern

→ Output: rough comfort risk map (radiant cold walls? summer overheating risk? infiltration likely?)

**Step 2 — Easy measurement layer**

- 2–4 cheap loggers placed for 2–4 weeks → reveal actual thermal lag, day/night swings, room-to-room delta
- IR thermometer sweep → find the worst surfaces

→ Output: ranked list of issues by severity

**Step 3 — Prioritized interventions**

- Infiltration sealing (cheap, high ROI, often #1 in old houses)
- Interior window insulation / secondary glazing (preserves façade, huge comfort gain)
- Thick curtains / thermal shutters (underrated)
- Heating system placement (radiator under the cold window matters enormously)
- Thermal mass activation vs. night setback strategy
- Summer: external shutters, night ventilation schedule

---

### Honest Assessment

**What's strong:**

- The efficiency vs. comfort framing is real and underserved. There's genuine intellectual substance here.
- The old-building focus has a large addressable audience in Europe (France alone has millions of pre-1948 buildings)
- The measurement-first diagnostic angle is practical and differentiating

**What's harder than it looks:**

- Comfort is _subjective and personal_ — PMV models are population averages, individuals vary wildly. This makes any "comfort score" output contentious.
- Old buildings are extremely heterogeneous — a tool that works for a Breton granite farmhouse fails for a Haussmann apartment. Calibration/validation is hard.
- The renovation market is crowded with energy-first tools. Repositioning around _comfort_ is clever but you'll fight perception.
- Transient simulation that's both accurate and fast enough for an interactive tool is genuinely technically difficult.

**The version I'd be most excited about:**
A lightweight diagnostic tool — declarative inputs + optional logger data → ranks comfort issues → gives actionable, prioritized, low-cost interventions with honest explanations of _why_ (thermal lag, radiant asymmetry, etc.). Not a simulation engine. An expert system with good physical intuition baked in.

That's buildable, useful, and doesn't exist well yet.

---

What angle interests you most — the tool/product side, the physical modeling side, or the policy/market framing?

---

### What exists in the wild (May 2026)

Quick scan of the web for tools and references close to what we're building (in particular the `inertie_nocturne` toy). Nothing close to it currently exists.

**Heavy professional simulators** — accurate, but for engineers, not curious humans:

- [ThermalSim](https://www.thermalsim.com/) — full dynamic room simulator (one day or one year), surface-by-surface, building-code-grade
- [HTflux thermal mass calculator (ISO 13786)](https://www.htflux.com/en/free-calculation-tool-for-thermal-mass-of-building-components-iso-13786/) — closest in spirit to our "épaisseur active" math, but it's about _components_, not "should I open my window tonight?"

**HVAC sizing calculators** — for picking an air conditioner. No concept of night ventilation, thermal mass dynamics, or fan-vs-fan comparison:

- [ServiceTitan HVAC load calculator (Manual J)](https://www.servicetitan.com/tools/hvac-load-calculator)
- [ProCalcLab room AC calculator](https://procalclab.com/room-area-air-conditioning-calculator/)

**Explorable explanations** — the Bret Victor lineage is alive but doesn't cover building thermal physics:

- [Awesome explorables (curated list)](https://github.com/blob42/awesome-explorables) — covers climate, epidemiology, neural nets, evolution. Nothing on building thermal physics.
- [The rise of explorable explanations — Maarten Lambrechts](https://www.maartenlambrechts.com/2015/03/04/the-rise-of-explorable-explanations.html)
- [Bret Victor — Wikipedia](https://en.wikipedia.org/wiki/Bret_Victor)
- [A Pedagogical "Toy" Climate Model (arXiv)](https://arxiv.org/abs/1002.1672) — closest neighbor in spirit, but atmosphere-scale

**Thermal-mass advocacy sites** — all explain in prose with static diagrams. None let you tweak sliders and see τ change:

- [YourHome — thermal mass guide (AU government)](https://www.yourhome.gov.au/passive-design/thermal-mass)
- [Rise — thermal mass in the home](https://www.buildwithrise.com/stories/thermal-mass-in-the-home)
- [Hogan Architects — thermal mass](https://www.hoganbuildings.com/past-thoughts/2023/2/20/thermal-mass)
