# Section I — Multi-Armed Bandit (Explore/Exploit)

Frames the weekly claim as a bandit over Section A archetypes. Thompson sampling and epsilon-greedy maintain Beta posteriors on each archetype's add-quality and choose which arm (player type profile) to claim from.

## 2026 (primary)

### Batters

- Context arms (archetypes): **3** | rows: **113** | base top-rate: **0.50**
- Contextual expected-reward rank-biserial r = `0.241` (does the cluster add-quality estimate rank top pickups above bottom?)

**Arm (archetype) posteriors:**

| Arm | n | top | bottom | posterior mean | Thompson pick-share |
|-----|---|-----|--------|----------------|---------------------|
| 0 | 18 | 7 | 3 | 0.67 | 0.55 |
| 1 | 73 | 13 | 20 | 0.40 | 0.01 |
| 2 | 22 | 6 | 3 | 0.64 | 0.45 |

| Policy | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| Epsilon-greedy (exploit arms) | 0.65 | 0.44 | 0.53 | 1.30 | 15 | 8 | 19 |
| Thompson (single best arm) | 0.64 | 0.26 | 0.37 | 1.29 | 9 | 5 | 25 |

### Pitchers

- Context arms (archetypes): **3** | rows: **109** | base top-rate: **0.50**
- Contextual expected-reward rank-biserial r = `0.525` (does the cluster add-quality estimate rank top pickups above bottom?)

**Arm (archetype) posteriors:**

| Arm | n | top | bottom | posterior mean | Thompson pick-share |
|-----|---|-----|--------|----------------|---------------------|
| 0 | 38 | 15 | 6 | 0.70 | 0.98 |
| 1 | 11 | 0 | 4 | 0.17 | 0.00 |
| 2 | 60 | 11 | 18 | 0.39 | 0.01 |

| Policy | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| Epsilon-greedy (exploit arms) | 0.73 | 0.52 | 0.60 | 1.45 | 16 | 6 | 15 |
| Thompson (single best arm) | 0.73 | 0.52 | 0.60 | 1.45 | 16 | 6 | 15 |

---

## 2025 (cross-season)

### Batters

- Context arms (archetypes): **6** | rows: **209** | base top-rate: **0.47**
- Contextual expected-reward rank-biserial r = `0.828` (does the cluster add-quality estimate rank top pickups above bottom?)

**Arm (archetype) posteriors:**

| Arm | n | top | bottom | posterior mean | Thompson pick-share |
|-----|---|-----|--------|----------------|---------------------|
| 0 | 51 | 5 | 9 | 0.38 | 0.00 |
| 1 | 46 | 23 | 2 | 0.89 | 0.78 |
| 2 | 18 | 3 | 3 | 0.50 | 0.00 |
| 3 | 15 | 4 | 2 | 0.62 | 0.04 |
| 4 | 32 | 0 | 30 | 0.03 | 0.00 |
| 5 | 47 | 18 | 4 | 0.79 | 0.17 |

| Policy | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| Epsilon-greedy (exploit arms) | 0.77 | 0.89 | 0.83 | 1.64 | 51 | 15 | 6 |
| Thompson (single best arm) | 0.90 | 0.46 | 0.60 | 1.90 | 26 | 3 | 31 |

### Pitchers

- Context arms (archetypes): **3** | rows: **135** | base top-rate: **0.50**
- Contextual expected-reward rank-biserial r = `0.406` (does the cluster add-quality estimate rank top pickups above bottom?)

**Arm (archetype) posteriors:**

| Arm | n | top | bottom | posterior mean | Thompson pick-share |
|-----|---|-----|--------|----------------|---------------------|
| 0 | 27 | 4 | 10 | 0.31 | 0.00 |
| 1 | 43 | 20 | 3 | 0.84 | 1.00 |
| 2 | 65 | 12 | 22 | 0.36 | 0.00 |

| Policy | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| Epsilon-greedy (exploit arms) | 0.77 | 0.54 | 0.63 | 1.54 | 20 | 6 | 17 |
| Thompson (single best arm) | 0.77 | 0.54 | 0.63 | 1.54 | 20 | 6 | 17 |
