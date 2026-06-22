# Analysis Prompt — Idea 12: Bat Tracking & Statcast Metrics as Player Predictors

> Execution-ready prompt for the Idea 12 analysis. Read this top to bottom before writing any code. See [`../../ideas.md`](../../ideas.md) §12 for the original idea.

---

## CRITICAL CONTEXT — Read First: The Data Window Reframes the Idea

The original idea text (ideas.md §12) assumes Statcast bat-tracking data exists "2020–present" and frames the whole analysis as a **year-over-year carry-forward regression** (metric in year N → fantasy outcome in year N+1). **That premise is wrong for the batting side and must be corrected before any code is written.**

- **MLB Statcast *bat tracking* (swing speed, squared-up %, blast rate, swing length) is available from 2023 onward** — verified live against the Savant leaderboard: 2020–2022 return 0 rows; 2023 (221), 2024 (214), 2025 (226) are full seasons with real `avg_bat_speed` values; 2026 (212) is in progress (current date 2026-06-22). (Hawk-Eye tracked swings in 2023 even though the metrics were productized publicly in 2024.) That yields **two clean full-season YoY pairs (2023→2024 and 2024→2025)** plus a partial 2025→2026 — modest but genuinely testable, not a single pair.
- **MLB Statcast *pitching* / pitch tracking (velocity, spin rate, movement) goes back to 2015; pulled for 2023–2026.** **Decision (from user):** the pitching side is scoped to a **same-season baseline** this round — establish how fastball stuff (velocity, spin) relates to results (ERA/WHIP/K9) *within 2026* before attempting prediction. The predictive YoY version is a deliberate **later step**, not part of this build.

**Decision (locked, from user):** The **same-season breakout finder** is the **primary** deliverable — *which current (2026) hitters have elite bat-tracking physical profiles but lagging traditional / fantasy-category stats* are the regression-to-the-mean buy-low / breakout candidates on our rosters and the waiver wire **right now**. The batting **YoY carry-forward** (2023→2024, 2024→2025, + partial 2025→2026) is a genuine **co-deliverable** — two full pairs is enough to test whether bat tracking carries forward, reported with an honest "modest sample (2 pairs)" caveat rather than dismissed. The pitching side uses the full multi-year YoY framing.

---

## Objective

1. **Acquire** multi-year Statcast bat-tracking metrics (batters, 2024–2026) and pitch-tracking/Statcast metrics (pitchers, 2015–2026 as available) from Baseball Savant into the Bronze layer, keyed to our canonical player identity.
2. **Batting (same-season, primary deliverable):** identify 2026 hitters whose bat-tracking profile (swing speed, squared-up %, blast rate, etc.) is elite relative to the population but whose traditional / fantasy-category output (HR, AVG/OBP/SLG→OPS, SB context) lags — flag them as breakout / buy-low candidates, cross-referenced against ESPN ownership to surface still-claimable names.
3. **Batting (YoY, co-deliverable):** run the 2023→2024 and 2024→2025 carry-forward correlations (+ partial 2025→2026) to test which bat-tracking metrics predict next-season fantasy-relevant outcomes, favoring metrics that hold across both pairs. Report with a "modest sample (2 pairs)" caveat.
4. **Pitching (same-season baseline, secondary):** within 2026, correlate fastball velocity/spin against ERA/WHIP/K9, and build a "stuff vs results" gap list (good stuff + lagging results = buy-low; producing on modest stuff = sustainability watch), split SP/RP with role-relative z-scores. Predictive YoY deferred to a later step.

---

## Scope & Data-Availability Matrix

| Side | Source metrics | Seasons available | Framing |
|------|----------------|-------------------|---------|
| Batting | Bat tracking (verified live cols): `avg_bat_speed`, `hard_swing_rate`, `squared_up_per_bat_contact`, `squared_up_per_swing`, `blast_per_bat_contact`, `blast_per_swing`, `swing_length`, `whiff_per_swing`, `batter_run_value`, `percent_swings_competitive`, `contact` | 2023, 2024, 2025 (full) + 2026 (partial); 2020–22 empty | **Same-season breakout finder (primary)** + 2023→2024 & 2024→2025 YoY (co-deliverable, 2-pair caveat) |
| Pitching | Statcast pitch arsenals: per-pitch-type velocity (`ff_avg_speed`, `si_avg_speed`, …) and spin (`ff_avg_spin`, …), `pitcher`=MLBAM id | pulled 2023–2026; **only 2026 used this round** | **Same-season stuff↔results baseline (secondary); YoY deferred** |

Batting spans 2023–2026 (two full YoY pairs + partial). Pitching uses 2026 only for the baseline this round (the 2023–2025 pulls are on disk, ready for the deferred predictive step).

---

## Data Sources

### To be fetched — Baseball Savant (new to the data lake; nothing Statcast exists locally yet)

Savant leaderboards expose a CSV export. **Build step 1 is to verify the exact endpoint and query params** (open the leaderboard, trigger "Download CSV", capture the request URL) before writing the parser — do not hard-code an unverified URL.

- **Bat tracking:** verified working — `https://baseballsavant.mlb.com/leaderboard/bat-tracking?attempts=50&minSwings=q&minGroupSwings=1&seasonStart={Y}&seasonEnd={Y}&type=batter&sort=4&sortDir=desc&csv=true`. Decode with `utf-8-sig` (leading BOM on the first column). `id` = MLBAM id, `name` = "Last, First". Pull one CSV per season **2023, 2024, 2025, 2026**. (`minSwings=q` = qualified.)
- **Pitching Statcast:** verified working — `pitch-arsenals` gives one row per pitcher with per-pitch-type velocity and spin. Velo: `https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?year={Y}&min=100&type=avg_speed&hand=&csv=true`; spin: same with `type=avg_spin`. `pitcher` = MLBAM id; `last_name, first_name` = name. Pull **2023, 2024, 2025, 2026**; merge the velo and spin pulls per pitcher-season into one row.
- **Fetch mechanics (obey CLAUDE.md):** use `urllib` (stdlib) to GET each season's CSV; parse with `csv.DictReader` into a list of dicts; **no `pandas` in the committed fetch script**, and **no `pybaseball`** (it pulls pandas as a hard dependency). Add a polite delay between requests and a descriptive User-Agent. If a season's export 404s or schema-drifts, log it and continue — do not abort the whole pull.
- **Savant player id:** Savant rows carry the MLBAM player id (often `player_id`). This is the join key.

### Existing local files — `data-lake/01_Bronze/fantasy_baseball/`

- **`player_map.csv`** — canonical identity, single source of truth. Has **`mlbam_player_id`** (== Savant id), `espn_player_id`, `mlb_name`, `espn_name`, `normalized_name`, `b_or_p`, `primary_position`, `last_seen_year`. **Join Savant → our universe on `mlbam_player_id`.** Fall back to `normalized_name` only for unmatched rows, and log the unmatched count.
- **MLB game logs (prediction targets / traditional-stat side):** `2023_mlb_stats_daily.csv`, `2024_mlb_stats_daily.csv`, `2025_mlb_stats_daily.csv` (schema: `playerName`/`playerId`/`b_or_p`; batting `AB,H,2B,3B,HR,R,RBI,SB,CS,B_BB,HBP,SF,SO,TB`; pitching `OUTS,ER,K,P_BB,P_H,P_HR,P_R,QS,SV,HLD,SVHD,W,L,GS`), and **`2026_mlb_stats_boxscore.csv`** / `2026_mlb_stats_daily_archive.csv` (same stats, identity renamed to `player_id`/`player_name`, adds `did_play`; **note there is no `2026_mlb_stats_daily.csv`**). Aggregate daily → per-player season totals, recomputing rate stats (OPS via OBP+SLG, ERA, WHIP, K/9) from **summed components**, never averaging averages. Apply min-sample filters (state them; e.g. batters ≥ ~100 AB for a full-season profile, pitchers ≥ ~30 IP).
- **`2026_espn_rankings_daily.csv`** — market overlay: `pct_owned`, `pct_change`, `avg_draft_position`, `position_rank`. Use to (a) flag breakout candidates that are still low-owned / claimable, and (b) quantify the gap between physical profile and market valuation.
- **`2026_espn_stats_daily.csv`** — overlay only, to map breakout candidates to fantasy `team_name` / `injury_status` / `lineup_slot`. Do **not** compute category math from it.

---

## Analytical Approach

### 0. Fetch & persist (build step 1)
- Verify Savant CSV endpoints, fetch per-season files, parse with `csv.DictReader`, harmonize column names across seasons (Savant occasionally renames columns year to year — map to a stable internal schema), tag each row with `season`.
- Persist raw pulls to Bronze under convention: `2023_mlb_bat_tracking_season.csv` … `2026_mlb_bat_tracking_season.csv`, and `{YEAR}_mlb_pitch_tracking_season.csv` per pitching season. (`mlb` source = MLB/Savant; Category `bat_tracking` / `pitch_tracking`; Granularity `season`.) Log the pull to `data-lake/00_Logs/fantasy_baseball/`.

### 1. Join to identity & traditional stats
- Map every Savant row to `mlbam_player_id` via `player_map.csv`; attach season-aggregated traditional stats from the MLB game logs for the same player-season. Report match rate and list notable unmatched players.

### 2. Batting — same-season breakout finder (PRIMARY)
- For **2026**, standardize (z-score) each bat-tracking metric across the qualified-batter population.
- Standardize the **outcome** side too: traditional power/contact output (HR rate, SLG, OPS, barrel-equivalent from blast/squared-up, AVG).
- Compute a **physical-profile score** (composite z of the predictive bat-tracking metrics — weight by whichever metrics the YoY/established literature flags strongest; default equal-weight if YoY is too thin) and an **output score** (composite z of current traditional stats).
- **Breakout candidate = high physical-profile score, low output score** (large positive `physical − output` gap). Rank these. The opposite quadrant (high output, weak physical profile) = regression-*down* / sell-high watch.
- Overlay ownership: flag breakout candidates with `pct_owned` below a stated threshold (still claimable) and note which are on our roster / a league roster vs free agents.

### 3. Batting — YoY carry-forward (CO-DELIVERABLE)
- Build matched player sets for **2023→2024 and 2024→2025** (qualified both years), plus 2025→2026 as a partial-season check. For each bat-tracking metric in year N, correlate against year-N+1 fantasy-relevant outcomes (HR, AVG, OPS). Report Pearson + Spearman and R², and whether a metric's carry-forward is **consistent across both full pairs** (consistency across the two pairs is the robustness signal).
- **State the caveat plainly:** two full-season pairs (+ one partial) — modest sample; treat coefficients as directional, and prefer metrics that hold across both pairs over any single-pair standout. The same-season breakout score (§2) may weight metrics by their cross-pair carry-forward strength if that strength is stable; otherwise default to equal-weight.

### 4. Pitching — same-season baseline (SECONDARY)
- For 2026 (≥20 IP, tracked fastball), correlate primary-fastball velocity/spin (prefer 4-seam `ff_`, else sinker `si_`) against same-season ERA, WHIP, K/9 — the baseline relationship table.
- Build stuff-vs-results gaps: stuff = mean z(velo, spin); results = mean of z(K9), −z(ERA), −z(WHIP); gap = stuff − results. **Z-score within role (SP vs RP separately)** and present SP/RP lists separately — pooling floods every list with harder-throwing relievers, and RP small-IP ERAs are noisier.
- Infer SP/RP role from GS vs actual appearances (rows with OUTS>0); the daily `G` column over-counts (it is 1 on non-pitching roster-days).
- Predictive YoY (year N → N+1) is deferred; the 2023–2025 arsenal pulls are already in Bronze for that later step.

### 5. Honesty pass
- Every predictive claim states its sample size and season span. The batting YoY section is labeled preliminary throughout. The report's lede is the **2026 batting breakout list**, with the pitching YoY ranking as the methodologically stronger companion.

---

## Questions the Analysis Must Answer

1. Which 2026 hitters have elite bat-tracking profiles but lagging traditional/fantasy stats (breakout / buy-low candidates), and which of those are still low-owned / claimable?
2. Which bat-tracking metrics show carry-forward into next-season HR/AVG/OPS across the two full pairs (2023→2024, 2024→2025) — and which hold consistently vs. appear in only one pair?
3. On the pitching side (2026 baseline), how does fastball velocity/spin relate to same-season ERA/WHIP/K9, and which pitchers show a stuff-vs-results gap (buy-low or sustainability watch), split SP/RP?
4. Which current-roster players (ours and league-wide) have elite physical profiles suggesting an upward correction, and which have weak profiles suggesting their current output is unsustainable (sell-high)?
5. Are bat-tracking metrics more stable / population-discriminating than traditional rate stats in-season (a proxy for "more reliable signal"), given we can't fully test YoY?

---

## Deliverables

1. **Fetch script:** `fantasy_baseball/fetch_statcast_savant_season.py` — promoted to a first-class collection runner (was `ideas/idea_12_bat_tracking/`) and wired into `/fantasy-collect-all-data` as a weekly-gated step. `{Verb}_{Object}_{Source}_{Modifier}.py`; top docstring with **Description / Source Data / Outputs**; stdlib `urllib` + `csv`, no pandas, no pybaseball. Defaults to current season; `--backfill` pulls 2023..current; `--weekly` self-gates (skips if run within 7 days).
2. **Analysis script:** `ideas/idea_12_bat_tracking/analyze_bat_tracking_mlb_2026.py` — same docstring rules; native Python + `numpy`/`scipy` for math (verify what's installed in the venv before importing; idea 05/16/17 hand-rolled with numpy/scipy/statsmodels and no sklearn — match that posture); no pandas in the committed file.
3. **Report:** `fantasy_baseball/reports/bat_tracking_2026.md` (mirror the structure of `ideas/idea_16_waiver_signals/reports/`):
   - Data-availability matrix up top (the constraint is part of the finding).
   - **2026 batting breakout candidate list** (primary) with physical vs output scores, gap, ownership, roster status.
   - Batting YoY carry-forward tables (2023→2024, 2024→2025, + partial), with the 2-pair caveat.
   - Pitching same-season baseline: stuff↔results correlation table + SP/RP stuff-vs-results lists.
   - Sell-high / regression-down (batting) and sustainability-watch (pitching) lists.
   - Plain-English takeaways for roster/waiver decisions now.
4. **Derived CSVs → Bronze** (`local` = computed here): `2026_local_bat_tracking_breakouts.csv`, `2026_local_bat_tracking_yoy_batter.csv`, `2026_local_statcast_pitcher_stuff.csv`. **Raw Savant pulls** land as `{YEAR}_mlb_bat_tracking_season.csv` / `{YEAR}_mlb_pitch_tracking_season.csv`. **No report artifacts (.md) in the data lake.**

---

## Engineering Constraints (from CLAUDE.md — obey exactly)

- **Python executable:** `C:/Users/peter.rigali/Desktop/acn_repo/.venv/Scripts/python.exe` (full absolute path; never bare `python`). Set `$env:PYTHONIOENCODING = 'utf-8'` when running.
- **No `pandas`** in either committed script; **no `pybaseball`** (drags in pandas). Use `urllib` + `csv.DictReader` (rows as list-of-dicts) and `numpy`/`scipy` for math.
- **CSV loading:** always `csv.DictReader` → list of dicts.
- **File header docstring** with Description / Source Data / Outputs on every `.py`.
- **Secrets:** none needed for Savant (public); if any key is ever required, read from `config.ini` via `configparser` — never hard-code.
- **No scripts in `data-lake/`**; pull/run logs → `data-lake/00_Logs/fantasy_baseball/`.
- **Identity:** join through `player_map.csv` (`mlbam_player_id`); if new MLBAM ids appear that aren't in the map, log them — do not silently invent identities.
- After completing, update the **Future Analysis** table in `fantasy_baseball/README.md` and flip Idea 12's status in `ideas.md` (`Not Started` → `In Progress` → `Complete`), per the maintenance note atop ideas.md.

---

## Definition of Done

- Savant bat-tracking (2023–2026) and pitch-arsenal velo/spin (2023–2026) pulled into Bronze with convention-compliant names; 100% match rate to `player_map.csv` (verified).
- 2026 batting **breakout candidate list** produced and ownership-overlaid (the primary deliverable).
- 2023→2024 and 2024→2025 batting YoY carry-forward computed and reported **with the 2-pair sample caveat stated**.
- Pitching **2026 same-season baseline** produced (stuff↔results correlation + SP/RP stuff-vs-results lists); predictive YoY explicitly deferred.
- All five questions answered explicitly in `bat_tracking_2026.md`.
- Both scripts run clean under the venv Python with no `pandas`/`pybaseball` import in committed files; derived + raw CSVs land in Bronze; report lands in `fantasy_baseball/reports/`.
