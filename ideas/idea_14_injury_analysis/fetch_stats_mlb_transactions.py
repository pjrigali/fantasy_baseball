"""
Description: Fetch player status changes (Injured List placements and activations) from the MLB Stats API
             for a given year and save to the Bronze layer of the data lake.
Source Data: statsapi.mlb.com/api/v1/transactions
Outputs: c:/Users/peter/Desktop/vscode/main/data-lake/01_Bronze/fantasy_baseball/stats_mlb_season_transactions_{year}.csv
"""
import os
import csv
import argparse
import requests
from datetime import datetime

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SCRIPT_DIR)))
DATA_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')
LOG_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '00_Logs', 'fantasy_baseball')

def log_event(message):
    """Logs an event message to the console and to the log file."""
    os.makedirs(LOG_PATH, exist_ok=True)
    log_file = os.path.join(LOG_PATH, "fetch_stats_mlb_transactions.log")
    timestamp = datetime.now().isoformat(timespec='seconds')
    log_line = f"[{timestamp}] {message}"
    print(log_line)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

def fetch_transactions_for_year(year):
    """Queries the MLB API for status change transactions and writes to CSV."""
    # Season start/end dates range
    start_date = f"{year}-03-01"
    
    # If fetching the current year, cap at today's date
    current_year = datetime.now().year
    if year == current_year:
        end_date = datetime.now().strftime("%Y-%m-%d")
    else:
        end_date = f"{year}-11-01"
        
    log_event(f"Starting fetch for {year} | Range: {start_date} to {end_date}")
    
    url = "https://statsapi.mlb.com/api/v1/transactions"
    params = {
        "sportId": 1,
        "startDate": start_date,
        "endDate": end_date
    }
    
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        log_event(f"[ERROR] Failed to query MLB API: {e}")
        return False
        
    raw_transactions = data.get("transactions", [])
    log_event(f"Fetched {len(raw_transactions)} raw transactions from MLB Stats API.")
    
    # Filter for IL status changes
    il_records = []
    for t in raw_transactions:
        type_code = t.get("typeCode")
        description = t.get("description", "")
        
        # We only care about Status Change (SC) transactions involving the Injured List
        if type_code == "SC" and description:
            desc_lower = description.lower()
            if "injured list" in desc_lower or "activated" in desc_lower or "placed" in desc_lower:
                # Resolve player
                person = t.get("person", {})
                player_id = person.get("id")
                player_name = person.get("fullName")
                
                # Resolve team
                to_team = t.get("toTeam", {})
                team_id = to_team.get("id")
                team_name = to_team.get("name")
                
                il_records.append({
                    "date": t.get("date"),
                    "player_id": player_id,
                    "player_name": player_name,
                    "team_id": team_id,
                    "team_name": team_name,
                    "description": description
                })
                
    log_event(f"Filtered down to {len(il_records)} Injured List placements/activations.")
    
    # Sort chronologically
    il_records.sort(key=lambda x: x["date"])
    
    # Write to Bronze CSV
    os.makedirs(DATA_PATH, exist_ok=True)
    csv_file = os.path.join(DATA_PATH, f"stats_mlb_season_transactions_{year}.csv")
    
    fieldnames = ["date", "player_id", "player_name", "team_id", "team_name", "description"]
    
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for record in il_records:
                writer.writerow(record)
        log_event(f"[SUCCESS] Saved {len(il_records)} records to {csv_file}")
        return True
    except Exception as e:
        log_event(f"[ERROR] Failed to write CSV file {csv_file}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Fetch Injured List transactions from MLB API")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Year to fetch transactions for (default: current year)')
    args = parser.parse_args()
    
    fetch_transactions_for_year(args.year)

if __name__ == "__main__":
    main()
