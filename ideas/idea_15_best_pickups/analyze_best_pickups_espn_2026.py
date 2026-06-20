"""
Description: Ranks the best non-draft player acquisitions (FA ADDED) of the 2026 ESPN fantasy
             baseball season by post-add categorical contribution. For each pickup, builds a
             post-add stat window scoped strictly to that team's ownership period (capped at the
             next re-add date so overlapping windows are prevented), then collapses multiple
             stints for the same player-team into one combined row with a date-range label.
             Z-score normalization is applied within each player type (batter/pitcher) on the
             collapsed data to produce a composite ranking score.
             Also identifies the worst drops: players released who went on to contribute
             meaningfully on other fantasy teams, ranked by post-drop composite z-score.
Source Data: data-lake/01_Bronze/fantasy_baseball/2026_espn_activity_season.csv
             data-lake/01_Bronze/fantasy_baseball/2026_espn_stats_daily.csv
Outputs:     stdout — top 15 batters, top 15 pitchers, per-team leaderboard, wasted pickups,
                      top 10 worst batter drops, top 10 worst pitcher drops
             data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv
"""

import csv
import io
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

# Add fantasy_baseball/ to sys.path so mlb_processing can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import mlb_processing as mp

ACTIVITY_FILE = os.path.join(mp.DATA_PATH, '2026_espn_activity_season.csv')
STATS_FILE    = os.path.join(mp.DATA_PATH, '2026_espn_stats_daily.csv')
OUTPUT_FILE   = os.path.join(mp.DATA_PATH, '2026_espn_best_pickups.csv')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default  # guard NaN
    except (ValueError, TypeError):
        return default


def parse_date(s):
    try:
        return datetime.strptime(str(s)[:10], '%Y-%m-%d').date()
    except Exception:
        return None


def fmt_date(d):
    """date → 'MM/DD' display string."""
    return d.strftime('%m/%d') if d else '?'


def compute_z_scores(values):
    """Returns z-scores for a list of floats; std == 0 → all zeros."""
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


# ---------------------------------------------------------------------------
# Step 1 — Load pickups and assign end_date caps
# ---------------------------------------------------------------------------

def load_pickups():
    """
    Reads 2026_espn_activity_season.csv. Returns one dict per FA ADDED event.
    For the same (player_id, team_name) picked up multiple times, each stint's
    end_date is capped at (next_add_date - 1 day) so stat windows never overlap.
    """
    seen = set()
    pickups = []
    with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('action') != 'FA ADDED':
                continue
            pid   = row.get('player_id', '').strip()
            pname = row.get('player_name', '').strip()
            tname = row.get('team_name', '').strip()
            acq   = row.get('date', '')[:10]
            key   = (pid, tname, acq)
            if key in seen:
                continue
            seen.add(key)
            pickups.append({
                'player_id':        pid,
                'player_name':      pname,
                'team_name':        tname,
                'acquisition_date': acq,
                'end_date':         None,   # filled in below
            })

    # For each (player_id, team_name) group, sort by add date and cap each
    # non-final stint at one day before the next re-add.
    stints_by_key = defaultdict(list)
    for p in pickups:
        stints_by_key[(p['player_id'], p['team_name'])].append(p)

    for stints in stints_by_key.values():
        stints.sort(key=lambda x: x['acquisition_date'])
        for i, s in enumerate(stints):
            if i < len(stints) - 1:
                next_acq = parse_date(stints[i + 1]['acquisition_date'])
                s['end_date'] = (next_acq - timedelta(days=1)).isoformat()
            # Last (or only) stint keeps end_date = None (no cap)

    print(f"Loaded {len(pickups)} unique FA ADDED pickups.")
    return pickups


# ---------------------------------------------------------------------------
# Step 2 — Load stats
# ---------------------------------------------------------------------------

def load_stats():
    """Reads 2026_espn_stats_daily.csv and returns a dict: player_id -> [rows]."""
    stats = defaultdict(list)
    with open(STATS_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stats[row.get('player_id', '').strip()].append(row)
    print(f"Loaded stats for {len(stats)} unique player IDs.")
    return stats


# ---------------------------------------------------------------------------
# Step 3 — Aggregate per-stint stats (with end_date cap)
# ---------------------------------------------------------------------------

def _is_il(slot):
    s = slot.strip()
    return s == 'IL' or s.startswith('IL')


def _player_type(post_rows):
    """Returns 'batter' or 'pitcher' by majority vote across post-add rows."""
    counts = defaultdict(int)
    for row in post_rows:
        pt = row.get('player_type', '').strip().lower()
        if pt in ('batter', 'pitcher'):
            counts[pt] += 1
    if not counts:
        return None
    return max(counts, key=counts.get)


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

    result['R']    = int(R)
    result['HR']   = int(HR)
    result['RBI']  = int(RBI)
    result['SB']   = int(SB)
    result['OPS']  = round(weighted_ops / total_ab, 3) if total_ab > 0 else 0.0
    result['QS']   = ''
    result['SVHD'] = ''
    result['K/9']  = ''
    result['ERA']  = ''
    result['WHIP'] = ''
    result['games_active']    = games_active
    result['games_benched']   = games_benched
    result['utilization_rate'] = (
        round(games_active / total_games, 3) if total_games > 0 else 0.0
    )
    # Intermediates for cross-stint combining (batter fields; pitcher fields zeroed for safety)
    result['_total_ab']     = total_ab
    result['_weighted_ops'] = weighted_ops
    result['_ER'] = result['_P_H'] = result['_P_BB'] = result['_K'] = result['_OUTS'] = 0.0


def _agg_pitcher(result, active_rows, benched_rows):
    QS = SVHD = K = 0.0
    ER = P_H = P_BB = OUTS = 0.0
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

    result['QS']   = int(QS)
    result['SVHD'] = int(SVHD)
    result['K/9']  = round((K * 27) / OUTS, 2) if OUTS > 0 else 0.0
    result['ERA']  = round((ER * 27) / OUTS, 3) if OUTS > 0 else 0.0
    result['WHIP'] = round((P_H + P_BB) / (OUTS / 3), 3) if OUTS > 0 else 0.0
    result['R']    = ''
    result['HR']   = ''
    result['RBI']  = ''
    result['SB']   = ''
    result['OPS']  = ''
    result['games_active']    = games_active
    result['games_benched']   = games_benched
    result['utilization_rate'] = (
        round(games_active / total_games, 3) if total_games > 0 else 0.0
    )
    # Intermediates for cross-stint combining (pitcher fields; batter fields zeroed for safety)
    result['_ER']           = ER
    result['_P_H']          = P_H
    result['_P_BB']         = P_BB
    result['_K']            = K
    result['_OUTS']         = OUTS
    result['_total_ab']     = 0.0
    result['_weighted_ops'] = 0.0


def aggregate_pickup(pickup, player_rows):
    """
    Builds the post-add window (start = acquisition_date, end = end_date if set)
    scoped to the owning team, then aggregates stats for that stint.
    Returns an enriched dict or None if no usable data exists in the window.
    """
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

    active_rows  = []
    benched_rows = []
    for row in post_rows:
        slot = row.get('lineup_slot', '')
        if _is_il(slot):
            continue
        elif slot.strip() == 'BE':
            benched_rows.append(row)
        else:
            active_rows.append(row)

    valid_dates = [parse_date(r.get('date', '')) for r in post_rows]
    valid_dates = [d for d in valid_dates if d is not None]
    last_date   = max(valid_dates) if valid_dates else acq_date
    days_held   = (last_date - acq_date).days

    result = {
        'player_id':        pickup['player_id'],
        'player_name':      pickup['player_name'],
        'team_name':        pickup['team_name'],
        'acquisition_date': pickup['acquisition_date'],
        'end_date':         last_date.isoformat(),   # actual last stat date
        'player_type':      player_type,
        'days_held':        days_held,
    }

    if player_type == 'batter':
        _agg_batter(result, active_rows, benched_rows)
    else:
        _agg_pitcher(result, active_rows, benched_rows)

    return result


# ---------------------------------------------------------------------------
# Step 4 — Collapse multiple stints for same (player, team) into one row
# ---------------------------------------------------------------------------

def _held_ranges(stints):
    """
    Builds a compact date-range string for a list of stints.
    Each stint contributes 'MM/DD–MM/DD'. Adjacent or single-day ranges are
    simplified: if a range is one day, it shows as 'MM/DD'.
    """
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
    """
    Groups per-stint results by (player_id, team_name). When a player has
    multiple stints with the same team, their stats are summed (or re-derived
    from summed intermediates) and their ownership periods are represented as a
    comma-separated list of date ranges in the 'held_ranges' field.
    """
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
        total_days    = sum(s['days_held'] for s in stints)

        row['games_active']    = total_active
        row['games_benched']   = total_benched
        row['days_held']       = total_days
        row['utilization_rate'] = (
            round(total_active / total_games, 3) if total_games > 0 else 0.0
        )

        if first['player_type'] == 'batter':
            total_ab     = sum(s['_total_ab']     for s in stints)
            weighted_ops = sum(s['_weighted_ops'] for s in stints)
            row['R']    = sum(s['R']   for s in stints)
            row['HR']   = sum(s['HR']  for s in stints)
            row['RBI']  = sum(s['RBI'] for s in stints)
            row['SB']   = sum(s['SB']  for s in stints)
            row['OPS']  = round(weighted_ops / total_ab, 3) if total_ab > 0 else 0.0
            row['QS'] = row['SVHD'] = row['K/9'] = row['ERA'] = row['WHIP'] = ''
        else:
            ER   = sum(s['_ER']   for s in stints)
            P_H  = sum(s['_P_H']  for s in stints)
            P_BB = sum(s['_P_BB'] for s in stints)
            K    = sum(s['_K']    for s in stints)
            OUTS = sum(s['_OUTS'] for s in stints)
            row['QS']   = sum(s['QS']   for s in stints)
            row['SVHD'] = sum(s['SVHD'] for s in stints)
            row['K/9']  = round((K * 27) / OUTS, 2) if OUTS > 0 else 0.0
            row['ERA']  = round((ER * 27) / OUTS, 3) if OUTS > 0 else 0.0
            row['WHIP'] = round((P_H + P_BB) / (OUTS / 3), 3) if OUTS > 0 else 0.0
            row['R'] = row['HR'] = row['RBI'] = row['SB'] = row['OPS'] = ''

        collapsed.append(row)

    multi = sum(1 for r in collapsed if r['num_stints'] > 1)
    print(f"Collapsed to {len(collapsed)} unique player-team entries "
          f"({multi} with multiple stints).")
    return collapsed


# ---------------------------------------------------------------------------
# Step 5 — Z-score normalization
# ---------------------------------------------------------------------------

_BATTER_STATS  = ['R', 'HR', 'RBI', 'SB', 'OPS']
_PITCHER_STATS = ['QS', 'SVHD', 'K/9', 'ERA', 'WHIP']
_PITCHER_INV   = {'ERA', 'WHIP'}

_ALL_Z_FIELDS = [f'z_{s}' for s in _BATTER_STATS + _PITCHER_STATS]


def add_z_scores(pickups):
    """
    Computes z-scores within each player type and adds composite_z.
    Batter stats: R, HR, RBI, SB, OPS (all higher-is-better).
    Pitcher stats: QS, SVHD, K/9 (higher-is-better); ERA, WHIP negated (lower-is-better).
    """
    for p in pickups:
        for field in _ALL_Z_FIELDS:
            p[field] = ''
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
# Step 6 — Print output
# ---------------------------------------------------------------------------

def _stints_label(p):
    """Returns '(2 stints)' annotation if multiple stints, else ''."""
    n = p.get('num_stints', 1)
    return f' ({n} stints)' if n > 1 else ''


def print_batter_table(title, batters):
    print(f"\n{'=' * 132}")
    print(f"  {title}")
    print(f"{'=' * 132}")
    cols   = ['Player', 'Team', 'Held', 'Days', 'Util%', 'G_act', 'G_bnch',
              'R', 'HR', 'RBI', 'SB', 'OPS', 'Z_composite']
    widths = [22, 20, 22, 5, 6, 6, 7, 5, 5, 5, 5, 6, 12]
    print_table(cols, [
        [
            p['player_name'] + _stints_label(p),
            p['team_name'],
            p['held_ranges'],
            p['days_held'],
            f"{p['utilization_rate']:.3f}",
            p['games_active'],
            p['games_benched'],
            p['R'], p['HR'], p['RBI'], p['SB'],
            f"{p['OPS']:.3f}" if p['OPS'] != '' else '-',
            f"{p['composite_z']:.4f}",
        ]
        for p in batters
    ], widths)


def print_pitcher_table(title, pitchers):
    print(f"\n{'=' * 138}")
    print(f"  {title}")
    print(f"{'=' * 138}")
    cols   = ['Player', 'Team', 'Held', 'Days', 'Util%', 'G_act', 'G_bnch',
              'QS', 'SVHD', 'K/9', 'ERA', 'WHIP', 'Z_composite']
    widths = [22, 20, 22, 5, 6, 6, 7, 5, 6, 6, 7, 7, 12]
    print_table(cols, [
        [
            p['player_name'] + _stints_label(p),
            p['team_name'],
            p['held_ranges'],
            p['days_held'],
            f"{p['utilization_rate']:.3f}",
            p['games_active'],
            p['games_benched'],
            p['QS']   if p['QS']   != '' else '-',
            p['SVHD'] if p['SVHD'] != '' else '-',
            f"{p['K/9']:.2f}"  if p['K/9']  != '' else '-',
            f"{p['ERA']:.3f}"  if p['ERA']  != '' else '-',
            f"{p['WHIP']:.3f}" if p['WHIP'] != '' else '-',
            f"{p['composite_z']:.4f}",
        ]
        for p in pitchers
    ], widths)


def print_team_leaderboard(pickups):
    print(f"\n{'=' * 90}")
    print("  Per-Team Leaderboard — Best Pickup & Average Utilization Rate")
    print(f"{'=' * 90}")
    print("  (Low avg utilization = team leaves their own waiver pickups on the bench)\n")

    by_team = defaultdict(list)
    for p in pickups:
        if p.get('composite_z') != '':
            by_team[p['team_name']].append(p)

    rows = []
    for team, tpickups in by_team.items():
        best     = max(tpickups, key=lambda x: safe_float(x.get('composite_z')))
        avg_util = sum(p['utilization_rate'] for p in tpickups) / len(tpickups)
        rows.append((
            team,
            best['player_name'],
            best['player_type'],
            f"{best['composite_z']:.4f}",
            f"{avg_util:.3f}",
            len(tpickups),
        ))

    rows.sort(key=lambda x: float(x[3]), reverse=True)
    cols   = ['Team', 'Best Pickup', 'Type', 'Best Z', 'Avg Util%', 'Unique Pickups']
    widths = [22, 22, 8, 10, 10, 14]
    print_table(cols, rows, widths)


def print_wasted_pickups(pickups):
    print(f"\n{'=' * 118}")
    print("  Wasted Pickups — composite_z > 0 (above avg) but utilization_rate < 0.50")
    print(f"{'=' * 118}")

    wasted = sorted(
        [p for p in pickups
         if p.get('composite_z') != ''
         and safe_float(p.get('composite_z')) > 0
         and p.get('utilization_rate', 0) < 0.5],
        key=lambda x: safe_float(x.get('composite_z')),
        reverse=True,
    )

    if not wasted:
        print("  (none)\n")
        return

    cols   = ['Player', 'Team', 'Type', 'Held', 'Util%', 'G_act', 'G_bnch', 'Z_composite']
    widths = [22, 22, 8, 22, 7, 6, 7, 12]
    print_table(cols, [
        [
            p['player_name'] + _stints_label(p),
            p['team_name'],
            p['player_type'],
            p['held_ranges'],
            f"{p['utilization_rate']:.3f}",
            p['games_active'],
            p['games_benched'],
            f"{p['composite_z']:.4f}",
        ]
        for p in wasted
    ], widths)


# ---------------------------------------------------------------------------
# Worst Drops — load, aggregate, print
# ---------------------------------------------------------------------------

def load_drops():
    """
    Reads DROPPED events from activity file.
    Returns one dict per unique (player_id, team_name, date) drop event.
    """
    seen  = set()
    drops = []
    with open(ACTIVITY_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get('action') != 'DROPPED':
                continue
            pid   = row.get('player_id',   '').strip()
            pname = row.get('player_name', '').strip()
            tname = row.get('team_name',   '').strip()
            date  = row.get('date', '')[:10]
            key   = (pid, tname, date)
            if key in seen:
                continue
            seen.add(key)
            drops.append({
                'player_id':     pid,
                'player_name':   pname,
                'dropping_team': tname,
                'drop_date':     date,
            })
    print(f"Loaded {len(drops)} unique DROPPED events.")
    return drops


def aggregate_post_drop(drop, player_rows):
    """
    Builds the post-drop window: date > drop_date, team_name != dropping_team.
    Returns an enriched dict or None if no usable post-drop data exists.
    """
    drop_date = parse_date(drop['drop_date'])
    if drop_date is None:
        return None

    dropping_team = drop['dropping_team']
    post_rows = [
        r for r in player_rows
        if (rd := parse_date(r.get('date', ''))) is not None
        and rd > drop_date
        and r.get('team_name', '').strip() not in (dropping_team, '')
    ]
    if not post_rows:
        return None

    player_type = _player_type(post_rows)
    if player_type is None:
        return None

    active_rows  = []
    benched_rows = []
    for row in post_rows:
        slot = row.get('lineup_slot', '')
        if _is_il(slot):
            continue
        elif slot.strip() == 'BE':
            benched_rows.append(row)
        else:
            active_rows.append(row)

    valid_dates = [parse_date(r.get('date', '')) for r in post_rows]
    valid_dates = [d for d in valid_dates if d is not None]
    last_date   = max(valid_dates) if valid_dates else drop_date
    days_after  = (last_date - drop_date).days

    # Collect teams that held the player after the drop, in chronological order
    seen_teams = []
    for r in sorted(post_rows, key=lambda x: x.get('date', '')):
        t = r.get('team_name', '').strip()
        if t and t not in seen_teams:
            seen_teams.append(t)
    picked_up_by = ', '.join(seen_teams)

    result = {
        'player_id':       drop['player_id'],
        'player_name':     drop['player_name'],
        'dropping_team':   dropping_team,
        'drop_date':       drop['drop_date'],
        'days_after_drop': days_after,
        'picked_up_by':    picked_up_by,
        'player_type':     player_type,
        'team_name':       dropping_team,   # stub so add_z_scores works unchanged
    }

    if player_type == 'batter':
        _agg_batter(result, active_rows, benched_rows)
    else:
        _agg_pitcher(result, active_rows, benched_rows)

    if result.get('games_active', 0) == 0:
        return None

    return result


def print_batter_drops(title, batters):
    print(f"\n{'=' * 148}")
    print(f"  {title}")
    print(f"{'=' * 148}")
    cols   = ['Player', 'Dropped By', 'Picked Up By', 'Drop Date', 'Days After',
              'R', 'HR', 'RBI', 'SB', 'OPS', 'Z_composite']
    widths = [22, 22, 22, 10, 11, 5, 5, 5, 5, 6, 12]
    print_table(cols, [
        [
            p['player_name'],
            p['dropping_team'],
            p.get('picked_up_by', ''),
            fmt_date(parse_date(p['drop_date'])),
            p['days_after_drop'],
            p['R'], p['HR'], p['RBI'], p['SB'],
            f"{p['OPS']:.3f}" if p['OPS'] != '' else '-',
            f"{p['composite_z']:.4f}",
        ]
        for p in batters
    ], widths)


def print_pitcher_drops(title, pitchers):
    print(f"\n{'=' * 154}")
    print(f"  {title}")
    print(f"{'=' * 154}")
    cols   = ['Player', 'Dropped By', 'Picked Up By', 'Drop Date', 'Days After',
              'QS', 'SVHD', 'K/9', 'ERA', 'WHIP', 'Z_composite']
    widths = [22, 22, 22, 10, 11, 5, 6, 6, 7, 7, 12]
    print_table(cols, [
        [
            p['player_name'],
            p['dropping_team'],
            p.get('picked_up_by', ''),
            fmt_date(parse_date(p['drop_date'])),
            p['days_after_drop'],
            p['QS']   if p['QS']   != '' else '-',
            p['SVHD'] if p['SVHD'] != '' else '-',
            f"{p['K/9']:.2f}"  if p['K/9']  != '' else '-',
            f"{p['ERA']:.3f}"  if p['ERA']  != '' else '-',
            f"{p['WHIP']:.3f}" if p['WHIP'] != '' else '-',
            f"{p['composite_z']:.4f}",
        ]
        for p in pitchers
    ], widths)


# ---------------------------------------------------------------------------
# Save CSV
# ---------------------------------------------------------------------------

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
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
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
    print("\n=== Best Pickups — ESPN 2026 ===\n")

    pickups   = load_pickups()
    all_stats = load_stats()

    # Aggregate per-stint (end_date-capped, team-scoped)
    stints    = []
    skipped   = 0
    for p in pickups:
        result = aggregate_pickup(p, all_stats.get(p['player_id'], []))
        if result is not None:
            stints.append(result)
        else:
            skipped += 1
    print(f"Aggregated {len(stints)} stints with post-add data "
          f"({skipped} skipped — no stats in window).")

    # Collapse same-player-same-team stints into one combined row
    collapsed = collapse_stints(stints)

    # Z-score on the collapsed data
    add_z_scores(collapsed)

    batters  = sorted(
        [p for p in collapsed if p['player_type'] == 'batter'],
        key=lambda x: safe_float(x.get('composite_z')), reverse=True,
    )
    pitchers = sorted(
        [p for p in collapsed if p['player_type'] == 'pitcher'],
        key=lambda x: safe_float(x.get('composite_z')), reverse=True,
    )

    print_batter_table("Top 15 Batter Pickups — ranked by composite z-score", batters[:15])
    print_pitcher_table("Top 15 Pitcher Pickups — ranked by composite z-score", pitchers[:15])
    print_team_leaderboard(collapsed)
    print_wasted_pickups(collapsed)

    save_csv(collapsed)

    # --- Worst drops (separate z-score pool from pickups) ---
    print("\n=== Worst Drops — ESPN 2026 ===\n")
    drops = load_drops()
    drop_results = []
    drop_skipped = 0
    for d in drops:
        result = aggregate_post_drop(d, all_stats.get(d['player_id'], []))
        if result is not None:
            drop_results.append(result)
        else:
            drop_skipped += 1
    print(f"Aggregated {len(drop_results)} drops with post-drop data "
          f"({drop_skipped} skipped — no stats on other teams after drop).")

    add_z_scores(drop_results)

    drop_batters  = sorted(
        [p for p in drop_results if p['player_type'] == 'batter'],
        key=lambda x: safe_float(x.get('composite_z')), reverse=True,
    )
    drop_pitchers = sorted(
        [p for p in drop_results if p['player_type'] == 'pitcher'],
        key=lambda x: safe_float(x.get('composite_z')), reverse=True,
    )

    print_batter_drops(
        "Top 10 Worst Batter Drops — players released who contributed most elsewhere",
        drop_batters[:10],
    )
    print_pitcher_drops(
        "Top 10 Worst Pitcher Drops — players released who contributed most elsewhere",
        drop_pitchers[:10],
    )

    print("\nDone.")


if __name__ == '__main__':
    main()
