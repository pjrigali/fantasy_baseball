# Section A — Unsupervised Clustering (Archetype Discovery)

Clusters the standardized pre-pickup feature space **without** outcome labels, then overlays Idea 15 composite_z to find which archetypes predict top-quartile pickups. PCA/K-means/DBSCAN hand-rolled (no sklearn); hierarchical via SciPy.

## 2026 (primary)

### Batters

- Valid rows clustered: **113** | base top-rate (top / top+bottom): **0.50**
- PCA explained variance (first 3 PCs): `0.29`, `0.17`, `0.11` (cumulative `0.57`)

**PCA loadings (which features define each axis):**

| PC | `ops_7d` | `ops_14d` | `ops_21d` | `ab_per_game_7d` | `ab_per_game_14d` | `hr_per_game_14d` | `sb_per_game_14d` | `r_per_game_14d` | `rbi_per_game_14d` | `games_played_14d` | `pct_owned_at_pickup` | `pct_change_mean_7d` | `ownership_slope_7d` | `batting_slot_mode_7d` | `top_order_rate_7d` |
|----|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PC1 | +0.40 | +0.45 | +0.43 | +0.03 | +0.06 | +0.39 | -0.01 | +0.29 | +0.38 | -0.05 | -0.04 | +0.16 | +0.18 | -0.06 | -0.01 |
| PC2 | -0.07 | -0.10 | -0.10 | +0.45 | +0.45 | +0.07 | -0.02 | +0.15 | +0.05 | +0.27 | +0.25 | -0.11 | -0.01 | -0.46 | +0.43 |
| PC3 | +0.03 | -0.05 | -0.10 | -0.35 | -0.34 | +0.14 | -0.39 | -0.04 | -0.22 | +0.27 | +0.12 | +0.34 | +0.42 | -0.25 | +0.29 |

**Method validation (flag = member of a cluster with above-base top-rate):**

| Method | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| K-means (k=3) | 0.65 | 0.44 | 0.53 | 1.30 | 15 | 8 | 19 |
| DBSCAN (eps=1.00) | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | 34 |
| Hierarchical (Ward, 3) | 0.62 | 0.38 | 0.47 | 1.24 | 13 | 8 | 21 |

**K-means archetype profiles (k=3, original-unit centroids):**

| Cluster | n | top-rate | `ops_7d` | `ops_14d` | `ops_21d` | `ab_per_game_7d` | `ab_per_game_14d` | `hr_per_game_14d` | `sb_per_game_14d` | `r_per_game_14d` |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 ⭐ | 18 | 0.70 | 0.86 | 0.80 | 0.76 | 3.69 | 3.66 | 0.16 | 0.05 | 0.55 |
| 1 | 73 | 0.39 | 0.90 | 0.84 | 0.82 | 3.43 | 3.39 | 0.11 | 0.09 | 0.45 |
| 2 ⭐ | 22 | 0.67 | 1.39 | 1.34 | 1.27 | 3.40 | 3.35 | 0.36 | 0.15 | 0.82 |

⭐ = predictive archetype (top-rate above base). DBSCAN isolated **101** outlier players (novel opportunity types worth manual inspection).

### Pitchers

- Valid rows clustered: **109** | base top-rate (top / top+bottom): **0.50**
- PCA explained variance (first 3 PCs): `0.29`, `0.23`, `0.15` (cumulative `0.67`)

**PCA loadings (which features define each axis):**

| PC | `k9_7d` | `k9_14d` | `k9_21d` | `era_7d` | `era_14d` | `era_21d` | `whip_7d` | `whip_14d` | `svhd_per_app_14d` | `appearances_14d` | `qs_14d` | `pct_owned_at_pickup` | `pct_change_mean_7d` | `ownership_slope_7d` |
|----|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PC1 | -0.02 | -0.04 | -0.01 | +0.40 | +0.44 | +0.36 | +0.36 | +0.37 | -0.16 | -0.09 | -0.01 | +0.30 | -0.20 | -0.28 |
| PC2 | -0.43 | -0.49 | -0.48 | -0.09 | -0.11 | -0.09 | +0.04 | +0.04 | -0.26 | -0.32 | +0.34 | +0.11 | +0.09 | +0.08 |
| PC3 | +0.32 | +0.25 | +0.23 | -0.05 | +0.11 | +0.25 | -0.29 | -0.14 | -0.44 | -0.39 | +0.37 | +0.19 | +0.19 | +0.22 |

**Method validation (flag = member of a cluster with above-base top-rate):**

| Method | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| K-means (k=5) | 0.67 | 0.58 | 0.62 | 1.33 | 18 | 9 | 13 |
| DBSCAN (eps=1.75) | 0.50 | 0.06 | 0.11 | 1.00 | 2 | 2 | 29 |
| Hierarchical (Ward, 5) | 0.57 | 0.68 | 0.62 | 1.14 | 21 | 16 | 10 |

**K-means archetype profiles (k=5, original-unit centroids):**

| Cluster | n | top-rate | `k9_7d` | `k9_14d` | `k9_21d` | `era_7d` | `era_14d` | `era_21d` | `whip_7d` | `whip_14d` |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 ⭐ | 22 | 0.67 | 7.19 | 7.56 | 7.75 | 1.21 | 0.93 | 0.87 | 1.08 | 0.90 |
| 1 | 50 | 0.33 | 8.17 | 8.50 | 8.41 | 1.20 | 1.73 | 2.27 | 0.88 | 0.94 |
| 2 ⭐ | 23 | 0.64 | 14.48 | 14.27 | 13.12 | 1.19 | 1.61 | 2.14 | 0.61 | 0.72 |
| 3 | 5 | 1.00 | 9.10 | 7.16 | 7.29 | 1.76 | 1.66 | 2.32 | 0.82 | 0.88 |
| 4 | 9 | 0.00 | 10.44 | 9.66 | 9.82 | 10.57 | 6.95 | 5.33 | 2.09 | 1.62 |

⭐ = predictive archetype (top-rate above base). DBSCAN isolated **91** outlier players (novel opportunity types worth manual inspection).

---

## 2025 (cross-season, game-log features only)

### Batters

- Valid rows clustered: **209** | base top-rate (top / top+bottom): **0.47**
- PCA explained variance (first 3 PCs): `0.37`, `0.19`, `0.13` (cumulative `0.69`)

**PCA loadings (which features define each axis):**

| PC | `ops_7d` | `ops_14d` | `ops_21d` | `ab_per_game_7d` | `ab_per_game_14d` | `hr_per_game_14d` | `sb_per_game_14d` | `r_per_game_14d` | `rbi_per_game_14d` | `games_played_14d` |
|----|---|---|---|---|---|---|---|---|---|---|
| PC1 | +0.33 | +0.44 | +0.41 | -0.02 | -0.05 | +0.42 | +0.05 | +0.38 | +0.39 | +0.23 |
| PC2 | -0.01 | +0.17 | +0.20 | -0.61 | -0.65 | -0.08 | -0.10 | -0.23 | -0.03 | -0.26 |
| PC3 | +0.34 | +0.32 | +0.32 | +0.35 | +0.24 | -0.11 | -0.22 | -0.28 | -0.18 | -0.57 |

**Method validation (flag = member of a cluster with above-base top-rate):**

| Method | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| K-means (k=7) | 0.77 | 0.88 | 0.82 | 1.63 | 50 | 15 | 7 |
| DBSCAN (eps=1.50) | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 0 | 57 |
| Hierarchical (Ward, 7) | 0.75 | 0.86 | 0.80 | 1.60 | 49 | 16 | 8 |

**K-means archetype profiles (k=7, original-unit centroids):**

| Cluster | n | top-rate | `ops_7d` | `ops_14d` | `ops_21d` | `ab_per_game_7d` | `ab_per_game_14d` | `hr_per_game_14d` | `sb_per_game_14d` | `r_per_game_14d` |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 32 | 0.00 | 0.56 | 0.67 | 0.67 | 3.50 | 3.64 | 0.00 | 0.00 | 0.02 |
| 1 ⭐ | 47 | 0.81 | 0.63 | 0.80 | 0.82 | 3.99 | 3.96 | 0.17 | 0.07 | 0.62 |
| 2 ⭐ | 17 | 0.62 | 0.70 | 0.85 | 0.87 | 3.53 | 3.48 | 0.09 | 0.45 | 0.55 |
| 3 ⭐ | 4 | 0.75 | 1.11 | 1.49 | 1.49 | 2.80 | 2.64 | 0.38 | 0.03 | 0.70 |
| 4 | 51 | 0.42 | 0.57 | 0.79 | 0.84 | 3.13 | 3.26 | 0.11 | 0.05 | 0.50 |
| 5 ⭐ | 38 | 0.95 | 0.96 | 1.05 | 0.99 | 3.52 | 3.61 | 0.33 | 0.06 | 0.72 |
| 6 ⭐ | 20 | 0.50 | 0.36 | 0.42 | 0.48 | 3.61 | 3.64 | 0.02 | 0.07 | 0.22 |

⭐ = predictive archetype (top-rate above base). DBSCAN isolated **152** outlier players (novel opportunity types worth manual inspection).

### Pitchers

- Valid rows clustered: **135** | base top-rate (top / top+bottom): **0.50**
- PCA explained variance (first 3 PCs): `0.35`, `0.28`, `0.14` (cumulative `0.77`)

**PCA loadings (which features define each axis):**

| PC | `k9_7d` | `k9_14d` | `k9_21d` | `era_7d` | `era_14d` | `era_21d` | `whip_7d` | `whip_14d` | `svhd_per_app_14d` | `appearances_14d` | `qs_14d` |
|----|---|---|---|---|---|---|---|---|---|---|---|
| PC1 | +0.06 | +0.06 | +0.05 | -0.40 | -0.47 | -0.43 | -0.38 | -0.42 | +0.22 | +0.23 | +0.00 |
| PC2 | +0.39 | +0.48 | +0.51 | +0.18 | +0.07 | +0.05 | +0.16 | +0.07 | +0.31 | +0.30 | -0.31 |
| PC3 | -0.47 | -0.36 | -0.19 | +0.10 | +0.09 | +0.03 | +0.08 | +0.03 | +0.46 | +0.42 | -0.45 |

**Method validation (flag = member of a cluster with above-base top-rate):**

| Method | Precision | Recall | F1 | Lift | tp | fp | fn |
|--------|-----------|--------|----|------|----|----|----|
| K-means (k=3) | 0.77 | 0.54 | 0.63 | 1.54 | 20 | 6 | 17 |
| DBSCAN (eps=1.50) | 0.80 | 0.11 | 0.19 | 1.60 | 4 | 1 | 33 |
| Hierarchical (Ward, 3) | 0.59 | 0.86 | 0.70 | 1.19 | 32 | 22 | 5 |

**K-means archetype profiles (k=3, original-unit centroids):**

| Cluster | n | top-rate | `k9_7d` | `k9_14d` | `k9_21d` | `era_7d` | `era_14d` | `era_21d` | `whip_7d` | `whip_14d` |
|---|---|---|---|---|---|---|---|---|---|---|
| 0 | 67 | 0.37 | 7.43 | 7.86 | 7.93 | 3.92 | 3.20 | 2.94 | 1.28 | 1.16 |
| 1 ⭐ | 44 | 0.80 | 8.51 | 9.64 | 10.26 | 2.38 | 1.54 | 1.35 | 1.09 | 0.91 |
| 2 | 24 | 0.27 | 12.32 | 11.29 | 11.71 | 13.64 | 7.36 | 5.62 | 2.33 | 1.68 |

⭐ = predictive archetype (top-rate above base). DBSCAN isolated **88** outlier players (novel opportunity types worth manual inspection).
