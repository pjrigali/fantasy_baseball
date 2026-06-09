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
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Path setup — ensure the project root is on sys.path so we can import
# the shared mlb_processing module.
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from espn_api.baseball import League
from espn_api.baseball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP
from fantasy_baseball.mlb_processing import (
    load_config, setup_league, DATA_PATH, date_to_scoring_period,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Lineup slot IDs that indicate a pitcher
PITCHER_SLOT_IDS = {13, 14, 15}   # P, SP, RP




# ---------------------------------------------------------------------------
# Core: fetch daily stats for a single scoring period
# ---------------------------------------------------------------------------
def _build_roster_lookup(league, scoring_period_id):
    """
    Fetch the full roster for every team using the mRoster view, which includes
    bench and IL pitchers that are absent from the mMatchupScore view.

    Returns a dict keyed by (team_id, player_id) -> {lineupSlotId, lineupSlotName}.
    Only pitcher entries (eligible slots contain SP/RP/P slot IDs) are stored;
    batter bench/IL slots are already present in the matchup data.
    """
    params = {
        'view': ['mRoster'],
        'scoringPeriodId': scoring_period_id,
    }
    try:
        data = league.espn_request.league_get(params=params, headers={})
    except Exception:
        return {}

    lookup = {}
    for team in data.get('teams', []):
        team_id = team.get('id')
        roster = team.get('roster', {})
        for entry in roster.get('entries', []):
            pool_entry = entry.get('playerPoolEntry', {})
            player = pool_entry.get('player', {})
            player_id = player.get('id')
            eligible_raw = player.get('eligibleSlots', [])
            if not any(s in PITCHER_SLOT_IDS for s in eligible_raw):
                continue  # only care about pitchers here
            lineup_slot_id = int(entry.get('lineupSlotId', -1))
            lookup[(team_id, player_id)] = {
                'lineup_slot_id': lineup_slot_id,
                'lineup_slot_name': POSITION_MAP.get(lineup_slot_id, str(lineup_slot_id)),
            }
    return lookup


def _extract_entry(
    entry, team_id, team_info, scoring_period_id, target_date_str,
    lineup_slot_override=None,
):
    """
    Convert a single ESPN roster entry dict into a flat row-dict.
    lineup_slot_override is used when the slot is sourced from the mRoster
    view rather than the matchup view (bench/IL pitchers).
    """
    pool_entry = entry.get('playerPoolEntry', {})
    player = pool_entry.get('player', {})

    if lineup_slot_override is not None:
        lineup_slot_id = lineup_slot_override['lineup_slot_id']
        lineup_slot_name = lineup_slot_override['lineup_slot_name']
    else:
        lineup_slot_id = int(entry.get('lineupSlotId', -1))
        lineup_slot_name = POSITION_MAP.get(lineup_slot_id, str(lineup_slot_id))

    default_pos_id = player.get('defaultPositionId', -1)
    default_pos = POSITION_MAP.get(default_pos_id - 1, str(default_pos_id))

    eligible_raw = player.get('eligibleSlots', [])
    eligible_names = [POSITION_MAP.get(s, str(s)) for s in eligible_raw]
    eligible_str = '|'.join(eligible_names)

    injury_status = player.get('injuryStatus', 'ACTIVE')
    injured = player.get('injured', False)
    pro_team_id = player.get('proTeamId', 0)
    pro_team = PRO_TEAM_MAP.get(pro_team_id, str(pro_team_id))
    acquisition_type = pool_entry.get('acquisitionType', '')
    player_type = 'pitcher' if any(s in PITCHER_SLOT_IDS for s in eligible_raw) else 'batter'

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

    if player.get('stats'):
        for stat_block in player['stats']:
            sp_id = stat_block.get('scoringPeriodId')
            stat_source = stat_block.get('statSourceId', -1)
            if sp_id == scoring_period_id and stat_source == 0:
                row['points'] = stat_block.get('appliedTotal', 0)
                for stat_id_str, stat_val in stat_block.get('stats', {}).items():
                    stat_id = int(stat_id_str)
                    if stat_id in STATS_MAP:
                        row[STATS_MAP[stat_id]] = stat_val
                break

    return row


def fetch_daily_stats(league, scoring_period_id, target_date_str):
    """
    Call the ESPN API for a single scoring period and return a list of
    flat row-dicts ready for CSV output.

    Uses two API views:
      - mMatchupScore / mScoreboard  : active-slot players with scoring stats
      - mRoster                      : full roster, used to back-fill bench and
                                       IL pitchers that the matchup view omits

    Each row captures:
      - identifiers  : date, team, player
      - metadata     : position, lineup slot, injury, pro team, eligibility
      - stats        : every stat id mapped through STATS_MAP
    """
    team_map = {t.team_id: {'name': t.team_name, 'abbrev': t.team_abbrev} for t in league.teams}

    # --- Step 1: full roster lookup (bench + IL pitchers) ---
    roster_lookup = _build_roster_lookup(league, scoring_period_id)

    # --- Step 2: matchup data (active slots for all players) ---
    params = {
        'view': ['mMatchupScore', 'mScoreboard'],
        'scoringPeriodId': scoring_period_id,
    }

    data = league.espn_request.league_get(params=params, headers={})
    schedule = data.get('schedule', [])

    rows = []
    seen_pitcher_keys = set()  # track (team_id, player_id) for pitchers already added

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
                player_id = entry.get('playerPoolEntry', {}).get('player', {}).get('id')
                eligible_raw = entry.get('playerPoolEntry', {}).get('player', {}).get('eligibleSlots', [])
                is_pitcher = any(s in PITCHER_SLOT_IDS for s in eligible_raw)

                # Use the roster_lookup slot for pitchers so we get the correct
                # BE/IL slot rather than whatever the matchup view reports.
                slot_override = roster_lookup.get((team_id, player_id)) if is_pitcher else None

                row = _extract_entry(
                    entry, team_id, team_info, scoring_period_id, target_date_str,
                    lineup_slot_override=slot_override,
                )
                rows.append(row)

                if is_pitcher:
                    seen_pitcher_keys.add((team_id, player_id))

    # --- Step 3: back-fill bench + IL pitchers missing from matchup view ---
    # Build a reverse map: team_id -> list of mRoster entries, restricted to
    # pitchers not already emitted above.
    #
    # The mRoster view returns player data under league.teams[].roster.entries,
    # but we already parsed that into roster_lookup (slot info only). We need
    # the full entry dicts, so we re-fetch to get player/stats payloads.
    # We reuse the same mRoster response cached in _build_roster_lookup by
    # making a second lightweight call here. This is a small penalty (~1 extra
    # API call per day) but keeps the logic clean.
    try:
        roster_data = league.espn_request.league_get(
            params={'view': ['mRoster'], 'scoringPeriodId': scoring_period_id},
            headers={},
        )
        for team in roster_data.get('teams', []):
            team_id = team.get('id')
            team_info = team_map.get(team_id, {'name': '', 'abbrev': ''})
            for entry in team.get('roster', {}).get('entries', []):
                pool_entry = entry.get('playerPoolEntry', {})
                player = pool_entry.get('player', {})
                player_id = player.get('id')
                eligible_raw = player.get('eligibleSlots', [])

                if not any(s in PITCHER_SLOT_IDS for s in eligible_raw):
                    continue  # batters handled by matchup view
                if (team_id, player_id) in seen_pitcher_keys:
                    continue  # active-slot pitcher already added

                # This is a bench or IL pitcher absent from the matchup view
                slot_info = roster_lookup.get((team_id, player_id))
                row = _extract_entry(
                    entry, team_id, team_info, scoring_period_id, target_date_str,
                    lineup_slot_override=slot_info,
                )
                rows.append(row)
    except Exception:
        pass  # mRoster back-fill is best-effort; active-slot data is already captured

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
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Collect daily ESPN fantasy baseball stats.")
    parser.add_argument('--date', type=str, default=None,
                        help='Target date YYYY-MM-DD (default: auto-detect from time of day)')
    parser.add_argument('--year', type=int, default=2026,
                        help='Season year (default: 2026)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview rows that would be written without saving to disk')
    args = parser.parse_args()

    year = args.year

    # Determine which dates to collect.
    # Explicit --date: collect only that date.
    # Auto-detect: before noon → yesterday only (avoid partial-day grabs);
    #              noon or later → yesterday + today.
    if args.date is not None:
        dates = [datetime.strptime(args.date, '%Y-%m-%d').date()]
    else:
        today = date.today()
        yesterday = today - timedelta(days=1)
        end_date = yesterday if datetime.now().hour < 12 else today

        # Auto-detect gaps: find the last recorded date in the CSV and backfill
        # from the day after it through end_date. Falls back to yesterday/today
        # if the file doesn't exist yet.
        csv_path_check = os.path.join(DATA_PATH, f"stats_espn_daily_{year}.csv")
        last_recorded = None
        if os.path.exists(csv_path_check):
            with open(csv_path_check, 'r', newline='', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    d = date.fromisoformat(row['date'])
                    if last_recorded is None or d > last_recorded:
                        last_recorded = d

        if last_recorded is not None and last_recorded < end_date:
            start_date = last_recorded + timedelta(days=1)
            dates = []
            cur = start_date
            while cur <= end_date:
                dates.append(cur)
                cur += timedelta(days=1)
        else:
            dates = [yesterday] if datetime.now().hour < 12 else [yesterday, today]

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"[ERROR] collect_stats_espn_daily: {e}")
        return

    try:
        league = setup_league(config, year=year)
    except Exception as e:
        print(f"[ERROR] collect_stats_espn_daily: failed to init league — {e}")
        return

    os.makedirs(DATA_PATH, exist_ok=True)
    csv_path = os.path.join(DATA_PATH, f"stats_espn_daily_{year}.csv")
    existing_keys = load_existing_keys(csv_path)

    total_written = 0
    total_dupes = 0

    for target_date in dates:
        target_date_str = target_date.strftime('%Y-%m-%d')

        try:
            scoring_period = date_to_scoring_period(target_date, year)
        except ValueError as e:
            print(f"[ERROR] collect_stats_espn_daily: {e}")
            continue

        try:
            rows = fetch_daily_stats(league, scoring_period, target_date_str)
        except Exception as e:
            print(f"[ERROR] collect_stats_espn_daily: failed to fetch stats for {target_date_str} — {e}")
            continue

        if not rows:
            print(f"[WARN]  collect_stats_espn_daily: no data for SP {scoring_period} ({target_date_str}) — games may not have started")
            continue

        if args.dry_run:
            new = [r for r in rows if (r['date'], str(r['team_id']), str(r['player_id'])) not in existing_keys]
            for r in new:
                existing_keys.add((r['date'], str(r['team_id']), str(r['player_id'])))
            total_written += len(new)
            total_dupes += len(rows) - len(new)
        else:
            written = append_rows(csv_path, rows, existing_keys)
            total_written += written
            total_dupes += len(rows) - written

    date_range = f"{dates[0]} → {dates[-1]}" if len(dates) > 1 else str(dates[0])
    tag = "[DRY-RUN]" if args.dry_run else "[OK]   "
    verb = "would write" if args.dry_run else "rows written,"
    print(f"{tag} collect_stats_espn_daily: {total_written} {verb} {total_dupes} dupes skipped | {date_range}")

    # ── Write run log ─────────────────────────────────────────────────────────
    if not args.dry_run:
        try:
            _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'data-lake', '00_Logs', 'fantasy_baseball')
            os.makedirs(_log_dir, exist_ok=True)
            _csv_rows = sum(1 for _ in open(csv_path, encoding='utf-8')) - 1
            _entry = {
                'ts'             : datetime.now().isoformat(timespec='seconds'),
                'workflow'       : 'fantasy-collect-daily-espn-stats',
                'status'         : 'ok',
                'csv_path'       : csv_path,
                'csv_total_rows' : _csv_rows,
                'rows_written'   : total_written,
                'last_date_in_csv': str(dates[-1]) if dates else '',
            }
            with open(os.path.join(_log_dir, 'fantasy-collect-daily-espn-stats.jsonl'), 'a', encoding='utf-8') as _f:
                _f.write(json.dumps(_entry) + '\n')
        except Exception as _e:
            print(f'[WARN] run-log write failed: {_e}')


if __name__ == '__main__':
    main()
