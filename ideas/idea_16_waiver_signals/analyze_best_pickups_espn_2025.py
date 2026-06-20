"""
Description:
    Ranks the best non-draft player acquisitions of the 2025 ESPN fantasy baseball season
    by post-add categorical contribution. Because no activity log exists for 2025, pickups
    are inferred from first-appearance detection: any (player, team) pair whose first
    scoring period > 1 is treated as a waiver/FA add with acquisition_date derived from
    2025_espn_schedule_matchup.csv. Multiple stints (player dropped and re-added to the
    same team) are detected by gaps in scoring periods and treated as separate windows.
    Stat aggregation, z-score logic, and output format are identical to the 2026 version.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/2025_espn_stats_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2025_espn_schedule_matchup.csv
    - data-lake/01_Bronze/fantasy_baseball/2025_espn_teams_season.csv

Outputs:
    - stdout — top 15 batters, top 15 pitchers, per-team leaderboard
    - data-lake/01_Bronze/fantasy_baseball/2025_espn_best_pickups.csv
"""

import csv
import io
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import mlb_processing as mp

STATS_FILE    = os.path.join(mp.DATA_PATH, '2025_espn_stats_daily.csv')
SCHEDULE_FILE = os.path.join(mp.DATA_PATH, '2025_espn_schedule_matchup.csv')
TEAMS_FILE    = os.path.join(mp.DATA_PATH, '2025_espn_teams_season.csv')
OUTPUT_FILE   = os.path.join(mp.DATA_PATH, '2025_espn_best_pickups.csv')

# ---------------------------------------------------------------------------
# Helpers (identical to 2026 version)
# ---------------------------------------------------------------------------

def safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default
    except (ValueError, TypeError):
        return default


def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def fmt_date(d):
    return d.strftime('%m/%d') if d else '?'


def compute_z_scores(values):
    n = len(values)
    if n < 2:
        return [0.0] * n
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = variance ** 0.5
    if std == 0:
        return [0.0] * n
    return [(v - mean) / std for v in values]


def fmt_row(cols, widths):
    return '  '.join(str(v)[:w].ljust(w) for v, w in zip(cols, widths))


def print_table(header, rows, widths):
    print(fmt_row(header, widths))
    print('  '.join('-' * w for w in widths))
    for row in rows:
        print(fmt_row(row, widths))
    print()


def _is_il(slot):
    s = str(slot).strip()
    return s == 'IL' or s.startswith('IL')


# ---------------------------------------------------------------------------
# Step 1 — Build lookup tables
# ---------------------------------------------------------------------------

def load_schedule():
    """Returns dict: scoring_period (int) -> date str (YYYY-MM-DD)."""
    sp_to_date = {}
    with open(SCHEDULE_FILE, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                sp = int(row['scoring_period'])
                sp_to_date[sp] = row['date'].strip()
            except (ValueError, KeyError):
                pass
    print(f"Loaded {len(sp_to_date)} scoring-period → date mappings.")
    return sp_to_date


def load_teams():
    """Returns dict: team_id (str) -> team_name (str)."""
    teams = {}
    with open(TEAMS_FILE, encoding='utf-8') as f:
        for row in csv.DictReader(f):
            tid = row.get('team_id', '').strip()
            name = row.get('team_name', '').strip()
            if tid and name:
                teams[tid] = name
    print(f"Loaded {len(teams)} team name mappings.")
    return teams


# ---------------------------------------------------------------------------
# Step 2 — Load and normalise 2025 stats
# ---------------------------------------------------------------------------

def load_stats(sp_to_date, team_names):
    """
    Reads 2025_espn_stats_daily.csv, normalises column names to match 2026 format,
    and resolves scoring_period → date. Returns dict: player_id -> [normalised rows].
    """
    stats = defaultdict(list)
    with open(STATS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            pid = row.get('playerId', '').strip()
            tid = row.get('teamId', '').strip()
            sp  = row.get('scoring_period', '').strip()
            if not pid or not tid or not sp:
                continue
            try:
                sp_int = int(sp)
            except ValueError:
                continue

            date_str = sp_to_date.get(sp_int, '')
            # Normalise to 2026-compatible column names
            norm = {
                'player_id':      pid,
                'player_name':    row.get('playerName', '').strip(),
                'team_id':        tid,
                'team_name':      team_names.get(tid, tid),
                'lineup_slot':    row.get('lineupSlot', '').strip(),
                'player_type':    row.get('b_or_p', '').strip(),
                'date':           date_str,
                'scoring_period': sp_int,
                # Batting stats
                'AB':   row.get('AB',  ''),
                'R':    row.get('R',   ''),
                'HR':   row.get('HR',  ''),
                'RBI':  row.get('RBI', ''),
                'SB':   row.get('SB',  ''),
                'OPS':  row.get('OPS', ''),
                # Pitching stats
                'OUTS': row.get('OUTS', ''),
                'QS':   row.get('QS',   ''),
                'SVHD': row.get('SVHD', ''),
                'K':    row.get('K',    ''),
                'ER':   row.get('ER',   ''),
                'P_H':  row.get('P_H',  ''),
                'P_BB': row.get('P_BB', ''),
                'K/9':  row.get('K/9',  ''),
                'ERA':  row.get('ERA',  ''),
                'WHIP': row.get('WHIP', ''),
            }
            stats[pid].append(norm)

    # Sort each player's rows by scoring_period
    for pid in stats:
        stats[pid].sort(key=lambda r: r['scoring_period'])

    print(f"Loaded stats for {len(stats)} unique player IDs.")
    return stats


# ---------------------------------------------------------------------------
# Step 3 — Infer pickups from first-appearance detection
# ---------------------------------------------------------------------------

def detect_stints(sp_list):
    """
    Given a sorted list of scoring periods, split into consecutive runs.
    A gap of > 7 scoring periods (roughly one week) signals a drop-and-re-add.
    Returns list of (first_sp, last_sp) tuples, one per stint.
    """
    if not sp_list:
        return []
    stints = []
    run_start = sp_list[0]
    prev = sp_list[0]
    for sp in sp_list[1:]:
        if sp - prev > 7:
            stints.append((run_start, prev))
            run_start = sp
        prev = sp
    stints.append((run_start, prev))
    return stints


def infer_pickups(stats, sp_to_date):
    """
    For each (player_id, team_id) combination, group the scoring periods they appeared
    together, split into stints (gaps > 7 SP = new stint), then treat any stint that
    starts at SP > 1 as a waiver/FA pickup.
    Returns list of pickup dicts with acquisition_date and end_date.
    """
    # Group: (player_id, team_id) -> sorted list of scoring periods
    pt_sps = defaultdict(list)
    for pid, rows in stats.items():
        for r in rows:
            pt_sps[(pid, r['team_id'])].append(r['scoring_period'])

    for key in pt_sps:
        pt_sps[key] = sorted(set(pt_sps[key]))

    pickups = []
    for (pid, tid), sp_list in pt_sps.items():
        stints = detect_stints(sp_list)
        # Find player name and team name from stats rows
        sample_rows = [r for r in stats[pid] if r['team_id'] == tid]
        pname = sample_rows[0]['player_name'] if sample_rows else ''
        tname = sample_rows[0]['team_name']   if sample_rows else tid

        for i, (start_sp, end_sp) in enumerate(stints):
            if start_sp <= 1:
                continue  # drafted player, skip
            acq_date = sp_to_date.get(start_sp, '')
            # End date: day of last scoring period in this stint
            # (the aggregate_pickup logic uses date >= acq_date and team match,
            #  so we cap it by tagging end_date as the date of end_sp)
            end_date = sp_to_date.get(end_sp, '') if end_sp != sp_list[-1] else None
            pickups.append({
                'player_id':        pid,
                'player_name':      pname,
                'team_name':        tname,
                'team_id':          tid,
                'acquisition_date': acq_date,
                'end_date':         end_date,
            })

    print(f"Inferred {len(pickups)} non-draft pickup stints "
          f"(from {sum(1 for p in pickups if not p['end_date'])} final / "
          f"{sum(1 for p in pickups if p['end_date'])} capped stints).")
    return pickups


# ---------------------------------------------------------------------------
# Step 4 — Aggregate per-stint stats (same logic as 2026)
# ---------------------------------------------------------------------------

def _player_type(post_rows):
    counts = defaultdict(int)
    for row in post_rows:
        pt = row.get('player_type', '').strip().lower()
        if pt in ('batter', 'pitcher'):
            counts[pt] += 1
    return max(counts, key=counts.get) if counts else None


def _agg_batter(result, active_rows, benched_rows):
    R = HR = RBI = SB = 0.0
    total_ab = weighted_ops = 0.0
    games_active = 0
    for row in active_rows:
        ab = safe_float(row.get('AB'))
        if ab > 0:
            games_active += 1
            R   += safe_float(row.get('R'))
            HR  += safe_float(row.get('HR'))
            RBI += safe_float(row.get('RBI'))
            SB  += safe_float(row.get('SB'))
            ops  = safe_float(row.get('OPS'))
            total_ab     += ab
            weighted_ops += ab * ops
    games_benched = sum(1 for r in benched_rows if safe_float(r.get('AB')) > 0)
    total_games   = games_active + games_benched
    result.update({
        'R': int(R), 'HR': int(HR), 'RBI': int(RBI), 'SB': int(SB),
        'OPS': round(weighted_ops / total_ab, 3) if total_ab > 0 else 0.0,
        'QS': '', 'SVHD': '', 'K/9': '', 'ERA': '', 'WHIP': '',
        'games_active': games_active, 'games_benched': games_benched,
        'utilization_rate': round(games_active / total_games, 3) if total_games > 0 else 0.0,
        '_total_ab': total_ab, '_weighted_ops': weighted_ops,
        '_ER': 0.0, '_P_H': 0.0, '_P_BB': 0.0, '_K': 0.0, '_OUTS': 0.0,
    })


def _agg_pitcher(result, active_rows, benched_rows):
    QS = SVHD = K = ER = P_H = P_BB = OUTS = 0.0
    games_active = 0
    for row in active_rows:
        outs = safe_float(row.get('OUTS'))
        if outs > 0:
            games_active += 1
            QS   += safe_float(row.get('QS'))
            SVHD += safe_float(row.get('SVHD'))
            K    += safe_float(row.get('K'))
            ER   += safe_float(row.get('ER'))
            P_H  += safe_float(row.get('P_H'))
            P_BB += safe_float(row.get('P_BB'))
            OUTS += outs
    games_benched = sum(1 for r in benched_rows if safe_float(r.get('OUTS')) > 0)
    total_games   = games_active + games_benched
    result.update({
        'QS': int(QS), 'SVHD': int(SVHD),
        'K/9':  round((K * 27) / OUTS, 2)         if OUTS > 0 else 0.0,
        'ERA':  round((ER * 27) / OUTS, 3)         if OUTS > 0 else 0.0,
        'WHIP': round((P_H + P_BB) / (OUTS / 3), 3) if OUTS > 0 else 0.0,
        'R': '', 'HR': '', 'RBI': '', 'SB': '', 'OPS': '',
        'games_active': games_active, 'games_benched': games_benched,
        'utilization_rate': round(games_active / total_games, 3) if total_games > 0 else 0.0,
        '_ER': ER, '_P_H': P_H, '_P_BB': P_BB, '_K': K, '_OUTS': OUTS,
        '_total_ab': 0.0, '_weighted_ops': 0.0,
    })


def aggregate_pickup(pickup, player_rows):
    acq_date = parse_date(pickup['acquisition_date'])
    end_date = parse_date(pickup['end_date']) if pickup.get('end_date') else None
    if acq_date is None:
        return None

    team_name = pickup['team_name']
    post_rows = [
        r for r in player_rows
        if (rd := parse_date(r.get('date', ''))) is not None
        and rd >= acq_date
        and (end_date is None or rd <= end_date)
        and r.get('team_name', '').strip() == team_name
    ]
    if not post_rows:
        return None

    player_type = _player_type(post_rows)
    if player_type is None:
        return None

    active_rows, benched_rows = [], []
    for row in post_rows:
        slot = row.get('lineup_slot', '')
        if _is_il(slot):
            continue
        elif slot.strip() == 'BE':
            benched_rows.append(row)
        else:
            active_rows.append(row)

    valid_dates = [parse_date(r.get('date', '')) for r in post_rows if parse_date(r.get('date', ''))]
    last_date   = max(valid_dates) if valid_dates else acq_date
    days_held   = (last_date - acq_date).days

    result = {
        'player_id':        pickup['player_id'],
        'player_name':      pickup['player_name'],
        'team_name':        pickup['team_name'],
        'acquisition_date': pickup['acquisition_date'],
        'end_date':         last_date.isoformat(),
        'player_type':      player_type,
        'days_held':        days_held,
    }

    if player_type == 'batter':
        _agg_batter(result, active_rows, benched_rows)
    else:
        _agg_pitcher(result, active_rows, benched_rows)

    return result


# ---------------------------------------------------------------------------
# Step 5 — Collapse stints (same as 2026)
# ---------------------------------------------------------------------------

def _held_ranges(stints):
    parts = []
    for s in stints:
        start = parse_date(s['acquisition_date'])
        end   = parse_date(s['end_date'])
        if start == end or end is None:
            parts.append(fmt_date(start))
        else:
            parts.append(f"{fmt_date(start)}–{fmt_date(end)}")
    return ', '.join(parts)


def collapse_stints(aggregated):
    groups = defaultdict(list)
    for p in aggregated:
        groups[(p['player_id'], p['team_name'], p['player_type'])].append(p)

    collapsed = []
    for (_pid, _team, _ptype), stints in groups.items():
        stints = sorted(stints, key=lambda x: x['acquisition_date'])
        first  = stints[0]
        row = {
            'player_id':        first['player_id'],
            'player_name':      first['player_name'],
            'team_name':        first['team_name'],
            'acquisition_date': first['acquisition_date'],
            'held_ranges':      _held_ranges(stints),
            'num_stints':       len(stints),
            'player_type':      first['player_type'],
        }
        total_active  = sum(s['games_active']  for s in stints)
        total_benched = sum(s['games_benched'] for s in stints)
        total_games   = total_active + total_benched
        row['games_active']     = total_active
        row['games_benched']    = total_benched
        row['days_held']        = sum(s['days_held'] for s in stints)
        row['utilization_rate'] = round(total_active / total_games, 3) if total_games > 0 else 0.0

        if first['player_type'] == 'batter':
            total_ab     = sum(s['_total_ab']     for s in stints)
            weighted_ops = sum(s['_weighted_ops'] for s in stints)
            row.update({
                'R': sum(s['R'] for s in stints), 'HR': sum(s['HR'] for s in stints),
                'RBI': sum(s['RBI'] for s in stints), 'SB': sum(s['SB'] for s in stints),
                'OPS': round(weighted_ops / total_ab, 3) if total_ab > 0 else 0.0,
                'QS': '', 'SVHD': '', 'K/9': '', 'ERA': '', 'WHIP': '',
            })
        else:
            ER = sum(s['_ER'] for s in stints); P_H  = sum(s['_P_H']  for s in stints)
            P_BB = sum(s['_P_BB'] for s in stints); K = sum(s['_K'] for s in stints)
            OUTS = sum(s['_OUTS'] for s in stints)
            row.update({
                'QS': sum(s['QS'] for s in stints), 'SVHD': sum(s['SVHD'] for s in stints),
                'K/9':  round((K * 27) / OUTS, 2)           if OUTS > 0 else 0.0,
                'ERA':  round((ER * 27) / OUTS, 3)           if OUTS > 0 else 0.0,
                'WHIP': round((P_H + P_BB) / (OUTS / 3), 3) if OUTS > 0 else 0.0,
                'R': '', 'HR': '', 'RBI': '', 'SB': '', 'OPS': '',
            })
        collapsed.append(row)

    multi = sum(1 for r in collapsed if r['num_stints'] > 1)
    print(f"Collapsed to {len(collapsed)} unique player-team entries ({multi} multi-stint).")
    return collapsed


# ---------------------------------------------------------------------------
# Step 6 — Z-scores (identical to 2026)
# ---------------------------------------------------------------------------

_BATTER_STATS  = ['R', 'HR', 'RBI', 'SB', 'OPS']
_PITCHER_STATS = ['QS', 'SVHD', 'K/9', 'ERA', 'WHIP']
_PITCHER_INV   = {'ERA', 'WHIP'}
_ALL_Z_FIELDS  = [f'z_{s}' for s in _BATTER_STATS + _PITCHER_STATS]


def add_z_scores(pickups):
    for p in pickups:
        for f in _ALL_Z_FIELDS:
            p[f] = ''
        p['composite_z'] = ''
    for player_type, stat_list, inverted in [
        ('batter',  _BATTER_STATS,  set()),
        ('pitcher', _PITCHER_STATS, _PITCHER_INV),
    ]:
        group = [p for p in pickups if p.get('player_type') == player_type]
        if not group:
            continue
        for stat in stat_list:
            vals = [safe_float(p.get(stat)) for p in group]
            zs   = compute_z_scores(vals)
            for p, z in zip(group, zs):
                p[f'z_{stat}'] = round(-z if stat in inverted else z, 4)
        for p in group:
            p['composite_z'] = round(
                sum(safe_float(p.get(f'z_{stat}')) for stat in stat_list), 4
            )


# ---------------------------------------------------------------------------
# Step 7 — Output
# ---------------------------------------------------------------------------

def print_batter_table(title, batters):
    print(f"\n{'=' * 120}\n  {title}\n{'=' * 120}")
    cols   = ['Player', 'Team', 'Held', 'Days', 'G_act', 'R', 'HR', 'RBI', 'SB', 'OPS', 'Z_composite']
    widths = [22, 22, 18, 5, 6, 5, 5, 5, 5, 6, 12]
    print_table(cols, [
        [p['player_name'], p['team_name'], p['held_ranges'], p['days_held'],
         p['games_active'], p['R'], p['HR'], p['RBI'], p['SB'],
         f"{p['OPS']:.3f}" if p['OPS'] != '' else '-',
         f"{p['composite_z']:.4f}"]
        for p in batters
    ], widths)


def print_pitcher_table(title, pitchers):
    print(f"\n{'=' * 120}\n  {title}\n{'=' * 120}")
    cols   = ['Player', 'Team', 'Held', 'Days', 'G_act', 'QS', 'SVHD', 'K/9', 'ERA', 'WHIP', 'Z_composite']
    widths = [22, 22, 18, 5, 6, 5, 6, 6, 7, 7, 12]
    print_table(cols, [
        [p['player_name'], p['team_name'], p['held_ranges'], p['days_held'],
         p['games_active'],
         p['QS'] if p['QS'] != '' else '-', p['SVHD'] if p['SVHD'] != '' else '-',
         f"{p['K/9']:.2f}"  if p['K/9']  != '' else '-',
         f"{p['ERA']:.3f}"  if p['ERA']  != '' else '-',
         f"{p['WHIP']:.3f}" if p['WHIP'] != '' else '-',
         f"{p['composite_z']:.4f}"]
        for p in pitchers
    ], widths)


_CSV_FIELDS = [
    'player_id', 'player_name', 'team_name', 'acquisition_date', 'held_ranges',
    'num_stints', 'player_type', 'days_held', 'games_active', 'games_benched',
    'utilization_rate', 'R', 'HR', 'RBI', 'SB', 'OPS',
    'QS', 'SVHD', 'K/9', 'ERA', 'WHIP',
    'z_R', 'z_HR', 'z_RBI', 'z_SB', 'z_OPS',
    'z_QS', 'z_SVHD', 'z_K/9', 'z_ERA', 'z_WHIP',
    'composite_z',
]


def save_csv(pickups):
    with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction='ignore')
        writer.writeheader()
        for p in pickups:
            writer.writerow({k: p.get(k, '') for k in _CSV_FIELDS})
    print(f"Saved {len(pickups)} rows → {OUTPUT_FILE}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n=== Best Pickups — ESPN 2025 (inferred from first-appearance) ===\n")

    sp_to_date  = load_schedule()
    team_names  = load_teams()
    all_stats   = load_stats(sp_to_date, team_names)
    pickups     = infer_pickups(all_stats, sp_to_date)

    stints, skipped = [], 0
    for p in pickups:
        result = aggregate_pickup(p, all_stats.get(p['player_id'], []))
        if result is not None:
            stints.append(result)
        else:
            skipped += 1
    print(f"Aggregated {len(stints)} stints ({skipped} skipped — no post-add data).")

    collapsed = collapse_stints(stints)
    add_z_scores(collapsed)

    batters  = sorted([p for p in collapsed if p['player_type'] == 'batter'],
                      key=lambda x: safe_float(x.get('composite_z')), reverse=True)
    pitchers = sorted([p for p in collapsed if p['player_type'] == 'pitcher'],
                      key=lambda x: safe_float(x.get('composite_z')), reverse=True)

    print_batter_table("Top 15 Batter Pickups — 2025 (composite z-score)", batters[:15])
    print_pitcher_table("Top 15 Pitcher Pickups — 2025 (composite z-score)", pitchers[:15])

    save_csv(collapsed)
    print("\nDone.")


if __name__ == '__main__':
    main()
