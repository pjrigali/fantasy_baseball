# Waiver Wire Signal Detection — Pre-Pickup Indicator Analysis (2026)

**Analysis date:** 2026-06-19  
**Ground truth source:** `2026_espn_best_pickups.csv` (Idea 15)  
**Total pickups:** 256 (134 batters, 122 pitchers)  
**Archive coverage:** 72% of batters, 83% of pitchers had pre-pickup game log data  

---

## Methodology

1. **Label quartiles** — top-quartile: composite_z ≥ 75th pct (within player type); bottom-quartile: composite_z ≤ 25th pct; middle excluded from testing
2. **Build pre-pickup features** — 7-day and 14-day rolling windows before `acquisition_date` from `2026_mlb_stats_daily_archive`, `espn_rankings_daily`, and `mlb_lineups_batters`
3. **Rank features** — Mann-Whitney U rank-biserial correlation r ∈ [−1, 1]: |r| near 1 means the feature consistently separates top from bottom pickups
4. **Find thresholds** — single-feature decision boundary that maximises F1 score (top-quartile = positive class)

> **Note on cross-season validation:** Prior-year `activity_espn_season` and `rankings_espn_daily` are not in the data lake, so 2024/2025 back-testing is deferred. The signals here are single-season observations — treat effect sizes as directional, not definitive.

---

## Batter Signals

- **Top quartile (34 pickups):** composite_z ≥ 1.37
- **Bottom quartile (34 pickups):** composite_z ≤ -3.18

### Signal Importance — Batters

| # | Feature | r | Direction | Threshold | Precision | Recall | F1 | Top Median | Bot Median |
|---|---------|---|-----------|-----------|-----------|--------|-----|------------|------------|
| 1 | `pct_owned_at_pickup` | 0.700 | ↑ higher | ≥ 22.760 | 1.00 | 0.75 | 0.86 | 23.170 | 7.420 |
| 2 | `hr_per_game_7d` | 0.480 | ↑ higher | ≥ 0.143 | 0.75 | 0.75 | 0.75 | 0.225 | 0.000 |
| 3 | `hr_per_game_14d` | 0.468 | ↑ higher | ≥ 0.167 | 0.73 | 0.76 | 0.75 | 0.222 | 0.000 |
| 4 | `batting_slot_mode_7d` | -0.424 | ↓ lower | ≤ 7.000 | 0.69 | 0.96 | 0.80 | 5.000 | 7.000 |
| 5 | `r_per_game_14d` | 0.409 | ↑ higher | ≥ 0.250 | 0.60 | 0.96 | 0.74 | 0.583 | 0.333 |
| 6 | `r_per_game_7d` | 0.367 | ↑ higher | ≥ 0.167 | 0.64 | 0.96 | 0.77 | 0.633 | 0.400 |
| 7 | `ownership_slope_14d` | 0.333 | ↑ higher | ≥ 1.670 | 1.00 | 0.67 | 0.80 | 1.670 | 0.592 |
| 8 | `ops_7d` | 0.306 | ↑ higher | ≥ 0.293 | 0.63 | 1.00 | 0.77 | 1.041 | 0.940 |
| 9 | `pct_change_mean_14d` | 0.300 | ↑ higher | ≥ 3.503 | 1.00 | 0.50 | 0.67 | 2.107 | 0.482 |
| 10 | `games_played_7d` | 0.286 | ↑ higher | ≥ 2.000 | 0.63 | 1.00 | 0.77 | 5.000 | 5.000 |
| 11 | `ab_per_game_14d` | 0.273 | ↑ higher | ≥ 3.000 | 0.69 | 1.00 | 0.82 | 3.500 | 3.333 |
| 12 | `ops_14d` | 0.256 | ↑ higher | ≥ 0.543 | 0.62 | 0.96 | 0.75 | 0.947 | 0.804 |
| 13 | `games_played_14d` | 0.250 | ↑ higher | ≥ 3.000 | 0.59 | 0.96 | 0.73 | 11.000 | 8.000 |
| 14 | `pct_change_mean_7d` | 0.250 | ↑ higher | ≥ 3.503 | 1.00 | 0.50 | 0.67 | 2.107 | 0.844 |
| 15 | `top_order_rate_7d` | 0.205 | ↑ higher | ≥ 0.000 | 0.60 | 1.00 | 0.75 | 0.000 | 0.000 |

### Prescriptive Rules — Batters

Rules from the top 8 discriminating features. Each threshold maximises F1 on the 2026 labeled set.

- **`pct_owned_at_pickup` ≥ 22.760**  (r = 0.700, precision = 1.00, recall = 0.75, F1 = 0.86)
- **`hr_per_game_7d` ≥ 0.143**  (r = 0.480, precision = 0.75, recall = 0.75, F1 = 0.75)
- **`hr_per_game_14d` ≥ 0.167**  (r = 0.468, precision = 0.73, recall = 0.76, F1 = 0.75)
- **`batting_slot_mode_7d` ≤ 7.000**  (r = -0.424, precision = 0.69, recall = 0.96, F1 = 0.80)
- **`r_per_game_14d` ≥ 0.250**  (r = 0.409, precision = 0.60, recall = 0.96, F1 = 0.74)
- **`r_per_game_7d` ≥ 0.167**  (r = 0.367, precision = 0.64, recall = 0.96, F1 = 0.77)
- **`ownership_slope_14d` ≥ 1.670**  (r = 0.333, precision = 1.00, recall = 0.67, F1 = 0.80)
- **`ops_7d` ≥ 0.293**  (r = 0.306, precision = 0.63, recall = 1.00, F1 = 0.77)

---

## Pitcher Signals

- **Top quartile (31 pickups):** composite_z ≥ 1.47
- **Bottom quartile (31 pickups):** composite_z ≤ -1.53

### Signal Importance — Pitchers

| # | Feature | r | Direction | Threshold | Precision | Recall | F1 | Top Median | Bot Median |
|---|---------|---|-----------|-----------|-----------|--------|-----|------------|------------|
| 1 | `pct_change_mean_7d` | 0.500 | ↑ higher | ≥ 1.042 | 1.00 | 0.50 | 0.67 | 0.586 | -0.004 |
| 2 | `pct_change_mean_14d` | 0.432 | ↑ higher | ≥ 1.042 | 1.00 | 0.50 | 0.67 | 0.596 | 0.005 |
| 3 | `era_14d` | -0.402 | ↓ lower | ≤ 2.250 | 0.69 | 0.85 | 0.76 | 1.256 | 2.455 |
| 4 | `ownership_slope_14d` | 0.386 | ↑ higher | ≥ 0.533 | 0.38 | 0.75 | 0.50 | 0.617 | 0.098 |
| 5 | `appearances_7d` | 0.259 | ↑ higher | ≥ 1.000 | 0.62 | 1.00 | 0.77 | 2.000 | 1.000 |
| 6 | `whip_14d` | -0.234 | ↓ lower | ≤ 1.167 | 0.62 | 0.92 | 0.74 | 0.826 | 1.000 |
| 7 | `svhd_per_app_14d` | 0.226 | ↑ higher | ≥ 0.000 | 0.54 | 1.00 | 0.70 | 0.183 | 0.000 |
| 8 | `appearances_14d` | 0.201 | ↑ higher | ≥ 1.000 | 0.54 | 1.00 | 0.70 | 3.000 | 2.000 |
| 9 | `svhd_per_app_7d` | 0.163 | ↑ higher | ≥ 0.000 | 0.62 | 1.00 | 0.77 | 0.250 | 0.000 |
| 10 | `era_7d` | -0.120 | ↓ lower | ≤ 5.400 | 0.62 | 1.00 | 0.77 | 0.000 | 1.350 |
| 11 | `whip_7d` | 0.048 | ↑ higher | ≥ 0.167 | 0.66 | 1.00 | 0.79 | 0.929 | 0.846 |
| 12 | `ownership_slope_7d` | 0.048 | ↑ higher | ≥ 4.624 | 1.00 | 0.25 | 0.40 | 0.124 | 0.306 |
| 13 | `k9_14d` | 0.045 | ↑ higher | ≥ 7.425 | 0.61 | 0.88 | 0.72 | 10.125 | 10.348 |
| 14 | `k9_7d` | 0.045 | ↑ higher | ≥ 7.105 | 0.69 | 0.88 | 0.77 | 10.385 | 11.077 |
| 15 | `pct_owned_at_pickup` | 0.023 | ↑ higher | ≥ 17.760 | 0.23 | 0.75 | 0.35 | 19.155 | 12.745 |

### Prescriptive Rules — Pitchers

Rules from the top 8 discriminating features.

- **`pct_change_mean_7d` ≥ 1.042**  (r = 0.500, precision = 1.00, recall = 0.50, F1 = 0.67)
- **`pct_change_mean_14d` ≥ 1.042**  (r = 0.432, precision = 1.00, recall = 0.50, F1 = 0.67)
- **`era_14d` ≤ 2.250**  (r = -0.402, precision = 0.69, recall = 0.85, F1 = 0.76)
- **`ownership_slope_14d` ≥ 0.533**  (r = 0.386, precision = 0.38, recall = 0.75, F1 = 0.50)
- **`appearances_7d` ≥ 1.000**  (r = 0.259, precision = 0.62, recall = 1.00, F1 = 0.77)
- **`whip_14d` ≤ 1.167**  (r = -0.234, precision = 0.62, recall = 0.92, F1 = 0.74)
- **`svhd_per_app_14d` ≥ 0.000**  (r = 0.226, precision = 0.54, recall = 1.00, F1 = 0.70)
- **`appearances_14d` ≥ 1.000**  (r = 0.201, precision = 0.54, recall = 1.00, F1 = 0.70)

---

## Retrospective Audit — Top Pickups

Which of the top 6 signals were already firing in the pre-pickup window for each top-quartile pickup. A signal "fires" when the player's pre-pickup value meets the F1-optimal threshold.

### Batters

| Player | Team | Acq Date | Z | Signals Firing |
|--------|------|----------|---|----------------|
| Jordan Walker | Midnight Muncy's | 2026-03-30 | 19.84 | `hr_per_game_7d` (0.33 >= 0.14), `hr_per_game_14d` (0.33 >= 0.17), `batting_slot_mode_7d` (6.00 <= 7.00), `r_per_game_14d` (2.00 >= 0.25), `r_per_game_7d` (2.00 >= 0.17) |
| Miguel Vargas | Midnight Muncy's | 2026-03-30 | 19.39 | `batting_slot_mode_7d` (3.00 <= 7.00), `r_per_game_14d` (0.67 >= 0.25), `r_per_game_7d` (0.67 >= 0.17) |
| Liam Hicks | All Rise | 2026-04-02 | 11.11 | `hr_per_game_7d` (0.60 >= 0.14), `hr_per_game_14d` (0.60 >= 0.17), `batting_slot_mode_7d` (4.00 <= 7.00), `r_per_game_14d` (1.20 >= 0.25), `r_per_game_7d` (1.20 >= 0.17) |
| Bryson Stott | Midnight Muncy's | 2026-03-23 | 10.20 | — |
| Brandon Marsh | Datalickmyballs | 2026-04-15 | 9.12 | `hr_per_game_7d` (0.17 >= 0.14), `hr_per_game_14d` (0.18 >= 0.17), `batting_slot_mode_7d` (4.00 <= 7.00), `r_per_game_14d` (0.64 >= 0.25), `r_per_game_7d` (0.67 >= 0.17) |
| Wilyer Abreu | Dingers Only | 2026-03-26 | 8.16 | — |
| Casey Schmitt | Welcome to the JUNGle | 2026-05-05 | 7.62 | `hr_per_game_7d` (0.17 >= 0.14), `hr_per_game_14d` (0.27 >= 0.17), `batting_slot_mode_7d` (4.00 <= 7.00), `r_per_game_14d` (0.36 >= 0.25), `r_per_game_7d` (0.17 >= 0.17) |
| Zack Gelof | All Rise | 2026-05-09 | 7.53 | `hr_per_game_7d` (0.40 >= 0.14), `hr_per_game_14d` (0.18 >= 0.17), `batting_slot_mode_7d` (5.00 <= 7.00), `r_per_game_14d` (0.64 >= 0.25), `r_per_game_7d` (1.20 >= 0.17) |
| Luke Raley | Datalickmyballs | 2026-04-15 | 6.53 | `batting_slot_mode_7d` (6.00 <= 7.00), `r_per_game_14d` (0.25 >= 0.25), `r_per_game_7d` (0.33 >= 0.17) |
| Ivan Herrera | This Schlitt is Bazzanas | 2026-04-27 | 6.43 | `hr_per_game_7d` (0.33 >= 0.14), `hr_per_game_14d` (0.33 >= 0.17), `batting_slot_mode_7d` (2.00 <= 7.00), `r_per_game_14d` (0.58 >= 0.25), `r_per_game_7d` (0.33 >= 0.17) |
| Dillon Dingler | This Schlitt is Bazzanas | 2026-04-04 | 6.43 | `hr_per_game_7d` (0.25 >= 0.14), `hr_per_game_14d` (0.33 >= 0.17), `batting_slot_mode_7d` (5.00 <= 7.00), `r_per_game_14d` (0.50 >= 0.25), `r_per_game_7d` (0.50 >= 0.17) |
| Mickey Moniak | Skubal Snacks | 2026-04-12 | 6.14 | `hr_per_game_7d` (0.71 >= 0.14), `hr_per_game_14d` (0.56 >= 0.17), `batting_slot_mode_7d` (3.00 <= 7.00), `r_per_game_14d` (0.67 >= 0.25), `r_per_game_7d` (0.71 >= 0.17) |
| Sam Antonacci | All Rise | 2026-04-15 | 5.27 | — |
| Mauricio Dubon | Big Dumpers | 2026-04-29 | 4.57 | `batting_slot_mode_7d` (7.00 <= 7.00), `r_per_game_14d` (0.36 >= 0.25), `r_per_game_7d` (0.50 >= 0.17) |
| Nolan Arenado | Big Dumpers | 2026-04-29 | 4.39 | `hr_per_game_7d` (0.20 >= 0.14), `hr_per_game_14d` (0.20 >= 0.17), `batting_slot_mode_7d` (7.00 <= 7.00), `r_per_game_14d` (0.80 >= 0.25), `r_per_game_7d` (1.20 >= 0.17) |

### Pitchers

| Player | Team | Acq Date | Z | Signals Firing |
|--------|------|----------|---|----------------|
| Erik Sabrowski | This Schlitt is Bazzanas | 2026-04-01 | 4.52 | `era_14d` (0.00 <= 2.25), `appearances_7d` (3.00 >= 1.00), `whip_14d` (0.60 <= 1.17) |
| Paul Sewald | All Rise | 2026-04-05 | 4.37 | `appearances_7d` (4.00 >= 1.00), `whip_14d` (0.50 <= 1.17) |
| Emerson Hancock | Midnight Muncy's | 2026-03-30 | 4.35 | `era_14d` (0.00 <= 2.25), `appearances_7d` (1.00 >= 1.00), `whip_14d` (0.17 <= 1.17) |
| Gregory Soto | Shohei Me the Money | 2026-04-07 | 4.11 | `era_14d` (1.42 <= 2.25), `appearances_7d` (4.00 >= 1.00), `whip_14d` (0.79 <= 1.17) |
| Bryan Baker | Welcome to the JUNGle | 2026-04-28 | 3.72 | `era_14d` (1.69 <= 2.25), `appearances_7d` (3.00 >= 1.00), `whip_14d` (1.12 <= 1.17) |
| Tanner Scott | Skubal Snacks | 2026-04-10 | 3.40 | `appearances_7d` (2.00 >= 1.00), `whip_14d` (1.09 <= 1.17) |
| Louis Varland | Welcome to the JUNGle | 2026-04-15 | 3.39 | `era_14d` (0.00 <= 2.25), `appearances_7d` (4.00 >= 1.00), `whip_14d` (0.57 <= 1.17) |
| Ian Seymour | Midnight Muncy's | 2026-03-23 | 3.25 | — |
| Payton Tolle | Skubal Snacks | 2026-04-21 | 3.21 | — |
| Kyle Harrison | Skubal Snacks | 2026-04-29 | 2.87 | `era_14d` (1.00 <= 2.25), `appearances_7d` (1.00 >= 1.00), `whip_14d` (1.00 <= 1.17) |
| Braxton Ashcraft | Dingers Only | 2026-03-25 | 2.79 | — |
| Michael Wacha | All Rise | 2026-04-21 | 2.78 | `era_14d` (1.29 <= 2.25), `appearances_7d` (1.00 >= 1.00), `whip_14d` (0.79 <= 1.17) |
| Davis Martin | Dingers Only | 2026-04-28 | 2.71 | `era_14d` (1.35 <= 2.25), `appearances_7d` (1.00 >= 1.00), `whip_14d` (0.90 <= 1.17) |
| Trevor Megill | Shohei Me the Money | 2026-05-11 | 2.71 | `era_14d` (2.25 <= 2.25), `appearances_7d` (2.00 >= 1.00), `whip_14d` (0.75 <= 1.17) |
| Dylan Lee | This Schlitt is Bazzanas | 2026-05-25 | 2.63 | `era_14d` (1.59 <= 2.25), `ownership_slope_14d` (0.53 >= 0.53), `appearances_7d` (3.00 >= 1.00), `whip_14d` (1.06 <= 1.17) |

---

## Cross-Year Validation — 2026 vs 2025 (Game-Log Features Only)

2025 signals use only `2025_mlb_stats_daily.csv` (no ownership or batting-order data).
Features that show **consistent direction and similar |r|** across both seasons are the most robust.

### Batters

| Feature | r 2026 | Dir 26 | r 2025 | Dir 25 | Consistent? |
|---------|--------|--------|--------|--------|-------------|
| `hr_per_game_7d` | 0.480 | ↑ | 0.385 | ↑ | ✓ |
| `hr_per_game_14d` | 0.468 | ↑ | 0.652 | ↑ | ✓ |
| `r_per_game_14d` | 0.409 | ↑ | 0.746 | ↑ | ✓ |
| `r_per_game_7d` | 0.367 | ↑ | 0.646 | ↑ | ✓ |
| `ops_7d` | 0.306 | ↑ | 0.437 | ↑ | ✓ |
| `games_played_7d` | 0.286 | ↑ | 0.740 | ↑ | ✓ |
| `ab_per_game_14d` | 0.273 | ↑ | 0.328 | ↑ | ✓ |
| `ops_14d` | 0.256 | ↑ | 0.449 | ↑ | ✓ |
| `games_played_14d` | 0.250 | ↑ | 0.706 | ↑ | ✓ |
| `ab_per_game_7d` | 0.133 | ↑ | 0.307 | ↑ | ✓ |
| `sb_per_game_14d` | 0.073 | ↑ | 0.396 | ↑ | ✓ |
| `sb_per_game_7d` | 0.067 | ↑ | 0.254 | ↑ | ✓ |

### Pitchers

| Feature | r 2026 | Dir 26 | r 2025 | Dir 25 | Consistent? |
|---------|--------|--------|--------|--------|-------------|
| `era_14d` | -0.402 | ↓ | -0.671 | ↓ | ✓ |
| `appearances_7d` | 0.259 | ↑ | 0.357 | ↑ | ✓ |
| `whip_14d` | -0.234 | ↓ | -0.593 | ↓ | ✓ |
| `svhd_per_app_14d` | 0.226 | ↑ | 0.441 | ↑ | ✓ |
| `appearances_14d` | 0.201 | ↑ | 0.467 | ↑ | ✓ |
| `svhd_per_app_7d` | 0.163 | ↑ | 0.433 | ↑ | ✓ |
| `era_7d` | -0.120 | ↓ | -0.506 | ↓ | ✓ |
| `whip_7d` | 0.048 | ↑ | -0.351 | ↓ | ✗ |
| `k9_14d` | 0.045 | ↑ | 0.542 | ↑ | ✓ |
| `k9_7d` | 0.045 | ↑ | 0.516 | ↑ | ✓ |

---

## Limitations & Next Steps

- **Sample size:** ~30–35 players per quartile group per type — effect sizes are directional, not definitive.
- **2025 cross-validation:** Game-log features only — no prior-year ownership or batting-order data in the lake.
- **Name coverage:** Players without a `player_lookup.csv` entry have no archive features.
- **Archive gaps:** `2026_mlb_stats_daily_archive.csv` is the legacy per-player fetcher; bench players not included.

**Next steps:**
1. Build the weekly runtime watchlist script that applies these thresholds to the current available player pool
2. Progress to Idea 17 for unsupervised clustering, changepoint detection, and anomaly detection methods