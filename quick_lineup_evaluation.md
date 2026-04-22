# How to Measure Lineup Decision Quality

League type: **Head-to-Head 5x5 Categories**
Evaluation approach: **Retroactive, daily** — for each scoring period, measure the raw 5x5 stat contribution from benched players that was missed by the active lineup. Expressed as missed box score stats per category, not fantasy points.

---

## Data Requirements

### ESPN API connections needed

| Data | ESPN API call | Existing function |
|---|---|---|
| Who was started vs benched each scoring period | `fetch_league_matchup_data()` | ✅ |
| Actual stats produced per player per day | `fetch_league_matchup_data()` (`points` field per scoring period) | ✅ |
| Weekly category win/loss outcomes | `get_matchup_scoreboard()` | ✅ |
| Lineup activity log (manual vs Quick Lineup) | ESPN communication/activity endpoint | ❌ needs `get_lineup_activity()` |

### Manual vs Quick Lineup detection

ESPN activity data includes a `'Moved'` message type for lineup changes. This comes from the same communication endpoint already used by `get_league_transactions()` — that function currently filters `'Moved'` out and needs to be extended to capture it.

Detection heuristic: count `'Moved'` events per team per scoring period.
- **> 2 moves** on a given day → treat as **Quick Lineup** (ESPN auto-set moves many players at once)
- **≤ 2 moves** → treat as **manual** selection

This gives a simple, ESPN-native flag requiring no separate API call. The manual vs Quick Lineup label becomes a filter on top of all existing metrics.

---

## Daily Missed Stats Calculation (core method)

For each scoring period:
1. Pull active lineup and bench from `fetch_league_matchup_data()`
2. Pull actual stats produced by every rostered player that day (same source)
3. For each bench player who produced stats, record what was missed per category:
   - Hitters: R, HR, RBI, SB, OPS
   - Pitchers: K/9, ERA, WHIP, QS, SVHD
4. For each active slot, identify if a bench player would have contributed more in any category

This gives a daily "missed box score" — a raw stat delta per category, per day.

---

## 1. Daily missed stats test

Primary evaluation. For each scoring period, compare active lineup output vs what benched players actually produced.

Metrics:
- missed R, HR, RBI, SB per day (counting stats — direct sum)
- missed OPS per day (rate stat — average of benched eligible hitters who played)
- missed K/9, ERA, WHIP per day (rate stats — average of benched eligible pitchers who started)
- missed QS, SVHD per day (counting stats)

Aggregate over a week to see if daily bench production would have flipped any categories.

---

## 2. Benchmark comparison test

Compare actual lineup decisions against two baselines using the same daily missed stats method.

Baselines:
- **Always play if has a game**: start any rostered player whose team plays that day; measure how much this baseline would have missed
- **Rolling stats rank**: start players ranked by 14-day rolling stats in each category; measure missed stats vs this ordering

Metrics:
- average daily missed stats per category vs each baseline
- which baseline leaves less on the bench

---

## 3. Calibration test

For each start/sit decision (chosen player vs benched alternative), track whether the chosen player outperformed the benched player in the categories relevant to their role.

For hitters: R, HR, RBI, SB, OPS only.
For pitchers: K/9, ERA, WHIP, QS, SVHD only.
Cross-category comparisons are not evaluated (1 HR ≠ 1 SB).

Metrics:
- pairwise win rate per category (chosen player produced more than benched player)
- split by decision type: manual decisions vs Quick Lineup decisions

---

## 4. Slot efficiency test

Evaluate whether players were placed in the right slots relative to their category strengths on that day.

Example: a high-SB hitter placed in UTIL while a low-SB hitter plays OF wastes SB output.

Metrics:
- daily missed stats attributable to slot misassignment vs player selection
- % of days with avoidable slot inefficiency

---

## 5. Categories impact test

Roll up daily missed stats to the weekly matchup level to measure whether bench production would have changed category outcomes.

Metrics:
- weeks where cumulative missed stats in a category exceeded the margin of loss in that category (avoidable loss)
- category win rate split: manual decision weeks vs Quick Lineup weeks
- which categories are most frequently left on the bench

---

## 6. Robustness test

Test evaluation across conditions where lineup information was incomplete at decision time.

Scenarios:
- doubleheaders (player produces double the typical output)
- uncertain lineups (batting order not yet posted when lineup was locked)
- tight matchups (category decided by small margin at end of week)

Metrics:
- daily missed stats by scenario type
- does Quick Lineup or manual perform better under uncertainty

---

## Core metrics summary

| Metric | Description |
|---|---|
| Daily missed stats | Raw 5x5 stat delta between bench and active lineup per scoring period |
| Avoidable category loss | Weeks where bench production exceeded the margin of loss in a category |
| Calibration accuracy | % of start/sit decisions where chosen player led the benched alternative per category |
| Slot efficiency loss | Missed stats attributable to wrong slot assignment vs wrong player selection |
| Manual vs Quick Lineup delta | Difference in missed stats between manually set and auto-set lineups |
