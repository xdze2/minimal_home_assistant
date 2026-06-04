# Field landscape — drivers, positioning, contacts

Where the grey-box building thermal identification field is going, who to
talk to in France about it, and what positionings look viable for a
project like this one in the next 18 months.

## 1. The four candidate driving forces, ranked by my read

### A. Data availability — real but mostly solved

Cheap sensors (ESP32 + DS18B20 ≈ €5), Home Assistant, Matter/Thread,
smart-thermostat APIs (Netatmo, Tado, Nest, Daikin Cloud), national-grid
smart meters (Linky in France: 30-min electricity with consent). Tertiary
side: BACnet/Modbus exports are standard.

The driver here is **consent and API access, not hardware**. Linky data
is theoretically available, practically gated by Enedis flows.
Manufacturer APIs are reversed or grudgingly opened. The real lever is
regulatory/legal access to data that already exists (RGPD, EPBD, French
décret tertiaire).

**Verdict:** diminishing returns. Most homes that _will_ be instrumented
in the next 5 years already could be today. Hardware is not the
bottleneck.

### B. Compute / better frameworks / AI — most over-hyped

PyMC / NumPyro / Stan are genuinely better than 5 years ago. JAX makes
Bayesian SSMs tractable. Foundation models for time series (Chronos,
TimesFM, Moirai) exist.

But: this problem is **not compute-bound**. A 2R2C fit on a year of data
runs in 100 ms. Bayesian in 30 s. SLDS in minutes. Methods that matter
(grey-box, Bayesian, switching) have existed since the 90s.

LLMs add value at the **interpretation** ("explain why the bedroom is
colder") and **configuration** layer ("set up a model from a
description") — that's UX, not method.

Foundation time-series models predict well and tell you nothing — they
are anti-explainability, exactly opposite to what this project wants.

**Verdict:** marginal.

### C. Software / UX — the biggest underexploited lever

The methods exist. The data is increasingly available. **What's missing
is the layer that turns a non-expert's house into an identified model in
10 minutes.**

Today this requires: writing YAML, knowing what a time constant is,
choosing between 1R1C / 2R2C, interpreting residuals. PhD-level workflow.

What would change the field:

- **Plug-and-play identification** — connect to Home Assistant, pick a
  room, get a calibrated RC model with uncertainty
- **Automated regime detection** — "your residuals jump at 7am, probably
  heating, want me to add it as input?"
- **Counterfactual explanations** — "if you double wall R, you save
  X kWh ± Y" (this is the actual user-facing question)
- **Tooling that closes the loop with renovation** — link the identified
  model to BIM, to ADEME aid simulation, to RGE quotes

CTSM-R has existed for 20+ years and almost nobody outside DTU uses it.
That's a UX failure, not a method failure.

**Verdict:** biggest lever. **Method maturity vastly outpaces tool
maturity.**

### D. Investment in renovation — the real binding constraint

For an individual homeowner, the decision "should I insulate the north
wall?" is 80% driven by capital cost (€10–50k), available aid
(MaPrimeRénov', CEE, eco-PTZ), trust in the RGE artisan, and disruption
tolerance. **20%** by quality of information.

Macro: France needs ~700k thermal renovations/year by 2030, currently
delivers ~70k complete ones. The gap is **financing and labour, not
information**.

**But** — better information unlocks better financing:

- Energy Performance Contracts (CPE) require trusted measurement
- Tiers-financement (ETP-style) needs credible kWh prediction for bonds
- Insurance products on renovation outcomes need measured baselines
- EPBD recast mandates smart-readiness indicators that need data

Information matters as the **substrate for new financial products**, not
as a homeowner-facing decision aid.

## 2. What is actually driving the field, next 5 years

In rough order of importance:

1. **Regulation forcing measurement.** EU EPBD recast (2024), French
   décret tertiaire / Eco Énergie Tertiaire, Energy Performance Contracts
   for public buildings. These create a **buyer** for grey-box models —
   facility managers and ESCOs who _legally must_ produce measured-savings
   reports.

2. **ESCO economics.** EnergieSprong-style "renovation guarantee" models
   (NL/UK/FR). The whole-stack play: finance + renovation + monitoring +
   measured-savings guarantee. The guarantee cannot be written without
   the model.

3. **Flexibility-market aggregation.** As electricity becomes variable
   (PV, wind), predictable load shifting becomes valuable. A grey-box
   model is a prerequisite for selling **thermal flexibility** into
   capacity markets. RTE has experiments. Voltalis is the early player.

4. **Tool consolidation.** Whoever builds the "Home Assistant of grey-box
   thermal" — open-source, hackable, one-click identification — captures
   the prosumer + small-tertiary segment. Currently no one has.

## 3. Viable positionings for this project

In decreasing margin / increasing reach:

- **B2B SaaS for ESCOs and facility managers.** Plumbing for M&V reports
  and CPEs. Boring, real revenue.
- **Renovation-decision support tied to financing.** Partner with banks
  or aid programs to produce model-backed renovation recommendations.
  High value-per-customer, slow sales cycle.
- **Flexibility-market angle.** Sell aggregated thermal load using
  identified models. Capital-intensive, regulatory-complex.
- **Open-source prosumer tool.** Home Assistant integration. Low margin,
  high reach. Defensible if you become _the_ default.

## 4. One contrarian thought worth keeping

The single biggest unsolved technical problem in the field is
**transfer / generalisation across buildings**.

Every paper fits one building. **Nobody has a credible way to say "we
calibrated 500 houses, here is the distribution of parameters, here is
how to use it as a prior for the 501st."** This is the **hierarchical
Bayesian** angle that almost no one in building physics has done well,
and it is a natural fit for the regulator's question ("what is the
typical performance gap between EPC and reality across all post-1990
French apartments?").

That is the intersection where a technical edge (hierarchical model +
auto-identification on a fleet) and a real buyer (ADEME, ANAH, an ESCO
with 10k buildings) align.

Practical implication for the next 18 months: **build the tool for one
room, fast, in the open** (Home Assistant integration), use it to grow a
dataset, and the hierarchical model on that dataset becomes the eventual
moat.

## 5. French research labs to contact

### Toulouse / Albi (local anchors)

- **LMDC — Laboratoire Matériaux et Durabilité des Constructions**
  (INSA Toulouse + UT3, UMR). Inverse identification of building thermal
  characteristics with RC networks. Strongest local match.
  - Contacts: **Stéphane Ginestet** (RC identification, Energy and
    Buildings 2013 +), **Matthieu Labat** (hygro-thermal envelope)
  - [www-lmdc.insa-toulouse.fr](https://www-lmdc.insa-toulouse.fr)
- **RAPSODEE — IMT Mines Albi** (UMR CNRS 5302). "Sustainable buildings
  & cities" pathway. Less RC-identification specifically, but a natural
  Albi anchor.
  - [rapsodee.imt-mines-albi.fr](https://rapsodee.imt-mines-albi.fr/en)
- **LAAS-CNRS** (Toulouse). MAC / DISCO groups: nonlinear MPC, observer
  design, Kalman/UKF. Approach as a **methods partner**, not a building
  partner.

### Where the actual French expertise lives (Alpine corridor + Paris)

- **CEA INES** (Chambéry). **The #1 lab to contact.** Closest French
  analogue to DTU's CTSM tradition.
  - **Étienne Wurtz** — canonical 6R2C grey-box calibration (IBPSA 2015)
    [CEA Liten profile](https://liten.cea.fr/cea-tech/liten/english/Pages/CEA-Liten/Fellow/WURTZ-Etienne.aspx)
  - **Adrien Brun** — automated stochastic grey-box calibration (2024,
    [HAL cea-04653216](https://cea.hal.science/cea-04653216v1/document))
- **CETHIL** (INSA Lyon, UMR 5008). Highest-profile French academic in
  this niche.
  - **Christian Ghiaus** — thermal-network state-space, RC ID, MPC for
    HVAC, 30 years of work
    [HAL CV](https://cv.hal.science/cghiaus)
- **LOCIE** (Université Savoie Mont Blanc, Chambéry).
  - **Monika Woloszyn** (coupled heat/mass, envelope ID)
    [profile](https://www.univ-smb.fr/locie/en/monika-woloszyn-enseignante-chercheuse-membre-du-locie/)
  - **Gilles Fraisse** (building dynamics), **Jeanne Goffart**
    (sensitivity analysis, calibration)
- **G-SCOP** (Grenoble INP). Closest to the regime-switching /
  occupancy angle.
  - **Stéphane Ploix** — inverse modelling, occupancy via Bayesian
    networks, Predis-MHI living lab
    [profile](https://g-scop.grenoble-inp.fr/fr/laboratoire/ploix-stephane)
- **G2Elab** (Grenoble INP / CNRS).
  - **Frédéric Wurtz** (DR CNRS) — building energy + grid + storage,
    GreEn-ER living lab
    [profile](https://g2elab.grenoble-inp.fr/fr/le-laboratoire/wurtz-frederic)
- **Mines Paris–PSL, CES** (Sophia Antipolis / Paris). Lab Kocliko spun
  out of.
  - **Bruno Peuportier** (COMFIE simulator, life cycle + thermal),
    **Pascal Stabat**, **Dominique Marchio** (HVAC systems)
    [team page](https://www.ces.minesparis.psl.eu/Groupes-de-recherche/ETB/)
- **LaSIE** (La Rochelle, UMR 7356). **Patrick Salagnac** — inverse
  methods for multilayer walls.
  [profile](https://lasie.univ-larochelle.fr/salagnac-patrick)
- **IMT Atlantique DSEE** (Nantes). Hierarchical grey/black-box internal
  models for MPC. **Bruno Lacarrière** on district heating.
- **PIMENT** (Université de La Réunion). **François Garde**,
  **Laetitia Adelard** — tropical building physics, CODYRUN. Relevant if
  overseas scope.

## 6. French startup landscape (competition / reference)

- **Kocliko** (Paris, Mines Paris–PSL spinoff, partnered with Idex) —
  digital twins + AI for collective heating. Closest French commercial
  analogue. [psl.eu/.../kocliko](https://psl.eu/en/startup-des-laboratoires/kocliko)
- **Vesta System** (Grenoble) — building energy optimisation, G2Elab
  heritage. [vesta-system.fr](https://www.vesta-system.fr/)
- **Accenta** (Paris) — geothermal storage + AI plant-side MPC.
- **BeeBryte** (Lyon / Singapore) — predictive HVAC-R control.
- **Voltalis**, **DeltaDore**, **Enerbrain** — building-side flexibility,
  more product than R&D.

Model is **commercially viable but already has incumbents.**
Differentiation needs to come from a vertical (collective housing,
social landlords, tertiary) or a technical edge (online identification,
regime switching, occupancy-aware, hierarchical-across-fleet) — not from
"we do RC + MPC".

## 7. Toulouse-region funding and incubators

- **Nubbo** (Toulouse) — B2B incubator, "à mission". Natural early entry
  once the project has a product hypothesis. [nubbo.co](https://nubbo.co/)
- **SATT Toulouse Tech Transfer** — maturation funding for INSA / UT3 /
  IMT Albi IP. Lever for any LMDC- or RAPSODEE-based deeptech.
- **ADEME Occitanie** (DR Toulouse) — recurrent AAPs on building energy
  management, MPC, instrumentation. France 2030 envelope ≈ 1.7 B€ for
  buildings.
- **Région Occitanie** — REPOS 2050 plan, ~52 000 renovations/year
  target, dedicated energy-efficiency AAPs.
- **IRT Saint Exupéry** — aero-focused, but embedded-systems competence
  reusable. [irt-saintexupery.com](https://www.irt-saintexupery.com/)
- **IoT Valley (Labège)** — sensor / data acquisition side, not
  modelling.
- Generic later-stage: **Bpifrance Deeptech**, **i-Lab**,
  **EIC Accelerator**.

## 8. Pragmatic 18-month plan

1. **Cold-email Adrien Brun (CEA INES) and Christian Ghiaus (CETHIL)**
   with a focused 1-page note showing current results (the residual
   diagnosis on the chambre week is good material — it shows
   identification understanding, not just curve-fitting). Ask for 30 min
   to discuss whether the regime-switching direction overlaps with
   anything they're doing.
2. **Meet Ginestet (LMDC)** in parallel for local academic anchoring —
   relevant for CIFRE pipeline or SATT maturation later.
3. **Build the open-source tool for one room, fast.** Home Assistant
   integration is the natural distribution channel.
4. **Talk to Nubbo** once the product hypothesis is clearer (not yet —
   still at the research stage).
5. **Read Kocliko's public material carefully** — it tells you what they
   _don't_ do, which is where the differentiation has to live.
