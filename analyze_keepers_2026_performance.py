"""
Description:
    Evaluates how each team's 2026 keepers have performed through the current season.
    Aggregates actual MLB stats from the daily archive, compares to pre-season projections,
    and produces a per-player verdict (Exceeding / On Track / Underperforming / Injured).

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/2026_local_keepers_actual.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_local_keepers_projected.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_stats_daily_archive.csv

Outputs:
    Prints a formatted keeper performance report to stdout.
    Writes data-lake/01_Bronze/fantasy_baseball/2026_local_keepers_performance.csv
"""

import csv
import os
import sys
sys.stdout.reconfigure(encoding="utf-8")

BASE = r"C:\Users\peter.rigali\desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball"


def load_csv(filename):
    with open(os.path.join(BASE, filename), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def safe_float(val, default=0.0):
    try:
        return float(val) if val not in ("", None) else default
    except (ValueError, TypeError):
        return default


def aggregate_player_stats(daily_rows):
    players = {}
    for row in daily_rows:
        name = row["player_name"]
        bop = row.get("b_or_p", "").strip().lower()
        if name not in players:
            players[name] = {
                "name": name, "type": bop, "G": 0,
                "AB": 0.0, "H": 0.0, "HR": 0.0, "R": 0.0, "RBI": 0.0,
                "SB": 0.0, "TB": 0.0, "B_BB": 0.0, "HBP": 0.0, "SF": 0.0,
                "OUTS": 0.0, "ER": 0.0, "K": 0.0, "P_BB": 0.0, "P_H": 0.0,
                "QS": 0.0, "SV": 0.0, "HLD": 0.0, "SVHD": 0.0, "W": 0.0,
            }
        p = players[name]
        if bop == "batter":
            p["AB"]   += safe_float(row.get("AB"))
            p["H"]    += safe_float(row.get("H"))
            p["HR"]   += safe_float(row.get("HR"))
            p["R"]    += safe_float(row.get("R"))
            p["RBI"]  += safe_float(row.get("RBI"))
            p["SB"]   += safe_float(row.get("SB"))
            p["TB"]   += safe_float(row.get("TB"))
            p["B_BB"] += safe_float(row.get("B_BB"))
            p["HBP"]  += safe_float(row.get("HBP"))
            p["SF"]   += safe_float(row.get("SF"))
            p["G"]    += 1
        else:
            p["OUTS"] += safe_float(row.get("OUTS"))
            p["ER"]   += safe_float(row.get("ER"))
            p["K"]    += safe_float(row.get("K"))
            p["P_BB"] += safe_float(row.get("P_BB"))
            p["P_H"]  += safe_float(row.get("P_H"))
            p["QS"]   += safe_float(row.get("QS"))
            p["SV"]   += safe_float(row.get("SV"))
            p["HLD"]  += safe_float(row.get("HLD"))
            p["SVHD"] += safe_float(row.get("SVHD"))
            p["W"]    += safe_float(row.get("W"))
            p["G"]    += 1
    return players


def compute_rate_stats(p):
    result = dict(p)
    if p["type"] == "batter":
        ab = p["AB"]
        pa = ab + p["B_BB"] + p["HBP"] + p["SF"]
        result["BA"]  = round(p["H"] / ab, 3) if ab > 0 else 0.0
        result["SLG"] = round(p["TB"] / ab, 3) if ab > 0 else 0.0
        obp_den = ab + p["B_BB"] + p["HBP"] + p["SF"]
        result["OBP"] = round((p["H"] + p["B_BB"] + p["HBP"]) / obp_den, 3) if obp_den > 0 else 0.0
        result["OPS"] = round(result["OBP"] + result["SLG"], 3)
        result["R"]   = int(p["R"])
        result["HR"]  = int(p["HR"])
        result["RBI"] = int(p["RBI"])
        result["SB"]  = int(p["SB"])
    else:
        ip = p["OUTS"] / 3.0
        result["IP"]   = round(ip, 1)
        result["ERA"]  = round((p["ER"] * 9) / ip, 2) if ip > 0 else 0.0
        result["WHIP"] = round((p["P_H"] + p["P_BB"]) / ip, 2) if ip > 0 else 0.0
        result["K9"]   = round((p["K"] * 9) / ip, 1) if ip > 0 else 0.0
        result["QS"]   = int(p["QS"])
        result["SVHD"] = int(p["SVHD"])
        result["W"]    = int(p["W"])
    return result


def keeper_verdict(player_type, stats, proj_z, games):
    if games < 5:
        return "Injured/DNP"
    if player_type == "batter":
        ops = stats.get("OPS", 0)
        hr  = stats.get("HR", 0)
        rbi = stats.get("RBI", 0)
        r   = stats.get("R", 0)
        if proj_z >= 5.0:
            good = ops >= 0.850 or (hr >= 10 and rbi >= 35)
            poor = ops < 0.700 and hr < 6
        elif proj_z >= 3.0:
            good = ops >= 0.800 or (hr >= 8 and rbi >= 28)
            poor = ops < 0.680 and hr < 4
        else:
            good = ops >= 0.760 or rbi >= 25
            poor = ops < 0.650
        if good:
            return "Exceeding"
        elif poor:
            return "Underperforming"
        else:
            return "On Track"
    else:
        ip   = stats.get("IP", 0)
        era  = stats.get("ERA", 99)
        whip = stats.get("WHIP", 99)
        svhd = stats.get("SVHD", 0)
        qs   = stats.get("QS", 0)
        if ip < 10 and svhd < 5:
            return "Injured/DNP"
        if proj_z >= 5.0:
            good = (era <= 2.80 and whip <= 1.10) or svhd >= 20
            poor = (era >= 5.00 and ip > 20) or (svhd < 5 and ip < 15)
        elif proj_z >= 3.0:
            good = (era <= 3.20 and whip <= 1.20) or svhd >= 15
            poor = era >= 5.50 or (svhd < 3 and ip < 15)
        else:
            good = era <= 3.50 or svhd >= 10
            poor = era >= 5.50
        if good:
            return "Exceeding"
        elif poor:
            return "Underperforming"
        else:
            return "On Track"


def fmt_batter(s):
    return (f"G={s['G']} R={s['R']} HR={s['HR']} RBI={s['RBI']} "
            f"SB={s['SB']} OPS={s['OPS']:.3f}")


def fmt_pitcher(s):
    return (f"G={s['G']} IP={s['IP']} ERA={s['ERA']:.2f} "
            f"WHIP={s['WHIP']:.2f} K9={s['K9']:.1f} QS={s['QS']} SVHD={s['SVHD']}")


def main():
    keepers_raw    = load_csv("2026_local_keepers_actual.csv")
    projections    = load_csv("2026_local_keepers_projected.csv")
    daily          = load_csv("2026_mlb_stats_daily_archive.csv")

    proj_lookup = {}
    for row in projections:
        proj_lookup[row["Player"]] = row

    agg    = aggregate_player_stats(daily)
    stats  = {name: compute_rate_stats(p) for name, p in agg.items()}

    owner_map = {
        "1": "Brian",  "2": "Pete", "3": "Robbie", "4": "Mike",
        "5": "Dakota", "6": "Isaac/Kaz", "7": "Chad", "8": "Phyllis/Ted",
        "9": "Jack",   "10": "Mack",
    }
    team_name_map = {
        "1": "Fresh Prince of Bueh Ler", "2": "Datalickmyballs",
        "3": "Midnight Muncy's", "4": "Honey Nut Chourios",
        "5": "I Shota the Sheriff", "6": "Drill ya mama",
        "7": "All Rise", "8": "Big Papi",
        "9": "DEVERSity", "10": "Shohei Me the Money",
    }

    output_rows = []
    results_by_team = {}

    for k in keepers_raw:
        team_id   = k["team_id"]
        owner     = owner_map.get(team_id, k["Owner"])
        team_name = team_name_map.get(team_id, "Unknown")
        player    = k["Player"]
        cost_rd   = k["2026 Round"]

        proj = proj_lookup.get(player, {})
        proj_z    = safe_float(proj.get("Blend_Z", 0))
        proj_type = proj.get("Type", "").lower()
        adp_rd    = proj.get("ADP_Round", "--")

        st = stats.get(player)

        if st is None:
            verdict = "No Data"
            stat_str = "No stats found"
            actual_type = proj_type if proj_type else "unknown"
            games = 0
        else:
            actual_type = st["type"] if st["type"] else proj_type
            games = st["G"]
            verdict = keeper_verdict(actual_type, st, proj_z, games)
            stat_str = fmt_batter(st) if actual_type == "batter" else fmt_pitcher(st)

        rec = {
            "team_id": team_id, "team": team_name, "owner": owner,
            "player": player, "type": actual_type,
            "cost_round": cost_rd, "adp_round": adp_rd,
            "proj_blend_z": proj_z, "games": games,
            "stats": stat_str, "verdict": verdict,
        }
        output_rows.append(rec)
        results_by_team.setdefault(team_id, []).append(rec)

    VERDICT_ICON = {
        "Exceeding":       "✓✓",
        "On Track":        "✓",
        "Underperforming": "✗",
        "Injured/DNP":     "—",
        "No Data":         "?",
    }

    print("\n" + "=" * 72)
    print("  2026 KEEPER PERFORMANCE REVIEW")
    print("=" * 72)

    team_order = ["1","2","3","4","5","6","7","8","9","10"]
    for tid in team_order:
        rows = results_by_team.get(tid, [])
        if not rows:
            continue
        print(f"\n{'─'*72}")
        print(f"  {rows[0]['team']} ({rows[0]['owner']})")
        print(f"{'─'*72}")
        scores = {"Exceeding": 2, "On Track": 1, "Underperforming": 0, "Injured/DNP": 0, "No Data": 0}
        total  = sum(scores[r["verdict"]] for r in rows)
        for r in rows:
            icon = VERDICT_ICON[r["verdict"]]
            pz_str = f"ProjZ={r['proj_blend_z']:+.1f}" if r["proj_blend_z"] != 0 else "ProjZ=N/A"
            print(f"  {icon:2s}  {r['player']:<28s} [{r['type'][:3]:3s}]  {pz_str}  Cost=R{r['cost_round']}")
            print(f"        {r['stats']}")
            print(f"        Verdict: {r['verdict']}")
        print(f"\n  Team score: {total}/{len(rows)*2}  ({total/max(len(rows)*2,1)*100:.0f}%)")

    print("\n" + "=" * 72)
    print("  LEAGUE SUMMARY")
    print("=" * 72)
    team_scores = []
    for tid in team_order:
        rows = results_by_team.get(tid, [])
        if not rows:
            continue
        scores = {"Exceeding": 2, "On Track": 1, "Underperforming": 0, "Injured/DNP": 0, "No Data": 0}
        total    = sum(scores[r["verdict"]] for r in rows)
        max_s    = len(rows) * 2
        exc      = sum(1 for r in rows if r["verdict"] == "Exceeding")
        under    = sum(1 for r in rows if r["verdict"] == "Underperforming")
        injured  = sum(1 for r in rows if r["verdict"] == "Injured/DNP")
        team_scores.append((rows[0]["team"], rows[0]["owner"], total, max_s, exc, under, injured))

    team_scores.sort(key=lambda x: -x[2])
    print(f"\n  {'Team':<36s} {'Score':>6s}  {'%':>5s}  {'Exc':>4s}  {'Under':>5s}  {'Inj':>4s}")
    print(f"  {'─'*36} {'─'*6}  {'─'*5}  {'─'*4}  {'─'*5}  {'─'*4}")
    for t, o, sc, mx, exc, under, inj in team_scores:
        pct = sc / max(mx, 1) * 100
        print(f"  {t:<36s} {sc:>4d}/{mx:<2d}  {pct:>4.0f}%  {exc:>4d}  {under:>5d}  {inj:>4d}")

    out_path = os.path.join(BASE, "2026_local_keepers_performance.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "team_id","team","owner","player","type","cost_round","adp_round",
            "proj_blend_z","games","stats","verdict"
        ])
        writer.writeheader()
        writer.writerows(output_rows)
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
