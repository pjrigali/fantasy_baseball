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
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview records that would be written without saving to disk')
    args = parser.parse_args()

    target_year = args.year

    try:
        config = mp.load_config()
    except Exception as e:
        print(f"[ERROR] fetch_activity_espn_season: {e}")
        return

    try:
        league = mp.setup_league(config, year=target_year)
    except Exception as e:
        print(f"[ERROR] fetch_activity_espn_season: failed to init league — {e}")
        return

    os.makedirs(mp.DATA_PATH, exist_ok=True)
    filename = f"activity_espn_season_{target_year}.csv"
    save_path = os.path.join(mp.DATA_PATH, filename)

    since_epoch = None
    if os.path.exists(save_path):
        df_check = pd.read_csv(save_path)
        if 'date_epoch' in df_check.columns and not df_check.empty:
            since_epoch = int(df_check['date_epoch'].max())

    try:
        activity_data = mp.get_recent_activity(
            league,
            size=args.size,
            max_pages=args.max_pages,
            since_epoch=since_epoch,
        )
    except Exception as e:
        print(f"[ERROR] fetch_activity_espn_season: failed to fetch activity — {e}")
        return

    if not activity_data:
        tag = "[DRY-RUN]" if args.dry_run else "[OK]   "
        print(f"{tag} fetch_activity_espn_season: 0 new records (already current) | {target_year}")
        return

    dates = sorted(set(r.get('date', '')[:10] for r in activity_data if r.get('date')))
    date_range = f"{dates[0]} → {dates[-1]}" if len(dates) > 1 else (dates[0] if dates else str(target_year))

    if args.dry_run:
        print(f"[DRY-RUN] fetch_activity_espn_season: {len(activity_data)} records would be written | {date_range}")
        return

    df_new = pd.DataFrame(activity_data)
    write_header = not os.path.exists(save_path)
    df_new.to_csv(save_path, mode='a', index=False, header=write_header)
    print(f"[OK]    fetch_activity_espn_season: {len(df_new)} records written | {date_range}")


if __name__ == "__main__":
    main()
