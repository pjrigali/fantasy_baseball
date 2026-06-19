"""
Description: Analyze historical MLB injury transaction logs (2023-2026) and ESPN fantasy rosters (2025-2026)
             to track injury durations, frequencies, types, and impact on fantasy team lineups.
Source Data: stats_mlb_season_transactions_{year}.csv, stats_espn_daily_{year}.csv, player_map.csv
Outputs: c:/Users/peter/Desktop/vscode/main/reports/injury_analysis_report.md
"""
import os
import csv
import sys
from datetime import datetime, date, timedelta
from collections import defaultdict, Counter

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
DATA_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')
REPORT_PATH = SCRIPT_DIR
LOG_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '00_Logs', 'fantasy_baseball')

def log_event(message):
    """Logs an event message to the console and to the log file."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "analyze_stats_espn_injuries.log")
    timestamp = datetime.now().isoformat(timespec='seconds')
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

def parse_date(date_str):
    """Parses YYYY-MM-DD date strings safely."""
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except Exception:
        return None

def normalize_name(name):
    """Normalizes player names for fuzzy matching."""
    if not name:
        return ""
    # Lowercase, remove accents, dots, junior/senior suffixes
    name = name.lower().strip()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n",
        "í": "i", "ü": "u", "ý": "y", "ć": "c", "ō": "o", "’": "", "'": "",
        ".": "", "jr": "", "sr": "", "iii": "", "ii": "", "iv": ""
    }
    for orig, rep in replacements.items():
        name = name.replace(orig, rep)
    return " ".join(name.split())

def load_player_maps():
    """Loads player_map.csv and returns MLB-to-ESPN ID and Name-to-ESPN ID maps."""
    map_file = os.path.join(DATA_PATH, "player_map.csv")
    mlb_to_espn = {}
    name_to_espn = {}
    
    if not os.path.exists(map_file):
        log_event(f"[WARN] player_map.csv not found at {map_file}. Matching will rely on names.")
        return mlb_to_espn, name_to_espn

    try:
        with open(map_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                espn_id = row.get("espn_player_id")
                mlb_id = row.get("statcast_player_id")
                full_name = row.get("full_name")
                
                if espn_id:
                    if mlb_id:
                        mlb_to_espn[mlb_id] = espn_id
                    if full_name:
                        norm_name = normalize_name(full_name)
                        name_to_espn[norm_name] = espn_id
        log_event(f"Loaded player map: {len(mlb_to_espn)} MLB IDs, {len(name_to_espn)} player names.")
    except Exception as e:
        log_event(f"[ERROR] Failed to load player_map.csv: {e}")
        
    return mlb_to_espn, name_to_espn

def categorize_injury(description):
    """Categorizes injury reason from description string."""
    desc = description.lower()
    
    # Check for body part keywords
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
    """Extracts the injury reason from transaction descriptions."""
    # Description usually ends with sentence containing injury reason.
    # E.g. "Brewers placed Brandon Woodruff on the 15-day IL. Right shoulder inflammation."
    parts = description.split(".")
    if len(parts) > 1:
        reason = parts[1].strip()
        if reason:
            return reason
    return "Unspecified Injury"

def parse_il_duration(description):
    """Extracts standard IL duration from description."""
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

def reconstruct_mlb_stints(year):
    """Reads transactions CSV and reconstructs Completed and Ongoing IL stints."""
    csv_file = os.path.join(DATA_PATH, f"stats_mlb_season_transactions_{year}.csv")
    if not os.path.exists(csv_file):
        log_event(f"[WARN] Transactions file not found for {year}: {csv_file}")
        return []
        
    stints = []
    active_stints = {} # player_id -> active stint dict
    
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
                
                # Check for Placement on IL
                if "placed" in desc_lower or "transferred" in desc_lower:
                    severity = parse_il_duration(desc)
                    reason = parse_injury_details(desc)
                    category = categorize_injury(desc)
                    
                    if player_id in active_stints:
                        # Update active stint (e.g. transfer 15-day -> 60-day)
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
                        
                # Check for Activation from IL
                elif "activated" in desc_lower:
                    if player_id in active_stints:
                        stint = active_stints[player_id]
                        stint["end_date"] = tx_date
                        stint["status"] = "Completed"
                        stints.append(stint)
                        del active_stints[player_id]
                        
        # Resolve ongoing stints at the end of the season range
        # Cap date is either today (if current year) or Nov 1st of the season
        current_year = datetime.now().year
        if year == current_year:
            cap_date = datetime.now().date()
        else:
            cap_date = date(year, 11, 1)
            
        for player_id, stint in active_stints.items():
            # For past years, ongoing stints at end of season are capped
            stint["end_date"] = cap_date
            stint["status"] = "Ongoing"
            stints.append(stint)
            
        log_event(f"Reconstructed {len(stints)} IL stints for {year} season.")
    except Exception as e:
        log_event(f"[ERROR] Failed to reconstruct stints for {year}: {e}")
        
    return stints

def load_espn_rosters(year):
    """Loads daily ESPN roster database for 2025/2026."""
    csv_file = os.path.join(DATA_PATH, f"stats_espn_daily_{year}.csv")
    if not os.path.exists(csv_file):
        log_event(f"[WARN] ESPN daily stats file not found for {year}: {csv_file}")
        return {}
        
    # Maps: player_id -> date -> {team_id, team_name, team_abbrev, lineup_slot}
    rosters = defaultdict(dict)
    
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Harmonize 2025 vs 2026 column keys
                p_id = row.get("player_id") or row.get("playerId")
                p_name = row.get("player_name") or row.get("playerName")
                t_id = row.get("team_id") or row.get("teamId")
                t_name = row.get("team_name")
                t_abbrev = row.get("team_abbrev")
                l_slot = row.get("lineup_slot") or row.get("lineupSlot")
                row_date = row.get("date")
                
                # In 2025, date is not in the row but we have scoring_period
                # We can calculate calendar date from scoring_period if date is missing
                if not row_date:
                    sp = row.get("scoring_period")
                    if sp:
                        # Opening Day 2025 was March 27
                        sp_int = int(sp)
                        opening = date(2025, 3, 27)
                        row_date = str(opening + timedelta(days=sp_int - 1))
                
                if p_id and row_date:
                    rosters[p_id][row_date] = {
                        "team_id": t_id,
                        "team_name": t_name or t_id,
                        "team_abbrev": t_abbrev or t_id,
                        "lineup_slot": l_slot,
                        "player_name": p_name
                    }
        log_event(f"Loaded daily ESPN roster records for {year}: {len(rosters)} unique players mapped.")
    except Exception as e:
        log_event(f"[ERROR] Failed to load ESPN daily stats for {year}: {e}")
        
    return rosters

def analyze_injuries():
    log_event("Starting comparative player injury analysis...")
    
    mlb_to_espn, name_to_espn = load_player_maps()
    
    # 1. Reconstruct all stints (2023-2026)
    all_stints = []
    for yr in [2023, 2024, 2025, 2026]:
        all_stints.extend(reconstruct_mlb_stints(yr))
        
    log_event(f"Total reconstructed stints across all years: {len(all_stints)}")
    
    # Group stints by position (using a lookup helper)
    # We will build a player position lookup from ESPN 2026 stats and player map
    player_positions = {}
    
    # Load player map positions
    map_file = os.path.join(DATA_PATH, "player_map.csv")
    if os.path.exists(map_file):
        with open(map_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("full_name")
                slots = row.get("player_eligible_slots", "")
                # Estimate default position based on slots
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

    # Load 2026 ESPN roster positions
    espn_2026_file = os.path.join(DATA_PATH, "stats_espn_daily_2026.csv")
    if os.path.exists(espn_2026_file):
        with open(espn_2026_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("player_name")
                pos = row.get("player_position")
                if name and pos:
                    player_positions[normalize_name(name)] = pos

    # Function to get position
    def get_player_pos(player_name):
        norm = normalize_name(player_name)
        return player_positions.get(norm, "Unknown")
        
    # Apply position and duration to all stints
    for stint in all_stints:
        stint["position"] = get_player_pos(stint["player_name"])
        if stint["end_date"] and stint["start_date"]:
            stint["duration"] = (stint["end_date"] - stint["start_date"]).days
        else:
            stint["duration"] = 0

    # 2. Compile Positional Stats (2023-2026)
    position_stats = defaultdict(list)
    for stint in all_stints:
        pos = stint["position"]
        if pos != "Unknown" and stint["duration"] > 0:
            position_stats[pos].append(stint["duration"])
            
    # 3. Categorize by Injury Type (2023-2026)
    category_stats = defaultdict(list)
    for stint in all_stints:
        cat = stint["category"]
        if stint["duration"] > 0:
            category_stats[cat].append(stint["duration"])
            
    # 4. Multi-Year Injury Propensity (2023-2026)
    player_stints_count = Counter()
    player_total_days = Counter()
    for stint in all_stints:
        p_name = stint["player_name"]
        player_stints_count[p_name] += 1
        player_total_days[p_name] += stint["duration"]

    # 5. ESPN Fantasy Impact (2025 & 2026)
    # Maps: (year, team_abbrev) -> {total_il_days, roster_drag_days, total_lags, lags_count}
    team_metrics = defaultdict(lambda: {"il_days": 0, "drag_days": 0, "total_lag": 0, "lag_count": 0})
    
    for yr in [2025, 2026]:
        rosters = load_espn_rosters(yr)
        if not rosters:
            continue
            
        yr_stints = [s for s in all_stints if s["year"] == yr]
        
        for stint in yr_stints:
            mlb_id = stint["player_id"]
            player_name = stint["player_name"]
            start_date = stint["start_date"]
            end_date = stint["end_date"]
            
            # Map MLB ID to ESPN ID
            espn_id = mlb_to_espn.get(mlb_id)
            if not espn_id:
                # Fallback to name-matching
                espn_id = name_to_espn.get(normalize_name(player_name))
                
            if not espn_id or espn_id not in rosters:
                continue
                
            player_daily = rosters[espn_id]
            stint_range = []
            
            # Generate daily range dates
            curr = start_date
            limit = end_date or datetime.now().date()
            while curr <= limit:
                stint_range.append(str(curr))
                curr = curr + timedelta(days=1)
                
            # Track fantasy roster placements during IL stint
            first_rostered_injured_date = None
            placed_on_fantasy_il_date = None
            
            for date_str in stint_range:
                if date_str in player_daily:
                    day_info = player_daily[date_str]
                    team_abbrev = day_info["team_abbrev"]
                    lineup_slot = day_info["lineup_slot"]
                    
                    team_metrics[(yr, team_abbrev)]["il_days"] += 1
                    
                    # If player was in an active starting slot while injured, this is Roster Drag!
                    active_slots = {"C", "1B", "2B", "3B", "SS", "OF", "UTIL", "SP", "RP", "P"}
                    if lineup_slot in active_slots:
                        team_metrics[(yr, team_abbrev)]["drag_days"] += 1
                        
                    # For Manager Reaction Time calculation:
                    if not first_rostered_injured_date:
                        first_rostered_injured_date = parse_date(date_str)
                        
                    if lineup_slot == "IL" and not placed_on_fantasy_il_date:
                        placed_on_fantasy_il_date = parse_date(date_str)
            
            # Calculate manager reaction lag
            if first_rostered_injured_date and placed_on_fantasy_il_date:
                lag = (placed_on_fantasy_il_date - first_rostered_injured_date).days
                # Sanity cap (e.g. within 30 days) to avoid outliers
                if 0 <= lag <= 30:
                    # Resolve team at start of injury
                    start_date_str = str(first_rostered_injured_date)
                    if start_date_str in player_daily:
                        team_abbrev = player_daily[start_date_str]["team_abbrev"]
                        team_metrics[(yr, team_abbrev)]["total_lag"] += lag
                        team_metrics[(yr, team_abbrev)]["lag_count"] += 1

    # 6. Generate Markdown Report
    os.makedirs(REPORT_PATH, exist_ok=True)
    report_file = os.path.join(REPORT_PATH, "injury_analysis_report.md")
    
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            f.write("# Player Injury Data & Roster Drag Analysis (2023 - 2026)\n\n")
            f.write("> **Analysis generated on:** " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
            f.write("This report compiles historical MLB injury transaction data from 2023 through 2026 ")
            f.write("and joins it with ESPN fantasy league active rosters to measure how injuries impact ")
            f.write("counting stats, roster management efficiency, and team success.\n\n")
            
            # Section 1: Executive Summary Table
            f.write("## 1. Executive Summary\n\n")
            f.write("| Year | Total IL Placements | Completed Stints | Avg Stint Duration (Days) |\n")
            f.write("|------|----------------------|------------------|---------------------------|\n")
            for yr in [2023, 2024, 2025, 2026]:
                yr_stints = [s for s in all_stints if s["year"] == yr]
                completed = [s["duration"] for s in yr_stints if s["status"] == "Completed" and s["duration"] > 0]
                avg_dur = sum(completed) / len(completed) if completed else 0
                f.write(f"| {yr} | {len(yr_stints)} | {len(completed)} | {avg_dur:.1f} |\n")
            f.write("\n")
            
            # Section 2: Positional Injury Profile
            f.write("## 2. Positional Injury Profile (2023 - 2026)\n\n")
            f.write("| Position | Total IL Placements | Median Duration (Days) | Max Duration (Days) | Total Days Missed |\n")
            f.write("|----------|----------------------|------------------------|---------------------|-------------------|\n")
            
            # Sort positions by count
            sorted_positions = sorted(position_stats.keys(), key=lambda k: len(position_stats[k]), reverse=True)
            for pos in sorted_positions:
                durations = position_stats[pos]
                count = len(durations)
                durations.sort()
                median = durations[count // 2] if count > 0 else 0
                max_dur = max(durations) if count > 0 else 0
                total_days = sum(durations)
                f.write(f"| {pos} | {count} | {median} | {max_dur} | {total_days} |\n")
            f.write("\n")
            
            # Section 3: Injury Categories & Severity
            f.write("## 3. Injury Category Breakdown (2023 - 2026)\n\n")
            f.write("| Injury Category | Total Placements | Avg Duration (Days) | Representative Examples |\n")
            f.write("|-----------------|------------------|---------------------|-------------------------|\n")
            
            sorted_categories = sorted(category_stats.keys(), key=lambda k: len(category_stats[k]), reverse=True)
            for cat in sorted_categories:
                durations = category_stats[cat]
                count = len(durations)
                avg_dur = sum(durations) / count if count > 0 else 0
                
                # Get a few examples
                examples = [s["reason"] for s in all_stints if s["category"] == cat and s["reason"] != "Unspecified Injury"]
                example_str = ", ".join(list(set(examples))[:2]) if examples else "Status changes"
                
                f.write(f"| {cat} | {count} | {avg_dur:.1f} | {example_str} |\n")
            f.write("\n")
            
            # Section 4: Player Injury Propensity Leaderboards
            f.write("## 4. Multi-Year Player Injury Propensity Leaderboards\n\n")
            f.write("### Most Frequent IL Stints (2023 - 2026)\n")
            f.write("| Player Name | Total IL Placements | Total Days Missed | Injury Profile (Recent) |\n")
            f.write("|-------------|----------------------|-------------------|-------------------------|\n")
            for p_name, count in player_stints_count.most_common(10):
                total_days = player_total_days[p_name]
                p_stints = [s for s in all_stints if s["player_name"] == p_name]
                recent_reason = p_stints[-1]["reason"] if p_stints else ""
                f.write(f"| {p_name} | {count} | {total_days} | {recent_reason} |\n")
            f.write("\n")
            
            f.write("### Most Total Days Missed (2023 - 2026)\n")
            f.write("| Player Name | Total Days Missed | Total Placements | Primary Injury Reason |\n")
            f.write("|-------------|-------------------|------------------|-----------------------|\n")
            for p_name, total_days in player_total_days.most_common(10):
                count = player_stints_count[p_name]
                p_stints = [s for s in all_stints if s["player_name"] == p_name]
                primary_reason = max(set([s["reason"] for s in p_stints]), key=[s["reason"] for s in p_stints].count) if p_stints else ""
                f.write(f"| {p_name} | {total_days} | {count} | {primary_reason} |\n")
            f.write("\n")
            
            # Section 5: ESPN Fantasy Impact Analysis
            f.write("## 5. ESPN Fantasy Impact & Roster Management efficiency\n\n")
            
            for yr in [2025, 2026]:
                f.write(f"### {yr} Season Injury Drag Ledger\n")
                f.write("| Team Abbrev | Total IL Days rostered | Roster Drag Days (In Starting Slot) | Roster Drag % | Avg Reaction Lag (Days) |\n")
                f.write("|-------------|------------------------|-------------------------------------|---------------|-------------------------|\n")
                
                # Get unique teams for this year
                yr_teams = sorted(set(k[1] for k in team_metrics.keys() if k[0] == yr))
                for team in yr_teams:
                    metrics = team_metrics[(yr, team)]
                    il_days = metrics["il_days"]
                    drag_days = metrics["drag_days"]
                    drag_pct = (drag_days / il_days * 100) if il_days > 0 else 0
                    
                    total_lag = metrics["total_lag"]
                    lag_count = metrics["lag_count"]
                    avg_lag = (total_lag / lag_count) if lag_count > 0 else 0
                    
                    f.write(f"| {team} | {il_days} | {drag_days} | {drag_pct:.1f}% | {avg_lag:.1f} |\n")
                f.write("\n")
                
        log_event(f"[SUCCESS] Comparative injury report generated successfully at {report_file}")
    except Exception as e:
        log_event(f"[ERROR] Failed to generate report: {e}")

if __name__ == "__main__":
    analyze_injuries()
