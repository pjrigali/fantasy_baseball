"""
Mutually Beneficial Trade Finder — ESPN Fantasy Baseball 2026

Description:
    Scans every roster in the ESPN fantasy league, builds per-team YTD and
    projected category profiles across all 10 H2H scoring categories, then
    enumerates every 1-for-1 same-type player swap between each pair of teams.
    A trade is "mutually beneficial" when BOTH teams improve their net category
    rank (more categories gained than lost) using full-season projected stats.

    Methodology:
      1. Aggregate YTD stats (active lineup slots only) from stats_espn_daily to
         establish current team standings. Rate stats (OPS, ERA, WHIP, K/9) are
         computed from underlying counting components — never by averaging the
         pre-computed rate column.
      2. Load full-season projections; normalize player names (strip \xa0 and
         parenthetical team/pos suffixes, Unicode-flatten accents) and match to
         ESPN rosters. YTD stats scaled to full-season equivalents (×3.9) are
         used as fallback for unmatched players.
      3. Build projected full-season category totals for each team from projection
         vectors for all non-IL rostered players.
      4. Rank all 10 teams in each category (1 = best; ERA/WHIP rank 1 = lowest).
      5. For every team pair × every same-type player swap: apply the swap to both
         teams' projection aggregates, re-rank all 10 teams, count category rank
         improvements and worsenings for each side. Surface trades where BOTH
         teams net-improve (improved > worsened).
      6. Sort by combined net category gain; output top 500 to CSV.

    Limitations:
      - Pitcher SVHD uses projected SV only (holds not in projection file).
      - Positional slot eligibility is not enforced (e.g., a team swapping their
        only catcher for a corner OF may create a roster gap — verify manually).
      - Projection source is full-season, not rest-of-season; relative rankings
        between players are unaffected by this choice.

Source Data:
    data-lake/01_Bronze/fantasy_baseball/stats_espn_daily_2026.csv
    data-lake/01_Bronze/fantasy_baseball/player_batter_projections_2026.csv
    data-lake/01_Bronze/fantasy_baseball/player_pitcher_projections_2026.csv

Outputs:
    data-lake/01_Bronze/fantasy_baseball/analyze_trade_finder_espn_2026.csv
"""

import csv
import io
import os
import re
import sys
import unicodedata
from collections import defaultdict

# Force UTF-8 output on Windows to avoid cp1252 errors with special chars
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ─── Constants ────────────────────────────────────────────────────────────────

ACTIVE_BATTER_SLOTS  = frozenset({'C', '1B', '2B', '3B', 'SS', '2B/SS', '1B/3B', 'OF', 'UTIL'})
ACTIVE_PITCHER_SLOTS = frozenset({'SP', 'RP', 'P'})

BATTING_CATS   = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHING_CATS  = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
ALL_CATS       = BATTING_CATS + PITCHING_CATS
LOWER_IS_BETTER = frozenset({'ERA', 'WHIP'})

# Season fractions — data spans 2026-03-26 to 2026-05-13 (48 elapsed days)
# MLB season ≈ 187 days; scale YTD stats to full-season equivalent for fallback players.
SEASON_DAYS    = 187
ELAPSED_DAYS   = 48
YTD_TO_FS      = SEASON_DAYS / ELAPSED_DAYS   # ≈ 3.90

# Minimum thresholds to be a meaningful trade candidate
MIN_BATTER_AB  = 30
MIN_PITCHER_IP = 5

# Cap output rows
MAX_TRADES_OUT = 500


# ─── Path resolver ────────────────────────────────────────────────────────────

def _data_path():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    for name in ('.data_lake', 'data-lake'):
        p = os.path.join(root, name, '01_Bronze', 'fantasy_baseball')
        if os.path.isdir(p):
            return p
    raise FileNotFoundError(f"Bronze data path not found in {root} (searched .data_lake/data-lake)")


# ─── Utilities ────────────────────────────────────────────────────────────────

def flt(v, default=0.0):
    """Safe float: returns default for empty/None/non-numeric/NaN."""
    if v is None or v == '':
        return default
    try:
        f = float(v)
        return default if f != f else f
    except (ValueError, TypeError):
        return default


def normalize_name(name: str) -> str:
    """
    Canonical player name for cross-source matching.
    Removes \\xa0 separators, strips trailing (TEAM - POS) suffix,
    flattens Unicode accents (e.g. Acuña → Acuna), collapses whitespace.
    """
    name = name.replace('\xa0', ' ')
    name = re.sub(r'\s*\(.*', '', name)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return ' '.join(name.split()).strip()


# ─── ESPN daily loader ────────────────────────────────────────────────────────

def load_espn_daily(path):
    """
    Single-pass read of stats_espn_daily_2026.csv.

    Returns
    -------
    team_bat_ytd   {team_id: {component: float}}  — active batter slots only
    team_pit_ytd   {team_id: {component: float}}  — active pitcher slots only
    team_names     {team_id: str}
    player_current {player_id: {player_name, team_id, team_name, player_type, lineup_slot}}
    player_bat_acc {player_id: {component: float}}  — all slots (for fallback)
    player_pit_acc {player_id: {component: float}}  — all slots (for fallback)
    """
    team_bat_ytd   = defaultdict(lambda: defaultdict(float))
    team_pit_ytd   = defaultdict(lambda: defaultdict(float))
    team_names     = {}
    player_current = {}
    player_bat_acc = defaultdict(lambda: defaultdict(float))
    player_pit_acc = defaultdict(lambda: defaultdict(float))

    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            tid   = row['team_id']
            pid   = row['player_id']
            ptype = row['player_type']
            slot  = row['lineup_slot']
            date  = row['date']

            team_names[tid] = row['team_name']

            # Keep most-recent state per player
            if pid not in player_current or date >= player_current[pid]['date']:
                player_current[pid] = {
                    'date': date,
                    'player_name': row['player_name'],
                    'team_id': tid,
                    'team_name': row['team_name'],
                    'player_type': ptype,
                    'lineup_slot': slot,
                }

            if ptype == 'batter':
                b = {
                    'R':   flt(row.get('R')),
                    'HR':  flt(row.get('HR')),
                    'RBI': flt(row.get('RBI')),
                    'SB':  flt(row.get('SB')),
                    'H':   flt(row.get('H')),
                    'BB':  flt(row.get('B_BB')),
                    'HBP': flt(row.get('HBP')),
                    'AB':  flt(row.get('AB')),
                    'SF':  flt(row.get('SF')),
                    'TB':  flt(row.get('TB')),
                }
                for k, v in b.items():
                    player_bat_acc[pid][k] += v
                if slot in ACTIVE_BATTER_SLOTS:
                    for k, v in b.items():
                        team_bat_ytd[tid][k] += v

            elif ptype == 'pitcher':
                p = {
                    'OUTS': flt(row.get('OUTS')),
                    'K':    flt(row.get('K')),
                    'ER':   flt(row.get('ER')),
                    'P_H':  flt(row.get('P_H')),
                    'P_BB': flt(row.get('P_BB')),
                    'QS':   flt(row.get('QS')),
                    'SV':   flt(row.get('SV')),
                    'HLD':  flt(row.get('HLD')),
                }
                for k, v in p.items():
                    player_pit_acc[pid][k] += v
                if slot in ACTIVE_PITCHER_SLOTS:
                    for k, v in p.items():
                        team_pit_ytd[tid][k] += v

    return (team_bat_ytd, team_pit_ytd, team_names,
            player_current, player_bat_acc, player_pit_acc)


# ─── Projection loaders ───────────────────────────────────────────────────────

def load_batter_projections(path):
    """Returns {normalized_name: batter_component_dict}."""
    projs = {}
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = normalize_name(row['Player'])
            H      = flt(row.get('H'))
            two_b  = flt(row.get('2B'))
            three_b = flt(row.get('3B'))
            HR     = flt(row.get('HR'))
            BB     = flt(row.get('BB'))
            AB     = flt(row.get('AB'))
            # TB = H + 2B + 2*3B + 3*HR  (derived: 1B×1 + 2B×2 + 3B×3 + HR×4)
            TB = H + two_b + 2.0 * three_b + 3.0 * HR
            projs[name] = {
                'R':   flt(row.get('R')),
                'HR':  HR,
                'RBI': flt(row.get('RBI')),
                'SB':  flt(row.get('SB')),
                'AB':  AB, 'H': H, 'BB': BB,
                'HBP': 0.0, 'SF': 0.0, 'TB': TB,
            }
    return projs


def load_free_agents(path):
    """
    Read activity_espn_season_2026.csv and return the set of player_ids who are
    currently free agents (most recent action is DROPPED with no later re-add).
    """
    last_add  = {}   # pid -> date of most recent FA ADDED / WAIVER ADDED
    last_drop = {}   # pid -> date of most recent DROPPED

    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            pid    = row['player_id']
            action = row['action']
            date   = row['date']
            if action == 'DROPPED':
                if pid not in last_drop or date > last_drop[pid]:
                    last_drop[pid] = date
            elif action in ('FA ADDED', 'WAIVER ADDED', 'TRADED'):
                if pid not in last_add or date > last_add[pid]:
                    last_add[pid] = date

    free_agents = set()
    for pid, drop_date in last_drop.items():
        add_date = last_add.get(pid)
        if add_date is None or drop_date > add_date:
            free_agents.add(pid)
    return free_agents


def load_pitcher_projections(path):
    """Returns {normalized_name: pitcher_component_dict}."""
    projs = {}
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = normalize_name(row['Player'])
            IP  = flt(row.get('IP'))
            GS  = flt(row.get('GS'))
            SV  = flt(row.get('SV'))
            projs[name] = {
                'K':    flt(row.get('K')),
                'IP':   IP,
                'ER':   flt(row.get('ER')),
                'P_H':  flt(row.get('H')),
                'P_BB': flt(row.get('BB')),
                'QS':   0.65 * GS,
                'SVHD': SV,   # holds not in projections; SV is floor
                'SV':   SV,
                'GS':   GS,
            }
    return projs


# ─── Component → category conversion ─────────────────────────────────────────

def bat_to_cats(b):
    """Aggregate batter components → {R, HR, RBI, SB, OPS}."""
    obp_n = b.get('H', 0) + b.get('BB', 0) + b.get('HBP', 0)
    obp_d = b.get('AB', 0) + b.get('BB', 0) + b.get('HBP', 0) + b.get('SF', 0)
    slg_n = b.get('TB', 0)
    slg_d = b.get('AB', 0)
    OPS = (obp_n / obp_d if obp_d > 0 else 0.0) + (slg_n / slg_d if slg_d > 0 else 0.0)
    return {
        'R': b.get('R', 0), 'HR': b.get('HR', 0),
        'RBI': b.get('RBI', 0), 'SB': b.get('SB', 0), 'OPS': OPS,
    }


def pit_to_cats(p):
    """Aggregate pitcher components → {K/9, QS, SVHD, ERA, WHIP}."""
    IP = p.get('IP', 0.0)
    if IP <= 0:
        return {'K/9': 0.0, 'QS': p.get('QS', 0), 'SVHD': p.get('SVHD', 0),
                'ERA': 99.99, 'WHIP': 99.99}
    return {
        'K/9':  p.get('K', 0) * 9.0 / IP,
        'QS':   p.get('QS', 0),
        'SVHD': p.get('SVHD', 0),
        'ERA':  p.get('ER', 0) * 9.0 / IP,
        'WHIP': (p.get('P_H', 0) + p.get('P_BB', 0)) / IP,
    }


def ytd_pit_to_cats(p):
    """YTD pitcher components (OUTS not IP, SV+HLD not SVHD) → pitching cats."""
    OUTS = p.get('OUTS', 0.0)
    IP   = OUTS / 3.0
    if IP <= 0:
        return {'K/9': 0.0, 'QS': p.get('QS', 0),
                'SVHD': p.get('SV', 0) + p.get('HLD', 0),
                'ERA': 99.99, 'WHIP': 99.99}
    return {
        'K/9':  p.get('K', 0) * 9.0 / IP,
        'QS':   p.get('QS', 0),
        'SVHD': p.get('SV', 0) + p.get('HLD', 0),
        'ERA':  p.get('ER', 0) * 9.0 / IP,
        'WHIP': (p.get('P_H', 0) + p.get('P_BB', 0)) / IP,
    }


# ─── Team ranking ─────────────────────────────────────────────────────────────

def rank_teams(team_cats, all_team_ids):
    """Return {team_id: {cat: rank}}; rank 1 = best."""
    ranks = {tid: {} for tid in all_team_ids}
    for cat in ALL_CATS:
        vals = [(tid, team_cats[tid].get(cat, 0.0)) for tid in all_team_ids]
        reverse = cat not in LOWER_IS_BETTER
        for r, (tid, _) in enumerate(sorted(vals, key=lambda x: x[1], reverse=reverse), 1):
            ranks[tid][cat] = r
    return ranks


# ─── Player projection vectors ────────────────────────────────────────────────

def make_proj_vec(pid, player_current, bat_projs, pit_projs,
                  player_bat_acc, player_pit_acc):
    """
    Build a projection component vector for one player.
    Priority: full-season projection file → YTD stats scaled to full season.
    Returns None if the player has insufficient data to evaluate.
    """
    info  = player_current[pid]
    ptype = info['player_type']
    name  = normalize_name(info['player_name'])

    if ptype == 'batter':
        proj = bat_projs.get(name)
        if proj and proj['AB'] >= MIN_BATTER_AB:
            return {'ptype': 'batter', 'source': 'proj', **proj}
        # YTD fallback
        acc = player_bat_acc.get(pid)
        if not acc:
            return None
        s   = YTD_TO_FS
        AB  = acc.get('AB', 0) * s
        if AB < MIN_BATTER_AB:
            return None
        return {
            'ptype': 'batter', 'source': 'ytd',
            'R':   acc.get('R', 0) * s,  'HR':  acc.get('HR', 0) * s,
            'RBI': acc.get('RBI', 0) * s, 'SB':  acc.get('SB', 0) * s,
            'AB':  AB,
            'H':   acc.get('H', 0) * s,   'BB':  acc.get('BB', 0) * s,
            'HBP': acc.get('HBP', 0) * s, 'SF':  acc.get('SF', 0) * s,
            'TB':  acc.get('TB', 0) * s,
        }

    else:  # pitcher
        proj = pit_projs.get(name)
        if proj and proj['IP'] >= MIN_PITCHER_IP:
            return {'ptype': 'pitcher', 'source': 'proj', **proj}
        acc = player_pit_acc.get(pid)
        if not acc:
            return None
        s    = YTD_TO_FS
        IP   = (acc.get('OUTS', 0) / 3.0) * s
        if IP < MIN_PITCHER_IP:
            return None
        SV  = acc.get('SV', 0) * s
        HLD = acc.get('HLD', 0) * s
        return {
            'ptype': 'pitcher', 'source': 'ytd',
            'K':    acc.get('K', 0) * s,    'IP':   IP,
            'ER':   acc.get('ER', 0) * s,   'P_H':  acc.get('P_H', 0) * s,
            'P_BB': acc.get('P_BB', 0) * s, 'QS':   acc.get('QS', 0) * s,
            'SVHD': SV + HLD,
            'SV':   SV, 'GS': 0.0,
        }


def player_cat_summary(pv):
    """Compute per-player projected category stats for output display."""
    if pv is None:
        return {c: '' for c in ALL_CATS}
    if pv['ptype'] == 'batter':
        cats = bat_to_cats(pv)
        return {c: round(cats.get(c, 0), 3) if c in BATTING_CATS else '' for c in ALL_CATS}
    else:
        cats = pit_to_cats(pv)
        return {c: '' if c in BATTING_CATS else round(cats.get(c, 0), 3) for c in ALL_CATS}


# ─── Team projection aggregates ───────────────────────────────────────────────

def build_team_proj_aggs(team_rosters, proj_vecs):
    """
    Sum projection vectors per team (all non-IL rostered players).
    Returns (team_bat_proj, team_pit_proj) as plain dicts of component sums.
    """
    team_bat_proj = {}
    team_pit_proj = {}
    for tid, pids in team_rosters.items():
        bat = defaultdict(float)
        pit = defaultdict(float)
        for pid in pids:
            pv = proj_vecs.get(pid)
            if not pv:
                continue
            if pv['ptype'] == 'batter':
                for k in ('R', 'HR', 'RBI', 'SB', 'AB', 'H', 'BB', 'HBP', 'SF', 'TB'):
                    bat[k] += pv.get(k, 0.0)
            else:
                for k in ('K', 'IP', 'ER', 'P_H', 'P_BB', 'QS', 'SVHD'):
                    pit[k] += pv.get(k, 0.0)
        team_bat_proj[tid] = dict(bat)
        team_pit_proj[tid] = dict(pit)
    return team_bat_proj, team_pit_proj


def team_agg_to_cats(bat, pit):
    b_cats = bat_to_cats(bat)
    p_cats = pit_to_cats(pit)
    return {**b_cats, **p_cats}


# ─── Trade simulation ─────────────────────────────────────────────────────────

def _apply_pv(bat, pit, pv, sign):
    """Add (sign=+1) or remove (sign=-1) a player's projection vector in-place."""
    if pv['ptype'] == 'batter':
        for k in ('R', 'HR', 'RBI', 'SB', 'AB', 'H', 'BB', 'HBP', 'SF', 'TB'):
            bat[k] = bat.get(k, 0.0) + sign * pv.get(k, 0.0)
    else:
        for k in ('K', 'IP', 'ER', 'P_H', 'P_BB', 'QS', 'SVHD'):
            pit[k] = pit.get(k, 0.0) + sign * pv.get(k, 0.0)


def eval_swap(tid_a, tid_b, pid_x, pid_y,
              proj_vecs, team_bat_proj, team_pit_proj,
              proj_cats_base, baseline_ranks, all_team_ids):
    """
    Evaluate swapping player pid_x (from tid_a) with pid_y (from tid_b).
    Returns a result dict if mutually beneficial, else None.
    """
    pv_x = proj_vecs.get(pid_x)
    pv_y = proj_vecs.get(pid_y)
    if not pv_x or not pv_y:
        return None
    if pv_x['ptype'] != pv_y['ptype']:
        return None

    # Shallow-copy only the two affected teams' aggregates
    bat_a = dict(team_bat_proj[tid_a])
    pit_a = dict(team_pit_proj[tid_a])
    bat_b = dict(team_bat_proj[tid_b])
    pit_b = dict(team_pit_proj[tid_b])

    # Apply swap
    _apply_pv(bat_a, pit_a, pv_x, -1)
    _apply_pv(bat_a, pit_a, pv_y, +1)
    _apply_pv(bat_b, pit_b, pv_y, -1)
    _apply_pv(bat_b, pit_b, pv_x, +1)

    # Build new_cats: start from baseline, override only the two changed teams
    new_cats = dict(proj_cats_base)
    new_cats[tid_a] = team_agg_to_cats(bat_a, pit_a)
    new_cats[tid_b] = team_agg_to_cats(bat_b, pit_b)
    new_ranks = rank_teams(new_cats, all_team_ids)

    def side(tid):
        imp = sum(1 for c in ALL_CATS if new_ranks[tid][c] < baseline_ranks[tid][c])
        wor = sum(1 for c in ALL_CATS if new_ranks[tid][c] > baseline_ranks[tid][c])
        return imp, wor

    imp_a, wor_a = side(tid_a)
    imp_b, wor_b = side(tid_b)
    net_a = imp_a - wor_a
    net_b = imp_b - wor_b

    if net_a <= 0 or net_b <= 0:
        return None

    cat_delta_a = {c: (baseline_ranks[tid_a][c], new_ranks[tid_a][c]) for c in ALL_CATS}
    cat_delta_b = {c: (baseline_ranks[tid_b][c], new_ranks[tid_b][c]) for c in ALL_CATS}

    return {
        'tid_a': tid_a, 'tid_b': tid_b,
        'pid_x': pid_x, 'pid_y': pid_y,
        'ptype': pv_x['ptype'],
        'imp_a': imp_a, 'wor_a': wor_a, 'net_a': net_a,
        'imp_b': imp_b, 'wor_b': wor_b, 'net_b': net_b,
        'combined': net_a + net_b,
        'cat_delta_a': cat_delta_a,
        'cat_delta_b': cat_delta_b,
        'pv_x': pv_x, 'pv_y': pv_y,
    }


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    import argparse
    from datetime import datetime
    parser = argparse.ArgumentParser(description="Find mutually beneficial 1-for-1 trades.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    args = parser.parse_args()
    year = args.year

    dp = _data_path()

    # ── Load ESPN daily ────────────────────────────────────────────────────────
    print(f"Loading ESPN daily stats (year={year})...")
    (team_bat_ytd, team_pit_ytd, team_names,
     player_current, player_bat_acc, player_pit_acc) = load_espn_daily(
        os.path.join(dp, f'stats_espn_daily_{year}.csv'))
    print(f"  {len(team_names)} teams, {len(player_current)} players tracked")

    # ── Load activity — determines who is actually on a roster right now ─────
    print("Loading activity log to identify current free agents...")
    free_agents = load_free_agents(os.path.join(dp, f'activity_espn_season_{year}.csv'))
    n_fa = sum(1 for pid in player_current if pid in free_agents)
    print(f"  {n_fa} players in ESPN daily history are now free agents — excluded from analysis")

    # ── Load projections ───────────────────────────────────────────────────────
    print("Loading projections...")
    bat_projs = load_batter_projections(
        os.path.join(dp, f'player_batter_projections_{year}.csv'))
    pit_projs = load_pitcher_projections(
        os.path.join(dp, f'player_pitcher_projections_{year}.csv'))
    print(f"  {len(bat_projs)} batter projections, {len(pit_projs)} pitcher projections")

    # ── Build active rosters (exclude IL and free agents) ─────────────────────
    all_team_ids = sorted(team_names.keys())
    team_rosters = defaultdict(list)
    for pid, info in player_current.items():
        if info['lineup_slot'] != 'IL' and pid not in free_agents:
            team_rosters[info['team_id']].append(pid)

    # ── YTD category stats and rankings ───────────────────────────────────────
    ytd_cats = {}
    for tid in all_team_ids:
        ytd_cats[tid] = {
            **bat_to_cats(team_bat_ytd[tid]),
            **ytd_pit_to_cats(team_pit_ytd[tid]),
        }
    ytd_ranks = rank_teams(ytd_cats, all_team_ids)

    # ── Print YTD standings ────────────────────────────────────────────────────
    print("\n── YTD Category Rankings (active lineup slots only) ──")
    hdr = f"{'Team':<30} " + "  ".join(f"{c:>5}" for c in ALL_CATS) + "  TOTAL"
    print(hdr)
    for tid in sorted(all_team_ids, key=lambda t: sum(ytd_ranks[t][c] for c in ALL_CATS)):
        rrow = "  ".join(f"{ytd_ranks[tid][c]:>5}" for c in ALL_CATS)
        total = sum(ytd_ranks[tid][c] for c in ALL_CATS)
        print(f"{team_names[tid]:<30} {rrow}  {total:>5}")

    # ── Build player projection vectors ───────────────────────────────────────
    print("\nBuilding player projection vectors...")
    proj_vecs = {}
    n_proj = n_ytd = n_skip = 0
    for pid, info in player_current.items():
        if info['lineup_slot'] == 'IL' or pid in free_agents:
            continue
        pv = make_proj_vec(pid, player_current, bat_projs, pit_projs,
                           player_bat_acc, player_pit_acc)
        if pv:
            proj_vecs[pid] = pv
            if pv['source'] == 'proj':
                n_proj += 1
            else:
                n_ytd += 1
        else:
            n_skip += 1
    print(f"  Projection-matched: {n_proj}, YTD-scaled fallback: {n_ytd}, skipped (insufficient data): {n_skip}")

    # ── Projected team totals and baseline rankings ────────────────────────────
    team_bat_proj, team_pit_proj = build_team_proj_aggs(team_rosters, proj_vecs)
    proj_cats_base = {tid: team_agg_to_cats(team_bat_proj[tid], team_pit_proj[tid])
                      for tid in all_team_ids}
    baseline_ranks = rank_teams(proj_cats_base, all_team_ids)

    # ── Print projected standings ──────────────────────────────────────────────
    print("\n── Projected Category Rankings (full-season projections) ──")
    print(hdr)
    for tid in sorted(all_team_ids, key=lambda t: sum(baseline_ranks[t][c] for c in ALL_CATS)):
        rrow = "  ".join(f"{baseline_ranks[tid][c]:>5}" for c in ALL_CATS)
        total = sum(baseline_ranks[tid][c] for c in ALL_CATS)
        print(f"{team_names[tid]:<30} {rrow}  {total:>5}")

    # ── Enumerate all 1-for-1 swaps ───────────────────────────────────────────
    print("\nScanning trade candidates (1-for-1 same-type swaps)...")
    results = []
    team_id_list = list(all_team_ids)
    n_pairs = n_swaps = n_mutual = 0

    for i in range(len(team_id_list)):
        for j in range(i + 1, len(team_id_list)):
            tid_a = team_id_list[i]
            tid_b = team_id_list[j]
            n_pairs += 1

            pids_a = [p for p in team_rosters[tid_a] if p in proj_vecs]
            pids_b = [p for p in team_rosters[tid_b] if p in proj_vecs]

            for pid_x in pids_a:
                for pid_y in pids_b:
                    n_swaps += 1
                    res = eval_swap(tid_a, tid_b, pid_x, pid_y,
                                    proj_vecs, team_bat_proj, team_pit_proj,
                                    proj_cats_base, baseline_ranks, all_team_ids)
                    if res:
                        n_mutual += 1
                        results.append(res)

    print(f"  {n_pairs} team pairs, {n_swaps:,} swaps evaluated, {n_mutual} mutually beneficial")
    results.sort(key=lambda r: (r['combined'], r['net_a'] + r['net_b']), reverse=True)

    # ── Write output CSV ───────────────────────────────────────────────────────
    out_path = os.path.join(dp, f'analyze_trade_finder_espn_{year}.csv')

    cat_rank_cols = []
    for c in ALL_CATS:
        cat_rank_cols += [
            f'a_{c}_rank_before', f'a_{c}_rank_after',
            f'b_{c}_rank_before', f'b_{c}_rank_after',
        ]

    player_stat_cols = []
    for role in ('a_gives', 'b_gives'):
        for cat in ALL_CATS:
            player_stat_cols.append(f'{role}_proj_{cat}')

    fieldnames = (
        ['team_a_name', 'team_b_name',
         'player_a_gives', 'player_b_gives',
         'player_type',
         'a_cats_improved', 'a_cats_worsened', 'a_net_cats',
         'b_cats_improved', 'b_cats_worsened', 'b_net_cats',
         'combined_net_cats',
         'balance_min',   # min(net_a, net_b) — higher = both sides gain more equally
         'balance_diff',  # abs(net_a - net_b) — lower = more balanced
         'player_a_gives_source', 'player_b_gives_source']
        + player_stat_cols
        + cat_rank_cols
    )

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in results[:MAX_TRADES_OUT]:
            pv_x = r['pv_x']  # player A gives (x)
            pv_y = r['pv_y']  # player B gives (y)
            sum_x = player_cat_summary(pv_x)
            sum_y = player_cat_summary(pv_y)

            row = {
                'team_a_name':  team_names[r['tid_a']],
                'team_b_name':  team_names[r['tid_b']],
                'player_a_gives': player_current[r['pid_x']]['player_name'],
                'player_b_gives': player_current[r['pid_y']]['player_name'],
                'player_type':  r['ptype'],
                'a_cats_improved': r['imp_a'], 'a_cats_worsened': r['wor_a'],
                'a_net_cats':   r['net_a'],
                'b_cats_improved': r['imp_b'], 'b_cats_worsened': r['wor_b'],
                'b_net_cats':   r['net_b'],
                'combined_net_cats': r['combined'],
                'balance_min':  min(r['net_a'], r['net_b']),
                'balance_diff': abs(r['net_a'] - r['net_b']),
                'player_a_gives_source': pv_x.get('source', ''),
                'player_b_gives_source': pv_y.get('source', ''),
            }

            for cat in ALL_CATS:
                row[f'a_gives_proj_{cat}'] = sum_x.get(cat, '')
                row[f'b_gives_proj_{cat}'] = sum_y.get(cat, '')

            for cat in ALL_CATS:
                bef_a, aft_a = r['cat_delta_a'][cat]
                bef_b, aft_b = r['cat_delta_b'][cat]
                row[f'a_{cat}_rank_before'] = bef_a
                row[f'a_{cat}_rank_after']  = aft_a
                row[f'b_{cat}_rank_before'] = bef_b
                row[f'b_{cat}_rank_after']  = aft_b

            writer.writerow(row)

    print(f"\nOutput saved → {out_path}")
    print(f"Top 5 mutually beneficial trades:")
    for r in results[:5]:
        ax = player_current[r['pid_x']]['player_name']
        ay = player_current[r['pid_y']]['player_name']
        print(f"  {team_names[r['tid_a']]} gives {ax!r:30s} | "
              f"{team_names[r['tid_b']]} gives {ay!r:30s} | "
              f"({r['ptype']}) net: A+{r['net_a']} B+{r['net_b']} combined={r['combined']}")


if __name__ == '__main__':
    main()
