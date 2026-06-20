"""
Description: Snapshots the current ESPN fantasy league roster for all teams.
Source Data: ESPN Fantasy API (via mlb_processing.get_league_rosters).
Outputs: data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_roster_season.csv
"""

import argparse
import os
import csv
from datetime import datetime
from fantasy_baseball import mlb_processing as mp


def main():
    parser = argparse.ArgumentParser(description="Refresh current ESPN rosters into the Bronze data lake.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    args = parser.parse_args()
    year = args.year

    print(f"--- Starting Roster Update (year={year}) ---")

    config = mp.load_config()
    print("Config loaded.")

    league = mp.setup_league(config, year=year)
    print(f"League initialized: {league}")

    today_str = datetime.now().strftime('%Y-%m-%d')
    rosters = mp.get_league_rosters(league, today_dt=today_str)
    print(f"Fetched {len(rosters)} player records.")

    if not rosters:
        print("No roster data returned.")
        return

    os.makedirs(mp.DATA_PATH, exist_ok=True)
    save_path = os.path.join(mp.DATA_PATH, f"{year}_espn_roster_season.csv")

    fieldnames = list({k for r in rosters for k in r.keys()})
    preferred_order = ['date', 'team_id', 'team_name', 'player_id', 'player_name',
                       'lineup_slot', 'injuryStatus', 'eligibleSlots']
    ordered = [c for c in preferred_order if c in fieldnames] + \
              [c for c in fieldnames if c not in preferred_order]

    with open(save_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ordered)
        writer.writeheader()
        for row in rosters:
            writer.writerow(row)

    print(f"Successfully saved data to: {save_path}")
    print(f"Rows: {len(rosters)}")


if __name__ == "__main__":
    main()
