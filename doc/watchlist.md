# Watchlist — theory videos and MOOCs

Curated free video resources for the theory behind grey-box thermal
identification, Bayesian state-space models, and switching dynamical
systems. Tuned to this project — see
[../miniha/th_models/model_families.md](../miniha/th_models/model_families.md)
and [../miniha/th_models/model_theory_tvp.md](../miniha/th_models/model_theory_tvp.md)
for the methods these videos cover.

Target audience: engineer with a physics/math background, comfortable
with ODEs and probability, wants the actual math (not a 5-minute intro).

## Top 5 — if you only watch these

1. **Statistical Rethinking — Richard McElreath (MPI)**
   - [2023 playlist](https://www.youtube.com/playlist?list=PLDcUM9US4XdPz-KxHM4XHt7uUVGWWVSus)
     · [channel](https://www.youtube.com/channel/UCNJK6_DZvcMqNSzQdEkzvzA/playlists)
   - ~20 lectures × 1 h. EN, graduate intro.
   - The clearest video introduction to Bayesian workflow, priors,
     multilevel models, posterior predictive checks. Mental scaffolding
     before touching Stan/PyMC. **Start here.**

2. **Bayesian Filtering and Smoothing — Simo Särkkä (Aalto ELEC-E8106)**
   - [course page](https://mycourses.aalto.fi/course/view.php?id=39443)
     · [book PDF](https://users.aalto.fi/~ssarkka/pub/bfs_book_2023_online.pdf)
     · [code](https://github.com/EEA-sensors/Bayesian-Filtering-and-Smoothing)
   - ~12 lectures. EN, graduate.
   - LDS → KF → EKF/UKF → particle filters → smoothers, rigorous
     Bayesian derivation. The single most relevant course for this
     stack.

3. **Kalman Filter playlist — Steve Brunton (UW)**
   - [playlist](https://www.youtube.com/playlist?list=PL96NqWbg_XU-0EGZH-a0kcJyRO9h3Fhgn)
     · [channel](https://www.youtube.com/c/Eigensteve/playlists)
   - Short whiteboard videos, ~15–25 min each. EN, practitioner.
   - Best intuition for KF, observers, balanced reduction, OKID,
     DMD/SINDy. Pair with Särkkä for the math.

4. **Bayesian Data Analysis — Aki Vehtari (Aalto CS-E5710)**
   - [course site](https://avehtari.github.io/BDA_course_Aalto/)
     · [YouTube playlist](https://www.youtube.com/playlist?list=PLBqnAso5Dy7O0IVoVn2b-WtetXQk5CDk6)
   - 12 weeks, ~24 videos. EN, graduate.
   - Diagnostics, LOO-CV, model comparison — what you need to defend a
     grey-box fit.

5. **Cours Thermique du Bâtiment — Christian Ghiaus (CETHIL Lyon)**
   - [playlist](https://www.youtube.com/playlist?list=PL_H3px_X_iX4sp7WfNbDH-_h7BHrhnHAP)
     · [analogie électrique RC](https://www.youtube.com/watch?v=FSd0qlY6uOQ)
   - **FR**, graduate.
   - Closest thing to a French academic course on the exact topic.
     Same Ghiaus listed in [landscape.md](landscape.md) as a cold-email
     target.

## State-space, Kalman, particle filters

- **Linear Dynamical Systems EE263 — Stephen Boyd (Stanford)**
  - [playlist](https://www.youtube.com/playlist?list=PL06960BA52D0DB32B)
    · [EE363 slides extension](https://stanford.edu/class/ee363/lectures.html)
  - 20 × 75 min. EN, graduate.
  - LDS / observer / least-squares bedrock. EE363 extends to LQG/KF.
- **Artificial Intelligence for Robotics — Sebastian Thrun (Udacity CS373)**
  - Free archived course.
  - EN, undergrad.
  - Cleanest hands-on introduction to particle filters.

## HMM, switching, SLDS — the rSLDS direction

- **State Space Models for Natural and Artificial Intelligence —
  Scott Linderman (Kempner Seminar)**
  - [video](https://www.youtube.com/watch?v=2hL6Keqp_xs)
  - ~1 h. EN, graduate seminar.
- **Nuts and Bolts of Modern SSMs Part I — Scott Linderman (CCN tutorial)**
  - [video](https://www.youtube.com/watch?v=9TwfcHbBbeY)
  - ~1 h. EN, graduate.
  - Clearest spoken explanation of rSLDS and modern deep SSMs.
- **Probabilistic Graphical Models — Daphne Koller (Stanford / Coursera)**
  - [specialization](https://www.coursera.org/specializations/probabilistic-graphical-models)
    · [full playlist mirror](https://www.youtube.com/playlist?list=PLBAGcD3siRDjiQ5VZQ8t0C7jkHQ8fhuq8)
  - 3 courses × 7–8 weeks. EN, graduate.
  - Canonical HMM/DBN material.

## Bayesian / probabilistic programming

- **Scalable Bayesian Inference with HMC — Michael Betancourt**
  - [Part 1](https://www.youtube.com/watch?v=pHsuIaPbNbY)
    · [Sydney talk](https://www.youtube.com/watch?v=_fnDz2Bz3h8)
  - 1–2 h talks. EN, advanced.
  - Geometry of HMC — useful when Stan diverges on the TVP RC model.
- **Bayesian Methods for Machine Learning — HSE (Coursera)**
  - [course](https://www.coursera.org/learn/bayesian-methods-in-machine-learning)
  - 6 weeks. EN, graduate intro.
  - VI, sampling, Gaussian processes.

## Grey-box building thermal (the narrow niche)

- **CTSM-R materials — Henrik Madsen (DTU)**
  - [ctsm.info](https://ctsm.info/)
    · [henrikmadsen.org](http://henrikmadsen.org/)
  - Slides + scattered seminars. EN, graduate seminar. **No full MOOC.**
  - The reference for stochastic grey-box building ID.

## System identification (classical)

- **System Identification playlist — Lennart Ljung**
  - [YouTube](https://www.youtube.com/playlist?list=PLn8PRpmsu08qoV9Nca1_Pv62sjGoDNQuK)
    · [MATLAB series](https://www.mathworks.com/videos/series/lennart-ljung-on-system-identification-toolbox-97005.html)
  - Short videos. EN, practitioner.
  - Vendor-flavoured but Ljung is Ljung.

## Foundations (refreshers)

- **Probabilistic Systems Analysis — Tsitsiklis (MIT 6.041 OCW)**
  - [video lectures](https://ocw.mit.edu/courses/6-041-probabilistic-systems-analysis-and-applied-probability-fall-2010/video_galleries/video-lectures/)
  - EN, undergrad.
  - Clean Bayesian estimation / LLS / Kalman lecture included.
- **Des probabilités à l'estimation bayésienne — Inria (FUN-MOOC)**
  - [course](https://www.fun-mooc.fr/en/cours/des-probabilites-a-lestimation-bayesienne/)
  - 14 modules. **FR**, intro.
  - Good French entry point to Bayesian estimation.

## Notable gap

**There is no free MOOC on grey-box / stochastic identification of
buildings.** The DTU/Madsen group publishes papers, the CTSM-R manual,
and conference talks — but no recorded multi-lecture course. IBPSA
conferences are not systematically archived on YouTube. The Ghiaus INSA
playlist is the closest French-language analogue but stops at thermal
physics, not stochastic ID. Nothing on FUN-MOOC, edX, or Coursera covers
RC-network identification specifically.

**Bridging the gap = stitching together**: Särkkä (filtering) + Ljung
(classical ID) + Madsen's papers (grey-box buildings) + Ghiaus (physics).
That stitched curriculum *is* the project.

## Suggested viewing order

For the next few weeks alongside `toy_tvp/` v1:

1. **McElreath lectures 1–6** — priors, posterior, MCMC. Makes Stan less
   mysterious.
2. **Brunton KF playlist** (~1–2 h total) — KF intuition.
3. **Särkkä Lectures 1–4** — state-space, KF, EKF. Math underneath.
4. **Ghiaus RC analogy lecture** (FR, ~1 h) — local-language
   reinforcement of physics you already know.
5. **Linderman SSM Part I** — once v1 works, for the SLDS roadmap from
   [model_families.md](../miniha/th_models/model_families.md).

~20 h total. Feasible alongside coding.
