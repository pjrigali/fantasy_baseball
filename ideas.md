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
- `stats_mlb_daily_2026.csv` — who actually played each day (game logs)
- `stats_espn_daily_2026.csv` — which players are on which fantasy team, and their fantasy points
- `lineups_mlb_batters_2026.csv` — batting order data to cross-reference active players

**Possible output:** A daily participation rate per fantasy team (% of roster with a game log entry), plotted against fantasy points scored that day/week.

---

## 2. Gini Analysis — Box Score Concentration by Player and Team

**Status:** `Not Started`

**Observation:** Fantasy scoring is likely highly unequal — a small number of players probably account for a disproportionate share of total points scored across the league. A Gini coefficient (0 = perfectly equal, 1 = one player scores everything) quantifies that concentration.

**Idea:** Apply a Gini analysis at three levels:
1. **Player level** — across all rostered players, how concentrated is total fantasy scoring? Who are the top contributors driving the Lorenz curve?
2. **Team level** — within each fantasy team's roster, how dependent are they on a small number of players? A high intra-roster Gini means they live and die by 2–3 stars.
3. **League capture** — which fantasy team "owns" the highest-scoring players? Does one team disproportionately hold the value-dense tail of the distribution?

**Keeper angle:** The players sitting in the high-scoring tail of the Gini curve are the natural keeper candidates — they produce outsized value relative to replacement. Cross-reference against `activity_espn_season_2026.csv` to see how they were acquired (waiver, draft, trade) and whether they're likely to be retained.

**Questions to answer:**
- What is the league-wide Gini on cumulative season fantasy points?
- Which 10–15 players account for the top decile of scoring?
- Which team holds the most of those players, and how concentrated is their roster?
- Are the high-Gini players draftable keepers, or were they waiver pickups (suggesting volatility)?

**Data sources:**
- `stats_espn_daily_2026.csv` — daily fantasy points per player per team
- `activity_espn_season_2026.csv` — acquisition history (drafted vs waiver vs trade)
- `rankings_espn_daily_2026.csv` — ownership % and ADP as a proxy for perceived value

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
- `lineups_mlb_batters_2026.csv` — date, team, player, batting order slot
- `stats_mlb_daily_2026.csv` — per-game hitting stats (AB, R, H, HR, RBI, SB, TB, BB, SO)
- `stats_espn_daily_2026.csv` — fantasy points, to tie MLB output back to fantasy value

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
- `stats_mlb_daily_2026.csv` — per-game H, AB, BB, HBP, SF (to compute game-level OBP)
- `stats_espn_daily_2026.csv` — fantasy points and roster slot context
- `lineups_mlb_batters_2026.csv` — to control for games where player sat out vs played and went hitless

**Key metric:** Game-level OBP distribution per player (mean, std dev, % of games with OBP = 0, % of games above .400). A "consistency score" could be mean / std_dev — higher is more reliable.

**Possible output:** Player consistency rankings; scatter of season-avg OBP vs consistency score to surface the "illusory" quadrant; streakiness heatmap by player over the season calendar.

---

## 5. Box Score Stat Relationships — Correlation, Redundancy, and Scoring System Audit

**Status:** `Not Started`

**Observation:** Fantasy scoring systems typically assign fixed point values to each stat (R, HR, RBI, SB, OPS, K, ERA, WHIP, etc.), but those stats are not independent. HR drives RBI and R simultaneously, meaning power hitters get amplified credit while a walk-heavy, low-power player may be undervalued. Understanding the correlation structure exposes which stats are redundant, which are independent signals, and whether the current scoring weights reflect actual value.

**Idea:** Build a full correlation matrix across all box score stats for both batters and pitchers, then audit the current ESPN scoring weights against what the data actually shows. Identify the player archetypes that emerge from the stat clusters.

**Questions to answer:**
- Which stats are highly correlated (e.g. HR↔RBI, K↔ERA) and therefore effectively double-counted in the scoring system?
- Which stats are independent signals that capture value not already reflected elsewhere (e.g. SB, BB, HBP)?
- Are there stats not currently scored that have strong relationships with fantasy outcomes and should be added?
- Are there stats being scored that are nearly redundant with higher-weighted stats and could be dropped or reweighted?
- What player archetypes emerge when clustering by stat profile — speedsters, power bats, contact hitters, strikeout pitchers, ground-ball pitchers — and which fantasy teams hold which archetypes?
- Do certain archetypes consistently over- or under-perform their ESPN scoring relative to their actual MLB contribution?

**Data sources:**
- `stats_mlb_daily_2026.csv` — full per-game stat vectors for batters and pitchers
- `stats_espn_daily_2026.csv` — ESPN fantasy points (the scoring output to audit against)
- `rankings_espn_daily_2026.csv` — ownership and ADP as a market proxy for perceived value

**Approach:**
- Pearson correlation matrix across all numeric stat columns, split by batter/pitcher
- PCA or clustering (k-means) on season-aggregated stat profiles to surface archetypes
- Regression of individual stats against ESPN fantasy points to back out implied weights vs actual ESPN weights

**Possible output:** Correlation heatmap (batters and pitchers separately); archetype cluster profiles with representative players named; a side-by-side of current ESPN scoring weights vs regression-implied weights to flag candidates for rebalancing.

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

**Data sources:** `activity_espn_season_2026.csv`, `stats_espn_daily_2026.csv`

**Possible output:** Per-team transaction ROI leaderboard; list of the worst drops of the season by value left on the table.

---

## 7. Ownership Lag — Finding Market Inefficiencies Before ESPN Catches Up

**Status:** `Not Started`

**Motivation:** The `rankings_espn_daily_2026.csv` captures both `pct_owned` and `pct_change` (the trending signal) on a daily basis. A player breaking out will show strong game-log stats before the ownership % moves. The lag between performance and market reaction is the window to act.

**Idea:** For each player, compare their rolling 7-day `stats_mlb_daily` performance against their ownership trend in `rankings_espn_daily`. Identify players where performance has materially outpaced ownership movement — the market hasn't caught up yet.

**Questions to answer:**
- Which currently low-owned players have the strongest recent game logs relative to their ownership %?
- How many days on average does it take for ESPN ownership to respond to a breakout performance?
- Are there position groups (e.g. RP, MI) where the market consistently lags longer?
- Which of our league's teams are fastest to identify and acquire breakout players?

**Data sources:** `stats_mlb_daily_2026.csv`, `rankings_espn_daily_2026.csv`, `activity_espn_season_2026.csv`

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

**Data sources:** `stats_espn_daily_2026.csv` — lineup slot, points per player per day

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

**Data sources:** `activity_espn_season_2026.csv`, `stats_espn_daily_2026.csv`

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
- `stats_espn_daily_2026.csv` — current roster composition, lineup slots, and per-player fantasy points by team
- `stats_mlb_daily_2026.csv` — YTD box score stats to compute position-adjusted value
- `player_batter_projections_2026.csv` / `player_pitcher_projections_2026.csv` — rest-of-season projections to evaluate forward value, not just past performance
- `rankings_espn_daily_2026.csv` — ownership % and positional rank as a sanity check on player value

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

**Data sources:** `stats_espn_daily_2026.csv`, `rankings_espn_daily_2026.csv` (ownership context), `stats_mlb_daily_2026.csv` (raw game logs)

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
- `stats_mlb_daily_2026.csv` / prior seasons — traditional box score stats for the prediction target
- `rankings_espn_daily_2026.csv` — ESPN ADP and ownership as a proxy for market valuation (to find the gap between physical profile and perceived value)

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
- `player_batter_projections_2023.csv` / `2024.csv` / `2025.csv` / `2026.csv` — preseason projected stats per batter by year
- `player_pitcher_projections_2023.csv` / `2024.csv` / `2025.csv` / `2026.csv` — preseason projected stats per pitcher by year
- `stats_mlb_daily_2023.csv` through `stats_mlb_daily_2026.csv` — actual game-log stats aggregated to season totals for comparison
- `rankings_espn_daily_2026.csv` — ADP and ownership % as a proxy for how much the market trusted each projection

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

**Idea:** Filter `activity_espn_season_2026.csv` to adds that were not the result of the initial draft. For each add, record the acquisition date and compute that player's cumulative stats in the 5 batting categories (R, HR, RBI, SB, OPS) and 5 pitching categories (K/9, QS, SVHD, ERA, WHIP) from their pickup date through the end of the available data window. Rank pickups by their post-acquisition categorical value to surface the players who delivered the most real scoring-category impact after being claimed.

**Questions to answer:**
- Which non-drafted players have contributed the most across the 5x5 categories since being picked up?
- Which team made the single best waiver claim of the season, measured by post-add categorical output?
- Are the best pickups concentrated in a specific position (e.g., breakout SP, hot-streak RP, emerging OF)?
- How does the pickup date affect value — do early-season adds outperform late-season streamers by total contribution, and do late-season adds win on a per-week basis?
- Which players were picked up and dropped quickly despite going on to produce significant value elsewhere (missed opportunities)?
- Is there a team that has consistently found high-value waiver adds throughout the season vs one that has made mostly low-return claims?

**Data sources:**
- `activity_espn_season_2026.csv` — acquisition type (waiver, free agent, trade) and date; used to isolate non-draft adds and set the post-acquisition start date
- `stats_espn_daily_2026.csv` — daily stats per player to accumulate post-add totals for R, HR, RBI, SB, OPS
- `stats_mlb_daily_2026.csv` — game-level box score data for pitching categories (K/9, QS, SVHD, ERA, WHIP) from the pickup date forward
- `rankings_espn_daily_2026.csv` — ownership % at pickup date as a proxy for how overlooked the player was when claimed

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

**Status:** `Not Started`

**Motivation:** Idea 15 identified *who* the best waiver pickups of 2026 were after the fact. This idea works backwards: given that ground truth, what could we have *known before* the acquisition date that predicted those players would be valuable? The goal is a set of prescriptive, threshold-based signals — concrete rules a manager can apply each week to identify the next Jordan Walker or Bryan Baker before someone else claims them.

**Idea:** For every pickup in `best_pickups_espn_2026.csv`, build a pre-pickup feature profile using the 7, 14, and 21 days of game logs *before* the acquisition date. Separate the top-quartile pickups (high composite z) from the bottom-quartile pickups (low composite z). Measure which pre-pickup metrics differ most significantly between the two groups. Then translate those differences into prescriptive thresholds: "if a player shows X in the prior 7 days AND Y, they are a strong add candidate."

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
1. Load `best_pickups_espn_2026.csv` to get the labeled set — label each pickup as top-quartile (composite z ≥ 75th percentile within player type) or bottom-quartile (composite z ≤ 25th percentile)
2. For each pickup, pull pre-pickup game logs from `stats_mlb_daily_2026.csv` and `stats_espn_daily_2026.csv` for the 7, 14, and 21 days before `acquisition_date`
3. Compute pre-pickup feature vectors per player: rolling OPS/ERA/K9/WHIP, games played rate, batting order slot distribution, ownership trend slope from `rankings_espn_daily_2026.csv`
4. For each feature, compute the mean and distribution for top-quartile vs bottom-quartile pickups; use a simple t-test or Mann-Whitney U to rank features by discriminative power
5. Translate the top features into threshold rules: find the cutoff value for each metric that maximizes separation between the two groups (similar to a single-feature decision boundary)
6. Combine the top 3–4 signals into a composite "add score" per signal combination — score = number of signals triggered
7. Back-test the signal rules against 2024 and 2025 activity + stat data to measure precision (what % of flagged players become top-quartile pickups) and recall (what % of top-quartile pickups were flagged in advance)
8. Report the final ruleset as concrete, actionable thresholds — e.g., "Batter with 7-day OPS ≥ .820, AB/G ≥ 3.5, ownership < 30%, and batting order slot ≤ 3 in 5+ of last 7 games: strong add"

**Data sources:**
- `data-lake/01_Bronze/fantasy_baseball/best_pickups_espn_2026.csv` — ground truth labels from idea 15 (top vs bottom pickup performers)
- `stats_mlb_daily_2026.csv` / `2025.csv` / `2024.csv` — pre-pickup game logs for feature construction
- `stats_espn_daily_2026.csv` / `2025.csv` / `2024.csv` — lineup slot, ownership context, fantasy points in the pre-pickup window
- `rankings_espn_daily_2026.csv` / `2025.csv` / `2024.csv` — ownership %, pct_change, ESPN rank trend before the pickup date
- `activity_espn_season_2026.csv` / prior seasons — pickup dates and which team made the claim (to reproduce the same analysis for 2024/2025)
- `lineups_mlb_batters_2026.csv` — batting order slot history in the pre-pickup window (batter signal only)

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
