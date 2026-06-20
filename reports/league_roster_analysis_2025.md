# League-Wide Roster Analysis (Deep Dive)

## 1. Optimal Evaluation Window
**Selected Window:** 30 Days
Correlation with future performance: **0.3784**
*(Analysis performed on all players across the entire league)*

### Sensitivity Analysis (Correlation by Window):
- 3 Days: 0.1904
- 15 Days: 0.3285
- **30 Days**: 0.3784** (Selected)
- 45 Days: 0.4003
- 60 Days: 0.4075
- 75 Days: 0.4131
- 90 Days: 0.4179

## 2. Optimal Roster Cadence
Based on the Top 3 Teams (Average Value: 2438.7):
- **Optimal Churn Rate**: 2.2 adds per week
- **Target Hold Time (Drops)**: 61.3 days

### Member Breakdown (vs Optimal)
| Team | Total Value | Adds/Week | vs Optimal Churn | Avg Hold | Median Hold |
|---|---|---|---|---|---|
| AFFO | 2541.5 | 2.3 | +0.1 | 56.7d | 25.5d |
| PJR | 2540.0 | 1.2 | -1.0 | 82.0d | 69.0d |
| HILL | 2234.7 | 3.1 | +0.9 | 45.4d | 11.5d |
| BP | 2136.9 | 3.3 | +1.0 | 44.6d | 19.0d |
| CHER | 2090.7 | 2.8 | +0.6 | 47.2d | 23.0d |
| DO | 1878.2 | 0.5 | -1.8 | 117.1d | 154.0d |
| ELLI | 1872.6 | 1.4 | -0.8 | 75.6d | 44.0d |
| $$$ | 1478.0 | 0.5 | -1.8 | 120.1d | 155.0d |
| GIBB | 1448.3 | 0.3 | -1.9 | 146.4d | 167.0d |
| YBSD | 1368.1 | 0.1 | -2.1 | 152.2d | 167.0d |

## Visualizations

### Evaluation Window Sensitivity
The curve shows the predictive power of different lookback windows.

```mermaid
xychart-beta
    title "Predictive Power vs Lookback Window"
    x-axis "Days" [3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36, 39, 42, 45, 48, 51, 54, 57, 60, 63, 66, 69, 72, 75, 78, 81, 84, 87, 90]
    y-axis "Correlation" 0.181 --> 0.439
    line [0.1904, 0.2510, 0.2845, 0.3106, 0.3285, 0.3440, 0.3547, 0.3637, 0.3716, 0.3784, 0.3844, 0.3895, 0.3937, 0.3974, 0.4003, 0.4022, 0.4039, 0.4043, 0.4055, 0.4075, 0.4088, 0.4096, 0.4102, 0.4113, 0.4131, 0.4152, 0.4173, 0.4181, 0.4175, 0.4179]
```

### Manager Style: Patience vs. Value

```mermaid
quadrantChart
    title "Roster Management Style"
    x-axis "Patience (Avg Hold Time)" --> "Stubborness"
    y-axis "Low Value" --> "High Value"
    quadrant-1 "Diamond Hands (High Value)"
    quadrant-2 "Churn & Burn (High Value)"
    quadrant-3 "Panic Dropper (Low Value)"
    quadrant-4 "Sleeping at Wheel (Low Value)"
    $$$: [0.68, 0.13]
    AFFO: [0.15, 0.95]
    BP: [0.05, 0.64]
    CHER: [0.07, 0.60]
    DO: [0.66, 0.44]
    ELLI: [0.31, 0.44]
    GIBB: [0.90, 0.11]
    HILL: [0.06, 0.71]
    PJR: [0.36, 0.95]
    YBSD: [0.95, 0.05]
```
