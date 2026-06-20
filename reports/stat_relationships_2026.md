# Idea 5 - Box Score Stat Relationships: Correlation, Redundancy & Category-System Audit

*Generated 2026-06-20 15:04 from MLB game logs 2023-2026. League: Head-to-Head 5x5 **Categories** (see `scoring.md`) - there are no point weights; this audit measures how independent the 10 categories actually are.*

## Method

- **Stat source (locked):** MLB game logs for every season including 2026. ESPN files are used only to overlay fantasy-team holdings and market valuation (2026).
- **Sample filters (per season):** batters >= 50 AB, pitchers >= 20 IP.
- **Qualified player-seasons:** 1997 batters, 2013 pitchers (413 / 380 in 2026).
- Rate stats (OPS, ERA, WHIP, K/9) recomputed from summed components, not averaged.
- Redundancy threshold |r| >= 0.70; scarce threshold max|r| < 0.40.

## 1-2. Scoring-Category Correlation Block (pooled 2023-2026)

### Batting categories (Pearson)

| | R | HR | RBI | SB | OPS |
|---|---|---|---|---|---|
| **R** | 1.00 | 0.86 | 0.92 | 0.54 | 0.59 |
| **HR** | 0.86 | 1.00 | 0.92 | 0.31 | 0.64 |
| **RBI** | 0.92 | 0.92 | 1.00 | 0.39 | 0.61 |
| **SB** | 0.54 | 0.31 | 0.39 | 1.00 | 0.22 |
| **OPS** | 0.59 | 0.64 | 0.61 | 0.22 | 1.00 |

### Pitching categories (Pearson)

| | K/9 | QS | SVHD | ERA | WHIP |
|---|---|---|---|---|---|
| **K/9** | 1.00 | -0.03 | 0.37 | -0.27 | -0.26 |
| **QS** | -0.03 | 1.00 | -0.39 | -0.11 | -0.19 |
| **SVHD** | 0.37 | -0.39 | 1.00 | -0.35 | -0.28 |
| **ERA** | -0.27 | -0.11 | -0.35 | 1.00 | 0.79 |
| **WHIP** | -0.26 | -0.19 | -0.28 | 0.79 | 1.00 |

Full correlation matrices across all supporting stats are saved to `2026_local_stat_correlations_batter.csv` and `2026_local_stat_correlations_pitcher.csv`.

## 3. Redundancy / Independence Audit

### Redundant category pairs (|r| >= 0.70) - effectively double/triple-counted

| Side | Pair | Pearson r |
|---|---|---|
| Batting | R <-> RBI | 0.92 |
| Batting | HR <-> RBI | 0.92 |
| Batting | R <-> HR | 0.86 |
| Pitching | ERA <-> WHIP | 0.79 |

### Scarce / orthogonal categories (max |r| with any other category < 0.40)

| Side | Category | Max |r| vs others |
|---|---|---|
| Pitching | K/9 | 0.37 |
| Pitching | QS | 0.39 |
| Pitching | SVHD | 0.39 |

**Primary differentiator (most independent category, lowest mean |r|):** Batting -> **SB** (mean |r| 0.37); Pitching -> **QS** (mean |r| 0.18). Even where it sits just above the scarce threshold, this is the category that least 'comes for free' with the correlated bundle.

### Effective dimensionality of the category set (PCA)

- **Batting:** participation ratio = 1.88 of 5 axes; 3 PCs explain 90% of variance. Explained-variance ratios: 0.70, 0.17, 0.10, 0.02, 0.01.
- **Pitching:** participation ratio = 3.30 of 5 axes; 4 PCs explain 90% of variance. Explained-variance ratios: 0.44, 0.28, 0.16, 0.08, 0.04.

## 5. Cross-Season Stability (per-season Pearson, 2023-2026)

### Batting category pairs

| Pair | mean r | std | min | max |
|---|---|---|---|---|
| HR<->RBI | 0.90 | 0.04 | 0.84 | 0.93 |
| R<->RBI | 0.90 | 0.03 | 0.85 | 0.92 |
| R<->HR | 0.84 | 0.03 | 0.78 | 0.86 |
| HR<->OPS | 0.68 | 0.02 | 0.65 | 0.70 |
| RBI<->OPS | 0.66 | 0.03 | 0.62 | 0.68 |
| R<->OPS | 0.65 | 0.02 | 0.61 | 0.67 |
| R<->SB | 0.51 | 0.05 | 0.43 | 0.57 |
| RBI<->SB | 0.34 | 0.06 | 0.24 | 0.41 |
| HR<->SB | 0.26 | 0.08 | 0.13 | 0.33 |
| SB<->OPS | 0.22 | 0.05 | 0.13 | 0.26 |

### Pitching category pairs

| Pair | mean r | std | min | max |
|---|---|---|---|---|
| ERA<->WHIP | 0.79 | 0.01 | 0.77 | 0.80 |
| QS<->SVHD | -0.42 | 0.04 | -0.50 | -0.39 |
| K/9<->SVHD | 0.37 | 0.03 | 0.33 | 0.41 |
| SVHD<->ERA | -0.36 | 0.05 | -0.44 | -0.30 |
| SVHD<->WHIP | -0.28 | 0.05 | -0.31 | -0.19 |
| K/9<->ERA | -0.27 | 0.06 | -0.36 | -0.20 |
| K/9<->WHIP | -0.26 | 0.04 | -0.31 | -0.19 |
| QS<->WHIP | -0.20 | 0.02 | -0.23 | -0.19 |
| QS<->ERA | -0.12 | 0.00 | -0.12 | -0.11 |
| K/9<->QS | -0.04 | 0.01 | -0.05 | -0.02 |

## 4. Player Archetypes - Batters

k-means on PCA(3) of the batters stat profile. Selected k by silhouette.

### Contact Bat  _(cluster 2, n=708, 136 in 2026)_
- **Category line:** R 37.96 (z+0.0) · HR 9.04 (z-0.1) · RBI 38.47 (z+0.1) · SB 3.69 (z-0.3) · OPS 0.70 (z+0.1)
- **Representative players:** Eli White (2026), Victor Caratini (2023), Joshua Palacios (2023), Liam Hicks (2025), Luis Matos (2025)
- **Avg ownership (2026):** 25.6% (n=124)

### Free-Swinger Bat  _(cluster 1, n=555, 105 in 2026)_
- **Category line:** R 17.14 (z-0.7) · HR 4.02 (z-0.6) · RBI 16.15 (z-0.7) · SB 2.33 (z-0.4) · OPS 0.57 (z-1.1)
- **Representative players:** Tyler O'Neill (2026), Jesse Winker (2023), Jose Herrera (2025), Carlos Narváez (2026), Yu Chang (2023)
- **Avg ownership (2026):** 7.3% (n=95)

### Power Bat  _(cluster 0, n=446, 103 in 2026)_
- **Category line:** R 56.24 (z+0.7) · HR 18.78 (z+1.0) · RBI 56.13 (z+0.8) · SB 6.03 (z+0.0) · OPS 0.83 (z+1.2)
- **Representative players:** Teoscar Hernández (2024), Curtis Mead (2026), Riley Greene (2026), Gunnar Henderson (2023), J.P. Crawford (2023)
- **Avg ownership (2026):** 51.6% (n=98)

### Speed Contact Bat  _(cluster 3, n=288, 69 in 2026)_
- **Category line:** R 43.45 (z+0.2) · HR 7.78 (z-0.2) · RBI 34.11 (z-0.1) · SB 18.12 (z+1.5) · OPS 0.69 (z-0.0)
- **Representative players:** Sam Haggerty (2025), Hyeseong Kim (2025), Pete Crow-Armstrong (2024), Brandon Lockridge (2026), Bryson Stott (2026)
- **Avg ownership (2026):** 28.3% (n=60)

**2026 team holdings by archetype (Batters):**

| Fantasy team | Contact Bat | Free-Swinger Bat | Power Bat | Speed Contact Bat |
|---|---|---|---|---|
| All Rise | 3 | 0 | 10 | 4 |
| Big Dumpers | 7 | 6 | 6 | 1 |
| Big Papi | 1 | 1 | 0 | 0 |
| Datalickmyballs | 8 | 2 | 10 | 4 |
| Dingers Only | 10 | 4 | 11 | 6 |
| Long Bohms Away | 2 | 1 | 1 | 0 |
| Midnight Muncy's | 1 | 4 | 9 | 4 |
| Rock and Aroldis | 11 | 2 | 6 | 2 |
| Shohei Me the Money | 12 | 1 | 3 | 3 |
| Skubal Snacks | 4 | 3 | 7 | 7 |
| This Schlitt is Bazzanas | 2 | 3 | 9 | 7 |
| This Sh!t is Bazzana | 1 | 1 | 0 | 0 |
| Welcome to the JUNGle | 6 | 2 | 10 | 2 |

## 4. Player Archetypes - Pitchers

k-means on PCA(3) of the pitchers stat profile. Selected k by silhouette.

### Reliever Ratio-Anchor (SV/HD)  _(cluster 0, n=736, 140 in 2026)_
- **Category line:** K/9 9.57 (z+0.5) · QS 0.03 (z-0.6) · SVHD 14.60 (z+0.9) · ERA 3.24 (z-0.6) · WHIP 1.18 (z-0.5)
- **Representative players:** A.J. Puk (2023), Adrian Morejon (2024), Anthony Bender (2024), Sam Hentges (2023), Robert Garcia (2024)
- **Avg ownership (2026):** 11.7% (n=127)

### Starter  _(cluster 2, n=701, 135 in 2026)_
- **Category line:** K/9 8.39 (z-0.1) · QS 7.31 (z+0.9) · SVHD 0.42 (z-0.6) · ERA 3.80 (z-0.3) · WHIP 1.20 (z-0.4)
- **Representative players:** Martín Pérez (2025), Luis Morales (2025), Quinn Priester (2025), Jose Quintana (2023), Eduardo Rodriguez (2026)
- **Avg ownership (2026):** 43.4% (n=126)

### Swingman Volatile  _(cluster 1, n=576, 105 in 2026)_
- **Category line:** K/9 7.84 (z-0.4) · QS 1.13 (z-0.4) · SVHD 2.47 (z-0.4) · ERA 5.81 (z+1.1) · WHIP 1.56 (z+1.1)
- **Representative players:** Dallas Keuchel (2023), Hogan Harris (2023), Brent Headrick (2023), Brandon Pfaadt (2026), Paxton Schultz (2026)
- **Avg ownership (2026):** 7.7% (n=96)

**2026 team holdings by archetype (Pitchers):**

| Fantasy team | Reliever Ratio-Anchor (SV/HD) | Starter | Swingman Volatile |
|---|---|---|---|
| All Rise | 3 | 6 | 5 |
| Big Dumpers | 2 | 8 | 3 |
| Big Papi | 0 | 0 | 2 |
| Datalickmyballs | 5 | 6 | 4 |
| Dingers Only | 5 | 9 | 4 |
| Long Bohms Away | 1 | 0 | 0 |
| Midnight Muncy's | 7 | 8 | 1 |
| Rock and Aroldis | 4 | 13 | 1 |
| Shohei Me the Money | 5 | 7 | 0 |
| Skubal Snacks | 4 | 12 | 3 |
| This Schlitt is Bazzanas | 7 | 13 | 1 |
| Welcome to the JUNGle | 7 | 8 | 3 |

## 6. Market Valuation by Archetype (2026)

Average ESPN ownership % per archetype - high category value at low ownership signals a market the league can exploit; low value at high ownership is a trap.

| Side | Archetype | Avg pct_owned | n |
|---|---|---|---|
| Batting | Power Bat | 51.6% | 98 |
| Batting | Speed Contact Bat | 28.3% | 60 |
| Batting | Contact Bat | 25.6% | 124 |
| Batting | Free-Swinger Bat | 7.3% | 95 |
| Pitching | Starter | 43.4% | 126 |
| Pitching | Reliever Ratio-Anchor (SV/HD) | 11.7% | 127 |
| Pitching | Swingman Volatile | 7.7% | 96 |

## Roster-Construction Takeaways

- **The batting bundle HR, R, RBI is effectively one category** (pairwise r up to 0.92). Any high-volume bat in a good lineup wins all three together - do not pay a separate premium for each; one or two elite run-producers covers the bundle.
- **SB is the batting differentiator** (mean |r| 0.37 - the lowest of the five). It does not ride along with the power bundle, so it must be targeted deliberately with dedicated sources or it is simply lost. This is where batting matchups are actually decided.
- **ERA and WHIP move together** (r=0.79) - a single strong-ratio arm helps both, but a blow-up hurts both, so ratio categories are won/lost as a pair.
- **K/9, QS, and SVHD are three independent pitching levers** (each weakly correlated with the rest). They are won by *roster construction*, not ace quality: SVHD needs dedicated saves+holds arms, QS needs innings-eating starters, and K/9 needs strikeout stuff - a staff of great-ratio pitchers can still lose all three.
- **Effective dimensionality:** the batting set carries only ~1.9 of 5 independent axes; pitching ~3.3 of 5. Pitching is the more multi-dimensional side, so balanced pitching construction has more leverage than chasing the collapsed batting bundle.

## Proposed Metrics - Balancing Batting & Pitching Independence

**Problem.** The two sides are lopsided in internal redundancy. Today the batting categories carry only ~1.9 effective independent axes (R/HR/RBI are one tied bundle, max tied-cluster = 3), while pitching carries ~3.3 (only ERA/WHIP tied, max cluster = 2). Two scenarios below rebalance them. Search population: same pooled 2023-2026 qualified players; candidate categories restricted to realistic, trackable stats.

### Balance scorecard

| Structure | Batting cats | Bat eff-axes | Bat max-tie | Pitching cats | Pit eff-axes | Pit max-tie | Balance gap |
|---|---|---|---|---|---|---|---|
| **Current** | R, HR, RBI, SB, OPS | 1.88 | 3 | K/9, QS, SVHD, ERA, WHIP | 3.30 | 2 | 1.41 |
| **A: Mirror** | R, HR, RBI, SB, OPS _(unchanged)_ | 1.88 | 3 | ERA, WHIP, BB/9, K/BB, H/9 | 2.13 | 3 | 0.25 |
| **B: Max-independence** | SB, SLG, AVG, BB, SO | 2.70 | 2 | K, WHIP, W, K/BB, H/9 | 2.70 | 2 | 0.00 |
| **C: 6x6 add-one** | R, HR, RBI, SB, OPS, AVG | 2.13 | 3 | K/9, QS, SVHD, ERA, WHIP, H/9 | 3.07 | 3 | 0.95 |

### Scenario A - Mirror (smallest change, most adoptable)

Batting is left **unchanged** - it already has the 3-category tied bundle (**R / HR / RBI (min pairwise |r| 0.86)**) plus two looser categories. We swap the pitching side so it carries a *parallel* run-prevention tied trio, mirroring the same shape.

- **Proposed pitching categories:** ERA, WHIP, BB/9, K/BB, H/9 (retains 2 of the current 5).
- **Pitching tied trio:** ERA / WHIP / H/9 (min pairwise |r| 0.76) - the mirror of batting's R/HR/RBI bundle.
- **Effective axes:** batting 1.88 vs pitching 2.13 (gap 0.25; current gap 1.41).
- **Other candidate pitching sets (next best mirrors):**
  - ERA, WHIP, K/BB, HR/9, H/9 - eff-axes 2.18, tied trio ERA / WHIP / H/9 (min pairwise |r| 0.76)
  - SVHD, ERA, WHIP, HR/9, H/9 - eff-axes 2.24, tied trio ERA / WHIP / H/9 (min pairwise |r| 0.76)
  - ERA, WHIP, BB/9, HR/9, H/9 - eff-axes 2.24, tied trio ERA / WHIP / H/9 (min pairwise |r| 0.76)

*Note:* pitching stats are inherently more independent than hitting stats, so the tightest pitching trio is a touch looser than R/HR/RBI; it is built from the run-prevention family (ERA / WHIP / hit- or walk-rate), which genuinely move together.

### Scenario B - Max independence (broadens desirable player types)

Built from scratch to maximize - and equalize - the number of distinct skills scored, so value spreads across many player profiles instead of concentrating in a few must-own players.

**Key structural fact:** hitting stats are inherently more correlated than pitching stats (everything rides the same playing-time + lineup-quality halo). The most independent five *batting* categories top out at only ~2.70 effective axes, whereas five pitching categories can reach ~4.64 (K, SV, HLD, BB/9, HR/9). Batting is therefore the binding side: to truly *equalize* the two, we take batting's most independent set and cap pitching at the same ceiling (rather than letting pitching run away and re-open the gap).

- **Proposed batting categories:** SB (speed); SLG (power / extra-base); AVG (contact / batting average); BB (plate discipline (walks)); SO (contact (avoiding strikeouts))
  - effective axes 2.70 of 5; max tied-cluster 2; mean |r| 0.42. (Nearly doubles batting independence vs the current 1.88.)
- **Proposed pitching categories (capped to match):** K (strikeout volume); WHIP (baserunner prevention); W (wins (team + durability)); K/BB (command); H/9 (hit prevention)
  - effective axes 2.70 of 5; max tied-cluster 2; mean |r| 0.39.
- **Balance:** effective-axis gap **0.00** (vs current 1.41) - the two sides are now near-identical in internal independence.
- **Familiar variant (keep HR):** the statistically optimal batting set drops HR/RBI because they are redundant with SLG/AVG/SB. The most independent batting set that still includes HR is **HR, SB, OBP, AVG, SO**, which costs essentially no independence (effective axes 2.70 vs 2.70), so it is the **recommended** Scenario B batting set - equally balanced but far more recognizable to the league.
- **Why it broadens the pool:** each category rewards a different skill, so speedsters, on-base specialists, contact hitters and power bats all hold standalone value (and starters, closers/setup arms, control artists and strikeout arms on the pitching side). No single archetype sweeps multiple categories, so a manager who misses the early run on power bats can still build a competitive roster through other categories.

### Scenario C - Keep 5x5, add one category to each (-> 6x6)

Leaves all ten current categories in place and adds a single new category per side - the least disruptive way to move the two sides toward each other. The batting addition is chosen to be the most *independent* of the existing five (raising batting's effective axes = bringing its internal relationship **down**); the pitching addition is chosen to be the most *redundant* with the existing five (lowering pitching's effective axes = bringing its internal relationship **up**).

- **Add to batting: `AVG`** (contact / batting average). Batting effective axes 1.88 -> **2.13** of 6 - it is the least-entangled recognizable hitting stat. *Limitation:* the gain is modest because every hitting category still shares the same playing-time + lineup-quality halo, so one addition narrows the gap but cannot fully fix batting's redundancy (that needs Scenario B, which *removes* a redundant category).
  - Next-best independent batting additions: OBP (2.11), SLG (1.94), SO (1.89). (AVG and OBP are near-tied; OBP doubles as a discipline axis if preferred.)
- **Add to pitching: `H/9`** (hit prevention). Pitching effective axes 3.30 -> **3.07** of 6, and it forms a tied bundle (largest mutually-tied cluster grows to 3: ERA / WHIP / H/9 (min pairwise |r| 0.76)). It deliberately overlaps an existing ratio category, mirroring how batting's R/HR/RBI move together.
  - Next-best redundant pitching additions: HLD (3.45), K (3.47), IP (3.49).
- **Balance:** 6x6 effective-axis gap **0.95** (vs current 5x5 gap 1.41) - the two sides converge while every existing category is preserved.
- **Trade-off vs Scenario A/B:** this keeps the league maximally familiar (nothing removed) at the cost of an extra category per side. It does not de-redundantize as fully as B, but it is the easiest sell.

## Re-Scoring the Season - Outcome Impact of Each Scenario

*How the **11** completed, fully-covered matchup periods of 2026 (MP 1-11, through scoring period 85) would have played out under each proposed category structure.*

**Method.** Each team's category totals are rebuilt from **active-lineup** player-days only (bench and IL slots excluded), summed per matchup period, with rate stats (OPS, ERA, WHIP, K/9, ...) recomputed from components. The league is **Head-to-Head Each Category**, so the primary record is the per-category W-L-T; the matchup-level result (most categories) is shown as a secondary view. Scenario B uses the most-independent category sets; C is the 6x6 add-one (12 categories, so its category totals are larger).

**Pipeline validation:** recomputed *current-scoring* matchup winners match ESPN's actual result on **52/55** decided matchups (95%) - the residual gap is daily-lineup reconstruction noise (mid-week roster moves, partial IL days).

### Category record deltas vs current (W-L-T, sorted by current win%)

| Team | Current W-L-T | A: Mirror (Δ) | B: Independent (Δ) | C: 6x6 (Δ) |
|---|---|---|---|---|
| Skubal Snacks | 60-43-7 | 65-42-3 (+5/-1/-4) | 56-42-12 (-4/-1/+5) | 72-53-7 (+12/+10/+0) |
| This Schlitt is Bazzanas | 58-51-1 | 57-53-0 (-1/+2/-1) | 57-38-15 (-1/-13/+14) | 74-57-1 (+16/+6/+0) |
| Datalickmyballs | 57-50-3 | 61-48-1 (+4/-2/-2) | 48-51-11 (-9/+1/+8) | 64-65-3 (+7/+15/+0) |
| Midnight Muncy's | 56-49-5 | 63-45-2 (+7/-4/-3) | 55-41-14 (-1/-8/+9) | 67-60-5 (+11/+11/+0) |
| Dingers Only | 56-50-4 | 59-48-3 (+3/-2/-1) | 52-43-15 (-4/-7/+11) | 67-61-4 (+11/+11/+0) |
| Rock and Aroldis | 52-52-6 | 54-53-3 (+2/+1/-3) | 44-52-14 (-8/+0/+8) | 63-63-6 (+11/+11/+0) |
| Welcome to the JUNGle | 52-53-5 | 52-55-3 (+0/+2/-2) | 44-50-16 (-8/-3/+11) | 64-63-5 (+12/+10/+0) |
| All Rise | 46-55-9 | 40-66-4 (-6/+11/-5) | 45-51-14 (-1/-4/+5) | 55-68-9 (+9/+13/+0) |
| Shohei Me the Money | 46-58-6 | 39-68-3 (-7/+10/-3) | 38-59-13 (-8/+1/+7) | 58-68-6 (+12/+10/+0) |
| Big Dumpers | 40-62-8 | 47-59-4 (+7/-3/-4) | 43-55-12 (+3/-7/+4) | 49-75-8 (+9/+13/+0) |

**Biggest category win% movers:** **A** -> up: Midnight Muncy's (+6% win), down: Shohei Me the Money (-6% win); **B** -> up: Big Dumpers (+3% win), down: Datalickmyballs (-8% win); **C** -> up: This Schlitt is Bazzanas (+3% win), down: Datalickmyballs (-3% win).

Matchup-level view (each matchup decided by most categories; ties at 5-5 / 6-6):

### Matchup record deltas vs current (W-L-T, sorted by current win%)

| Team | Current W-L-T | A: Mirror (Δ) | B: Independent (Δ) | C: 6x6 (Δ) |
|---|---|---|---|---|
| This Schlitt is Bazzanas | 7-4-0 | 6-4-1 (-1/+0/+1) | 8-3-0 (+1/-1/+0) | 7-3-1 (+0/-1/+1) |
| Midnight Muncy's | 6-5-0 | 6-4-1 (+0/-1/+1) | 7-3-1 (+1/-2/+1) | 6-4-1 (+0/-1/+1) |
| Skubal Snacks | 6-3-2 | 8-3-0 (+2/+0/-2) | 7-4-0 (+1/+1/-2) | 7-3-1 (+1/+0/-1) |
| Dingers Only | 6-5-0 | 6-4-1 (+0/-1/+1) | 7-4-0 (+1/-1/+0) | 6-5-0 (+0/+0/+0) |
| Datalickmyballs | 5-5-1 | 7-3-1 (+2/-2/+0) | 5-6-0 (+0/+1/-1) | 4-6-1 (-1/+1/+0) |
| Rock and Aroldis | 5-6-0 | 4-7-0 (-1/+1/+0) | 2-9-0 (-3/+3/+0) | 5-5-1 (+0/-1/+1) |
| Welcome to the JUNGle | 5-4-2 | 4-5-2 (-1/+1/+0) | 5-6-0 (+0/+2/-2) | 5-4-2 (+0/+0/+0) |
| Shohei Me the Money | 5-6-0 | 3-8-0 (-2/+2/+0) | 5-6-0 (+0/+0/+0) | 5-6-0 (+0/+0/+0) |
| All Rise | 4-6-1 | 1-8-2 (-3/+2/+1) | 4-6-1 (+0/+0/+0) | 4-7-0 (+0/+1/-1) |
| Big Dumpers | 2-7-2 | 6-5-0 (+4/-2/-2) | 4-7-0 (+2/+0/-2) | 2-8-1 (+0/+1/-1) |

**Matchup outcomes that flip vs current scoring:** A 14/55, B 13/55, C 5/55.

*Reading the deltas:* a positive ΔW with negative ΔL means that team fares **better** under the proposed structure - typically teams whose strength is in the categories the proposal de-emphasizes (the redundant power bundle) lose ground, while teams built on the now-distinct categories (speed, ratios, saves/holds, on-base) gain.

## Answers to the Six Questions

1. **Redundant categories:** R<->RBI (0.92), HR<->RBI (0.92), R<->HR (0.86), ERA<->WHIP (0.79).
2. **Independent / scarce differentiators:** pitching -> K/9, QS, SVHD; batting -> **SB** (most independent, mean |r| 0.37) is the lever, though it sits just above the strict scarce threshold.
3. **Unscored signals:** see the full correlation CSVs - OBP/BB% (batting) and BB/9, K/BB (pitching) carry independent information beyond the scored categories; OPS already absorbs most OBP value.
4. **Near-redundant scored categories:** any pair listed in Q1 is low-leverage to chase separately (notably the R/HR/RBI bundle and ERA/WHIP).
5. **Archetypes:** batters -> Contact Bat, Free-Swinger Bat, Power Bat, Speed Contact Bat; pitchers -> Reliever Ratio-Anchor (SV/HD), Starter, Swingman Volatile. Team concentration tables above.
6. **Market mis-valuation:** ownership-by-archetype table in section 6 flags which profiles are cheap relative to their category contribution.
