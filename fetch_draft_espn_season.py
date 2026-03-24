import os
import sys
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp
YEAR = 2026


def main():
    print(f"--- Fetching Draft Results for {YEAR} ---")
    
    # 1. Load config
    try:
        config = mp.load_config()
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    league = mp.setup_league(config, year=YEAR)
    print(f"League initialized: {league}")

    # 3. Fetch Draft Results
    try:
        draft_picks = mp.get_draft_recap(league)
        print(f"Captured {len(draft_picks)} draft picks.")
        
        if draft_picks:
            df = pd.DataFrame(draft_picks)
            
            # Save
            os.makedirs(mp.DATA_PATH, exist_ok=True)
            save_path = os.path.join(mp.DATA_PATH, f"draft_results_espn_{YEAR}.csv")
            df.to_csv(save_path, index=False)
            print(f"Saved draft results to {save_path}")
            print(df.head())
            print(df.tail())
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error fetching draft results: {e}")

if __name__ == "__main__":
    main()
