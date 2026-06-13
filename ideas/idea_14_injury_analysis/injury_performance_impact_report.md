# MLB Injury Performance Impact Analysis (2023 - 2026)

> **Generated On:** 2026-06-12 18:04:01
> **Methodology:** Evaluates active player performance over a **28-game active window** before IL placement against a **28-game active window** immediately following IL activation. Stints are filtered to include only players with a minimum of **10 active games** in both windows to ensure statistical integrity. Counting stats (R, HR, RBI, SB, QS, SVHD) are scaled to a standard 28-game representation.

## 1. Overall Performance Impact & Distribution by IL Length

This section standardizes overall player value across all 5 batter/pitcher scoring categories using Z-scores to evaluate whether players return better or worse from various IL lengths (7-day, 10-day, 15-day, 60-day).

### Post-IL Performance Change Distributions
Below is the generated 3x2 grid of histograms showing the distribution of Z-score changes. Green represents improvement, while red represents regression. The percentage of players getting better vs. worse is summarized in each chart:

![Post-IL Performance Distribution](../../pjrigali.github.io/assets/images/injury_performance_histograms.png)

### Batters: Summary of Improvement vs. Regression by IL Type

| IL Type | Stints | Worse % (< 0 Delta Z) | Better % (>= 0 Delta Z) | Median Z-Score Delta |
|---------|--------|------------------------|-------------------------|----------------------|
| 7-day IL | 26 | 57.7% | 42.3% | -1.76 |
| 10-day IL | 517 | 49.9% | 50.1% | +0.02 |
| 60-day IL | 4 | 50.0% | 50.0% | +2.06 |

### Pitchers: Summary of Improvement vs. Regression by IL Type

| IL Type | Stints | Worse % (< 0 Delta Z) | Better % (>= 0 Delta Z) | Median Z-Score Delta |
|---------|--------|------------------------|-------------------------|----------------------|
| 10-day IL | 62 | 64.5% | 35.5% | -0.67 |
| 15-day IL | 183 | 56.3% | 43.7% | -0.66 |
| 60-day IL | 1 | 0.0% | 100.0% | +4.72 |

### Batters by IL Length

| IL Type | Stints | Avg Duration (Days) | Pre OPS | Post OPS | OPS Δ | R Δ | HR Δ | RBI Δ | SB Δ |
|---------|--------|---------------------|---------|----------|-------|-----|------|-------|------|
| 7-day IL | 26 | 15.3 | 0.782 | 0.694 | -0.088 | -1.1 | -1.1 | -2.1 | -0.6 |
| 10-day IL | 517 | 21.7 | 0.718 | 0.717 | -0.001 | -0.2 | +0.1 | -0.1 | -0.3 |
| 60-day IL | 4 | 75.0 | 0.701 | 0.759 | +0.057 | +0.3 | -0.4 | -0.1 | +0.8 |

### Starting Pitchers (SP) by IL Length

| IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | QS Δ |
|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|------|
| 10-day IL | 14 | 3.2 | 3.56 | 4.18 | +0.62 | 1.21 | 1.32 | +0.12 | +0.2 | -1.9 |
| 15-day IL | 35 | 23.3 | 4.36 | 4.82 | +0.46 | 1.33 | 1.37 | +0.04 | -0.1 | -2.5 |
| 60-day IL | 1 | 62.0 | 6.15 | 3.84 | -2.32 | 1.29 | 1.20 | -0.09 | +2.7 | +5.6 |

### Relief Pitchers (RP) by IL Length

| IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | SVHD Δ |
|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|--------|
| 7-day IL | 1 | 8.0 | 3.18 | 4.80 | +1.62 | 1.41 | 1.27 | -0.15 | +5.7 | +1.7 |
| 10-day IL | 48 | 3.6 | 3.05 | 4.16 | +1.11 | 1.20 | 1.27 | +0.07 | -0.4 | +0.1 |
| 15-day IL | 148 | 27.2 | 3.96 | 4.17 | +0.21 | 1.30 | 1.32 | +0.03 | -0.3 | -1.2 |

## 2. Batting Performance Impact by Category & IL Length

| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre OPS | Post OPS | OPS Δ | R Δ | HR Δ | RBI Δ | SB Δ |
|-----------------|---------|--------|---------------------|---------|----------|-------|-----|------|-------|------|
| **Other/Unspecified (All)** | - | **159** | **13.2** | **0.742** | **0.719** | **-0.023** | **-0.5** | **-0.1** | **-0.5** | **-0.4** |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 7-day | 1 | 13.0 | 0.953 | 0.980 | +0.028 | -2.0 | +1.0 | +3.0 | +2.0 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 10-day | 155 | 12.0 | 0.740 | 0.715 | -0.025 | -0.5 | -0.1 | -0.6 | -0.4 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 60-day | 3 | 80.0 | 0.770 | 0.829 | +0.059 | +1.8 | -0.2 | +0.6 | +0.8 |
| **Hamstring (All)** | - | **79** | **23.6** | **0.710** | **0.714** | **+0.004** | **-0.2** | **+0.4** | **+0.4** | **-0.1** |
| &nbsp;&nbsp;&bull;&nbsp;Hamstring | 10-day | 79 | 23.6 | 0.710 | 0.714 | +0.004 | -0.2 | +0.4 | +0.4 | -0.1 |
| **Oblique/Rib (All)** | - | **63** | **26.8** | **0.752** | **0.741** | **-0.011** | **-0.7** | **-0.4** | **-0.6** | **-0.2** |
| &nbsp;&nbsp;&bull;&nbsp;Oblique/Rib | 10-day | 62 | 26.3 | 0.756 | 0.744 | -0.012 | -0.7 | -0.4 | -0.6 | -0.3 |
| &nbsp;&nbsp;&bull;&nbsp;Oblique/Rib | 60-day | 1 | 60.0 | 0.495 | 0.546 | +0.051 | -4.0 | -1.0 | -2.0 | +1.0 |
| **Wrist/Hand/Finger (All)** | - | **62** | **25.9** | **0.679** | **0.718** | **+0.039** | **+0.2** | **+0.7** | **+0.9** | **-0.3** |
| &nbsp;&nbsp;&bull;&nbsp;Wrist/Hand/Finger | 10-day | 62 | 25.9 | 0.679 | 0.718 | +0.039 | +0.2 | +0.7 | +0.9 | -0.3 |
| **Back/Spine (All)** | - | **48** | **23.2** | **0.694** | **0.718** | **+0.023** | **-0.0** | **-0.1** | **-0.3** | **-0.2** |
| &nbsp;&nbsp;&bull;&nbsp;Back/Spine | 10-day | 48 | 23.2 | 0.694 | 0.718 | +0.023 | -0.0 | -0.1 | -0.3 | -0.2 |
| **Ankle/Foot (All)** | - | **41** | **25.1** | **0.726** | **0.709** | **-0.017** | **-0.9** | **-0.2** | **-1.1** | **-0.6** |
| &nbsp;&nbsp;&bull;&nbsp;Ankle/Foot | 10-day | 41 | 25.1 | 0.726 | 0.709 | -0.017 | -0.9 | -0.2 | -1.1 | -0.6 |
| **Concussion (All)** | - | **27** | **16.7** | **0.788** | **0.683** | **-0.105** | **-1.2** | **-1.3** | **-3.0** | **-0.8** |
| &nbsp;&nbsp;&bull;&nbsp;Concussion | 7-day | 25 | 15.4 | 0.776 | 0.683 | -0.093 | -1.1 | -1.2 | -2.3 | -0.7 |
| &nbsp;&nbsp;&bull;&nbsp;Concussion | 10-day | 2 | 33.5 | 0.940 | 0.686 | -0.255 | -2.8 | -3.4 | -11.0 | -1.9 |
| **Knee (All)** | - | **23** | **23.0** | **0.741** | **0.694** | **-0.046** | **+0.0** | **+0.4** | **-1.0** | **-0.1** |
| &nbsp;&nbsp;&bull;&nbsp;Knee | 10-day | 23 | 23.0 | 0.741 | 0.694 | -0.046 | +0.0 | +0.4 | -1.0 | -0.1 |
| **Elbow/UCL (All)** | - | **23** | **32.0** | **0.678** | **0.713** | **+0.035** | **+0.3** | **-0.3** | **+0.6** | **-0.5** |
| &nbsp;&nbsp;&bull;&nbsp;Elbow/UCL | 10-day | 23 | 32.0 | 0.678 | 0.713 | +0.035 | +0.3 | -0.3 | +0.6 | -0.5 |
| **Shoulder (All)** | - | **22** | **36.8** | **0.641** | **0.718** | **+0.077** | **+2.3** | **+1.2** | **+2.7** | **-0.1** |
| &nbsp;&nbsp;&bull;&nbsp;Shoulder | 10-day | 22 | 36.8 | 0.641 | 0.718 | +0.077 | +2.3 | +1.2 | +2.7 | -0.1 |

## 3. Starting Pitcher (SP) Performance Impact by Category & IL Length

| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | QS Δ |
|-----------------|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|------|
| **Other/Unspecified (All)** | - | **21** | **13.7** | **4.02** | **4.37** | **+0.36** | **1.29** | **1.33** | **+0.04** | **+0.1** | **-0.8** |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 10-day | 13 | 3.1 | 3.61 | 4.32 | +0.71 | 1.23 | 1.35 | +0.12 | +0.1 | -1.7 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 15-day | 7 | 26.4 | 4.47 | 4.56 | +0.09 | 1.39 | 1.30 | -0.09 | -0.2 | +0.1 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 60-day | 1 | 62.0 | 6.15 | 3.84 | -2.32 | 1.29 | 1.20 | -0.09 | +2.7 | +5.6 |
| **Elbow/UCL (All)** | - | **7** | **29.3** | **3.65** | **4.17** | **+0.51** | **1.22** | **1.27** | **+0.05** | **+0.1** | **-3.4** |
| &nbsp;&nbsp;&bull;&nbsp;Elbow/UCL | 15-day | 7 | 29.3 | 3.65 | 4.17 | +0.51 | 1.22 | 1.27 | +0.05 | +0.1 | -3.4 |
| **Shoulder (All)** | - | **5** | **16.4** | **5.14** | **6.68** | **+1.53** | **1.44** | **1.74** | **+0.30** | **-1.3** | **-3.3** |
| &nbsp;&nbsp;&bull;&nbsp;Shoulder | 15-day | 5 | 16.4 | 5.14 | 6.68 | +1.53 | 1.44 | 1.74 | +0.30 | -1.3 | -3.3 |
| **Back/Spine (All)** | - | **5** | **19.0** | **4.65** | **4.14** | **-0.51** | **1.38** | **1.22** | **-0.15** | **+0.8** | **-1.5** |
| &nbsp;&nbsp;&bull;&nbsp;Back/Spine | 15-day | 5 | 19.0 | 4.65 | 4.14 | -0.51 | 1.38 | 1.22 | -0.15 | +0.8 | -1.5 |
| **Ankle/Foot (All)** | - | **5** | **17.0** | **4.38** | **4.42** | **+0.04** | **1.27** | **1.30** | **+0.03** | **+0.8** | **-3.4** |
| &nbsp;&nbsp;&bull;&nbsp;Ankle/Foot | 10-day | 1 | 5.0 | 2.96 | 2.44 | -0.52 | 0.92 | 0.95 | +0.03 | +1.2 | -4.7 |
| &nbsp;&nbsp;&bull;&nbsp;Ankle/Foot | 15-day | 4 | 20.0 | 4.73 | 4.91 | +0.18 | 1.36 | 1.38 | +0.03 | +0.7 | -3.0 |
| **Oblique/Rib (All)** | - | **2** | **13.0** | **3.90** | **5.17** | **+1.27** | **1.41** | **1.39** | **-0.02** | **-1.0** | **-1.3** |
| &nbsp;&nbsp;&bull;&nbsp;Oblique/Rib | 15-day | 2 | 13.0 | 3.90 | 5.17 | +1.27 | 1.41 | 1.39 | -0.02 | -1.0 | -1.3 |
| **Hamstring (All)** | - | **2** | **35.5** | **3.76** | **4.39** | **+0.63** | **1.15** | **1.25** | **+0.10** | **+0.4** | **-2.1** |
| &nbsp;&nbsp;&bull;&nbsp;Hamstring | 15-day | 2 | 35.5 | 3.76 | 4.39 | +0.63 | 1.15 | 1.25 | +0.10 | +0.4 | -2.1 |
| **Wrist/Hand/Finger (All)** | - | **2** | **24.5** | **3.05** | **4.42** | **+1.37** | **0.96** | **1.30** | **+0.33** | **-0.6** | **-7.1** |
| &nbsp;&nbsp;&bull;&nbsp;Wrist/Hand/Finger | 15-day | 2 | 24.5 | 3.05 | 4.42 | +1.37 | 0.96 | 1.30 | +0.33 | -0.6 | -7.1 |
| **Knee (All)** | - | **1** | **21.0** | **6.44** | **5.96** | **-0.48** | **1.68** | **1.62** | **-0.06** | **+0.5** | **-8.4** |
| &nbsp;&nbsp;&bull;&nbsp;Knee | 15-day | 1 | 21.0 | 6.44 | 5.96 | -0.48 | 1.68 | 1.62 | -0.06 | +0.5 | -8.4 |

## 4. Relief Pitcher (RP) Performance Impact by Category & IL Length

| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | SVHD Δ |
|-----------------|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|--------|
| **Other/Unspecified (All)** | - | **93** | **15.2** | **3.67** | **4.35** | **+0.68** | **1.26** | **1.29** | **+0.03** | **-0.5** | **-0.0** |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 7-day | 1 | 8.0 | 3.18 | 4.80 | +1.62 | 1.41 | 1.27 | -0.15 | +5.7 | +1.7 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 10-day | 47 | 3.7 | 3.05 | 4.09 | +1.04 | 1.20 | 1.27 | +0.07 | -0.3 | +0.4 |
| &nbsp;&nbsp;&bull;&nbsp;Other/Unspecified | 15-day | 45 | 27.4 | 4.32 | 4.61 | +0.29 | 1.32 | 1.31 | -0.02 | -0.7 | -0.4 |
| **Elbow/UCL (All)** | - | **32** | **28.6** | **3.42** | **4.00** | **+0.58** | **1.25** | **1.35** | **+0.10** | **+0.7** | **-1.1** |
| &nbsp;&nbsp;&bull;&nbsp;Elbow/UCL | 15-day | 32 | 28.6 | 3.42 | 4.00 | +0.58 | 1.25 | 1.35 | +0.10 | +0.7 | -1.1 |
| **Shoulder (All)** | - | **19** | **27.9** | **4.14** | **4.71** | **+0.57** | **1.30** | **1.40** | **+0.10** | **-0.6** | **-1.7** |
| &nbsp;&nbsp;&bull;&nbsp;Shoulder | 15-day | 19 | 27.9 | 4.14 | 4.71 | +0.57 | 1.30 | 1.40 | +0.10 | -0.6 | -1.7 |
| **Back/Spine (All)** | - | **17** | **21.9** | **4.23** | **3.81** | **-0.43** | **1.33** | **1.29** | **-0.05** | **-1.2** | **-3.5** |
| &nbsp;&nbsp;&bull;&nbsp;Back/Spine | 10-day | 1 | 3.0 | 3.27 | 7.58 | +4.31 | 1.36 | 1.63 | +0.27 | -3.7 | -10.3 |
| &nbsp;&nbsp;&bull;&nbsp;Back/Spine | 15-day | 16 | 23.1 | 4.29 | 3.57 | -0.72 | 1.33 | 1.27 | -0.07 | -1.1 | -3.0 |
| **Oblique/Rib (All)** | - | **14** | **33.5** | **2.77** | **3.95** | **+1.18** | **1.13** | **1.37** | **+0.24** | **+0.2** | **-2.4** |
| &nbsp;&nbsp;&bull;&nbsp;Oblique/Rib | 15-day | 14 | 33.5 | 2.77 | 3.95 | +1.18 | 1.13 | 1.37 | +0.24 | +0.2 | -2.4 |
| **Hamstring (All)** | - | **10** | **25.7** | **3.01** | **3.94** | **+0.93** | **1.22** | **1.28** | **+0.06** | **-0.6** | **-2.7** |
| &nbsp;&nbsp;&bull;&nbsp;Hamstring | 15-day | 10 | 25.7 | 3.01 | 3.94 | +0.93 | 1.22 | 1.28 | +0.06 | -0.6 | -2.7 |
| **Knee (All)** | - | **5** | **20.6** | **6.50** | **3.56** | **-2.94** | **1.59** | **1.27** | **-0.32** | **-0.4** | **+0.3** |
| &nbsp;&nbsp;&bull;&nbsp;Knee | 15-day | 5 | 20.6 | 6.50 | 3.56 | -2.94 | 1.59 | 1.27 | -0.32 | -0.4 | +0.3 |
| **Wrist/Hand/Finger (All)** | - | **4** | **25.0** | **5.05** | **2.76** | **-2.29** | **1.48** | **1.18** | **-0.31** | **-1.3** | **+2.6** |
| &nbsp;&nbsp;&bull;&nbsp;Wrist/Hand/Finger | 15-day | 4 | 25.0 | 5.05 | 2.76 | -2.29 | 1.48 | 1.18 | -0.31 | -1.3 | +2.6 |
| **Ankle/Foot (All)** | - | **3** | **17.7** | **4.47** | **3.84** | **-0.64** | **1.54** | **1.39** | **-0.15** | **-1.3** | **+1.6** |
| &nbsp;&nbsp;&bull;&nbsp;Ankle/Foot | 15-day | 3 | 17.7 | 4.47 | 3.84 | -0.64 | 1.54 | 1.39 | -0.15 | -1.3 | +1.6 |

## 5. Individual Player Case Studies (Recent Large Stints)

A sample of high-impact hitters and pitchers showing the largest performance changes post-activation:

### Hitters with Largest Post-IL OPS Drops

| Player | Injury Category | IL Duration | Pre OPS | Post OPS | OPS Δ | HR Δ | SB Δ |
|--------|-----------------|-------------|---------|----------|-------|------|------|
| Logan O'Hoppe | Concussion | 152 days | 1.014 | 0.416 | -0.598 | -10.8 | +0.0 |
| Max Muncy | Oblique/Rib | 24 days | 1.109 | 0.562 | -0.546 | -2.9 | -1.0 |
| Cristian Pache | Elbow/UCL | 49 days | 0.957 | 0.433 | -0.524 | -2.7 | +0.5 |
| Tyler O'Neill | Concussion | 5 days | 1.209 | 0.695 | -0.514 | -9.1 | -1.9 |
| Evan Longoria | Back/Spine | 23 days | 0.921 | 0.448 | -0.474 | -6.0 | +0.0 |
| Jose Miranda | Back/Spine | 13 days | 1.058 | 0.608 | -0.450 | -3.0 | -1.0 |
| Royce Lewis | Knee | 10 days | 0.822 | 0.382 | -0.440 | -3.3 | -3.3 |
| Max Muncy | Other/Unspecified | 3 days | 1.129 | 0.690 | -0.439 | -8.0 | -1.3 |
| Austin Hays | Hamstring | 7 days | 1.143 | 0.706 | -0.436 | -7.8 | -1.2 |
| Weston Wilson | Other/Unspecified | 2 days | 1.017 | 0.588 | -0.429 | -4.0 | -1.2 |

### Pitchers with Largest Post-IL ERA Increases

| Player | Injury Category | IL Duration | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ |
|--------|-----------------|-------------|---------|----------|-------|----------|-----------|--------|
| Jimmy Herget | Other/Unspecified | 4 days | 1.50 | 15.75 | +14.25 | 0.83 | 3.00 | +2.17 |
| Zach Agnos | Other/Unspecified | 3 days | 1.50 | 13.50 | +12.00 | 0.83 | 2.48 | +1.64 |
| Shawn Dubin | Elbow/UCL | 49 days | 1.33 | 10.80 | +9.47 | 1.13 | 1.88 | +0.74 |
| Kyle Freeland | Shoulder | 13 days | 2.30 | 11.47 | +9.18 | 1.09 | 2.14 | +1.05 |
| Steven Matz | Elbow/UCL | 15 days | 3.34 | 12.10 | +8.76 | 1.05 | 2.28 | +1.22 |
| Yunior Marte | Shoulder | 53 days | 2.70 | 11.37 | +8.67 | 1.27 | 2.53 | +1.25 |
| Trevor Richards | Other/Unspecified | 15 days | 2.81 | 10.80 | +7.99 | 1.06 | 1.91 | +0.85 |
| Steven Wilson | Back/Spine | 21 days | 2.84 | 9.19 | +6.35 | 1.26 | 1.98 | +0.72 |
| Fernando Cruz | Other/Unspecified | 7 days | 2.43 | 8.74 | +6.31 | 1.04 | 1.24 | +0.19 |
| Graham Ashcraft | Other/Unspecified | 3 days | 1.26 | 6.97 | +5.71 | 1.26 | 1.26 | +0.00 |
