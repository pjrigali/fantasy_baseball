import os
import sys
import pandas as pd
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

def main():
    target_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    print(f"--- Starting Daily Stats Update for {target_year} ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
        print("Config loaded.")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League (Try 2025, fallback to 2024+swap logic if needed, but 2025 should be direct)
    league = None
    try:
        print(f"Attempting to initialize league for {target_year}...")
        league = mp.setup_league(config, year=target_year)
    except Exception as e:
        print(f"Direct init failed for {target_year}: {e}")
        # If needed, can keep the fallback logic for robustness, but 2025 *should* work if config is valid.
        # Keeping it simple for 2025 based on previous success:
        return

    print(f"League initialized: {league}")

    # 3. Build Daily Scoring Period List
    # We want "each day", so we ignore the matchup map which might be weekly aggregated.
    # MLB season is approx 180-190 days. We'll check up to 195.
    print("Generating daily scoring period list (1-195)...")
    daily_scoring_periods = list(range(1, 196)) # 1 to 195 inclusive

    # 4. Fetch Data
    print("Fetching daily player stats (this may take a while)...")
    try:
        # Pass the simple list to fetch_league_matchup_data
        # It will iterate each SP without filtering by matchup_period
        data, team_map = mp.fetch_league_matchup_data(league, daily_scoring_periods)
        print(f"Fetched {len(data)} records.")
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        # Continue to save empty if needed or retur
        if not 'data' in locals():
            return

    # 5. Save to Data Lake
    if data:
        try:
            df = pd.DataFrame(data)
            
            # Map Team IDs to Names if available
            if team_map:
                 # Check if team_id matches format in df (usually integer)
                df['team_abbrev'] = df['teamId'].map(team_map)
            
            os.makedirs(mp.DATA_PATH, exist_ok=True)
            filename = f"stats_espn_daily_{target_year}.csv"
            save_path = os.path.join(mp.DATA_PATH, filename)
            
            df.to_csv(save_path, index=False)
            print(f"Successfully saved data to: {save_path}")
            print(df.head())
            
        except Exception as e:
            print(f"Error saving data: {e}")
    else:
        print("No daily stats data returned.")

if __name__ == "__main__":
    main()
