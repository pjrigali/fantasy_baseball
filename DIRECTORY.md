# Fantasy Baseball — File Directory

> Central reference for all files in the `fantasy_baseball/` repository.
> Last updated: 2026-06-14

---

## Core Module

| File | Description | Outputs |
|---|---|---|
| `mlb_processing.py` | **Central utility library.** All shared helper functions live here: ESPN API wrappers, MLB Stats API scrapers, data fetching, name normalization, player lineup scraping, z-score calculations, streak detection, and the portable `DATA_PATH` resolver. Imported as `mp` by every other script. | N/A (library) |
| `__init__.py` | Package init — allows `from fantasy_baseball import mlb_processing`. | N/A |
| `config.ini` | ESPN API credentials (league ID, espn_s2, swid). **Gitignored.** | N/A |

---

## Data Collection (Pipelines)

These scripts fetch raw data from ESPN or MLB APIs and write to the Bronze data lake.

| File | Description | Data Source | Output CSV |
|---|---|---|---|
| `collect_stats_espn_daily.py` | **Primary daily pipeline.** Collects per-player stats for all teams in the ESPN league for a given date range. Handles column expansion, deduplication, and incremental append. Used by the `fantasy-collect-daily-espn-stats` workflow. | ESPN API | `{YEAR}_espn_stats_daily.csv` |
| `fetch_stats_espn_daily.py` | Bulk historical stat fetch. Iterates all 195 scoring periods and saves a full-season CSV using `mp.fetch_league_matchup_data()`. | ESPN API | `{YEAR}_espn_stats_daily.csv` |
| `fetch_stats_mlb_boxscore.py` | Fetches per-game hitting and pitching stats via the boxscore endpoint (~15 requests/day vs ~1000). Includes bench players with `did_play=0` for play-frequency tracking. | MLB Stats API | `{SEASON}_mlb_stats_boxscore.csv` |
| `fetch_stats_mlb_daily.py` | **Archived** — superseded by `fetch_stats_mlb_boxscore.py`. Player-by-player game log fetcher (~1000 requests/day, no bench coverage). | MLB Stats API | `2026_mlb_stats_daily_archive.csv` |
| `fetch_stats_mlb_scrape.py` | Scrapes season-level hitting and pitching leaderboards from MLB.com. Saves dated snapshots with full stat lines. | MLB Stats API | `stats_mlb_season_hitting_{SEASON}_{DATE}.csv`, `stats_mlb_season_pitching_{SEASON}_{DATE}.csv` |
| `fetch_lineups_mlb_daily.py` | Scrapes today's MLB starting lineups via `mp.scrape_mlb_lineups()` and appends to the Bronze CSV with dedup. Used by the `fantasy-collect-mlb-lineups` workflow. | MLB.com | `{YEAR}_mlb_lineups_batters.csv` |
| `fetch_activity_espn_season.py` | Fetches ESPN league activity (adds, drops, trades, waivers) via `mp.get_recent_activity()`. Appends with dedup on `(date_epoch, player_id, action_id, team_id)`. Used by the `fantasy-collect-activity-data` workflow. | ESPN API | `{YEAR}_espn_activity_season.csv` |
| `fetch_draft_espn_season.py` | Fetches the league's draft results via `mp.get_draft_recap()`. | ESPN API | `{YEAR}_espn_draft_results.csv` |
| `fetch_rosters_espn_current.py` | Snapshots the current ESPN roster for all teams via `mp.get_league_rosters()`. | ESPN API | `{YEAR}_espn_roster_season.csv` |
| `fetch_scoreboard_espn_matchup.py` | Captures the current matchup scoreboard for all league matchups. | ESPN API | `{YEAR}_espn_scoreboard_matchup.csv` |
| `fetch_transactions_espn_season.py` | Fetches full-season transaction log via `mp.get_league_transactions()`. Uses year-swap trick for historical seasons. | ESPN API | `transactions_espn_season_{YEAR}.csv` |

---

## Data Processing (Transforms)

These scripts transform or enrich existing data lake CSVs.

| File | Description | Input CSV | Output CSV |
|---|---|---|---|
| `process_stats_espn_matchup.py` | Backfills the `matchup_period` column in the daily stats CSV by deriving a scoring-period-to-matchup-period mapping from league settings. | `2025_espn_stats_daily.csv` | `2025_espn_stats_daily.csv` (in-place update) |
| `generate_schedule_espn_matchup.py` | Generates a full scoring-period ↔ matchup-period ↔ calendar-date mapping CSV using league settings heuristics. | ESPN API (league settings) | `{YEAR}_espn_schedule_matchup.csv` |
| `process_dashboard_data.py` | Collects roster/free-agent snapshots daily, appends to a flat CSV, generates an HTML dashboard, and pushes to GitHub Pages. Supports `--dry-run` (uses existing CSV) and `--no-push` modes. | ESPN API or `2025_espn_stats_daily.csv` | `dashboard_snapshots.csv`, `17_Fantasy_Baseball_Dashboard.html` |

---

## Analysis Scripts

These scripts consume data lake CSVs and produce reports or stdout analysis.

| File | Description | Input Data | Output |
|---|---|---|---|
| `analyze_player_contributions.py` | **Roster evaluation.** For a target team, z-scores every player across 5x5 categories, flags non-contributors, and recommends free-agent replacements ranked by composite score (z + lineup order + start rate). | `2026_espn_stats_daily.csv`, `2026_mlb_lineups_batters.csv`, projection CSVs | `reports/player_contributions_{DATE}.md` |
| `analyze_team_scorecards.py` | League-wide team scorecards. Aggregates and ranks all 10 teams across 5x5 categories with per-day rates and grade tiers. | `2026_espn_stats_daily.csv` | stdout |
| `analyze_league_rosters.py` | Deep-dive league-wide roster management analysis: optimal evaluation window, roster patience (hold time), churn rate, team success correlation, and Mermaid visualizations. | `2025_espn_roster_history.csv`, `2025_mlb_stats_daily.csv`, `player_map.csv` | markdown report |
| `analyze_quick_lineup_impact.py` | Evaluates whether ESPN's Quick Lineup feature costs teams stats by attributing bench placements (quick vs manual vs default) and measuring missed counting stats. | `2026_espn_activity_season.csv`, `2026_espn_stats_daily.csv` | stdout + `2026_local_quick_lineup_bench.csv` |
| `generate_roster_recommendations.py` | Weekly checkpoint analysis: compares rolling 28-day z-score value of rostered players vs available free agents and flags missed opportunities. | `{YEAR}_espn_roster_history.csv`, `{YEAR}_mlb_stats_daily.csv`, `player_map.csv` | `reports/roster_analysis_report_{YEAR}.md` |
| `watch_waiver_signals_espn.py` | **Daily waiver wire watchlist.** Scans all players with `pct_owned < 80%` from the latest rankings snapshot, builds 7d/14d feature vectors, and scores against the Idea 16 signal thresholds. Appends all players with ≥ 1 signal firing. Run as Step 7 of `fantasy-collect-all-data`. Accepts `--max-owned`, `--dry-run`. | `{YEAR}_espn_rankings_daily.csv`, `{YEAR}_mlb_stats_boxscore.csv`, `{YEAR}_mlb_lineups_batters.csv`, `player_lookup.csv` | `{YEAR}_espn_waiver_watchlist.csv` |
---

## Ideas & Investigations (`ideas/`)

Structured investigations into specific research topics (linked to `ideas.md`).

### Idea 11: Mutually Beneficial Trade Finder (`ideas/idea_11_trade_finder/`)

Scripts for identifying and evaluating mutually beneficial trades.

| File | Description | Input Data | Output |
|---|---|---|---|
| `ideas/idea_11_trade_finder/analyze_trade_finder_espn_2026.py` | **Mutually beneficial trade finder.** Scans every team's roster, builds YTD and full-season projected category profiles, then enumerates all 1-for-1 same-type player swaps. Surfaces trades where both teams net-improve their H2H category rank count. Includes `balance_min` and `balance_diff` columns for fairness scoring. | `2026_espn_stats_daily.csv`, `2026_ext_projections_batter.csv`, `2026_ext_projections_pitcher.csv`, `2026_espn_activity_season.csv` | `2026_local_trade_finder.csv` |
| `ideas/idea_11_trade_finder/generate_trade_report_espn_2026.py` | Human-readable stdout wrapper over the trade finder CSV. Prints formatted trade blocks with projected stats, per-category rank changes, and plain-English gain/loss summaries. Supports `--team TEAM` and `--top N` flags. | `2026_local_trade_finder.csv` | stdout |
| `ideas/idea_11_trade_finder/generate_trade_summary_espn_2026.py` | Per-team markdown report. Groups all trades by team, splits into **Most Balanced** (sorted by min-gain fairness) and **Highest Impact** (top 2 by combined gain) sections. Top 5 balanced per team. | `2026_local_trade_finder.csv` | `reports/trade_summary_espn_2026_{DATE}.md` |

### Idea 15: Best Waiver Pickups (`ideas/idea_15_best_pickups/`)

Identifies the highest-value waiver pickups by aggregating game stats across each player's held tenure and z-scoring across 5×5 categories into a composite score.

| File | Description | Input Data | Output |
|---|---|---|---|
| `ideas/idea_15_best_pickups/analyze_best_pickups_espn_2026.py` | **2026 best-pickups engine.** Uses `2026_espn_activity_season.csv` for real pickup dates; aggregates MLB archive stats over each player's held tenure; z-scores R, HR, RBI, SB, OPS (batters) and K/9, QS, SVHD, ERA, WHIP (pitchers) into a composite. | `2026_espn_activity_season.csv`, `2026_mlb_stats_daily_archive.csv`, `player_lookup.csv` | `2026_espn_best_pickups.csv` |
---

### Idea 16: Waiver Wire Signal Detection (`ideas/idea_16_waiver_signals/`)

Pre-pickup signal analysis: which rolling stats, ownership trends, and batting-order features predict top-quartile waiver pickups.

| File | Description | Input Data | Output |
|---|---|---|---|
| `ideas/idea_16_waiver_signals/analyze_best_pickups_espn_2025.py` | **2025 best-pickups engine (cross-year prerequisite).** No activity CSV available for 2025; uses first-appearance detection from `2025_espn_stats_daily.csv` (any player appearing at scoring_period > 1 is treated as a waiver pickup). Converts scoring periods to calendar dates via `2025_espn_schedule_matchup.csv`. Run this first to produce `2025_espn_best_pickups.csv` before running the signal detector. | `2025_espn_stats_daily.csv`, `2025_espn_schedule_matchup.csv` | `2025_espn_best_pickups.csv` |
| `ideas/idea_16_waiver_signals/analyze_waiver_signals_espn_2026.py` | **Pre-pickup signal detector.** Labels top/bottom quartile pickups from idea 15 ground truth, builds 7-day and 14-day rolling feature vectors (OPS, K/9, ERA, WHIP, ownership trend, batting order slot), ranks features by Mann-Whitney rank-biserial correlation, and derives F1-optimal threshold rules per player type. Includes a cross-year validation section comparing 2026 r values against 2025 (game-log features only). | `2026_espn_best_pickups.csv`, `2026_mlb_stats_daily_archive.csv`, `2026_espn_rankings_daily.csv`, `2026_mlb_lineups_batters.csv`, `player_lookup.csv`, `2025_espn_best_pickups.csv` (optional), `2025_mlb_stats_daily.csv` (optional) | `reports/waiver_signals_2026.md` |

---

### Idea 14: Player Injury Data Analysis (`ideas/idea_14_injury_analysis/`)

Scripts for fetching and analyzing Injured List (IL) stint histories and roster impact.

| File | Description | Input Data | Output |
|---|---|---|---|
| `ideas/idea_14_injury_analysis/fetch_stats_mlb_transactions.py` | **MLB transactions crawler.** Queries `statsapi.mlb.com/api/v1/transactions` for player status changes (IL placements/activations) for a given year. | MLB Stats API | `{YEAR}_mlb_transactions_season.csv` |
| `ideas/idea_14_injury_analysis/analyze_stats_espn_injuries.py` | **Injury analysis engine.** Reconstructs player IL stints, categorizes injuries, and joins with daily ESPN roster stats to calculate positional frequency, duration, fantasy team roster drag, and manager reaction time. | `{YEAR}_mlb_transactions_season.csv`, `{YEAR}_espn_stats_daily.csv`, `player_map.csv` | `reports/injury_analysis_report.md` |
| `ideas/idea_14_injury_analysis/generate_detailed_injury_report.py` | **Detailed duration reporting.** Computes recovery stats for completed IL stints broken down by injury category, estimated day category, position, and MLB team. | `{YEAR}_mlb_transactions_season.csv`, `player_map.csv`, `{YEAR}_espn_stats_daily.csv` | `reports/detailed_injury_duration_report.md` |
---

## Notebooks

| File | Description |
|---|---|
| `analyze_rookies.ipynb` | Evaluates MLB rookie performance across 5x5 categories using daily game logs and ESPN age calculations. |
| `analyze_roster_churn.ipynb` | Determines the optimal evaluation window for roster decisions and identifies missed opportunities for Team PJR. Produces the 28-day window finding used across analysis scripts. |
| `batting_order_analysis.ipynb` | Identifies where rostered batters hit in their real MLB lineups (batting order position trends). |
| `regression_to_mean.ipynb` | Tracks how each batter's rolling 30-game Daily_Value drifts above and below their season-long mean; identifies hot/cold streaks and regression patterns. |
| `draft_strategy_2026.ipynb` | Pre-draft strategy notebook: category rankings, position tiers, ADP analysis, and draft board for the 2026 season. **Gitignored.** |

---

## Player Name Resolution

ESPN data uses plain-ASCII names (e.g. "Andres Munoz"); the MLB stats archive uses UTF-8 accented names (e.g. "Andrés Muñoz"). Use the lookup infrastructure below to translate between them — never do raw string matching against the archive.

| File | Description | Input | Output |
|---|---|---|---|
| `generate_player_lookup.py` | Builds the base player lookup by cross-referencing `player_map.csv` against `2026_mlb_stats_daily_archive.csv` using accent-stripped fuzzy matching. Handles Jr./Sr. suffixes. Run first when refreshing. | `player_map.csv`, `2026_mlb_stats_daily_archive.csv` | `player_lookup.csv` |
| `crosscheck_player_lookup.py` | Enriches `player_lookup.csv` against all MLB stats files in the data-lake (2023–2026 daily, boxscore, hitting, pitching). Adds archive-only players not in `player_map.csv`. Run second after `generate_player_lookup.py`. | All `stats_mlb_*` and `mlb_hitting/pitching_*` CSVs | `player_lookup.csv` (updated in-place) |
| `player_lookup_utils.py` | Importable helpers for name resolution. Load once per process. | `player_lookup.csv` | N/A (library) |

**`player_lookup.csv`** lives at `data-lake/01_Bronze/fantasy_baseball/player_lookup.csv`. Columns: `espn_player_id, espn_name, archive_name, b_or_p, statcast_player_id`. ~2,200 rows covering all players seen across 2023–2026 stats files.

**Usage:**
```python
from fantasy_baseball.player_lookup_utils import get_archive_name, get_b_or_p
archive_name = get_archive_name("Andres Munoz")  # -> "Andrés Muñoz"
```

**Data quality note — Aroldis Chapman:** Chapman appears as `b_or_p = "batter"` in `player_lookup.csv` and `2026_local_keepers_performance.csv` (a data artifact from the archive containing zeroed batter rows for him). He is a pitcher. Always filter `b_or_p == "pitcher"` when querying his archive stats. If regenerating the lookup, fix the dedup logic in `generate_player_lookup.py` to prefer pitcher rows when both types exist for the same player.

---

## Documentation

| File | Description |
|---|---|
| `README.md` | Project overview and setup instructions. |
| `DIRECTORY.md` | This file. Central reference for all files in the repo. |
| `scoring.md` | League scoring rules: H2H 5x5 categories — R, HR, RBI, SB, OPS (batting) and K/9, QS, SVHD, ERA, WHIP (pitching). |
| `data_requirements.md` | Data inventory and gap analysis: documents what data is needed, where it comes from, and what helper functions still need to be built. |

---

## Generated / Gitignored

These files are produced by analysis scripts and excluded from version control.

| Location | Contents |
|---|---|
| `reports/` | Markdown reports and PNG charts generated by analysis scripts. **Gitignored.** |
| `*.png` | Chart images from notebooks and test scripts. **Gitignored.** |
| `config.ini` | API credentials. **Gitignored.** |
| `archive/` | Retired scripts and notebooks. **Gitignored.** |
| `dashboard_template.html` | HTML template for the GitHub Pages dashboard. **Gitignored.** |

---

## Archive (`archive/`)

Retired or one-off scripts moved out of the root for cleanliness.

| File | Original Purpose |
|---|---|
| `_ramp_test.py` | Experimental ramp-up event study for player performance after activation. |
| `_streak_test.py` | Experimental hot/cold streak detection and survival analysis. |
| `_run_mlb_daily_backfill.py` | One-off backfill of MLB Stats API game logs (superseded by `fetch_stats_mlb_daily.py`). |
| `run_ts_analysis.py` | One-off time series analysis experiment using pandas. |
| `evaluate_roster_2026.py` | Early-season roster evaluation (superseded by `analyze_player_contributions.py`). |
| `league_data.py` | Legacy league data helpers (superseded by `mlb_processing.py`). |
| `batters.ipynb`, `pitchers.ipynb`, `bb.ipynb` | Early exploratory notebooks from initial development. |
| `box_scores.ipynb` | Box score parsing experiments. |
| `espn_helper.ipynb` | ESPN API exploration notebook. |
| `lineups.ipynb` | Lineup scraping prototype. |
| `SB.ipynb` | Stolen base analysis prototype. |
| `player_stat_leaders_espn.ipynb` | ESPN leaderboard scraping prototype. |
| `notebook_summary.md` | Summary of archived notebooks. |

---

## Workflow Reference

Active workflows in `agent/workflows/` that invoke these scripts:

| Workflow | Scripts Used |
|---|---|
| `fantasy-collect-daily-espn-stats` | `collect_stats_espn_daily.py` |
| `fantasy-collect-daily-mlb-stats` | `fetch_stats_mlb_boxscore.py` |
| `fantasy-collect-mlb-lineups` | `fetch_lineups_mlb_daily.py` |
| `fantasy-collect-activity-data` | `fetch_activity_espn_season.py` |
| `fantasy-collect-all-data` | Orchestrates all four collection workflows above |
| `fantasy-roster-analysis` | `analyze_player_contributions.py`, `analyze_team_scorecards.py` |
