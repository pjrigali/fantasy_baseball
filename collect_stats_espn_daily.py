"""
collect_stats_espn_daily.py
===========================
Collects daily player stats for every team in the ESPN fantasy baseball league
and appends them to a cumulative CSV file in the Bronze data lake.

Inputs:
  - config.ini          : ESPN API credentials (BB_LEAGUE_ID, BB_SWID, BB_ESPN_2)
  - Optional CLI args   : --date YYYY-MM-DD  (defaults to today)
                           --year NNNN        (defaults to 2026)

Outputs:
  - .data_lake/01_bronze/fantasy_baseball/stats_espn_daily_{year}.csv
    Appended with one row per player per team for the target date.
    Duplicate rows (same date + team_id + player_id) are skipped.

Columns:
  date, team_id, team_name, team_abbrev, player_id, player_name, player_position,
  player_type (batter/pitcher), lineup_slot, injury_status, injured,
  pro_team, eligible_slots, acquisition_type, points,
  ... all STATS_MAP stat columns (R, HR, RBI, SB, OPS, K, ERA, WHIP, etc.)
"""

import os
import sys
import csv
import json
import argparse
import configparser
from datetime import datetime, date

# ---------------------------------------------------------------------------
# Path setup — ensure the project root is on sys.path so we can import
# the shared mlb_processing module.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from espn_api.baseball import League
from espn_api.baseball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(PROJECT_ROOT, '.data_lake', '01_bronze', 'fantasy_baseball')

# Lineup slot IDs that indicate a pitcher
PITCHER_SLOT_IDS = {13, 14, 15}   # P, SP, RP


# ---------------------------------------------------------------------------
# Config & league helpers
# ---------------------------------------------------------------------------
def load_config(config_file="config.ini"):
    """Load config.ini from CWD, script dir, or project root."""
    search_dirs = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        PROJECT_ROOT,
    ]
    for d in search_dirs:
        path = os.path.join(d, config_file)
        if os.path.exists(path):
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(path)
            return cfg
    raise FileNotFoundError(f"Could not locate {config_file} in any expected directory.")


def setup_league(config, year):
    """Initialise ESPN League object from config."""
    bb = config['BASEBALL']
    return League(
        league_id=int(bb['BB_LEAGUE_ID']),
        year=year,
        espn_s2=bb['BB_ESPN_2'],
        swid='{' + bb['BB_SWID'] + '}',
    )


# ---------------------------------------------------------------------------
# Core: fetch daily stats for a single scoring period
# ---------------------------------------------------------------------------
def fetch_daily_stats(league, scoring_period_id, target_date_str):
    """
    Call the ESPN API for a single scoring period and return a list of
    flat row-dicts ready for CSV output.

    Each row captures:
      - identifiers  : date, team, player
      - metadata     : position, lineup slot, injury, pro team, eligibility
      - stats        : every stat id mapped through STATS_MAP
    """
    team_map = {t.team_id: {'name': t.team_name, 'abbrev': t.team_abbrev} for t in league.teams}

    params = {
        'view': ['mMatchupScore', 'mScoreboard'],
        'scoringPeriodId': scoring_period_id,
    }

    data = league.espn_request.league_get(params=params, headers={})
    schedule = data.get('schedule', [])

    rows = []
    for matchup in schedule:
        for side in ('away', 'home'):
            if side not in matchup:
                continue

            team_data = matchup[side]
            roster_key = 'rosterForCurrentScoringPeriod'
            if roster_key not in team_data:
                continue

            team_id = team_data.get('teamId')
            team_info = team_map.get(team_id, {'name': '', 'abbrev': ''})

            entries = team_data[roster_key].get('entries', [])
            for entry in entries:
                pool_entry = entry.get('playerPoolEntry', {})
                player = pool_entry.get('player', {})

                lineup_slot_id = int(entry.get('lineupSlotId', -1))
                lineup_slot_name = POSITION_MAP.get(lineup_slot_id, str(lineup_slot_id))

                # Default position
                default_pos_id = player.get('defaultPositionId', -1)
                default_pos = POSITION_MAP.get(default_pos_id - 1, str(default_pos_id))

                # Eligible slots as a pipe-separated string for CSV friendliness
                eligible_raw = player.get('eligibleSlots', [])
                eligible_names = [POSITION_MAP.get(s, str(s)) for s in eligible_raw]
                eligible_str = '|'.join(eligible_names)

                # Injury info
                injury_status = player.get('injuryStatus', 'ACTIVE')
                injured = player.get('injured', False)

                # Pro team
                pro_team_id = player.get('proTeamId', 0)
                pro_team = PRO_TEAM_MAP.get(pro_team_id, str(pro_team_id))

                # Acquisition type
                acquisition_type = pool_entry.get('acquisitionType', '')

                # Player type
                player_type = 'pitcher' if lineup_slot_id in PITCHER_SLOT_IDS else 'batter'

                row = {
                    'date': target_date_str,
                    'scoring_period': scoring_period_id,
                    'team_id': team_id,
                    'team_name': team_info['name'],
                    'team_abbrev': team_info['abbrev'],
                    'player_id': player.get('id'),
                    'player_name': player.get('fullName', ''),
                    'player_position': default_pos,
                    'player_type': player_type,
                    'lineup_slot': lineup_slot_name,
                    'injury_status': injury_status,
                    'injured': injured,
                    'pro_team': pro_team,
                    'eligible_slots': eligible_str,
                    'acquisition_type': acquisition_type,
                    'points': 0,
                }

                # Flatten stats
                if player.get('stats'):
                    for stat_block in player['stats']:
                        # Match the scoring period to avoid grabbing projected or
                        # season-level stat blocks
                        sp_id = stat_block.get('scoringPeriodId')
                        stat_source = stat_block.get('statSourceId', -1)
                        if sp_id == scoring_period_id and stat_source == 0:
                            row['points'] = stat_block.get('appliedTotal', 0)
                            for stat_id_str, stat_val in stat_block.get('stats', {}).items():
                                stat_id = int(stat_id_str)
                                if stat_id in STATS_MAP:
                                    row[STATS_MAP[stat_id]] = stat_val
                            break  # Found the matching block

                rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def load_existing_keys(csv_path):
    """
    Read the existing CSV and return a set of (date, team_id, player_id)
    tuples for fast duplicate checking.
    """
    keys = set()
    if not os.path.exists(csv_path):
        return keys

    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row['date'], str(row['team_id']), str(row['player_id']))
            keys.add(key)
    return keys


def append_rows(csv_path, rows, existing_keys):
    """
    Append *new* rows to the CSV, skipping any whose (date, team_id, player_id)
    key already exists.  Creates the file with a header if it doesn't exist.

    Returns the count of rows actually written.
    """
    if not rows:
        return 0

    # Build the canonical column order from the first row + any extras
    # We want a stable column order: fixed columns first, then stats alphabetically.
    fixed_cols = [
        'date', 'scoring_period', 'team_id', 'team_name', 'team_abbrev',
        'player_id', 'player_name', 'player_position', 'player_type',
        'lineup_slot', 'injury_status', 'injured', 'pro_team',
        'eligible_slots', 'acquisition_type', 'points',
    ]
    # Gather any stat columns that appeared across all rows
    stat_cols = set()
    for r in rows:
        stat_cols.update(k for k in r.keys() if k not in fixed_cols)
    all_cols = fixed_cols + sorted(stat_cols)

    # If file already exists, read its header to stay consistent
    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    if file_exists:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_cols = reader.fieldnames or []
        # Merge: keep existing order, append any new stat columns
        new_stat_cols = [c for c in all_cols if c not in existing_cols]
        if new_stat_cols:
            # Need to rewrite header — rare edge case when new stats appear
            all_cols = existing_cols + new_stat_cols
            _rewrite_with_new_cols(csv_path, all_cols)
        else:
            all_cols = existing_cols

    written = 0
    mode = 'a' if file_exists else 'w'
    with open(csv_path, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        for r in rows:
            key = (r['date'], str(r['team_id']), str(r['player_id']))
            if key in existing_keys:
                continue
            writer.writerow(r)
            existing_keys.add(key)
            written += 1
    return written


def _rewrite_with_new_cols(csv_path, new_fieldnames):
    """Re-write an existing CSV with an expanded set of column headers."""
    tmp_path = csv_path + '.tmp'
    with open(csv_path, 'r', newline='', encoding='utf-8') as fin, \
         open(tmp_path, 'w', newline='', encoding='utf-8') as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=new_fieldnames, extrasaction='ignore')
        writer.writeheader()
        for row in reader:
            writer.writerow(row)
    os.replace(tmp_path, csv_path)


# ---------------------------------------------------------------------------
# Scoring period helper
# ---------------------------------------------------------------------------
def date_to_scoring_period(target_date, season_year):
    """
    Convert a calendar date to an ESPN scoring period ID.
    ESPN scoring period 1 = Opening Day of the MLB season.
    Approximate opening days (adjust if needed):
      2025: March 27   2026: March 26
    """
    opening_days = {
        2025: date(2025, 3, 27),
        2026: date(2026, 3, 26),
    }
    opening = opening_days.get(season_year)
    if opening is None:
        # Fallback: assume late March
        opening = date(season_year, 3, 27)

    delta = (target_date - opening).days + 1  # SP 1 = opening day
    if delta < 1:
        raise ValueError(f"Date {target_date} is before the {season_year} season opening ({opening}).")
    return delta


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Collect daily ESPN fantasy baseball stats.")
    parser.add_argument('--date', type=str, default=None,
                        help='Target date in YYYY-MM-DD format (default: today)')
    parser.add_argument('--year', type=int, default=2026,
                        help='Season year (default: 2026)')
    args = parser.parse_args()

    target_date = date.today() if args.date is None else datetime.strptime(args.date, '%Y-%m-%d').date()
    target_date_str = target_date.strftime('%Y-%m-%d')
    year = args.year

    print(f"=== Daily Stats Collection ===")
    print(f"  Date  : {target_date_str}")
    print(f"  Season: {year}")

    # 1. Resolve scoring period
    try:
        scoring_period = date_to_scoring_period(target_date, year)
        print(f"  Scoring Period: {scoring_period}")
    except ValueError as e:
        print(f"  ERROR: {e}")
        return

    # 2. Load config & init league
    try:
        config = load_config()
        print("  Config loaded.")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        return

    try:
        league = setup_league(config, year=year)
        print(f"  League initialised: {league}")
    except Exception as e:
        print(f"  ERROR initialising league: {e}")
        return

    # 3. Fetch daily stats
    print("  Fetching player stats...")
    try:
        rows = fetch_daily_stats(league, scoring_period, target_date_str)
        print(f"  Fetched {len(rows)} player records.")
    except Exception as e:
        print(f"  ERROR fetching stats: {e}")
        return

    if not rows:
        print("  No data returned for this scoring period. Games may not have started yet.")
        return

    # 4. Append to CSV with dedup
    os.makedirs(DATA_PATH, exist_ok=True)
    csv_filename = f"stats_espn_daily_{year}.csv"
    csv_path = os.path.join(DATA_PATH, csv_filename)

    print(f"  Loading existing keys for dedup...")
    existing_keys = load_existing_keys(csv_path)
    print(f"  Existing rows: {len(existing_keys)}")

    written = append_rows(csv_path, rows, existing_keys)
    print(f"  New rows written: {written}")
    print(f"  Duplicates skipped: {len(rows) - written}")
    print(f"  CSV path: {csv_path}")
    print("=== Done ===")


if __name__ == '__main__':
    main()
