"""
Trade Analyzer — ESPN Fantasy Baseball 2026

Description:
    Evaluates a proposed 1-for-1 trade between two fantasy teams. For each
    player involved, reports:
      1. Current roster context for both teams (fresh ESPN API pull) including
         every player's lineup slot and IL/injury status
      2. Historical per-season stats from MLB daily data (2023–2026)
      3. 2026 full-season projection vs YTD actuals and full-season pace
      4. Category impact simulation: before/after rank changes across all 10
         H2H scoring categories (R, HR, RBI, SB, OPS / K/9, QS, SVHD, ERA, WHIP)
         for both teams, re-ranking all 10 league teams after the swap
      5. Plain-English verdict: who benefits, by how much, and key considerations

Source Data:
    ESPN API  (live roster pull via mlb_processing.setup_league)
    data-lake/01_Bronze/fantasy_baseball/2026_espn_stats_daily.csv
    data-lake/01_Bronze/fantasy_baseball/2026_espn_activity_season.csv
    data-lake/01_Bronze/fantasy_baseball/2026_ext_projections_batter.csv
    data-lake/01_Bronze/fantasy_baseball/2026_ext_projections_pitcher.csv
    data-lake/01_Bronze/fantasy_baseball/2023_mlb_stats_daily.csv  (and 2024, 2025, 2026)

Outputs:
    fantasy_baseball/reports/trade_analysis_{PlayerA}_{PlayerB}_{DATE}.md
    stdout (full report)

Usage:
    python analyze_trade_espn_2026.py \\
        --team-a "Datalickmyballs" \\
        --team-b "Skubal Snacks" \\
        --a-gives "Jazz Chisholm Jr." \\
        --b-gives "Eugenio Suarez"
"""

import csv
import io
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import date

# Allow importing mlb_processing from the parent fantasy_baseball/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import mlb_processing as mp

# ─── Constants ────────────────────────────────────────────────────────────────

BATTING_CATS    = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHING_CATS   = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
ALL_CATS        = BATTING_CATS + PITCHING_CATS
LOWER_IS_BETTER = frozenset({'ERA', 'WHIP'})

ACTIVE_BATTER_SLOTS  = frozenset({'C', '1B', '2B', '3B', 'SS', '2B/SS', '1B/3B', 'OF', 'UTIL'})
ACTIVE_PITCHER_SLOTS = frozenset({'SP', 'RP', 'P'})

MLB_YEARS    = [2023, 2024, 2025, 2026]
SEASON_DAYS  = 187
ELAPSED_DAYS = 48
YTD_SCALE    = SEASON_DAYS / ELAPSED_DAYS   # ≈ 3.90

MIN_BATTER_AB  = 30
MIN_PITCHER_IP = 5


# ─── Path helpers ─────────────────────────────────────────────────────────────

def _root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def _dp():
    return mp.DATA_PATH

def _rpt_dir():
    d = os.path.dirname(os.path.abspath(__file__))
    return d


# ─── Utilities ────────────────────────────────────────────────────────────────

def flt(v, default=0.0):
    if v is None or v == '':
        return default
    try:
        f = float(v)
        return default if f != f else f
    except (ValueError, TypeError):
        return default


def normalize_name(name: str) -> str:
    name = name.replace('\xa0', ' ')
    name = re.sub(r'\s*\(.*', '', name)
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    return ' '.join(name.split()).strip()


# ─── Category computation ─────────────────────────────────────────────────────

def bat_to_cats(b):
    obp_n = b.get('H', 0) + b.get('BB', 0) + b.get('HBP', 0)
    obp_d = b.get('AB', 0) + b.get('BB', 0) + b.get('HBP', 0) + b.get('SF', 0)
    slg_n = b.get('TB', 0)
    slg_d = b.get('AB', 0)
    OPS = (obp_n / obp_d if obp_d > 0 else 0.0) + (slg_n / slg_d if slg_d > 0 else 0.0)
    return {'R': b.get('R', 0), 'HR': b.get('HR', 0),
            'RBI': b.get('RBI', 0), 'SB': b.get('SB', 0), 'OPS': OPS}


def pit_to_cats(p):
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


def team_agg_to_cats(bat, pit):
    return {**bat_to_cats(bat), **pit_to_cats(pit)}


def rank_teams(team_cats, all_team_ids):
    ranks = {tid: {} for tid in all_team_ids}
    for cat in ALL_CATS:
        vals = [(tid, team_cats[tid].get(cat, 0.0)) for tid in all_team_ids]
        reverse = cat not in LOWER_IS_BETTER
        for r, (tid, _) in enumerate(
                sorted(vals, key=lambda x: x[1], reverse=reverse), 1):
            ranks[tid][cat] = r
    return ranks


# ─── ESPN daily loader ────────────────────────────────────────────────────────

def load_espn_daily(path):
    team_names     = {}
    player_current = {}
    player_bat_acc = defaultdict(lambda: defaultdict(float))
    player_pit_acc = defaultdict(lambda: defaultdict(float))
    team_bat_ytd   = defaultdict(lambda: defaultdict(float))
    team_pit_ytd   = defaultdict(lambda: defaultdict(float))

    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            tid   = row['team_id']
            pid   = row['player_id']
            ptype = row['player_type']
            slot  = row['lineup_slot']
            d     = row['date']
            team_names[tid] = row['team_name']

            if pid not in player_current or d >= player_current[pid]['date']:
                player_current[pid] = {
                    'date': d,
                    'player_name': row['player_name'],
                    'team_id': tid,
                    'team_name': row['team_name'],
                    'player_type': ptype,
                    'lineup_slot': slot,
                }

            if ptype == 'batter':
                b = {
                    'R': flt(row.get('R')), 'HR': flt(row.get('HR')),
                    'RBI': flt(row.get('RBI')), 'SB': flt(row.get('SB')),
                    'H': flt(row.get('H')), 'BB': flt(row.get('B_BB')),
                    'HBP': flt(row.get('HBP')), 'AB': flt(row.get('AB')),
                    'SF': flt(row.get('SF')), 'TB': flt(row.get('TB')),
                }
                for k, v in b.items():
                    player_bat_acc[pid][k] += v
                if slot in ACTIVE_BATTER_SLOTS:
                    for k, v in b.items():
                        team_bat_ytd[tid][k] += v
            elif ptype == 'pitcher':
                p = {
                    'OUTS': flt(row.get('OUTS')), 'K': flt(row.get('K')),
                    'ER': flt(row.get('ER')), 'P_H': flt(row.get('P_H')),
                    'P_BB': flt(row.get('P_BB')), 'QS': flt(row.get('QS')),
                    'SV': flt(row.get('SV')), 'HLD': flt(row.get('HLD')),
                }
                for k, v in p.items():
                    player_pit_acc[pid][k] += v
                if slot in ACTIVE_PITCHER_SLOTS:
                    for k, v in p.items():
                        team_pit_ytd[tid][k] += v

    return (team_names, player_current,
            player_bat_acc, player_pit_acc,
            team_bat_ytd, team_pit_ytd)


# ─── Free agent loader ────────────────────────────────────────────────────────

def load_free_agents(path):
    last_add, last_drop = {}, {}
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            pid, action, d = row['player_id'], row['action'], row['date']
            if action == 'DROPPED':
                if pid not in last_drop or d > last_drop[pid]:
                    last_drop[pid] = d
            elif action in ('FA ADDED', 'WAIVER ADDED', 'TRADED'):
                if pid not in last_add or d > last_add[pid]:
                    last_add[pid] = d
    return {pid for pid, drop_d in last_drop.items()
            if last_add.get(pid) is None or drop_d > last_add.get(pid)}


# ─── Projection loaders ───────────────────────────────────────────────────────

def load_batter_projections(path):
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
            TB     = H + two_b + 2.0 * three_b + 3.0 * HR
            projs[name] = {
                'ptype': 'batter',
                'R': flt(row.get('R')), 'HR': HR,
                'RBI': flt(row.get('RBI')), 'SB': flt(row.get('SB')),
                'AB': AB, 'H': H, 'BB': BB,
                'HBP': 0.0, 'SF': 0.0, 'TB': TB,
            }
    return projs


def load_pitcher_projections(path):
    projs = {}
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            name = normalize_name(row['Player'])
            IP   = flt(row.get('IP'))
            GS   = flt(row.get('GS'))
            SV   = flt(row.get('SV'))
            projs[name] = {
                'ptype': 'pitcher',
                'K':    flt(row.get('K')),
                'IP':   IP,
                'ER':   flt(row.get('ER')),
                'P_H':  flt(row.get('H')),
                'P_BB': flt(row.get('BB')),
                'QS':   0.65 * GS,
                'SVHD': SV,
                'SV':   SV,
                'GS':   GS,
            }
    return projs


# ─── Historical MLB stats loader ──────────────────────────────────────────────

def load_historical_stats(dp, years, target_norms):
    """
    Aggregate per-player per-year stats from MLB daily files (2023–2026).
    Handles column name differences: 2023-2025 use playerName/playerId,
    2026 uses player_name/player_id.

    Returns {norm_name: {year: stats_dict}}
    """
    results = {n: {} for n in target_norms}

    for year in years:
        path = os.path.join(dp, f'{year}_mlb_stats_daily.csv')
        if not os.path.isfile(path):
            continue

        bat_acc = defaultdict(lambda: defaultdict(float))
        pit_acc = defaultdict(lambda: defaultdict(float))

        with open(path, encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            name_col = 'player_name' if 'player_name' in reader.fieldnames else 'playerName'

            for row in reader:
                norm = normalize_name(row[name_col])
                if norm not in results:
                    continue
                b_or_p = row.get('b_or_p', '')

                if b_or_p == 'batter':
                    for col in ('R', 'HR', 'RBI', 'SB', 'H', 'AB',
                                'B_BB', 'HBP', 'SF', 'TB', 'G', '2B', '3B'):
                        bat_acc[norm][col] += flt(row.get(col))
                elif b_or_p == 'pitcher':
                    for col in ('OUTS', 'K', 'ER', 'P_H', 'P_BB',
                                'QS', 'SV', 'HLD', 'G', 'GS'):
                        pit_acc[norm][col] += flt(row.get(col))

        for norm in target_norms:
            if norm in bat_acc:
                b = bat_acc[norm]
                obp_n = b['H'] + b['B_BB'] + b['HBP']
                obp_d = b['AB'] + b['B_BB'] + b['HBP'] + b['SF']
                slg_d = b['AB']
                OPS = ((obp_n / obp_d) if obp_d > 0 else 0.0) + \
                      ((b['TB'] / slg_d) if slg_d > 0 else 0.0)
                results[norm][year] = {
                    'ptype': 'batter',
                    'G': int(b['G']), 'AB': int(b['AB']),
                    'R': int(b['R']), 'HR': int(b['HR']),
                    'RBI': int(b['RBI']), 'SB': int(b['SB']),
                    'OPS': round(OPS, 3),
                }
            elif norm in pit_acc:
                p = pit_acc[norm]
                IP = p['OUTS'] / 3.0
                results[norm][year] = {
                    'ptype': 'pitcher',
                    'G': int(p['G']), 'GS': int(p['GS']),
                    'IP': round(IP, 1),
                    'K/9':  round(p['K'] * 9 / IP, 1) if IP > 0 else 0.0,
                    'QS':   int(p['QS']),
                    'SVHD': int(p['SV'] + p['HLD']),
                    'ERA':  round(p['ER'] * 9 / IP, 3) if IP > 0 else 0.0,
                    'WHIP': round((p['P_H'] + p['P_BB']) / IP, 3) if IP > 0 else 0.0,
                }

    return results


# ─── Projection vector + team aggregate (for simulation) ─────────────────────

def make_proj_vec(pid, player_current, bat_projs, pit_projs,
                  player_bat_acc, player_pit_acc):
    info  = player_current[pid]
    ptype = info['player_type']
    name  = normalize_name(info['player_name'])

    if ptype == 'batter':
        proj = bat_projs.get(name)
        if proj and proj['AB'] >= MIN_BATTER_AB:
            return {'ptype': 'batter', 'source': 'proj', **proj}
        acc = player_bat_acc.get(pid)
        if not acc:
            return None
        s  = YTD_SCALE
        AB = acc.get('AB', 0) * s
        if AB < MIN_BATTER_AB:
            return None
        return {
            'ptype': 'batter', 'source': 'ytd',
            'R':   acc['R'] * s, 'HR':  acc['HR'] * s,
            'RBI': acc['RBI'] * s, 'SB': acc['SB'] * s,
            'AB':  AB,
            'H':   acc['H'] * s, 'BB':  acc['BB'] * s,
            'HBP': acc['HBP'] * s, 'SF': acc['SF'] * s,
            'TB':  acc['TB'] * s,
        }
    else:
        proj = pit_projs.get(name)
        if proj and proj['IP'] >= MIN_PITCHER_IP:
            return {'ptype': 'pitcher', 'source': 'proj', **proj}
        acc = player_pit_acc.get(pid)
        if not acc:
            return None
        s  = YTD_SCALE
        IP = (acc.get('OUTS', 0) / 3.0) * s
        if IP < MIN_PITCHER_IP:
            return None
        SV  = acc.get('SV', 0) * s
        HLD = acc.get('HLD', 0) * s
        return {
            'ptype': 'pitcher', 'source': 'ytd',
            'K':    acc['K'] * s, 'IP':   IP,
            'ER':   acc['ER'] * s, 'P_H':  acc['P_H'] * s,
            'P_BB': acc['P_BB'] * s, 'QS': acc['QS'] * s,
            'SVHD': SV + HLD, 'SV': SV, 'GS': 0.0,
        }


def _apply_pv(bat, pit, pv, sign):
    if pv['ptype'] == 'batter':
        for k in ('R', 'HR', 'RBI', 'SB', 'AB', 'H', 'BB', 'HBP', 'SF', 'TB'):
            bat[k] = bat.get(k, 0.0) + sign * pv.get(k, 0.0)
    else:
        for k in ('K', 'IP', 'ER', 'P_H', 'P_BB', 'QS', 'SVHD'):
            pit[k] = pit.get(k, 0.0) + sign * pv.get(k, 0.0)


def build_team_proj_aggs(team_rosters, proj_vecs):
    team_bat_proj, team_pit_proj = {}, {}
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


# ─── Roster table renderer ────────────────────────────────────────────────────

def render_roster_table(team_obj, highlight_norms):
    lines = ['| Player | Pos | Slot | IL / Injury |',
             '|--------|-----|------|-------------|']
    for player in sorted(team_obj.roster,
                         key=lambda p: (p.lineupSlot == 'IL', p.lineupSlot, p.name)):
        status = ''
        if player.injured:
            status = player.injuryStatus or 'IL'
        flag = ' ◄' if normalize_name(player.name) in highlight_norms else ''
        lines.append(f'| **{player.name}**{flag} | {player.position} '
                     f'| {player.lineupSlot} | {status} |')
    return '\n'.join(lines)


# ─── Team category profiles ───────────────────────────────────────────────────

def render_team_profiles(baseline_ranks, team_names, tid_a, tid_b):
    lines = []
    for tid in (tid_a, tid_b):
        tname = team_names.get(tid, tid)
        ranks = baseline_ranks[tid]
        lines.append(f'### {tname}')
        lines.append('| Category | Rank | Status |')
        lines.append('|----------|------|--------|')
        for cat in ALL_CATS:
            r = ranks[cat]
            if r <= 3:
                status = 'Strength'
            elif r >= 8:
                status = 'Weakness'
            else:
                status = 'Competitive'
            lines.append(f'| {cat} | #{r} | {status} |')
        lines.append('')
    return '\n'.join(lines)


# ─── Strategic verdict ────────────────────────────────────────────────────────

def render_strategic_verdict(sim_result, team_names):
    tid_a, tid_b = sim_result['tid_a'], sim_result['tid_b']
    br, nr       = sim_result['baseline_ranks'], sim_result['new_ranks']
    lines = []
    for tid in (tid_a, tid_b):
        tname    = team_names.get(tid, tid)
        improved = [c for c in ALL_CATS if nr[tid][c] < br[tid][c]]
        worsened = [c for c in ALL_CATS if nr[tid][c] > br[tid][c]]

        needs_met      = [c for c in improved if br[tid][c] >= 8]
        strength_piled = [c for c in improved if br[tid][c] <= 3]
        strength_lost  = [c for c in worsened if br[tid][c] <= 3]
        weakness_dug   = [c for c in worsened if br[tid][c] >= 8]

        parts = []
        if needs_met:
            parts.append(f'addresses weakness in {", ".join(needs_met)}')
        if strength_piled:
            parts.append(f'reinforces already-strong {", ".join(strength_piled)}')
        if strength_lost:
            parts.append(f'gives up a strength in {", ".join(strength_lost)}')
        if weakness_dug:
            parts.append(f'worsens an already-weak {", ".join(weakness_dug)}')
        if not improved and not worsened:
            parts.append('no meaningful rank movement')

        lines.append(f'**{tname}:** {"; ".join(parts) if parts else "no change"}.')
    return '\n'.join(lines)


# ─── Player profile section ───────────────────────────────────────────────────

def render_player_profile(player_name, pid, ptype, historical,
                          bat_projs, pit_projs,
                          player_bat_acc, player_pit_acc):
    norm  = normalize_name(player_name)
    lines = []

    # ── Historical table ──────────────────────────────────────────────────────
    hist = historical.get(norm, {})
    if hist:
        if ptype == 'batter':
            lines += ['**Historical Stats (MLB, full season)**', '',
                      '| Year | G | AB | R | HR | RBI | SB | OPS |',
                      '|------|---|----|----|-----|-----|-----|-----|']
            for yr in MLB_YEARS:
                if yr not in hist:
                    continue
                s = hist[yr]
                lines.append(f'| {yr} | {s["G"]} | {s["AB"]} | {s["R"]} '
                              f'| {s["HR"]} | {s["RBI"]} | {s["SB"]} '
                              f'| {s["OPS"]:.3f} |')
        else:
            lines += ['**Historical Stats (MLB, full season)**', '',
                      '| Year | G | GS | IP | K/9 | QS | SVHD | ERA | WHIP |',
                      '|------|---|----|----|-----|-----|------|-----|------|']
            for yr in MLB_YEARS:
                if yr not in hist:
                    continue
                s = hist[yr]
                lines.append(f'| {yr} | {s["G"]} | {s["GS"]} | {s["IP"]} '
                              f'| {s["K/9"]:.1f} | {s["QS"]} | {s["SVHD"]} '
                              f'| {s["ERA"]:.3f} | {s["WHIP"]:.3f} |')
        lines.append('')

    # ── 2026 Projection vs YTD pace ───────────────────────────────────────────
    proj_raw = bat_projs.get(norm) or pit_projs.get(norm)

    if ptype == 'batter' and pid:
        acc = dict(player_bat_acc.get(pid, {}))
        if acc and acc.get('AB', 0) >= 5 and proj_raw:
            obp_n = acc.get('H', 0) + acc.get('BB', 0) + acc.get('HBP', 0)
            obp_d = acc.get('AB', 0) + acc.get('BB', 0) + acc.get('HBP', 0) + acc.get('SF', 0)
            slg_d = acc.get('AB', 0)
            ops_ytd = ((obp_n / obp_d) if obp_d > 0 else 0.0) + \
                      ((acc.get('TB', 0) / slg_d) if slg_d > 0 else 0.0)
            s = YTD_SCALE
            proj_ops = bat_to_cats(proj_raw)['OPS']

            lines += ['**2026: Projection vs YTD Actuals vs Full-Season Pace**', '',
                      '| | R | HR | RBI | SB | OPS |',
                      '|---|---|----|----|-----|-----|']
            lines.append(
                f'| Full-Season Projection | {int(proj_raw.get("R",0))} '
                f'| {int(proj_raw.get("HR",0))} | {int(proj_raw.get("RBI",0))} '
                f'| {int(proj_raw.get("SB",0))} | {proj_ops:.3f} |')
            lines.append(
                f'| YTD Actual | {int(acc.get("R",0))} | {int(acc.get("HR",0))} '
                f'| {int(acc.get("RBI",0))} | {int(acc.get("SB",0))} '
                f'| {ops_ytd:.3f} |')
            lines.append(
                f'| Full-Season Pace (×{s:.1f}) | {int(acc.get("R",0)*s)} '
                f'| {int(acc.get("HR",0)*s)} | {int(acc.get("RBI",0)*s)} '
                f'| {int(acc.get("SB",0)*s)} | {ops_ytd:.3f} |')

            # Pace vs projection indicators
            def pace_vs_proj(ytd_val, proj_val, scale):
                pace = ytd_val * scale
                pct  = (pace / proj_val - 1) * 100 if proj_val else 0
                arrow = '▲' if pct >= 5 else ('▼' if pct <= -5 else '►')
                return f'{arrow} {pct:+.0f}%'

            lines.append(
                f'| Pace vs Projection | '
                f'{pace_vs_proj(acc.get("R",0), proj_raw.get("R",1), s)} | '
                f'{pace_vs_proj(acc.get("HR",0), proj_raw.get("HR",1), s)} | '
                f'{pace_vs_proj(acc.get("RBI",0), proj_raw.get("RBI",1), s)} | '
                f'{pace_vs_proj(acc.get("SB",0), proj_raw.get("SB",1), s)} | '
                f'{pace_vs_proj(ops_ytd, proj_ops, 1)} |')
            lines.append('')

    elif ptype == 'pitcher' and pid:
        acc = dict(player_pit_acc.get(pid, {}))
        IP  = acc.get('OUTS', 0) / 3.0
        if IP >= 1 and proj_raw:
            s      = YTD_SCALE
            k9_ytd  = acc.get('K', 0) * 9 / IP
            era_ytd = acc.get('ER', 0) * 9 / IP
            whip_ytd = (acc.get('P_H', 0) + acc.get('P_BB', 0)) / IP
            svhd_ytd = acc.get('SV', 0) + acc.get('HLD', 0)
            qs_ytd   = acc.get('QS', 0)

            proj_cats = pit_to_cats(proj_raw)

            lines += ['**2026: Projection vs YTD Actuals vs Full-Season Pace**', '',
                      '| | IP | K/9 | QS | SVHD | ERA | WHIP |',
                      '|---|---|-----|-----|------|-----|------|']
            lines.append(
                f'| Full-Season Projection | {proj_raw.get("IP",0):.0f} '
                f'| {proj_cats["K/9"]:.1f} | {proj_raw.get("QS",0):.0f} '
                f'| {proj_raw.get("SVHD",0):.0f} '
                f'| {proj_cats["ERA"]:.3f} | {proj_cats["WHIP"]:.3f} |')
            lines.append(
                f'| YTD Actual | {IP:.1f} | {k9_ytd:.1f} | {int(qs_ytd)} '
                f'| {int(svhd_ytd)} | {era_ytd:.3f} | {whip_ytd:.3f} |')
            lines.append(
                f'| Full-Season Pace (×{s:.1f}) | {IP*s:.0f} | {k9_ytd:.1f} '
                f'| {int(qs_ytd*s)} | {int(svhd_ytd*s)} '
                f'| {era_ytd:.3f} | {whip_ytd:.3f} |')

            def pace_vs_proj_pit(ytd_val, proj_val, scale, lower_better=False):
                pace = ytd_val * scale if scale != 1 else ytd_val
                pct  = (pace / proj_val - 1) * 100 if proj_val else 0
                if lower_better:
                    arrow = '▲' if pct <= -5 else ('▼' if pct >= 5 else '►')
                else:
                    arrow = '▲' if pct >= 5 else ('▼' if pct <= -5 else '►')
                return f'{arrow} {pct:+.0f}%'

            lines.append(
                f'| Pace vs Projection | '
                f'{pace_vs_proj_pit(IP, proj_raw.get("IP",1), s)} | '
                f'{pace_vs_proj_pit(k9_ytd, proj_cats["K/9"], 1)} | '
                f'{pace_vs_proj_pit(qs_ytd, proj_raw.get("QS",1), s)} | '
                f'{pace_vs_proj_pit(svhd_ytd, proj_raw.get("SVHD",1), s)} | '
                f'{pace_vs_proj_pit(era_ytd, proj_cats["ERA"], 1, lower_better=True)} | '
                f'{pace_vs_proj_pit(whip_ytd, proj_cats["WHIP"], 1, lower_better=True)} |')
            lines.append('')

    return '\n'.join(lines)


# ─── Category impact table ────────────────────────────────────────────────────

def render_category_impact(sim, team_names):
    ta, tb = sim['tid_a'], sim['tid_b']
    br, nr = sim['baseline_ranks'], sim['new_ranks']
    tname_a = team_names.get(ta, ta)[:20]
    tname_b = team_names.get(tb, tb)[:20]

    lines = [
        f'| Cat | {tname_a} Before | After | Δ | {tname_b} Before | After | Δ |',
        '|-----|' + '---------|' * 6,
    ]

    for cat in ALL_CATS:
        ba, aa = br[ta][cat], nr[ta][cat]
        bb, ab = br[tb][cat], nr[tb][cat]
        da = ba - aa   # positive = rank improved (lower rank number)
        db = bb - ab
        sym_a = f'**+{da}↑**' if da > 0 else (f'{da}↓' if da < 0 else '—')
        sym_b = f'**+{db}↑**' if db > 0 else (f'{db}↓' if db < 0 else '—')
        lines.append(f'| {cat} | {ba} | {aa} | {sym_a} | {bb} | {ab} | {sym_b} |')

    return '\n'.join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    team_a = team_b = a_gives = b_gives = None
    i = 0
    while i < len(args):
        if args[i] == '--team-a'   and i + 1 < len(args): team_a   = args[i+1]; i += 2
        elif args[i] == '--team-b' and i + 1 < len(args): team_b   = args[i+1]; i += 2
        elif args[i] == '--a-gives'and i + 1 < len(args): a_gives  = args[i+1]; i += 2
        elif args[i] == '--b-gives'and i + 1 < len(args): b_gives  = args[i+1]; i += 2
        else: i += 1

    if not all([team_a, team_b, a_gives, b_gives]):
        print('Usage: python analyze_trade_espn_2026.py '
              '--team-a NAME --team-b NAME --a-gives PLAYER --b-gives PLAYER')
        sys.exit(1)

    a_norm = normalize_name(a_gives)
    b_norm = normalize_name(b_gives)
    dp     = _dp()

    # ── Fresh ESPN rosters via API ─────────────────────────────────────────────
    print('Fetching current ESPN rosters via API...', file=sys.stderr)
    config   = mp.load_config('config.ini')
    league   = mp.setup_league(config, year=2026)
    team_map = {normalize_name(t.team_name): t for t in league.teams}
    team_obj_a = next((v for k, v in team_map.items()
                       if team_a.lower() in k.lower()), None)
    team_obj_b = next((v for k, v in team_map.items()
                       if team_b.lower() in k.lower()), None)
    if not team_obj_a:
        print(f"ERROR: no team matching '{team_a}'"); sys.exit(1)
    if not team_obj_b:
        print(f"ERROR: no team matching '{team_b}'"); sys.exit(1)

    # ── ESPN daily (YTD stats + team projection base) ─────────────────────────
    print('Loading ESPN daily stats...', file=sys.stderr)
    (team_names, player_current,
     player_bat_acc, player_pit_acc,
     team_bat_ytd, team_pit_ytd) = load_espn_daily(
        os.path.join(dp, '2026_espn_stats_daily.csv'))

    free_agents = load_free_agents(
        os.path.join(dp, '2026_espn_activity_season.csv'))

    # Find ESPN player IDs for the traded players (include IL, exclude FA)
    pid_a = pid_b = None
    for pid, info in player_current.items():
        if pid in free_agents:
            continue
        if normalize_name(info['player_name']) == a_norm:
            pid_a = pid
        if normalize_name(info['player_name']) == b_norm:
            pid_b = pid

    if not pid_a:
        print(f"WARNING: '{a_gives}' not found on active rosters", file=sys.stderr)
    if not pid_b:
        print(f"WARNING: '{b_gives}' not found on active rosters", file=sys.stderr)

    # ── Projections ───────────────────────────────────────────────────────────
    print('Loading projections...', file=sys.stderr)
    bat_projs = load_batter_projections(
        os.path.join(dp, '2026_ext_projections_batter.csv'))
    pit_projs = load_pitcher_projections(
        os.path.join(dp, '2026_ext_projections_pitcher.csv'))

    # ── Historical MLB stats 2023–2026 ────────────────────────────────────────
    print('Loading historical MLB stats (2023–2026)...', file=sys.stderr)
    historical = load_historical_stats(dp, MLB_YEARS, [a_norm, b_norm])

    # ── Build league-wide projection aggregates for simulation ────────────────
    print('Building team projection aggregates...', file=sys.stderr)
    all_team_ids = sorted(team_names.keys())

    team_rosters = defaultdict(list)
    for pid, info in player_current.items():
        if info['lineup_slot'] != 'IL' and pid not in free_agents:
            team_rosters[info['team_id']].append(pid)

    proj_vecs = {}
    for pid, info in player_current.items():
        if pid in free_agents:
            continue
        pv = make_proj_vec(pid, player_current, bat_projs, pit_projs,
                           player_bat_acc, player_pit_acc)
        if pv:
            proj_vecs[pid] = pv

    team_bat_proj, team_pit_proj = build_team_proj_aggs(team_rosters, proj_vecs)
    proj_cats_base = {tid: team_agg_to_cats(team_bat_proj[tid], team_pit_proj[tid])
                      for tid in all_team_ids}
    baseline_ranks = rank_teams(proj_cats_base, all_team_ids)

    tid_a = next((tid for tid, n in team_names.items()
                  if team_a.lower() in n.lower()), None)
    tid_b = next((tid for tid, n in team_names.items()
                  if team_b.lower() in n.lower()), None)

    # ── Simulate the trade ────────────────────────────────────────────────────
    sim_result = None
    ptype_a = ptype_b = None

    if pid_a:
        ptype_a = player_current[pid_a]['player_type']
    elif a_norm in bat_projs:
        ptype_a = 'batter'
    elif a_norm in pit_projs:
        ptype_a = 'pitcher'

    if pid_b:
        ptype_b = player_current[pid_b]['player_type']
    elif b_norm in bat_projs:
        ptype_b = 'batter'
    elif b_norm in pit_projs:
        ptype_b = 'pitcher'

    if pid_a and pid_b and tid_a and tid_b:
        pv_a = proj_vecs.get(pid_a)
        pv_b = proj_vecs.get(pid_b)
        if pv_a and pv_b:
            bat_a = dict(team_bat_proj[tid_a]); pit_a = dict(team_pit_proj[tid_a])
            bat_b = dict(team_bat_proj[tid_b]); pit_b = dict(team_pit_proj[tid_b])
            # Only subtract if the player was active — IL players aren't in team aggregates
            if player_current.get(pid_a, {}).get('lineup_slot') != 'IL':
                _apply_pv(bat_a, pit_a, pv_a, -1)
            _apply_pv(bat_a, pit_a, pv_b, +1)
            if player_current.get(pid_b, {}).get('lineup_slot') != 'IL':
                _apply_pv(bat_b, pit_b, pv_b, -1)
            _apply_pv(bat_b, pit_b, pv_a, +1)
            new_cats = dict(proj_cats_base)
            new_cats[tid_a] = team_agg_to_cats(bat_a, pit_a)
            new_cats[tid_b] = team_agg_to_cats(bat_b, pit_b)
            new_ranks = rank_teams(new_cats, all_team_ids)

            def side(tid):
                imp = sum(1 for c in ALL_CATS
                          if new_ranks[tid][c] < baseline_ranks[tid][c])
                wor = sum(1 for c in ALL_CATS
                          if new_ranks[tid][c] > baseline_ranks[tid][c])
                return imp, wor

            imp_a, wor_a = side(tid_a)
            imp_b, wor_b = side(tid_b)
            sim_result = {
                'tid_a': tid_a, 'tid_b': tid_b,
                'imp_a': imp_a, 'wor_a': wor_a, 'net_a': imp_a - wor_a,
                'imp_b': imp_b, 'wor_b': wor_b, 'net_b': imp_b - wor_b,
                'baseline_ranks': baseline_ranks,
                'new_ranks': new_ranks,
            }

    # ── Build report ──────────────────────────────────────────────────────────
    tname_a = team_names.get(tid_a, team_a)
    tname_b = team_names.get(tid_b, team_b)

    lines = []
    lines.append(f'# Trade Analysis: {a_gives} ↔ {b_gives}')
    lines.append(f'*Generated: {date.today()}*')
    lines.append(f'*{tname_a} gives **{a_gives}** | {tname_b} gives **{b_gives}***')
    lines.append('')
    lines.append('---')

    # ── Current Rosters ───────────────────────────────────────────────────────
    lines.append('')
    lines.append('## Current Rosters')
    lines.append('*◄ = player involved in this trade*')
    lines.append('')
    for label, obj, tid in [(tname_a, team_obj_a, tid_a),
                             (tname_b, team_obj_b, tid_b)]:
        lines.append(f'### {label}')
        lines.append(render_roster_table(obj, {a_norm, b_norm}))
        lines.append('')

    lines.append('---')

    # ── Team Category Profiles ────────────────────────────────────────────────
    if tid_a and tid_b and baseline_ranks:
        lines.append('')
        lines.append('## Team Category Profiles')
        lines.append('*Rank 1 = best in league, 10 = worst. Based on full-season projections.*')
        lines.append('')
        lines.append(render_team_profiles(baseline_ranks, team_names, tid_a, tid_b))
        lines.append('---')

    # ── Player Profiles ───────────────────────────────────────────────────────
    lines.append('')
    lines.append('## Player Profiles')
    lines.append('')

    for pname, pid, ptype, giving in [
        (a_gives, pid_a, ptype_a, tname_a),
        (b_gives, pid_b, ptype_b, tname_b),
    ]:
        lines.append(f'### {pname}')
        lines.append(f'*Currently on {giving} | Type: {ptype or "unknown"}*')
        lines.append('')
        lines.append(render_player_profile(
            pname, pid, ptype, historical,
            bat_projs, pit_projs, player_bat_acc, player_pit_acc))
        lines.append('---')
        lines.append('')

    # ── Category Impact ───────────────────────────────────────────────────────
    lines.append('## Category Impact Simulation')
    lines.append('')

    if sim_result:
        lines.append('*Re-ranks all 10 teams after the swap. Rank 1 = best, 10 = worst.*')
        lines.append('')
        lines.append(render_category_impact(sim_result, team_names))
        lines.append('')

        net_a = sim_result['net_a']
        net_b = sim_result['net_b']
        lines.append(
            f'**{tname_a}:** {sim_result["imp_a"]} improved, '
            f'{sim_result["wor_a"]} worsened → net '
            f'**{"+" if net_a >= 0 else ""}{net_a}**')
        lines.append(
            f'**{tname_b}:** {sim_result["imp_b"]} improved, '
            f'{sim_result["wor_b"]} worsened → net '
            f'**{"+" if net_b >= 0 else ""}{net_b}**')
        lines.append('')

        if net_a > 0 and net_b > 0:
            lines.append('**Verdict: Mutually beneficial** — both teams net-improve.')
        elif net_a > 0:
            lines.append(f'**Verdict: Favors {tname_a}** — {tname_b} does not net-improve.')
        elif net_b > 0:
            lines.append(f'**Verdict: Favors {tname_b}** — {tname_a} does not net-improve.')
        else:
            lines.append('**Verdict: Neither team net-improves** on projected category rankings.')
        lines.append('')
        lines.append('**Strategic Fit:**')
        lines.append(render_strategic_verdict(sim_result, team_names))
    else:
        lines.append('*Simulation unavailable — one or more players not found in active rosters.*')

    lines.append('')
    lines.append('---')
    lines.append(f'*Last Updated: {date.today()}*')

    report = '\n'.join(lines)

    # ── Save and print ────────────────────────────────────────────────────────
    out_name = (f'trade_analysis_'
                f'{a_gives.split()[0]}_{b_gives.split()[0]}_'
                f'{date.today()}.md')
    out_path = os.path.join(_rpt_dir(), out_name)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)
    print(f'\nReport saved → {out_path}', file=sys.stderr)


if __name__ == '__main__':
    main()
