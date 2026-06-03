# Fantasy Baseball — File Directory

> Central reference for all files in the `fantasy_baseball/` repository.
> Last updated: 2026-05-01

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
| `collect_stats_espn_daily.py` | **Primary daily pipeline.** Collects per-player stats for all teams in the ESPN league for a given date range. Handles column expansion, deduplication, and incremental append. Used by the `fantasy-collect-daily-espn-stats` workflow. | ESPN API | `stats_espn_daily_{YEAR}.csv` |
| `fetch_stats_espn_daily.py` | Bulk historical stat fetch. Iterates all 195 scoring periods and saves a full-season CSV using `mp.fetch_league_matchup_data()`. | ESPN API | `stats_espn_daily_{YEAR}.csv` |
| `fetch_stats_mlb_boxscore.py` | Fetches per-game hitting and pitching stats via the boxscore endpoint (~15 requests/day vs ~1000). Includes bench players with `did_play=0` for play-frequency tracking. | MLB Stats API | `stats_mlb_boxscore_{SEASON}.csv` |
| `fetch_stats_mlb_daily.py` | **Archived** — superseded by `fetch_stats_mlb_boxscore.py`. Player-by-player game log fetcher (~1000 requests/day, no bench coverage). | MLB Stats API | `stats_mlb_daily_2026_archive.csv` |
| `fetch_stats_mlb_scrape.py` | Scrapes season-level hitting and pitching leaderboards from MLB.com. Saves dated snapshots with full stat lines. | MLB Stats API | `stats_mlb_season_hitting_{SEASON}_{DATE}.csv`, `stats_mlb_season_pitching_{SEASON}_{DATE}.csv` |
| `fetch_lineups_mlb_daily.py` | Scrapes today's MLB starting lineups via `mp.scrape_mlb_lineups()` and appends to the Bronze CSV with dedup. Used by the `fantasy-collect-mlb-lineups` workflow. | MLB.com | `lineups_mlb_batters_{YEAR}.csv` |
| `fetch_activity_espn_season.py` | Fetches ESPN league activity (adds, drops, trades, waivers) via `mp.get_recent_activity()`. Appends with dedup on `(date_epoch, player_id, action_id, team_id)`. Used by the `fantasy-collect-activity-data` workflow. | ESPN API | `activity_espn_season_{YEAR}.csv` |
| `fetch_draft_espn_season.py` | Fetches the league's draft results via `mp.get_draft_recap()`. | ESPN API | `draft_results_espn_{YEAR}.csv` |
| `fetch_rosters_espn_current.py` | Snapshots the current ESPN roster for all teams via `mp.get_league_rosters()`. | ESPN API | `roster_espn_season_{YEAR}.csv` |
| `fetch_scoreboard_espn_matchup.py` | Captures the current matchup scoreboard for all league matchups. | ESPN API | `scoreboard_espn_matchup_{YEAR}.csv` |
| `fetch_transactions_espn_season.py` | Fetches full-season transaction log via `mp.get_league_transactions()`. Uses year-swap trick for historical seasons. | ESPN API | `transactions_espn_season_{YEAR}.csv` |

---

## Data Processing (Transforms)

These scripts transform or enrich existing data lake CSVs.

| File | Description | Input CSV | Output CSV |
|---|---|---|---|
| `process_stats_espn_matchup.py` | Backfills the `matchup_period` column in the daily stats CSV by deriving a scoring-period-to-matchup-period mapping from league settings. | `stats_espn_daily_2025.csv` | `stats_espn_daily_2025.csv` (in-place update) |
| `generate_schedule_espn_matchup.py` | Generates a full scoring-period ↔ matchup-period ↔ calendar-date mapping CSV using league settings heuristics. | ESPN API (league settings) | `schedule_espn_matchup_{YEAR}.csv` |
| `process_dashboard_data.py` | Collects roster/free-agent snapshots daily, appends to a flat CSV, generates an HTML dashboard, and pushes to GitHub Pages. Supports `--dry-run` (uses existing CSV) and `--no-push` modes. | ESPN API or `stats_espn_daily_2025.csv` | `dashboard_snapshots.csv`, `17_Fantasy_Baseball_Dashboard.html` |

---

## Analysis Scripts

These scripts consume data lake CSVs and produce reports or stdout analysis.

| File | Description | Input Data | Output |
|---|---|---|---|
| `analyze_player_contributions.py` | **Roster evaluation.** For a target team, z-scores every player across 5x5 categories, flags non-contributors, and recommends free-agent replacements ranked by composite score (z + lineup order + start rate). | `stats_espn_daily_2026.csv`, `lineups_mlb_batters_2026.csv`, projection CSVs | `reports/player_contributions_{DATE}.md` |
| `analyze_team_scorecards.py` | League-wide team scorecards. Aggregates and ranks all 10 teams across 5x5 categories with per-day rates and grade tiers. | `stats_espn_daily_2026.csv` | stdout |
| `analyze_league_rosters.py` | Deep-dive league-wide roster management analysis: optimal evaluation window, roster patience (hold time), churn rate, team success correlation, and Mermaid visualizations. | `roster_history_2025.csv`, `stats_mlb_daily_2025.csv`, `player_map.csv` | markdown report |
| `analyze_quick_lineup_impact.py` | Evaluates whether ESPN's Quick Lineup feature costs teams stats by attributing bench placements (quick vs manual vs default) and measuring missed counting stats. | `activity_espn_season_2026.csv`, `stats_espn_daily_2026.csv` | stdout + `quick_lineup_bench_performances_2026.csv` |
| `generate_roster_recommendations.py` | Weekly checkpoint analysis: compares rolling 28-day z-score value of rostered players vs available free agents and flags missed opportunities. | `roster_history_{YEAR}.csv`, `stats_mlb_daily_{YEAR}.csv`, `player_map.csv` | `reports/roster_analysis_report_{YEAR}.md` |
---

## Trade Analysis (`trade_analysis/`)

Scripts for identifying and evaluating mutually beneficial trades.

| File | Description | Input Data | Output |
|---|---|---|---|
| `trade_analysis/analyze_trade_finder_espn_2026.py` | **Mutually beneficial trade finder.** Scans every team's roster, builds YTD and full-season projected category profiles, then enumerates all 1-for-1 same-type player swaps. Surfaces trades where both teams net-improve their H2H category rank count. Includes `balance_min` and `balance_diff` columns for fairness scoring. | `stats_espn_daily_2026.csv`, `player_batter_projections_2026.csv`, `player_pitcher_projections_2026.csv`, `activity_espn_season_2026.csv` | `analyze_trade_finder_espn_2026.csv` |
| `trade_analysis/generate_trade_report_espn_2026.py` | Human-readable stdout wrapper over the trade finder CSV. Prints formatted trade blocks with projected stats, per-category rank changes, and plain-English gain/loss summaries. Supports `--team TEAM` and `--top N` flags. | `analyze_trade_finder_espn_2026.csv` | stdout |
| `trade_analysis/generate_trade_summary_espn_2026.py` | Per-team markdown report. Groups all trades by team, splits into **Most Balanced** (sorted by min-gain fairness) and **Highest Impact** (top 2 by combined gain) sections. Top 5 balanced per team. | `analyze_trade_finder_espn_2026.csv` | `reports/trade_summary_espn_2026_{DATE}.md` |

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

Active workflows in `.agent/workflows/` that invoke these scripts:

| Workflow | Scripts Used |
|---|---|
| `fantasy-collect-daily-espn-stats` | `collect_stats_espn_daily.py` |
| `fantasy-collect-daily-mlb-stats` | `fetch_stats_mlb_boxscore.py` |
| `fantasy-collect-mlb-lineups` | `fetch_lineups_mlb_daily.py` |
| `fantasy-collect-activity-data` | `fetch_activity_espn_season.py` |
| `fantasy-collect-all-data` | Orchestrates all four collection workflows above |
| `fantasy-roster-analysis` | `analyze_player_contributions.py`, `analyze_team_scorecards.py` |
