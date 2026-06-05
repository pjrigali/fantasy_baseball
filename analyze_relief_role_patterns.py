"""
Description:
    Analyzes appearance-pattern signals for MLB relief pitchers to support role inference logic.
    Computes per-pitcher metrics from full-season boxscore data (2026), then aggregates by
    FanGraphs-assigned role to identify thresholds for: outs per game (usage depth),
    SVHD rate (high-leverage frequency), SV rate, HLD rate, and total appearances.

Source Data:
    - C:/Users/peter.rigali/Desktop/acn_repo/data-lake/01_Bronze/fantasy_baseball/closer_depth_fangraphs_2026.csv
      (Most recent snapshot: max date_scraped = 2026-06-01)
    - C:/Users/peter.rigali/Desktop/acn_repo/data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_2026.csv
      (Full 2026 season, relief appearances only: b_or_p=pitcher, did_play=1, GS=0)

Outputs:
    Console report with per-role statistics and inference thresholds.
"""

import csv
import statistics
from collections import defaultdict

# ---------------------------------------------------------------------------
# 1. Load FanGraphs — use most recent snapshot (max date_scraped)
# ---------------------------------------------------------------------------
FG_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\closer_depth_fangraphs_2026.csv"
BOX_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\stats_mlb_boxscore_2026.csv"

# Find max date_scraped
all_dates = set()
with open(FG_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        all_dates.add(row["date_scraped"])
max_date = max(all_dates)

# Load FanGraphs rows at max date — keep roles of interest
ROLES_OF_INTEREST = {"Closer", "Closer Committee", "Co-Closer", "Setup Man", "Middle Reliever", "Long Reliever"}
fg_pitchers = {}  # player_name -> role
with open(FG_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["date_scraped"] == max_date and row["role"] in ROLES_OF_INTEREST:
            fg_pitchers[row["player_name"].strip()] = row["role"]

print(f"FanGraphs snapshot date: {max_date}")
print(f"FanGraphs pitchers loaded: {len(fg_pitchers)}")
from collections import Counter
role_counts = Counter(fg_pitchers.values())
for role, cnt in sorted(role_counts.items()):
    print(f"  {role}: {cnt}")
print()

# ---------------------------------------------------------------------------
# 2. Load boxscore — full season, relief appearances only
# ---------------------------------------------------------------------------
def safe_int(val):
    try:
        return int(float(val)) if val not in ("", None) else 0
    except (ValueError, TypeError):
        return 0

pitcher_stats = defaultdict(lambda: {
    "games": 0, "outs": 0, "svhd": 0, "sv": 0, "hld": 0, "outs_per_game_list": []
})

with open(BOX_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["b_or_p"] != "pitcher":
            continue
        if row["did_play"] != "1":
            continue
        if row["GS"] != "0":
            continue
        name = row["player_name"].strip()
        outs = safe_int(row["OUTS"])
        svhd = safe_int(row["SVHD"])
        sv   = safe_int(row["SV"])
        hld  = safe_int(row["HLD"])

        s = pitcher_stats[name]
        s["games"] += 1
        s["outs"] += outs
        s["svhd"] += svhd
        s["sv"] += sv
        s["hld"] += hld
        s["outs_per_game_list"].append(outs)

# Compute derived metrics
pitcher_metrics = {}
for name, s in pitcher_stats.items():
    g = s["games"]
    if g == 0:
        continue
    avg_outs = s["outs"] / g
    pitcher_metrics[name] = {
        "total_games":      g,
        "total_outs":       s["outs"],
        "avg_outs_per_game": round(avg_outs, 3),
        "total_svhd":       s["svhd"],
        "svhd_rate":        round(s["svhd"] / g, 3),
        "sv_rate":          round(s["sv"] / g, 3),
        "hld_rate":         round(s["hld"] / g, 3),
        "outs_list":        s["outs_per_game_list"],
    }

print(f"Pitchers with boxscore data: {len(pitcher_metrics)}")

# ---------------------------------------------------------------------------
# 3. Match FanGraphs pitchers to boxscore metrics
# ---------------------------------------------------------------------------
matched = {}   # name -> {role, metrics}
unmatched = []
for name, role in fg_pitchers.items():
    if name in pitcher_metrics:
        matched[name] = {"role": role, **pitcher_metrics[name]}
    else:
        unmatched.append((name, role))

print(f"Matched: {len(matched)}, Unmatched: {len(unmatched)}")
if unmatched:
    print("Unmatched FanGraphs pitchers (no boxscore data):")
    for n, r in sorted(unmatched):
        print(f"  {n} ({r})")
print()

# ---------------------------------------------------------------------------
# 4. Group by role and compute statistics
# ---------------------------------------------------------------------------
def pct_fmt(num, denom):
    return f"{num/denom*100:.1f}%" if denom > 0 else "N/A"

def stats_block(values, label):
    if not values:
        return f"  {label}: no data\n"
    mn  = statistics.mean(values)
    med = statistics.median(values)
    return f"  {label}: mean={mn:.3f}, median={med:.3f}, n={len(values)}\n"

FOCUS_ROLES = ["Closer", "Co-Closer", "Closer Committee", "Setup Man", "Middle Reliever", "Long Reliever"]

by_role = defaultdict(list)
for name, d in matched.items():
    by_role[d["role"]].append(d)

print("=" * 70)
print("ROLE-BY-ROLE APPEARANCE PATTERN ANALYSIS")
print("=" * 70)

for role in FOCUS_ROLES:
    players = by_role.get(role, [])
    if not players:
        continue
    n = len(players)
    print(f"\n{'-'*70}")
    print(f"ROLE: {role}  (n={n})")
    print(f"{'-'*70}")

    avg_outs_vals  = [p["avg_outs_per_game"] for p in players]
    svhd_rate_vals = [p["svhd_rate"] for p in players]
    sv_rate_vals   = [p["sv_rate"] for p in players]
    hld_rate_vals  = [p["hld_rate"] for p in players]
    total_g_vals   = [p["total_games"] for p in players]

    print(stats_block(avg_outs_vals,  "avg_outs_per_game"), end="")
    print(stats_block(svhd_rate_vals, "svhd_rate"),         end="")
    print(stats_block(sv_rate_vals,   "sv_rate"),           end="")
    print(stats_block(hld_rate_vals,  "hld_rate"),          end="")
    print(stats_block(total_g_vals,   "total_games"),       end="")

    # avg_outs distribution
    lt3  = [v for v in avg_outs_vals if v < 3.0]
    b3_35 = [v for v in avg_outs_vals if 3.0 <= v <= 3.5]
    gt35 = [v for v in avg_outs_vals if v > 3.5]
    print(f"  avg_outs distribution:")
    print(f"    < 3.0 (sub-inning):           {pct_fmt(len(lt3), n)}  ({len(lt3)}/{n})")
    print(f"    3.0–3.5 (clean inning):       {pct_fmt(len(b3_35), n)}  ({len(b3_35)}/{n})")
    print(f"    > 3.5 (multi-inning):         {pct_fmt(len(gt35), n)}  ({len(gt35)}/{n})")

    # svhd_rate distribution
    hi5 = [v for v in svhd_rate_vals if v >= 0.5]
    hi7 = [v for v in svhd_rate_vals if v >= 0.7]
    print(f"  svhd_rate distribution:")
    print(f"    >= 0.50 (high-leverage):      {pct_fmt(len(hi5), n)}  ({len(hi5)}/{n})")
    print(f"    >= 0.70 (elite high-lev):     {pct_fmt(len(hi7), n)}  ({len(hi7)}/{n})")

# ---------------------------------------------------------------------------
# 5. Cross-role comparison: Setup Man vs Middle Reliever (avg_outs)
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("SETUP MAN vs MIDDLE RELIEVER — avg_outs_per_game comparison")
print("=" * 70)
sm_outs = [p["avg_outs_per_game"] for p in by_role.get("Setup Man", [])]
mr_outs = [p["avg_outs_per_game"] for p in by_role.get("Middle Reliever", [])]
if sm_outs and mr_outs:
    print(f"  Setup Man    n={len(sm_outs)}: mean={statistics.mean(sm_outs):.3f}, median={statistics.median(sm_outs):.3f}")
    print(f"  Middle Rel.  n={len(mr_outs)}: mean={statistics.mean(mr_outs):.3f}, median={statistics.median(mr_outs):.3f}")
    diff = statistics.mean(sm_outs) - statistics.mean(mr_outs)
    print(f"  Mean difference (SM - MR): {diff:+.3f} outs/game")

# ---------------------------------------------------------------------------
# 6. Does svhd_rate separate Closer vs Closer Committee?
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("CLOSER vs CLOSER COMMITTEE — svhd_rate comparison")
print("=" * 70)
cl_svhd  = [p["svhd_rate"] for p in by_role.get("Closer", [])]
cc_svhd  = [p["svhd_rate"] for p in by_role.get("Closer Committee", [])]
coc_svhd = [p["svhd_rate"] for p in by_role.get("Co-Closer", [])]
if cl_svhd:
    print(f"  Closer           n={len(cl_svhd)}: mean={statistics.mean(cl_svhd):.3f}, median={statistics.median(cl_svhd):.3f}")
if coc_svhd:
    print(f"  Co-Closer        n={len(coc_svhd)}: mean={statistics.mean(coc_svhd):.3f}, median={statistics.median(coc_svhd):.3f}")
if cc_svhd:
    print(f"  Closer Committee n={len(cc_svhd)}: mean={statistics.mean(cc_svhd):.3f}, median={statistics.median(cc_svhd):.3f}")

# Setup vs Middle for svhd_rate
sm_svhd = [p["svhd_rate"] for p in by_role.get("Setup Man", [])]
mr_svhd = [p["svhd_rate"] for p in by_role.get("Middle Reliever", [])]
print()
print("SETUP MAN vs MIDDLE RELIEVER — svhd_rate comparison")
if sm_svhd:
    print(f"  Setup Man    n={len(sm_svhd)}: mean={statistics.mean(sm_svhd):.3f}, median={statistics.median(sm_svhd):.3f}")
if mr_svhd:
    print(f"  Middle Rel.  n={len(mr_svhd)}: mean={statistics.mean(mr_svhd):.3f}, median={statistics.median(mr_svhd):.3f}")

# ---------------------------------------------------------------------------
# 7. Middle Relievers with high svhd_rate (potential mis-labels)
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("MIDDLE RELIEVERS with svhd_rate >= 0.40 (potential high-leverage mis-labels)")
print("=" * 70)
mr_players = by_role.get("Middle Reliever", [])
high_lev_mr = [(p["player_name"] if "player_name" in p else "?", p) for p in mr_players if p["svhd_rate"] >= 0.40]
# Re-build with name
high_lev_mr = []
for name, d in matched.items():
    if d["role"] == "Middle Reliever" and d["svhd_rate"] >= 0.40:
        high_lev_mr.append((name, d))
high_lev_mr.sort(key=lambda x: -x[1]["svhd_rate"])
if high_lev_mr:
    print(f"  {'Name':<25} {'Games':>6} {'AvgOuts':>8} {'SVHD_rate':>10} {'SV_rate':>8} {'HLD_rate':>9}")
    for name, d in high_lev_mr:
        print(f"  {name:<25} {d['total_games']:>6} {d['avg_outs_per_game']:>8.3f} {d['svhd_rate']:>10.3f} {d['sv_rate']:>8.3f} {d['hld_rate']:>9.3f}")
else:
    print("  None found.")

# ---------------------------------------------------------------------------
# 8. Outs variance — high vs low signal
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("OUTS VARIANCE (std dev of per-game outs) by role")
print("=" * 70)
print("  High stdev => inconsistent usage (sometimes multi-inning, sometimes short)")
print("  Low stdev  => consistent role specialist")
print()
for role in FOCUS_ROLES:
    players = by_role.get(role, [])
    if not players:
        continue
    stdevs = []
    for p in players:
        ol = p["outs_list"]
        if len(ol) >= 3:
            stdevs.append(statistics.stdev(ol))
    if stdevs:
        print(f"  {role:<22}  n={len(stdevs):>3}  mean_stdev={statistics.mean(stdevs):.3f}  median_stdev={statistics.median(stdevs):.3f}")

# ---------------------------------------------------------------------------
# 9. Proposed inference thresholds summary
# ---------------------------------------------------------------------------
print()
print("=" * 70)
print("PROPOSED APPEARANCE-PATTERN THRESHOLDS FOR ROLE INFERENCE")
print("=" * 70)
print("""
  Signal: avg_outs_per_game
    > 3.5  => multi-inning usage (Long Reliever / spot starter territory)
    3.0–3.5 => clean one-inning specialist
    < 3.0  => sub-inning / late specialist (often Closer or high-lev setup)

  Signal: svhd_rate
    >= 0.70 => strong high-leverage signal (Closer or elite Setup Man)
    0.40–0.69 => moderate (Setup / Closer Committee territory)
    < 0.40  => lower-leverage (Middle / Long)

  Signal: sv_rate
    >= 0.40 => likely true Closer
    0.10–0.39 => Closer Committee or Co-Closer
    < 0.10  => Setup Man or below

  Signal: hld_rate
    >= 0.40 => strong Setup Man signal
    0.20–0.39 => Closer Committee / secondary setup
    < 0.20  => Closer (saves, not holds) or Middle

  Combined rule sketch:
    IF svhd_rate >= 0.70 AND sv_rate >= 0.40                 => Closer
    IF svhd_rate >= 0.70 AND hld_rate >= 0.40                => Setup Man
    IF svhd_rate >= 0.40 AND sv_rate >= 0.10 AND sv_rate < 0.40  => Closer Committee
    IF avg_outs_per_game > 3.5                               => Long Reliever
    IF svhd_rate < 0.30 AND avg_outs_per_game <= 3.5         => Middle Reliever
""")
