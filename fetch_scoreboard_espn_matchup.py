"""
Description: Captures the ESPN fantasy league matchup scoreboard for the current matchup period.
Source Data: ESPN Fantasy API (via mlb_processing.get_matchup_scoreboard).
Outputs: data-lake/01_Bronze/fantasy_baseball/scoreboard_espn_matchup_<YEAR>.csv
"""

import argparse
import csv
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp


def main():
    parser = argparse.ArgumentParser(description="Capture ESPN matchup scoreboard for the given season.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    args = parser.parse_args()
    year = args.year

    print(f"--- Capturing Matchup Scoreboard (year={year}) ---")
    config = mp.load_config()
    league = mp.setup_league(config, year=year)
    print(f"League initialized: {league}")

    scoreboard_data = mp.get_matchup_scoreboard(league)
    print(f"Captured {len(scoreboard_data)} matchups.")
    if not scoreboard_data:
        print("No scoreboard data returned.")
        return

    team_map = {team.team_id: team.team_abbrev for team in league.teams}
    for row in scoreboard_data:
        if 'homeTeamId' in row:
            row['homeTeamParams'] = team_map.get(row.get('homeTeamId'))
        if 'awayTeamId' in row:
            row['awayTeamParams'] = team_map.get(row.get('awayTeamId'))

    os.makedirs(mp.DATA_PATH, exist_ok=True)
    save_path = os.path.join(mp.DATA_PATH, f"scoreboard_espn_matchup_{year}.csv")
    fieldnames = list({k for r in scoreboard_data for k in r.keys()})
    with open(save_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in scoreboard_data:
            w.writerow(row)
    print(f"Scoreboard saved to: {save_path}")
    print(f"Rows: {len(scoreboard_data)}")


if __name__ == "__main__":
    main()
