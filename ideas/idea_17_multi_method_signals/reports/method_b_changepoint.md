# Section B — Statistical Change Detection

Finds the game where a regime shifted (vs smoothing it over with a rolling window). CUSUM, an exact single-changepoint (PELT-style), and a Bayesian changepoint posterior run on each good-direction per-game series. A flag = recent, sustained, upward shift. All hand-rolled (no ruptures).

## 2026 (primary)

### Batters

- Players with a usable per-game series (>= 5 games): **88** | base top-rate: **0.50**

| Detector | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| CUSUM (sustained upward drift) | 0.57 | 0.12 | 0.20 | 1.14 | 4 | 3 | 30 |
| PELT (recent upward regime shift) | 0.59 | 0.29 | 0.39 | 1.18 | 10 | 7 | 24 |
| Bayesian changepoint (P>=0.5) | 0.54 | 0.21 | 0.30 | 1.08 | 7 | 6 | 27 |

### Pitchers

- Players with a usable per-game series (>= 5 games): **68** | base top-rate: **0.50**

| Detector | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| CUSUM (sustained upward drift) | 1.00 | 0.06 | 0.12 | 2.00 | 2 | 0 | 29 |
| PELT (recent upward regime shift) | 0.43 | 0.10 | 0.16 | 0.86 | 3 | 4 | 28 |
| Bayesian changepoint (P>=0.5) | 0.33 | 0.06 | 0.11 | 0.67 | 2 | 4 | 29 |

---

## 2025 (cross-season)

### Batters

- Players with a usable per-game series (>= 5 games): **173** | base top-rate: **0.47**

| Detector | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| CUSUM (sustained upward drift) | 0.53 | 0.18 | 0.26 | 1.12 | 10 | 9 | 47 |
| PELT (recent upward regime shift) | 0.77 | 0.30 | 0.43 | 1.64 | 17 | 5 | 40 |
| Bayesian changepoint (P>=0.5) | 0.75 | 0.16 | 0.26 | 1.59 | 9 | 3 | 48 |

### Pitchers

- Players with a usable per-game series (>= 5 games): **111** | base top-rate: **0.50**

| Detector | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| CUSUM (sustained upward drift) | 0.50 | 0.05 | 0.10 | 1.00 | 2 | 2 | 35 |
| PELT (recent upward regime shift) | 0.55 | 0.16 | 0.25 | 1.09 | 6 | 5 | 31 |
| Bayesian changepoint (P>=0.5) | 0.45 | 0.14 | 0.21 | 0.91 | 5 | 6 | 32 |
