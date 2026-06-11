# MLB Player Injury Duration Analysis (2023 - 2026)

> **Document Purpose:** Detailed analysis of actual player recovery time spent on the Injured List (IL) compared to their initial estimated day categories (7-day, 10-day, 15-day, 60-day IL), broken down by injury type, position, and MLB team.
> **Analysis Period:** 2023 - 2026 seasons  |  **Stints Reconstructed:** 3016 total (2236 completed stints analyzed for durations)
> **Generated On:** 2026-06-10 14:22:39

## 1. Executive Summary: Estimated vs. Actual IL Durations

The table below compares the initial IL placement category against the actual time players spent before activation. Stints are categorized as *Completed* when the player was formally activated. Ongoing/uncensored stints are excluded from duration statistics to prevent downward bias.

| Estimated IL Type | Total Placements | Completed Stints | Avg Recovery (Days) | Median Recovery (Days) | Spend Minimum (<= IL Type) | Extended (> IL Type) |
|-------------------|------------------|------------------|----------------------|------------------------|----------------------------|----------------------|
| **7-day IL** | 54 | 50 | 15.5 | 9 | 34.0% (17) | 66.0% (33) |
| **10-day IL** | 1297 | 1082 | 23.9 | 16 | 38.1% (412) | 61.9% (670) |
| **15-day IL** | 1388 | 1010 | 39.6 | 28 | 23.0% (232) | 77.0% (778) |
| **60-day IL** | 277 | 94 | 110.3 | 100 | 3.2% (3) | 96.8% (91) |

> [!NOTE]
> Placements on the 60-day IL are reserved for severe injuries, and players cannot be activated before 60 days have elapsed. Consequently, the minimum actual duration for completed 60-day IL stints is mathematically >= 60 days.

## 2. Actual Duration by Injury Category & Estimated IL Type

This table breaks down actual recovery times by the diagnosed injury body part and the estimated day category. This highlights which injury types are most frequently extended beyond their minimum designations.

| Injury Category | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Max Recovery (Days) |
|-----------------|-------------------|------------|-----------|----------------------|------------------------|---------------------|
| Other/Unspecified | 7-day | 10 | 10 | 18.2 | 11 | 83 |
| Other/Unspecified | 10-day | 450 | 389 | 14.3 | 4 | 173 |
| Other/Unspecified | 15-day | 328 | 260 | 37.0 | 28 | 196 |
| Other/Unspecified | 60-day | 55 | 28 | 97.7 | 81 | 182 |
| Elbow/UCL | 10-day | 63 | 43 | 34.3 | 23 | 131 |
| Elbow/UCL | 15-day | 396 | 222 | 46.1 | 31 | 207 |
| Elbow/UCL | 60-day | 91 | 25 | 124.4 | 131 | 183 |
| Shoulder | 10-day | 64 | 49 | 44.6 | 33 | 215 |
| Shoulder | 15-day | 277 | 194 | 49.3 | 38 | 219 |
| Shoulder | 60-day | 60 | 21 | 117.2 | 113 | 209 |
| Oblique/Rib | 10-day | 153 | 130 | 28.2 | 25 | 124 |
| Oblique/Rib | 15-day | 74 | 67 | 40.0 | 35 | 125 |
| Oblique/Rib | 60-day | 11 | 4 | 104.0 | 118 | 148 |
| Wrist/Hand/Finger | 10-day | 155 | 129 | 30.6 | 24 | 118 |
| Wrist/Hand/Finger | 15-day | 58 | 54 | 31.4 | 24 | 120 |
| Wrist/Hand/Finger | 60-day | 9 | 3 | 113.7 | 100 | 145 |
| Back/Spine | 10-day | 112 | 95 | 25.4 | 17 | 138 |
| Back/Spine | 15-day | 95 | 83 | 28.0 | 22 | 122 |
| Back/Spine | 60-day | 13 | 4 | 115.0 | 123 | 130 |
| Hamstring | 10-day | 137 | 117 | 25.9 | 22 | 92 |
| Hamstring | 15-day | 60 | 56 | 28.9 | 23 | 153 |
| Hamstring | 60-day | 6 | 1 | 58.0 | 58 | 58 |
| Knee | 10-day | 70 | 54 | 28.0 | 22 | 113 |
| Knee | 15-day | 60 | 43 | 31.0 | 22 | 92 |
| Knee | 60-day | 18 | 5 | 119.0 | 112 | 181 |
| Ankle/Foot | 10-day | 90 | 74 | 27.0 | 18 | 86 |
| Ankle/Foot | 15-day | 40 | 31 | 28.7 | 20 | 104 |
| Ankle/Foot | 60-day | 14 | 3 | 64.0 | 64 | 67 |
| Concussion | 7-day | 44 | 40 | 14.8 | 9 | 152 |
| Concussion | 10-day | 3 | 2 | 33.5 | 39 | 39 |

## 3. Actual Duration by Player Position & Estimated IL Type

Pitchers (SP/RP) and hitters have different IL rules. In particular, pitchers are placed on the 15-day IL as a minimum, whereas hitters are eligible for the 10-day IL.

| Position | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Max Recovery (Days) |
|----------|-------------------|------------|-----------|----------------------|------------------------|---------------------|
| **C** | 7-day | 3 | 2 | 13.5 | 20 | 20 |
| **C** | 10-day | 62 | 55 | 18.4 | 11 | 85 |
| **C** | 15-day | 209 | 155 | 38.2 | 26 | 161 |
| **C** | 60-day | 20 | 10 | 112.7 | 118 | 175 |
| **RF** | 7-day | 3 | 3 | 11.7 | 10 | 16 |
| **RF** | 10-day | 21 | 20 | 3.2 | 3 | 7 |
| **RF** | 15-day | 99 | 78 | 34.4 | 21 | 133 |
| **RF** | 60-day | 9 | 2 | 105.5 | 113 | 113 |
| **OF** | 7-day | 3 | 2 | 7.5 | 8 | 8 |
| **OF** | 10-day | 91 | 74 | 27.8 | 18 | 154 |
| **OF** | 60-day | 2 | 1 | 87.0 | 87 | 87 |
| **SP** | 10-day | 7 | 6 | 3.3 | 3 | 5 |
| **SP** | 15-day | 71 | 51 | 38.1 | 27 | 119 |
| **SP** | 60-day | 13 | 3 | 108.0 | 102 | 132 |
| **1B** | 7-day | 5 | 5 | 53.8 | 16 | 152 |
| **1B** | 10-day | 66 | 52 | 31.9 | 23 | 173 |
| **1B** | 15-day | 1 | 1 | 46.0 | 46 | 46 |
| **LF** | 7-day | 3 | 3 | 11.0 | 12 | 16 |
| **LF** | 10-day | 62 | 52 | 23.1 | 14 | 111 |
| **LF** | 60-day | 2 | 2 | 80.5 | 91 | 91 |
| **3B** | 10-day | 54 | 49 | 29.0 | 23 | 215 |
| **3B** | 15-day | 8 | 4 | 49.8 | 25 | 158 |
| **3B** | 60-day | 2 | 2 | 83.5 | 100 | 100 |
| **RP** | 10-day | 8 | 7 | 16.6 | 3 | 93 |
| **RP** | 15-day | 50 | 39 | 30.9 | 22 | 168 |
| **RP** | 60-day | 2 | 1 | 156.0 | 156 | 156 |
| **2B** | 7-day | 1 | 1 | 8.0 | 8 | 8 |
| **2B** | 10-day | 53 | 50 | 23.2 | 15 | 99 |
| **2B** | 60-day | 2 | 1 | 128.0 | 128 | 128 |
| **SS** | 10-day | 54 | 49 | 23.8 | 14 | 118 |
| **SS** | 15-day | 1 | 1 | 44.0 | 44 | 44 |
| **1B/3B** | 7-day | 3 | 3 | 11.7 | 13 | 13 |
| **1B/3B** | 10-day | 46 | 36 | 29.6 | 19 | 162 |
| **1B/3B** | 60-day | 2 | 1 | 62.0 | 62 | 62 |
| **CF** | 7-day | 1 | 1 | 15.0 | 15 | 15 |
| **CF** | 10-day | 42 | 37 | 24.0 | 16 | 113 |
| **CF** | 15-day | 1 | 1 | 16.0 | 16 | 16 |
| **2B/SS** | 10-day | 36 | 27 | 15.1 | 11 | 44 |
| **UTIL** | 10-day | 2 | 2 | 72.5 | 104 | 104 |

## 4. Actual Duration by MLB Team & Estimated IL Type

Different team training staffs, medical protocols, and roster depths influence how long players remain on the IL before activation.

| MLB Team | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Primary Injury (Count) |
|----------|-------------------|------------|-----------|----------------------|------------------------|------------------------|
| Los Angeles Angels | 7-day | 4 | 4 | 51.2 | 30 | Other/Unspecified (33) |
|  | 10-day | 62 | 44 | 23.5 | 19 |  |
|  | 15-day | 51 | 35 | 37.3 | 21 |  |
|  | 60-day | 9 | 1 | 79.0 | 79 |  |
| Cincinnati Reds | 7-day | 3 | 3 | 8.7 | 9 | Other/Unspecified (36) |
|  | 10-day | 54 | 47 | 34.3 | 18 |  |
|  | 15-day | 55 | 45 | 34.5 | 23 |  |
|  | 60-day | 13 | 6 | 136.2 | 155 |  |
| Los Angeles Dodgers | 7-day | 1 | 1 | 12.0 | 12 | Other/Unspecified (29) |
|  | 10-day | 40 | 35 | 21.8 | 13 |  |
|  | 15-day | 73 | 52 | 52.1 | 44 |  |
|  | 60-day | 10 | 3 | 88.0 | 61 |  |
| San Francisco Giants | 7-day | 6 | 5 | 11.0 | 7 | Other/Unspecified (26) |
|  | 10-day | 63 | 55 | 17.1 | 11 |  |
|  | 15-day | 39 | 33 | 27.5 | 25 |  |
|  | 60-day | 14 | 4 | 130.8 | 134 |  |
| Boston Red Sox | 7-day | 2 | 2 | 7.5 | 10 | Other/Unspecified (38) |
|  | 10-day | 53 | 45 | 24.6 | 15 |  |
|  | 15-day | 51 | 40 | 34.1 | 26 |  |
|  | 60-day | 15 | 3 | 77.7 | 79 |  |
| Miami Marlins | 7-day | 1 | 1 | 13.0 | 13 | Other/Unspecified (39) |
|  | 10-day | 55 | 51 | 24.1 | 17 |  |
|  | 15-day | 46 | 30 | 33.1 | 24 |  |
|  | 60-day | 13 | 5 | 96.4 | 94 |  |
| Texas Rangers | 10-day | 50 | 44 | 21.4 | 11 | Other/Unspecified (30) |
|  | 15-day | 53 | 41 | 28.5 | 22 |  |
|  | 60-day | 11 | 5 | 123.0 | 127 |  |
| Chicago White Sox | 10-day | 53 | 44 | 22.1 | 13 | Other/Unspecified (32) |
|  | 15-day | 52 | 40 | 32.3 | 23 |  |
|  | 60-day | 9 | 1 | 73.0 | 73 |  |
| Minnesota Twins | 7-day | 3 | 3 | 12.0 | 13 | Other/Unspecified (33) |
|  | 10-day | 61 | 55 | 21.2 | 14 |  |
|  | 15-day | 44 | 31 | 52.0 | 36 |  |
|  | 60-day | 5 | 1 | 181.0 | 181 |  |
| Colorado Rockies | 7-day | 2 | 1 | 15.0 | 15 | Other/Unspecified (34) |
|  | 10-day | 44 | 38 | 20.2 | 12 |  |
|  | 15-day | 55 | 37 | 28.4 | 18 |  |
|  | 60-day | 8 | 6 | 141.7 | 142 |  |
| Milwaukee Brewers | 7-day | 2 | 1 | 16.0 | 16 | Other/Unspecified (34) |
|  | 10-day | 39 | 33 | 32.3 | 22 |  |
|  | 15-day | 59 | 41 | 44.6 | 29 |  |
|  | 60-day | 9 | 5 | 84.6 | 82 |  |
| Baltimore Orioles | 7-day | 4 | 4 | 9.0 | 9 | Other/Unspecified (28) |
|  | 10-day | 44 | 38 | 25.2 | 21 |  |
|  | 15-day | 47 | 33 | 39.2 | 31 |  |
|  | 60-day | 10 | 5 | 128.8 | 158 |  |
| Houston Astros | 7-day | 1 | 1 | 7.0 | 7 | Elbow/UCL (29) |
|  | 10-day | 44 | 36 | 24.4 | 18 |  |
|  | 15-day | 50 | 31 | 41.6 | 26 |  |
|  | 60-day | 10 | 3 | 101.7 | 91 |  |
| New York Yankees | 7-day | 2 | 2 | 12.0 | 16 | Other/Unspecified (36) |
|  | 10-day | 46 | 33 | 29.9 | 31 |  |
|  | 15-day | 47 | 41 | 46.8 | 42 |  |
|  | 60-day | 9 | 4 | 90.0 | 83 |  |
| Athletics | 10-day | 42 | 29 | 29.6 | 25 | Other/Unspecified (25) |
|  | 15-day | 51 | 38 | 56.6 | 38 |  |
|  | 60-day | 8 | 6 | 89.2 | 96 |  |
| Atlanta Braves | 7-day | 2 | 2 | 19.0 | 29 | Elbow/UCL (24) |
|  | 10-day | 37 | 28 | 23.9 | 15 |  |
|  | 15-day | 49 | 32 | 38.7 | 26 |  |
|  | 60-day | 12 | 2 | 116.5 | 143 |  |
| Chicago Cubs | 7-day | 2 | 2 | 11.5 | 16 | Other/Unspecified (25) |
|  | 10-day | 28 | 23 | 16.2 | 15 |  |
|  | 15-day | 58 | 43 | 34.0 | 21 |  |
|  | 60-day | 11 | 4 | 115.8 | 125 |  |
| Tampa Bay Rays | 10-day | 42 | 35 | 22.8 | 13 | Other/Unspecified (32) |
|  | 15-day | 44 | 31 | 29.0 | 21 |  |
|  | 60-day | 13 | 4 | 133.5 | 136 |  |
| New York Mets | 10-day | 39 | 32 | 26.2 | 16 | Other/Unspecified (33) |
|  | 15-day | 47 | 30 | 45.5 | 31 |  |
|  | 60-day | 9 | 2 | 89.5 | 117 |  |
| Kansas City Royals | 7-day | 3 | 3 | 7.3 | 7 | Other/Unspecified (21) |
|  | 10-day | 34 | 28 | 21.2 | 12 |  |
|  | 15-day | 50 | 37 | 39.2 | 28 |  |
|  | 60-day | 6 | 2 | 87.5 | 113 |  |
| Pittsburgh Pirates | 7-day | 4 | 4 | 16.2 | 20 | Other/Unspecified (28) |
|  | 10-day | 45 | 37 | 20.9 | 17 |  |
|  | 15-day | 36 | 26 | 47.3 | 33 |  |
|  | 60-day | 7 | 3 | 132.7 | 154 |  |
| Toronto Blue Jays | 7-day | 4 | 4 | 10.0 | 9 | Elbow/UCL (21) |
|  | 10-day | 40 | 34 | 21.1 | 15 |  |
|  | 15-day | 38 | 26 | 42.4 | 34 |  |
|  | 60-day | 9 | 3 | 136.0 | 156 |  |
| San Diego Padres | 7-day | 2 | 1 | 8.0 | 8 | Other/Unspecified (24) |
|  | 10-day | 34 | 26 | 24.2 | 20 |  |
|  | 15-day | 47 | 31 | 41.9 | 33 |  |
|  | 60-day | 6 | 2 | 86.0 | 102 |  |
| Detroit Tigers | 10-day | 38 | 30 | 26.4 | 26 | Other/Unspecified (37) |
|  | 15-day | 38 | 26 | 33.5 | 22 |  |
|  | 60-day | 12 | 4 | 72.0 | 75 |  |
| Arizona Diamondbacks | 10-day | 37 | 31 | 29.7 | 21 | Back/Spine (28) |
|  | 15-day | 41 | 28 | 36.8 | 29 |  |
|  | 60-day | 9 | 1 | 114.0 | 114 |  |
| Seattle Mariners | 7-day | 2 | 2 | 8.5 | 10 | Other/Unspecified (29) |
|  | 10-day | 32 | 27 | 26.1 | 19 |  |
|  | 15-day | 40 | 29 | 39.6 | 34 |  |
|  | 60-day | 5 | 2 | 82.0 | 87 |  |
| St. Louis Cardinals | 7-day | 1 | 1 | 7.0 | 7 | Other/Unspecified (17) |
|  | 10-day | 42 | 38 | 25.2 | 17 |  |
|  | 15-day | 26 | 22 | 46.2 | 29 |  |
|  | 60-day | 5 | 2 | 134.0 | 145 |  |
| Cleveland Guardians | 7-day | 2 | 2 | 6.5 | 7 | Other/Unspecified (27) |
|  | 10-day | 28 | 24 | 13.8 | 8 |  |
|  | 15-day | 37 | 30 | 51.7 | 51 |  |
|  | 60-day | 5 | 2 | 67.5 | 73 |  |
| Washington Nationals | 7-day | 1 | 1 | 83.0 | 83 | Other/Unspecified (25) |
|  | 10-day | 32 | 28 | 25.0 | 16 |  |
|  | 15-day | 29 | 21 | 31.6 | 19 |  |
|  | 60-day | 10 | 2 | 186.0 | 189 |  |
| Philadelphia Phillies | 10-day | 32 | 32 | 22.9 | 14 | Other/Unspecified (16) |
|  | 15-day | 33 | 29 | 38.7 | 31 |  |
|  | 60-day | 5 | 1 | 82.0 | 82 |  |
| National League All-Stars | 15-day | 2 | 1 | 67.0 | 67 | Other/Unspecified (4) |
| American League All-Stars | 10-day | 4 | 2 | 35.5 | 67 | Other/Unspecified (3) |

