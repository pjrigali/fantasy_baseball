"""Co-Closer analysis from the 2026-05-20 FanGraphs snapshot."""
import csv, datetime
from collections import defaultdict

FG_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\2026_fangraphs_closers_depth.csv"
BOX_FILE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\2026_mlb_stats_boxscore.csv"

def safe_int(v, d=0):
    try:
        return int(float(v))
    except Exception:
        return d

with open(FG_FILE, newline="", encoding="utf-8") as f:
    fg_rows = list(csv.DictReader(f))

co_date = "2026-05-20"
co_rows = [r for r in fg_rows if r["date_scraped"] == co_date and r["role"] == "Co-Closer"]
print(f"Co-Closer pitchers on {co_date}: {len(co_rows)}")
for r in co_rows:
    print(f"  {r['team']}: {r['player_name']}  season_sv={r['sv']} season_hld={r['hld']}")

scrape_dt = datetime.date.fromisoformat(co_date)
window_start = scrape_dt - datetime.timedelta(days=14)
box_agg = defaultdict(lambda: {"sv": 0, "hld": 0, "games": 0})

with open(BOX_FILE, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row.get("b_or_p", "").strip().lower() != "pitcher":
            continue
        if safe_int(row.get("did_play", 0)) != 1:
            continue
        if safe_int(row.get("GS", 0)) != 0:
            continue
        try:
            gdt = datetime.date.fromisoformat(row["date"][:10])
        except Exception:
            continue
        if not (window_start <= gdt <= scrape_dt):
            continue
        key = row.get("player_name", "").strip().lower()
        box_agg[key]["sv"] += safe_int(row.get("SV", 0))
        box_agg[key]["hld"] += safe_int(row.get("HLD", 0))
        box_agg[key]["games"] += 1

print()
print("Co-Closer 14-day stats:")
co_teams = defaultdict(list)
for r in co_rows:
    key = r["player_name"].strip().lower()
    r["_sv"] = box_agg[key]["sv"]
    r["_hld"] = box_agg[key]["hld"]
    r["_games"] = box_agg[key]["games"]
    co_teams[r["team"]].append(r)

for team, players in sorted(co_teams.items()):
    print(f"  {team}:")
    for p in players:
        print(f"    {p['player_name']:<25} season_sv={p['sv']:<4} season_hld={p['hld']:<4} "
              f"win_sv={p['_sv']} win_hld={p['_hld']} win_games={p['_games']}")

# Also look at how hot_seat and on_rise appear across ALL snapshots
print()
print("Hot-seat and On-rise across ALL dates:")
for row in fg_rows:
    if row.get("hot_seat", "False") not in ("False", ""):
        print(f"  HOT_SEAT  {row['date_scraped']} {row['team']} {row['player_name']} role={row['role']} hot_seat={row['hot_seat']}")
    if row.get("on_rise", "False") not in ("False", ""):
        print(f"  ON_RISE   {row['date_scraped']} {row['team']} {row['player_name']} role={row['role']} on_rise={row['on_rise']}")
