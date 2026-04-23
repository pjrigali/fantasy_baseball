"""
Fetch ESPN Fantasy Baseball league activity (adds, drops, trades, waivers)
and save/append to the Bronze data lake layer.

Usage:
    python fetch_activity_espn_season.py [--year 2026] [--max-pages 20]
"""
import os
import sys
import argparse
import pandas as pd
from datetime import datetime

# Ensure the parent directory is on the path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp


def main():
    parser = argparse.ArgumentParser(description="Fetch ESPN league activity data")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current year)')
    parser.add_argument('--max-pages', type=int, default=20,
                        help='Max pages to paginate through (default: 20)')
    parser.add_argument('--size', type=int, default=100,
                        help='Records per API page (default: 100)')
    args = parser.parse_args()

    target_year = args.year
    print(f"--- Fetching League Activity for {target_year} ---")

    # 1. Load config
    try:
        config = mp.load_config()
        print("Config loaded.")
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # 2. Setup League
    try:
        league = mp.setup_league(config, year=target_year)
        print(f"League initialized for {target_year}: {league}")
    except Exception as e:
        print(f"Error initializing league: {e}")
        return

    # 3. Fetch Activity
    print(f"Fetching activity data (max_pages={args.max_pages}, size={args.size})...")
    try:
        activity_data = mp.get_recent_activity(
            league, 
            size=args.size, 
            max_pages=args.max_pages
        )
        print(f"Fetched {len(activity_data)} activity records.")
    except Exception as e:
        print(f"Error fetching activity: {e}")
        return

    if not activity_data:
        print("No activity data found.")
        return

    # 4. Convert to DataFrame
    df_new = pd.DataFrame(activity_data)

    # 5. Append to existing data (deduplicate)
    os.makedirs(mp.DATA_PATH, exist_ok=True)
    filename = f"activity_espn_season_{target_year}.csv"
    save_path = os.path.join(mp.DATA_PATH, filename)

    if os.path.exists(save_path):
        print(f"Existing data found at: {save_path}")
        df_existing = pd.read_csv(save_path)
        print(f"  Existing records: {len(df_existing)}")
        
        # Combine and deduplicate on composite key
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        dedup_cols = ['date_epoch', 'player_id', 'action_id', 'team_id']
        before_dedup = len(df_combined)
        df_combined.drop_duplicates(subset=dedup_cols, keep='last', inplace=True)
        after_dedup = len(df_combined)
        
        new_records = after_dedup - len(df_existing)
        print(f"  After dedup: {after_dedup} records ({new_records} new)")
        df_final = df_combined
    else:
        print("No existing data found — creating new file.")
        df_final = df_new

    # 6. Sort by date descending and save
    df_final.sort_values('date_epoch', ascending=False, inplace=True)
    df_final.to_csv(save_path, index=False)
    print(f"\nSaved {len(df_final)} records to: {save_path}")

    # 7. Preview
    print("\nPreview (latest 10 records):")
    preview_cols = ['date', 'team_abbrev', 'action', 'player_name', 'position_from', 'position_to']
    available_cols = [c for c in preview_cols if c in df_final.columns]
    print(df_final[available_cols].head(10).to_string(index=False))

    # 8. Summary stats
    print("\n--- Summary ---")
    print(f"Total records: {len(df_final)}")
    if 'action' in df_final.columns:
        print("\nRecords by action type:")
        print(df_final['action'].value_counts().to_string())
    if 'team_name' in df_final.columns:
        print("\nRecords by team:")
        print(df_final['team_name'].value_counts().to_string())


if __name__ == "__main__":
    main()
