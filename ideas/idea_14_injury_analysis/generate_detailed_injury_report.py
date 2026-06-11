"""
Description: Generate a detailed markdown report analyzing player injury durations across 2023-2026
             broken down by injury category, estimated day category (IL type), position, and MLB team.
Source Data: stats_mlb_season_transactions_{year}.csv, player_map.csv, stats_espn_daily_{year}.csv
Outputs: c:/Users/peter/Desktop/vscode/main/reports/detailed_injury_duration_report.md
"""
import os
import csv
from datetime import datetime, date, timedelta
from collections import defaultdict

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
DATA_PATH = os.path.join(PROJECT_ROOT, '.data_lake', '01_Bronze', 'fantasy_baseball')
REPORT_PATH = SCRIPT_DIR

def log_event(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def parse_date(date_str):
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def normalize_name(name):
    if not name:
        return ""
    name = name.lower().strip()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        "ü": "u", "ý": "y", "ć": "c", "ō": "o", "’": "", "'": "",
        ".": "", "jr": "", "sr": "", "iii": "", "ii": "", "iv": ""
    }
    for orig, rep in replacements.items():
        name = name.replace(orig, rep)
    return " ".join(name.split())

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
    return 10  # default / fallback

def load_player_positions():
    """Loads player positions from player_map.csv and daily ESPN stats."""
    player_positions = {}
    
    # Load player map positions
    map_file = os.path.join(DATA_PATH, "player_map.csv")
    if os.path.exists(map_file):
        try:
            with open(map_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    name = row.get("full_name")
                    slots = row.get("player_eligible_slots", "")
                    pos = "UTIL"
                    if "SP" in slots: pos = "SP"
                    elif "RP" in slots: pos = "RP"
                    elif "C" in slots: pos = "C"
                    elif "1B" in slots: pos = "1B"
                    elif "2B" in slots: pos = "2B"
                    elif "3B" in slots: pos = "3B"
                    elif "SS" in slots: pos = "SS"
                    elif "OF" in slots: pos = "OF"
                    
                    if name:
                        player_positions[normalize_name(name)] = pos
        except Exception as e:
            log_event(f"Error reading player_map.csv: {e}")

    # Load ESPN daily stats positions for 2025 and 2026
    for year in [2025, 2026]:
        espn_file = os.path.join(DATA_PATH, f"stats_espn_daily_{year}.csv")
        if os.path.exists(espn_file):
            try:
                with open(espn_file, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        name = row.get("player_name") or row.get("playerName")
                        pos = row.get("player_position")
                        if name and pos:
                            player_positions[normalize_name(name)] = pos
            except Exception as e:
                log_event(f"Error reading stats_espn_daily_{year}.csv: {e}")
                
    return player_positions

def reconstruct_stints(year):
    csv_file = os.path.join(DATA_PATH, f"stats_mlb_season_transactions_{year}.csv")
    if not os.path.exists(csv_file):
        log_event(f"Transactions file not found for {year}: {csv_file}")
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
                        
        # Resolve ongoing stints at the end of the season range
        current_year = datetime.now().year
        if year == current_year:
            cap_date = datetime.now().date()
        else:
            cap_date = date(year, 11, 1)
            
        for player_id, stint in active_stints.items():
            stint["end_date"] = cap_date
            stint["status"] = "Ongoing"
            stints.append(stint)
            
    except Exception as e:
        log_event(f"Error reconstructing stints for {year}: {e}")
        
    return stints

def calculate_stats(durations):
    if not durations:
        return 0.0, 0.0, 0
    count = len(durations)
    avg_dur = sum(durations) / count
    sorted_durs = sorted(durations)
    median_dur = sorted_durs[count // 2]
    return avg_dur, median_dur, count

def main():
    log_event("Starting Detailed Player Injury Duration Analysis...")
    positions_map = load_player_positions()
    
    all_stints = []
    for yr in [2023, 2024, 2025, 2026]:
        all_stints.extend(reconstruct_stints(yr))
        
    log_event(f"Reconstructed {len(all_stints)} total stints (2023-2026).")
    
    # Enrich stints with position
    for stint in all_stints:
        norm_name = normalize_name(stint["player_name"])
        stint["position"] = positions_map.get(norm_name, "Unknown")
        if stint["end_date"] and stint["start_date"]:
            stint["duration"] = (stint["end_date"] - stint["start_date"]).days
        else:
            stint["duration"] = 0
            
    completed_stints = [s for s in all_stints if s["status"] == "Completed" and s["duration"] > 0]
    log_event(f"Analyzed {len(completed_stints)} completed stints for duration statistics.")
    
    # 1. Overall stats by Estimated Day Category (Severity)
    severity_durs = defaultdict(list)
    severity_totals = defaultdict(int)
    for stint in all_stints:
        severity_totals[stint["severity"]] += 1
        if stint["status"] == "Completed" and stint["duration"] > 0:
            severity_durs[stint["severity"]].append(stint["duration"])
            
    # 2. Breakdown by Injury Category + Severity (Estimated Day Category)
    cat_sev_durs = defaultdict(list)
    cat_totals = defaultdict(int)
    for stint in all_stints:
        cat_totals[stint["category"]] += 1
        if stint["status"] == "Completed" and stint["duration"] > 0:
            cat_sev_durs[(stint["category"], stint["severity"])].append(stint["duration"])
            
    # 3. Breakdown by Position + Severity
    pos_sev_durs = defaultdict(list)
    pos_totals = defaultdict(int)
    for stint in all_stints:
        pos_totals[stint["position"]] += 1
        if stint["status"] == "Completed" and stint["duration"] > 0:
            pos_sev_durs[(stint["position"], stint["severity"])].append(stint["duration"])
            
    # 4. Breakdown by MLB Team + Severity
    team_sev_durs = defaultdict(list)
    team_totals = defaultdict(int)
    team_injury_counts = defaultdict(lambda: defaultdict(int))
    for stint in all_stints:
        # Standardize team names slightly (remove "MLB" or city names if needed, but keeping actual transaction tricode/name)
        team = stint["team_name"]
        if not team:
            team = "Unknown Team"
        team_totals[team] += 1
        team_injury_counts[team][stint["category"]] += 1
        if stint["status"] == "Completed" and stint["duration"] > 0:
            team_sev_durs[(team, stint["severity"])].append(stint["duration"])
            
    # Write Report
    os.makedirs(REPORT_PATH, exist_ok=True)
    report_file = os.path.join(REPORT_PATH, "detailed_injury_duration_report.md")
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("# MLB Player Injury Duration Analysis (2023 - 2026)\n\n")
        f.write("> **Document Purpose:** Detailed analysis of actual player recovery time spent on the Injured List (IL) compared to their initial estimated day categories (7-day, 10-day, 15-day, 60-day IL), broken down by injury type, position, and MLB team.\n")
        f.write(f"> **Analysis Period:** 2023 - 2026 seasons  |  **Stints Reconstructed:** {len(all_stints)} total ({len(completed_stints)} completed stints analyzed for durations)\n")
        f.write(f"> **Generated On:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        
        # Section 1: Executive Summary
        f.write("## 1. Executive Summary: Estimated vs. Actual IL Durations\n\n")
        f.write("The table below compares the initial IL placement category against the actual time players spent before activation. Stints are categorized as *Completed* when the player was formally activated. Ongoing/uncensored stints are excluded from duration statistics to prevent downward bias.\n\n")
        f.write("| Estimated IL Type | Total Placements | Completed Stints | Avg Recovery (Days) | Median Recovery (Days) | Spend Minimum (<= IL Type) | Extended (> IL Type) |\n")
        f.write("|-------------------|------------------|------------------|----------------------|------------------------|----------------------------|----------------------|\n")
        
        for sev in sorted(severity_totals.keys()):
            durs = severity_durs[sev]
            total = severity_totals[sev]
            completed = len(durs)
            avg_dur, med_dur, _ = calculate_stats(durs)
            
            # Count how many spent <= IL type days
            min_count = sum(1 for d in durs if d <= sev)
            ext_count = sum(1 for d in durs if d > sev)
            min_pct = (min_count / completed * 100) if completed > 0 else 0
            ext_pct = (ext_count / completed * 100) if completed > 0 else 0
            
            f.write(f"| **{sev}-day IL** | {total} | {completed} | {avg_dur:.1f} | {med_dur:.0f} | {min_pct:.1f}% ({min_count}) | {ext_pct:.1f}% ({ext_count}) |\n")
            
        f.write("\n> [!NOTE]\n")
        f.write("> Placements on the 60-day IL are reserved for severe injuries, and players cannot be activated before 60 days have elapsed. Consequently, the minimum actual duration for completed 60-day IL stints is mathematically >= 60 days.\n\n")
        
        # Section 2: Breakdown by Injury Category and IL Type
        f.write("## 2. Actual Duration by Injury Category & Estimated IL Type\n\n")
        f.write("This table breaks down actual recovery times by the diagnosed injury body part and the estimated day category. This highlights which injury types are most frequently extended beyond their minimum designations.\n\n")
        f.write("| Injury Category | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Max Recovery (Days) |\n")
        f.write("|-----------------|-------------------|------------|-----------|----------------------|------------------------|---------------------|\n")
        
        sorted_cats = sorted(cat_totals.keys(), key=lambda c: cat_totals[c], reverse=True)
        for cat in sorted_cats:
            for sev in [7, 10, 15, 60]:
                durs = cat_sev_durs[(cat, sev)]
                if not durs:
                    continue
                avg_dur, med_dur, completed = calculate_stats(durs)
                max_dur = max(durs)
                total_placements = sum(1 for s in all_stints if s["category"] == cat and s["severity"] == sev)
                f.write(f"| {cat} | {sev}-day | {total_placements} | {completed} | {avg_dur:.1f} | {med_dur:.0f} | {max_dur} |\n")
                
        f.write("\n")
        
        # Section 3: Breakdown by Position and IL Type
        f.write("## 3. Actual Duration by Player Position & Estimated IL Type\n\n")
        f.write("Pitchers (SP/RP) and hitters have different IL rules. In particular, pitchers are placed on the 15-day IL as a minimum, whereas hitters are eligible for the 10-day IL.\n\n")
        f.write("| Position | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Max Recovery (Days) |\n")
        f.write("|----------|-------------------|------------|-----------|----------------------|------------------------|---------------------|\n")
        
        sorted_pos = sorted(pos_totals.keys(), key=lambda p: pos_totals[p], reverse=True)
        for pos in sorted_pos:
            if pos == "Unknown":
                continue
            for sev in [7, 10, 15, 60]:
                durs = pos_sev_durs[(pos, sev)]
                if not durs:
                    continue
                avg_dur, med_dur, completed = calculate_stats(durs)
                max_dur = max(durs)
                total_placements = sum(1 for s in all_stints if s["position"] == pos and s["severity"] == sev)
                f.write(f"| **{pos}** | {sev}-day | {total_placements} | {completed} | {avg_dur:.1f} | {med_dur:.0f} | {max_dur} |\n")
                
        f.write("\n")
        
        # Section 4: Breakdown by MLB Team and IL Type
        f.write("## 4. Actual Duration by MLB Team & Estimated IL Type\n\n")
        f.write("Different team training staffs, medical protocols, and roster depths influence how long players remain on the IL before activation.\n\n")
        f.write("| MLB Team | Estimated IL Type | Placements | Completed | Avg Recovery (Days) | Median Recovery (Days) | Primary Injury (Count) |\n")
        f.write("|----------|-------------------|------------|-----------|----------------------|------------------------|------------------------|\n")
        
        sorted_teams = sorted(team_totals.keys(), key=lambda t: team_totals[t], reverse=True)
        for team in sorted_teams:
            if team == "Unknown Team" or team == "":
                continue
            
            # Get primary injury type for this team
            inj_counts = team_injury_counts[team]
            primary_inj = "None"
            if inj_counts:
                primary_inj = max(inj_counts.keys(), key=lambda k: inj_counts[k])
                primary_inj = f"{primary_inj} ({inj_counts[primary_inj]})"
                
            first_row = True
            for sev in [7, 10, 15, 60]:
                durs = team_sev_durs[(team, sev)]
                if not durs:
                    continue
                avg_dur, med_dur, completed = calculate_stats(durs)
                total_placements = sum(1 for s in all_stints if s["team_name"] == team and s["severity"] == sev)
                
                team_display = team if first_row else ""
                prim_display = primary_inj if first_row else ""
                f.write(f"| {team_display} | {sev}-day | {total_placements} | {completed} | {avg_dur:.1f} | {med_dur:.0f} | {prim_display} |\n")
                first_row = False
                
        f.write("\n")
        
    log_event(f"Successfully generated detailed injury duration report at: {report_file}")

if __name__ == "__main__":
    main()
