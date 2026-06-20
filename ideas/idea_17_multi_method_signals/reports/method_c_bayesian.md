# Section C — Bayesian Updating (Small-Sample Shrinkage)

Shrinks each player's recent good-game rate toward an empirical-Bayes Beta prior so short hot streaks are weighted correctly. Compares the shrunk posterior against the naive raw rate to show the value of regression-to-mean.

## 2026 (primary)

### Batters

- Players with usable series (>= 4 games): **90** | base top-rate: **0.50**
- Fitted Beta prior: `alpha0=8.01`, `beta0=9.80` (prior good-game rate `0.450`)
- Posterior-mean rank-biserial r = `-0.211`; raw-rate r = `-0.250` — shrinkage improves separation.

| Estimate | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| Empirical-Bayes posterior > median | 0.50 | 0.24 | 0.32 | 1.00 | 8 | 8 | 26 |
| Naive raw rate > median | 0.50 | 0.24 | 0.32 | 1.00 | 8 | 8 | 26 |

### Pitchers

- Players with usable series (>= 4 games): **82** | base top-rate: **0.50**
- Fitted Beta prior: `alpha0=2.16`, `beta0=1.30` (prior good-game rate `0.624`)
- Posterior-mean rank-biserial r = `0.121`; raw-rate r = `0.116` — shrinkage improves separation.

| Estimate | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| Empirical-Bayes posterior > median | 0.52 | 0.39 | 0.44 | 1.04 | 12 | 11 | 19 |
| Naive raw rate > median | 0.52 | 0.39 | 0.44 | 1.04 | 12 | 11 | 19 |

---

## 2025 (cross-season)

### Batters

- Players with usable series (>= 4 games): **175** | base top-rate: **0.47**
- Fitted Beta prior: `alpha0=9.14`, `beta0=11.80` (prior good-game rate `0.437`)
- Posterior-mean rank-biserial r = `0.178`; raw-rate r = `0.180` — shrinkage does not improve separation.

| Estimate | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| Empirical-Bayes posterior > median | 0.76 | 0.51 | 0.61 | 1.62 | 29 | 9 | 28 |
| Naive raw rate > median | 0.76 | 0.51 | 0.61 | 1.62 | 29 | 9 | 28 |

### Pitchers

- Players with usable series (>= 4 games): **119** | base top-rate: **0.50**
- Fitted Beta prior: `alpha0=2.18`, `beta0=1.36` (prior good-game rate `0.615`)
- Posterior-mean rank-biserial r = `0.587`; raw-rate r = `0.586` — shrinkage improves separation.

| Estimate | Precision | Recall | F1 | Lift | tp | fp | fn |
|----------|-----------|--------|----|------|----|----|----|
| Empirical-Bayes posterior > median | 0.71 | 0.65 | 0.68 | 1.41 | 24 | 10 | 13 |
| Naive raw rate > median | 0.71 | 0.65 | 0.68 | 1.41 | 24 | 10 | 13 |
