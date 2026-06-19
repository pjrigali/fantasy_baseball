"""
Description:
    Trade analysis for Corbin Carroll (OF, ARI) vs Bryan Woo (SP, SEA).
    Aggregates per-game box score stats across 2023-2026 from the MLB daily
    stats files and applies the friend's league scoring system to produce a
    like-for-like fantasy points comparison by year plus 2026 full-season
    projections.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_daily_{year}.csv  (2023-2026)
    - data-lake/01_Bronze/fantasy_baseball/player_batter_projections_2026.csv
    - data-lake/01_Bronze/fantasy_baseball/player_pitcher_projections_2026.csv

Outputs:
    Printed multi-year summary table to console.
"""

import csv
import os
from collections import defaultdict

# Go up 5 levels to get the workspace root containing data-lake or data-lake
_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
BASE = None
for name in ('data-lake', 'data-lake'):
    p = os.path.join(_root, name, '01_Bronze', 'fantasy_baseball')
    if os.path.isdir(p):
        BASE = p
        break
if not BASE:
    BASE = os.path.join(_root, 'data-lake', '01_Bronze', 'fantasy_baseball')

CARROLL_ID = "682998"
WOO_ID     = "693433"
YEARS      = [2023, 2024, 2025, 2026]

# ---------------------------------------------------------------------------
# Scoring system (friend's league)
# Batting:  TB +1, BB +1, R +1, RBI +1, SB +1, K -1
# Pitching: OUTS x1 (= IP x3), ER -2, W +2, L -2, SV +5, BS -1,
#           K +1, H -1, BB -1, QS +5, HD +2
# ---------------------------------------------------------------------------

def batter_pts(tb, bb, r, rbi, sb, k):
    return tb + bb + r + rbi + sb - k

def pitcher_pts(outs, er, w, l, sv, bs, k, h, bb, qs, hd):
    return outs - (er * 2) + (w * 2) - (l * 2) + (sv * 5) - bs + k - h - bb + (qs * 5) + (hd * 2)

def safe(val, default=0.0):
    try:
        return float(val) if val not in ("", None) else default
    except (ValueError, TypeError):
        return default

# ---------------------------------------------------------------------------
# Column name normalisation — 2023/24/25 use camelCase, 2026 uses snake_case
# ---------------------------------------------------------------------------

def get_player_id(row):
    return row.get("playerId") or row.get("player_id", "")

# ---------------------------------------------------------------------------
# Aggregate yearly stats from stats_mlb_daily_{year}.csv
# ---------------------------------------------------------------------------

BATTER_COLS  = ["TB", "B_BB", "R", "RBI", "SB", "SO"]
PITCHER_COLS = ["OUTS", "ER", "W", "L", "SV", "K", "P_H", "P_BB", "QS", "HLD"]

def aggregate_year(year):
    path = f"{BASE}\\stats_mlb_daily_{year}.csv"
    if not os.path.exists(path):
        path = f"{BASE}\\stats_mlb_boxscore_{year}.csv"
    if not os.path.exists(path):
        path = f"{BASE}\\stats_mlb_daily_{year}_archive.csv"
    if not os.path.exists(path):
        return defaultdict(float), defaultdict(float)

    carroll = defaultdict(float)
    woo     = defaultdict(float)

    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pid  = get_player_id(row)
            borp = row.get("b_or_p", "")

            if pid == CARROLL_ID and borp == "batter":
                for col in BATTER_COLS:
                    carroll[col] += safe(row.get(col, 0))
                carroll["G"] += 1

            elif pid == WOO_ID and borp == "pitcher":
                for col in PITCHER_COLS:
                    woo[col] += safe(row.get(col, 0))
                woo["GS"] += safe(row.get("GS", 0))
                woo["G"]  += 1

    return carroll, woo

# ---------------------------------------------------------------------------
# 2026 full-season projections
# ---------------------------------------------------------------------------

def load_carroll_proj():
    with open(f"{BASE}\\player_batter_projections_2026.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if "Carroll" in row.get("Player", "").replace("\xa0", " "):
                h   = safe(row["H"])
                hr  = safe(row["HR"])
                b2  = safe(row["2B"])
                b3  = safe(row["3B"])
                tb  = h + b2 + (2 * b3) + (3 * hr)
                bb  = safe(row["BB"])
                r   = safe(row["R"])
                rbi = safe(row["RBI"])
                sb  = safe(row["SB"])
                k   = safe(row["SO"])
                pts = batter_pts(tb, bb, r, rbi, sb, k)
                return {"TB": tb, "B_BB": bb, "R": r, "RBI": rbi,
                        "SB": sb, "SO": k, "pts": pts, "G": 145}
    return {}

def load_woo_proj():
    with open(f"{BASE}\\player_pitcher_projections_2026.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = row.get("Player", "").replace("\xa0", " ")
            if "Woo" in name and "Bryan" in name:
                ip  = safe(row["IP"])
                er  = safe(row["ER"])
                w   = safe(row["W"])
                l   = safe(row["L"])
                sv  = safe(row["SV"])
                k   = safe(row["K"])
                h   = safe(row["H"])
                bb  = safe(row["BB"])
                gs  = safe(row["GS"])
                qs  = gs * 0.65        # QS not in projection file — estimate 65% of GS
                pts = pitcher_pts(ip * 3, er, w, l, sv, 0, k, h, bb, qs, 0)
                return {"OUTS": ip * 3, "ER": er, "W": w, "L": l, "SV": sv,
                        "K": k, "P_H": h, "P_BB": bb, "QS": qs, "HLD": 0,
                        "pts": pts, "GS": gs, "G": gs}
    return {}

# ---------------------------------------------------------------------------
# Build results table
# ---------------------------------------------------------------------------

results = {}
for yr in YEARS:
    c, w = aggregate_year(yr)
    c_pts = batter_pts(c["TB"], c["B_BB"], c["R"], c["RBI"], c["SB"], c["SO"])
    w_pts = pitcher_pts(w["OUTS"], w["ER"], w["W"], w["L"], w["SV"], 0,
                        w["K"], w["P_H"], w["P_BB"], w["QS"], w["HLD"])
    c["pts"] = c_pts
    w["pts"] = w_pts
    results[yr] = (c, w)

carroll_proj = load_carroll_proj()
woo_proj     = load_woo_proj()

# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

SEP = "=" * 78

print(SEP)
print("TRADE ANALYSIS: Corbin Carroll (OF/ARI)  for  Bryan Woo (SP/SEA)")
print("Scoring: TB+1 BB+1 R+1 RBI+1 SB+1 K-1 | OUTS+1 ER-2 W+2 L-2 SV+5 BS-1 K+1 H-1 BB-1 QS+5 HD+2")
print(SEP)

# --- Carroll multi-year ---
print("\n--- CORBIN CARROLL (batter) ---")
print(f"  {'Year':<10} {'G':>4} {'TB':>5} {'BB':>4} {'R':>4} {'RBI':>4} {'SB':>4} {'K':>4} {'PTS':>6} {'PTS/G':>7}")
print(f"  {'-'*62}")
for yr in YEARS:
    c = results[yr][0]
    g = int(c["G"]) or 1
    ppg = c["pts"] / g
    label = f"{yr} YTD" if yr == 2026 else str(yr)
    print(f"  {label:<10} {g:>4} {int(c['TB']):>5} {int(c['B_BB']):>4} {int(c['R']):>4} "
          f"{int(c['RBI']):>4} {int(c['SB']):>4} {int(c['SO']):>4} {int(c['pts']):>6} {ppg:>7.1f}")

if carroll_proj:
    g   = int(carroll_proj["G"])
    ppg = carroll_proj["pts"] / g
    print(f"  {'2026 Proj':<10} {'~'+str(g):>4} {int(carroll_proj['TB']):>5} {int(carroll_proj['B_BB']):>4} "
          f"{int(carroll_proj['R']):>4} {int(carroll_proj['RBI']):>4} {int(carroll_proj['SB']):>4} "
          f"{int(carroll_proj['SO']):>4} {int(carroll_proj['pts']):>6} {ppg:>7.1f}")

# --- Woo multi-year ---
print(f"\n--- BRYAN WOO (starter) ---")
print(f"  {'Year':<10} {'G':>4} {'IP':>6} {'ER':>4} {'W':>3} {'L':>3} {'K':>4} {'H':>4} {'BB':>4} {'QS':>4} {'PTS':>6} {'PTS/G':>7}")
print(f"  {'-'*72}")
for yr in YEARS:
    w = results[yr][1]
    g = int(w["G"]) or 1
    ip = w["OUTS"] / 3
    ppg = w["pts"] / g if g > 0 else 0
    label = f"{yr} YTD" if yr == 2026 else str(yr)
    print(f"  {label:<10} {g:>4} {ip:>6.1f} {int(w['ER']):>4} {int(w['W']):>3} {int(w['L']):>3} "
          f"{int(w['K']):>4} {int(w['P_H']):>4} {int(w['P_BB']):>4} {int(w['QS']):>4} "
          f"{int(w['pts']):>6} {ppg:>7.1f}")

if woo_proj:
    g   = int(woo_proj["GS"])
    ip  = woo_proj["OUTS"] / 3
    ppg = woo_proj["pts"] / g
    print(f"  {'2026 Proj':<10} {'~'+str(g):>4} {ip:>6.1f} {int(woo_proj['ER']):>4} {int(woo_proj['W']):>3} "
          f"{int(woo_proj['L']):>3} {int(woo_proj['K']):>4} {int(woo_proj['P_H']):>4} "
          f"{int(woo_proj['P_BB']):>4} {int(woo_proj['QS']):>4} {int(woo_proj['pts']):>6} {ppg:>7.1f}")

# --- Head-to-head by year ---
print(f"\n--- HEAD-TO-HEAD FANTASY POINTS BY YEAR ---")
print(f"  {'Year':<10} {'Carroll':>10} {'Woo':>10} {'Woo Adv':>10} {'Carroll/G':>10} {'Woo/G':>8}")
print(f"  {'-'*60}")
for yr in YEARS:
    c   = results[yr][0]
    w   = results[yr][1]
    cg  = int(c["G"]) or 1
    wg  = int(w["G"]) or 1
    label = f"{yr} YTD" if yr == 2026 else str(yr)
    print(f"  {label:<10} {int(c['pts']):>10} {int(w['pts']):>10} "
          f"{int(w['pts'] - c['pts']):>+10} {c['pts']/cg:>10.1f} {w['pts']/wg:>8.1f}")

if carroll_proj and woo_proj:
    c_pace = (results[2026][0]["pts"] / (int(results[2026][0]["G"]) or 1)) * 162
    w_pace = (results[2026][1]["pts"] / (int(results[2026][1]["G"]) or 1)) * 31
    print(f"  {'2026 Pace':<10} {int(c_pace):>10} {int(w_pace):>10} {int(w_pace - c_pace):>+10}")
    print(f"  {'2026 Proj':<10} {int(carroll_proj['pts']):>10} {int(woo_proj['pts']):>10} "
          f"{int(woo_proj['pts'] - carroll_proj['pts']):>+10}")

print(f"\n  Notes:")
print(f"  * QS uses actual QS column from stats_mlb_daily files for all years.")
print(f"  * QS for 2026 projection estimated at 65% of GS (not in projection file).")
print(f"  * Woo MLB debut was mid-2023 — partial season expected.")
print(f"  * Carroll IDs as batter only; Woo as pitcher only.")
print(SEP)
