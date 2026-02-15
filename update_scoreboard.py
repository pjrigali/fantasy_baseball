import os
import sys
import pandas as pd
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

def main():
    print("--- Capturing Matchup Scoreboard ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
        print("Config loaded.")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    league = None
    try:
        # Default to 2025 as per current season
        league = mp.setup_league(config, year=2025)
        print(f"League initialized: {league}")
    except Exception as e:
        print(f"League init failed: {e}")
        return

    # 3. Fetch Scoreboard
    try:
        print("Fetching scoreboard for all matchups...")
        scoreboard_data = mp.get_matchup_scoreboard(league)
        print(f"Captured {len(scoreboard_data)} matchups.")
    except Exception as e:
        print(f"Error fetching scoreboard: {e}")
        return
        print(f"Error fetching scoreboard: {e}")
        return

    # 4. Save to CSV
    if scoreboard_data:
        try:
            df = pd.DataFrame(scoreboard_data)
            
            # Enrich with Team Names if possible
            # league.teams has ID -> Name mapping
            team_map = {team.team_id: team.team_abbrev for team in league.teams}
            
            df['homeTeamParams'] = df['homeTeamId'].map(team_map)
            df['awayTeamParams'] = df['awayTeamId'].map(team_map)
            
            os.makedirs(mp.DATA_PATH, exist_ok=True)
            save_path = os.path.join(mp.DATA_PATH, "matchup_scoreboard_2025.csv")
            
            df.to_csv(save_path, index=False)
            print(f"Scoreboard saved to: {save_path}")
            print(df.head())
            
        except Exception as e:
            print(f"Error saving data: {e}")
    else:
        print("No scoreboard data returned.")

if __name__ == "__main__":
    main()
