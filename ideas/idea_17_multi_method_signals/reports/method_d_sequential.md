# Section D — Sequential Testing (Earliest Signal + Lead Time)

SPRT and one-sided CUSUM reach a real-shift-vs-noise decision in as few games as possible, then report how many days before the acquisition date the signal would have fired for top-quartile pickups.

## 2026 (primary)

### Batters

- Usable series (>= 4 games): **94** | base top-rate: **0.50**
- Population baseline: mu0 = `0.819`, sigma = `0.757`, alternative delta = `0.757` (1 sigma above baseline)

| Test | Precision | Recall | F1 | Lift | Median lead (top picks) |
|------|-----------|--------|----|------|--------------------------|
| SPRT | 1.00 | 0.15 | 0.26 | 2.00 | 8.0 days |
| CUSUM alarm | 1.00 | 0.09 | 0.16 | 2.00 | 18.0 days |

> **Lead time** = median days between the signal first firing and the actual acquisition date for top-quartile pickups: the edge was visible **~8 days (SPRT) / 18 days (CUSUM)** before the league reacted.

### Pitchers

- Usable series (>= 4 games): **88** | base top-rate: **0.50**
- Population baseline: mu0 = `9.621`, sigma = `6.877`, alternative delta = `6.877` (1 sigma above baseline)

| Test | Precision | Recall | F1 | Lift | Median lead (top picks) |
|------|-----------|--------|----|------|--------------------------|
| SPRT | 0.62 | 0.16 | 0.26 | 1.25 | 9.0 days |
| CUSUM alarm | 1.00 | 0.10 | 0.18 | 2.00 | 9.0 days |

> **Lead time** = median days between the signal first firing and the actual acquisition date for top-quartile pickups: the edge was visible **~9 days (SPRT) / 9 days (CUSUM)** before the league reacted.

---

## 2025 (cross-season)

### Batters

- Usable series (>= 4 games): **176** | base top-rate: **0.47**
- Population baseline: mu0 = `0.808`, sigma = `0.756`, alternative delta = `0.756` (1 sigma above baseline)

| Test | Precision | Recall | F1 | Lift | Median lead (top picks) |
|------|-----------|--------|----|------|--------------------------|
| SPRT | 0.76 | 0.33 | 0.46 | 1.61 | 10.0 days |
| CUSUM alarm | 0.80 | 0.14 | 0.24 | 1.70 | 10.5 days |

> **Lead time** = median days between the signal first firing and the actual acquisition date for top-quartile pickups: the edge was visible **~10 days (SPRT) / 10 days (CUSUM)** before the league reacted.

### Pitchers

- Usable series (>= 4 games): **123** | base top-rate: **0.50**
- Population baseline: mu0 = `9.896`, sigma = `7.149`, alternative delta = `7.149` (1 sigma above baseline)

| Test | Precision | Recall | F1 | Lift | Median lead (top picks) |
|------|-----------|--------|----|------|--------------------------|
| SPRT | 0.69 | 0.24 | 0.36 | 1.38 | 17.0 days |
| CUSUM alarm | 0.60 | 0.08 | 0.14 | 1.20 | 13.0 days |

> **Lead time** = median days between the signal first firing and the actual acquisition date for top-quartile pickups: the edge was visible **~17 days (SPRT) / 13 days (CUSUM)** before the league reacted.
