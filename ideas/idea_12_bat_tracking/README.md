# Idea 12 — Bat Tracking & Statcast Metrics as Player Predictors

**Status:** In Progress (see [`../../ideas.md`](../../ideas.md) §12). Batting = same-season breakout finder + YoY carry-forward; pitching = same-season stuff-vs-results baseline (predictive pitching YoY deferred).

Full spec: [`PROMPT.md`](PROMPT.md). Report: [`../../reports/bat_tracking_2026.md`](../../reports/bat_tracking_2026.md).

## Scripts

| Script | Location | Role |
|---|---|---|
| `analyze_bat_tracking_mlb_2026.py` | **this folder** | The analysis: breakout finder, batting YoY, pitching baseline. Produces the `*_local_*` files below. |
| `fetch_statcast_savant_season.py` | **repo root** `fantasy_baseball/` | Collects Savant **season** leaderboards. Promoted to a first-class collector; runs as Step 8b of `/fantasy-collect-all-data` (weekly, self-gated). |
| `fetch_statcast_savant_games.py` | **repo root** `fantasy_baseball/` | Collects Savant **game-level** aggregates (batters + pitchers). Runs as Step 8a of `/fantasy-collect-all-data` (daily, incremental). |

> The fetchers live at the repo root (not here) because they are recurring data collectors wired into the collect-all-data workflow. This analysis only reads their season-level output today; the game-level files are collected for future rolling-window work (Ideas 10/16/17).

## Data-lake files (`data-lake/01_Bronze/fantasy_baseball/`)

All join to `player_map.csv` on **`mlbam_player_id`** (Savant `id`/`pitcher`/`batter` columns are MLBAM ids).

### Raw — season leaderboards · producer: `fetch_statcast_savant_season.py`
| File | Contents |
|---|---|
| `{2023-2026}_mlb_bat_tracking_season.csv` | One row per qualified batter per season. Carries Savant's **exact** squared-up/blast (the game files only approximate these). Consumed by the analysis. |
| `{2023-2026}_mlb_pitch_tracking_season.csv` | One row per pitcher per season: per-pitch-type velocity + spin. |

### Raw — game level · producer: `fetch_statcast_savant_games.py`
| File | Contents |
|---|---|
| `{2023-2026}_mlb_bat_tracking_games.csv` | One row per `(game_date, batter)`: bat speed, swing length, hard-swing %, exit velo, hard-hit %, barrels, HR, PA. For rolling windows. **Not yet consumed by the analysis.** |
| `{2023-2026}_mlb_pitch_tracking_games.csv` | One row per `(game_date, pitcher)`: fastball velo/spin, CSW%, K, HR allowed. For rolling windows. |

Coverage note: pitcher velo/spin and batter exit-velo/outcome columns are full 2023–2026. Batter **swing-tracking** (bat_speed/swing_length/hard-swing) is ~43% populated in 2023 (coverage began mid-season), ~95% in 2024, ~99% in 2025–26.

### Derived — producer: `analyze_bat_tracking_mlb_2026.py`
| File | Contents |
|---|---|
| `2026_local_bat_tracking_breakouts.csv` | 2026 batters: physical-profile vs output z-scores + gap (breakout / sell-high). |
| `2026_local_bat_tracking_yoy_batter.csv` | Bat-tracking metric → next-season HR/AVG/OPS carry-forward (2023→24, 2024→25, partial 25→26). |
| `2026_local_statcast_pitcher_stuff.csv` | 2026 pitchers: stuff (velo/spin) vs results (ERA/WHIP/K9), role-relative, with stuff-vs-results gap. |

## Run order
1. Collect (handled by `/fantasy-collect-all-data`, or `/fantasy-collect-statcast` standalone) → raw season + game files.
2. `python fantasy_baseball/ideas/idea_12_bat_tracking/analyze_bat_tracking_mlb_2026.py` → derived `*_local_*` files + `reports/bat_tracking_2026.md`.
