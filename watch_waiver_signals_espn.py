"""
Description:
  Daily waiver wire watchlist generator. Scans all low-ownership players in the latest
  ESPN rankings snapshot, builds 7-day and 14-day pre-pickup feature vectors using the
  same logic as Idea 16, and scores each player against the signal thresholds derived
  from that analysis. Outputs a ranked watchlist so breakout targets can be spotted
  before ownership rises.

  Typical use: run after fantasy-collect-all-data so the boxscore, rankings, and lineup
  files are all fresh.

Source Data:
  - data-lake/01_Bronze/fantasy_baseball/{YEAR}_espn_rankings_daily.csv
  - data-lake/01_Bronze/fantasy_baseball/{YEAR}_mlb_stats_boxscore.csv
  - data-lake/01_Bronze/fantasy_baseball/{YEAR}_mlb_lineups_batters.csv
  - data-lake/01_Bronze/fantasy_baseball/player_map.csv (canonical identity; was player_lookup.csv)

Outputs:
  - fantasy_baseball/ideas/idea_16_waiver_signals/reports/waiver_watchlist_{DATE}.md

Usage:
  python watch_waiver_signals_espn.py [--year YYYY] [--date YYYY-MM-DD]
                                      [--max-owned FLOAT] [--top N] [--dry-run]
"""

import argparse
import csv
import os
import unicodedata
from collections import defaultdict
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.dirname(SCRIPT_DIR)
DATA_DIR   = os.path.join(REPO_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')

# Signal thresholds derived from Idea 16 (analyze_waiver_signals_espn_2026.py)
# Format: (feature_name, direction, threshold, r_value)
BATTER_SIGNALS = [
    ('pct_owned_at_pickup',  '>=', 22.760, 0.700),
    ('hr_per_game_7d',       '>=',  0.143, 0.480),
    ('hr_per_game_14d',      '>=',  0.167, 0.468),
    ('batting_slot_mode_7d', '<=',  7.000, 0.424),
    ('r_per_game_14d',       '>=',  0.250, 0.409),
    ('r_per_game_7d',        '>=',  0.167, 0.367),
    ('ownership_slope_14d',  '>=',  1.670, 0.333),
    ('ops_7d',               '>=',  0.293, 0.306),
]

PITCHER_SIGNALS = [
    ('pct_change_mean_7d',  '>=',  1.042, 0.500),
    ('pct_change_mean_14d', '>=',  1.042, 0.432),
    ('era_14d',             '<=',  2.250, 0.402),
    ('ownership_slope_14d', '>=',  0.533, 0.386),
    ('appearances_7d',      '>=',  1.000, 0.259),
    ('whip_14d',            '<=',  1.167, 0.234),
    ('svhd_per_app_14d',    '>=',  0.000, 0.226),
    ('appearances_14d',     '>=',  1.000, 0.201),
]

PITCHER_POSITIONS = {'SP', 'RP', 'P', 'SP,RP', 'RP,SP'}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_name(name):
    if not name:
        return ''
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_name = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ascii_name.lower().strip()


def parse_date(s):
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def safe_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def safe_int(v, default=0):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Stat calculators (same logic as idea 16)
# ---------------------------------------------------------------------------

def compute_ops(rows):
    ab = sum(safe_int(r.get('AB')) for r in rows)
    h  = sum(safe_int(r.get('H'))  for r in rows)
    bb = sum(safe_int(r.get('B_BB')) for r in rows)
    hbp = sum(safe_int(r.get('HBP')) for r in rows)
    sf = sum(safe_int(r.get('SF'))  for r in rows)
    tb = sum(safe_int(r.get('TB'))  for r in rows)
    obp_denom = ab + bb + hbp + sf
    slg_denom = ab
    if obp_denom == 0 or slg_denom == 0:
        return None
    return (h + bb + hbp) / obp_denom + tb / slg_denom


def compute_ab_per_game(rows):
    if not rows:
        return None
    return sum(safe_int(r.get('AB')) for r in rows) / len(rows)


def compute_k9(rows):
    outs = sum(safe_int(r.get('OUTS')) for r in rows)
    k    = sum(safe_int(r.get('K'))    for r in rows)
    if outs == 0:
        return None
    return k / (outs / 27)


def compute_era(rows):
    outs = sum(safe_int(r.get('OUTS')) for r in rows)
    er   = sum(safe_int(r.get('ER'))   for r in rows)
    if outs == 0:
        return None
    return er / (outs / 27)


def compute_whip(rows):
    outs = sum(safe_int(r.get('OUTS')) for r in rows)
    bb   = sum(safe_int(r.get('P_BB')) for r in rows)
    h    = sum(safe_int(r.get('P_H'))  for r in rows)
    if outs == 0:
        return None
    ip = outs / 3
    return (bb + h) / ip


def compute_svhd_per_app(rows):
    apps = sum(1 for r in rows if safe_int(r.get('OUTS')) > 0)
    if apps == 0:
        return None
    svhd = sum(safe_int(r.get('SVHD')) for r in rows)
    return svhd / apps


def ownership_slope(rank_rows):
    if len(rank_rows) < 2:
        return None
    n = len(rank_rows)
    xs = list(range(n))
    ys = [safe_float(r.get('pct_owned'), 0.0) for r in rank_rows]
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    num = sum((xs[i] - x_mean) * (ys[i] - y_mean) for i in range(n))
    den = sum((xs[i] - x_mean) ** 2 for i in range(n))
    return num / den if den else None


def batting_slot_mode(lineup_rows):
    slots = [safe_int(r.get('batting_order')) for r in lineup_rows
             if safe_int(r.get('batting_order')) > 0]
    if not slots:
        return None
    counts = defaultdict(int)
    for s in slots:
        counts[s] += 1
    return max(counts, key=lambda k: counts[k])


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def load_player_lookup(year):
    # Canonical single source of truth (was player_lookup.csv); mlb_name is the
    # accented MLB/archive name -> normalize_name(mlb_name) is the same join key.
    path = os.path.join(DATA_DIR, 'player_map.csv')
    lookup = {}
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            eid   = row.get('espn_player_id', '').strip()
            aname = (row.get('mlb_name') or '').strip()
            if eid and aname:
                lookup[eid] = normalize_name(aname)
    return lookup


def load_mlb_archive(year):
    """Load boxscore (daily-updated) into dict: normalize_name -> sorted rows."""
    path = os.path.join(DATA_DIR, f'{year}_mlb_stats_boxscore.csv')
    by_player = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name', ''))
            if key:
                by_player[key].append(row)
    for key in by_player:
        by_player[key].sort(key=lambda r: r['_date'])
    return by_player


def load_rankings(year):
    """Load rankings into dict: player_id -> sorted rows."""
    path = os.path.join(DATA_DIR, f'{year}_espn_rankings_daily.csv')
    by_player = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            pid = row.get('player_id', '').strip()
            if pid:
                by_player[pid].append(row)
    for pid in by_player:
        by_player[pid].sort(key=lambda r: r['_date'])
    return by_player


def load_lineups(year):
    """Load lineups into dict: normalize_name -> sorted rows."""
    path = os.path.join(DATA_DIR, f'{year}_mlb_lineups_batters.csv')
    by_player = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name', ''))
            if key:
                by_player[key].append(row)
    for key in by_player:
        by_player[key].sort(key=lambda r: r['_date'])
    return by_player


def get_available_players(rankings_by_player, ref_date):
    """
    Return one dict per player from the latest rankings snapshot <= ref_date.
    Excludes players currently rostered on a fantasy team or marked injured.
    """
    latest = {}
    for pid, rows in rankings_by_player.items():
        eligible = [r for r in rows if r['_date'] <= ref_date]
        if eligible:
            latest[pid] = eligible[-1]

    available = []
    for pid, row in latest.items():
        if row.get('on_team_id', '').strip() not in ('', '0'):
            continue
        if row.get('injured', '').strip().lower() == 'true':
            continue
        owned  = safe_float(row.get('pct_owned'), 0.0)
        pos    = row.get('player_position', '').strip().upper()
        b_or_p = 'pitcher' if pos in PITCHER_POSITIONS else 'batter'
        available.append({
            'player_id':   pid,
            'player_name': row.get('player_name', ''),
            'player_pos':  pos,
            'pct_owned':   owned,
            'pct_change':  safe_float(row.get('pct_change'), 0.0),
            'b_or_p':      b_or_p,
            '_rank_row':   row,
        })
    return available


# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def build_features(player, ref_date, player_lookup, mlb_archive, rankings_by_player, lineups):
    pid      = player['player_id']
    b_or_p   = player['b_or_p']
    archive_key = player_lookup.get(pid)

    def archive_window(days):
        if not archive_key:
            return []
        rows = mlb_archive.get(archive_key, [])
        lo = ref_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] < ref_date]

    def rank_window(days):
        rows = rankings_by_player.get(pid, [])
        lo = ref_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] <= ref_date]

    def lineup_window(days):
        if not archive_key:
            return []
        rows = lineups.get(archive_key, [])
        lo = ref_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] < ref_date]

    feats = {}

    for w in (7, 14):
        arch = archive_window(w)
        rank = rank_window(w)

        if b_or_p == 'batter':
            feats[f'ops_{w}d']           = compute_ops(arch)
            feats[f'ab_per_game_{w}d']   = compute_ab_per_game(arch)
            n = len(arch)
            if n > 0:
                feats[f'hr_per_game_{w}d']  = sum(safe_int(r.get('HR')) for r in arch) / n
                feats[f'sb_per_game_{w}d']  = sum(safe_int(r.get('SB')) for r in arch) / n
                feats[f'r_per_game_{w}d']   = sum(safe_int(r.get('R'))  for r in arch) / n
                feats[f'games_played_{w}d'] = n
            else:
                feats[f'hr_per_game_{w}d']  = None
                feats[f'sb_per_game_{w}d']  = None
                feats[f'r_per_game_{w}d']   = None
                feats[f'games_played_{w}d'] = None
        else:
            feats[f'k9_{w}d']           = compute_k9(arch)
            feats[f'era_{w}d']          = compute_era(arch)
            feats[f'whip_{w}d']         = compute_whip(arch)
            feats[f'svhd_per_app_{w}d'] = compute_svhd_per_app(arch)
            appearances = sum(1 for r in arch if safe_int(r.get('OUTS')) > 0)
            feats[f'appearances_{w}d']  = appearances if arch else None

        if rank:
            feats['pct_owned_at_pickup']    = safe_float(rank[-1].get('pct_owned'))
            feats[f'pct_change_mean_{w}d']  = (
                sum(safe_float(r.get('pct_change'), 0.0) for r in rank) / len(rank)
            )
            feats[f'ownership_slope_{w}d']  = ownership_slope(rank)

    if b_or_p == 'batter':
        lu7 = lineup_window(7)
        feats['batting_slot_mode_7d'] = batting_slot_mode(lu7)

    return feats


# ---------------------------------------------------------------------------
# Signal scoring
# ---------------------------------------------------------------------------

def score_signals(feats, signal_defs):
    """Return list of (name, value, threshold, direction, r) for each firing signal."""
    fired = []
    for name, direction, threshold, r_val in signal_defs:
        val = feats.get(name)
        if val is None:
            continue
        if direction == '>=' and val >= threshold:
            fired.append((name, val, threshold, direction, r_val))
        elif direction == '<=' and val <= threshold:
            fired.append((name, val, threshold, direction, r_val))
    return fired


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------

CSV_FEATURE_COLS = [
    'pct_owned_at_pickup',
    'pct_change_mean_7d', 'pct_change_mean_14d',
    'ownership_slope_7d', 'ownership_slope_14d',
    'ops_7d', 'ops_14d',
    'ab_per_game_7d', 'ab_per_game_14d',
    'hr_per_game_7d', 'hr_per_game_14d',
    'sb_per_game_7d', 'sb_per_game_14d',
    'r_per_game_7d', 'r_per_game_14d',
    'games_played_7d', 'games_played_14d',
    'batting_slot_mode_7d',
    'k9_7d', 'k9_14d',
    'era_7d', 'era_14d',
    'whip_7d', 'whip_14d',
    'appearances_7d', 'appearances_14d',
    'svhd_per_app_7d', 'svhd_per_app_14d',
]

CSV_COLS = [
    'date', 'player_id', 'player_name', 'player_pos', 'b_or_p',
    'pct_owned', 'pct_change', 'signals_fired', 'signals_total', 'firing_signals',
] + CSV_FEATURE_COLS


def fmt_val(v):
    if v is None:
        return ''
    if isinstance(v, float):
        return f'{v:.4f}'
    return str(v)


def build_rows(available, ref_date):
    rows = []
    for p in available:
        feats  = p['_features']
        b_or_p = p['b_or_p']
        signals = BATTER_SIGNALS if b_or_p == 'batter' else PITCHER_SIGNALS
        fired   = score_signals(feats, signals)
        if not fired:
            continue
        firing_names = '|'.join(name for name, *_ in fired)
        row = {
            'date':           str(ref_date),
            'player_id':      p['player_id'],
            'player_name':    p['player_name'],
            'player_pos':     p['player_pos'],
            'b_or_p':         b_or_p,
            'pct_owned':      fmt_val(p['pct_owned']),
            'pct_change':     fmt_val(p['pct_change']),
            'signals_fired':  len(fired),
            'signals_total':  len(signals),
            'firing_signals': firing_names,
        }
        for col in CSV_FEATURE_COLS:
            row[col] = fmt_val(feats.get(col))
        rows.append(row)

    rows.sort(key=lambda r: (-r['signals_fired'], -float(r['pct_owned'] or 0)))
    return rows


def write_csv(rows, year, dry_run=False):
    out_path = os.path.join(DATA_DIR, f'{year}_espn_waiver_watchlist.csv')
    existing_keys = set()
    file_exists = os.path.exists(out_path)

    if file_exists:
        with open(out_path, encoding='utf-8', errors='replace') as f:
            for r in csv.DictReader(f):
                existing_keys.add((r.get('date', ''), r.get('player_id', '')))

    new_rows = [r for r in rows if (str(r['date']), str(r['player_id'])) not in existing_keys]

    if dry_run:
        print(f'\n[DRY-RUN] Would append {len(new_rows)} new rows to {out_path}')
        print(f'  ({len(rows) - len(new_rows)} already present, skipped)')
        for r in new_rows[:5]:
            print(f"  {r['player_name']} ({r['b_or_p']}) — {r['signals_fired']}/{r['signals_total']} signals")
        return 0

    write_header = not file_exists
    with open(out_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLS)
        if write_header:
            writer.writeheader()
        writer.writerows(new_rows)

    print(f'  {len(new_rows)} new rows written to {out_path}')
    print(f'  ({len(rows) - len(new_rows)} already present, skipped)')
    return len(new_rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Daily waiver wire watchlist generator')
    parser.add_argument('--year',      type=int,   default=date.today().year)
    parser.add_argument('--date',      type=str,   default=None,
                        help='Reference date YYYY-MM-DD (default: today)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Score players but do not write to disk')
    args = parser.parse_args()

    ref_date = parse_date(args.date) if args.date else date.today()

    print(f'Waiver Wire Watchlist — {ref_date}')
    print(f'  Year: {args.year}  |  free agents only, no injured')

    print('\nLoading data...')
    player_lookup = load_player_lookup(args.year)
    mlb_archive   = load_mlb_archive(args.year)
    rankings      = load_rankings(args.year)
    lineups       = load_lineups(args.year)

    print(f'  {len(player_lookup):,} entries in player_lookup')
    print(f'  {len(mlb_archive):,} players in MLB boxscore archive')
    print(f'  {len(rankings):,} players in rankings')
    print(f'  {len(lineups):,} players in lineups')

    available = get_available_players(rankings, ref_date)
    batters   = [p for p in available if p['b_or_p'] == 'batter']
    pitchers  = [p for p in available if p['b_or_p'] == 'pitcher']
    print(f'\n  Free agents (healthy): {len(batters)} batters, {len(pitchers)} pitchers')

    print('\nBuilding features...')
    for p in available:
        p['_features'] = build_features(
            p, ref_date, player_lookup, mlb_archive, rankings, lineups
        )

    cov_b = sum(
        1 for p in batters
        if p['_features'].get('ops_7d') is not None or p['_features'].get('ops_14d') is not None
    ) / max(len(batters), 1)
    cov_p = sum(
        1 for p in pitchers
        if p['_features'].get('k9_7d') is not None or p['_features'].get('era_7d') is not None
    ) / max(len(pitchers), 1)
    print(f'  Archive coverage: batters {cov_b:.0%}, pitchers {cov_p:.0%}')

    print('\nScoring signals...')
    rows   = build_rows(available, ref_date)
    b_rows = [r for r in rows if r['b_or_p'] == 'batter']
    p_rows = [r for r in rows if r['b_or_p'] == 'pitcher']
    print(f'  {len(b_rows)} batters, {len(p_rows)} pitchers with >= 1 signal firing')

    write_csv(rows, args.year, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
