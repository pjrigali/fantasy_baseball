# Best Waiver Pickups — 2026 ESPN Fantasy Baseball
*Generated: 2026-06-18 | Source: analyze_best_pickups_espn_2026.py*

Rankings are based on post-add categorical contribution, not total season value. Each player's stat window is scoped strictly to the period(s) when they were on that specific fantasy team's roster — the window opens on the acquisition date and closes the day before any subsequent re-add (preventing overlapping windows), then each stint's stats are combined into a single row. The **Held** column shows `MM/DD–MM/DD` date ranges, with a comma separating separate stints where the player was dropped and re-added.

Z-scores are computed within each player type (batters vs. pitchers) across all 256 unique player-team entries this season, so a composite z of +5.0 means that entry ranked five standard deviations above the average pickup.

**Methodology:**
- **Active stats** — rows where `lineup_slot` is not BE or IL and the player's MLB game was played (AB > 0 for batters, OUTS > 0 for pitchers)
- **Rate stats** — ERA, WHIP, K/9 computed from aggregated totals across all stints (not per-game or per-stint averages); OPS weighted by AB
- **Composite z** — sum of five per-category z-scores: batters (R, HR, RBI, SB, OPS), pitchers (QS, SVHD, K/9, −ERA, −WHIP)
- **Utilization rate** — active games / (active + benched games) across all stints combined; 1.00 = never benched when healthy
- **Multiple stints** — denoted with `(N stints)` in the player name column; date ranges shown as `MM/DD–MM/DD, MM/DD–MM/DD`

---

## Top 15 Batter Pickups

| # | Player | Team | Held | Days | Util% | G_act | G_bnch | R | HR | RBI | SB | OPS | Z |
|---|--------|------|------|------|-------|-------|--------|---|----|-----|----|-----|---|
| 1 | Jordan Walker | Midnight Muncy's | 03/30–06/16 | 78 | 0.984 | 61 | 1 | 38 | 15 | 46 | 10 | .862 | **19.84** |
| 2 | Miguel Vargas | Midnight Muncy's | 03/30–06/16 | 78 | 1.000 | 63 | 0 | 47 | 15 | 38 | 9 | .834 | **19.39** |
| 3 | Liam Hicks | All Rise | 04/02–06/16 | 75 | 1.000 | 63 | 0 | 31 | 10 | 39 | 1 | .756 | **11.11** |
| 4 | Bryson Stott | Midnight Muncy's | 03/23–05/31 | 69 | 0.980 | 50 | 1 | 15 | 5 | 25 | 10 | .647 | **10.20** |
| 5 | Brandon Marsh | Datalickmyballs | 04/15–06/16 | 62 | 0.958 | 46 | 2 | 28 | 6 | 21 | 4 | .887 | **9.12** |
| 6 | Wilyer Abreu | Dingers Only | 03/26–06/16 | 82 | 0.894 | 59 | 7 | 25 | 5 | 28 | 3 | .706 | **8.16** |
| 7 | Casey Schmitt | Welcome to the JUNGle | 05/05–06/16 | 42 | 0.882 | 30 | 4 | 16 | 8 | 19 | 4 | .702 | **7.62** |
| 8 | Zack Gelof | All Rise | 05/09–06/16 | 38 | 0.970 | 32 | 1 | 19 | 6 | 15 | 5 | .777 | **7.53** |
| 9 | Luke Raley | Datalickmyballs | 04/15–06/16 | 62 | 0.891 | 41 | 5 | 15 | 9 | 21 | 1 | .723 | **6.53** |
| 10 | Ivan Herrera | This Schlitt is Bazzanas | 04/27–06/16 | 50 | 0.900 | 36 | 4 | 27 | 4 | 13 | 3 | .766 | **6.43** |
| 11 | Dillon Dingler | This Schlitt is Bazzanas | 04/04–06/16 | 73 | 0.868 | 33 | 5 | 17 | 8 | 23 | 0 | .838 | **6.43** |
| 12 | Mickey Moniak | Skubal Snacks | 04/12–06/16 | 65 | 0.909 | 30 | 3 | 15 | 7 | 19 | 1 | .931 | **6.14** |
| 13 | Sam Antonacci *(2 stints)* | All Rise | 04/15–04/25, 05/06–06/16 | 44 | 0.861 | 31 | 5 | 20 | 0 | 7 | 7 | .666 | **5.27** |
| 14 | Mauricio Dubon | Big Dumpers | 04/29–06/16 | 48 | 1.000 | 37 | 0 | 13 | 4 | 23 | 1 | .688 | **4.57** |
| 15 | Nolan Arenado | Big Dumpers | 04/29–06/16 | 48 | 1.000 | 38 | 0 | 15 | 3 | 14 | 3 | .658 | **4.39** |

### Batter Notes

**Jordan Walker (Midnight Muncy's, Z = 19.84)** is the runaway winner — a full five-category contributor with 38R/15HR/46RBI/10SB and an .862 OPS across 61 active games from March 30 through the end of the data window. Started in all but one available game.

**Miguel Vargas (#2, Z = 19.39)** nearly matches him: 47R/15HR/38RBI/9SB at .834 OPS in 63 games, started every single game Midnight Muncy's owned him. Midnight Muncy's finding both players gives them the two best batter pickups in the league this year.

**Bryson Stott (#4, Z = 10.20)** held from March 23 to May 31 — notably, one of the few top-10 entries without a season-long hold. His 10 SB in that window ranks among the highest of any batter pickup, and SB scarcity in H2H leagues amplifies its z-score weight considerably.

**Sam Antonacci (#13, 2 stints)** was dropped April 25, then re-added May 6. The combined window (44 total days held) counts stats from both stretches — April 15–25 and May 6–June 16. His 7 SB show up in both stints, making the multi-stint entry more representative than either single row was on its own.

---

## Top 15 Pitcher Pickups

| # | Player | Team | Held | Days | Util% | G_act | G_bnch | QS | SVHD | K/9 | ERA | WHIP | Z |
|---|--------|------|------|------|-------|-------|--------|----|----|-----|-----|------|---|
| 1 | Erik Sabrowski | This Schlitt is Bazzanas | 04/01–06/16 | 76 | 1.000 | 11 | 0 | 0 | 7 | 20.52 | 0.000 | 1.080 | **4.52** |
| 2 | Paul Sewald *(2 stints)* | All Rise | 04/05–04/12, 04/13–06/16 | 71 | 1.000 | 24 | 0 | 0 | 15 | 9.27 | 3.224 | 0.761 | **4.37** |
| 3 | Emerson Hancock | Midnight Muncy's | 03/30–06/16 | 78 | 1.000 | 13 | 0 | 7 | 0 | 8.06 | 3.543 | 1.086 | **4.35** |
| 4 | Gregory Soto | Shohei Me the Money | 04/07–06/16 | 70 | 1.000 | 23 | 0 | 0 | 14 | 9.00 | 1.957 | 0.739 | **4.11** |
| 5 | Bryan Baker | Welcome to the JUNGle | 04/28–06/16 | 49 | 1.000 | 18 | 0 | 0 | 12 | 10.06 | 1.059 | 0.882 | **3.72** |
| 6 | Tanner Scott | Skubal Snacks | 04/10–06/16 | 67 | 1.000 | 25 | 0 | 0 | 11 | 10.12 | 2.625 | 0.750 | **3.40** |
| 7 | Louis Varland | Welcome to the JUNGle | 04/15–06/16 | 62 | 1.000 | 20 | 0 | 0 | 11 | 10.32 | 1.588 | 0.971 | **3.39** |
| 8 | Ian Seymour *(2 stints)* | Midnight Muncy's | 03/23–03/29, 03/30–06/16 | 76 | 1.000 | 25 | 0 | 0 | 12 | 9.58 | 3.774 | 1.194 | **3.25** |
| 9 | Payton Tolle | Skubal Snacks | 04/21–06/16 | 56 | 1.000 | 9 | 0 | 5 | 0 | 9.11 | 3.038 | 1.069 | **3.21** |
| 10 | Kyle Harrison | Skubal Snacks | 04/29–06/16 | 48 | 0.875 | 7 | 1 | 4 | 0 | 10.42 | 2.368 | 1.026 | **2.87** |
| 11 | Braxton Ashcraft | Dingers Only | 03/25–06/16 | 83 | 0.571 | 8 | 6 | 4 | 0 | 10.73 | 3.884 | 1.089 | **2.79** |
| 12 | Michael Wacha | All Rise | 04/21–06/16 | 56 | 0.778 | 7 | 2 | 5 | 0 | 7.68 | 3.738 | 1.177 | **2.78** |
| 13 | Davis Martin | Dingers Only | 04/28–06/16 | 49 | 1.000 | 7 | 0 | 4 | 0 | 10.32 | 3.073 | 1.171 | **2.71** |
| 14 | Trevor Megill | Shohei Me the Money | 05/11–06/16 | 36 | 1.000 | 10 | 0 | 0 | 6 | 14.40 | 2.700 | 1.000 | **2.71** |
| 15 | Dylan Lee | This Schlitt is Bazzanas | 05/25–06/16 | 22 | 1.000 | 7 | 0 | 0 | 6 | 12.86 | 1.286 | 0.714 | **2.63** |

### Pitcher Notes

**Erik Sabrowski (This Schlitt is Bazzanas, Z = 4.52)** leads all pitchers with the best strikeout rate of any pickup stint this season: a **20.52 K/9** across 11 appearances and a **0.000 ERA** in his ownership window. The K/9 alone pushes him more than three standard deviations above the mean for relief pickups. Started in every available game.

**Paul Sewald (#2, 2 stints)** was dropped by All Rise on April 12, then re-added the very next day. The combined row correctly isolates April 5–12 as one stint and April 13 onward as the second, preventing any stat overlap. Summed across both stints: 15 SVHD, 9.27 K/9, 3.224 ERA, 0.761 WHIP — and started in every single appearance across both windows (1.000 utilization).

**Ian Seymour (#8, 2 stints, Midnight Muncy's)** has two stints that span March 23–29 and March 30 onward — effectively consecutive days, suggesting a very brief drop-and-re-add around the season's opening week. The combined stats (25 games active, 12 SVHD, 9.58 K/9) represent his full contribution to Midnight Muncy's.

**Pitchers are almost never benched.** Twelve of the top 15 pitcher entries have 1.000 utilization. The two exceptions — Braxton Ashcraft (0.571) and Michael Wacha (0.778) — are the only managers who routinely left a started arm on the bench during ownership.

---

## Per-Team Leaderboard

*Sorted by best single pickup composite z. Avg utilization is the mean across all unique player-team pickups for that team. Lower signals a team that is bad at deploying its own waiver claims. Unique Pickups is the number of distinct player-team combinations after collapsing multi-stint adds.*

| Team | Unique Pickups | Best Pickup | Type | Best Z | Avg Util% |
|------|----------------|-------------|------|--------|-----------|
| Midnight Muncy's | 19 | Jordan Walker | batter | 19.843 | 0.925 |
| All Rise | 26 | Liam Hicks | batter | 11.109 | 0.854 |
| Datalickmyballs | 15 | Brandon Marsh | batter | 9.125 | 0.719 |
| Dingers Only | 47 | Wilyer Abreu | batter | 8.160 | 0.624 |
| Welcome to the JUNGle | 17 | Casey Schmitt | batter | 7.620 | 0.943 |
| This Schlitt is Bazzanas | 26 | Ivan Herrera | batter | 6.431 | 0.815 |
| Skubal Snacks | 42 | Mickey Moniak | batter | 6.139 | 0.658 |
| Big Dumpers | 11 | Mauricio Dubon | batter | 4.572 | 0.838 |
| Rock and Aroldis | 19 | JJ Bleday | batter | 4.181 | 0.622 |
| Shohei Me the Money | 8 | Gregory Soto | pitcher | 4.106 | 0.643 |
| Big Papi | 26 | Max Muncy | batter | 3.648 | 0.755 |

### Team Notes

**Midnight Muncy's** wins the pickup game outright. They found the two best batter pickups in the league (Walker and Vargas), made only 19 unique adds, and deployed their claims at a 0.925 average utilization rate. High-quality, low-volume, high-utilization.

**Welcome to the JUNGle** is the hidden gem: 17 unique adds (second-fewest), the **highest average utilization in the league at 0.943**, and their best pickup (Casey Schmitt) ranks 7th overall. They make few moves but start almost everything they pick up.

**Dingers Only** is the clearest cautionary tale: 47 unique player-team adds (most in the league, 2.5× Midnight Muncy's) paired with 0.624 average utilization — second-worst in the league. They are churning through the waiver wire but not starting what they pick up.

**Skubal Snacks** (42 unique adds, 0.658 avg utilization — worst among active teams) has the same problem in an even more extreme form on utilization. High add volume, worst deployment rate of any team with meaningful waiver activity.

**Rock and Aroldis** (0.622 avg utilization) is the third-worst deployer. Given their 19 unique adds, they're leaving production on the bench consistently.

---

## Wasted Pickups

*Players with composite z > 0 (above-average production when active) but utilization rate < 0.50 (benched more than half their available games).*

| Player | Team | Type | Held | Util% | G_act | G_bnch | Z |
|--------|------|------|------|-------|-------|--------|---|
| Clay Holmes | Dingers Only | pitcher | 05/02–05/16 | 0.333 | 1 | 2 | 0.272 |

Only one entry meets both criteria: **Clay Holmes (Dingers Only)**, held from May 2–16, started in 1 of 3 available games, and produced above-average results when he did pitch. Consistent with Dingers Only's pattern of picking up relievers and then not committing to starting them (0.624 team average utilization, second-worst in the league).

The near-absence of wasted pickups is a positive league-wide signal — when managers bother to add a player, they generally start them in the majority of their available games. The real cost of poor utilization shows up in team-level averages.

---

## Worst Drops

*Players released by a fantasy team who went on to contribute meaningfully elsewhere. Post-drop stats cover every day after the drop date on any team **except** the dropping team. Z-scores are computed separately from the pickups pool (300 total drop events, 91 with usable post-drop data). Each drop event is its own entry — if the same player was dropped by multiple teams, each appears separately.*

### Worst Batter Drops

| # | Player | Dropped By | Picked Up By | Drop Date | Days After | R | HR | RBI | SB | OPS | Z |
|---|--------|-----------|-------------|-----------|-----------|---|----|-----|-----|-----|---|
| 1 | Miguel Vargas | Big Papi | Midnight Muncy's | 03/29 | 79 | 47 | 15 | 38 | 9 | .834 | **17.45** |
| 2 | Max Muncy | Dingers Only | Big Papi, Rock and Aroldis | 04/05 | 72 | 29 | 10 | 20 | 0 | .896 | **6.88** |
| 3 | Wilyer Abreu | This Schlitt is Bazzanas | Dingers Only | 03/26 | 82 | 25 | 5 | 28 | 3 | .706 | **6.76** |
| 4 | Casey Schmitt | Skubal Snacks | Welcome to the JUNGle | 04/28 | 49 | 16 | 8 | 19 | 4 | .702 | **6.27** |
| 5 | Mickey Moniak | This Schlitt is Bazzanas | Skubal Snacks | 03/23 | 85 | 15 | 7 | 19 | 1 | .931 | **4.89** |
| 6 | Nolan Arenado | This Schlitt is Bazzanas | Skubal Snacks, Big Dumpers | 04/23 | 54 | 16 | 3 | 14 | 3 | .669 | **3.38** |
| 7 | Nolan Arenado | Welcome to the JUNGle | Long Bohms Away, Skubal Snacks, … | 03/30 | 78 | 16 | 3 | 14 | 3 | .669 | **3.38** |
| 8 | Mauricio Dubon | This Schlitt is Bazzanas | Big Dumpers | 04/27 | 50 | 13 | 4 | 23 | 1 | .688 | **3.34** |
| 9 | Nolan Arenado | Skubal Snacks | Big Dumpers | 04/25 | 52 | 15 | 3 | 14 | 3 | .658 | **3.23** |
| 10 | Daulton Varsho | Skubal Snacks | Datalickmyballs | 04/21 | 56 | 17 | 2 | 10 | 3 | .754 | **2.98** |

### Worst Pitcher Drops

| # | Player | Dropped By | Picked Up By | Drop Date | Days After | QS | SVHD | K/9 | ERA | WHIP | Z |
|---|--------|-----------|-------------|-----------|-----------|----|----|-----|-----|------|---|
| 1 | Bryan Baker | Skubal Snacks | Welcome to the JUNGle | 04/16 | 61 | 0 | 12 | 10.06 | 1.059 | 0.882 | **4.00** |
| 2 | Tanner Scott | This Schlitt is Bazzanas | Skubal Snacks | 04/01 | 76 | 0 | 11 | 10.36 | 2.959 | 0.781 | **3.69** |
| 3 | Bryce Elder | This Schlitt is Bazzanas | Skubal Snacks | 04/10 | 67 | 8 | 0 | 7.02 | 3.510 | 1.110 | **3.19** |
| 4 | Trevor Megill | Big Papi | Shohei Me the Money | 04/13 | 64 | 0 | 6 | 14.40 | 2.700 | 1.000 | **3.00** |
| 5 | Drew Rasmussen | Big Papi | This Schlitt is Bazzanas | 04/07 | 70 | 6 | 0 | 8.68 | 3.214 | 0.946 | **2.65** |
| 6 | Riley O'Brien | Welcome to the JUNGle | All Rise | 04/26 | 51 | 0 | 10 | 9.00 | 6.188 | 1.625 | **2.45** |
| 7 | Kyle Harrison | All Rise | Skubal Snacks | 04/11 | 66 | 4 | 0 | 10.42 | 2.368 | 1.026 | **2.05** |
| 8 | Michael Wacha | Big Papi | All Rise | 04/02 | 75 | 5 | 0 | 7.68 | 3.738 | 1.177 | **1.72** |
| 9 | Juan Morillo | This Schlitt is Bazzanas | Dingers Only, Midnight Muncy's | 04/15 | 62 | 0 | 2 | 13.50 | 2.596 | 1.038 | **1.40** |
| 10 | Michael Soroka | Dingers Only | Rock and Aroldis | 04/25 | 52 | 4 | 0 | 6.75 | 2.531 | 0.688 | **1.21** |

### Drop Notes

**Miguel Vargas (Big Papi → Midnight Muncy's, Z = 17.45) is the single costliest drop of the season.** Big Papi released him on March 29 — the second day of the season — and Midnight Muncy's immediately claimed him. Vargas went on to post 47R/15HR/38RBI/9SB at an .834 OPS across 63 active games, making him the #2 batter pickup in the league. Big Papi's season-opening miscalculation directly handed Midnight Muncy's one of their two star acquisitions.

**Nolan Arenado appears three separate times** because three teams dropped him in quick succession — Welcome to the JUNGle (03/30), This Schlitt is Bazzanas (04/23), and Skubal Snacks (04/25) — before Big Dumpers claimed and held him from April 29 onward. Welcome to the JUNGle's drop was particularly deep in the waiver chain: Arenado passed through Long Bohms Away and Skubal Snacks before landing at Big Dumpers. The post-drop production is the same underlying stat line in each row (Big Dumpers' ownership), with slightly varying Days After depending on when each team let him go.

**Bryan Baker (#1 worst pitcher drop, Skubal Snacks → Welcome to the JUNGle, Z = 4.00):** Skubal Snacks dropped Baker on April 16 and Welcome to the JUNGle picked him up April 28. Baker delivered 12 SVHD, a 1.059 ERA, and 0.882 WHIP across 18 appearances — ranking #5 among all pitcher pickups leaguewide. Baker appears in both the worst-drops list (as a Skubal Snacks mistake) and the best-pickups list (as a Welcome to the JUNGle win), illustrating exactly how one team's waiver discard becomes another's gain.

**Tanner Scott (#2, This Schlitt is Bazzanas → Skubal Snacks, Z = 3.69):** Dropped April 1, claimed by Skubal Snacks April 10. Scott became Skubal Snacks' 6th-best pickup (Z=3.40). This Schlitt is Bazzanas also dropped Bryce Elder (#3 pitcher drop) and Drew Rasmussen went to them after Big Papi's drop — the data reveals they were simultaneously shedding valuable arms and picking up others.

**This Schlitt is Bazzanas** has the heaviest overall drop footprint: Wilyer Abreu (#3 batter, to Dingers Only), Mickey Moniak (#5, to Skubal Snacks), Nolan Arenado (#6), Mauricio Dubon (#8), Tanner Scott (#2 pitcher), Bryce Elder (#3 pitcher), Juan Morillo (#9 pitcher). Despite ranking 6th in the pickups leaderboard, they were simultaneously rotating some of the most productive waiver players in the league out the door.

**Big Papi** dropped four players who contributed meaningfully elsewhere: Miguel Vargas (→ Midnight Muncy's, #1 worst drop), Trevor Megill (→ Shohei Me the Money, #4 pitcher), Drew Rasmussen (→ This Schlitt is Bazzanas, #5 pitcher), and Michael Wacha (→ All Rise, #8 pitcher). Their early-season roster churn cost them more in combined post-drop production than any other team.

---

*Full data: `data-lake/01_Bronze/fantasy_baseball/best_pickups_espn_2026.csv` (256 rows — one per unique player-team combination, with multi-stint stats combined, held_ranges, z-scores, and utilization fields)*
