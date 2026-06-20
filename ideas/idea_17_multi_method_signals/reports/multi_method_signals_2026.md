# Idea 17 — Multi-Method Waiver Signal Consolidation

**Analysis date:** 2026-06-19  
Runs all nine method classes (A–I) on the Idea 15 labeled pickup set, scores each player by how many independent methods flag them (the **multi-method confidence score**), and validates that score against composite_z. Method G (market) is reported but excluded from the default score (validated lift < 1 — ownership hype attaches to busts too).

> All methods are unsupervised or relative; the table values are in-sample on the labeled set, with 2025 used to confirm the method ranking is stable.

---

## 2026 (primary)

### Batters

- Eval pool: **34** top + **34** bottom | base top-rate: **0.50**
- Confidence-score rank-biserial r = `0.471` (higher score → more likely top quartile)

**Individual method predictive power (in-sample):**

| Method | Flagged | Precision | Recall | F1 | Lift |
|--------|---------|-----------|--------|----|------|
| A_clustering | 39 | 0.67 | 0.76 | 0.71 | 1.33 |
| B_changepoint | 16 | 0.56 | 0.26 | 0.36 | 1.12 |
| C_bayesian | 16 | 0.50 | 0.24 | 0.32 | 1.00 |
| D_sequential | 5 | 1.00 | 0.15 | 0.26 | 2.00 |
| E_anomaly | 7 | 0.71 | 0.15 | 0.24 | 1.43 |
| F_forecast | 16 | 0.75 | 0.35 | 0.48 | 1.50 |
| G_market _(weak)_ | 8 | 0.25 | 0.06 | 0.10 | 0.50 |
| H_opportunity | 23 | 0.70 | 0.47 | 0.56 | 1.39 |
| I_bandit | 37 | 0.68 | 0.74 | 0.70 | 1.35 |

**Multi-method confidence score (excludes weak G):**

| Score >= | n flagged (top+bottom) | Precision | Recall | Lift |
|----------|------------------------|-----------|--------|------|
| 1 | 45 | 0.60 | 0.79 | 1.20 |
| 2 | 44 | 0.61 | 0.79 | 1.23 |
| 3 | 38 | 0.66 | 0.74 | 1.32 |
| 4 | 19 | 0.84 | 0.47 | 1.68 |
| 5 | 10 | 0.90 | 0.26 | 1.80 |
| 6 | 3 | 0.67 | 0.06 | 1.33 |

**Fusion with Idea 16 supervised rule:**

- Idea 16 rule: `ops_14d` >= 0.320 (P=0.58, R=0.76, lift=1.16)
- **Highest-confidence tier** (Idea 16 rule AND >=3 Idea 17 methods): 38 flagged, P=0.66, lift=1.32

**Retrospective audit — top pickups & methods that fired:**

| Player | Acq Date | Z | Score | Methods Fired |
|--------|----------|---|-------|---------------|
| Jordan Walker | 2026-03-30 | 19.84 | 3 | A, E, I |
| Miguel Vargas | 2026-03-30 | 19.39 | 2 | H, I |
| Liam Hicks | 2026-04-02 | 11.11 | 5 | A, C, E, F, I |
| Bryson Stott | 2026-03-23 | 10.20 | 0 | — |
| Brandon Marsh | 2026-04-15 | 9.12 | 4 | A, B, H, I |
| Wilyer Abreu | 2026-03-26 | 8.16 | 0 | — |
| Casey Schmitt | 2026-05-05 | 7.62 | 6 | A, B, C, F, H, I |
| Zack Gelof | 2026-05-09 | 7.53 | 5 | A, C, F, H, I |
| Luke Raley | 2026-04-15 | 6.53 | 5 | A, C, D, F, I |
| Ivan Herrera | 2026-04-27 | 6.43 | 5 | A, B, C, H, I |
| Dillon Dingler | 2026-04-04 | 6.43 | 5 | A, C, F, H, I |
| Mickey Moniak | 2026-04-12 | 6.14 | 4 | A, E, F, H |

### Pitchers

- Eval pool: **31** top + **31** bottom | base top-rate: **0.50**
- Confidence-score rank-biserial r = `0.224` (higher score → more likely top quartile)

**Individual method predictive power (in-sample):**

| Method | Flagged | Precision | Recall | F1 | Lift |
|--------|---------|-----------|--------|----|------|
| A_clustering | 27 | 0.67 | 0.58 | 0.62 | 1.33 |
| B_changepoint | 7 | 0.43 | 0.10 | 0.16 | 0.86 |
| C_bayesian | 22 | 0.50 | 0.35 | 0.42 | 1.00 |
| D_sequential | 8 | 0.62 | 0.16 | 0.26 | 1.25 |
| E_anomaly | 8 | 0.62 | 0.16 | 0.26 | 1.25 |
| F_forecast | 17 | 0.53 | 0.29 | 0.38 | 1.06 |
| G_market _(weak)_ | 12 | 0.17 | 0.06 | 0.09 | 0.33 |
| H_opportunity | 21 | 0.62 | 0.42 | 0.50 | 1.24 |
| I_bandit | 29 | 0.69 | 0.65 | 0.67 | 1.38 |

**Multi-method confidence score (excludes weak G):**

| Score >= | n flagged (top+bottom) | Precision | Recall | Lift |
|----------|------------------------|-----------|--------|------|
| 1 | 36 | 0.56 | 0.65 | 1.11 |
| 2 | 32 | 0.59 | 0.61 | 1.19 |
| 3 | 26 | 0.62 | 0.52 | 1.23 |
| 4 | 20 | 0.70 | 0.45 | 1.40 |
| 5 | 15 | 0.73 | 0.35 | 1.47 |
| 6 | 7 | 0.57 | 0.13 | 1.14 |
| 7 | 2 | 0.00 | 0.00 | 0.00 |

**Fusion with Idea 16 supervised rule:**

- Idea 16 rule: `k9_14d` >= 7.425 (P=0.60, R=0.77, lift=1.20)
- **Highest-confidence tier** (Idea 16 rule AND >=3 Idea 17 methods): 21 flagged, P=0.67, lift=1.33

**Retrospective audit — top pickups & methods that fired:**

| Player | Acq Date | Z | Score | Methods Fired |
|--------|----------|---|-------|---------------|
| Erik Sabrowski | 2026-04-01 | 4.52 | 2 | A, I |
| Paul Sewald | 2026-04-05 | 4.37 | 5 | A, C, F, H, I |
| Emerson Hancock | 2026-03-30 | 4.35 | 3 | A, E, I |
| Gregory Soto | 2026-04-07 | 4.11 | 6 | A, C, D, F, H, I |
| Bryan Baker | 2026-04-28 | 3.72 | 5 | A, B, C, H, I |
| Tanner Scott | 2026-04-10 | 3.40 | 6 | A, C, D, F, H, I |
| Louis Varland | 2026-04-15 | 3.39 | 5 | A, C, F, H, I |
| Ian Seymour | 2026-03-23 | 3.25 | 0 | — |
| Payton Tolle | 2026-04-21 | 3.21 | 0 | — |
| Kyle Harrison | 2026-04-29 | 2.87 | 5 | A, B, C, F, I |
| Braxton Ashcraft | 2026-03-25 | 2.79 | 0 | — |
| Michael Wacha | 2026-04-21 | 2.78 | 0 | — |

---

## 2025 (cross-season)

### Batters

- Eval pool: **57** top + **64** bottom | base top-rate: **0.47**
- Confidence-score rank-biserial r = `0.777` (higher score → more likely top quartile)

**Individual method predictive power (in-sample):**

| Method | Flagged | Precision | Recall | F1 | Lift |
|--------|---------|-----------|--------|----|------|
| A_clustering | 66 | 0.77 | 0.89 | 0.83 | 1.64 |
| B_changepoint | 22 | 0.77 | 0.30 | 0.43 | 1.64 |
| C_bayesian | 37 | 0.78 | 0.51 | 0.62 | 1.66 |
| D_sequential | 33 | 0.76 | 0.44 | 0.56 | 1.61 |
| E_anomaly | 33 | 0.82 | 0.47 | 0.60 | 1.74 |
| F_forecast | 41 | 0.83 | 0.60 | 0.69 | 1.76 |
| G_market _(weak)_ | 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| H_opportunity | 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| I_bandit | 67 | 0.78 | 0.91 | 0.84 | 1.65 |

**Multi-method confidence score (excludes weak G):**

| Score >= | n flagged (top+bottom) | Precision | Recall | Lift |
|----------|------------------------|-----------|--------|------|
| 1 | 74 | 0.73 | 0.95 | 1.55 |
| 2 | 72 | 0.74 | 0.93 | 1.56 |
| 3 | 61 | 0.77 | 0.82 | 1.64 |
| 4 | 49 | 0.82 | 0.70 | 1.73 |
| 5 | 29 | 0.97 | 0.49 | 2.05 |
| 6 | 12 | 0.92 | 0.19 | 1.95 |
| 7 | 2 | 1.00 | 0.04 | 2.12 |

**Fusion with Idea 16 supervised rule:**

- Idea 16 rule: `ops_14d` >= 0.541 (P=0.72, R=0.91, lift=1.53)
- **Highest-confidence tier** (Idea 16 rule AND >=3 Idea 17 methods): 61 flagged, P=0.77, lift=1.64

**Retrospective audit — top pickups & methods that fired:**

| Player | Acq Date | Z | Score | Methods Fired |
|--------|----------|---|-------|---------------|
| Geraldo Perdomo | 2025-04-16 | 18.33 | 6 | A, B, C, E, F, I |
| Nick Kurtz | 2025-04-26 | 14.89 | 2 | A, I |
| Andy Pages | 2025-05-08 | 13.37 | 6 | A, C, D, E, F, I |
| Spencer Torkelson | 2025-04-06 | 13.17 | 5 | A, C, D, F, I |
| Chandler Simpson | 2025-04-28 | 12.04 | 5 | A, B, E, F, I |
| Willson Contreras | 2025-04-19 | 11.93 | 2 | A, I |
| TJ Friedl | 2025-04-09 | 11.48 | 2 | A, I |
| Vinnie Pasquantino | 2025-05-13 | 11.00 | 3 | A, C, I |
| Kyle Stowers | 2025-05-22 | 9.35 | 4 | A, D, F, I |
| Gavin Sheets | 2025-04-09 | 9.25 | 2 | D, E |
| Trent Grisham | 2025-04-16 | 9.15 | 5 | A, C, E, F, I |
| Salvador Perez | 2025-05-17 | 8.92 | 2 | A, I |

### Pitchers

- Eval pool: **37** top + **37** bottom | base top-rate: **0.50**
- Confidence-score rank-biserial r = `0.530` (higher score → more likely top quartile)

**Individual method predictive power (in-sample):**

| Method | Flagged | Precision | Recall | F1 | Lift |
|--------|---------|-----------|--------|----|------|
| A_clustering | 29 | 0.76 | 0.59 | 0.67 | 1.52 |
| B_changepoint | 11 | 0.55 | 0.16 | 0.25 | 1.09 |
| C_bayesian | 34 | 0.71 | 0.65 | 0.68 | 1.41 |
| D_sequential | 13 | 0.69 | 0.24 | 0.36 | 1.38 |
| E_anomaly | 19 | 0.68 | 0.35 | 0.46 | 1.37 |
| F_forecast | 31 | 0.81 | 0.68 | 0.74 | 1.61 |
| G_market _(weak)_ | 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| H_opportunity | 0 | 0.00 | 0.00 | 0.00 | 0.00 |
| I_bandit | 29 | 0.76 | 0.59 | 0.67 | 1.52 |

**Multi-method confidence score (excludes weak G):**

| Score >= | n flagged (top+bottom) | Precision | Recall | Lift |
|----------|------------------------|-----------|--------|------|
| 1 | 49 | 0.63 | 0.84 | 1.27 |
| 2 | 37 | 0.73 | 0.73 | 1.46 |
| 3 | 31 | 0.74 | 0.62 | 1.48 |
| 4 | 24 | 0.83 | 0.54 | 1.67 |
| 5 | 16 | 0.81 | 0.35 | 1.62 |
| 6 | 9 | 0.78 | 0.19 | 1.56 |

**Fusion with Idea 16 supervised rule:**

- Idea 16 rule: `k9_14d` >= 7.105 (P=0.60, R=0.95, lift=1.21)
- **Highest-confidence tier** (Idea 16 rule AND >=3 Idea 17 methods): 27 flagged, P=0.78, lift=1.56

**Retrospective audit — top pickups & methods that fired:**

| Player | Acq Date | Z | Score | Methods Fired |
|--------|----------|---|-------|---------------|
| Nick Pivetta | 2025-04-18 | 5.88 | 1 | C |
| Abner Uribe | 2025-05-17 | 5.81 | 4 | A, C, F, I |
| Jeremiah Estrada | 2025-05-01 | 4.94 | 3 | B, C, F |
| Matthew Boyd | 2025-04-24 | 4.79 | 0 | — |
| Carlos Estevez | 2025-04-24 | 4.65 | 4 | A, C, F, I |
| Emilio Pagan | 2025-04-24 | 4.43 | 2 | A, I |
| Ranger Suarez | 2025-05-29 | 4.20 | 1 | F |
| Merrill Kelly | 2025-05-21 | 3.85 | 2 | E, F |
| Daniel Palencia | 2025-06-09 | 3.35 | 6 | A, B, C, E, F, I |
| Hunter Gaddis | 2025-04-17 | 3.28 | 5 | A, C, E, F, I |
| Trevor Megill | 2025-07-02 | 3.10 | 5 | A, C, D, F, I |
| Nick Lodolo | 2025-06-08 | 2.71 | 0 | — |

---

## Cross-Season Method Ranking (Stability = Robustness)

Mean lift across player types per season. Methods with high lift in **both** seasons are the robust core to build the watchlist around.

| Method | 2026 mean lift | 2025 mean lift | Robust? |
|--------|----------------|----------------|---------|
| D_sequential | 1.62 | 1.50 | ✓ |
| I_bandit | 1.37 | 1.58 | ✓ |
| E_anomaly | 1.34 | 1.55 | ✓ |
| A_clustering | 1.33 | 1.58 | ✓ |
| H_opportunity | 1.31 | 0.00 |  |
| F_forecast | 1.28 | 1.69 | ✓ |
| C_bayesian | 1.00 | 1.54 |  |
| B_changepoint | 0.99 | 1.37 |  |
| G_market | 0.42 | 0.00 |  |

## How to Use This

1. Run `watch_multi_method_signals.py` weekly to score the current free-agent pool.
2. Prioritize players with **confidence score >= 3** — and especially those that also pass the Idea 16 supervised threshold (highest tier).
3. Treat the robust-core methods (✓ above) as the trustworthy signals; down-weight the rest.
