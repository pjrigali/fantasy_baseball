# Analysis Prompt — Idea 5: Box Score Stat Relationships (Correlation, Redundancy & Category-System Audit)

> Execution-ready prompt for the Idea 5 analysis. Read this top to bottom before writing any code. See [`../../ideas.md`](../../ideas.md) §5 for the original idea and [`../../scoring.md`](../../scoring.md) for the league scoring definition.

---

## CRITICAL CONTEXT — Read First: This Is a Categories League, Not a Points League

The original idea text (ideas.md §5) is written as if this were a **points** league — it talks about "fixed point values per stat," "scoring weights," "implied weights vs ESPN weights," and "regression of stats against ESPN fantasy points." **That framing does not apply here.**

Per [`scoring.md`](../../scoring.md), the league is **Head-to-Head, 5x5 Categories**:

- **Batting (5):** R, HR, RBI, SB, OPS
- **Pitching (5):** K/9, QS, SVHD, ERA (lower better), WHIP (lower better)

There are **no per-stat point weights to audit.** Each category is won or lost independently each matchup week (you win the week by taking the majority of the 10 categories). This is confirmed in the data: the `points` column in `2026_espn_stats_daily.csv` is `0.0` for every row.

**Reframe the "scoring system audit" accordingly.** Instead of "back out implied point weights," the audit answers: *How many effectively independent axes do these 10 categories actually represent, and which categories are redundant vs. which are the true scarce differentiators?* In a categories league, if R/HR/RBI all move together, then a roster built for one tends to win all three "for free" — meaning the five batting categories are **not** five independent levers. The categories that are weakly correlated with the rest (likely SB on offense, SVHD on pitching) are where matchups are actually won and lost, and therefore where roster construction should concentrate.

If any part of the analysis seems to require point weights, stop and re-derive it in categories terms — do not invent weights.

---

## Objective

Build the full correlation structure of box-score stats (batters and pitchers separately), determine which of the 10 scoring categories are redundant vs. independent, surface the player archetypes that emerge from the stat clusters, and translate all of it into concrete roster-construction guidance for THIS league's category set.

---

## Scope — Multi-Year (2023–2026)

MLB daily game logs go back to **2023**, so run the correlation / redundancy / archetype analysis across **all four seasons (2023, 2024, 2025, 2026)**. A single season's correlation structure can be a small-sample artifact; the value of the audit comes from showing the redundancy bundle (HR/R/RBI, ERA/WHIP) and the scarce/orthogonal categories (SB, SVHD) are **stable year over year**. Report the per-season category correlation block side by side, plus a pooled all-years view.

The league/roster/market context only exists for **2025–2026** (ESPN files), so the **team-holdings and market-valuation overlays are limited to those seasons** — the underlying stat-relationship and archetype work spans all four.

## Data Sources (verified columns — use these exact files)

All under `data-lake/01_Bronze/fantasy_baseball/`.

### MLB game logs — the multi-year stat base (all 10 categories derivable)
1. **`2023_mlb_stats_daily.csv`, `2024_mlb_stats_daily.csv`, `2025_mlb_stats_daily.csv`** — shared schema: identity via `playerName` / `playerId`, batter-vs-pitcher split via the **`b_or_p`** column. Stat columns: `AB, H, 2B, 3B, HR, R, RBI, SB, CS, B_BB, HBP, SF, SO, TB` (batting) and `OUTS, ER, K, P_BB, P_H, P_HR, P_R, QS, SV, HLD, SVHD, W, L, GS` (pitching). All 10 scoring categories are computable from these: **OPS** = OBP + SLG where OBP = (H+B_BB+HBP)/(AB+B_BB+HBP+SF) and SLG = TB/AB; **K/9** = K·9/(OUTS/3); **ERA** = ER·9/(OUTS/3); **WHIP** = (P_BB+P_H)/(OUTS/3); QS, SVHD, R, HR, RBI, SB are direct.
2. **`2026_mlb_stats_boxscore.csv`** (and `2026_mlb_stats_daily_archive.csv`) — 2026 game logs. **Same stat columns** as above, but identity columns are renamed (`player_id`, `player_name`, plus `did_play`); `b_or_p` is still present. **Note:** ideas.md §5 references `2026_mlb_stats_daily.csv`, which does **not** exist for 2026 — these are its equivalents. Harmonize the column names against the 2023–2025 schema before pooling.

### League / market context (2025–2026 only — for overlays)
3. **`2026_espn_stats_daily.csv`** (and `2025_espn_stats_daily.csv`) — **overlay only, not the stat source.** One row per (date, team, player), with the box-score vector aligned to fantasy rosters. Use it **solely** to map players to fantasy teams (`team_name`) for the team-holdings overlay and for roster/lineup context — **do not** compute the category values from it.
   - **Decision (locked):** all category values are computed from the MLB game logs (sources 1–2) for **every** season including 2026. The ESPN daily file is "more or less the same stats but covers fewer players" (only rostered/relevant players), so using the MLB logs keeps the population consistent across 2023–2026 and avoids a survivorship bias toward owned players. Do not cross-source category math from ESPN.
   - Split batter vs pitcher on the **`player_type`** column (`batter` / `pitcher`) when using it for the overlay.
   - `points` column is `0.0` everywhere — ignore it (categories league).
   - Useful overlay/context columns: `team_name`, `acquisition_type`, `lineup_slot`, `eligible_slots`, `injury_status`, `pro_team`.
4. **`2026_espn_rankings_daily.csv`** — market proxy. Columns include `pct_owned`, `pct_started`, `pct_change`, `avg_draft_position`, `auction_value_avg`, `position_rank`, `total_rank`, `pr7`/`pr15`/`pr30`/`pr_season`. Use ownership/ADP as an external valuation benchmark to test whether the market over/under-values certain archetypes.

---

## Analytical Approach

Work batters and pitchers as two fully separate analyses (different stat vectors, different categories). For each:

### 0. Harmonize the multi-year schemas
- The 2023–2025 MLB daily files use `playerName`/`playerId`/`b_or_p`; the 2026 boxscore file renames identity columns (`player_name`/`player_id`, adds `did_play`) but keeps the same stat columns and `b_or_p`. Map all four to a common schema before pooling. Tag each row with its `season` year.

### 1. Aggregate to season-to-date per player, per year
- Roll up the daily rows to **per-player, per-season** totals/rates (so a player appears once per year). Counting stats sum; rate stats (OPS, ERA, WHIP, K/9, AVG, OBP, SLG) must be **recomputed from the summed components**, not averaged-of-averages (recompute OPS from total OBP/SLG inputs; ERA from total ER and OUTS; K/9 from total K and IP via OUTS/3).
- Apply minimum-sample filters to avoid small-sample noise (e.g. batters with ≥ ~50 AB; pitchers with ≥ ~20 IP). State the thresholds you pick. Apply them per season.

### 2. Correlation matrix
- Pearson correlation across all numeric stat columns, batters and pitchers separately. Persist each full matrix as a CSV.
- Also compute Spearman (rank) correlation — rate stats and counting stats have skewed distributions, and Spearman is more robust to that. Report where Pearson and Spearman disagree.
- Explicitly extract and tabulate the pairwise correlations **among the 10 scoring categories only** — this is the heart of the audit.

### 3. Category redundancy / independence audit (the reframed "scoring system audit")
- From the 5x5 category correlation block, quantify how much independent information the category set carries. Two complementary lenses:
  - **Correlation clustering / PCA on the 5 batting categories and the 5 pitching categories.** How many principal components explain the bulk of variance? If the 5 batting categories collapse to ~2–3 effective dimensions, the league is effectively scoring fewer independent things than it appears to.
  - **Pairwise redundancy flags:** call out category pairs with |r| above a stated threshold (likely HR↔RBI, HR↔R, RBI↔R; ERA↔WHIP on pitching) as "effectively double/triple-counted."
- Identify the **scarce / orthogonal categories** — those weakly correlated with the rest (hypotheses: SB for batters, SVHD for pitchers). Frame these as the high-leverage roster-construction targets, since they don't come "for free" with the correlated bundle.
- Test whether any **non-scored** stat is a strong independent signal that the category set misses (e.g. BB/OBP-only value, holds vs saves split), and whether any scored category is nearly redundant. Phrase recommendations as *roster-construction implications* ("punt or stream X because it rides along with Y"), not as point-weight changes.

### 4. Archetype discovery (clustering)
- Standardize the season-aggregated stat profiles (z-score each column) and cluster:
  - PCA to 2–3 components first (inspect and name the loadings/axes), then k-means; select k via silhouette/elbow. Expect ~4–6 archetypes per player type.
  - Hypothesized batter archetypes: power bats, speedsters, contact/OBP hitters, balanced. Pitchers: strikeout SP, ground-ball/contact SP, high-leverage RP (saves/holds), volume innings SP.
- Profile each cluster (centroid stat line, representative named players, cluster size).
- Overlay the league: which fantasy teams hold which archetypes (`team_name`), and overlay the market (`pct_owned`/ADP) to flag archetypes the market systematically over- or under-values relative to their category contribution in THIS scoring system.

### 5. Cross-season robustness (core deliverable, not optional)
- Run the category correlation block for **each season 2023–2026** and present them side by side, plus a pooled all-years view. Confirm the redundancy structure (HR/R/RBI bundle, ERA/WHIP bundle, SB & SVHD orthogonality) is stable year over year, not a single-season artifact. Call out any category pair whose correlation is unstable across seasons — that instability is itself a finding.

---

## Questions the Analysis Must Answer

1. Which scoring categories are highly correlated and therefore effectively double/triple-counted (so winning one tends to win the others)?
2. Which scoring categories are independent/scarce, and are therefore the true differentiators teams should build around or contest?
3. Are there unscored stats that carry strong independent signal the category set fails to capture?
4. Is any scored category nearly redundant with another (and thus low-leverage / streamable)?
5. What player archetypes emerge from the stat clusters, who exemplifies each, and which fantasy teams are concentrated in which archetypes?
6. Which archetypes does the market (ownership/ADP) over- or under-value relative to their actual contribution to THIS league's categories?

---

## Deliverables

1. **Analysis script:** `ideas/idea_05_stat_relationships/analyze_stat_relationships_espn_2026.py`
   - Follow the script naming convention `{Verb}_{Object}_{Source}_{Modifier}.py`.
   - Top-of-file docstring with the mandated sub-headers: **Description**, **Source Data**, **Outputs**.
2. **Report:** `fantasy_baseball/reports/stat_relationships_2026.md` (mirror the structure used by `ideas/idea_16_waiver_signals/reports/`) containing:
   - Batter and pitcher correlation matrices saved as CSVs; the key 5x5 category blocks rendered as tables in the report.
   - The 5x5 category correlation tables **per season (2023–2026) plus pooled**, with redundant pairs and scarce categories explicitly flagged and any cross-season instability called out.
   - PCA "effective dimensionality" summary per player type.
   - Archetype cluster cards (centroid line, size, representative players) + team-holdings and market-valuation overlays.
   - A plain-English **roster-construction takeaways** section translating the findings into how to play this categories league.
3. Any derived CSVs (e.g. per-player archetype assignments, category correlation matrix) go to `data-lake/01_Bronze/fantasy_baseball/` using the naming convention, e.g. `2026_local_stat_correlations_batter.csv`, `2026_local_archetypes_batter.csv` (`local` = computed on this machine). **No report artifacts (.md) in the data lake.**

---

## Engineering Constraints (from CLAUDE.md — obey exactly)

- **Python executable:** `C:/Users/peter.rigali/Desktop/acn_repo/.venv/Scripts/python.exe` (full absolute path; never bare `python`). Set `$env:PYTHONIOENCODING = 'utf-8'` when running.
- **No `pandas` in the final artifact** (`analyze_stat_relationships_espn_2026.py`) — prefer native Python (`csv.DictReader` to load rows as list-of-dicts) and `numpy`/`scipy`/`statsmodels` for the math. Pandas is allowed only for scratch/EDA, not in the committed script. (Idea 17 hand-rolled its methods with numpy/scipy/statsmodels and no sklearn — match that posture; verify what's installed in the venv before importing.)
- **CSV loading:** always `csv.DictReader` → list of dicts.
- **File header docstring** with Description / Source Data / Outputs on the `.py` file.
- **No scripts in `data-lake/`**; logs (if any) to `data-lake/00_Logs/fantasy_baseball/`.
- After completing, update the **Future Analysis** table in `fantasy_baseball/README.md` and flip Idea 5's status in `ideas.md` to `In Progress` / `Complete` as appropriate (per the maintenance note at the top of ideas.md).

---

## Addendum — Proposed Metrics (balance the two sides' internal independence)

Added scope: propose a new scoring structure where the **batting categories and the pitching
categories carry an equal amount of internal correlation** (the two sides do *not* need to
correlate with each other — they can't; the goal is symmetric *intra-side* structure). Today
the sides are lopsided: batting collapses to ~1.9 effective axes (R/HR/RBI tied bundle) while
pitching spreads across ~3.3. Measure internal independence with the **participation ratio** of
each side's category correlation matrix (eigenvalue-based effective dimensionality) plus the
largest mutually-tied cluster at |r| ≥ 0.70.

Produce **two** scenarios:

- **Scenario A — Mirror (minimal change, most adoptable):** keep batting unchanged (it already
  has the 3-tied R/HR/RBI bundle), and search realistic pitching categories for the 5-set whose
  internal correlation *shape* best mirrors batting's — i.e. it has its own 3-category tied
  bundle plus two looser categories. Prefer sets that retain the current pitching categories.
- **Scenario B — Max independence (from scratch, broaden player types):** pick the most
  *independent* 5 categories per side and equalize them. Hitting stats are structurally more
  correlated, so batting is the binding constraint (its 5-cat ceiling is ~2.7 effective axes vs
  pitching's ~4.6); cap pitching at batting's ceiling so the two truly equalize rather than
  letting pitching run away. The aim is to spread value across many player archetypes so no
  single profile sweeps multiple categories and managers who miss early runs can still compete.

- **Scenario C — Keep 5x5, add one category each (→ 6x6):** leave all ten current categories
  in place and add a single new category per side. The batting addition is the most
  *independent* of the existing five (raises batting's effective axes = lowers its internal
  relationship); the pitching addition is the most *redundant* with the existing five (lowers
  pitching's effective axes = raises its internal relationship). Restrict batting candidates to
  recognizable, higher-volume stats — rare counting stats (2B/3B/HBP/CS) read as "independent"
  only because they are noisy, not because they measure a new skill. Note honestly that one
  batting addition only partially closes the gap (batting's shared offensive halo limits it).

Candidate categories restricted to realistic, trackable fantasy stats. Output: a "Proposed
Metrics" report section with a balance scorecard (current vs A vs B vs C: effective axes, max
tied cluster, balance gap per side) and `2026_local_proposed_scoring.csv`.

## Definition of Done

- Correlation matrices produced for batters and pitchers, **across 2023–2026** (per-season + pooled).
- 5x5 category redundancy/independence audit completed and stated in categories terms (no invented point weights), with cross-season stability confirmed or instability flagged.
- Archetypes discovered, named, profiled, and overlaid with team holdings + market valuation.
- All six questions above answered explicitly in the report.
- Script runs clean under the venv Python with no pandas import in the committed file; derived CSVs land in the Bronze layer with convention-compliant names; report lands in `fantasy_baseball/reports/`.
