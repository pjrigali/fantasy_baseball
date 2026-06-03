"""
fetch_stats_mlb_boxscore.py
============================
Description: Fetches per-game hitting and pitching stats for all MLB players
             via the MLB Stats API boxscore endpoint. Collects one request per
             game (vs one per player in fetch_stats_mlb_daily.py), then extracts
             stats for every player on each team's active roster — including
             players who were present but did not play (did_play=0). This
             supports play-frequency analysis alongside standard box-score stats.

             Flow:
               1. GET /api/v1/schedule  — find all Final games in the date range
               2. GET /api/v1/game/{gamePk}/boxscore  — one request per game (~15/day)
               3. Emit one row per player per game per role (batter or pitcher).
                  Bench players get zeroed stats with did_play=0.

Source Data: MLB Stats API
               /api/v1/schedule?startDate=...&endDate=...&sportId=1&gameType=R
               /api/v1/game/{gamePk}/boxscore

Outputs: data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_{year}.csv
         Columns match stats_mlb_daily_{year}.csv plus a did_play flag.
         Deduplicates on (date, player_id, b_or_p). Safe to re-run.
"""

import requests
import csv
import os
import sys
import time
import argparse
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
}

PITCHER_POSITIONS = {'P', 'SP', 'RP', 'TWP'}

SEASON_START = {
    2025: date(2025, 3, 20),
    2026: date(2026, 3, 26),
}

BATTER_COLS = [
    'G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'SB', 'CS',
    'B_BB', 'SO', 'HBP', 'SF', 'TB',
]
PITCHER_COLS = [
    'G', 'GS', 'W', 'L', 'SV', 'HLD', 'SVHD', 'OUTS',
    'P_H', 'P_R', 'ER', 'P_HR', 'P_BB', 'K', 'QS',
]
ALL_STAT_COLS = sorted(set(BATTER_COLS + PITCHER_COLS))

OUTPUT_COLS = [
    'date', 'scoring_period', 'player_id', 'player_name',
    'team_id', 'team_name', 'opponent_id', 'is_home',
    'game_id', 'b_or_p', 'did_play',
] + ALL_STAT_COLS


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_game_ids(start_date: str, end_date: str) -> list[dict]:
    """Return list of {gamePk, date, home_id, away_id} for all Final games."""
    url = (
        f'https://statsapi.mlb.com/api/v1/schedule'
        f'?startDate={start_date}&endDate={end_date}&sportId=1&gameType=R'
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f'  Schedule fetch error: {e}')
        return []

    games = []
    for day in resp.json().get('dates', []):
        for g in day.get('games', []):
            if g['status']['abstractGameState'] != 'Final':
                continue
            games.append({
                'gamePk':   g['gamePk'],
                'date':     g['officialDate'],
                'home_id':  g['teams']['home']['team']['id'],
                'home_name': g['teams']['home']['team']['name'],
                'away_id':  g['teams']['away']['team']['id'],
                'away_name': g['teams']['away']['team']['name'],
            })
    return games


def get_boxscore(game_pk: int) -> dict | None:
    """Fetch boxscore for a single game. Returns None on error."""
    url = f'https://statsapi.mlb.com/api/v1/game/{game_pk}/boxscore'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f'  Boxscore fetch error for game {game_pk}: {e}')
        return None


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def scoring_period(game_date_str: str, season: int) -> int:
    season_start = SEASON_START.get(season, date(season, 3, 26))
    try:
        d = datetime.strptime(game_date_str, '%Y-%m-%d').date()
        return max(1, (d - season_start).days + 1)
    except ValueError:
        return 0


def _ip_to_outs(ip_str: str) -> int:
    s = str(ip_str)
    if '.' in s:
        inn, partial = s.split('.')
        return int(inn) * 3 + int(partial)
    return int(s) * 3 if s else 0


def build_batter_row(player: dict, meta: dict) -> dict:
    s = player['stats'].get('batting', {})
    did_play = 1 if s.get('plateAppearances', 0) or s.get('atBats', 0) else 0
    row = {c: '' for c in ALL_STAT_COLS}
    row.update({
        'G':    1,
        'AB':   s.get('atBats', 0),
        'R':    s.get('runs', 0),
        'H':    s.get('hits', 0),
        '2B':   s.get('doubles', 0),
        '3B':   s.get('triples', 0),
        'HR':   s.get('homeRuns', 0),
        'RBI':  s.get('rbi', 0),
        'SB':   s.get('stolenBases', 0),
        'CS':   s.get('caughtStealing', 0),
        'B_BB': s.get('baseOnBalls', 0),
        'SO':   s.get('strikeOuts', 0),
        'HBP':  s.get('hitByPitch', 0),
        'SF':   s.get('sacFlies', 0),
        'TB':   s.get('totalBases', 0),
    })
    row.update(meta)
    row['b_or_p'] = 'batter'
    row['did_play'] = did_play
    return row


def build_pitcher_row(player: dict, meta: dict) -> dict:
    s = player['stats'].get('pitching', {})
    outs = s.get('outs', 0) or _ip_to_outs(s.get('inningsPitched', '0'))
    gs = s.get('gamesStarted', 0)
    er = s.get('earnedRuns', 0)
    sv = s.get('saves', 0)
    hld = s.get('holds', 0)
    did_play = 1 if s.get('gamesPitched', 0) or outs else 0
    row = {c: '' for c in ALL_STAT_COLS}
    row.update({
        'G':    1,
        'GS':   gs,
        'W':    s.get('wins', 0),
        'L':    s.get('losses', 0),
        'SV':   sv,
        'HLD':  hld,
        'SVHD': sv + hld,
        'OUTS': outs,
        'P_H':  s.get('hits', 0),
        'P_R':  s.get('runs', 0),
        'ER':   er,
        'P_HR': s.get('homeRuns', 0),
        'P_BB': s.get('baseOnBalls', 0),
        'K':    s.get('strikeOuts', 0),
        'QS':   1 if (gs == 1 and outs >= 18 and er <= 3) else 0,
    })
    row.update(meta)
    row['b_or_p'] = 'pitcher'
    row['did_play'] = did_play
    return row


def extract_rows(boxscore: dict, game_info: dict, season: int) -> list[dict]:
    """Extract one row per player per role from a boxscore."""
    rows = []
    sp = scoring_period(game_info['date'], season)

    for side in ('home', 'away'):
        team_data = boxscore['teams'][side]
        team_id   = team_data['team']['id']
        team_name = team_data['team']['name']
        is_home   = (side == 'home')
        opp_id    = game_info['away_id'] if is_home else game_info['home_id']

        meta = {
            'date':           game_info['date'],
            'scoring_period': sp,
            'team_id':        team_id,
            'team_name':      team_name,
            'opponent_id':    opp_id,
            'is_home':        is_home,
            'game_id':        game_info['gamePk'],
        }

        for player_key, player in team_data.get('players', {}).items():
            pid  = player['person']['id']
            name = player['person']['fullName']
            pos  = player.get('position', {}).get('abbreviation', '')
            meta_p = {**meta, 'player_id': pid, 'player_name': name}

            batting_stats  = player['stats'].get('batting', {})
            pitching_stats = player['stats'].get('pitching', {})

            if pos in PITCHER_POSITIONS:
                rows.append(build_pitcher_row(player, meta_p))
                # Two-way: also emit a batter row if they actually batted
                if batting_stats.get('plateAppearances', 0):
                    rows.append(build_batter_row(player, meta_p))
            else:
                rows.append(build_batter_row(player, meta_p))
                # Position player who also pitched
                if pitching_stats.get('gamesPitched', 0):
                    rows.append(build_pitcher_row(player, meta_p))

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Fetch MLB daily stats via boxscore endpoint')
    parser.add_argument('--year', type=int, default=datetime.now().year)
    parser.add_argument('--start-date', type=str, default=None,
                        help='Collect from this date YYYY-MM-DD (overrides auto-detect from CSV)')
    parser.add_argument('--date', type=str, default=None,
                        help='Collect through this date YYYY-MM-DD (default: auto-detect)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    season = args.year

    if args.date:
        target_date = args.date
    elif datetime.now().hour < 12:
        target_date = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')
    else:
        target_date = date.today().strftime('%Y-%m-%d')

    output_file = os.path.join(mp.DATA_PATH, f'stats_mlb_boxscore_{season}.csv')

    # Load existing rows to determine start date and dedup keys
    existing_keys = set()
    existing_rows = []
    start_date = f'{season}-03-23'

    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                existing_rows.append(row)
                existing_keys.add((row['date'], str(row['player_id']), row['b_or_p']))
        if existing_rows:
            start_date = max(r['date'] for r in existing_rows)  # one-day overlap, deduped

    if args.start_date:
        start_date = args.start_date

    games = get_game_ids(start_date, target_date)
    print(f'  Found {len(games)} Final games between {start_date} and {target_date}')

    new_rows = []
    for game in games:
        print(f'  {game["date"]}  {game["away_name"]} @ {game["home_name"]}  (pk={game["gamePk"]})')
        boxscore = get_boxscore(game['gamePk'])
        if not boxscore:
            continue
        for row in extract_rows(boxscore, game, season):
            key = (row['date'], str(row['player_id']), row['b_or_p'])
            if key not in existing_keys:
                new_rows.append(row)
                existing_keys.add(key)
        time.sleep(0.5)

    tag  = '[DRY-RUN]' if args.dry_run else '[OK]   '
    verb = 'would write' if args.dry_run else 'rows written'

    if new_rows and not args.dry_run:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        write_header = not existing_rows
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(existing_rows)
            writer.writerows(new_rows)

    print(f'{tag} fetch_stats_mlb_boxscore: {len(new_rows)} {verb} | '
          f'{start_date} → {target_date} | {len(games)} games')

    # ── Write run log ─────────────────────────────────────────────────────────
    if not args.dry_run:
        try:
            import json as _json
            _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'data-lake', '00_Logs', 'fantasy_baseball')
            os.makedirs(_log_dir, exist_ok=True)
            _csv_rows = len(existing_rows) + len(new_rows)
            _entry = {
                'ts'             : datetime.now().isoformat(timespec='seconds'),
                'workflow'       : 'fantasy-collect-daily-mlb-stats',
                'status'         : 'ok',
                'csv_path'       : output_file,
                'csv_total_rows' : _csv_rows,
                'rows_written'   : len(new_rows),
                'last_date_in_csv': target_date,
                'games_fetched'  : len(games),
            }
            with open(os.path.join(_log_dir, 'fantasy-collect-daily-mlb-stats.jsonl'), 'a', encoding='utf-8') as _f:
                _f.write(_json.dumps(_entry) + '\n')
        except Exception as _e:
            print(f'[WARN] run-log write failed: {_e}')


if __name__ == '__main__':
    main()
