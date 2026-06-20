# Fantasy Baseball — Ideas & Things to Investigate

> **Maintenance note:** When a new idea is added here, update the **Future Analysis** table in [`README.md`](README.md) with the idea number, name, one-sentence description, and status.

---

## Status Categories

| Status | Meaning |
|--------|---------|
| `Not Started` | Idea captured, no work begun |
| `In Progress` | Actively being built or investigated |
| `Complete` | Analysis finished and documented |
| `On Hold` | Paused — blocked or deprioritized |
| `Abandoned` | Decided not to pursue |

---

## 1. Roster Play-Time Density vs Box Score Performance

**Status:** `Not Started`

**Observation:** On a given day, only ~420 MLB players appear in game logs out of the ~1,100 tracked (509 hitters + 597 pitchers). That means roughly 60% of rostered players are idle on any given day.

**Idea:** For each fantasy league team, measure what percentage of their rostered players actually appeared in a game log on a given day. Then correlate that "play-time density" against the team's daily/weekly box score (fantasy points scored).

**Questions to answer:**
- Which league teams consistently have the most active rosters day-to-day?
- Does higher daily participation rate predict higher fantasy scoring?
- Are there teams that score well despite low participation (i.e. relying on a few high-impact players) vs teams that need broad participation to compete?
- Is there a threshold participation rate below which a team almost never wins the week?

**Data sources:**
- `2026_mlb_stats_daily.csv` — who actually played each day (game logs)
- `2026_espn_stats_daily.csv` — which players are on which fantasy team, and their fantasy points
- `2026_mlb_lineups_batters.csv` — batting order data to cross-reference active players

**Possible output:** A daily participation rate per fantasy team (% of roster with a game log entry), plotted against fantasy points scored that day/week.

---

## 2. Gini Analysis — Box Score Concentration by Player and Team

**Status:** `Not Started`

**Observation:** Fantasy scoring is likely highly unequal — a small number of players probably account for a disproportionate share of total points scored across the league. A Gini coefficient (0 = perfectly equal, 1 = one player scores everything) quantifies that concentration.

**Idea:** Apply a Gini analysis at three levels:
1. **Player level** — across all rostered players, how concentrated is total fantasy scoring? Who are the top contributors driving the Lorenz curve?
2. **Team level** — within each fantasy team's roster, how dependent are they on a small number of players? A high intra-roster Gini means they live and die by 2–3 stars.
3. **League capture** — which fantasy team "owns" the highest-scoring players? Does one team disproportionately hold the value-dense tail of the distribution?

**Keeper angle:** The players sitting in the high-scoring tail of the Gini curve are the natural keeper candidates — they produce outsized value relative to replacement. Cross-reference against `2026_espn_activity_season.csv` to see how they were acquired (waiver, draft, trade) and whether they're likely to be retained.

**Questions to answer:**
- What is the league-wide Gini on cumulative season fantasy points?
- Which 10–15 players account for the top decile of scoring?
- Which team holds the most of those players, and how concentrated is their roster?
- Are the high-Gini players draftable keepers, or were they waiver pickups (suggesting volatility)?

**Data sources:**
- `2026_espn_stats_daily.csv` — daily fantasy points per player per team
- `2026_espn_activity_season.csv` — acquisition history (drafted vs waiver vs trade)
- `2026_espn_rankings_daily.csv` — ownership % and ADP as a proxy for perceived value

**Possible output:** Lorenz curve per team and league-wide; ranked list of "value-dense" players flagged as keeper candidates with their acquisition type.

---

## 3. Batting Order Position vs Batter Stats

**Status:** `Not Started`

**Context:** We now have two complementary datasets that haven't been joined before — `lineups_mlb_batters` gives us the exact batting order slot each player hit in on a given day, and `stats_mlb_daily` gives us their actual game-level output. Joining on `(date, player_name/team)` enables a clean batting-order analysis grounded in real per-game data rather than season aggregates.

**Idea:** Analyze how batting order position (1–9) relates to counting stats and fantasy-relevant production. Revisit any prior batting order analysis with this richer, date-aligned dataset.

**Questions to answer:**
- Which batting order slots produce the most fantasy value on average (R, HR, RBI, SB, TB)?
- Is the 2-hole or 3-hole consistently outperforming the cleanup spot in this era?
- Do certain stats (SB, R) correlate more tightly with top-of-order slots while power (HR, RBI) clusters in 3–5?
- How much does batting order slot vary game-to-game for the same player, and does slot volatility hurt their fantasy production?
- Which fantasy-rostered players are consistently hitting in high-value slots vs floating?

**Data sources:**
- `2026_mlb_lineups_batters.csv` — date, team, player, batting order slot
- `2026_mlb_stats_daily.csv` — per-game hitting stats (AB, R, H, HR, RBI, SB, TB, BB, SO)
- `2026_espn_stats_daily.csv` — fantasy points, to tie MLB output back to fantasy value

**Join key:** `(date, player_name)` or `(date, team_tricode + player_name)` — worth checking name formatting consistency across sources before joining.

**Possible output:** Per-slot stat averages and distributions (box plots); a "slot value index" ranking batting order positions by average fantasy contribution; player-level slot consistency scores.

---

## 4. Batter Consistency — Streakiness, Slumps, and the OBP Drag Problem

**Status:** `Not Started`

**Observation:** Some batters appear to go 0-for on multiple consecutive days then explode in a single game. When those games get averaged into a season OBP/OPS, the player looks respectable — but the underlying pattern is feast-or-famine, which is practically worse for daily/weekly fantasy scoring than the average suggests.

**Idea:** Measure per-game consistency for each batter and determine whether "good" players by season average are actually suppressing team-level rate stats (OBP, OPS) due to high variance in their day-to-day output. A player averaging .300 OBP via 3 great games and 7 hitless ones is not the same as a player consistently going 1-for-4 every game.

**Questions to answer:**
- What is each batter's game-level OBP standard deviation, and how does it correlate with their season average?
- Which players are "illusory" — strong season averages driven by outlier games masking frequent zero days?
- When a feast-or-famine batter is in a slump, does their drag on counting stats (0 AB contribution days) meaningfully hurt the fantasy team's weekly OBP?
- Is there a consistency threshold (e.g. hit-rate in at least X% of games) that separates reliable contributors from volatile ones?
- Do high-variance batters cluster at specific roster positions or batting order slots?

**Data sources:**
- `2026_mlb_stats_daily.csv` — per-game H, AB, BB, HBP, SF (to compute game-level OBP)
- `2026_espn_stats_daily.csv` — fantasy points and roster slot context
- `2026_mlb_lineups_batters.csv` — to control for games where player sat out vs played and went hitless

**Key metric:** Game-level OBP distribution per player (mean, std dev, % of games with OBP = 0, % of games above .400). A "consistency score" could be mean / std_dev — higher is more reliable.

**Possible output:** Player consistency rankings; scatter of season-avg OBP vs consistency score to surface the "illusory" quadrant; streakiness heatmap by player over the season calendar.

---

## 5. Box Score Stat Relationships — Correlation, Redundancy, and Category-System Audit

**Status:** `Complete` (2026-06-20)

> **Execution prompt:** [`ideas/idea_05_stat_relationships/PROMPT.md`](ideas/idea_05_stat_relationships/PROMPT.md)

**Deliverables:**
- `ideas/idea_05_stat_relationships/analyze_stat_relationships_espn_2026.py` — multi-year (2023–2026) correlation engine: Pearson/Spearman matrices, 5x5 category redundancy audit, hand-rolled PCA (numpy SVD) effective-dimensionality, and PCA+k-means archetype discovery (scipy; no sklearn in venv). MLB game logs are the single locked stat source; ESPN is overlay-only.
- `reports/stat_relationships_2026.md` — full write-up with per-season + pooled category tables, redundancy/scarcity flags, archetype cards, team-holdings + market-valuation overlays, and roster-construction takeaways. Heatmaps: `reports/stat_relationships_2026_{batter,pitcher}_corr.png`.
- Derived CSVs in Bronze: `2026_local_stat_correlations_{batter,pitcher}.csv`, `2026_local_category_corr_by_season_{batter,pitcher}.csv`, `2026_local_archetypes_{batter,pitcher}.csv`, `2026_local_proposed_scoring.csv`, `2026_local_rescore_results.csv`.
- **Season re-scoring** (report) — replays the 11 completed, fully-covered matchup periods (MP1–11, through SP85) under each scenario from **active-lineup** category totals, with per-team W-L-T deltas at both category and matchup level. Pipeline validated at **95%** (52/55) against ESPN's actual matchup winners. Matchup outcomes that flip vs current: **A 14/55, B 13/55, C 5/55** — C is the least disruptive, B/A reshuffle standings most (teams reliant on the redundant power bundle lose ground; speed/ratio/saves-built teams gain). Required fixing `generate_schedule_espn_matchup.py` to use ESPN's authoritative `pointsByScoringPeriod` day-membership (the old heuristic drifted and only validated at 53%).
- **Proposed Metrics** section (report) — rebalances the two sides so batting and pitching carry equal internal independence. **Scenario A (Mirror, minimal change):** keep batting as-is, swap pitching to `ERA, WHIP, BB/9, K/BB, H/9` (parallel run-prevention tied trio ERA/WHIP/H/9); balance gap 1.41 → 0.25. **Scenario B (from scratch, max breadth):** batting is the binding side (5 hitting cats top out ~2.7 effective axes vs pitching's ~4.6), so cap pitching at batting's ceiling — `SB, SLG, AVG, BB, SO` vs `K, WHIP, W, K/BB, H/9`, both 2.70 axes (gap 0.00). HR-inclusive variant `HR, SB, OBP, AVG, SO` is equally independent and recommended for adoptability. **Scenario C (keep 5x5, add one → 6x6):** add the most-independent batting category (**AVG**, raises batting 1.88 → 2.13) and the most-redundant pitching category (**H/9**, lowers pitching 3.30 → 3.07 and forms an ERA/WHIP/H/9 tied trio mirroring R/HR/RBI); gap 1.41 → 0.95. Least disruptive (nothing removed) but only partial — batting's halo limits how far one addition can de-redundantize it.

**Key findings (2026, stable across 2023–2026):**
- *Batting redundancy:* **R/HR/RBI are effectively one category** (pairwise r 0.86–0.92, cross-season std ≤0.04). The five batting categories collapse to ~1.9 effective independent axes of 5.
- *Batting differentiator:* **SB** is the most independent batting category (mean |r| 0.37) — won deliberately, not "for free" with the power bundle.
- *Pitching:* **ERA↔WHIP** are redundant (r=0.79); **K/9, QS, SVHD are three independent levers** (≈3.3 effective axes of 5) won by roster construction, not ace quality.
- *Archetypes:* batters → Power / Speed-Contact / Contact / Free-Swinger; pitchers → Reliever (SV/HD) / Starter / Swingman-Volatile. Market overlay flags Speed-Contact bats as underowned (~28%) relative to Power (~52%) despite SB being the batting differentiator.

**Scoring context (important):** This is a **Head-to-Head 5x5 Categories** league (see [`scoring.md`](scoring.md)), **not** a points league — there are no per-stat point weights to audit, and the `points` column in `2026_espn_stats_daily.csv` is `0.0` everywhere. The five batting categories are **R, HR, RBI, SB, OPS**; the five pitching categories are **K/9, QS, SVHD, ERA, WHIP**. Each category is won or lost independently per matchup week. The "audit" therefore asks how many *effectively independent* axes the 10 categories represent, not what their point weights should be.

**Observation:** The scoring categories are not independent. HR drives RBI and R simultaneously, so a roster built to win one of those tends to win all three "for free" — meaning the five batting categories are not five independent levers. On pitching, ERA and WHIP move together. Understanding the correlation structure exposes which categories are redundant (low-leverage, ride along with others), which are the scarce/orthogonal differentiators (likely SB and SVHD) where matchups are actually decided, and which player archetypes dominate each.

**Idea:** Build a full correlation matrix across all box score stats for both batters and pitchers, audit the redundancy/independence structure of the 10 scoring categories in **categories terms** (no invented point weights), and identify the player archetypes that emerge from the stat clusters — then translate the findings into concrete roster-construction guidance for this category set.

**Questions to answer:**
- Which scoring categories are highly correlated (e.g. HR↔RBI↔R, ERA↔WHIP) and therefore effectively redundant — winning one tends to win the others?
- Which scoring categories are independent/scarce (likely SB, SVHD) and are therefore the true differentiators to build around or contest?
- Are there unscored stats (e.g. BB/OBP-only value, holds vs saves split) that carry strong independent signal the category set fails to capture?
- Is any scored category nearly redundant with another, making it low-leverage / streamable?
- What player archetypes emerge when clustering by stat profile — speedsters, power bats, contact/OBP hitters, strikeout pitchers, ground-ball pitchers, high-leverage relievers — and which fantasy teams hold which archetypes?
- Which archetypes does the market (ownership/ADP) over- or under-value relative to their actual contribution to this league's categories?

**Data sources (multi-year):** MLB daily game logs go back to **2023**, so the correlation/redundancy/archetype analysis should be run across **2023–2026** to confirm the structure is stable year over year, not a single-season artifact. League/roster/market context only exists for 2025–2026, so team-holdings and market overlays are limited to those seasons.
- `2023_mlb_stats_daily.csv`, `2024_mlb_stats_daily.csv`, `2025_mlb_stats_daily.csv` — per-game stat vectors for batters and pitchers (shared schema using `b_or_p`, `playerName`). All 10 categories are derivable from these (OPS from OBP+SLG components; K/9, ERA, WHIP from OUTS).
- `2026_mlb_stats_boxscore.csv` / `2026_mlb_stats_daily_archive.csv` — 2026 game logs (same stat columns; identity columns renamed to `player_id`/`player_name`). Note: there is no `2026_mlb_stats_daily.csv` — these are its equivalents.
- `2026_espn_stats_daily.csv` (and `2025_espn_stats_daily.csv`) — full box-score vector already aligned to fantasy rosters/league context; `player_type` splits batter/pitcher. Provides team-holdings overlay.
- `2026_espn_rankings_daily.csv` — ownership and ADP as a market proxy for perceived value.

**Approach:**
- Harmonize the 2023–2026 MLB daily schemas; aggregate daily rows to per-player season totals, recomputing rate stats (OPS, ERA, WHIP, K/9) from summed components rather than averaging averages; apply minimum-sample filters.
- Pearson **and** Spearman correlation matrices across all numeric stat columns, split by batter/pitcher; report where they disagree (stat distributions are skewed).
- Isolate the 5x5 category correlation block; use PCA on the batting and pitching category sets to measure effective dimensionality and flag redundant pairs vs. orthogonal/scarce categories.
- PCA + k-means (silhouette/elbow for k) on standardized season-aggregated stat profiles to surface archetypes; profile centroids, name representative players, overlay team holdings and market valuation.
- Repeat the category correlation block per season (2023–2026) to confirm robustness.

**Possible output:** Correlation heatmaps (batters and pitchers separately, per season); a 5x5 category redundancy/independence table flagging redundant pairs and scarce differentiators; PCA effective-dimensionality summary; archetype cluster cards with representative players, team-holdings and market-valuation overlays; a plain-English roster-construction takeaways section for playing this categories league.

---

## 6. Waiver Wire Timing and Transaction ROI

**Status:** `Not Started`

**Motivation:** The activity data captures every add, drop, and trade with timestamps. Teams that are winning may be making smarter or better-timed roster moves — or the causality runs the other way. Either way, the data exists to measure it.

**Idea:** For every waiver add, compute the fantasy points that player scored in the 7 and 14 days following acquisition. Compare that against the points the dropped player scored over the same window. This gives a per-transaction ROI. Aggregate by team to see who is winning and losing the waiver wire.

**Questions to answer:**
- Which teams have the highest average post-add return on waiver claims?
- Do teams that add earlier in the week (Monday/Tuesday) outperform teams that react later?
- Which drops were mistakes — players dropped who then outscored their replacement?
- Is there a team consistently selling assets cheap (dropping players who bounce back)?

**Data sources:** `2026_espn_activity_season.csv`, `2026_espn_stats_daily.csv`

**Possible output:** Per-team transaction ROI leaderboard; list of the worst drops of the season by value left on the table.

---

## 7. Ownership Lag — Finding Market Inefficiencies Before ESPN Catches Up

**Status:** `Not Started`

**Motivation:** The `2026_espn_rankings_daily.csv` captures both `pct_owned` and `pct_change` (the trending signal) on a daily basis. A player breaking out will show strong game-log stats before the ownership % moves. The lag between performance and market reaction is the window to act.

**Idea:** For each player, compare their rolling 7-day `stats_mlb_daily` performance against their ownership trend in `rankings_espn_daily`. Identify players where performance has materially outpaced ownership movement — the market hasn't caught up yet.

**Questions to answer:**
- Which currently low-owned players have the strongest recent game logs relative to their ownership %?
- How many days on average does it take for ESPN ownership to respond to a breakout performance?
- Are there position groups (e.g. RP, MI) where the market consistently lags longer?
- Which of our league's teams are fastest to identify and acquire breakout players?

**Data sources:** `2026_mlb_stats_daily.csv`, `2026_espn_rankings_daily.csv`, `2026_espn_activity_season.csv`

**Possible output:** Daily "inefficiency" watchlist of underowned performers; ownership lag curve by position.

---

## 8. Roster Slot Efficiency — Are Teams Wasting Positional Slots?

**Status:** `Not Started`

**Motivation:** Every fantasy team has a fixed number of roster slots per position. A team with a great SS1 but a weak SS2 is leaving value on the table relative to what that slot could produce. This measures how efficiently each team converts their positional allocation into points.

**Idea:** For each positional slot (C, 1B, 2B, SS, 3B, OF×3, SP, RP), compute the actual fantasy points scored vs the league-average output for that slot. Sum the gaps to get a "slot efficiency" score per team — how much value are they under- or over-performing relative to the average slot holder?

**Questions to answer:**
- Which teams are getting above-average production from every slot vs coasting on 2–3 positions?
- Which specific slots are the biggest drags league-wide (typically C, RP)?
- Is there a correlation between slot efficiency and weekly win rate?
- Which teams have injury-exposed slots that are quietly costing them points?

**Data sources:** `2026_espn_stats_daily.csv` — lineup slot, points per player per day

**Possible output:** Slot efficiency heatmap (teams × positions); per-slot league average as a benchmark; weekly slot efficiency trend per team.

---

## 9. Trade Value Audit — Who Is Winning the League's Trades?

**Status:** `Not Started`

**Motivation:** The activity data logs every trade with player names and timestamps. By pulling the season stats of every traded player and splitting them into pre-trade and post-trade windows, we can objectively score each side of every deal.

**Idea:** For each trade, compute cumulative fantasy points for all players exchanged in the 30 days before and 30 days after the trade date. The team receiving the higher post-trade value won the trade. Aggregate across all trades to rank teams by trade acumen.

**Questions to answer:**
- Which team has gained the most cumulative fantasy value through trades this season?
- Are there repeat patterns — one team consistently buying low and another consistently selling low?
- Which single trade had the largest value swing in either direction?
- Do winning trades correlate with winning records, or are teams trading well but still losing?

**Data sources:** `2026_espn_activity_season.csv`, `2026_espn_stats_daily.csv`

**Possible output:** Trade-by-trade value ledger; net trade value gained/lost per team; league trade balance table.

---

## 11. Mutually Beneficial Trade Finder — Identifying Win-Win Deals Within the League

**Status:** `Complete`

**Motivation:** Most trade analysis evaluates a specific proposal after the fact. A proactive approach would scan every team's roster, identify where each team is weak and strong relative to the scoring system, and surface trade candidates that simultaneously improve both sides. In a points-based league, a deal is mutually beneficial when both teams improve their projected weekly fantasy points after the swap — which requires surplus at one position to be exchanged for surplus at another.

**Idea:** For each pair of teams in the league, compute their positional strength scores (fantasy points per slot vs league average). Identify positions where Team A is strong and Team B is weak, and vice versa. Then search the actual rosters for specific player swaps that would close both gaps — and rank candidate deals by the combined two-sided improvement.

**Questions to answer:**
- Which teams have a clear surplus at one position and a clear deficit at another?
- For a given team, which other teams have the most complementary surplus/deficit profiles?
- Which specific 1-for-1 (or 2-for-2) player swaps produce the largest combined two-sided point gain?
- How does the trade value change when evaluated against rest-of-season projections vs recent form?
- Are there deals that look neutral on ADP/rankings but are actually win-win under this specific league's scoring weights?

**Data sources:**
- `2026_espn_stats_daily.csv` — current roster composition, lineup slots, and per-player fantasy points by team
- `2026_mlb_stats_daily.csv` — YTD box score stats to compute position-adjusted value
- `2026_ext_projections_batter.csv` / `2026_ext_projections_pitcher.csv` — rest-of-season projections to evaluate forward value, not just past performance
- `2026_espn_rankings_daily.csv` — ownership % and positional rank as a sanity check on player value

**Approach:**
1. Aggregate each team's fantasy points by positional slot YTD; compute delta vs league average per slot to get a surplus/deficit profile per team
2. For every pair of teams, score their profile compatibility (how well does one team's surplus offset the other's deficit?)
3. For the most compatible pairs, enumerate candidate player swaps and score each deal: `Δ = (Team A pts after) + (Team B pts after) - (Team A pts before) - (Team B pts before)`
4. Rank all candidate swaps by combined Δ; filter to deals where both sides are positive

**Connection to trade_analysis workflow:** Deals surfaced here can be fed directly into the `ideas/idea_11_trade_finder/trade_N/` pipeline for full scoring-system evaluation and write-up.

**Possible output:** League-wide surplus/deficit heatmap (teams × positions); ranked list of mutually beneficial swap candidates with projected two-sided point gain; compatibility score matrix showing which team pairs have the most trade potential.

---

## 10. Hot Hand Detection — Rolling Performance Windows for Streaming Decisions

**Status:** `Not Started`

**Motivation:** A player's season average is a lagging indicator. For daily/weekly lineup decisions, what matters is recent form. By computing rolling 7- and 14-day windows across the full game-log history, we can build a real-time "temperature" metric for every player that surfaces who is hot right now vs who is riding a cold streak.

**Idea:** For each player, compute rolling 7-day and 14-day fantasy point totals from `stats_espn_daily`. Flag players whose recent window significantly exceeds or trails their season-to-date average. Cross-reference against roster status to identify hot free agents being ignored and cold roster players who should be benched or dropped.

**Questions to answer:**
- Which rostered players are currently in a significant cold streak relative to their season average?
- Which free agents are the hottest players not yet owned in the league?
- Does a 7-day hot streak predict the following 7 days, or does regression to the mean dominate?
- Are there players who run in consistent hot/cold cycles that could be exploited with buy-low timing?

**Data sources:** `2026_espn_stats_daily.csv`, `2026_espn_rankings_daily.csv` (ownership context), `2026_mlb_stats_daily.csv` (raw game logs)

**Possible output:** Daily "temperature" leaderboard (hottest and coldest players); persistence analysis of streaks; streaming recommendation list of hot, low-owned free agents.

---

## 12. Bat Tracking Metrics as Batter Predictors — Year-Over-Year Carry-Forward

**Status:** `Not Started`

**Motivation:** MLB's Statcast bat-tracking leaderboard (https://baseballsavant.mlb.com/leaderboard/bat-tracking) publishes per-season metrics like swing speed, squared-up rate, blast rate, and attack angle for every batter. These are physical attributes that change slowly and may be more predictive of the following year's performance than traditional rate stats, which are subject to BABIP noise and strand-rate variance.

**Idea:** Collect yearly bat-tracking data (and analogous Statcast pitching metrics — spin rate, extension, pitch movement profiles) and measure how well each metric predicts next-year performance. Run a year-over-year regression for both hitters and pitchers: which underlying physical metrics are the strongest leading indicators of fantasy-relevant outcomes (HR, AVG, SB, K%, ERA, WHIP)?

**Questions to answer:**
- Which bat-tracking metrics (swing speed, blast rate, squared-up %, etc.) have the strongest year-over-year correlation with following-season HR, AVG, and OPS?
- Are bat-tracking metrics more stable and predictive than traditional stats like xwOBA or wRC+?
- On the pitching side, which Statcast metrics (spin rate, velocity, extension, chase rate) best predict next-year ERA, WHIP, and K/9?
- Are there batters currently undervalued in ESPN rankings whose bat-tracking profiles suggest a breakout is coming?
- Which current-roster players have elite bat-tracking numbers but depressed traditional stats — suggesting a correction upward?

**Data sources:**
- [Baseball Savant Bat Tracking Leaderboard](https://baseballsavant.mlb.com/leaderboard/bat-tracking) — yearly swing speed, blast rate, squared-up %, attack angle per batter
- Baseball Savant Statcast pitching leaderboards — spin rate, velocity, extension, movement profiles per pitcher
- `2026_mlb_stats_daily.csv` / prior seasons — traditional box score stats for the prediction target
- `2026_espn_rankings_daily.csv` — ESPN ADP and ownership as a proxy for market valuation (to find the gap between physical profile and perceived value)

**Approach:**
- Scrape or download multi-year bat-tracking and pitching Statcast data (2020–present)
- Join to season-level traditional stats (HR, AVG, ERA, WHIP, K%) by player-year
- Run year-over-year correlations: metric in year N vs outcome in year N+1
- Rank metrics by predictive power (R², partial correlations controlling for age/opportunity)
- Flag current-season players with elite physical profiles whose traditional stats haven't caught up

**Possible output:** Predictive-power ranking of bat-tracking and pitching metrics; breakout candidate list (strong physical profile, lagging traditional stats); regression model coefficients for year-over-year fantasy value prediction.

---

## 13. Projection Accuracy Tracking — Actual vs Preseason Performance Over Multiple Years

**Status:** `Not Started`

**Motivation:** Preseason projections (from ESPN or external sources) are baked into ADP, draft position, and roster decisions. But how accurate are they? With multiple years of projection and actual stat data, we can measure systematic biases — which positions are consistently over-projected, which player archetypes beat projections most reliably, and whether projection error is predictable enough to exploit at draft time.

**Idea:** For each player-season, compute the delta between their preseason projected stats and their actual end-of-season stats across all fantasy-relevant categories (HR, R, RBI, SB, AVG, OBP for batters; ERA, WHIP, K/9, W, SV for pitchers). Track these deltas year-over-year (2023–2026) to identify systematic patterns: which projection sources are most accurate, which player types beat projections, and whether last year's projection error predicts this year's.

**Questions to answer:**
- Which fantasy-relevant stat categories are most and least accurately projected each year?
- Are there position groups (e.g. catchers, closers) where projections are systematically optimistic or pessimistic?
- Which individual players have consistently beaten or missed their preseason projections across multiple years?
- Does a player's prior-year projection error correlate with their current-year error — i.e., is beating projections a repeatable skill?
- Are young/breakout players systematically under-projected and veterans over-projected?
- Which stat categories show the most year-over-year projection volatility (large swings in error direction)?
- In draft value terms: which ADP ranges produce the most consistent projection beats vs busts?

**Data sources:**
- `2023_ext_projections_batter.csv` / `2024.csv` / `2025.csv` / `2026.csv` — preseason projected stats per batter by year
- `2023_ext_projections_pitcher.csv` / `2024.csv` / `2025.csv` / `2026.csv` — preseason projected stats per pitcher by year
- `2023_mlb_stats_daily.csv` through `2026_mlb_stats_daily.csv` — actual game-log stats aggregated to season totals for comparison
- `2026_espn_rankings_daily.csv` — ADP and ownership % as a proxy for how much the market trusted each projection

**Approach:**
1. Aggregate daily game logs to season totals per player per year (AB, HR, R, RBI, SB, AVG, OBP for batters; IP, ERA, WHIP, K, W, SV for pitchers)
2. Join to projection files on `(player_name, year)` — flag join failures (players with no projection, called-up mid-season) separately
3. Compute per-stat deltas: `actual - projected` for counting stats; `projected - actual` for ERA/WHIP (lower is better)
4. Aggregate by year, position, age bucket, and ADP tier to surface systematic biases
5. Run year-over-year correlation on individual player projection error to test repeatability
6. Flag players whose current-year projection looks mis-calibrated based on their historical error pattern

**Key metrics:**
- **Projection error** per stat: `actual - projected` (positive = beat projection)
- **Relative accuracy**: `actual / projected` ratio — useful for comparing across different stat scales
- **Bias score**: mean error across a group (position, age, ADP tier) — systematic over/under-projection
- **Repeatability score**: year-over-year correlation of individual player projection error (Pearson R across matched player-years)

**Possible output:** Multi-year projection error heatmap by stat and position; ranked list of players who consistently beat or miss projections; ADP tier accuracy analysis (which draft rounds are least/most predictable); current-year "regression candidates" flagged by historical error pattern.

---

## 14. Player Injury Data Analysis — Duration, Frequency, and Predictability

**Status:** `Complete`

**Motivation:** Injuries have a massive impact on fantasy performance. By capturing data around player injuries, we can understand the average duration by position, identify players who are systematically more prone to injury, and leverage historical injury data to better discount injury risk during drafts.

**Idea:** Track all injured list (IL) stints for players across the league. Compute the duration of each injury, categorize them by injury type and player position, and maintain a historical ledger of each player's injury frequency.

**Questions to answer:**
- How long are players typically injured when placed on the IL?
- How often do injuries occur per position (e.g., are pitchers significantly more likely to miss time)?
- Are certain players (or player profiles) systematically more likely to be injured?
- Can historical injury data be used to accurately forecast a player's injury risk?

**Data sources:**
- MLB API injury/transaction logs (via `fetch_activity_espn_season.py` or new MLB API scraper) to detect IL placements and activations.
- Historical MLB injury datasets (if available) or multi-year transaction logs.

**Approach:**
1. Parse transaction logs to capture every time a player is placed on or activated from the IL.
2. Calculate the total days missed for each injury stint.
3. Group and aggregate injury events by player, position, and injury type (if available).
4. Build a historical profile for each player computing their "injury frequency" and "average days missed per season".
5. Analyze positional injury rates (e.g., starting pitchers vs. outfielders).

**Possible output:** A player "injury risk" score/index based on historical IL stints; average injury duration tables by position; a list of "high-risk" draft targets based on their propensity for injury.

---

## 15. Best Waiver Pickups of the Season — Post-Acquisition Categorical Contribution

**Status:** `Complete`

> **TODO (end of season):** Rerun `fantasy_baseball/ideas/idea_15_best_pickups/analyze_best_pickups_espn_2026.py` once the full season's data is available. Update `best_pickups_espn_2026.md` and republish `pjrigali.github.io/pages/fantasy-baseball/31_Fantasy_Baseball_Best_Pickups_2026.md`. The mid-season run used data through 2026-06-16.

**Motivation:** Not every roster-building win happens at the draft. Waiver wire adds and free agent pickups can swing weekly matchups and shift league standings. By isolating all non-draft acquisitions and measuring each player's statistical contribution across all 10 scoring categories from the moment they were picked up, we can objectively rank the best in-season roster moves of the year.

**Idea:** Filter `2026_espn_activity_season.csv` to adds that were not the result of the initial draft. For each add, record the acquisition date and compute that player's cumulative stats in the 5 batting categories (R, HR, RBI, SB, OPS) and 5 pitching categories (K/9, QS, SVHD, ERA, WHIP) from their pickup date through the end of the available data window. Rank pickups by their post-acquisition categorical value to surface the players who delivered the most real scoring-category impact after being claimed.

**Questions to answer:**
- Which non-drafted players have contributed the most across the 5x5 categories since being picked up?
- Which team made the single best waiver claim of the season, measured by post-add categorical output?
- Are the best pickups concentrated in a specific position (e.g., breakout SP, hot-streak RP, emerging OF)?
- How does the pickup date affect value — do early-season adds outperform late-season streamers by total contribution, and do late-season adds win on a per-week basis?
- Which players were picked up and dropped quickly despite going on to produce significant value elsewhere (missed opportunities)?
- Is there a team that has consistently found high-value waiver adds throughout the season vs one that has made mostly low-return claims?

**Data sources:**
- `2026_espn_activity_season.csv` — acquisition type (waiver, free agent, trade) and date; used to isolate non-draft adds and set the post-acquisition start date
- `2026_espn_stats_daily.csv` — daily stats per player to accumulate post-add totals for R, HR, RBI, SB, OPS
- `2026_mlb_stats_daily.csv` — game-level box score data for pitching categories (K/9, QS, SVHD, ERA, WHIP) from the pickup date forward
- `2026_espn_rankings_daily.csv` — ownership % at pickup date as a proxy for how overlooked the player was when claimed

**Approach:**
1. Filter activity log to adds where acquisition type is not "Draft" — include waiver claims and free agent adds
2. For each add, join to `stats_espn_daily` and `stats_mlb_daily` on `(player_name, date >= acquisition_date)` to build a post-add stat window
3. Aggregate to cumulative totals: counting stats (R, HR, RBI, SB, QS, SVHD, K) and rate stats (OPS, ERA, WHIP, K/9) over the post-add window
4. **Scale contributions using z-scores**: for each of the 10 categories, compute the mean and standard deviation across all pickups in that category, then express each player's value as `(player_stat - mean) / std_dev`. This normalizes for distributional differences — HR has a tight distribution, so a single HR above the mean carries a larger z-score than a single R above the mean in the wider-spread R distribution. For inverse categories (ERA, WHIP), negate the z-score so that lower = better still reads as positive contribution.
5. Sum the 10 z-scores to produce a **composite z-score** per pickup — this is the primary ranking metric. A player who is +1.5 SD in HR contributes more to the composite than a player who is +1.5 SD in R, reflecting the inherent scarcity of power.
6. Separate batter and pitcher leaderboards (batters scored on 5 batting z-scores, pitchers on 5 pitching z-scores), then produce a combined overall list using all applicable categories per player type
7. Flag the ownership % at pickup date from `rankings_espn_daily` to highlight steals — high composite z-score at low ownership = true waiver gem

**Key metrics:**
- **Post-add cumulative counting stats**: R, HR, RBI, SB, QS, SVHD per player since acquisition
- **Post-add rate stats**: OPS, ERA, WHIP, K/9 over their active games since pickup
- **Per-category z-score**: each stat normalized to `(value - category_mean) / category_std` across all pickups — the unit of comparison that accounts for distributional scale differences between categories
- **Composite z-score**: sum of all applicable per-category z-scores — primary ranking metric (higher = more cross-category value delivered)
- **Ownership % at pickup**: from `rankings_espn_daily` on or near the acquisition date — low ownership + high composite z-score = overlooked gem
- **Days held**: how long each player remained on the roster after pickup — filters out short-lived streamers vs sustained contributors

**Possible output:** Ranked leaderboard of top 10–15 waiver/FA pickups by composite categorical contribution (batters and pitchers separately); per-team summary of total post-add value accumulated; "gems" list of high-value, low-ownership-at-pickup players; list of notable missed opportunities (dropped players who kept producing).

---

## 16. Waiver Wire Signal Detection — Pre-Pickup Indicators of Breakout Pickups

**Status:** `Complete`

**Deliverables:**
- `ideas/idea_16_waiver_signals/analyze_waiver_signals_espn_2026.py` — signal analysis engine; Mann-Whitney rank-biserial correlation ranking across 19 batter / 15 pitcher features; F1-optimal thresholds; cross-year validation vs 2025
- `ideas/idea_16_waiver_signals/analyze_best_pickups_espn_2025.py` — 2025 best-pickups engine using first-appearance detection as a proxy for pickup dates (no activity CSV available for 2025)
- `ideas/idea_16_waiver_signals/reports/waiver_signals_2026.md` — full signal report with ranked feature table, prescriptive rules, retrospective audit, and 2025 cross-year validation
- `watch_waiver_signals_espn.py` — daily watcher script; scores all healthy free agents against the derived thresholds; appends to `{YEAR}_espn_waiver_watchlist.csv`; runs as Step 7 of `fantasy-collect-all-data`
- `data-lake/01_Bronze/fantasy_baseball/2026_espn_waiver_watchlist.csv` — live daily watchlist CSV, deduped on `(date, player_id)`

**Top signals (2026, cross-validated vs 2025):**
- *Batters:* `pct_owned_at_pickup ≥ 22.8` (r=0.70), `hr_per_game_7d ≥ 0.14` (r=0.48), `batting_slot_mode_7d ≤ 7` (r=−0.42)
- *Pitchers:* `pct_change_mean_7d ≥ 1.04` (r=0.50), `era_14d ≤ 2.25` (r=−0.40), `ownership_slope_14d ≥ 0.53` (r=0.39)

**Motivation:** Idea 15 identified *who* the best waiver pickups of 2026 were after the fact. This idea works backwards: given that ground truth, what could we have *known before* the acquisition date that predicted those players would be valuable? The goal is a set of prescriptive, threshold-based signals — concrete rules a manager can apply each week to identify the next Jordan Walker or Bryan Baker before someone else claims them.

**Idea:** For every pickup in `2026_espn_best_pickups.csv`, build a pre-pickup feature profile using the 7, 14, and 21 days of game logs *before* the acquisition date. Separate the top-quartile pickups (high composite z) from the bottom-quartile pickups (low composite z). Measure which pre-pickup metrics differ most significantly between the two groups. Then translate those differences into prescriptive thresholds: "if a player shows X in the prior 7 days AND Y, they are a strong add candidate."

Cross-validate using prior seasons (2024, 2025) where the same data exists — signals that hold across multiple seasons are more robust than single-year artifacts.

**Questions to answer:**
- Which pre-pickup metrics most reliably separate top-quartile from bottom-quartile pickups?
- Do batters show a hitting streak, rising OPS, or batting order promotion before their breakout?
- Do pitchers show a strikeout spike, innings load increase, or ERA improvement before their breakout?
- How far in advance does the signal appear — 7 days, 14 days, or longer?
- Does ownership % trajectory before the pickup (rising vs flat) predict post-add value, independent of the stat signal?
- Do prior-season stats (the year before the pickup) predict who breaks out on the waiver wire, or is recent form the dominant signal?
- Are there position-specific signals — e.g., does a reliever's saves opportunity (closer injury on their team) predict SVHD accumulation regardless of recent ERA?

**Prescriptive signal targets (batters):**
- **Rolling 7-day OPS ≥ X** — identify batters in a hot streak before the market reacts
- **Rolling 7-day AB/G ≥ X** — confirms they're getting consistent plate appearances (not platooning)
- **Batting order slot ≤ 3 for ≥ Y of last 7 games** — promoted to a high-value lineup position
- **Prior-season SB ≥ X AND current stolen base pace below expectation** — speed likely to emerge
- **Return from IL within last 14 days AND pre-IL OPS ≥ X** — post-IL bounce candidate
- **Ownership % ≤ Y% AND pct_change trending upward** — market starting to notice, still claimable

**Prescriptive signal targets (pitchers):**
- **Rolling 7-day K/9 ≥ X** — strikeout spike indicating command improvement or opponent weakness
- **Rolling 14-day ERA ≤ X with WHIP ≤ Y** — sustained quality, not a one-game outlier
- **Team's primary closer on IL or struggling** — saves opportunities opening up; identify next saves source by team
- **SVHD in ≥ Z of last 7 appearances** — already accumulating holds/saves at pace
- **Starter recently demoted → reliever role** — K/9 typically spikes in shorter outings; flag high-K starters moved to bullpen
- **Recent IP/G ≥ X for starters** — workload consistent with QS pace

**Approach:**
1. Load `2026_espn_best_pickups.csv` to get the labeled set — label each pickup as top-quartile (composite z ≥ 75th percentile within player type) or bottom-quartile (composite z ≤ 25th percentile)
2. For each pickup, pull pre-pickup game logs from `2026_mlb_stats_daily.csv` and `2026_espn_stats_daily.csv` for the 7, 14, and 21 days before `acquisition_date`
3. Compute pre-pickup feature vectors per player: rolling OPS/ERA/K9/WHIP, games played rate, batting order slot distribution, ownership trend slope from `2026_espn_rankings_daily.csv`
4. For each feature, compute the mean and distribution for top-quartile vs bottom-quartile pickups; use a simple t-test or Mann-Whitney U to rank features by discriminative power
5. Translate the top features into threshold rules: find the cutoff value for each metric that maximizes separation between the two groups (similar to a single-feature decision boundary)
6. Combine the top 3–4 signals into a composite "add score" per signal combination — score = number of signals triggered
7. Back-test the signal rules against 2024 and 2025 activity + stat data to measure precision (what % of flagged players become top-quartile pickups) and recall (what % of top-quartile pickups were flagged in advance)
8. Report the final ruleset as concrete, actionable thresholds — e.g., "Batter with 7-day OPS ≥ .820, AB/G ≥ 3.5, ownership < 30%, and batting order slot ≤ 3 in 5+ of last 7 games: strong add"

**Data sources:**
- `data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv` — ground truth labels from idea 15 (top vs bottom pickup performers)
- `2026_mlb_stats_daily.csv` / `2025.csv` / `2024.csv` — pre-pickup game logs for feature construction
- `2026_espn_stats_daily.csv` / `2025.csv` / `2024.csv` — lineup slot, ownership context, fantasy points in the pre-pickup window
- `2026_espn_rankings_daily.csv` / `2025.csv` / `2024.csv` — ownership %, pct_change, ESPN rank trend before the pickup date
- `2026_espn_activity_season.csv` / prior seasons — pickup dates and which team made the claim (to reproduce the same analysis for 2024/2025)
- `2026_mlb_lineups_batters.csv` — batting order slot history in the pre-pickup window (batter signal only)

**Key metrics to derive:**
- **Rolling 7/14-day OPS** (batters) — weighted by AB, same method as idea 15
- **Rolling 7/14-day K/9, ERA, WHIP** (pitchers) — from aggregated OUTS, ER, P_H, P_BB, K totals
- **Games played rate** — games with AB > 0 (batters) or OUTS > 0 (pitchers) per calendar day in window
- **Batting order slot mode** — most frequent slot in the pre-pickup window; flag if ≤ 3 (batters)
- **Ownership % slope** — linear regression of pct_owned over the 7 days before pickup; positive slope = market waking up
- **Days since IL activation** — for players recently returned from injury
- **Prior-season composite z** (from a prior-year run of idea 15 or season-aggregated stats) — flags known talent not yet re-claimed

**Possible output:**
- Ranked signal importance table: which pre-pickup features most separate good from bad pickups, with effect size and cross-season validation score
- Prescriptive rulebook: a printed set of threshold-based rules per player type (batter / reliever / starter) with back-tested precision and recall on 2024–2025 data
- Retrospective audit of 2026 top pickups: for each top-15 batter and pitcher from idea 15, show which signals were firing in the days before someone claimed them — and how many days in advance the signal was available
- Weekly add-candidate watchlist generator: a script that reads the current week's `rankings_espn_daily` and `stats_mlb_daily` and outputs players currently meeting the signal thresholds who are still available (ownership < 50%)

---

## 17. Waiver Wire Signal Detection — Multi-Method Prescriptive Metric Discovery

**Status:** `Complete` (2026-06-19) — all sections A–I + consolidation + runtime watchlist in `ideas/idea_17_multi_method_signals/`. All algorithms hand-rolled (numpy/scipy/statsmodels; no sklearn/ruptures in venv). Robust-core methods: clustering (A), sequential/SPRT (D), anomaly (E), forecast (F), bandit (I). Section G (market) is an honest negative result. Cross-season scope is 2026 + 2025 (2024 infeasible — no ESPN ground truth).

**Motivation:** Idea 16 establishes the supervised baseline — use post-pickup composite z as a label and derive threshold rules. This idea expands the toolkit with every other method class available for signal detection: unsupervised clustering, statistical change detection, Bayesian inference, time series forecasting, anomaly detection, market efficiency analysis, opportunity graph modeling, and sequential testing. Each method sees the pre-pickup feature space differently. The goal is to run all of them, compare what each finds, and consolidate into the most robust and cross-validated signal set possible. Methods that agree across approaches are the ones worth building a weekly runtime watchlist around.

**Idea:** Build the same pre-pickup feature vectors as idea 16 (7/14/21-day rolling stats, ownership trend, batting order slot, opportunity signals) and run the full suite of methods below. After each method produces its signals or cluster assignments, overlay post-pickup composite z (from idea 15) to validate which signals actually predict good pickups. Methods are grouped by category. The full approach is modular — each section can be built and evaluated independently.

---

### A. Unsupervised Clustering — Archetype Discovery

Ignores post-pickup outcomes during training. Discovers natural groupings in the pre-pickup feature space, then overlays performance afterward to see which archetypes are predictive.

- **PCA first** — reduce the feature matrix to 2–3 principal components for visualization and to remove correlated noise before clustering. Inspect loadings to name the principal axes (e.g., PC1 = "hot hitter" axis loading on recent OPS and batting order slot; PC2 = "market lag" axis loading on ownership slope and days since IL return)
- **K-means** — cluster in PCA space; use silhouette score and elbow curve to select k (expect 4–7 meaningful archetypes per player type). Cluster centroids are the archetype profiles
- **DBSCAN** — density-based clustering; unlike K-means it doesn't force every player into a cluster, naturally isolating outlier breakout players who don't fit any archetype — these are worth inspecting individually each season as potential novel opportunity types
- **Hierarchical clustering** — dendrogram to show how archetypes relate; reveals whether "hot streak batter" and "IL return bounce" are siblings in feature space or fully orthogonal

**Expected archetypes (hypotheses to test):**

*Batters:* Hot Streak Riser (high 7-day OPS, high AB/G, batting order ≤ 3, rising ownership), Quiet Grinder (steady moderate stats, no spike, low ownership), IL Return Bounce (recent IL activation, strong pre-IL OPS, ownership declining during absence), Lineup Promoted (batting order moved up 2+ spots in last 7 days)

*Pitchers:* Closer Opportunity (SVHD accumulating, team's closer on IL or cold), Strikeout Spike (K/9 sharply higher in last 7 days vs prior 14), Workload Builder (IP/G steadily rising, QS pace consistent), Role Shift (starter moved to high-leverage relief — K/9 typically spikes)

---

### B. Statistical Change Detection — Pinpointing the Breakout Game

Fixed rolling windows (7/14-day) smooth over the actual inflection point. Change detection algorithms find the exact game where a player's performance regime shifted.

- **PELT (Pruned Exact Linear Time)** — efficient changepoint detection on a player's rolling game-log series (OPS per game for batters, ERA/K9 per outing for pitchers). Identifies the precise date of a regime shift — more actionable than "they've been hot recently"
- **CUSUM (Cumulative Sum Control Chart)** — detects sustained directional drift in a stat series. A CUSUM signal on a batter's OPS series means the upward move has been consistent enough to cross a statistical threshold, not a single outlier game
- **Bayesian changepoint detection** — probabilistic version; outputs a posterior distribution over the change date rather than a single point. Useful when the data is noisy (small sample sizes in short pre-pickup windows)

*Why this matters:* Two players can have the same 14-day rolling OPS, but one player has been trending up for 14 straight days (sustained shift) while the other had one great week then cooled. Change detection distinguishes them.

---

### C. Bayesian Updating — Correctly Weighting Small Samples

A player's 7-day hot streak means very different things depending on their prior track record. Bayesian methods incorporate both.

- **Empirical Bayes** — estimate each player's prior distribution from their preseason projection or prior-season stats. Update the prior with in-season game logs using Bayes' rule. A player with a strong prior (projected .850 OPS) who is currently .900 gets more credit than a career .650 OPS player running .900 on 20 AB
- **Beta-Binomial for rate stats** — model each player's "hit rate" (games above a threshold OPS) as a Beta distribution. Prior is set by prior-season performance; posterior is updated game by game. The posterior mean is the Bayesian estimate of true ability — shrinks hot streaks toward the mean appropriately
- **Regression-to-mean modeling** — for a given pre-pickup OPS or ERA, estimate the expected post-pickup regression. Players whose hot stretch is backed by sustainable underlying rates (high contact quality, low BABIP relative to exit velocity, high K%) will regress less. Flag players where the pre-pickup stat is likely to *persist* vs players riding luck

---

### D. Sequential Testing — Earliest Possible Signal Detection

SPRT and sequential methods are designed to reach a decision (real shift vs noise) with as few data points as possible — critical when the add window is short.

- **Sequential Probability Ratio Test (SPRT)** — tests the null (player is performing at their prior level) vs the alternative (player has shifted to a higher level). Raises a signal the moment the likelihood ratio crosses a decision boundary. For a batter: raises an "add" signal after the minimum number of games needed to be confident the OPS improvement is real, not random
- **One-sided CUSUM as a sequential test** — flag a player the first time their cumulative performance deviation from prior mean crosses a threshold. Identical to the control-chart application but framed as an alarm system: "this player crossed the signal threshold on Game N"

*Output of this section:* For each pickup in the ground truth set (idea 15 top quartile), report on which game before the acquisition date the SPRT or CUSUM signal would have fired. Median lead time = how many days in advance the signal was available before anyone claimed the player.

---

### E. Anomaly Detection — Flagging the Unusual

Train on the distribution of "normal" player stat profiles; flag anyone whose recent stats fall outside it. Catches breakouts without needing labeled outcomes or defined thresholds.

- **Isolation Forest** — ensemble method that isolates anomalies by randomly partitioning the feature space. Points requiring fewer partitions to isolate are anomalies. Run on the rolling stat feature matrix; a high anomaly score in a player's recent window means their recent performance is unusual relative to the broader population — either a breakout or a collapse. Separates by direction using the sign of the deviation
- **One-Class SVM** — train on the "normal" region of the feature space (the bulk of the player population in a given week); flag any player whose recent feature vector falls outside the learned boundary. Unlike isolation forest, the decision boundary is a smooth hypersurface in feature space

*Key advantage over clustering:* anomaly detection requires no cluster assignment and no archetype label. Any player whose recent stats are unusually good relative to the population gets flagged automatically.

---

### F. Time Series Forecasting — Project the Next 7 Days

Rather than describing what a player has done, forecast what they will do next week.

- **Exponential smoothing (ETS)** — weighted average of recent observations with exponential decay; more recent games count more. Project each player's next-7-day OPS/ERA/K9 from their game log history. Players whose projected next-7 exceeds their ownership-implied value are add candidates
- **ARIMA** — autoregressive model that captures both trend and autocorrelation in the performance series. More robust than simple smoothing when performance shows momentum (streaks) or mean-reversion patterns
- **Comparison to idea 16 thresholds:** the forecasted next-7 stat can replace the raw rolling average as the input feature to idea 16's threshold rules. "Add if forecasted 7-day OPS ≥ X" is more forward-looking than "add if last 7-day OPS ≥ X"

---

### G. Market Efficiency Analysis — Where Is the Edge Largest?

Treat ownership % as a prediction market. The lag between performance and market reaction is the add window.

- **Ownership lag by position** — for each position group (C, MI, OF, SP, RP), compute the median number of days between a player posting a qualifying performance signal and the corresponding ownership spike (defined as +10% pct_owned in a single day). Position groups with the longest lag have the widest add windows — the market is slowest to react there
- **Ownership slope vs performance decile** — bin all players by their rolling performance decile; plot mean ownership change rate per decile. The gap between performance rank and ownership response rate is the inefficiency to exploit
- **Low-signal, high-ownership players** — the inverse: players whose ownership is high but recent performance is weak. These are drop candidates; their roster spots are the ones where competing managers are leaving value on the table

---

### H. Opportunity Graph — Lineup Dependency Modeling

Sometimes a player's add value isn't about their own stats — it's about a structural change in their opportunity.

- **Batting order dependency** — for each MLB team, model which batting slots feed run-scoring opportunities to each other (e.g., leadoff OBP drives runs for the 2-3-4 hitters). When a high-OBP leadoff hitter gets injured and the 2-hole batter moves up, the 2-hole batter's R/RBI opportunity increases even if their own stats haven't changed yet
- **Saves opportunity cascade** — when a team's closer goes to the IL, the SVHD opportunity flows to the next arm in the bullpen hierarchy. Map each team's closer depth (from `2026_mlb_closers_depth.csv`) and flag the next-in-line relievers as add candidates whenever a closer event (IL, poor ERA, blown saves) occurs
- **Platoon detection** — identify players who are platooning (alternating starts vs LHP/RHP). A platoon partner going to the IL means the remaining player suddenly gets full-time at-bats — a structural opportunity increase not visible in their own recent stats

---

### I. Multi-Armed Bandit — Add Decision as Explore/Exploit

Frame the weekly waiver claim as a sequential decision problem under uncertainty.

- **Epsilon-greedy** — with probability ε, add a lower-signal player (explore); otherwise, add the highest-expected-value available player (exploit). Calibrate ε to the manager's add budget and weeks remaining in the season — exploration is more valuable early in the season when there's more time to benefit from a found gem
- **Thompson sampling** — maintain a Beta distribution over each available player's "add quality" (probability of being a top-quartile pickup). Sample from each distribution; claim the player whose sample is highest. Naturally balances exploration and exploitation; updates the distribution after each claim based on actual post-add performance
- **Contextual bandit** — extend to include context (matchup difficulty, bye weeks, injury news) as features that modify the expected reward. The archetype assignment from section A is one such context feature

---

### Approach (combined pipeline):

1. Build the pre-pickup feature matrix from `stats_mlb_daily`, `stats_espn_daily`, `rankings_espn_daily`, and `lineups_mlb_batters`; standardize all features; split into batter and pitcher sets
2. Run sections A–I sequentially, recording for each player which methods flagged them and what signal each produced
3. Overlay post-pickup composite z (idea 15) for validation — compute precision and recall for each method's flags
4. Rank methods by predictive power; identify the subset that agree most consistently across 2024–2026 seasons (cross-season stability = robustness)
5. For each top-15 batter and pitcher from idea 15, produce a retrospective audit: which methods would have fired before the pickup date, and how many days in advance?
6. Consolidate into a runtime watchlist script: each week, run all methods on the current available player pool and output a ranked add-candidate list with the methods that fired for each player

**Connection to idea 16:** Idea 16 produces threshold rules from the supervised approach. Idea 17 produces signals from every other method class. A player who triggers an idea 16 threshold rule AND is flagged by 3+ idea 17 methods is the highest-confidence add. The combined signal count is the confidence score.

**Data sources:** Same as idea 16.
- `data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv` — post-pickup composite z for validation only
- `2026_mlb_stats_daily.csv` / `2025.csv` / `2024.csv` — pre-pickup game logs
- `2026_espn_stats_daily.csv` / `2025.csv` / `2024.csv` — lineup slot, ownership, fantasy points
- `2026_espn_rankings_daily.csv` / `2025.csv` / `2024.csv` — ownership %, pct_change trend
- `2026_mlb_lineups_batters.csv` — batting order slot history
- `2026_mlb_closers_depth.csv` — bullpen hierarchy for saves opportunity cascade (section H)

**Possible output:**
- Per-method validation table: precision, recall, and cross-season stability score for each of sections A–I
- PCA biplot with cluster membership and anomaly scores overlaid
- Changepoint audit: for each idea 15 top pickup, which game did the SPRT/CUSUM signal fire, and how many days before the actual acquisition date?
- Archetype cards: one card per cluster with centroid features, cluster size, median composite z, and name
- Market lag table by position: median days between signal and ownership spike, ranked — shows where add windows are widest
- Opportunity graph per MLB team: closer depth hierarchy, lineup dependency map
- Weekly runtime watchlist script: ingests current week's data, runs all methods, outputs ranked add candidates with signal count and contributing methods per player
