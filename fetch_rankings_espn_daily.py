"""
fetch_rankings_espn_daily.py
============================
Description: Fetches daily player ownership, trending, and positional ranking data
             from the ESPN Fantasy Baseball API for all players (rostered and free agents).
             Captures percent owned, percent started, percent change (trending signal),
             average draft position, auction value, standard draft rank, and a computed
             positional rank (1 = most owned within that position group).

Source Data: ESPN Fantasy Baseball API (kona_player_info view). Credentials read from
             config.ini under [BASEBALL]: BB_LEAGUE_ID, BB_SWID, BB_ESPN_2.

Outputs: .data_lake/01_Bronze/fantasy_baseball/rankings_espn_daily_{year}.csv
         One row per player per date. Deduplicates on (date, player_id).
"""

import os
import sys
import csv
import json
import argparse
from datetime import datetime, date

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from espn_api.baseball.constant import POSITION_MAP, PRO_TEAM_MAP
from fantasy_baseball.mlb_processing import (
    load_config, setup_league, DATA_PATH, date_to_scoring_period,
)

# ---------------------------------------------------------------------------
# Position slot IDs — mirrors the POSITION_SLOT_IDS map in mlb_processing.py
# ---------------------------------------------------------------------------
POSITION_SLOT_IDS = {
    'C':  [0],
    '1B': [1],
    '2B': [2],
    '3B': [3],
    'SS': [4],
    'OF': [5],
    'DH': [12],
    'SP': [14],
    'RP': [15],
}

FIXED_COLS = [
    'date', 'scoring_period', 'player_id', 'player_name', 'player_position',
    'pro_team', 'injury_status', 'injured', 'on_team_id', 'trending_type',
    'eligible_slots',
    'pct_owned', 'pct_started', 'pct_change',
    'avg_draft_position', 'auction_value_avg', 'draft_rank_standard',
    'position_rank', 'total_rank',
    'pr7', 'pr15', 'pr30', 'pr_season',
]


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_player_rankings(league, scoring_period_id, size=300):
    """
    Fetch all players from the ESPN kona_player_info view across every position.
    Returns a list of (pos_group, raw_entry) tuples, deduplicated by player_id
    (first position match wins).
    """
    seen = {}

    for pos_name, slot_ids in POSITION_SLOT_IDS.items():
        filters = {
            "players": {
                "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
                "filterSlotIds": {"value": slot_ids},
                "limit": size,
                "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
            }
        }
        params = {
            'view': 'kona_player_info',
            'scoringPeriodId': scoring_period_id,
        }
        headers = {'x-fantasy-filter': json.dumps(filters)}

        try:
            data = league.espn_request.league_get(params=params, headers=headers)
        except Exception as e:
            print(f"  WARNING: failed to fetch {pos_name}: {e}")
            continue

        for entry in data.get('players', []):
            pid = entry.get('id')
            if pid is not None and pid not in seen:
                seen[pid] = (pos_name, entry)

    return list(seen.values())


# ---------------------------------------------------------------------------
# Parse
# ---------------------------------------------------------------------------
def parse_player_entry(pos_name, entry, target_date_str, scoring_period_id):
    """
    Flatten a single kona_player_info entry into a flat row dict.

    ESPN response structure (kona_player_info view):
      entry['player']          — player identity, ownership, stats
      entry['ratings']         — per-period positional/total rank and rating score
                                 keys: "0"=season, "1"=last7d, "2"=last15d, "3"=last30d
      entry['onTeamId']        — fantasy team that owns the player (0 = free agent)
      entry['status']          — ONTEAM / FREEAGENT / WAIVERS  (trending_type)
    """
    player = entry.get('player', {})

    player_id       = player.get('id', entry.get('id', ''))
    player_name     = player.get('fullName', '')
    player_position = pos_name   # fantasy slot from the filter loop (C, 1B, OF, SP, RP, etc.)

    pro_team_id    = player.get('proTeamId', 0)
    pro_team       = PRO_TEAM_MAP.get(pro_team_id, str(pro_team_id))

    eligible_raw   = player.get('eligibleSlots', [])
    eligible_slots = '|'.join(POSITION_MAP.get(s, str(s)) for s in eligible_raw)

    injury_status  = player.get('injuryStatus', 'ACTIVE')
    injured        = player.get('injured', False)

    on_team_id     = entry.get('onTeamId', 0)
    trending_type  = entry.get('status', '')          # ONTEAM / FREEAGENT / WAIVERS

    ownership       = player.get('ownership', {}) or {}
    pct_owned       = ownership.get('percentOwned', 0.0)
    pct_started     = ownership.get('percentStarted', 0.0)
    pct_change      = ownership.get('percentChange', 0.0)
    adp             = ownership.get('averageDraftPosition', 0.0)
    auction_val_avg = ownership.get('auctionValueAverage', 0.0)

    draft_ranks   = player.get('draftRanksByRankType', {}) or {}
    standard_rank = draft_ranks.get('STANDARD', {}).get('rank', 0) if draft_ranks else 0

    # ratings: "0"=season, "1"=last7d, "2"=last15d, "3"=last30d
    # totalRating  → PR7 / PR15 / PR30 / pr_season shown on ESPN trending page
    # positionalRanking → PRK (position rank within position group)
    # totalRanking      → overall rank across all players
    ratings = entry.get('ratings', {}) or {}

    def _get_rating(period_key):
        r = ratings.get(str(period_key), {}) or {}
        return (
            r.get('totalRating', 0.0),
            r.get('positionalRanking', 0),
            r.get('totalRanking', 0),
        )

    pr_season_val, pos_rank, total_rank = _get_rating(0)
    pr7_val,       _,        _          = _get_rating(1)
    pr15_val,      _,        _          = _get_rating(2)
    pr30_val,      _,        _          = _get_rating(3)

    def _f(v, decimals=2):
        try:
            return round(float(v), decimals)
        except (TypeError, ValueError):
            return 0.0

    return {
        'date':                 target_date_str,
        'scoring_period':       scoring_period_id,
        'player_id':            player_id,
        'player_name':          player_name,
        'player_position':      player_position,
        'pro_team':             pro_team,
        'injury_status':        injury_status,
        'injured':              injured,
        'on_team_id':           on_team_id,
        'trending_type':        trending_type,
        'eligible_slots':       eligible_slots,
        'pct_owned':            _f(pct_owned),
        'pct_started':          _f(pct_started),
        'pct_change':           _f(pct_change),
        'avg_draft_position':   _f(adp, 1),
        'auction_value_avg':    _f(auction_val_avg),
        'draft_rank_standard':  int(standard_rank) if standard_rank else 0,
        'position_rank':        int(pos_rank) if pos_rank else 0,
        'total_rank':           int(total_rank) if total_rank else 0,
        'pr7':                  _f(pr7_val),
        'pr15':                 _f(pr15_val),
        'pr30':                 _f(pr30_val),
        'pr_season':            _f(pr_season_val),
    }


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
def load_existing_keys(csv_path):
    keys = set()
    if not os.path.exists(csv_path):
        return keys
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            keys.add((row['date'], str(row['player_id'])))
    return keys


def append_rows(csv_path, rows, existing_keys):
    if not rows:
        return 0

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0

    if file_exists:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            cols = csv.DictReader(f).fieldnames or FIXED_COLS
    else:
        cols = FIXED_COLS

    written = 0
    mode = 'a' if file_exists else 'w'
    with open(csv_path, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        for r in rows:
            key = (r['date'], str(r['player_id']))
            if key in existing_keys:
                continue
            writer.writerow(r)
            existing_keys.add(key)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='Collect daily ESPN player rankings.')
    parser.add_argument('--date', type=str, default=None,
                        help='Target date YYYY-MM-DD (default: today)')
    parser.add_argument('--year', type=int, default=2026,
                        help='Season year (default: 2026)')
    parser.add_argument('--size', type=int, default=300,
                        help='Players to fetch per position slot (default: 300)')
    args = parser.parse_args()

    target_date     = date.today() if args.date is None else datetime.strptime(args.date, '%Y-%m-%d').date()
    target_date_str = target_date.strftime('%Y-%m-%d')
    year            = args.year

    try:
        scoring_period = date_to_scoring_period(target_date, year)
    except ValueError as e:
        print(f'[ERROR] fetch_rankings_espn_daily: {e}')
        return

    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f'[ERROR] fetch_rankings_espn_daily: {e}')
        return

    try:
        league = setup_league(config, year=year)
    except Exception as e:
        print(f'[ERROR] fetch_rankings_espn_daily: failed to init league — {e}')
        return

    raw = fetch_player_rankings(league, scoring_period, size=args.size)
    if not raw:
        print(f'[WARN]  fetch_rankings_espn_daily: no players returned for {target_date_str}')
        return

    rows = [parse_player_entry(pos, entry, target_date_str, scoring_period)
            for pos, entry in raw]

    os.makedirs(DATA_PATH, exist_ok=True)
    csv_path = os.path.join(DATA_PATH, f'rankings_espn_daily_{year}.csv')
    existing_keys = load_existing_keys(csv_path)
    written = append_rows(csv_path, rows, existing_keys)
    print(f'[OK]    fetch_rankings_espn_daily: {written} rows written, {len(rows) - written} dupes skipped | {target_date_str} SP {scoring_period} | {len(raw)} players fetched')


if __name__ == '__main__':
    main()
