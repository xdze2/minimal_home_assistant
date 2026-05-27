# Cool Inertia — Proposition

App web mobile-first, en français, qui répond à : _« Comment je rafraîchis ma pièce ce soir avec de la ventilation naturelle ? »_

Ton : weather app rencontre jouet de physique. Inspiration Bret Victor (dynamic medium). Pas un outil d'audit énergétique.

## L'idée centrale

Rendre visible la chose contre-intuitive : **l'air est une plume, les murs sont un camion**. Tout découle de là.

Ancres d'ordre de grandeur (pièce 4×5×2.4 m, briques) :

- Masse d'air : **~58 kg**
- Masse active des murs (peau de 12 cm) : **~10 000 kg**
- Rapport : **~200×**
- Énergie à extraire pour ΔT=10°C : **~23 kWh** (≈ une journée de frigo)
- Constante de temps τ avec ventilation correcte : **~5 h**

## Physique (volontairement simple)

1. **Épaisseur active** (profondeur de pénétration sur cycle 24h) :
   `d = √(α·T/π)` → ~12 cm pour brique, ~7 cm bois, ~15 cm béton.

2. **Masse active** : `m = ρ · A_murs · d`. Capacité thermique : `C = m·c`.

3. **Couche limite** : seuil ~1 m/s le long des parois.
   - Lent (laminaire) : h ≈ 2 W/m²·K
   - Turbulent : h ≈ 10 W/m²·K
   - Facteur 5 — c'est le levier le plus contre-intuitif.

4. **Décroissance exponentielle** :
   `T_int(t) = T_ext + (T_int₀ - T_ext) · exp(-t/τ)`
   avec `τ = (m·c) / (h·A)`.

5. **T_ext variable** (plus tard) : ODE simple, Euler explicite pas de 5 min,
   `dT_int/dt = (T_ext(t) - T_int) / τ`.

## Entrées (minimales)

- Pièce : a, b, h (3 nombres)
- Type de mur : léger (plâtre/bois) / brique / pierre-béton
- T° intérieure actuelle
- T° extérieure de la nuit

## Sorties

- Débit d'air nécessaire (m³/h) et renouvellement d'air (vol/h)
- Équivalent en ventilateurs concrets (voir échelle ci-dessous)
- Courbe T_int(t) sur la nuit
- Valeurs physiques brutes toujours visibles

## Garder visible les valeurs physiques

Principe : ne jamais cacher derrière une jauge. Toujours afficher :

```
Murs actifs
  Masse :           9 880 kg
  Capacité therm. : 8 300 kJ/K     (= m·c)
  Surface :         43 m²
  Épaisseur active : 12 cm
  Énergie à extraire (ΔT=10°) : 83 MJ ≈ 23 kWh

Air de la pièce
  Volume : 48 m³
  Masse :  58 kg
  Capacité therm. : 58 kJ/K
```

Visuellement : barres côte à côte pour `masse (kg)` et `capacité thermique (kJ/K)`. Les rapports diffèrent (c_brique ≠ c_air) — ça se voit.

## Échelle de ventilateurs (ordres de grandeur)

À montrer comme une frise, du plus faible au plus fort :

| Engin                                      | Débit ≈      |
| ------------------------------------------ | ------------ |
| Aération naturelle (fenêtre entrouverte)   | ~30 m³/h     |
| VMC simple flux (extraction salle de bain) | ~90 m³/h     |
| 1 ventilo PC 140mm                         | ~90 m³/h     |
| Ventilateur de table                       | ~500 m³/h    |
| Brasseur d'air plafond                     | ~2 000 m³/h  |
| Brasseur drum 30 cm (type Domair)          | ~3 300 m³/h  |
| Extracteur gaine industriel                | ~5 000+ m³/h |

Le calcul affiche le débit cible et **surligne où on tombe** sur cette frise. Ça ancre les m³/h dans des objets concrets.

## Décomposition mur par mur

**Pas dans le MVP.** Mais préparer le code pour l'ajouter.

La question physique utile n'est pas « sol / plafond / murs » mais **« quelles surfaces ont un puits froid de l'autre côté ? »** :

- Sol dalle béton : couplé au sol froid → aide
- Plafond toit : ennemi (chaud toute la nuit)
- Murs extérieurs sud/ouest : cuits toute la journée
- Murs intérieurs : pas de ΔT, ne participent quasi pas

V2 : toggle par surface (`extérieur / intérieur / sol / toit`) qui ajuste l'aire effective et α/c selon le matériau.

## T_ext variable

**Pas dans le MVP.** Roadmap :

1. **MVP** : T_ext constante (un seul nombre saisi).
2. **V2** : scénario sinusoïdal — `T_ext(t) = T_moy + A·cos(2π(t-t_pic)/24)`, deux sliders (amplitude, heure de pic). C'est le jouet Bret Victor — on tire l'amplitude, on voit l'intérieur s'amortir et déphaser.
3. **V3** : Open-Meteo (gratuit, sans clé), liste de villes en dur (Paris, Lyon, Marseille, Toulouse, Bordeaux, Lille, Strasbourg, Nantes, Montpellier, Nice…). Endpoint `hourly=temperature_2m`, prochaines 24h.

Bonus pédagogique V2/V3 : indiquer **quand ouvrir/fermer** — fan ON quand T_ext < T_int, OFF sinon.

## UI mobile (vertical, pile)

```
┌──────────────────────┐
│ Inertie nocturne     │
├──────────────────────┤
│ Pièce                │
│ 4m × 5m × 2.4m  [✎]  │
│                      │
│ Murs : ◯léger        │
│        ●brique       │
│        ◯pierre       │
├──────────────────────┤
│ [SVG : coupe pièce,  │
│  peau active brille] │
├──────────────────────┤
│ Air     │ Murs       │
│ 58 kg   │ 9 880 kg   │
│ ▏       │ ███████    │
├──────────────────────┤
│ T_int : 28°C  [slider]│
│ T_ext : 18°C  [slider]│
├──────────────────────┤
│ Ventilateur :        │
│ ▬▬▬●────  500 m³/h   │
│ ≈ ventilo de table   │
│                      │
│ τ = 5.4 h            │
│ ┌────────────────┐   │
│ │╲___            │   │ ← T_int(t)
│ │    ╲___        │   │
│ └────────────────┘   │
│                      │
│ Dans 6h : 22.3°C     │
│ Énergie sortie : 18 kWh│
└──────────────────────┘
```

Cibles tap larges, sliders plutôt que knobs, tout en français, unités SI.

## Stack

**Vanilla JS.** Un seul fichier HTML, un peu de CSS, SVG inline pour les graphes. ~300 lignes. Pas de build, pas de framework, pas de dépendances.

Pourquoi pas Svelte : pour cette taille (3 sliders, 2 courbes, ~10 nombres dérivés), le reactivity à la main est trivial — `recompute()` sur chaque `input`. Svelte ajoute un build step pour zéro gain. À reconsidérer si V2/V3 fait gonfler les états.

Hébergement : statique pur, n'importe quel S3 / Pages / Netlify.

## Plan d'itérations

**MVP (v0)** — un fichier, une journée :

- 3 sliders pièce + sélecteur matériau
- 2 sliders température (T_int, T_ext constants)
- 1 slider ventilateur en m³/h
- Calculs : épaisseur active, masses, τ, énergie
- Courbe exponentielle T_int(t) sur 12h
- Frise des ventilateurs avec marqueur
- Tous les nombres physiques affichés

**V1** — peaufinage :

- Coupe SVG de la pièce avec peau active animée
- Barres masse / capacité thermique
- Petit encart « couche limite » : laminaire vs turbulent, h qui saute

**V2** — T_ext sinusoïdale :

- Sliders amplitude + heure de pic
- ODE Euler explicite
- Indicateur ouvrir/fermer fenêtre
- Préparer hooks pour décomposition par surface

**V3** — données réelles :

- Liste de villes en dur
- Open-Meteo fetch
- État partageable via URL

**V4** (peut-être) — décomposition mur par mur, matériau par surface.

## Questions ouvertes

- Nommer le projet ? `cool_inertia` est sympa en interne, mais titre français pour l'UI ? « Inertie nocturne » / « Fraîcheur de nuit » / « Ventiler malin » ? "Inertie nocturne"
- Pour la frise ventilateurs, garder les marques (Domair, Arctic) ou rester génériques ? rester génériques
- Mode « explication » avec les formules visibles (clic sur τ → popup `τ = m·c/h·A`) ou rester silencieux ? TBD
