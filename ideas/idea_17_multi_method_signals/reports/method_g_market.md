# Section G — Market Efficiency Analysis

Ownership % as a prediction market: where the lag between performance and market reaction is largest, the add window is widest. 2026 only (no prior-year ownership in the data lake).

## Ownership Lag by Position

Median days between a qualifying performance game and the first +10% ownership spike. Longer = slower market = wider edge.

_Insufficient data: only 0 pickups had both a qualifying performance game and an ownership spike inside the window (ownership coverage is ~39%), too few to break out reliably by position. Revisit once more ownership history accrues._

## Ownership Slope vs Performance Decile

### Batters (binned by `ops_14d`)

| Decile | n | mean stat | mean own. slope | top-rate |
|--------|---|-----------|-----------------|----------|
| Q1 | 20 | 0.577 | -0.055 | 0.50 |
| Q2 | 20 | 0.787 | 0.632 | 0.55 |
| Q3 | 20 | 0.911 | 2.055 | 0.50 |
| Q4 | 20 | 1.035 | 2.536 | 0.62 |
| Q5 | 21 | 1.381 | 2.959 | 0.75 |

### Pitchers (binned by `k9_14d`)

| Decile | n | mean stat | mean own. slope | top-rate |
|--------|---|-----------|-----------------|----------|
| Q1 | 21 | 4.765 | 0.765 | 0.27 |
| Q2 | 21 | 7.704 | 0.810 | 0.78 |
| Q3 | 21 | 9.524 | -0.033 | 0.36 |
| Q4 | 21 | 11.302 | 0.650 | 0.33 |
| Q5 | 21 | 14.720 | 0.743 | 0.71 |

## Low-Signal, High-Ownership (Drop Candidates)

Pickups that were well-owned at acquisition yet landed in the bottom quartile — roster spots where the market left value on the table.

| Player | Type | pct_owned | composite_z |
|--------|------|-----------|-------------|
| Spencer Strider | pitcher | 78.4 | -1.56 |
| Edwin Diaz | pitcher | 64.0 | -1.56 |
| Tanner Bibee | pitcher | 60.6 | -2.53 |
| Landen Roupp | pitcher | 54.0 | -2.65 |

## Validated Add Rules — Honest Negative Result

Two candidate rules were tested and **both fail to separate top from bottom pickups** (lift < 1):

- **Momentum:** 7-day ownership slope above the type median.
- **Under-owned performer:** rolling stat above median AND ownership below median.

Why: ownership hype attaches to *busts as well as hits*. Bottom-quartile pickups were also added amid rising ownership (managers chased them, then they flopped), so ownership signals alone cannot tell a good add from a bad one. Section G's value is therefore **descriptive** (the performance/ownership decile gradient and the drop-candidate list above), not a standalone predictive signal. The consolidation step down-weights ownership-only flags accordingly.

| Rule | Type | Precision | Recall | F1 | Lift | tp | fp | fn |
|------|------|-----------|--------|----|------|----|----|----|
| Momentum | Batters | 0.25 | 0.06 | 0.10 | 0.50 | 2 | 6 | 32 |
| Under-owned perf. | Batters | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 2 | 34 |
| Momentum | Pitchers | 0.17 | 0.06 | 0.09 | 0.33 | 2 | 10 | 29 |
| Under-owned perf. | Pitchers | 0.00 | 0.00 | 0.00 | 0.00 | 0 | 4 | 31 |
