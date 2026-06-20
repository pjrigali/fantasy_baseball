"""
Description: Captures the ESPN fantasy league draft results for a given season.
Source Data: ESPN Fantasy API (via mlb_processing.get_draft_recap).
Outputs: data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_draft_results.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp


def main():
    parser = argparse.ArgumentParser(description="Fetch ESPN draft results for the given season.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    args = parser.parse_args()
    year = args.year

    print(f"--- Fetching Draft Results for {year} ---")
    config = mp.load_config()
    league = mp.setup_league(config, year=year)
    print(f"League initialized: {league}")

    draft_picks = mp.get_draft_recap(league)
    print(f"Captured {len(draft_picks)} draft picks.")

    if not draft_picks:
        print("No draft picks returned.")
        return

    os.makedirs(mp.DATA_PATH, exist_ok=True)
    save_path = os.path.join(mp.DATA_PATH, f"{year}_espn_draft_results.csv")
    fieldnames = list({k for p in draft_picks for k in p.keys()})
    with open(save_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in draft_picks:
            w.writerow(row)
    print(f"Saved draft results to {save_path}")
    print(f"Rows: {len(draft_picks)}")


if __name__ == "__main__":
    main()
