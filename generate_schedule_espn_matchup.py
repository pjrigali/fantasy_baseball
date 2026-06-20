"""
Description: Generates a scoring-period <-> matchup-period <-> calendar-date mapping
             for the ESPN fantasy league. Uses league settings + a heuristic
             even-distribution of scoring periods across matchups.
Source Data: ESPN Fantasy API (league settings via mlb_processing).
Outputs: data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_schedule_matchup.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp


OPENING_DAYS = {
    2025: date(2025, 3, 27),
    2026: date(2026, 3, 26),
}


def main():
    parser = argparse.ArgumentParser(description="Generate ESPN matchup-period <-> scoring-period <-> date map.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    parser.add_argument('--opening-day', type=str, default=None,
                        help='Override opening day (YYYY-MM-DD). Defaults to known opening day for the year.')
    args = parser.parse_args()
    year = args.year

    if args.opening_day:
        opening_day = date.fromisoformat(args.opening_day)
    elif year in OPENING_DAYS:
        opening_day = OPENING_DAYS[year]
    else:
        raise SystemExit(f"No opening day known for {year}; pass --opening-day YYYY-MM-DD.")

    print(f"--- Creating Matchup Period Mapping (year={year}, opening_day={opening_day}) ---")
    config = mp.load_config()
    league = mp.setup_league(config, year=year)

    params = {'view': 'mSettings'}
    data = league.espn_request.league_get(params=params)
    status = data.get('status', {})
    schedule_settings = data.get('settings', {}).get('scheduleSettings', {})

    final_sp = status.get('finalScoringPeriod', 167)
    mp_dict = schedule_settings.get('matchupPeriods', {})
    if mp_dict:
        total_matchups = len(mp_dict)
    else:
        total_matchups = schedule_settings.get('matchupPeriodCount', 18) + 2

    reg_season_count = league.settings.reg_season_count
    print(f"Details: Final SP={final_sp}, Total Matchups={total_matchups}, Reg Season={reg_season_count}")

    days_per_matchup = final_sp // total_matchups
    remainder = final_sp % total_matchups

    rows = []
    sp_counter = 1
    for mp_id in range(1, total_matchups + 1):
        days = days_per_matchup + (1 if mp_id <= remainder else 0)
        for _ in range(days):
            if sp_counter > final_sp:
                break
            game_date = opening_day + timedelta(days=sp_counter - 1)
            rows.append({
                'matchup_period': mp_id,
                'scoring_period': sp_counter,
                'date': game_date.isoformat(),
            })
            sp_counter += 1

    by_mp = defaultdict(list)
    for r in rows:
        by_mp[r['matchup_period']].append(r['date'])
    for r in rows:
        dates = by_mp[r['matchup_period']]
        r['matchup_start_date'] = min(dates)
        r['matchup_end_date'] = max(dates)

    os.makedirs(mp.DATA_PATH, exist_ok=True)
    save_path = os.path.join(mp.DATA_PATH, f"{year}_espn_schedule_matchup.csv")
    fieldnames = ['matchup_period', 'scoring_period', 'date', 'matchup_start_date', 'matchup_end_date']
    with open(save_path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"Mapping saved to {save_path}")
    print(f"Rows: {len(rows)}")


if __name__ == "__main__":
    main()
