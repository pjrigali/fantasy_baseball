"""
Analyze each league team's performance across all 10 H2H scoring categories.
Scoring categories (5x5):
  Batting: R, HR, RBI, SB, OPS
  Pitching: K/9, QS, SVHD, ERA, WHIP  (ERA/WHIP lower is better)
"""

import sys
import io
import pandas as pd
import numpy as np

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CSV_PATH = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\stats_espn_daily_2026.csv"

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df = pd.read_csv(CSV_PATH, low_memory=False)

# Numeric-ify every stat column we care about
stat_cols = ["R", "HR", "RBI", "SB", "OPS", "K/9", "QS", "SVHD", "ERA", "WHIP",
             "K", "OUTS", "ER", "P_BB", "P_H", "H", "AB", "OBP", "SLG",
             "IP_calc"]  # we'll derive IP from OUTS

for c in stat_cols[:-1]:          # skip IP_calc – we create it
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

# Innings pitched from OUTS (3 OUTS = 1 IP)
if "OUTS" in df.columns:
    df["IP"] = df["OUTS"] / 3.0
else:
    df["IP"] = 0.0

# ---------------------------------------------------------------------------
# Split batters vs pitchers by player_type
# ---------------------------------------------------------------------------
pitcher_mask = df["player_type"].str.lower().isin(["pitcher", "p"]) if "player_type" in df.columns else pd.Series(False, index=df.index)
batters = df[~pitcher_mask].copy()
pitchers = df[pitcher_mask].copy()

# ---------------------------------------------------------------------------
# Days active per team (distinct scoring dates)
# ---------------------------------------------------------------------------
days_per_team = df.groupby("team_name")["date"].nunique().rename("days")

# ---------------------------------------------------------------------------
# Batting aggregation
# ---------------------------------------------------------------------------
bat_agg = (
    batters.groupby("team_name")
    .agg(
        R=("R", "sum"),
        HR=("HR", "sum"),
        RBI=("RBI", "sum"),
        SB=("SB", "sum"),
        # OPS: weighted by AB
        _OPS_sum=("OPS", lambda x: (x * pd.to_numeric(
            batters.loc[x.index, "AB"] if "AB" in batters.columns else pd.Series(1, index=x.index),
            errors="coerce").fillna(1)).sum()),
        _AB_sum=("AB", "sum"),
    )
    .reset_index()
)

# Weighted OPS = sum(OPS*AB) / sum(AB)
bat_agg["OPS"] = bat_agg["_OPS_sum"] / bat_agg["_AB_sum"].replace(0, np.nan)
bat_agg.drop(columns=["_OPS_sum", "_AB_sum"], inplace=True)

# ---------------------------------------------------------------------------
# Pitching aggregation — use component stats for rate categories
# ---------------------------------------------------------------------------
pit_agg = (
    pitchers.groupby("team_name")
    .agg(
        QS=("QS", "sum"),
        SVHD=("SVHD", "sum"),
        IP=("IP", "sum"),
        K=("K", "sum"),
        ER=("ER", "sum"),
        _BB=("P_BB", "sum"),
        _H_pit=("P_H", "sum"),
    )
    .reset_index()
)

# Rate stats — guard against zero IP
pit_agg["K/9"]  = (pit_agg["K"]  * 9) / pit_agg["IP"].replace(0, np.nan)
pit_agg["ERA"]  = (pit_agg["ER"] * 9) / pit_agg["IP"].replace(0, np.nan)
pit_agg["WHIP"] = (pit_agg["_BB"] + pit_agg["_H_pit"]) / pit_agg["IP"].replace(0, np.nan)
pit_agg.drop(columns=["K", "ER", "_BB", "_H_pit", "IP"], inplace=True)

# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
teams = pd.merge(bat_agg, pit_agg, on="team_name", how="outer").fillna(0)
teams = teams.set_index("team_name")
teams = teams.join(days_per_team)

CATEGORIES = ["R", "HR", "RBI", "SB", "OPS", "K/9", "QS", "SVHD", "ERA", "WHIP"]
LOWER_IS_BETTER = {"ERA", "WHIP"}
# Counting stats that have meaningful per-day rates
COUNTING_CATS = {"R", "HR", "RBI", "SB", "QS", "SVHD"}

# Build per-day table (rate stats stay as-is)
avg_per_day = pd.DataFrame(index=teams.index)
for cat in CATEGORIES:
    if cat not in teams.columns:
        continue
    if cat in COUNTING_CATS:
        avg_per_day[cat] = teams[cat] / teams["days"].replace(0, np.nan)
    else:
        avg_per_day[cat] = teams[cat]   # already a rate stat

# ---------------------------------------------------------------------------
# Rank teams in each category (1 = best)
# Lower is better for ERA and WHIP
# ---------------------------------------------------------------------------

ranks = pd.DataFrame(index=teams.index)
for cat in CATEGORIES:
    if cat in teams.columns:
        ascending = cat in LOWER_IS_BETTER
        ranks[cat] = teams[cat].rank(ascending=ascending, method="min")

# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------
n_teams = len(teams)
STRENGTH_THRESHOLD  = n_teams * 0.35   # top ~35 %
WEAKNESS_THRESHOLD  = n_teams * 0.65   # bottom ~35 %

GRADE = {1: "★★★ Elite", 2: "★★★ Elite", 3: "★★  Strong", 4: "★★  Strong",
         5: "★    Average", 6: "★    Average", 7: "☆    Weak", 8: "☆    Weak",
         9: "✗    Poor", 10: "✗    Poor"}

def grade(r, n=10):
    pct = r / n
    if pct <= 0.20: return "★★★ Elite"
    if pct <= 0.40: return "★★  Strong"
    if pct <= 0.60: return "★   Average"
    if pct <= 0.80: return "☆   Weak"
    return "✗   Poor"

print("=" * 80)
print("  FANTASY BASEBALL 2026 — TEAM SCORECARDS (5x5 H2H Categories)")
print("=" * 80)
print(f"  Data covers {df['date'].nunique()} scoring days | {n_teams} teams\n")

# League averages for context
league_days = teams["days"].mean()
print(f"── LEAGUE AVERAGES (avg {league_days:.0f} scoring days per team) ──")
print(f"   {'Category':<10} {'Season':>8}  {'Avg/Day':>9}")
for cat in CATEGORIES:
    if cat not in teams.columns:
        continue
    avg_season = teams[cat].mean()
    if cat in COUNTING_CATS:
        avg_day = avg_per_day[cat].mean()
        print(f"   {cat:<10} {avg_season:>8.2f}  {avg_day:>9.2f}")
    else:
        print(f"   {cat:<10} {avg_season:>8.2f}  {'—':>9}")
print()

# Per-team scorecards
for team in sorted(teams.index):
    row  = teams.loc[team]
    rrow = ranks.loc[team]

    n_days = int(teams.loc[team, "days"])
    print("─" * 80)
    print(f"  TEAM: {team}  ({n_days} scoring days)")
    print("─" * 80)
    print(f"  {'Category':<10} {'Season':>10}  {'Avg/Day':>9}  {'Rank':>6}  {'Grade'}")
    print(f"  {'─'*10} {'─'*10}  {'─'*9}  {'─'*6}  {'─'*16}")

    strengths  = []
    weaknesses = []

    for cat in CATEGORIES:
        if cat not in row.index:
            continue
        val     = row[cat]
        per_day = avg_per_day.loc[team, cat]
        rnk     = int(rrow[cat])
        g       = grade(rnk, n_teams)
        note    = "(lower=better)" if cat in LOWER_IS_BETTER else ""
        # Rate stats show "—" in Avg/Day column to avoid confusion
        pd_str  = f"{per_day:>9.2f}" if cat in COUNTING_CATS else f"{'—':>9}"
        print(f"  {cat:<10} {val:>10.2f}  {pd_str}  {rnk:>4}/{n_teams}  {g}  {note}")

        if rnk <= STRENGTH_THRESHOLD:
            strengths.append(cat)
        elif rnk >= WEAKNESS_THRESHOLD:
            weaknesses.append(cat)

    print()
    print(f"  STRENGTHS  : {', '.join(strengths)  if strengths  else 'None in top tier'}")
    print(f"  WEAKNESSES : {', '.join(weaknesses) if weaknesses else 'None in bottom tier'}")
    print()

# ---------------------------------------------------------------------------
# Summary matrix
# ---------------------------------------------------------------------------
print("=" * 72)
print("  CATEGORY RANK MATRIX (rank / team, lower = better rank)")
print("=" * 72)
header = f"  {'Team':<30}" + "".join(f"{c:>7}" for c in CATEGORIES)
print(header)
print("  " + "─" * (30 + 7 * len(CATEGORIES)))
for team in sorted(teams.index):
    line = f"  {team:<30}"
    for cat in CATEGORIES:
        r = int(ranks.loc[team, cat]) if cat in ranks.columns else 0
        line += f"{r:>7}"
    print(line)

print()
print("  (ERA, WHIP: rank 1 = lowest value = best)")
print()

# ---------------------------------------------------------------------------
# Top-3 per category
# ---------------------------------------------------------------------------
print("=" * 72)
print("  CATEGORY LEADERS (top 3 teams per category)")
print("=" * 72)
for cat in CATEGORIES:
    if cat not in teams.columns:
        continue
    ascending = cat in LOWER_IS_BETTER
    top3 = teams[cat].sort_values(ascending=ascending).head(3)
    entries = [f"{t} ({v:.2f})" for t, v in top3.items()]
    print(f"  {cat:<8}: " + " | ".join(entries))
