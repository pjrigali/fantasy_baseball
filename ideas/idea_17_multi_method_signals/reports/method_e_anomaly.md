# Section E — Anomaly Detection

Flags players whose recent pre-pickup feature vector is unusual relative to the population, split by direction so only good-direction anomalies count as add candidates. Isolation Forest and Mahalanobis one-class are both hand-rolled (no sklearn).

## 2026 (primary)

### Batters

- Valid rows: **113** | base top-rate: **0.50**
- Undirected iForest rank-biserial r = `0.112` (near 0 expected — anomalies include both breakouts and collapses)
- Direction-signed iForest r = `0.210` (positive = good-direction anomalies skew toward top pickups)

| Method | Outliers | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|----------|-----------|--------|----|------|----|----|----|
| Isolation Forest (top-tercile + good dir) | 37 | 0.60 | 0.18 | 0.27 | 1.20 | 6 | 4 | 28 |
| Mahalanobis (chi2 p90 + good dir) | 21 | 0.83 | 0.15 | 0.25 | 1.67 | 5 | 1 | 29 |

### Pitchers

- Valid rows: **109** | base top-rate: **0.50**
- Undirected iForest rank-biserial r = `-0.125` (near 0 expected — anomalies include both breakouts and collapses)
- Direction-signed iForest r = `0.350` (positive = good-direction anomalies skew toward top pickups)

| Method | Outliers | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|----------|-----------|--------|----|------|----|----|----|
| Isolation Forest (top-tercile + good dir) | 36 | 0.62 | 0.16 | 0.26 | 1.25 | 5 | 3 | 26 |
| Mahalanobis (chi2 p90 + good dir) | 32 | 0.60 | 0.19 | 0.29 | 1.20 | 6 | 4 | 25 |

---

## 2025 (cross-season, game-log features only)

### Batters

- Valid rows: **209** | base top-rate: **0.47**
- Undirected iForest rank-biserial r = `0.580` (near 0 expected — anomalies include both breakouts and collapses)
- Direction-signed iForest r = `0.404` (positive = good-direction anomalies skew toward top pickups)

| Method | Outliers | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|----------|-----------|--------|----|------|----|----|----|
| Isolation Forest (top-tercile + good dir) | 69 | 0.82 | 0.47 | 0.60 | 1.74 | 27 | 6 | 30 |
| Mahalanobis (chi2 p90 + good dir) | 38 | 0.70 | 0.25 | 0.36 | 1.49 | 14 | 6 | 43 |

### Pitchers

- Valid rows: **135** | base top-rate: **0.50**
- Undirected iForest rank-biserial r = `0.225` (near 0 expected — anomalies include both breakouts and collapses)
- Direction-signed iForest r = `0.543` (positive = good-direction anomalies skew toward top pickups)

| Method | Outliers | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|----------|-----------|--------|----|------|----|----|----|
| Isolation Forest (top-tercile + good dir) | 45 | 0.74 | 0.38 | 0.50 | 1.47 | 14 | 5 | 23 |
| Mahalanobis (chi2 p90 + good dir) | 32 | 0.67 | 0.27 | 0.38 | 1.33 | 10 | 5 | 27 |
