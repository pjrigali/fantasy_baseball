"""
Description: Calculate Z-score performance deltas based on scoring.md metrics
             and generate a 3x2 grid of histograms separating Batters (Left) and Pitchers (Right)
             by their respective IL lengths.
Source Data: stats_mlb_season_transactions_{year}.csv, stats_mlb_daily_{year}.csv, stats_mlb_boxscore_2026.csv
Outputs: c:/Users/peter/Desktop/vscode/main/pjrigali.github.io/assets/images/injury_performance_histograms.png
"""
import os
import csv
import math
from datetime import datetime, date
from collections import defaultdict
import matplotlib.pyplot as plt
import numpy as np

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
DATA_PATH = os.path.join(PROJECT_ROOT, '.data_lake', '01_Bronze', 'fantasy_baseball')
IMAGE_DIR = os.path.join(PROJECT_ROOT, 'pjrigali.github.io', 'assets', 'images')

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

def main():
    log_event("Gathering all pre/post active game windows...")
    stints_all = []
    
    for year in [2023, 2024, 2025, 2026]:
        log_event(f"Loading data for {year}...")
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
            
            if is_pitcher:
                pre = calculate_pitcher_metrics(before_games)
                post = calculate_pitcher_metrics(after_games)
                if pre and post:
                    stints_all.append({
                        "player_name": stint["player_name"],
                        "severity": stint["severity"],
                        "is_pitcher": True,
                        "is_sp": pre["is_sp"],
                        "pre": pre,
                        "post": post
                    })
            else:
                pre = calculate_batter_metrics(before_games)
                post = calculate_batter_metrics(after_games)
                if pre and post:
                    stints_all.append({
                        "player_name": stint["player_name"],
                        "severity": stint["severity"],
                        "is_pitcher": False,
                        "is_sp": False,
                        "pre": pre,
                        "post": post
                    })
                    
    log_event(f"Matched {len(stints_all)} completed stints. Calculating standard deviations...")
    
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
    
    log_event("Computing Z-Score Deltas...")
    
    stints_with_z = []
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
                       
        stints_with_z.append({**s, "z_diff": z_diff})
        
    log_event("Generating side-by-side histograms...")
    
    plt.style.use('dark_background')
    fig, axes = plt.subplots(3, 2, figsize=(15, 14))
    fig.suptitle('Post-IL Performance Change Distributions (Hitter vs. Pitcher)\nNegative values = Worse upon return  |  Positive values = Better upon return',
                 fontsize=16, fontweight='bold', color='#E0E0E0', y=0.98)
                 
    # Define grid mapping
    # Rows: 1, 2, 3
    # Col 0: Batters
    # Col 1: Pitchers
    
    # 1. Row 0: Short/Fast (Batters 7-day, Pitchers 10-day)
    # 2. Row 1: Medium (Batters 10-day, Pitchers 15-day)
    # 3. Row 2: Long (Batters 60-day, Pitchers 60-day)
    
    layout = [
        # (row, col, is_pitcher, severity, label, color)
        (0, 0, False, 7, 'Batters: 7-day IL (Concussions)', '#E57373'),
        (0, 1, True, 10, 'Pitchers: 10-day IL (Short Stays)', '#FFB74D'),
        (1, 0, False, 10, 'Batters: 10-day IL (Standard)', '#4FC3F7'),
        (1, 1, True, 15, 'Pitchers: 15-day IL (Standard)', '#81C784'),
        (2, 0, False, 60, 'Batters: 60-day IL (Long-Term)', '#CE93D8'),
        (2, 1, True, 60, 'Pitchers: 60-day IL (Long-Term)', '#B39DDB')
    ]
    
    for row_idx, col_idx, is_pit, sev, title, color in layout:
        ax = axes[row_idx, col_idx]
        
        # Filter stints
        deltas = [s["z_diff"] for s in stints_with_z if s["is_pitcher"] == is_pit and s["severity"] == sev]
        
        if not deltas:
            ax.text(0.5, 0.5, 'No Data Available (n = 0)', horizontalalignment='center', verticalalignment='center', color='#888888', fontsize=12)
            ax.set_title(title, fontsize=13, fontweight='bold', color='#888888')
            ax.set_facecolor('#111111')
            continue
            
        n = len(deltas)
        worse_pct = sum(1 for x in deltas if x < 0) / n * 100
        better_pct = sum(1 for x in deltas if x >= 0) / n * 100
        
        # Plot
        bins = min(15, max(4, int(math.sqrt(n)) * 2))
        n_vals, bins_edges, patches = ax.hist(deltas, bins=bins, color=color, alpha=0.85, edgecolor='#1E1E1E')
        
        # Color code bars based on negative/positive deltas
        for patch in patches:
            if patch.get_x() < 0:
                patch.set_facecolor('#EF5350') # Red for regression
            else:
                patch.set_facecolor('#66BB6A') # Green for improvement
                
        # Vertical line at x=0
        ax.axvline(x=0, color='#B0BEC5', linestyle='--', linewidth=1.5, alpha=0.7)
        
        # Labels and format
        ax.set_title(f'{title} (n = {n})', fontsize=13, fontweight='bold', pad=10, color=color)
        ax.set_xlabel('Z-Score Delta (Post - Pre)', fontsize=10, color='#B0B0B0')
        ax.set_ylabel('Player Count', fontsize=10, color='#B0B0B0')
        ax.grid(True, linestyle=':', alpha=0.25, color='#424242')
        
        # Text box
        stats_text = f"Worse: {worse_pct:.1f}%\nBetter: {better_pct:.1f}%"
        ax.text(0.95, 0.95, stats_text, transform=ax.transAxes, fontsize=11, fontweight='bold',
                verticalalignment='top', horizontalalignment='right',
                bbox=dict(boxstyle='round,pad=0.4', facecolor='#121212', alpha=0.85, edgecolor='#333333'))
                
    plt.tight_layout()
    plt.subplots_adjust(top=0.92) # Adjust layout to make room for suptitle
    
    os.makedirs(IMAGE_DIR, exist_ok=True)
    out_path = os.path.join(IMAGE_DIR, "injury_performance_histograms.png")
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    
    log_event(f"Successfully generated and saved side-by-side histograms to: {out_path}")

if __name__ == "__main__":
    main()
