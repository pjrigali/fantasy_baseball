"""
Description: Generates a scoring-period <-> matchup-period <-> calendar-date mapping
             for the ESPN fantasy league. Uses the authoritative per-matchup day
             membership reported by ESPN (home/away pointsByScoringPeriod), not a
             heuristic distribution. Only periods that have begun are emitted.
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

    # Authoritative matchup-period -> scoring-period mapping pulled directly from ESPN's
    # matchup objects (home/away pointsByScoringPeriod). settings.matchupPeriods is unreliable
    # for this daily league (it returns 1:1 week indices), and an even-distribution heuristic
    # drifts badly mid-season, so we use the exact day membership ESPN reports per matchup.
    # Note: only periods that have begun (have points data) are emitted.
    sched_data = league.espn_request.league_get(params={'view': ['mMatchupScore', 'mScoreboard']})
    mp_to_sps = defaultdict(set)
    for m in sched_data.get('schedule', []):
        mp_id = m.get('matchupPeriodId')
        if mp_id is None:
            continue
        for side in ('home', 'away'):
            pbsp = (m.get(side) or {}).get('pointsByScoringPeriod') or {}
            mp_to_sps[mp_id].update(int(k) for k in pbsp.keys())

    rows = []
    for mp_id in sorted(mp_to_sps):
        for sp in sorted(mp_to_sps[mp_id]):
            game_date = opening_day + timedelta(days=sp - 1)
            rows.append({
                'matchup_period': mp_id,
                'scoring_period': sp,
                'date': game_date.isoformat(),
            })

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
