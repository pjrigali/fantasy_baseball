"""
fetch_closer_depth_mlb.py
==========================
Description: Fetches bullpen depth chart data for all 30 MLB teams from the
             MLB Stats API depthChart roster endpoint. Captures each reliever's
             official role designation (Closer, Pitcher), injury status, and
             season pitching stats. Intended to replace fetch_closer_depth_fangraphs.py,
             which broke when FanGraphs added bot-detection (403 Forbidden).

             Key differences vs the FanGraphs version:
               - Role source: official MLB roster designation (not editorial)
               - "Closer" maps to position_code "C" in the API
               - "Pitcher" (code "1") covers all non-starter, non-closer relievers —
                 there is no "Setup Man" or "Closer Committee" tier in the MLB API
               - Hot Seat / On the Rise editorial signals are not available
               - Closer committee situations surface as multiple code-C entries
                 on the same team (e.g. KC listing two pitchers as Closer)
               - SwStr%, K%, BB% are not available from this endpoint —
                 those Statcast metrics can be joined from Baseball Savant if needed

             Run ~3x/week. Safe to re-run; deduplicates on (date_scraped, player_id).

Source Data: MLB Stats API
               /api/v1/teams/{teamId}/roster?rosterType=depthChart
               &hydrate=person(pitchHand,stats(type=season,group=pitching,season={year}))

Outputs: data-lake/01_Bronze/fantasy_baseball/closer_depth_mlb_{year}.csv
         Columns: date_scraped, team_id, team_name, player_id, player_name,
                  throws, position_code, role, status,
                  games, innings_pitched, era, sv, hld, sd,
                  save_opportunities, blown_saves, k9, whip, strikeouts, walks
"""

import requests
import csv
import os
import sys
import time
import argparse
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
}

# All 30 MLB team IDs
TEAM_IDS = [
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
    118, 119, 120, 121, 133, 134, 135, 136, 137, 138,
    139, 140, 141, 142, 143, 144, 145, 146, 147, 158,
]

# The depthChart roster endpoint does not return a top-level team name,
# so we maintain a static mapping here. Team names are stable season to season.
TEAM_ID_TO_NAME = {
    108: 'Los Angeles Angels',
    109: 'Arizona Diamondbacks',
    110: 'Baltimore Orioles',
    111: 'Boston Red Sox',
    112: 'Chicago Cubs',
    113: 'Cincinnati Reds',
    114: 'Cleveland Guardians',
    115: 'Colorado Rockies',
    116: 'Detroit Tigers',
    117: 'Houston Astros',
    118: 'Kansas City Royals',
    119: 'Los Angeles Dodgers',
    120: 'Washington Nationals',
    121: 'New York Mets',
    133: 'Athletics',
    134: 'Pittsburgh Pirates',
    135: 'San Diego Padres',
    136: 'Seattle Mariners',
    137: 'San Francisco Giants',
    138: 'St. Louis Cardinals',
    139: 'Tampa Bay Rays',
    140: 'Texas Rangers',
    141: 'Toronto Blue Jays',
    142: 'Minnesota Twins',
    143: 'Philadelphia Phillies',
    144: 'Atlanta Braves',
    145: 'Chicago White Sox',
    146: 'Miami Marlins',
    147: 'New York Yankees',
    158: 'Milwaukee Brewers',
}

# Position codes that indicate a pitcher (exclude hitters/catchers/infielders)
PITCHER_CODES = {'C', '1', 'S', 'P', 'SP', 'RP', 'TWP'}

OUTPUT_FIELDS = [
    'date_scraped',
    'team_id', 'team_name',
    'player_id', 'player_name',
    'throws',             # R / L / S  (from pitchHand.code)
    'position_code',      # C = Closer | 1 = Pitcher | S = Starting Pitcher
    'role',               # "Closer" | "Pitcher" | "Starting Pitcher"
    'status',             # Active | Injured 15-Day | Injured 60-Day | etc.
    'games',              # season appearances
    'innings_pitched',
    'era',
    'sv',                 # saves
    'hld',                # holds
    'sd',                 # saves + holds (mirrors FanGraphs sd column)
    'save_opportunities',
    'blown_saves',
    'k9',                 # strikeouts per 9 innings
    'whip',
    'strikeouts',
    'walks',
]


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_team_roster(team_id: int, season: int) -> dict:
    """Fetch depthChart roster with pitching stats hydration for one team."""
    url = (
        f'https://statsapi.mlb.com/api/v1/teams/{team_id}/roster'
        f'?rosterType=depthChart'
        f'&season={season}'
        f'&hydrate=person(pitchHand,stats(type=season,group=pitching,season={season}))'
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f'  [WARN] Team {team_id} fetch error: {e}')
        return {}


def _safe_stat(stat_dict: dict, key: str, default='') -> str:
    """Return a stat value as a string, or default if missing/None."""
    val = stat_dict.get(key)
    if val is None:
        return default
    return str(val)


def extract_players(data: dict, team_id: int, season: int, today_str: str) -> list[dict]:
    """Parse one team's depthChart roster response into a list of row dicts."""
    rows = []
    team_name = ''

    # Team name can come from the first roster entry or a top-level team block
    roster = data.get('roster', [])
    if not roster:
        return rows

    for entry in roster:
        person      = entry.get('person', {})
        position    = entry.get('position', {})
        status_info = entry.get('status', {})

        pos_code = position.get('code', '')
        pos_name = position.get('name', '')

        # Skip non-pitchers (catchers, infielders, outfielders, DH)
        if pos_code not in PITCHER_CODES and pos_name not in {
            'Pitcher', 'Closer', 'Starting Pitcher', 'Relief Pitcher', 'Two-Way Player'
        }:
            continue

        player_id   = str(person.get('id', ''))
        player_name = person.get('fullName', '')

        # Throws hand: nested under pitchHand
        pitch_hand  = person.get('pitchHand', {})
        throws      = pitch_hand.get('code', '')   # 'R', 'L', or 'S'

        # Status description (Active / Injured 15-Day / etc.)
        status_desc = status_info.get('description', 'Active')

        # Season pitching stats — path: person.stats[0].splits[0].stat
        stat_dict = {}
        person_stats = person.get('stats', [])
        if person_stats:
            splits = person_stats[0].get('splits', [])
            if splits:
                stat_dict = splits[0].get('stat', {})

        sv  = int(stat_dict.get('saves', 0) or 0)
        hld = int(stat_dict.get('holds', 0) or 0)

        row = {
            'date_scraped':      today_str,
            'team_id':           team_id,
            'team_name':         team_name,   # filled below after first pass
            'player_id':         player_id,
            'player_name':       player_name,
            'throws':            throws,
            'position_code':     pos_code,
            'role':              pos_name,
            'status':            status_desc,
            'games':             _safe_stat(stat_dict, 'gamesPitched'),
            'innings_pitched':   _safe_stat(stat_dict, 'inningsPitched'),
            'era':               _safe_stat(stat_dict, 'era'),
            'sv':                str(sv),
            'hld':               str(hld),
            'sd':                str(sv + hld),
            'save_opportunities': _safe_stat(stat_dict, 'saveOpportunities'),
            'blown_saves':       _safe_stat(stat_dict, 'blownSaves'),
            'k9':                _safe_stat(stat_dict, 'strikeoutsPer9Inn'),
            'whip':              _safe_stat(stat_dict, 'whip'),
            'strikeouts':        _safe_stat(stat_dict, 'strikeOuts'),
            'walks':             _safe_stat(stat_dict, 'baseOnBalls'),
        }
        rows.append(row)

    # The depthChart endpoint does not include a team name in its response;
    # resolve it from the static lookup table.
    resolved_name = TEAM_ID_TO_NAME.get(team_id, str(team_id))
    for r in rows:
        r['team_name'] = resolved_name

    return rows


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def load_existing(filepath: str):
    """Return (list_of_rows, set_of_dedup_keys) from existing CSV, or empty."""
    rows = []
    keys = set()
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                rows.append(row)
                keys.add((row['date_scraped'], row['player_id']))
    return rows, keys


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Fetch MLB depthChart closer/bullpen roles → Bronze data lake.'
    )
    parser.add_argument('--year', type=int, default=date.today().year,
                        help='Season year (default: current year)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Fetch and parse without writing to disk')
    args = parser.parse_args()

    season    = args.year
    today_str = date.today().strftime('%Y-%m-%d')
    output_file = os.path.join(mp.DATA_PATH, f'closer_depth_mlb_{season}.csv')

    print(f'=== MLB Closer Depth Chart — {today_str} (season {season}) ===')

    # ---- Check if already current ----
    if not args.dry_run and os.path.exists(output_file):
        existing_rows, existing_keys = load_existing(output_file)
        already = sum(1 for k in existing_keys if k[0] == today_str)
        if already > 0:
            print(f'  Already current — {already} rows already recorded for {today_str}.')
            return
    else:
        existing_rows, existing_keys = [], set()

    # ---- Fetch all 30 teams ----
    all_players = []
    for team_id in TEAM_IDS:
        data = fetch_team_roster(team_id, season)
        players = extract_players(data, team_id, season, today_str)
        team_name = players[0]['team_name'] if players else str(team_id)
        closers = [p for p in players if p['position_code'] == 'C']
        print(f'  {team_name:<30}  {len(players):>3} pitchers  '
              f'{len(closers)} closer(s): '
              f'{", ".join(p["player_name"] for p in closers) or "none designated"}')
        all_players.extend(players)
        time.sleep(0.3)   # polite delay

    print(f'  Total pitchers fetched: {len(all_players)} across {len(TEAM_IDS)} teams')

    # ---- Dry-run output ----
    if args.dry_run:
        closers_only = [p for p in all_players if p['position_code'] == 'C']
        print(f'\n[DRY-RUN] Would write {len(all_players)} rows -> {output_file}')
        print(f'  Closers ({len(closers_only)}):')
        print(f'  {"TEAM":<28} {"PLAYER":<26} {"STATUS":<22} {"SV":>3} {"HLD":>4} {"ERA":>6} {"K/9":>5}')
        print('  ' + '-' * 97)
        for p in sorted(closers_only, key=lambda x: x['team_name']):
            print(f'  {p["team_name"]:<28} {p["player_name"]:<26} {p["status"]:<22} '
                  f'{p["sv"]:>3} {p["hld"]:>4} {p["era"]:>6} {p["k9"]:>5}')
        return

    # ---- Dedup and write ----
    new_rows = [
        p for p in all_players
        if (p['date_scraped'], p['player_id']) not in existing_keys
    ]

    if not new_rows:
        print(f'  Already current — 0 new rows for {today_str}.')
        return

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    total = len(existing_rows) + len(new_rows)
    closers_today = sum(1 for r in new_rows if r['position_code'] == 'C')
    print(f'[OK]    fetch_closer_depth_mlb: {len(new_rows)} rows written | {today_str} '
          f'| {closers_today} closers designated')
    print(f'  File total: {total} rows ({len(existing_rows)} prior + {len(new_rows)} new)')

    # ---- Write run log ----
    try:
        import json as _json
        _log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'data-lake', '00_Logs', 'fantasy_baseball'
        )
        os.makedirs(_log_dir, exist_ok=True)
        _entry = {
            'ts'             : datetime.now().isoformat(timespec='seconds'),
            'workflow'       : 'fantasy-collect-closer-depth-mlb',
            'status'         : 'ok',
            'csv_path'       : output_file,
            'csv_total_rows' : total,
            'rows_written'   : len(new_rows),
            'closers_today'  : closers_today,
            'latest_scrape'  : today_str,
        }
        _log_path = os.path.join(_log_dir, 'fantasy-collect-closer-depth-mlb.jsonl')
        with open(_log_path, 'a', encoding='utf-8') as _f:
            _f.write(_json.dumps(_entry) + '\n')
    except Exception as _e:
        print(f'[WARN] run-log write failed: {_e}')


if __name__ == '__main__':
    main()
