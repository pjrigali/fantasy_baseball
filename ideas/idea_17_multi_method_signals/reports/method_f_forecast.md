# Section F — Time Series Forecasting (Project the Next Game)

Forecasts each player's next good-direction game via ETS and ARIMA, then tests whether the forward-looking forecast separates top from bottom pickups better than the backward-looking rolling average used in Idea 16.

## 2026 (primary)

### Batters

- Forecasted players (>= 5 games): **74** | base top-rate: **0.50**
- Separation (rank-biserial r): ETS `0.201`, ARIMA `0.039`, raw rolling avg `0.042` — forecasting beats the backward-looking average.

| Forecaster | Precision | Recall | F1 | Lift | tp | fp | fn |
|------------|-----------|--------|----|------|----|----|----|
| ETS (exp. smoothing) | 0.75 | 0.35 | 0.48 | 1.50 | 12 | 4 | 22 |
| ARIMA(1,0,0) | 0.67 | 0.29 | 0.41 | 1.33 | 10 | 5 | 24 |

### Pitchers

- Forecasted players (>= 5 games): **64** | base top-rate: **0.50**
- Separation (rank-biserial r): ETS `0.276`, ARIMA `0.265`, raw rolling avg `0.182` — forecasting beats the backward-looking average.

| Forecaster | Precision | Recall | F1 | Lift | tp | fp | fn |
|------------|-----------|--------|----|------|----|----|----|
| ETS (exp. smoothing) | 0.53 | 0.29 | 0.38 | 1.06 | 9 | 8 | 22 |
| ARIMA(1,0,0) | 0.53 | 0.32 | 0.40 | 1.05 | 10 | 9 | 21 |

---

## 2025 (cross-season)

### Batters

- Forecasted players (>= 5 games): **125** | base top-rate: **0.47**
- Separation (rank-biserial r): ETS `0.368`, ARIMA `0.388`, raw rolling avg `0.477` — forecasting does not beat the backward-looking average.

| Forecaster | Precision | Recall | F1 | Lift | tp | fp | fn |
|------------|-----------|--------|----|------|----|----|----|
| ETS (exp. smoothing) | 0.83 | 0.60 | 0.69 | 1.76 | 34 | 7 | 23 |
| ARIMA(1,0,0) | 0.84 | 0.56 | 0.67 | 1.79 | 32 | 6 | 25 |

### Pitchers

- Forecasted players (>= 5 games): **88** | base top-rate: **0.50**
- Separation (rank-biserial r): ETS `0.575`, ARIMA `0.593`, raw rolling avg `0.530` — forecasting beats the backward-looking average.

| Forecaster | Precision | Recall | F1 | Lift | tp | fp | fn |
|------------|-----------|--------|----|------|----|----|----|
| ETS (exp. smoothing) | 0.80 | 0.65 | 0.72 | 1.60 | 24 | 6 | 13 |
| ARIMA(1,0,0) | 0.83 | 0.65 | 0.73 | 1.66 | 24 | 5 | 13 |
