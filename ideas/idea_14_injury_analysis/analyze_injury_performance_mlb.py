"""
Description: Analyze player performance changes (before vs. after injury) over a 28-game active window.
             Standardizes player categories using Z-score deltas to evaluate overall performance impact.
             Groups findings by injury category and IL placement length (7-day, 10-day, 15-day, 60-day).
Source Data: stats_mlb_season_transactions_{year}.csv, stats_mlb_daily_{year}.csv, stats_mlb_boxscore_2026.csv
Outputs: c:/Users/peter/Desktop/vscode/main/fantasy_baseball/ideas/idea_14_injury_analysis/injury_performance_impact_report.md
"""
import os
import csv
import math
from datetime import datetime, date
from collections import defaultdict

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
DATA_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')
REPORT_PATH = SCRIPT_DIR

def log_event(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def parse_date(date_str):
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def int_val(val, default=0):
    if val is None or val == '':
        return default
    try:
        return int(float(val))
    except ValueError:
        return default

def float_val(val, default=0.0):
    if val is None or val == '':
        return default
    try:
        return float(val)
    except ValueError:
        return default

def get_val(row, keys, default=None):
    for k in keys:
        if k in row:
            return row[k]
    return default

def categorize_injury(description):
    desc = description.lower()
    categories = {
        "Elbow/UCL": ["elbow", "ucl", "tommy john", "flexor", "forearm"],
        "Shoulder": ["shoulder", "rotator cuff", "capsule", "labrum", "subluxation"],
        "Hamstring": ["hamstring"],
        "Oblique/Rib": ["oblique", "rib", "intercostal", "abdominal"],
        "Knee": ["knee", "acl", "meniscus", "patella"],
        "Wrist/Hand/Finger": ["wrist", "hand", "finger", "thumb", "carpal", "fractured hand"],
        "Ankle/Foot": ["ankle", "foot", "toe", "achilles", "heel", "plantar"],
        "Back/Spine": ["back", "spine", "lumbar", "thoracic"],
        "Concussion": ["concussion"],
    }
    for cat, keywords in categories.items():
        for kw in keywords:
            if kw in desc:
                return cat
    return "Other/Unspecified"

def parse_injury_details(description):
    parts = description.split(".")
    if len(parts) > 1:
        reason = parts[1].strip()
        if reason:
            return reason
    return "Unspecified Injury"

def parse_il_duration(description):
    desc = description.lower()
    if "10-day" in desc:
        return 10
    elif "15-day" in desc:
        return 15
    elif "60-day" in desc:
        return 60
    elif "7-day" in desc:
        return 7
    return 10

def reconstruct_completed_stints(year):
    csv_file = os.path.join(DATA_PATH, f"stats_mlb_season_transactions_{year}.csv")
    if not os.path.exists(csv_file):
        return []
        
    stints = []
    active_stints = {}
    
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tx_date = parse_date(row["date"])
                player_id = row["player_id"]
                player_name = row["player_name"]
                team_name = row["team_name"]
                desc = row["description"]
                
                if not tx_date or not player_id:
                    continue
                    
                desc_lower = desc.lower()
                
                if "placed" in desc_lower or "transferred" in desc_lower:
                    severity = parse_il_duration(desc)
                    reason = parse_injury_details(desc)
                    category = categorize_injury(desc)
                    
                    if player_id in active_stints:
                        stint = active_stints[player_id]
                        stint["severity"] = max(stint["severity"], severity)
                        if reason != "Unspecified Injury":
                            stint["reason"] = reason
                            stint["category"] = category
                    else:
                        active_stints[player_id] = {
                            "player_id": player_id,
                            "player_name": player_name,
                            "team_name": team_name,
                            "start_date": tx_date,
                            "end_date": None,
                            "severity": severity,
                            "reason": reason,
                            "category": category,
                            "status": "Ongoing",
                            "year": year
                        }
                        
                elif "activated" in desc_lower:
                    if player_id in active_stints:
                        stint = active_stints[player_id]
                        stint["end_date"] = tx_date
                        stint["status"] = "Completed"
                        stints.append(stint)
                        del active_stints[player_id]
                        
    except Exception as e:
        log_event(f"Error reconstructing stints: {e}")
        
    return [s for s in stints if s["status"] == "Completed" and s["end_date"] and s["start_date"]]

def did_player_participate(row, b_or_p):
    if b_or_p == 'batter':
        ab = int_val(get_val(row, ['AB']))
        bb = int_val(get_val(row, ['B_BB']))
        hbp = int_val(get_val(row, ['HBP']))
        sf = int_val(get_val(row, ['SF']))
        return (ab + bb + hbp + sf) > 0
    else:
        outs = int_val(get_val(row, ['OUTS']))
        er = get_val(row, ['ER'])
        k = int_val(get_val(row, ['K']))
        p_bb = int_val(get_val(row, ['P_BB']))
        p_h = int_val(get_val(row, ['P_H']))
        return outs > 0 or er is not None or k > 0 or p_bb > 0 or p_h > 0

def load_daily_stats_lookup(year):
    if year == 2026:
        filename = "stats_mlb_boxscore_2026.csv"
    else:
        filename = f"stats_mlb_daily_{year}.csv"
        
    csv_file = os.path.join(DATA_PATH, filename)
    if not os.path.exists(csv_file):
        return {}
        
    lookup = defaultdict(list)
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                p_id = get_val(row, ['player_id', 'playerId'])
                d_str = get_val(row, ['date'])
                b_or_p = get_val(row, ['b_or_p'])
                
                if not p_id or not d_str or not b_or_p:
                    continue
                    
                d = parse_date(d_str)
                if not d:
                    continue
                    
                if did_player_participate(row, b_or_p):
                    lookup[p_id].append({
                        "date": d,
                        "b_or_p": b_or_p,
                        "row": row
                    })
        for p_id in lookup:
            lookup[p_id].sort(key=lambda x: x["date"])
    except Exception as e:
        log_event(f"Error loading stats lookup: {e}")
        
    return lookup

def calculate_batter_metrics(games):
    if not games:
        return None
    total_g = len(games)
    total_ab = 0
    total_h = 0
    total_bb = 0
    total_hbp = 0
    total_sf = 0
    total_tb = 0
    total_r = 0
    total_hr = 0
    total_rbi = 0
    total_sb = 0
    for g in games:
        row = g["row"]
        total_ab += int_val(get_val(row, ['AB']))
        total_h += int_val(get_val(row, ['H']))
        total_bb += int_val(get_val(row, ['B_BB']))
        total_hbp += int_val(get_val(row, ['HBP']))
        total_sf += int_val(get_val(row, ['SF']))
        total_tb += int_val(get_val(row, ['TB']))
        total_r += int_val(get_val(row, ['R']))
        total_hr += int_val(get_val(row, ['HR']))
        total_rbi += int_val(get_val(row, ['RBI']))
        total_sb += int_val(get_val(row, ['SB']))
    obp = 0.0
    slg = 0.0
    obp_denom = total_ab + total_bb + total_hbp + total_sf
    if obp_denom > 0:
        obp = (total_h + total_bb + total_hbp) / obp_denom
    if total_ab > 0:
        slg = total_tb / total_ab
    scale = 28.0 / total_g
    return {
        "games": total_g,
        "OPS": obp + slg,
        "R": total_r * scale,
        "HR": total_hr * scale,
        "RBI": total_rbi * scale,
        "SB": total_sb * scale
    }

def calculate_pitcher_metrics(games):
    if not games:
        return None
    total_g = len(games)
    total_outs = 0
    total_er = 0
    total_ph = 0
    total_pbb = 0
    total_k = 0
    total_qs = 0
    total_svhd = 0
    total_gs = 0
    for g in games:
        row = g["row"]
        total_outs += int_val(get_val(row, ['OUTS']))
        total_er += int_val(get_val(row, ['ER']))
        total_ph += int_val(get_val(row, ['P_H']))
        total_pbb += int_val(get_val(row, ['P_BB']))
        total_k += int_val(get_val(row, ['K']))
        total_qs += int_val(get_val(row, ['QS']))
        total_svhd += int_val(get_val(row, ['SVHD']))
        total_gs += int_val(get_val(row, ['GS']))
    if total_outs == 0:
        return None
    ip = total_outs / 3.0
    era = (total_er * 27.0) / total_outs
    whip = (total_ph + total_pbb) * 3.0 / total_outs
    k9 = (total_k * 27.0) / total_outs
    is_sp = (total_gs / total_g) >= 0.3
    scale = 28.0 / total_g
    return {
        "games": total_g,
        "is_sp": is_sp,
        "ERA": era,
        "WHIP": whip,
        "K9": k9,
        "QS": total_qs * scale,
        "SVHD": total_svhd * scale
    }

def std_dev(lst):
    n = len(lst)
    if n <= 1:
        return 1.0
    mean = sum(lst) / n
    variance = sum((x - mean) ** 2 for x in lst) / (n - 1)
    std = math.sqrt(variance)
    return std if std > 0 else 1.0

def get_performance_diffs(pre, post, is_pitcher):
    diff = {}
    if is_pitcher:
        diff["ERA"] = post["ERA"] - pre["ERA"]
        diff["WHIP"] = post["WHIP"] - pre["WHIP"]
        diff["K9"] = post["K9"] - pre["K9"]
        diff["QS"] = post["QS"] - pre["QS"]
        diff["SVHD"] = post["SVHD"] - pre["SVHD"]
    else:
        diff["OPS"] = post["OPS"] - pre["OPS"]
        diff["R"] = post["R"] - pre["R"]
        diff["HR"] = post["HR"] - pre["HR"]
        diff["RBI"] = post["RBI"] - pre["RBI"]
        diff["SB"] = post["SB"] - pre["SB"]
    return diff

def main():
    log_event("Starting Post-Injury Performance Impact Analysis (28-game windows)...")
    
    stints_all = []
    
    # Read stints across all years
    for year in [2023, 2024, 2025, 2026]:
        log_event(f"Processing season: {year}")
        stints = reconstruct_completed_stints(year)
        daily_lookup = load_daily_stats_lookup(year)
        
        for stint in stints:
            p_id = stint["player_id"]
            if p_id not in daily_lookup:
                continue
            p_games = daily_lookup[p_id]
            before_games = [g for g in p_games if g["date"] < stint["start_date"]][-28:]
            after_games = [g for g in p_games if g["date"] >= stint["end_date"]][:28]
            
            if len(before_games) < 10 or len(after_games) < 10:
                continue
                
            b_or_p = p_games[0]["b_or_p"]
            is_pitcher = (b_or_p == "pitcher")
            
            stint_data = {
                "player_name": stint["player_name"],
                "team_name": stint["team_name"],
                "category": stint["category"],
                "severity": stint["severity"],
                "reason": stint["reason"],
                "duration": (stint["end_date"] - stint["start_date"]).days,
                "is_pitcher": is_pitcher,
                "year": year
            }
            
            if is_pitcher:
                pre = calculate_pitcher_metrics(before_games)
                post = calculate_pitcher_metrics(after_games)
                if pre and post:
                    diffs = get_performance_diffs(pre, post, is_pitcher=True)
                    stint_data.update({
                        "pre": pre,
                        "post": post,
                        "diff": diffs,
                        "is_sp": pre["is_sp"]
                    })
                    stints_all.append(stint_data)
            else:
                pre = calculate_batter_metrics(before_games)
                post = calculate_batter_metrics(after_games)
                if pre and post:
                    diffs = get_performance_diffs(pre, post, is_pitcher=False)
                    stint_data.update({
                        "pre": pre,
                        "post": post,
                        "diff": diffs,
                        "is_sp": False
                    })
                    stints_all.append(stint_data)
                    
    log_event(f"Successfully matched {len(stints_all)} stints.")
    
    # Calculate baseline standard deviations from pre-injury windows
    batter_pre_ops = [s["pre"]["OPS"] for s in stints_all if not s["is_pitcher"]]
    batter_pre_r = [s["pre"]["R"] for s in stints_all if not s["is_pitcher"]]
    batter_pre_hr = [s["pre"]["HR"] for s in stints_all if not s["is_pitcher"]]
    batter_pre_rbi = [s["pre"]["RBI"] for s in stints_all if not s["is_pitcher"]]
    batter_pre_sb = [s["pre"]["SB"] for s in stints_all if not s["is_pitcher"]]
    
    sp_pre_era = [s["pre"]["ERA"] for s in stints_all if s["is_pitcher"] and s["is_sp"]]
    sp_pre_whip = [s["pre"]["WHIP"] for s in stints_all if s["is_pitcher"] and s["is_sp"]]
    sp_pre_k9 = [s["pre"]["K9"] for s in stints_all if s["is_pitcher"] and s["is_sp"]]
    sp_pre_qs = [s["pre"]["QS"] for s in stints_all if s["is_pitcher"] and s["is_sp"]]
    
    rp_pre_era = [s["pre"]["ERA"] for s in stints_all if s["is_pitcher"] and not s["is_sp"]]
    rp_pre_whip = [s["pre"]["WHIP"] for s in stints_all if s["is_pitcher"] and not s["is_sp"]]
    rp_pre_k9 = [s["pre"]["K9"] for s in stints_all if s["is_pitcher"] and not s["is_sp"]]
    rp_pre_svhd = [s["pre"]["SVHD"] for s in stints_all if s["is_pitcher"] and not s["is_sp"]]
    
    std_bat = {
        "OPS": std_dev(batter_pre_ops), "R": std_dev(batter_pre_r),
        "HR": std_dev(batter_pre_hr), "RBI": std_dev(batter_pre_rbi),
        "SB": std_dev(batter_pre_sb)
    }
    std_sp = {
        "ERA": std_dev(sp_pre_era), "WHIP": std_dev(sp_pre_whip),
        "K9": std_dev(sp_pre_k9), "QS": std_dev(sp_pre_qs)
    }
    std_rp = {
        "ERA": std_dev(rp_pre_era), "WHIP": std_dev(rp_pre_whip),
        "K9": std_dev(rp_pre_k9), "SVHD": std_dev(rp_pre_svhd)
    }
    
    # Calculate Z-score deltas
    for s in stints_all:
        pre, post = s["pre"], s["post"]
        if not s["is_pitcher"]:
            z_diff = ((post["OPS"] - pre["OPS"]) / std_bat["OPS"] +
                      (post["R"] - pre["R"]) / std_bat["R"] +
                      (post["HR"] - pre["HR"]) / std_bat["HR"] +
                      (post["RBI"] - pre["RBI"]) / std_bat["RBI"] +
                      (post["SB"] - pre["SB"]) / std_bat["SB"])
        elif s["is_sp"]:
            z_diff = (-(post["ERA"] - pre["ERA"]) / std_sp["ERA"] -
                       (post["WHIP"] - pre["WHIP"]) / std_sp["WHIP"] +
                       (post["K9"] - pre["K9"]) / std_sp["K9"] +
                       (post["QS"] - pre["QS"]) / std_sp["QS"])
        else:
            z_diff = (-(post["ERA"] - pre["ERA"]) / std_rp["ERA"] -
                       (post["WHIP"] - pre["WHIP"]) / std_rp["WHIP"] +
                       (post["K9"] - pre["K9"]) / std_rp["K9"] +
                       (post["SVHD"] - pre["SVHD"]) / std_rp["SVHD"])
                       
        s["z_diff"] = z_diff
        
    # Group results for output tables
    batter_stints_by_cat = defaultdict(list)
    sp_stints_by_cat = defaultdict(list)
    rp_stints_by_cat = defaultdict(list)
    
    batter_stints_by_sev = defaultdict(list)
    sp_stints_by_sev = defaultdict(list)
    rp_stints_by_sev = defaultdict(list)
    
    batter_stints_by_cat_sev = defaultdict(list)
    sp_stints_by_cat_sev = defaultdict(list)
    rp_stints_by_cat_sev = defaultdict(list)
    
    # Combined list by severity for histogram summary
    z_by_sev = defaultdict(list)
    
    for s in stints_all:
        z_by_sev[s["severity"]].append(s["z_diff"])
        if not s["is_pitcher"]:
            batter_stints_by_cat[s["category"]].append(s)
            batter_stints_by_sev[s["severity"]].append(s)
            batter_stints_by_cat_sev[(s["category"], s["severity"])].append(s)
        elif s["is_sp"]:
            sp_stints_by_cat[s["category"]].append(s)
            sp_stints_by_sev[s["severity"]].append(s)
            sp_stints_by_cat_sev[(s["category"], s["severity"])].append(s)
        else:
            rp_stints_by_cat[s["category"]].append(s)
            rp_stints_by_sev[s["severity"]].append(s)
            rp_stints_by_cat_sev[(s["category"], s["severity"])].append(s)
            
    # Write Report
    report_file = os.path.join(REPORT_PATH, "injury_performance_impact_report.md")
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# MLB Injury Performance Impact Analysis (2023 - 2026)\n\n")
        f.write(f"> **Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("> **Methodology:** Evaluates active player performance over a **28-game active window** before IL placement against a **28-game active window** immediately following IL activation. Stints are filtered to include only players with a minimum of **10 active games** in both windows to ensure statistical integrity. Counting stats (R, HR, RBI, SB, QS, SVHD) are scaled to a standard 28-game representation.\n\n")
        
        # --- SECTION 1: OVERALL BREAKDOWN BY IL LENGTH & HISTOGRAMS ---
        f.write("## 1. Overall Performance Impact & Distribution by IL Length\n\n")
        f.write("This section standardizes overall player value across all 5 batter/pitcher scoring categories using Z-scores to evaluate whether players return better or worse from various IL lengths (7-day, 10-day, 15-day, 60-day).\n\n")
        
        # Embed the generated histogram visualization
        f.write("### Post-IL Performance Change Distributions\n")
        f.write("Below is the generated 3x2 grid of histograms showing the distribution of Z-score changes. Green represents improvement, while red represents regression. The percentage of players getting better vs. worse is summarized in each chart:\n\n")
        f.write("![Post-IL Performance Distribution](../../pjrigali.github.io/assets/images/injury_performance_histograms.png)\n\n")
        
        # Table summarizing Better vs Worse % for Batters
        f.write("### Batters: Summary of Improvement vs. Regression by IL Type\n\n")
        f.write("| IL Type | Stints | Worse % (< 0 Delta Z) | Better % (>= 0 Delta Z) | Median Z-Score Delta |\n")
        f.write("|---------|--------|------------------------|-------------------------|----------------------|\n")
        for sev in [7, 10, 60]:
            stints_list = batter_stints_by_sev.get(sev, [])
            if not stints_list: continue
            deltas = [s["z_diff"] for s in stints_list]
            n = len(deltas)
            worse_pct = sum(1 for x in deltas if x < 0) / n * 100
            better_pct = sum(1 for x in deltas if x >= 0) / n * 100
            sorted_deltas = sorted(deltas)
            median_delta = sorted_deltas[n // 2]
            f.write(f"| {sev}-day IL | {n} | {worse_pct:.1f}% | {better_pct:.1f}% | {median_delta:+.2f} |\n")
        f.write("\n")

        # Table summarizing Better vs Worse % for Pitchers
        f.write("### Pitchers: Summary of Improvement vs. Regression by IL Type\n\n")
        f.write("| IL Type | Stints | Worse % (< 0 Delta Z) | Better % (>= 0 Delta Z) | Median Z-Score Delta |\n")
        f.write("|---------|--------|------------------------|-------------------------|----------------------|\n")
        for sev in [10, 15, 60]:
            stints_list = sp_stints_by_sev.get(sev, []) + rp_stints_by_sev.get(sev, [])
            if not stints_list: continue
            deltas = [s["z_diff"] for s in stints_list]
            n = len(deltas)
            worse_pct = sum(1 for x in deltas if x < 0) / n * 100
            better_pct = sum(1 for x in deltas if x >= 0) / n * 100
            sorted_deltas = sorted(deltas)
            median_delta = sorted_deltas[n // 2]
            f.write(f"| {sev}-day IL | {n} | {worse_pct:.1f}% | {better_pct:.1f}% | {median_delta:+.2f} |\n")
        f.write("\n")
        
        # Batting by IL length
        f.write("### Batters by IL Length\n\n")
        f.write("| IL Type | Stints | Avg Duration (Days) | Pre OPS | Post OPS | OPS Δ | R Δ | HR Δ | RBI Δ | SB Δ |\n")
        f.write("|---------|--------|---------------------|---------|----------|-------|-----|------|-------|------|\n")
        for sev in sorted(batter_stints_by_sev.keys()):
            stints_list = batter_stints_by_sev[sev]
            n = len(stints_list)
            if n == 0: continue
            avg_dur = sum(s["duration"] for s in stints_list) / n
            avg_pre_ops = sum(s["pre"]["OPS"] for s in stints_list) / n
            avg_post_ops = sum(s["post"]["OPS"] for s in stints_list) / n
            avg_ops_diff = sum(s["diff"]["OPS"] for s in stints_list) / n
            avg_r_diff = sum(s["diff"]["R"] for s in stints_list) / n
            avg_hr_diff = sum(s["diff"]["HR"] for s in stints_list) / n
            avg_rbi_diff = sum(s["diff"]["RBI"] for s in stints_list) / n
            avg_sb_diff = sum(s["diff"]["SB"] for s in stints_list) / n
            f.write(f"| {sev}-day IL | {n} | {avg_dur:.1f} | {avg_pre_ops:.3f} | {avg_post_ops:.3f} | {avg_ops_diff:+.3f} | {avg_r_diff:+.1f} | {avg_hr_diff:+.1f} | {avg_rbi_diff:+.1f} | {avg_sb_diff:+.1f} |\n")
        f.write("\n")
        
        # SP by IL length
        f.write("### Starting Pitchers (SP) by IL Length\n\n")
        f.write("| IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | QS Δ |\n")
        f.write("|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|------|\n")
        for sev in sorted(sp_stints_by_sev.keys()):
            stints_list = sp_stints_by_sev[sev]
            n = len(stints_list)
            if n == 0: continue
            avg_dur = sum(s["duration"] for s in stints_list) / n
            avg_pre_era = sum(s["pre"]["ERA"] for s in stints_list) / n
            avg_post_era = sum(s["post"]["ERA"] for s in stints_list) / n
            avg_era_diff = sum(s["diff"]["ERA"] for s in stints_list) / n
            avg_pre_whip = sum(s["pre"]["WHIP"] for s in stints_list) / n
            avg_post_whip = sum(s["post"]["WHIP"] for s in stints_list) / n
            avg_whip_diff = sum(s["diff"]["WHIP"] for s in stints_list) / n
            avg_k9_diff = sum(s["diff"]["K9"] for s in stints_list) / n
            avg_qs_diff = sum(s["diff"]["QS"] for s in stints_list) / n
            f.write(f"| {sev}-day IL | {n} | {avg_dur:.1f} | {avg_pre_era:.2f} | {avg_post_era:.2f} | {avg_era_diff:+.2f} | {avg_pre_whip:.2f} | {avg_post_whip:.2f} | {avg_whip_diff:+.2f} | {avg_k9_diff:+.1f} | {avg_qs_diff:+.1f} |\n")
        f.write("\n")
        
        # RP by IL length
        f.write("### Relief Pitchers (RP) by IL Length\n\n")
        f.write("| IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | SVHD Δ |\n")
        f.write("|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|--------|\n")
        for sev in sorted(rp_stints_by_sev.keys()):
            stints_list = rp_stints_by_sev[sev]
            n = len(stints_list)
            if n == 0: continue
            avg_dur = sum(s["duration"] for s in stints_list) / n
            avg_pre_era = sum(s["pre"]["ERA"] for s in stints_list) / n
            avg_post_era = sum(s["post"]["ERA"] for s in stints_list) / n
            avg_era_diff = sum(s["diff"]["ERA"] for s in stints_list) / n
            avg_pre_whip = sum(s["pre"]["WHIP"] for s in stints_list) / n
            avg_post_whip = sum(s["post"]["WHIP"] for s in stints_list) / n
            avg_whip_diff = sum(s["diff"]["WHIP"] for s in stints_list) / n
            avg_k9_diff = sum(s["diff"]["K9"] for s in stints_list) / n
            avg_svhd_diff = sum(s["diff"]["SVHD"] for s in stints_list) / n
            f.write(f"| {sev}-day IL | {n} | {avg_dur:.1f} | {avg_pre_era:.2f} | {avg_post_era:.2f} | {avg_era_diff:+.2f} | {avg_pre_whip:.2f} | {avg_post_whip:.2f} | {avg_whip_diff:+.2f} | {avg_k9_diff:+.1f} | {avg_svhd_diff:+.1f} |\n")
        f.write("\n")
        
        # --- SECTION 2: BATTING PERFORMANCE IMPACT BY CATEGORY & IL LENGTH ---
        f.write("## 2. Batting Performance Impact by Category & IL Length\n\n")
        f.write("| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre OPS | Post OPS | OPS Δ | R Δ | HR Δ | RBI Δ | SB Δ |\n")
        f.write("|-----------------|---------|--------|---------------------|---------|----------|-------|-----|------|-------|------|\n")
        
        all_bat_cats = sorted(batter_stints_by_cat.keys(), key=lambda c: len(batter_stints_by_cat[c]), reverse=True)
        for cat in all_bat_cats:
            cat_stints = batter_stints_by_cat[cat]
            n_all = len(cat_stints)
            avg_dur = sum(s["duration"] for s in cat_stints) / n_all
            avg_pre_ops = sum(s["pre"]["OPS"] for s in cat_stints) / n_all
            avg_post_ops = sum(s["post"]["OPS"] for s in cat_stints) / n_all
            avg_ops_diff = sum(s["diff"]["OPS"] for s in cat_stints) / n_all
            avg_r_diff = sum(s["diff"]["R"] for s in cat_stints) / n_all
            avg_hr_diff = sum(s["diff"]["HR"] for s in cat_stints) / n_all
            avg_rbi_diff = sum(s["diff"]["RBI"] for s in cat_stints) / n_all
            avg_sb_diff = sum(s["diff"]["SB"] for s in cat_stints) / n_all
            f.write(f"| **{cat} (All)** | - | **{n_all}** | **{avg_dur:.1f}** | **{avg_pre_ops:.3f}** | **{avg_post_ops:.3f}** | **{avg_ops_diff:+.3f}** | **{avg_r_diff:+.1f}** | **{avg_hr_diff:+.1f}** | **{avg_rbi_diff:+.1f}** | **{avg_sb_diff:+.1f}** |\n")
            
            for sev in [7, 10, 15, 60]:
                stints_list = batter_stints_by_cat_sev[(cat, sev)]
                n = len(stints_list)
                if n == 0: continue
                avg_dur_sev = sum(s["duration"] for s in stints_list) / n
                avg_pre_ops_sev = sum(s["pre"]["OPS"] for s in stints_list) / n
                avg_post_ops_sev = sum(s["post"]["OPS"] for s in stints_list) / n
                avg_ops_diff_sev = sum(s["diff"]["OPS"] for s in stints_list) / n
                avg_r_diff_sev = sum(s["diff"]["R"] for s in stints_list) / n
                avg_hr_diff_sev = sum(s["diff"]["HR"] for s in stints_list) / n
                avg_rbi_diff_sev = sum(s["diff"]["RBI"] for s in stints_list) / n
                avg_sb_diff_sev = sum(s["diff"]["SB"] for s in stints_list) / n
                f.write(f"| &nbsp;&nbsp;&bull;&nbsp;{cat} | {sev}-day | {n} | {avg_dur_sev:.1f} | {avg_pre_ops_sev:.3f} | {avg_post_ops_sev:.3f} | {avg_ops_diff_sev:+.3f} | {avg_r_diff_sev:+.1f} | {avg_hr_diff_sev:+.1f} | {avg_rbi_diff_sev:+.1f} | {avg_sb_diff_sev:+.1f} |\n")
        f.write("\n")
        
        # --- SECTION 3: SP PERFORMANCE IMPACT BY CATEGORY & IL LENGTH ---
        f.write("## 3. Starting Pitcher (SP) Performance Impact by Category & IL Length\n\n")
        f.write("| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | QS Δ |\n")
        f.write("|-----------------|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|------|\n")
        
        all_sp_cats = sorted(sp_stints_by_cat.keys(), key=lambda c: len(sp_stints_by_cat[c]), reverse=True)
        for cat in all_sp_cats:
            cat_stints = sp_stints_by_cat[cat]
            n_all = len(cat_stints)
            avg_dur = sum(s["duration"] for s in cat_stints) / n_all
            avg_pre_era = sum(s["pre"]["ERA"] for s in cat_stints) / n_all
            avg_post_era = sum(s["post"]["ERA"] for s in cat_stints) / n_all
            avg_era_diff = sum(s["diff"]["ERA"] for s in cat_stints) / n_all
            avg_pre_whip = sum(s["pre"]["WHIP"] for s in cat_stints) / n_all
            avg_post_whip = sum(s["post"]["WHIP"] for s in cat_stints) / n_all
            avg_whip_diff = sum(s["diff"]["WHIP"] for s in cat_stints) / n_all
            avg_k9_diff = sum(s["diff"]["K9"] for s in cat_stints) / n_all
            avg_qs_diff = sum(s["diff"]["QS"] for s in cat_stints) / n_all
            f.write(f"| **{cat} (All)** | - | **{n_all}** | **{avg_dur:.1f}** | **{avg_pre_era:.2f}** | **{avg_post_era:.2f}** | **{avg_era_diff:+.2f}** | **{avg_pre_whip:.2f}** | **{avg_post_whip:.2f}** | **{avg_whip_diff:+.2f}** | **{avg_k9_diff:+.1f}** | **{avg_qs_diff:+.1f}** |\n")
            
            for sev in [7, 10, 15, 60]:
                stints_list = sp_stints_by_cat_sev[(cat, sev)]
                n = len(stints_list)
                if n == 0: continue
                avg_dur_sev = sum(s["duration"] for s in stints_list) / n
                avg_pre_era_sev = sum(s["pre"]["ERA"] for s in stints_list) / n
                avg_post_era_sev = sum(s["post"]["ERA"] for s in stints_list) / n
                avg_era_diff_sev = sum(s["diff"]["ERA"] for s in stints_list) / n
                avg_pre_whip_sev = sum(s["pre"]["WHIP"] for s in stints_list) / n
                avg_post_whip_sev = sum(s["post"]["WHIP"] for s in stints_list) / n
                avg_whip_diff_sev = sum(s["diff"]["WHIP"] for s in stints_list) / n
                avg_k9_diff_sev = sum(s["diff"]["K9"] for s in stints_list) / n
                avg_qs_diff_sev = sum(s["diff"]["QS"] for s in stints_list) / n
                f.write(f"| &nbsp;&nbsp;&bull;&nbsp;{cat} | {sev}-day | {n} | {avg_dur_sev:.1f} | {avg_pre_era_sev:.2f} | {avg_post_era_sev:.2f} | {avg_era_diff_sev:+.2f} | {avg_pre_whip_sev:.2f} | {avg_post_whip_sev:.2f} | {avg_whip_diff_sev:+.2f} | {avg_k9_diff_sev:+.1f} | {avg_qs_diff_sev:+.1f} |\n")
        f.write("\n")
        
        # --- SECTION 4: RP PERFORMANCE IMPACT BY CATEGORY & IL LENGTH ---
        f.write("## 4. Relief Pitcher (RP) Performance Impact by Category & IL Length\n\n")
        f.write("| Injury Category | IL Type | Stints | Avg Duration (Days) | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ | K/9 Δ | SVHD Δ |\n")
        f.write("|-----------------|---------|--------|---------------------|---------|----------|-------|----------|-----------|--------|-------|--------|\n")
        
        all_rp_cats = sorted(rp_stints_by_cat.keys(), key=lambda c: len(rp_stints_by_cat[c]), reverse=True)
        for cat in all_rp_cats:
            cat_stints = rp_stints_by_cat[cat]
            n_all = len(cat_stints)
            avg_dur = sum(s["duration"] for s in cat_stints) / n_all
            avg_pre_era = sum(s["pre"]["ERA"] for s in cat_stints) / n_all
            avg_post_era = sum(s["post"]["ERA"] for s in cat_stints) / n_all
            avg_era_diff = sum(s["diff"]["ERA"] for s in cat_stints) / n_all
            avg_pre_whip = sum(s["pre"]["WHIP"] for s in cat_stints) / n_all
            avg_post_whip = sum(s["post"]["WHIP"] for s in cat_stints) / n_all
            avg_whip_diff = sum(s["diff"]["WHIP"] for s in cat_stints) / n_all
            avg_k9_diff = sum(s["diff"]["K9"] for s in cat_stints) / n_all
            avg_svhd_diff = sum(s["diff"]["SVHD"] for s in cat_stints) / n_all
            f.write(f"| **{cat} (All)** | - | **{n_all}** | **{avg_dur:.1f}** | **{avg_pre_era:.2f}** | **{avg_post_era:.2f}** | **{avg_era_diff:+.2f}** | **{avg_pre_whip:.2f}** | **{avg_post_whip:.2f}** | **{avg_whip_diff:+.2f}** | **{avg_k9_diff:+.1f}** | **{avg_svhd_diff:+.1f}** |\n")
            
            for sev in [7, 10, 15, 60]:
                stints_list = rp_stints_by_cat_sev[(cat, sev)]
                n = len(stints_list)
                if n == 0: continue
                avg_dur_sev = sum(s["duration"] for s in stints_list) / n
                avg_pre_era_sev = sum(s["pre"]["ERA"] for s in stints_list) / n
                avg_post_era_sev = sum(s["post"]["ERA"] for s in stints_list) / n
                avg_era_diff_sev = sum(s["diff"]["ERA"] for s in stints_list) / n
                avg_pre_whip_sev = sum(s["pre"]["WHIP"] for s in stints_list) / n
                avg_post_whip_sev = sum(s["post"]["WHIP"] for s in stints_list) / n
                avg_whip_diff_sev = sum(s["diff"]["WHIP"] for s in stints_list) / n
                avg_k9_diff_sev = sum(s["diff"]["K9"] for s in stints_list) / n
                avg_svhd_diff_sev = sum(s["diff"]["SVHD"] for s in stints_list) / n
                f.write(f"| &nbsp;&nbsp;&bull;&nbsp;{cat} | {sev}-day | {n} | {avg_dur_sev:.1f} | {avg_pre_era_sev:.2f} | {avg_post_era_sev:.2f} | {avg_era_diff_sev:+.2f} | {avg_pre_whip_sev:.2f} | {avg_post_whip_sev:.2f} | {avg_whip_diff_sev:+.2f} | {avg_k9_diff_sev:+.1f} | {avg_svhd_diff_sev:+.1f} |\n")
        f.write("\n")
        
        # --- SECTION 5: INDIVIDUAL CASE STUDIES ---
        f.write("## 5. Individual Player Case Studies (Recent Large Stints)\n\n")
        f.write("A sample of high-impact hitters and pitchers showing the largest performance changes post-activation:\n\n")
        
        # Collect top 10 batter case studies (biggest OPS drop)
        all_batter_cases = [s for s in stints_all if not s["is_pitcher"]]
        all_batter_cases.sort(key=lambda x: x["diff"]["OPS"])
        
        f.write("### Hitters with Largest Post-IL OPS Drops\n\n")
        f.write("| Player | Injury Category | IL Duration | Pre OPS | Post OPS | OPS Δ | HR Δ | SB Δ |\n")
        f.write("|--------|-----------------|-------------|---------|----------|-------|------|------|\n")
        for s in all_batter_cases[:10]:
            f.write(f"| {s['player_name']} | {s['category']} | {s['duration']} days | {s['pre']['OPS']:.3f} | {s['post']['OPS']:.3f} | {s['diff']['OPS']:+.3f} | {s['diff']['HR']:+.1f} | {s['diff']['SB']:+.1f} |\n")
        f.write("\n")
        
        # Collect top 10 pitcher case studies (biggest ERA increase)
        all_pitcher_cases = [s for s in stints_all if s["is_pitcher"]]
        all_pitcher_cases.sort(key=lambda x: x["diff"]["ERA"], reverse=True)
        
        f.write("### Pitchers with Largest Post-IL ERA Increases\n\n")
        f.write("| Player | Injury Category | IL Duration | Pre ERA | Post ERA | ERA Δ | Pre WHIP | Post WHIP | WHIP Δ |\n")
        f.write("|--------|-----------------|-------------|---------|----------|-------|----------|-----------|--------|\n")
        for s in all_pitcher_cases[:10]:
            f.write(f"| {s['player_name']} | {s['category']} | {s['duration']} days | {s['pre']['ERA']:.2f} | {s['post']['ERA']:.2f} | {s['diff']['ERA']:+.2f} | {s['pre']['WHIP']:.2f} | {s['post']['WHIP']:.2f} | {s['diff']['WHIP']:+.2f} |\n")
            
    log_event(f"Successfully generated detailed report at: {report_file}")

if __name__ == "__main__":
    main()
