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

# Role inference tuning — season-wide rate metrics + rolling lookback window
LOOKBACK_DAYS        = 14    # days of boxscore history for recent window
MIN_SV_CO_CLOSER     = 3     # recent saves needed to flag a co-closer emerging
MIN_SV_HLD_RATIO     = 0.51  # sv_hld_ratio threshold for Closer classification
MIN_HLD_RATE_SETUP   = 0.15  # hld_rate threshold for Setup Man classification
MIN_SV_RATE_COMMIT   = 0.08  # sv_rate threshold for Closer Committee membership
AVG_OUTS_LONG_REL    = 4.5   # avg_outs threshold for Long Reliever
MAX_SETUP_MEN        = 2     # max setup men labeled per team

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
    'recent_sv_rate',     # sv_rate over the lookback window
    'recent_hld_rate',    # hld_rate over the lookback window
    'recent_sv_hld_ratio',# sv_hld_ratio over the lookback window
    'recent_avg_outs',    # avg outs per appearance over the lookback window
    'sv_rate',            # sv_rate (full season: season_sv / season_games)
    'hld_rate',           # hld_rate (full season: season_hld / season_games)
    'sv_hld_ratio',       # sv_rate / (sv_rate + hld_rate), or 0.0 if both zero
    'avg_outs',           # avg outs per relief appearance (full season)
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
            'recent_sv_rate':    '',          # populated by infer_roles()
            'recent_hld_rate':   '',          # populated by infer_roles()
            'recent_sv_hld_ratio': '',        # populated by infer_roles()
            'recent_avg_outs':   '',          # populated by infer_roles()
            'sv_rate':           '',          # populated by infer_roles()
            'hld_rate':          '',          # populated by infer_roles()
            'sv_hld_ratio':      '',          # populated by infer_roles()
            'avg_outs':          '',          # populated by infer_roles()
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
    Aggregate per-pitcher stats from the boxscore CSV in a single pass,
    collecting both a rolling lookback window and full-season totals.

    Filters to: b_or_p == 'pitcher', did_play == '1', GS == '0' (relief only).

    Returns a dict mapping player_id (str) -> {
        'recent_sv':           int,   saves in lookback window
        'recent_hld':          int,   holds in lookback window
        'recent_games':        int,   appearances in lookback window
        'recent_sv_rate':      float, recent_sv / recent_games
        'recent_hld_rate':     float, recent_hld / recent_games
        'recent_sv_hld_ratio': float, rolling sv_rate / (sv_rate + hld_rate)
        'recent_avg_outs':     float, recent_outs / recent_games
        'season_sv':           int,   full-season saves
        'season_hld':          int,   full-season holds
        'season_games':        int,   full-season appearances
        'season_outs':         int,   full-season outs recorded
        'sv_rate':             float, season_sv / season_games
        'hld_rate':            float, season_hld / season_games
        'sv_hld_ratio':        float, sv_rate / (sv_rate + hld_rate), or 0.0
        'avg_outs':            float, season_outs / season_games
    }
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
            if int(row.get('did_play', 0) or 0) == 0:
                continue
            if int(row.get('GS', 0) or 0) > 0:
                continue

            pid = str(row['player_id'])
            if pid not in stats:
                stats[pid] = {
                    'recent_sv': 0, 'recent_hld': 0, 'recent_games': 0,
                    'recent_outs': 0,
                    'season_sv': 0, 'season_hld': 0, 'season_games': 0,
                    'season_outs': 0,
                }

            sv   = int(row.get('SV',   0) or 0)
            hld  = int(row.get('HLD',  0) or 0)
            outs = int(row.get('OUTS', 0) or 0)

            # Full-season accumulation (all rows)
            stats[pid]['season_sv']    += sv
            stats[pid]['season_hld']   += hld
            stats[pid]['season_games'] += 1
            stats[pid]['season_outs']  += outs

            # Recent-window accumulation (lookback only)
            if row.get('date', '') >= cutoff:
                stats[pid]['recent_sv']    += sv
                stats[pid]['recent_hld']   += hld
                stats[pid]['recent_games'] += 1
                stats[pid]['recent_outs']  += outs

    # Compute derived rate metrics from both season and rolling window
    for s in stats.values():
        # Season rates
        g = s['season_games']
        sv_rate  = s['season_sv']  / g if g else 0.0
        hld_rate = s['season_hld'] / g if g else 0.0
        denom    = sv_rate + hld_rate
        s['sv_rate']      = sv_rate
        s['hld_rate']     = hld_rate
        s['sv_hld_ratio'] = sv_rate / denom if denom else 0.0
        s['avg_outs']     = s['season_outs'] / g if g else 0.0

        # Rolling window rates
        rg = s['recent_games']
        r_sv_rate  = s['recent_sv']  / rg if rg else 0.0
        r_hld_rate = s['recent_hld'] / rg if rg else 0.0
        r_denom    = r_sv_rate + r_hld_rate
        s['recent_sv_rate']      = r_sv_rate
        s['recent_hld_rate']     = r_hld_rate
        s['recent_sv_hld_ratio'] = r_sv_rate / r_denom if r_denom else 0.0
        s['recent_avg_outs']     = s['recent_outs'] / rg if rg else 0.0

    return stats


def infer_roles(players: list, recent_stats: dict,
                min_sv_co_closer: int  = MIN_SV_CO_CLOSER,
                min_sv_hld_ratio: float = MIN_SV_HLD_RATIO,
                min_hld_rate: float    = MIN_HLD_RATE_SETUP,
                min_sv_rate: float     = MIN_SV_RATE_COMMIT,
                avg_outs_long: float   = AVG_OUTS_LONG_REL,
                max_setup_men: int     = MAX_SETUP_MEN) -> list:
    """
    Augment each player row with inferred_role and rate-based metrics.

    Decision tree per team (in order):
      Step 0 — Long Reliever (avg_outs > avg_outs_long)
      Step 1 — API-designated closers (position_code == 'C')
      Step 2 — No API closer: data-driven via sv_hld_ratio / sv_rate
      Step 3 — Setup Man (hld_rate >= min_hld_rate, up to max_setup_men)
      Step 4 — Default remaining relievers to 'Pitcher'
    """
    from collections import defaultdict

    # Attach all stats to every row
    for p in players:
        pid = str(p['player_id'])
        s = recent_stats.get(pid, {})
        p['recent_sv']           = str(s.get('recent_sv',           0))
        p['recent_hld']          = str(s.get('recent_hld',          0))
        p['recent_games']        = str(s.get('recent_games',        0))
        p['recent_sv_rate']      = str(round(s.get('recent_sv_rate',      0.0), 3))
        p['recent_hld_rate']     = str(round(s.get('recent_hld_rate',     0.0), 3))
        p['recent_sv_hld_ratio'] = str(round(s.get('recent_sv_hld_ratio', 0.0), 3))
        p['recent_avg_outs']     = str(round(s.get('recent_avg_outs',     0.0), 2))
        p['sv_rate']             = str(round(s.get('sv_rate',             0.0), 3))
        p['hld_rate']            = str(round(s.get('hld_rate',            0.0), 3))
        p['sv_hld_ratio']        = str(round(s.get('sv_hld_ratio',        0.0), 3))
        p['avg_outs']            = str(round(s.get('avg_outs',            0.0), 2))

    # Mark starters — skip them for all subsequent role inference
    for p in players:
        if p['role'] == 'Starting Pitcher':
            p['inferred_role'] = 'Starting Pitcher'

    # Group remaining pitchers (non-starters) by team
    team_groups: dict = defaultdict(list)
    for p in players:
        if p.get('inferred_role') == 'Starting Pitcher':
            continue
        team_groups[str(p['team_id'])].append(p)

    for team_id, relievers in team_groups.items():

        # ── Step 0: Long Reliever detection ─────────────────────────────────
        # Exclude pitchers with 3+ saves — multi-inning closers exist and a
        # true long reliever rarely accumulates meaningful save totals.
        for p in relievers:
            if float(p['avg_outs']) > avg_outs_long and int(p.get('sv', 0) or 0) < 3:
                p['inferred_role'] = 'Long Reliever'

        # Relievers still active for closer / setup classification
        active = [p for p in relievers if not p.get('inferred_role')]
        # Exclude 60-Day IL players — they can't pitch and shouldn't consume the Closer slot,
        # which would block the data-driven Step 2 from finding the active replacement.
        api_closers = [p for p in active if p['position_code'] == 'C'
                       and 'Injured 60-Day' not in p.get('status', '')]

        # ── Step 1: API-designated closers ──────────────────────────────────
        if api_closers:
            if len(api_closers) == 1:
                closer = api_closers[0]
                co_candidates = [
                    p for p in active
                    if p['player_id'] != closer['player_id']
                    and int(p['recent_sv']) >= min_sv_co_closer
                    and float(p['sv_hld_ratio']) >= 0.40
                ]
                if co_candidates:
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
            # ── Step 2: No API closer — data-driven via sv_hld_ratio ────────
            ratio_candidates = [
                p for p in active
                if float(p['sv_hld_ratio']) >= min_sv_hld_ratio
            ]
            if ratio_candidates:
                if len(ratio_candidates) == 1:
                    ratio_candidates[0]['inferred_role'] = 'Closer'
                elif len(ratio_candidates) == 2:
                    for c in ratio_candidates:
                        c['inferred_role'] = 'Co-Closer'
                else:
                    for c in ratio_candidates:
                        c['inferred_role'] = 'Closer Committee'

            else:
                # Fallback: someone getting saves but below ratio threshold
                commit_candidates = [
                    p for p in active
                    if float(p['sv_rate']) >= min_sv_rate
                    and float(p['sv_hld_ratio']) >= 0.25
                ]
                if commit_candidates:
                    sv_getters = [
                        p for p in active if float(p['sv_rate']) >= min_sv_rate
                    ]
                    if len(sv_getters) == 1:
                        sv_getters[0]['inferred_role'] = 'Closer'
                    else:
                        for p in sv_getters:
                            p['inferred_role'] = 'Closer Committee'
                # else: no clear save pattern — Setup Man logic handles the rest

        # ── Step 3: Setup Man detection ─────────────────────────────────────
        labeled = {p['player_id'] for p in relievers if p.get('inferred_role')}
        setup_candidates = sorted(
            [p for p in relievers
             if p['player_id'] not in labeled
             and float(p['hld_rate']) >= min_hld_rate],
            key=lambda p: float(p['hld_rate']), reverse=True
        )
        for p in setup_candidates[:max_setup_men]:
            p['inferred_role'] = 'Setup Man'

        # ── Step 4: Default remaining relievers ──────────────────────────────
        for p in relievers:
            if not p.get('inferred_role'):
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
            p['inferred_role']       = p['role']
            p['recent_sv']           = ''
            p['recent_hld']          = ''
            p['recent_games']        = ''
            p['recent_sv_rate']      = ''
            p['recent_hld_rate']     = ''
            p['recent_sv_hld_ratio'] = ''
            p['recent_avg_outs']     = ''
            p['sv_rate']             = ''
            p['hld_rate']            = ''
            p['sv_hld_ratio']        = ''
            p['avg_outs']            = ''

    # ---- Dry-run output ----
    if args.dry_run:
        key_roles = [p for p in all_players
                     if p.get('inferred_role') not in ('Pitcher', 'Starting Pitcher', '')]
        print(f'\n[DRY-RUN] Would write {len(all_players)} rows -> {output_file}')
        print(f'  Pitchers with inferred role ({len(key_roles)}):')
        print(f'  {"TEAM":<28} {"PLAYER":<26} {"INFERRED":<20} {"STATUS":<10} '
              f'{"RSV":>4} {"RHLD":>5} {"R_RATIO":>8} {"RATIO":>7} {"ΔRATIO":>7} '
              f'{"AVGOUTS":>8} {"SV":>3} {"ERA":>6}')
        print('  ' + '-' * 148)
        for p in sorted(key_roles, key=lambda x: (x['inferred_role'], x['team_name'])):
            season_ratio = float(p['sv_hld_ratio']  or 0)
            recent_ratio = float(p['recent_sv_hld_ratio'] or 0)
            delta        = recent_ratio - season_ratio
            delta_str    = f'{delta:+.3f}' if p['recent_games'] != '0' else '  n/a'
            print(f'  {p["team_name"]:<28} {p["player_name"]:<26} '
                  f'{p["inferred_role"]:<20} {p["status"]:<10} '
                  f'{p["recent_sv"]:>4} {p["recent_hld"]:>5} '
                  f'{recent_ratio:>8.3f} {season_ratio:>7.3f} {delta_str:>7} '
                  f'{p["avg_outs"]:>8} '
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
