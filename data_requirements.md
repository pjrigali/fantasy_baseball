# Better Approach: What Data You Need

League type: **Head-to-Head 5x5 Categories** (see `scoring.md` for full category definitions).
Primary data source: **ESPN API**. Rotowire scrape is used only where ESPN has no equivalent.

Status key: ✅ covered | ⚠️ partially covered | ❌ missing

---

## 1. Roster and league settings

Scoring categories and rules are static and documented in `scoring.md` — no need to fetch from ESPN dynamically.

| Data | Source | Status |
|---|---|---|
| Rostered players | ESPN API (`get_league_rosters`) | ✅ |
| Bench vs active slots | ESPN API (`lineupSlot` field) | ✅ |
| Position eligibility per player | ESPN API (`eligibleSlots` field) | ✅ |
| Pitcher role (SP vs RP) | ESPN API (`eligibleSlots` — SP/RP slots) | ✅ |
| Injury / rest / suspension status | ESPN API (`injuryStatus` field) | ✅ |

---

## 2. Schedule and availability

| Data | Source | Status |
|---|---|---|
| Whether the player's team plays that day | MLB.com scrape (`grab_mlb_sched`) | ✅ |
| Doubleheaders | MLB.com scrape (flag in schedule) | ⚠️ not explicitly flagged yet |
| Probable starters (is this SP pitching today) | Rotowire scrape (`get_daily_lineups`) | ✅ |
| Batting order position for hitters | Rotowire scrape (`batting_order` field) | ✅ |

Weather and postponement risk excluded — too unpredictable and low value for category decisions.

---

## 3. Player skill and recent usage

### Hitters

| Data | Source | Status |
|---|---|---|
| Season stats (R, HR, RBI, SB, OPS) | ESPN API game logs (`get_batter_game_logs`) | ✅ |
| Rolling-window stats (7/14/30 day) | Derived from ESPN game logs | ❌ needs `compute_rolling_stats()` |
| Stolen base attempt rate | Derived from game logs (SB + CS) | ⚠️ derivable, no helper yet |
| Recent playing time consistency | `analyze_roster_batters()` | ✅ |

Handedness and LHP/RHP splits excluded — marginal value in a 5x5 categories format where OPS is the only rate stat and decisions are made at the team-category level.

### Pitchers

| Data | Source | Status |
|---|---|---|
| Pitcher role (SP vs RP) | ESPN API roster (`eligibleSlots`) | ✅ |
| Is SP starting today | Rotowire scrape (`get_daily_lineups`) | ✅ |
| Season stats (K/9, ERA, WHIP, QS, SVHD) | ESPN API game logs (`get_pitcher_game_logs`) | ✅ |
| Rolling-window stats (7/14/30 day) | Derived from ESPN game logs | ❌ needs `compute_rolling_stats()` |
| Average IP per outing | Derived from game logs (`IP` field) | ⚠️ derivable, no helper yet |
| Pitch count trend | `P` field in ESPN game logs | ✅ |

---

## 4. Opponent and matchup context

### For hitters facing a pitcher

| Data | Source | Status |
|---|---|---|
| Opposing starting pitcher name | Rotowire scrape (`get_daily_lineups`) | ✅ |
| Opposing pitcher season stats (ERA, K/9, WHIP) | ESPN API game logs for that pitcher | ⚠️ data exists, no join helper yet |

Park factors and bullpen quality excluded — low signal for category-level weekly decisions.

### For pitchers facing a lineup

| Data | Source | Status |
|---|---|---|
| Opposing team season K rate and OPS | Aggregated from ESPN matchup data or game logs | ❌ needs `get_team_stats_by_team()` |
| Win/loss context | Low priority — skip for now | ❌ skip |

---

## 5. Projection target

This is a **categories league**, so the goal is not a single point estimate but an expected stat line contribution per category.

| Output | Approach | Status |
|---|---|---|
| Expected stats for today (R, HR, RBI, SB, OPS) | Rolling form + batting order + has a game | ❌ needs `project_player_day()` |
| Expected stats for today (K/9, QS, ERA, WHIP, SVHD) | Rolling form + is starting + opponent K rate | ❌ needs `project_player_day()` |
| Start / sit recommendation | Rank active roster by expected category contribution | ❌ downstream of projection |

---

## Summary: Functions to add to `mlb_processing.py`

1. `compute_rolling_stats(game_logs, windows=[7, 14, 30])` — aggregate ESPN game log data into rolling windows; works for both hitters (R, HR, RBI, SB, OPS) and pitchers (K/9, ERA, WHIP, IP, QS, SVHD)
2. `get_team_stats_by_team(matchup_data)` — aggregate team-level K rate and OPS from existing ESPN matchup data; used to rate pitcher matchup quality
3. `project_player_day(player, schedule, daily_lineup, rolling_stats)` — combine roster status, schedule, lineup position, and rolling form into a ranked daily expected category contribution
4. Extend `get_league_transactions()` to capture `'Moved'` message type — lineup moves come from the same ESPN communication endpoint already used; currently filtered out. Counting `'Moved'` events per team per scoring period enables the manual vs Quick Lineup heuristic (> 2 moves = Quick Lineup)
