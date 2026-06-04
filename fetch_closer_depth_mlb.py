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
from datetime import date, datetime, timedelta

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

# Role inference tuning — applied over the rolling lookback window
LOOKBACK_DAYS    = 14   # days of boxscore history to consider
MIN_SV_CO_CLOSER = 2    # saves needed for a non-designated closer to qualify as co-closer
MIN_HLD_SETUP    = 2    # holds needed in the window to be labeled Setup Man
MAX_SETUP_MEN    = 2    # maximum setup men labeled per team

OUTPUT_FIELDS = [
    'date_scraped',
    'team_id', 'team_name',
    'player_id', 'player_name',
    'throws',             # R / L / S  (from pitchHand.code)
    'position_code',      # C = Closer | 1 = Pitcher | S = Starting Pitcher
    'role',               # official MLB roster designation
    'inferred_role',      # role inferred from recent game data (see LOOKBACK_DAYS)
    'status',             # Active | Injured 15-Day | Injured 60-Day | etc.
    'recent_sv',          # saves in the lookback window
    'recent_hld',         # holds in the lookback window
    'recent_games',       # appearances in the lookback window
    'games',              # season appearances (full season)
    'innings_pitched',
    'era',
    'sv',                 # season saves
    'hld',                # season holds
    'sd',                 # season saves + holds (mirrors FanGraphs sd column)
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
            'inferred_role':     '',          # populated by infer_roles()
            'status':            status_desc,
            'recent_sv':         '',          # populated by infer_roles()
            'recent_hld':        '',          # populated by infer_roles()
            'recent_games':      '',          # populated by infer_roles()
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
# Role inference from recent boxscore data
# ---------------------------------------------------------------------------

def load_recent_boxscore_stats(boxscore_file: str, lookback_days: int) -> dict:
    """
    Aggregate saves and holds per pitcher from the last `lookback_days` days.

    Returns a dict mapping player_id (str) ->
        {'sv': int, 'hld': int, 'games': int}
    Returns an empty dict if the boxscore file does not exist.
    """
    if not os.path.exists(boxscore_file):
        return {}

    cutoff = (date.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    stats: dict[str, dict] = {}

    with open(boxscore_file, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row.get('b_or_p') != 'pitcher':
                continue
            if row.get('date', '') < cutoff:
                continue
            if int(row.get('did_play', 0) or 0) == 0:
                continue
            # Exclude games where the pitcher started — we only want relief appearances
            if int(row.get('GS', 0) or 0) > 0:
                continue

            pid = str(row['player_id'])
            if pid not in stats:
                stats[pid] = {'sv': 0, 'hld': 0, 'games': 0}
            stats[pid]['sv']    += int(row.get('SV',  0) or 0)
            stats[pid]['hld']   += int(row.get('HLD', 0) or 0)
            stats[pid]['games'] += 1

    return stats


def infer_roles(players: list, recent_stats: dict,
                min_sv_co_closer: int = MIN_SV_CO_CLOSER,
                min_hld_setup: int    = MIN_HLD_SETUP,
                max_setup_men: int    = MAX_SETUP_MEN) -> list:
    """
    Augment each player row with inferred_role, recent_sv, recent_hld,
    recent_games based on actual save/hold data from recent games.

    Role assignment logic (per team, applied in order):

    1. Closers (API + game-data)
       - 1 API Closer + no other reliever with >= min_sv_co_closer SVs
           → "Closer"
       - 1 API Closer + another reliever with >= min_sv_co_closer SVs
           → both = "Co-Closer"
       - 2 API Closers (committee designated by MLB)
           → both = "Co-Closer"
       - 3+ API Closers
           → all = "Closer Committee"
       - No API Closer, 1 pitcher with SVs
           → that pitcher = "Closer"
       - No API Closer, 2 pitchers with SVs, one has 3× more
           → dominant = "Closer"
       - No API Closer, 2 pitchers with comparable SVs
           → both = "Co-Closer"
       - No API Closer, 3+ pitchers with SVs
           → all = "Closer Committee"

    2. Setup Men
       - After closers are labeled, top `max_setup_men` relievers
         with >= min_hld_setup holds in the window → "Setup Man"

    3. All other relievers → "Pitcher"
    4. Starters → "Starting Pitcher" (unchanged)
    """
    from collections import defaultdict

    # Attach recent window stats to every row
    for p in players:
        pid = str(p['player_id'])
        s = recent_stats.get(pid, {})
        p['recent_sv']    = str(s.get('sv',    0))
        p['recent_hld']   = str(s.get('hld',   0))
        p['recent_games'] = str(s.get('games', 0))

    # Separate starters (skip them for role inference)
    for p in players:
        if p['role'] == 'Starting Pitcher':
            p['inferred_role'] = 'Starting Pitcher'

    # Group relievers by team
    team_groups: dict = defaultdict(list)
    for p in players:
        if p.get('inferred_role') == 'Starting Pitcher':
            continue
        team_groups[str(p['team_id'])].append(p)

    for team_id, relievers in team_groups.items():
        api_closers = [p for p in relievers if p['position_code'] == 'C']

        # ── Step 1: label closers ────────────────────────────────────────────
        if api_closers:
            if len(api_closers) == 1:
                closer = api_closers[0]
                co_candidates = [
                    p for p in relievers
                    if p['player_id'] != closer['player_id']
                    and int(p['recent_sv']) >= min_sv_co_closer
                ]
                if co_candidates:
                    # Another reliever is sharing closing duties
                    closer['inferred_role'] = 'Co-Closer'
                    for c in co_candidates:
                        c['inferred_role'] = 'Co-Closer'
                else:
                    closer['inferred_role'] = 'Closer'

            elif len(api_closers) == 2:
                for c in api_closers:
                    c['inferred_role'] = 'Co-Closer'

            else:  # 3+ API closers
                for c in api_closers:
                    c['inferred_role'] = 'Closer Committee'

        else:
            # No API-designated closer — infer from saves in the window
            pitchers_with_sv = sorted(
                [p for p in relievers if int(p['recent_sv']) >= 1],
                key=lambda p: int(p['recent_sv']), reverse=True
            )
            if len(pitchers_with_sv) == 0:
                pass  # no save data — cannot infer
            elif len(pitchers_with_sv) == 1:
                pitchers_with_sv[0]['inferred_role'] = 'Closer'
            elif len(pitchers_with_sv) == 2:
                sv0 = int(pitchers_with_sv[0]['recent_sv'])
                sv1 = int(pitchers_with_sv[1]['recent_sv'])
                if sv1 == 0 or sv0 >= 3 * sv1:
                    # One pitcher clearly dominant
                    pitchers_with_sv[0]['inferred_role'] = 'Closer'
                else:
                    pitchers_with_sv[0]['inferred_role'] = 'Co-Closer'
                    pitchers_with_sv[1]['inferred_role'] = 'Co-Closer'
            else:
                # 3+ pitchers sharing saves → committee
                for p in pitchers_with_sv:
                    p['inferred_role'] = 'Closer Committee'

        # ── Step 2: label top setup men ─────────────────────────────────────
        labeled = {p['player_id'] for p in relievers if p.get('inferred_role')}
        setup_candidates = sorted(
            [p for p in relievers
             if p['player_id'] not in labeled
             and int(p['recent_hld']) >= min_hld_setup],
            key=lambda p: int(p['recent_hld']), reverse=True
        )
        for p in setup_candidates[:max_setup_men]:
            p['inferred_role'] = 'Setup Man'

        # ── Step 3: default remaining relievers ──────────────────────────────
        for p in relievers:
            if 'inferred_role' not in p:
                p['inferred_role'] = 'Pitcher'

    return players


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
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch and overwrite today\'s rows even if already current')
    parser.add_argument('--lookback-days', type=int, default=LOOKBACK_DAYS,
                        help=f'Days of boxscore history for role inference (default: {LOOKBACK_DAYS})')
    args = parser.parse_args()

    season    = args.year
    today_str = date.today().strftime('%Y-%m-%d')
    output_file = os.path.join(mp.DATA_PATH, f'closer_depth_mlb_{season}.csv')

    print(f'=== MLB Closer Depth Chart — {today_str} (season {season}) ===')

    # ---- Check if already current ----
    if not args.dry_run and os.path.exists(output_file):
        existing_rows, existing_keys = load_existing(output_file)
        already = sum(1 for k in existing_keys if k[0] == today_str)
        if already > 0 and not args.force:
            print(f'  Already current — {already} rows already recorded for {today_str}.')
            return
        if args.force and already > 0:
            # Strip today's rows so they are re-fetched with enriched columns
            existing_rows = [r for r in existing_rows if r['date_scraped'] != today_str]
            existing_keys = {(r['date_scraped'], r['player_id']) for r in existing_rows}
            print(f'  --force: removed {already} existing rows for {today_str}, re-fetching.')
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

    # ---- Role inference from recent boxscore data ----
    boxscore_file = os.path.join(mp.DATA_PATH, f'stats_mlb_boxscore_{season}.csv')
    recent_stats  = load_recent_boxscore_stats(boxscore_file, args.lookback_days)
    if recent_stats:
        all_players = infer_roles(all_players, recent_stats)
        n_labeled = sum(
            1 for p in all_players
            if p.get('inferred_role') not in ('', 'Pitcher', 'Starting Pitcher')
        )
        print(f'  Role inference: {n_labeled} pitchers labeled beyond "Pitcher" '
              f'(lookback={args.lookback_days}d, '
              f'n={len(recent_stats)} pitchers in window)')
    else:
        print(f'  Role inference: skipped (boxscore file not found)')
        for p in all_players:
            p['inferred_role'] = p['role']
            p['recent_sv']     = ''
            p['recent_hld']    = ''
            p['recent_games']  = ''

    # ---- Dry-run output ----
    if args.dry_run:
        key_roles = [p for p in all_players
                     if p.get('inferred_role') not in ('Pitcher', 'Starting Pitcher', '')]
        print(f'\n[DRY-RUN] Would write {len(all_players)} rows -> {output_file}')
        print(f'  Pitchers with inferred role ({len(key_roles)}):')
        print(f'  {"TEAM":<28} {"PLAYER":<26} {"INFERRED":<20} {"STATUS":<22} '
              f'{"RSV":>4} {"RHLD":>5} {"SV":>3} {"ERA":>6}')
        print('  ' + '-' * 120)
        for p in sorted(key_roles, key=lambda x: (x['inferred_role'], x['team_name'])):
            print(f'  {p["team_name"]:<28} {p["player_name"]:<26} '
                  f'{p["inferred_role"]:<20} {p["status"]:<22} '
                  f'{p["recent_sv"]:>4} {p["recent_hld"]:>5} '
                  f'{p["sv"]:>3} {p["era"]:>6}')
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
    closers_today   = sum(1 for r in new_rows if r['position_code'] == 'C')
    inferred_counts: dict = {}
    for r in new_rows:
        ir = r.get('inferred_role', 'Pitcher')
        inferred_counts[ir] = inferred_counts.get(ir, 0) + 1
    role_summary = ', '.join(
        f'{v} {k}' for k, v in sorted(inferred_counts.items())
        if k not in ('Pitcher', 'Starting Pitcher', '')
    )
    print(f'[OK]    fetch_closer_depth_mlb: {len(new_rows)} rows written | {today_str} '
          f'| {closers_today} API closers | inferred: {role_summary or "none"}')
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
