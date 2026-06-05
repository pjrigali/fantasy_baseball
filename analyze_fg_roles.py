"""
Description: Reverse-engineer the quantitative logic FanGraphs used to assign pitcher
role labels (Closer, Co-Closer, Closer Committee, Setup Man, Middle Reliever) on their
Roster Resource Closer Depth Chart. Compares FanGraphs season stats and role labels
against recent 14-day boxscore performance.

Source Data:
  - closer_depth_fangraphs_2026.csv  (multi-date snapshot; uses most-recent date)
  - stats_mlb_boxscore_2026.csv      (daily pitcher game lines)

Outputs: Printed report to stdout.
"""

import csv
import datetime
from collections import defaultdict

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FG_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\closer_depth_fangraphs_2026.csv"
BOX_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\stats_mlb_boxscore_2026.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def safe_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default

def median(lst):
    if not lst:
        return None
    s = sorted(lst)
    n = len(s)
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2

def mean(lst):
    return sum(lst) / len(lst) if lst else None

def pct(num, denom):
    return round(100 * num / denom, 1) if denom else 0.0

# ---------------------------------------------------------------------------
# 1. Load FanGraphs — most recent snapshot
# ---------------------------------------------------------------------------
fg_rows = []
with open(FG_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        fg_rows.append(row)

latest_date = max(r["date_scraped"] for r in fg_rows)
fg_latest = [r for r in fg_rows if r["date_scraped"] == latest_date]
scrape_dt = datetime.date.fromisoformat(latest_date)
window_start = scrape_dt - datetime.timedelta(days=14)

print("=" * 70)
print(f"FANGRAPHS SNAPSHOT DATE : {latest_date}")
print(f"BOXSCORE WINDOW         : {window_start} to {scrape_dt}")
print(f"TOTAL FG PITCHERS       : {len(fg_latest)}")
print("=" * 70)

# Count per role
role_counts = defaultdict(int)
for r in fg_latest:
    role_counts[r["role"]] += 1
print("\n--- ROLE COUNTS ---")
for role, cnt in sorted(role_counts.items(), key=lambda x: -x[1]):
    print(f"  {role:<25} {cnt:>3}")

# ---------------------------------------------------------------------------
# 2. Load boxscore — 14-day window, relief pitchers only
# ---------------------------------------------------------------------------
# Aggregate per player: sv, hld, svhd, games
box_agg = defaultdict(lambda: {"sv": 0, "hld": 0, "svhd": 0, "games": 0})

with open(BOX_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row.get("b_or_p", "").strip().lower() != "pitcher":
            continue
        if safe_int(row.get("did_play", 0)) != 1:
            continue
        if safe_int(row.get("GS", 0)) != 0:
            continue
        try:
            game_dt = datetime.date.fromisoformat(row["date"][:10])
        except (ValueError, KeyError):
            continue
        if not (window_start <= game_dt <= scrape_dt):
            continue

        name_key = row.get("player_name", "").strip().lower()
        agg = box_agg[name_key]
        agg["sv"]    += safe_int(row.get("SV", 0))
        agg["hld"]   += safe_int(row.get("HLD", 0))
        agg["svhd"]  += safe_int(row.get("SVHD", 0))
        agg["games"] += 1

print(f"\nBoxscore relief pitcher records matched: {len(box_agg)} unique names")

# ---------------------------------------------------------------------------
# 3. Match FG players to boxscore
# ---------------------------------------------------------------------------
matched, unmatched = 0, []
for r in fg_latest:
    key = r["player_name"].strip().lower()
    if key in box_agg:
        r["_sv"]    = box_agg[key]["sv"]
        r["_hld"]   = box_agg[key]["hld"]
        r["_svhd"]  = box_agg[key]["svhd"]
        r["_games"] = box_agg[key]["games"]
        matched += 1
    else:
        r["_sv"] = r["_hld"] = r["_svhd"] = r["_games"] = 0
        unmatched.append(r["player_name"])

print(f"\nFG pitchers matched   : {matched}")
print(f"FG pitchers unmatched : {len(unmatched)}")
if unmatched:
    print("  Unmatched names:", ", ".join(sorted(unmatched)[:30]))

# ---------------------------------------------------------------------------
# 4. Stats by role
# ---------------------------------------------------------------------------
def stats_for_role(rows, field):
    vals = [r[field] for r in rows]
    return {
        "median": median(vals),
        "mean":   round(mean(vals), 2) if vals else None,
        "min":    min(vals) if vals else None,
        "max":    max(vals) if vals else None,
    }

ROLE_ORDER = ["Closer", "Co-Closer", "Closer Committee", "Setup Man", "Middle Reliever"]

print("\n" + "=" * 70)
print("SECTION 4: RECENT 14-DAY STATS BY ROLE")
print("=" * 70)

rows_by_role = defaultdict(list)
for r in fg_latest:
    rows_by_role[r["role"]].append(r)

fields = [("win_sv", "_sv"), ("win_hld", "_hld"), ("win_games", "_games"), ("win_svhd", "_svhd")]

for role in ROLE_ORDER:
    rrows = rows_by_role.get(role, [])
    if not rrows:
        continue
    n = len(rrows)
    print(f"\n  [{role}]  n={n}")
    for label, field in fields:
        vals = [r[field] for r in rrows]
        print(f"    {label:<12}  median={median(vals):<5}  mean={round(mean(vals),2):<6}  "
              f"min={min(vals):<4}  max={max(vals)}")

    # Distribution for sv and hld
    sv_vals  = [r["_sv"]  for r in rrows]
    hld_vals = [r["_hld"] for r in rrows]
    print(f"    SV distribution  : 0={pct(sum(v==0 for v in sv_vals),n)}%  "
          f">=1={pct(sum(v>=1 for v in sv_vals),n)}%  "
          f">=2={pct(sum(v>=2 for v in sv_vals),n)}%  "
          f">=3={pct(sum(v>=3 for v in sv_vals),n)}%")
    print(f"    HLD distribution : 0={pct(sum(v==0 for v in hld_vals),n)}%  "
          f">=1={pct(sum(v>=1 for v in hld_vals),n)}%  "
          f">=2={pct(sum(v>=2 for v in hld_vals),n)}%  "
          f">=3={pct(sum(v>=3 for v in hld_vals),n)}%")

# ---------------------------------------------------------------------------
# 5. Threshold rules
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 5: THRESHOLD RULE EXPLORATION")
print("=" * 70)

# 5a. Can win_sv separate Closer from Setup Man?
print("\n--- 5a. Closer vs Setup Man: win_sv thresholds ---")
for threshold in [0, 1, 2, 3]:
    for role in ["Closer", "Co-Closer", "Closer Committee", "Setup Man", "Middle Reliever"]:
        rrows = rows_by_role.get(role, [])
        if not rrows:
            continue
        n = len(rrows)
        pct_ge = pct(sum(r["_sv"] >= threshold for r in rrows), n)
        print(f"  win_sv >= {threshold}  [{role:<20}] {pct_ge:>5}%  (n={n})")
    print()

# 5b. win_hld: Setup Man vs Middle Reliever
print("--- 5b. Setup Man vs Middle Reliever: win_hld thresholds ---")
for threshold in [0, 1, 2, 3]:
    for role in ["Setup Man", "Middle Reliever"]:
        rrows = rows_by_role.get(role, [])
        if not rrows:
            continue
        n = len(rrows)
        pct_ge = pct(sum(r["_hld"] >= threshold for r in rrows), n)
        print(f"  win_hld >= {threshold}  [{role:<20}] {pct_ge:>5}%  (n={n})")
    print()

# 5c. Co-Closer: do both pitchers have comparable win_sv?
print("--- 5c. Co-Closer teams: both pitchers' win_sv ---")
co_teams = defaultdict(list)
for r in rows_by_role.get("Co-Closer", []):
    co_teams[r["team"]].append(r)
for team, players in sorted(co_teams.items()):
    sv_list = [(p["player_name"], p["_sv"]) for p in players]
    print(f"  {team}: " + ", ".join(f"{name} sv={sv}" for name, sv in sv_list))

# 5d. Closer Committee: do 3+ pitchers have win_sv >= 1?
print("\n--- 5d. Closer Committee teams: win_sv distribution ---")
cc_teams = defaultdict(list)
for r in rows_by_role.get("Closer Committee", []):
    cc_teams[r["team"]].append(r)
for team, players in sorted(cc_teams.items()):
    sv_ge1 = sum(p["_sv"] >= 1 for p in players)
    detail = ", ".join(f"{p['player_name']}({p['_sv']}sv)" for p in players)
    print(f"  {team} [{len(players)} pitchers, {sv_ge1} with sv>=1]: {detail}")

# ---------------------------------------------------------------------------
# 6. Season stats by role
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 6: FG SEASON STATS DISTRIBUTIONS BY ROLE")
print("=" * 70)

season_fields = [("era", "era"), ("sv", "sv"), ("hld", "hld"), ("sd", "sd"), ("md", "md"), ("k9", "k9")]

for role in ROLE_ORDER:
    rrows = rows_by_role.get(role, [])
    if not rrows:
        continue
    print(f"\n  [{role}]  n={len(rrows)}")
    for label, field in season_fields:
        vals = [safe_float(r.get(field)) for r in rrows]
        non_zero = [v for v in vals if v > 0]
        print(f"    {label:<6}  median={median(vals):<7}  mean={round(mean(vals),2):<7}  "
              f"min={round(min(vals),2):<6}  max={round(max(vals),2)}")

# Season SV thresholds
print("\n--- Season SV thresholds by role ---")
for threshold in [1, 3, 5, 8, 10]:
    for role in ROLE_ORDER:
        rrows = rows_by_role.get(role, [])
        if not rrows:
            continue
        n = len(rrows)
        pct_ge = pct(sum(safe_float(r.get("sv", 0)) >= threshold for r in rrows), n)
        print(f"  season_sv >= {threshold:>2}  [{role:<20}] {pct_ge:>5}%  (n={n})")
    print()

# Season HLD thresholds
print("--- Season HLD thresholds by role ---")
for threshold in [1, 3, 5, 8, 10]:
    for role in ROLE_ORDER:
        rrows = rows_by_role.get(role, [])
        if not rrows:
            continue
        n = len(rrows)
        pct_ge = pct(sum(safe_float(r.get("hld", 0)) >= threshold for r in rrows), n)
        print(f"  season_hld >= {threshold:>2}  [{role:<20}] {pct_ge:>5}%  (n={n})")
    print()

# ---------------------------------------------------------------------------
# 7. Hot Seat pitchers
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 7: HOT SEAT PITCHERS")
print("=" * 70)

hot_seat = [r for r in fg_latest if r.get("hot_seat", "").strip().lower() in ("true", "1", "yes")]
regular_closers = [r for r in rows_by_role.get("Closer", [])
                   if r.get("hot_seat", "").strip().lower() not in ("true", "1", "yes")]

print(f"\nHot-seat pitchers: {len(hot_seat)}")
for r in hot_seat:
    print(f"  {r['player_name']:<25} role={r['role']:<20} "
          f"era={r.get('era','?'):<6} sv={r.get('sv','?'):<4} "
          f"win_sv={r['_sv']} win_hld={r['_hld']} win_games={r['_games']}")

if hot_seat and regular_closers:
    print(f"\nHot-seat vs Regular Closer comparison (recent 14-day):")
    hs_sv    = [r["_sv"]    for r in hot_seat]
    hs_hld   = [r["_hld"]   for r in hot_seat]
    hs_games = [r["_games"] for r in hot_seat]
    rc_sv    = [r["_sv"]    for r in regular_closers]
    rc_hld   = [r["_hld"]   for r in regular_closers]
    rc_games = [r["_games"] for r in regular_closers]
    print(f"  {'Metric':<12} {'Hot Seat':>12} {'Reg Closer':>12}")
    for label, hs_v, rc_v in [("sv mean", mean(hs_sv), mean(rc_sv)),
                                ("sv median", median(hs_sv), median(rc_sv)),
                                ("hld mean", mean(hs_hld), mean(rc_hld)),
                                ("games mean", mean(hs_games), mean(rc_games))]:
        print(f"  {label:<12} {round(hs_v,2) if hs_v is not None else 'N/A':>12} "
              f"{round(rc_v,2) if rc_v is not None else 'N/A':>12}")

    # Season ERA
    hs_era = [safe_float(r.get("era")) for r in hot_seat]
    rc_era = [safe_float(r.get("era")) for r in regular_closers]
    print(f"  {'ERA mean':<12} {round(mean(hs_era),2) if hs_era else 'N/A':>12} "
          f"{round(mean(rc_era),2) if rc_era else 'N/A':>12}")

# ---------------------------------------------------------------------------
# 8. On the Rise pitchers
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("SECTION 8: ON THE RISE PITCHERS")
print("=" * 70)

on_rise = [r for r in fg_latest if r.get("on_rise", "").strip().lower() in ("true", "1", "yes")]
print(f"\nOn-the-rise pitchers: {len(on_rise)}")
for r in on_rise:
    print(f"  {r['player_name']:<25} role={r['role']:<20} "
          f"era={r.get('era','?'):<6} sv={r.get('sv','?'):<4} hld={r.get('hld','?'):<4} "
          f"win_sv={r['_sv']} win_hld={r['_hld']} win_games={r['_games']}")

if on_rise:
    rise_sv    = [r["_sv"]    for r in on_rise]
    rise_hld   = [r["_hld"]   for r in on_rise]
    rise_games = [r["_games"] for r in on_rise]
    print(f"\n  On-the-rise 14-day summary: sv mean={round(mean(rise_sv),2)}  "
          f"hld mean={round(mean(rise_hld),2)}  games mean={round(mean(rise_games),2)}")
    rise_era = [safe_float(r.get("era")) for r in on_rise]
    print(f"  Season ERA mean={round(mean(rise_era),2)}  "
          f"Season ERA range={round(min(rise_era),2)}-{round(max(rise_era),2)}")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
