import os
import pandas as pd
from fantasy_baseball import mlb_processing as mp
from datetime import datetime

def main():
    print("--- Starting Roster Update ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
        print("Config loaded.")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    try:
        league = mp.setup_league(config, year=2025)
        print(f"League initialized: {league}")
    except Exception as e:
        print(f"Error initializing league: {e}")
        return

    # 3. Fetch Rosters
    print("Fetching rosters...")
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        rosters = mp.get_league_rosters(league, today_dt=today_str)
        print(f"Fetched {len(rosters)} player records.")
    except Exception as e:
        print(f"Error fetching rosters: {e}")
        return

    # 4. Save to Data Lake
    if rosters:
        try:
            df = pd.DataFrame(rosters)
            
            # Ensure directory exists (it should, but good practice)
            os.makedirs(mp.DATA_PATH, exist_ok=True)
            
            save_path = os.path.join(mp.DATA_PATH, "roster_espn_season_2025.csv")
            df.to_csv(save_path, index=False)
            print(f"Successfully saved data to: {save_path}")
            
            # Preview
            print("\nPreview:")
            print(df.head())
            
        except Exception as e:
            print(f"Error saving data: {e}")
    else:
        print("No roster data returned.")

if __name__ == "__main__":
    main()
