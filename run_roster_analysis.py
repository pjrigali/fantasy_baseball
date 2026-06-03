"""
Description: Full fantasy baseball roster analysis — batter/pitcher stats, batting order,
             weakness identification (flag-based + z-score), FA scanning, and dual-method
             replacement recommendations: 8A position-matched, 8B position-agnostic, and
             z-score based per flagged player.
Source Data: data-lake/01_Bronze/fantasy_baseball/ CSVs + ESPN API
Outputs: fantasy_baseball/reports/roster_analysis_<YYYY-MM-DD>.md
"""

import sys, csv, os
from datetime import date, timedelta
import pandas as pd
import numpy as np

sys.path.insert(0, r'C:\Users\peter.rigali\Desktop\acn_repo')
from fantasy_baseball import mlb_processing as mp

YEAR  = 2026
TODAY = date.today().isoformat()
BASE  = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'

# Season pace multiplier — project current counting stats to full 183-day season
SEASON_START = date(YEAR, 3, 23)
days_played  = max(1, (date.today() - SEASON_START).days)
PACE_MULT    = 183 / days_played

# ── FanGraphs Closer Role Data ─────────────────────────────────────────────────
# Used to replace frozen preseason ProjSVHD with actual role signal from FanGraphs
# Roster Resource. Closers/Co-Closers/Closer Committees are the only RPs that
# reliably accumulate SVHD; Setup Men are included as a secondary tier.
CLOSER_ROLES = {'Closer', 'Co-Closer', 'Closer Committee', 'Setup Man'}

_fg_csv = os.path.join(BASE, f'closer_depth_fangraphs_{YEAR}.csv')
fg_role_lookup = {}   # lowercase player_name -> role string
_fg_max_date   = 'N/A'
if os.path.exists(_fg_csv):
    with open(_fg_csv, 'r', encoding='utf-8') as _fgf:
        _fg_rows = list(csv.DictReader(_fgf))
    if _fg_rows:
        _fg_max_date = max(r['date_scraped'] for r in _fg_rows)
        for _fgr in _fg_rows:
            if _fgr['date_scraped'] == _fg_max_date:
                fg_role_lookup[_fgr['player_name'].lower()] = _fgr['role']

def get_fg_role(name):
    """Return the FanGraphs projected role for a pitcher, or '' if not found."""
    return fg_role_lookup.get((name or '').lower(), '')

def svhd_rate(stats_dict):
    """Return SVHD per game (YTD actual rate). Returns 0.0 if no games played."""
    g    = (stats_dict or {}).get('G', 0) or 0
    svhd = (stats_dict or {}).get('SVHD', 0) or 0
    return svhd / g if g > 0 else 0.0

# Category thresholds for 5-cat scoring (0–5 scale)
CAT_THRESHOLDS = {'r': 60, 'hr': 15, 'rbi': 55, 'sb': 10, 'ops': 0.750}

# Z-score analysis config (28-day window, league-wide normalization)
EVAL_WINDOW      = 28
WEAK_Z_THRESH    = -0.3
DROP_Z_THRESH    = -0.5
FA_MIN_Z_GAMES   = 5
MIN_BAT_WIN_GP   = 10
MIN_PITCH_WIN_GP = 3
BAT_Z_CATS       = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCH_Z_CATS     = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
LOWER_BETTER_Z   = {'ERA', 'WHIP'}

# ── League init ───────────────────────────────────────────────────────────────
config      = mp.load_config()
league      = mp.setup_league(config, year=YEAR)
league_prev = mp.setup_league(config, year=YEAR - 1)
my_team_id  = int(config['BASEBALL']['BB_MY_TEAM_ID'])
my_team_obj = next(t for t in league.teams if t.team_id == my_team_id)
my_roster   = my_team_obj.roster

print(f'Team: {my_team_obj.team_name}')
print(f'Season pace: {days_played} days played, mult={PACE_MULT:.3f}x')

# ── Classify roster ───────────────────────────────────────────────────────────
hitter_slots = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'}
my_batters = [p for p in my_roster if not mp.is_pitcher(p)]
my_sps     = [p for p in my_roster if 'SP' in p.eligibleSlots
              and not any(s in hitter_slots for s in p.eligibleSlots)]
my_rps     = [p for p in my_roster if 'RP' in p.eligibleSlots
              and 'SP' not in p.eligibleSlots
              and not any(s in hitter_slots for s in p.eligibleSlots)]

# ── Load CSVs ─────────────────────────────────────────────────────────────────
with open(os.path.join(BASE, f'stats_mlb_boxscore_{YEAR}.csv'), encoding='utf-8') as f:
    mlb_rows = list(csv.DictReader(f))
batter_rows  = [r for r in mlb_rows if r['b_or_p'] == 'batter']
pitcher_rows = [r for r in mlb_rows if r['b_or_p'] == 'pitcher']

with open(os.path.join(BASE, f'lineups_mlb_batters_{YEAR}.csv'), encoding='utf-8') as f:
    all_lineups = list(csv.DictReader(f))

rank_lookup = {}
_rank_path = os.path.join(BASE, f'rankings_espn_daily_{YEAR}.csv')
if os.path.exists(_rank_path):
    with open(_rank_path, encoding='utf-8') as f:
        _rank_rows = list(csv.DictReader(f))
    if _rank_rows:
        _latest_rank = max(r['date'] for r in _rank_rows)
        for r in _rank_rows:
            if r['date'] == _latest_rank:
                rank_lookup[mp.normalize_player_name(r['player_name'])] = r

# ── Aggregation helpers ───────────────────────────────────────────────────────
def agg_batter(name):
    norm = mp.normalize_player_name(name)
    rows = [r for r in batter_rows if mp.normalize_player_name(r['player_name']) == norm]
    if not rows:
        return None
    def i(k): return sum(int(r[k]) for r in rows if r.get(k) not in ('', None))
    g=i('G'); ab=i('AB'); h=i('H'); r=i('R'); hr=i('HR'); rbi=i('RBI')
    sb=i('SB'); bb=i('B_BB'); so=i('SO'); hbp=i('HBP'); sf=i('SF'); tb=i('TB')
    avg = h/ab if ab else 0
    obp = (h+bb+hbp)/(ab+bb+hbp+sf) if (ab+bb+hbp+sf) else 0
    slg = tb/ab if ab else 0
    return dict(G=g, AB=ab, H=h, R=r, HR=hr, RBI=rbi, SB=sb, BB=bb,
                SO=so, AVG=avg, OBP=obp, SLG=slg, OPS=obp+slg)

def agg_pitcher(name):
    norm = mp.normalize_player_name(name)
    rows = [r for r in pitcher_rows if mp.normalize_player_name(r['player_name']) == norm]
    if not rows:
        return None
    def i(k): return sum(int(r[k]) for r in rows if r.get(k) not in ('', None))
    g=i('G'); gs=i('GS'); outs=i('OUTS'); er=i('ER')
    ph=i('P_H'); pbb=i('P_BB'); k=i('K'); qs=i('QS'); sv=i('SV'); hld=i('HLD')
    ip   = outs / 3
    era  = (er * 27) / outs  if outs else 0
    whip = (ph + pbb) / ip   if ip   else 0
    k9   = (k * 27) / outs   if outs else 0
    return dict(G=g, GS=gs, IP=round(ip,1), OUTS=outs, ER=er,
                ERA=round(era,2), WHIP=round(whip,2), K9=round(k9,2),
                QS=qs, SV=sv, HLD=hld, SVHD=sv+hld, P_H=ph, P_BB=pbb, K=k)

def proj_bd(player):
    try: return player.stats[0].get('projected_breakdown', {}) or {}
    except: return {}

def prev_stat(name, key):
    try:
        norm = mp.normalize_player_name(name)
        p = next((x for t in league_prev.teams for x in t.roster
                  if mp.normalize_player_name(x.name) == norm), None)
        if p: return (p.stats[0].get('breakdown', {}) or {}).get(key)
    except: pass
    return None

def player_status(p):
    """Return (on_il: bool, status_str: str) for a roster player."""
    inj   = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    # ESPN DL designations: TEN_DAY_DL, FIFTEEN_DAY_DL, SIXTY_DAY_DL, INJURY_RESERVE
    on_il = 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION')
    if on_il:
        return True, '[IL]'
    if inj == 'DAY_TO_DAY':
        return False, 'DTD'
    if inj not in ('ACTIVE', ''):
        return False, inj
    return False, 'Active'

# ── Batting order (last 7 days) ───────────────────────────────────────────────
cutoff_7  = (date.today() - timedelta(days=7)).isoformat()
recent_7  = [r for r in all_lineups if r['date'] >= cutoff_7]

def batting_order_stats(name):
    norm = mp.normalize_player_name(name)
    positions = []
    for r in recent_7:
        if mp.normalize_player_name(r['player_name']) == norm:
            try: positions.append(int(r['batting_order']))
            except: pass
    if not positions:
        return None, 0
    return round(sum(positions) / len(positions), 1), len(positions)

def get_rank(name):
    r = rank_lookup.get(mp.normalize_player_name(name), {})
    pr  = r.get('position_rank', '')
    p30 = r.get('pr30', '')
    pos_rank = int(pr)          if pr  not in ('', '0', None) else None
    pr30     = float(p30)       if p30 not in ('', None)      else None
    return pos_rank, pr30

# ── Lineup presence index (last 14 days) — used to filter FA batters ─────────
cutoff_14  = (date.today() - timedelta(days=14)).isoformat()
lu_presence = {}
for r in all_lineups:
    if r['date'] >= cutoff_14:
        norm = mp.normalize_player_name(r['player_name'])
        lu_presence[norm] = lu_presence.get(norm, 0) + 1

# ── BATTER TABLE ──────────────────────────────────────────────────────────────
print('\n=== BATTER STATS (sorted by OPS) ===')
hdr = f"{'Player':<25} {'Pos':<5} {'G':>4} {'AB':>4} {'R':>4} {'HR':>4} {'RBI':>4} {'SB':>4} {'OPS':>6} {'AVG':>6} {'AvgBO':>6} {'ProjOPS':>8} {'PrevOPS':>8} {'PRank':>6} {'PR30':>6} {'Status':<10}  Flags"
print(hdr); print('-'*len(hdr))

batter_data = []
for p in my_batters:
    s         = agg_batter(p.name)
    pb        = proj_bd(p)
    proj_ops  = pb.get('OPS')
    prev_ops  = prev_stat(p.name, 'OPS')
    avg_bo, bo_games = batting_order_stats(p.name)
    on_il, status    = player_status(p)
    pos_rank, pr30   = get_rank(p.name)

    ops = s['OPS'] if s else 0
    avg = s['AVG'] if s else 0
    r_  = s['R']   if s else 0
    hr_ = s['HR']  if s else 0
    rbi = s['RBI'] if s else 0
    sb  = s['SB']  if s else 0
    g   = s['G']   if s else 0
    ab  = s['AB']  if s else 0

    flags = []
    if not on_il:  # only flag active players
        if ops < 0.650: flags.append('LOW_OPS')
        if avg < 0.180: flags.append('LOW_AVG')
        if hr_ == 0 and rbi == 0 and sb == 0: flags.append('NO_CATS')
        if avg_bo and avg_bo >= 7: flags.append('BURIED_BO')
        if bo_games == 0: flags.append('NOT_IN_LINEUP')

    pos   = p.eligibleSlots[0] if p.eligibleSlots else '?'
    bo_s  = f'{avg_bo:.1f}' if avg_bo else 'N/A'
    pr_s  = f'{proj_ops:.3f}' if proj_ops else 'N/A'
    pv_s  = f'{prev_ops:.3f}' if prev_ops else 'N/A'
    rk_s  = f'#{pos_rank}' if pos_rank else 'N/A'
    p30_s = f'{pr30:+.1f}' if pr30 is not None else 'N/A'
    print(f'{p.name:<25} {pos:<5} {g:>4} {ab:>4} {r_:>4} {hr_:>4} {rbi:>4} {sb:>4} {ops:>6.3f} {avg:>6.3f} {bo_s:>6} {pr_s:>8} {pv_s:>8} {rk_s:>6} {p30_s:>6} {status:<10}  {", ".join(flags)}')
    batter_data.append(dict(player=p, stats=s, ops=ops, avg=avg, flags=flags,
                            avg_bo=avg_bo, bo_games=bo_games, proj_ops=proj_ops,
                            prev_ops=prev_ops, on_il=on_il, status=status,
                            pos_rank=pos_rank, pr30=pr30))

batter_data.sort(key=lambda x: x['ops'], reverse=True)

# ── SP TABLE ──────────────────────────────────────────────────────────────────
print('\n=== SP STATS (sorted by ERA) ===')
hdr = f"{'Player':<25} {'G':>4} {'GS':>4} {'IP':>6} {'ERA':>6} {'WHIP':>6} {'K/9':>6} {'QS':>4} {'SVHD':>5} {'ProjERA':>8} {'PrevERA':>8} {'PRank':>6} {'PR30':>6} {'Status':<10}  Flags"
print(hdr); print('-'*len(hdr))

sp_data = []
for p in my_sps:
    s        = agg_pitcher(p.name)
    pb       = proj_bd(p)
    proj_era = pb.get('ERA')
    prev_era = prev_stat(p.name, 'ERA')
    on_il, status    = player_status(p)
    pos_rank, pr30   = get_rank(p.name)
    flags = []
    if s and not on_il:
        if s['ERA']  > 5.0:  flags.append('HIGH_ERA')
        if s['WHIP'] > 1.50: flags.append('HIGH_WHIP')
        if s['K9']   < 6.0 and s['IP'] > 5: flags.append('LOW_K9')
        if s['GS'] > 0 and s['QS'] / s['GS'] < 0.40: flags.append('LOW_QS_RATE')
    elif not s:
        flags.append('NO_DATA')
    pe   = f'{proj_era:.2f}' if proj_era else 'N/A'
    pv   = f'{prev_era:.2f}' if prev_era else 'N/A'
    rk_s = f'#{pos_rank}' if pos_rank else 'N/A'
    p30_s= f'{pr30:+.1f}' if pr30 is not None else 'N/A'
    if s:
        print(f"{p.name:<25} {s['G']:>4} {s['GS']:>4} {s['IP']:>6.1f} {s['ERA']:>6.2f} {s['WHIP']:>6.2f} {s['K9']:>6.2f} {s['QS']:>4} {s['SVHD']:>5} {pe:>8} {pv:>8} {rk_s:>6} {p30_s:>6} {status:<10}  {', '.join(flags)}")
    else:
        print(f'{p.name:<25}  NO DATA  {status}')
    sp_data.append(dict(player=p, stats=s, flags=flags, proj_era=proj_era,
                        prev_era=prev_era, on_il=on_il, status=status,
                        pos_rank=pos_rank, pr30=pr30))

sp_data.sort(key=lambda x: x['stats']['ERA'] if x['stats'] else 99)

# ── RP TABLE ──────────────────────────────────────────────────────────────────
print('\n=== RP STATS (sorted by ProjSVHD) ===')
hdr = f"{'Player':<25} {'G':>4} {'IP':>6} {'ERA':>6} {'WHIP':>6} {'K/9':>6} {'SV':>4} {'HLD':>4} {'SVHD':>5} {'ProjSVHD':>9} {'ProjERA':>8} {'PRank':>6} {'PR30':>6} {'Status':<10}  Flags"
print(hdr); print('-'*len(hdr))

rp_data = []
for p in my_rps:
    s         = agg_pitcher(p.name)
    pb        = proj_bd(p)
    proj_svhd = pb.get('SVHD')
    proj_era  = pb.get('ERA')
    on_il, status  = player_status(p)
    pos_rank, pr30 = get_rank(p.name)
    flags = []
    if s and not on_il:
        if s['ERA']  > 5.0:  flags.append('HIGH_ERA')
        if s['WHIP'] > 1.50: flags.append('HIGH_WHIP')
        # Flag if no active closer role AND low YTD SVHD production rate
        if get_fg_role(p.name) not in CLOSER_ROLES and svhd_rate(s) < 0.2:
            flags.append('LOW_SVHD_CEIL')
    elif not s:
        flags.append('NO_DATA')
    ps   = f'{proj_svhd:.0f}' if proj_svhd else 'N/A'
    pe   = f'{proj_era:.2f}'  if proj_era  else 'N/A'
    rk_s = f'#{pos_rank}' if pos_rank else 'N/A'
    p30_s= f'{pr30:+.1f}' if pr30 is not None else 'N/A'
    if s:
        print(f"{p.name:<25} {s['G']:>4} {s['IP']:>6.1f} {s['ERA']:>6.2f} {s['WHIP']:>6.2f} {s['K9']:>6.2f} {s['SV']:>4} {s['HLD']:>4} {s['SVHD']:>5} {ps:>9} {pe:>8} {rk_s:>6} {p30_s:>6} {status:<10}  {', '.join(flags)}")
    else:
        print(f'{p.name:<25}  NO DATA  {status}')
    rp_data.append(dict(player=p, stats=s, flags=flags, proj_svhd=proj_svhd,
                        proj_era=proj_era, on_il=on_il, status=status,
                        pos_rank=pos_rank, pr30=pr30))

rp_data.sort(key=lambda x: (
    -svhd_rate(x['stats']),                          # SVHD/G rate desc (actual YTD production)
    x['stats']['ERA'] if x['stats'] else 99          # tiebreak: ERA asc
))

# ── Weakest players ───────────────────────────────────────────────────────────
print('\n=== WEAKEST PLAYERS ===')
weak_batters = [b for b in batter_data if b['flags']]
weak_sps     = [s for s in sp_data     if s['flags']]
weak_rps     = [r for r in rp_data     if r['flags']]

print(f'\nWeak Batters ({len(weak_batters)}):')
for b in weak_batters:
    print(f"  {b['player'].name:<25} OPS={b['ops']:.3f}  status={b['status']}  flags={b['flags']}")

print(f'\nWeak SPs ({len(weak_sps)}):')
for s in weak_sps:
    era = s['stats']['ERA'] if s['stats'] else 'N/A'
    print(f"  {s['player'].name:<25} ERA={era}  status={s['status']}  flags={s['flags']}")

print(f'\nWeak RPs ({len(weak_rps)}):')
for r in weak_rps:
    era = r['stats']['ERA']  if r['stats'] else 'N/A'
    ps  = f"{r['proj_svhd']:.0f}" if r['proj_svhd'] else 'N/A'
    print(f"  {r['player'].name:<25} ERA={era}  ProjSVHD={ps}  status={r['status']}  flags={r['flags']}")

# ── QL Slot Competition ───────────────────────────────────────────────────────
print('\n=== QL SLOT COMPETITION ===')
print('Players ranked by ESPN position_rank within each slot group (lower = better).')
print('* = top-ranked (QL will start).  ⚠ = ranked below a worse-performing teammate.\n')

_OF_SLOTS = {'OF', 'LF', 'CF', 'RF'}
_ql_groups = {}

for _b in batter_data:
    _pos = _b['player'].eligibleSlots[0] if _b['player'].eligibleSlots else '?'
    _grp = 'OF' if _pos in _OF_SLOTS else _pos
    if _grp in ('C','1B','2B','3B','SS','OF','DH'):
        _ql_groups.setdefault(_grp, []).append(('BAT', _b))

for _s in sp_data:
    _ql_groups.setdefault('SP', []).append(('SP', _s))

for _r in rp_data:
    _ql_groups.setdefault('RP', []).append(('RP', _r))

ql_manual_overrides = []

for _grp in ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'SP', 'RP']:
    _players = _ql_groups.get(_grp, [])
    if len(_players) < 2:
        continue

    _sorted = sorted(_players, key=lambda x: (
        1 if x[1]['on_il'] else 0,
        x[1].get('pos_rank') or 9999
    ))

    _active = [(t, d) for t, d in _sorted if not d['on_il']]
    if not _active:
        continue

    print(f'  {_grp}  ({len(_players)} rostered, {len(_active)} active):')

    for _i, (_ptype, _pdata) in enumerate(_sorted):
        _name  = _pdata['player'].name
        _pr    = _pdata.get('pos_rank')
        _pr30  = _pdata.get('pr30')
        _rk_s  = f'#{_pr}' if _pr else 'N/A'
        _p30_s = f'PR30={_pr30:+.1f}' if _pr30 is not None else 'PR30=N/A'
        _il_s  = ' [IL]' if _pdata['on_il'] else ''

        if _ptype == 'BAT':
            _stat_s = f"OPS={_pdata['ops']:.3f}"
        elif _ptype == 'SP':
            _st = _pdata['stats']
            _stat_s = f"ERA={_st['ERA']:.2f}  QS={_st['QS']}" if _st else 'no data'
        else:
            _st = _pdata['stats']
            _ps = _pdata.get('proj_svhd') or 0
            _stat_s = f"ProjSVHD={_ps:.0f}  ERA={_st['ERA']:.2f}" if _st else 'no data'

        _flag = ''
        if not _pdata['on_il']:
            _above = [(t, d) for t, d in _sorted[:_i] if not d['on_il']]
            for _at, _ad in _above:
                if _ptype == 'BAT' and _at == 'BAT':
                    if _pdata['ops'] > _ad['ops'] and _pdata['ops'] >= 0.700:
                        _flag = f'  ⚠ better OPS than {_ad["player"].name} (rank #{_ad.get("pos_rank")})'
                        ql_manual_overrides.append(dict(
                            group=_grp, player=_name, blocks=_ad['player'].name,
                            reason=f"OPS {_pdata['ops']:.3f} > {_ad['ops']:.3f} | rank #{_pr} vs #{_ad.get('pos_rank')}"
                        ))
                        break
                elif _ptype == 'SP' and _at == 'SP':
                    _st_a = _ad['stats']
                    if _pdata['stats'] and _st_a and _pdata['stats']['ERA'] < _st_a['ERA'] and _pdata['stats']['QS'] >= _st_a['QS']:
                        _flag = f'  ⚠ better ERA+QS than {_ad["player"].name} (rank #{_ad.get("pos_rank")})'
                        ql_manual_overrides.append(dict(
                            group=_grp, player=_name, blocks=_ad['player'].name,
                            reason=f"ERA {_pdata['stats']['ERA']:.2f} < {_st_a['ERA']:.2f} & QS {_pdata['stats']['QS']} >= {_st_a['QS']} | rank #{_pr} vs #{_ad.get('pos_rank')}"
                        ))
                        break
                elif _ptype == 'RP' and _at == 'RP':
                    _ps_a = _ad.get('proj_svhd') or 0
                    _st_a = _ad['stats']
                    _ps_me = _pdata.get('proj_svhd') or 0
                    _st_me = _pdata['stats']
                    if _ps_me > _ps_a and _st_me and _st_a and _st_me['ERA'] <= _st_a['ERA'] + 0.5:
                        _flag = f'  ⚠ better ProjSVHD than {_ad["player"].name} (rank #{_ad.get("pos_rank")})'
                        ql_manual_overrides.append(dict(
                            group=_grp, player=_name, blocks=_ad['player'].name,
                            reason=f"ProjSVHD {_ps_me:.0f} > {_ps_a:.0f} | rank #{_pr} vs #{_ad.get('pos_rank')}"
                        ))
                        break

        _star = '*' if (_i == 0 and not _pdata['on_il']) else ' '
        print(f"    {_star} {_name:<25} rank={_rk_s:<6}  {_p30_s:<14}  {_stat_s}{_il_s}{_flag}")

    print()

if ql_manual_overrides:
    print('  --- Manual Override Summary ---')
    for _item in ql_manual_overrides:
        print(f"  ⚠ {_item['group']:>3}: START {_item['player']} over {_item['blocks']} — {_item['reason']}")
    print()

# ── Free agents ───────────────────────────────────────────────────────────────
print('\n=== TOP FREE AGENTS ===')

def cat_score_fa(fa):
    """Score a FA batter on 5-cat thresholds using pace projections; return (score, pR, pHR, pRBI, pSB)."""
    pr   = int((fa.get('r',   0) or 0) * PACE_MULT)
    phr  = int((fa.get('hr',  0) or 0) * PACE_MULT)
    prbi = int((fa.get('rbi', 0) or 0) * PACE_MULT)
    psb  = int((fa.get('sb',  0) or 0) * PACE_MULT)
    ops  = fa.get('ops', 0) or 0
    score = ((pr   >= CAT_THRESHOLDS['r'])   +
             (phr  >= CAT_THRESHOLDS['hr'])  +
             (prbi >= CAT_THRESHOLDS['rbi']) +
             (psb  >= CAT_THRESHOLDS['sb'])  +
             (ops  >= CAT_THRESHOLDS['ops']))
    return score, pr, phr, prbi, psb

# FA batters — filter injured, not in lineups (14-day), enrich with pace/cat/composite
top_fa_batters_raw = mp.get_top_fa_batters(league, size=200, min_ab=10)
top_fa_batters = []
for fa in top_fa_batters_raw:
    inj = (fa.get('injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION'):
        continue
    norm     = mp.normalize_player_name(fa['name'])
    lu_games = lu_presence.get(norm, 0)
    if lu_games == 0:
        continue  # skip — not in any lineup last 14 days
    ops       = fa.get('ops',      0) or 0
    proj_ops  = fa.get('proj_ops', 0) or 0
    composite = 0.6 * ops + 0.4 * proj_ops
    score, pr, phr, prbi, psb = cat_score_fa(fa)
    fa_pos_rank, fa_pr30 = get_rank(fa['name'])
    top_fa_batters.append({**fa, 'composite': composite, 'cat_score': score,
                           'pace_r': pr, 'pace_hr': phr, 'pace_rbi': prbi,
                           'pace_sb': psb, 'lineup_games': lu_games,
                           'pos_rank': fa_pos_rank, 'pr30': fa_pr30})

top_fa_batters.sort(key=lambda x: (-x['cat_score'], -x['composite']))

# FA pitchers — split SP vs RP, filter injured
all_fa_pitchers_raw = mp.get_free_agents(league, position_ids=[14, 15], size=300)
# Dedup by name: the API call loops over position_ids [14, 15] separately, so
# pitchers with SP+RP eligibility appear twice in the combined list.
_seen_pit_names = set()
all_fa_pitchers = []
for _fp in all_fa_pitchers_raw:
    if _fp['name'] not in _seen_pit_names:
        _seen_pit_names.add(_fp['name'])
        all_fa_pitchers.append(_fp)

fa_sps_raw = [f for f in all_fa_pitchers if 'SP' in f.get('eligibleSlots', [])]
fa_rps_raw = [f for f in all_fa_pitchers
              if 'RP' in f.get('eligibleSlots', []) and 'SP' not in f.get('eligibleSlots', [])]

def fa_pitcher_stats(fa):
    s26 = (fa.get('stats') or {}).get('2026', {})
    p26 = (fa.get('stats') or {}).get('2026Projected', {})
    outs = s26.get('OUTS', 0) or 0
    er   = s26.get('ER',   0) or 0
    ph   = s26.get('P_H',  0) or 0
    pbb  = s26.get('P_BB', 0) or 0
    k    = s26.get('K',    0) or 0
    gp   = s26.get('GP',   0) or 0
    gs   = s26.get('GS',   0) or 0
    qs   = s26.get('QS',   0) or 0
    sv   = s26.get('SV',   0) or 0
    hld  = s26.get('HLD',  0) or 0
    ip   = outs / 3
    era  = (er * 27) / outs  if outs else 0
    whip = (ph + pbb) / ip   if ip   else 0
    k9   = (k * 27) / outs   if outs else 0
    return dict(G=int(gp), GS=int(gs), IP=round(ip, 1), ERA=round(era, 2),
                WHIP=round(whip, 2), K9=round(k9, 2), QS=int(qs),
                SV=int(sv), HLD=int(hld), SVHD=int(sv + hld),
                ProjERA=p26.get('ERA'), ProjSVHD=p26.get('SVHD'))

fa_sps = []
for fa in fa_sps_raw:
    inj = (fa.get('injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION'):
        continue
    s = fa_pitcher_stats(fa)
    if s['G'] < 1: continue
    fa_sps.append(dict(name=fa['name'], team=fa.get('proTeam', '?'),
                       eligibleSlots=fa.get('eligibleSlots', []), **s))
# Sort: qualified SPs (>=20 IP) by ERA first, then small-sample SPs by ERA.
# This prevents a 0.00 ERA / 2 IP pitcher from floating to the top of the list.
fa_sps.sort(key=lambda x: (0 if x['IP'] >= 20 else 1, x['ERA']))

fa_rps = []
for fa in fa_rps_raw:
    inj = (fa.get('injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION'):
        continue
    s = fa_pitcher_stats(fa)
    if s['G'] < 2: continue
    fa_rps.append(dict(name=fa['name'], team=fa.get('proTeam', '?'),
                       eligibleSlots=fa.get('eligibleSlots', []),
                       FGRole=get_fg_role(fa['name']), **s))
# Sort: active closer roles first, then by SVHD/G rate desc, tiebreak ERA asc.
# Replaces the old ProjSVHD sort which was frozen at draft and blind to mid-season
# breakouts (e.g., undrafted closers with ADP 260 had ProjSVHD=0 → invisible).
fa_rps.sort(key=lambda x: (
    0 if x['FGRole'] in CLOSER_ROLES else 1,   # closer-role players first
    -svhd_rate(x),                              # then SVHD/G rate desc
    x['ERA']                                    # tiebreak: ERA asc
))

print(f'\nTop FA Batters (top 20 by cat score + composite OPS, active, in lineups last 14d):')
print(f"  {'Name':<25} {'Pos':<6} {'OPS':>6} {'pR':>5} {'pHR':>5} {'pRBI':>6} {'pSB':>5} {'AB':>5} {'ProjOPS':>8} {'Comp':>6} {'Cat':>4} {'LU':>4} {'PRank':>6} {'PR30':>6}")
for fa in top_fa_batters[:20]:
    po    = fa.get('proj_ops')
    ps    = f'{po:.3f}' if po else 'N/A'
    rk_s  = f"#{fa['pos_rank']}" if fa.get('pos_rank') else 'N/A'
    p30_s = f"{fa['pr30']:+.1f}" if fa.get('pr30') is not None else 'N/A'
    print(f"  {fa['name']:<25} {fa.get('pos','?'):<6} {fa.get('ops',0):>6.3f} {fa['pace_r']:>5} {fa['pace_hr']:>5} {fa['pace_rbi']:>6} {fa['pace_sb']:>5} {int(fa.get('ab',0) or 0):>5} {ps:>8} {fa['composite']:>6.3f} {fa['cat_score']:>4} {fa['lineup_games']:>4} {rk_s:>6} {p30_s:>6}")

print(f'\nTop FA SPs (top 15 by ERA — qualified >=20 IP first, min 1 G, active only):')
print(f"  {'Name':<25} {'Team':<6} {'G':>4} {'IP':>6} {'ERA':>6} {'WHIP':>6} {'K/9':>6} {'QS':>4} {'ProjERA':>8}")
for fa in fa_sps[:15]:
    pe = f'{fa["ProjERA"]:.2f}' if fa['ProjERA'] else 'N/A'
    ip_flag = '' if fa['IP'] >= 20 else ' *'
    print(f"  {fa['name']:<25} {fa['team']:<6} {fa['G']:>4} {fa['IP']:>6.1f}{ip_flag} {fa['ERA']:>6.2f} {fa['WHIP']:>6.2f} {fa['K9']:>6.2f} {fa['QS']:>4} {pe:>8}")

print(f'\nTop FA RPs (top 20 by FG role + SVHD/G rate, min 2 G, active only):')
print(f"  {'Name':<25} {'Team':<6} {'G':>4} {'IP':>6} {'SV':>4} {'HLD':>4} {'SVHD':>5} {'SVHD/G':>7} {'ERA':>6} {'WHIP':>6} {'FG Role':<22} {'ProjERA':>8}")
for fa in fa_rps[:20]:
    sr   = svhd_rate(fa)
    sr_s = f'{sr:.2f}' if sr > 0 else '-'
    pe   = f'{fa["ProjERA"]:.2f}' if fa['ProjERA'] else 'N/A'
    fgr  = fa.get('FGRole', '')
    print(f"  {fa['name']:<25} {fa['team']:<6} {fa['G']:>4} {fa['IP']:>6.1f} {fa['SV']:>4} {fa['HLD']:>4} {fa['SVHD']:>5} {sr_s:>7} {fa['ERA']:>6.2f} {fa['WHIP']:>6.2f} {fgr:<22} {pe:>8}")

# ── Z-Score Analysis (ESPN daily stats — league-wide relative ranking) ────────
print('\nRunning z-score analysis...')
espn_daily_path = os.path.join(BASE, f'stats_espn_daily_{YEAR}.csv')
zdf = pd.read_csv(espn_daily_path, low_memory=False)
zdf['date'] = pd.to_datetime(zdf['date'])

for _c in ['R','HR','RBI','SB','OPS','QS','SVHD','K','OUTS','ER','P_BB','P_H','AB','HLD','SV']:
    if _c in zdf.columns:
        zdf[_c] = pd.to_numeric(zdf[_c], errors='coerce').fillna(0)

zdf['IP']         = zdf['OUTS'] / 3.0
zdf['is_pitcher'] = zdf['eligible_slots'].str.contains('SP|RP', na=False)

_GENERIC = {'BE', 'IL', 'UTIL', 'P', 'IF', 'DH'}
def _parse_slots(s):
    if pd.isna(s): return set()
    return {x.strip() for x in str(s).split('|')} - _GENERIC

slot_map_z = (
    zdf.groupby('player_name')['eligible_slots']
    .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else '')
    .apply(_parse_slots)
)

latest_z       = zdf['date'].max()
window_start_z = latest_z - timedelta(days=EVAL_WINDOW)

current_z      = (zdf[zdf['date'] == latest_z]
                  [['player_name','team_name','lineup_slot','is_pitcher']]
                  .drop_duplicates('player_name'))
all_rostered_z = set(current_z['player_name'].unique())

def _agg_z(data):
    bat = data[~data['is_pitcher']].copy()
    pit = data[ data['is_pitcher']].copy()
    bat['_played'] = bat['AB']   > 0
    pit['_played'] = pit['OUTS'] > 0

    bat_agg = bat.groupby('player_name').agg(
        games       =('date',    'nunique'),
        games_played=('_played', 'sum'),
        R =('R','sum'), HR=('HR','sum'), RBI=('RBI','sum'), SB=('SB','sum'),
        _ops_w=('OPS', lambda x: (x * bat.loc[x.index,'AB']).sum()),
        _ab   =('AB','sum'),
    ).reset_index()
    bat_agg['OPS'] = bat_agg['_ops_w'] / bat_agg['_ab'].replace(0, np.nan)
    bat_agg['is_pitcher'] = False
    bat_agg.drop(columns=['_ops_w','_ab'], inplace=True)

    pit_agg = pit.groupby('player_name').agg(
        games       =('date',    'nunique'),
        games_played=('_played', 'sum'),
        QS  =('QS','sum'),  SVHD=('SVHD','sum'), IP=('IP','sum'),
        K   =('K','sum'),   ER  =('ER','sum'),
        _BB =('P_BB','sum'), _H =('P_H','sum'),
    ).reset_index()
    pit_agg['K/9']  = (pit_agg['K']  * 9) / pit_agg['IP'].replace(0, np.nan)
    pit_agg['ERA']  = (pit_agg['ER'] * 9) / pit_agg['IP'].replace(0, np.nan)
    pit_agg['WHIP'] = (pit_agg['_BB'] + pit_agg['_H']) / pit_agg['IP'].replace(0, np.nan)
    pit_agg['is_pitcher'] = True
    pit_agg.drop(columns=['K','ER','_BB','_H'], inplace=True)
    return bat_agg, pit_agg

def _add_z(agg_df, cats):
    for cat in cats:
        if cat not in agg_df.columns: continue
        col = agg_df[cat].copy()
        mean = col.mean(); std = col.std()
        if pd.isna(std) or std == 0: std = 1
        z = (col - mean) / std
        if cat in LOWER_BETTER_Z: z = -z
        agg_df[f'z_{cat}'] = z.fillna(0)
    z_cols = [f'z_{c}' for c in cats if f'z_{c}' in agg_df.columns]
    agg_df['z_total'] = agg_df[z_cols].sum(axis=1)
    return agg_df

ssn_bat, ssn_pit = _agg_z(zdf)
win_bat, win_pit = _agg_z(zdf[zdf['date'] >= window_start_z])
ssn_bat = _add_z(ssn_bat, BAT_Z_CATS);   ssn_pit = _add_z(ssn_pit, PITCH_Z_CATS)
win_bat = _add_z(win_bat, BAT_Z_CATS);   win_pit = _add_z(win_pit, PITCH_Z_CATS)

def _get_z_profile(name, is_pit):
    sd, wd = (ssn_pit, win_pit) if is_pit else (ssn_bat, win_bat)
    cats   = PITCH_Z_CATS if is_pit else BAT_Z_CATS
    sr = sd[sd['player_name'] == name]
    wr = wd[wd['player_name'] == name]
    out = {
        'season_z':  round(float(sr['z_total'].values[0]), 2) if not sr.empty else 0.0,
        'window_z':  round(float(wr['z_total'].values[0]), 2) if not wr.empty else 0.0,
        'season_gp': int(sr['games_played'].values[0]) if not sr.empty else 0,
        'window_gp': int(wr['games_played'].values[0]) if not wr.empty else 0,
    }
    for cat in cats:
        if not sr.empty and f'z_{cat}' in sr.columns:
            out[f'sz_{cat}'] = round(float(sr[f'z_{cat}'].values[0]), 2)
        if not wr.empty and f'z_{cat}' in wr.columns:
            out[f'wz_{cat}'] = round(float(wr[f'z_{cat}'].values[0]), 2)
    return out

z_profiles = []
for _zr in current_z[current_z['team_name'] == my_team_obj.team_name].itertuples():
    p = _get_z_profile(_zr.player_name, _zr.is_pitcher)
    p.update({'player_name': _zr.player_name, 'is_pitcher': _zr.is_pitcher,
              'lineup_slot': _zr.lineup_slot})
    z_profiles.append(p)
z_df = pd.DataFrame(z_profiles) if z_profiles else pd.DataFrame()

# Flag by z-score criteria
z_flagged = []
if not z_df.empty:
    for _, _zr in z_df.iterrows():
        if _zr['lineup_slot'] == 'IL': continue
        min_gp = MIN_PITCH_WIN_GP if _zr['is_pitcher'] else MIN_BAT_WIN_GP
        if (_zr['window_z'] < DROP_Z_THRESH or
                (_zr['window_z'] < WEAK_Z_THRESH and _zr['season_z'] < WEAK_Z_THRESH)):
            reason = ('Drop candidate' if _zr['window_z'] < DROP_Z_THRESH
                      else 'Underperforming')
            if _zr['window_gp'] < min_gp:
                reason = f"Low sample ({int(_zr['window_gp'])}/{min_gp} games in 28d)"
            z_flagged.append({**_zr.to_dict(), 'flag_reason': reason})

# FA pool for z-score recommendations
fa_bat_z = ssn_bat[
    ~ssn_bat['player_name'].isin(all_rostered_z) & (ssn_bat['games'] >= FA_MIN_Z_GAMES)
].copy()
fa_pit_z = ssn_pit[
    ~ssn_pit['player_name'].isin(all_rostered_z) & (ssn_pit['games'] >= FA_MIN_Z_GAMES)
].copy()
fa_bat_z['eligible_slots'] = fa_bat_z['player_name'].map(slot_map_z)
fa_pit_z['eligible_slots'] = fa_pit_z['player_name'].map(slot_map_z)

def _best_fa_z(player_name, is_pit, n=3):
    pool   = fa_pit_z if is_pit else fa_bat_z
    p_slots = slot_map_z.get(player_name, set())
    cands  = pool.copy()
    cands['_ov'] = cands['eligible_slots'].apply(
        lambda s: len(p_slots & s) if isinstance(s, set) else 0)
    matched = cands[cands['_ov'] > 0]
    if matched.empty: matched = cands
    return matched.sort_values('z_total', ascending=False).head(n)

print(f'Z-score analysis complete: {len(z_flagged)} player(s) flagged')

# ── 8A: Position-matched replacements ────────────────────────────────────────
print('\n=== 8A: POSITION-MATCHED REPLACEMENTS ===')

pos_compat = {
    'C':  {'C'},
    '1B': {'1B', 'DH'},
    '3B': {'3B', '1B'},
    '2B': {'2B', 'SS'},
    'SS': {'SS', '2B'},
    'OF': {'OF', 'LF', 'CF', 'RF'},
    'LF': {'OF', 'LF', 'CF', 'RF'},
    'CF': {'OF', 'LF', 'CF', 'RF'},
    'RF': {'OF', 'LF', 'CF', 'RF'},
    'DH': {'DH', '1B', 'OF', 'LF', 'CF', 'RF'},
}

recs_8a_batters = []
for b in weak_batters:
    p     = b['player']
    if not b['stats'] or b['stats']['AB'] < 5: continue
    p_pos = p.eligibleSlots[0] if p.eligibleSlots else '?'
    compat = pos_compat.get(p_pos, {p_pos})
    candidates = []
    for fa in top_fa_batters:
        if fa.get('pos', '?') not in compat: continue
        if int(fa.get('ab', 0) or 0) < 10: continue
        if (fa.get('ops', 0) or 0) < 0.700: continue  # minimum OPS threshold
        imp = (fa.get('ops', 0) or 0) - b['ops']
        if imp >= 0.100:
            candidates.append((fa, imp))
    candidates.sort(key=lambda x: (-x[0]['cat_score'], -x[0]['composite']))
    if candidates:
        fa, imp = candidates[0]
        fa_ops = fa.get('ops', 0) or 0
        small  = ' (small sample)' if int(fa.get('ab', 0) or 0) < 15 else ''
        print(f"  DROP {p.name:<22} ({b['ops']:.3f} OPS, {p_pos}, {b['status']})  ADD {fa['name']:<22} ({fa_ops:.3f} OPS, {imp:+.3f}){small}")
        recs_8a_batters.append(dict(drop=p.name, drop_status=b['status'], add=fa['name'],
                                    slot=p_pos, ops_delta=imp, cat_score=fa['cat_score'],
                                    pace_r=fa['pace_r'], pace_hr=fa['pace_hr'],
                                    pace_rbi=fa['pace_rbi'], pace_sb=fa['pace_sb']))

recs_8a_sps = []
for s in weak_sps:
    p = s['player']
    if not s['stats']: continue
    # Sort by QS desc → WHIP asc → ERA asc (per league priorities)
    candidates = [fa for fa in fa_sps if fa['IP'] >= 5]
    candidates.sort(key=lambda x: (-x['QS'], x['WHIP'], x['ERA']))
    if candidates:
        fa = candidates[0]
        print(f"  DROP {p.name:<22} (ERA {s['stats']['ERA']:.2f}, QS {s['stats']['QS']}, {s['status']})  ADD {fa['name']:<22} (QS {fa['QS']}, WHIP {fa['WHIP']:.2f}, ERA {fa['ERA']:.2f})")
        recs_8a_sps.append(dict(drop=p.name, drop_status=s['status'], add=fa['name'],
                                era_delta=fa['ERA'] - s['stats']['ERA'],
                                whip=fa['WHIP'], k9=fa['K9'], qs=fa['QS']))

recs_8a_rps = []
for r in weak_rps:
    p = r['player']
    if not r['stats']: continue
    my_svhd_g = svhd_rate(r['stats'])
    # Filter: FA must have an active closer role (Closer / Co-Closer / Closer Committee
    # / Setup Man). Sort by SVHD/G rate desc → WHIP asc → ERA asc.
    # Replaces old ProjSVHD hard-filter which blocked undrafted mid-season closers.
    candidates = []
    for fa in fa_rps:
        if fa['FGRole'] not in CLOSER_ROLES: continue
        fa_svhd_g  = svhd_rate(fa)
        pace_svhd  = round(fa['SVHD'] * PACE_MULT, 1)
        candidates.append((fa, fa_svhd_g, fa['SVHD'], pace_svhd, fa['WHIP'], fa['ERA']))
    candidates.sort(key=lambda x: (-x[1], x[4], x[5]))
    if candidates:
        fa_d, fa_svhd_g, fa_svhd, pace_svhd, fa_whip, fa_era = candidates[0]
        print(f"  DROP {p.name:<22} (SVHD/G={my_svhd_g:.2f}, {r['status']})  "
              f"ADD {fa_d['name']:<22} (Role={fa_d['FGRole']}, SVHD/G={fa_svhd_g:.2f}, "
              f"SVHD={fa_svhd}, Pace={pace_svhd:.0f}, WHIP={fa_whip:.2f})")
        recs_8a_rps.append(dict(drop=p.name, drop_status=r['status'], add=fa_d['name'],
                                fg_role=fa_d['FGRole'], svhd_per_g=round(fa_svhd_g, 3),
                                curr_svhd=fa_svhd, pace_svhd=pace_svhd, whip=fa_whip,
                                era_delta=round(fa_era - (r['stats']['ERA'] if r['stats'] else 0), 2)))

# ── 8B: Position-agnostic replacements ───────────────────────────────────────
print('\n=== 8B: POSITION-AGNOSTIC REPLACEMENTS ===')

# Drop pool: all active flagged players across all positions, worst first
active_flagged = sorted(
    [dict(d, drop_type='BAT') for d in weak_batters if not d['on_il']] +
    [dict(d, drop_type='SP')  for d in weak_sps     if not d['on_il']] +
    [dict(d, drop_type='RP')  for d in weak_rps     if not d['on_il']],
    key=lambda x: len(x['flags']), reverse=True
)

# FA pool: qualifying FAs across all positions, sorted by impact
fa_bat_ok = [fa for fa in top_fa_batters
             if int(fa.get('ab', 0) or 0) >= 10 and (fa.get('ops', 0) or 0) >= 0.700]
fa_sp_ok  = [fa for fa in fa_sps if fa['IP'] >= 5]
# 8B RP pool: restrict to active closer roles (same logic as 8A) and sort by
# SVHD/G rate. ProjSVHD is frozen at draft; SVHD/G reflects current production.
fa_rp_ok  = [fa for fa in fa_rps if fa['FGRole'] in CLOSER_ROLES]
fa_rp_ok  = sorted(fa_rp_ok, key=lambda x: (
    -svhd_rate(x),
    x.get('WHIP', 9), x.get('ERA', 99)
))

fa_all = (
    [('BAT', fa, fa['cat_score'],   fa.get('composite', 0))   for fa in fa_bat_ok] +
    [('SP',  fa, 0,                 -(fa.get('ERA', 99)))      for fa in fa_sp_ok] +
    [('RP',  fa, 0,                  svhd_rate(fa))            for fa in fa_rp_ok]
)
fa_all.sort(key=lambda x: (-x[2], -x[3]))

agnostic_moves = []
seen_adds  = set()
seen_drops = set()

for drop_data in active_flagged[:6]:
    drop_name = drop_data['player'].name
    if drop_name in seen_drops:
        continue
    best = next((fa for fa in fa_all if fa[1]['name'] not in seen_adds), None)
    if not best:
        break
    fa_type, fa_obj, cat_score, _ = best

    if fa_type == 'BAT':
        cats = []
        if int(fa_obj.get('r',   0) or 0) >= 15: cats.append(f"+R({int(fa_obj['r'])})")
        if int(fa_obj.get('hr',  0) or 0) >= 5:  cats.append(f"+HR({int(fa_obj['hr'])})")
        if int(fa_obj.get('rbi', 0) or 0) >= 15: cats.append(f"+RBI({int(fa_obj['rbi'])})")
        if int(fa_obj.get('sb',  0) or 0) >= 3:  cats.append(f"+SB({int(fa_obj['sb'])})")
        cats.append(f"+OPS({fa_obj['ops']:.3f})")
        impact    = ', '.join(cats)
        svhd_lost = drop_data.get('proj_svhd') or 0
        composite = fa_obj.get('composite')
    elif fa_type == 'SP':
        impact    = f"ERA {fa_obj['ERA']:.2f}, WHIP {fa_obj.get('WHIP', 0):.2f}, QS {fa_obj.get('QS', 0)}"
        svhd_lost = drop_data.get('proj_svhd') or 0
        composite = None
    else:  # RP
        ps        = fa_obj.get('ProjSVHD') or 0
        impact    = f"+ProjSVHD({ps:.0f}), ERA {fa_obj.get('ERA', 0):.2f}, WHIP {fa_obj.get('WHIP', 0):.2f}"
        svhd_lost = 0
        composite = None

    print(f"  DROP {drop_name:<22} ({', '.join(drop_data['flags'])})  ADD {fa_obj['name']:<22} [{fa_type}] {impact}")
    agnostic_moves.append(dict(
        drop=drop_name, drop_type=drop_data['drop_type'], drop_status=drop_data['status'],
        drop_flags=drop_data['flags'],
        add=fa_obj['name'], add_type=fa_type,
        cat_score=cat_score, composite=composite,
        impact=impact, svhd_lost=svhd_lost
    ))
    seen_adds.add(fa_obj['name'])
    seen_drops.add(drop_name)

if agnostic_moves:
    bat_adds  = [m for m in agnostic_moves if m['add_type'] == 'BAT']
    rp_adds   = [m for m in agnostic_moves if m['add_type'] == 'RP']
    svhd_lost = sum(m['svhd_lost'] for m in bat_adds)
    print(f'\n  Combined scenario ({len(agnostic_moves)} swap(s)):')
    print(f'    Batter adds    : {len(bat_adds)} ({", ".join(m["add"] for m in bat_adds) or "none"})')
    print(f'    RP upgrades    : {len(rp_adds)} ({", ".join(m["add"] for m in rp_adds) or "none"})')
    print(f'    Proj SVHD lost : {svhd_lost:.0f} (from batter swaps)')

# ── Step 9: Markdown report ───────────────────────────────────────────────────
report_dir  = os.path.join(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball', 'reports')
os.makedirs(report_dir, exist_ok=True)
report_path = os.path.join(report_dir, f'roster_analysis_{TODAY}.md')

lines = []
lines.append(f'# Fantasy Roster Analysis — {TODAY}\n')
lines.append(f'**Team:** {my_team_obj.team_name}  \n**League:** 5x5 H2H Each Category  \n**Generated:** {TODAY}')
lines.append(f'\n> IL players are shown for completeness but excluded from active replacement priority.')
lines.append(f'> Season pace: {days_played} days played, pace multiplier = {PACE_MULT:.3f}x (projecting to 183-day season)\n')

# Batter table
lines.append('\n## My Roster — Batter Stats\n')
lines.append('| Player | Pos | G | AB | R | HR | RBI | SB | OPS | AVG | AvgBO | ProjOPS | PrevOPS | PRank | PR30 | Status | Flags |')
lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for b in sorted(batter_data, key=lambda x: x['ops'], reverse=True):
    s    = b['stats']
    pos  = b['player'].eligibleSlots[0] if b['player'].eligibleSlots else '?'
    bo_s = f"{b['avg_bo']:.1f}" if b['avg_bo'] else 'N/A'
    pr_s = f"{b['proj_ops']:.3f}" if b['proj_ops'] else 'N/A'
    pv_s = f"{b['prev_ops']:.3f}" if b.get('prev_ops') else 'N/A'
    rk_s = f"#{b['pos_rank']}" if b.get('pos_rank') else 'N/A'
    p30_s= f"{b['pr30']:+.1f}" if b.get('pr30') is not None else 'N/A'
    g_ = s['G'] if s else 0; ab_ = s['AB'] if s else 0; r_ = s['R'] if s else 0
    hr_= s['HR'] if s else 0; rbi_= s['RBI'] if s else 0; sb_= s['SB'] if s else 0
    flags = ', '.join(b['flags']) or '—'
    lines.append(f"| {b['player'].name} | {pos} | {g_} | {ab_} | {r_} | {hr_} | {rbi_} | {sb_} | {b['ops']:.3f} | {b['avg']:.3f} | {bo_s} | {pr_s} | {pv_s} | {rk_s} | {p30_s} | {b['status']} | {flags} |")

# SP table
lines.append('\n## My Roster — SP Stats\n')
lines.append('| Player | G | GS | IP | ERA | WHIP | K/9 | QS | ProjERA | PrevERA | PRank | PR30 | Status | Flags |')
lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for s in sorted(sp_data, key=lambda x: x['stats']['ERA'] if x['stats'] else 99):
    st = s['stats']
    if not st: continue
    pe   = f"{s['proj_era']:.2f}" if s['proj_era'] else 'N/A'
    pv   = f"{s['prev_era']:.2f}" if s.get('prev_era') else 'N/A'
    rk_s = f"#{s['pos_rank']}" if s.get('pos_rank') else 'N/A'
    p30_s= f"{s['pr30']:+.1f}" if s.get('pr30') is not None else 'N/A'
    lines.append(f"| {s['player'].name} | {st['G']} | {st['GS']} | {st['IP']} | {st['ERA']} | {st['WHIP']} | {st['K9']} | {st['QS']} | {pe} | {pv} | {rk_s} | {p30_s} | {s['status']} | {', '.join(s['flags']) or '—'} |")

# RP table
lines.append('\n## My Roster — RP Stats\n')
lines.append('| Player | G | IP | ERA | WHIP | K/9 | SV | HLD | SVHD | ProjSVHD | ProjERA | PRank | PR30 | Status | Flags |')
lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for r in sorted(rp_data, key=lambda x: (-(x['proj_svhd'] or 0), x['stats']['ERA'] if x['stats'] else 99)):
    st = r['stats']
    if not st: continue
    ps   = f"{r['proj_svhd']:.0f}" if r['proj_svhd'] else 'N/A'
    pe   = f"{r['proj_era']:.2f}"  if r['proj_era']  else 'N/A'
    rk_s = f"#{r['pos_rank']}" if r.get('pos_rank') else 'N/A'
    p30_s= f"{r['pr30']:+.1f}" if r.get('pr30') is not None else 'N/A'
    lines.append(f"| {r['player'].name} | {st['G']} | {st['IP']} | {st['ERA']} | {st['WHIP']} | {st['K9']} | {st['SV']} | {st['HLD']} | {st['SVHD']} | {ps} | {pe} | {rk_s} | {p30_s} | {r['status']} | {', '.join(r['flags']) or '—'} |")

# Z-Score Scorecard
lines.append('\n## Z-Score Scorecard (League-Wide Relative Ranking)\n')
lines.append('> Z-scores computed across all rostered league players from ESPN daily stats. '
             f'Positive = above average; negative = below. Season full + last {EVAL_WINDOW} days.\n')

def _fz(val):
    return f'{val:+.2f}' if val is not None and not (isinstance(val, float) and np.isnan(val)) else '—'

if not z_df.empty:
    bat_z_rows = z_df[~z_df['is_pitcher']].sort_values('season_z', ascending=False)
    if not bat_z_rows.empty:
        lines.append('\n### Batters\n')
        lines.append('| Player | Slot | z_R | z_HR | z_RBI | z_SB | z_OPS | Season Z | 28d Z | 28d GP |')
        lines.append('|---|---|---|---|---|---|---|---|---|---|')
        for _, r in bat_z_rows.iterrows():
            lines.append(
                f"| {r['player_name']} | {r['lineup_slot']} "
                f"| {_fz(r.get('sz_R'))} | {_fz(r.get('sz_HR'))} "
                f"| {_fz(r.get('sz_RBI'))} | {_fz(r.get('sz_SB'))} "
                f"| {_fz(r.get('sz_OPS'))} "
                f"| {r['season_z']:+.2f} | {r['window_z']:+.2f} | {int(r['window_gp'])} |"
            )
    pit_z_rows = z_df[z_df['is_pitcher']].sort_values('season_z', ascending=False)
    if not pit_z_rows.empty:
        lines.append('\n### Pitchers\n')
        lines.append('| Player | Slot | z_K/9 | z_QS | z_SVHD | z_ERA | z_WHIP | Season Z | 28d Z | 28d GP |')
        lines.append('|---|---|---|---|---|---|---|---|---|---|')
        for _, r in pit_z_rows.iterrows():
            lines.append(
                f"| {r['player_name']} | {r['lineup_slot']} "
                f"| {_fz(r.get('sz_K/9'))} | {_fz(r.get('sz_QS'))} "
                f"| {_fz(r.get('sz_SVHD'))} | {_fz(r.get('sz_ERA'))} "
                f"| {_fz(r.get('sz_WHIP'))} "
                f"| {r['season_z']:+.2f} | {r['window_z']:+.2f} | {int(r['window_gp'])} |"
            )
else:
    lines.append('_Z-score data unavailable._')

# Weakest section
lines.append('\n## Weakest Players\n')
lines.append('> Active underperformers listed first. IL players are valid drop candidates but not replacement priorities.\n')

lines.append('\n### Batters\n')
lines.append('| Player | OPS | AVG | AvgBO | Status | Flags |')
lines.append('|---|---|---|---|---|---|')
for b in weak_batters:
    bo_s = f"{b['avg_bo']:.1f}" if b['avg_bo'] else 'N/A'
    lines.append(f"| {b['player'].name} | {b['ops']:.3f} | {b['avg']:.3f} | {bo_s} | {b['status']} | {', '.join(b['flags'])} |")

lines.append('\n### Starting Pitchers\n')
lines.append('| Player | ERA | WHIP | K/9 | QS | Status | Flags |')
lines.append('|---|---|---|---|---|---|---|')
for s in weak_sps:
    st = s['stats']
    if not st: continue
    lines.append(f"| {s['player'].name} | {st['ERA']} | {st['WHIP']} | {st['K9']} | {st['QS']} | {s['status']} | {', '.join(s['flags'])} |")

lines.append('\n### Relief Pitchers\n')
lines.append('| Player | ERA | WHIP | SVHD | ProjSVHD | Status | Flags |')
lines.append('|---|---|---|---|---|---|---|')
for r in weak_rps:
    st = r['stats']
    if not st: continue
    ps = f"{r['proj_svhd']:.0f}" if r['proj_svhd'] else 'N/A'
    lines.append(f"| {r['player'].name} | {st['ERA']} | {st['WHIP']} | {st['SVHD']} | {ps} | {r['status']} | {', '.join(r['flags'])} |")

# QL Slot Competition section
lines.append('\n## QL Slot Competition\n')
lines.append('> Players ranked by ESPN `position_rank` within each slot group. Quick Lineup starts the top-ranked active player per slot. ⚠ = ranked below a worse-performing teammate — candidate for manual override.\n')

for _rgrp in ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH', 'SP', 'RP']:
    _rplayers = _ql_groups.get(_rgrp, [])
    _ractive  = [(t, d) for t, d in _rplayers if not d['on_il']]
    if len(_rplayers) < 2:
        continue
    lines.append(f'\n### {_rgrp} ({len(_rplayers)} rostered, {len(_ractive)} active)\n')
    if _rgrp in ('SP', 'RP'):
        lines.append('| Player | PRank | PR30 | ERA | QS/ProjSVHD | Status | Override |')
        lines.append('|---|---|---|---|---|---|---|')
    else:
        lines.append('| Player | PRank | PR30 | OPS | Status | Override |')
        lines.append('|---|---|---|---|---|---|')
    _rsorted = sorted(_rplayers, key=lambda x: (1 if x[1]['on_il'] else 0, x[1].get('pos_rank') or 9999))
    for _ri, (_rtype, _rdata) in enumerate(_rsorted):
        _rname  = _rdata['player'].name
        _rpr    = _rdata.get('pos_rank')
        _rp30   = _rdata.get('pr30')
        _rrk_s  = f"#{_rpr}" if _rpr else 'N/A'
        _rp30_s = f"{_rp30:+.1f}" if _rp30 is not None else 'N/A'
        _ril_s  = _rdata['status']
        _rover  = ''
        for _rov in ql_manual_overrides:
            if _rov['player'] == _rname and _rov['group'] == _rgrp:
                _rover = f'⚠ {_rov["reason"]}'
                break
        if _rtype == 'BAT':
            lines.append(f"| {_rname} | {_rrk_s} | {_rp30_s} | {_rdata['ops']:.3f} | {_ril_s} | {_rover} |")
        elif _rtype == 'SP':
            _rst = _rdata['stats']
            _rera = f"{_rst['ERA']:.2f}" if _rst else 'N/A'
            _rqs  = str(_rst['QS']) if _rst else 'N/A'
            lines.append(f"| {_rname} | {_rrk_s} | {_rp30_s} | {_rera} | {_rqs} QS | {_ril_s} | {_rover} |")
        else:
            _rst = _rdata['stats']
            _rera = f"{_rst['ERA']:.2f}" if _rst else 'N/A'
            _rps  = f"{_rdata.get('proj_svhd') or 0:.0f}"
            lines.append(f"| {_rname} | {_rrk_s} | {_rp30_s} | {_rera} | {_rps} ProjSVHD | {_ril_s} | {_rover} |")

if ql_manual_overrides:
    lines.append('\n### Manual Override Summary\n')
    lines.append('| Slot | Start | Over | Reason |')
    lines.append('|---|---|---|---|')
    for _ov in ql_manual_overrides:
        lines.append(f"| {_ov['group']} | {_ov['player']} | {_ov['blocks']} | {_ov['reason']} |")
else:
    lines.append('\n_No manual override candidates identified — QL rankings align with performance._\n')

# FA Batters table
lines.append('\n## Top Free Agents — Batters\n')
lines.append('> Active/healthy only, seen in lineups last 14 days. pR/pHR/pRBI/pSB = full-season pace. Cat = categories at pace (R≥60, HR≥15, RBI≥55, SB≥10, OPS≥.750). Composite = 60% curr OPS + 40% proj OPS.\n')
lines.append('| Name | Pos | OPS | pR | pHR | pRBI | pSB | AB | ProjOPS | Composite | Cat | LU | PRank | PR30 |')
lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
for fa in top_fa_batters[:20]:
    po    = fa.get('proj_ops'); ps = f'{po:.3f}' if po else 'N/A'
    rk_s  = f"#{fa['pos_rank']}" if fa.get('pos_rank') else 'N/A'
    p30_s = f"{fa['pr30']:+.1f}" if fa.get('pr30') is not None else 'N/A'
    lines.append(f"| {fa['name']} | {fa.get('pos','?')} | {fa.get('ops',0):.3f} | {fa['pace_r']} | {fa['pace_hr']} | {fa['pace_rbi']} | {fa['pace_sb']} | {int(fa.get('ab',0) or 0)} | {ps} | {fa['composite']:.3f} | {fa['cat_score']} | {fa['lineup_games']} | {rk_s} | {p30_s} |")

# FA SP table
lines.append('\n## Top Free Agents — SPs\n')
lines.append('> Active/healthy only, min 1 game.\n')
lines.append('| Name | Team | G | IP | ERA | WHIP | K/9 | QS | ProjERA |')
lines.append('|---|---|---|---|---|---|---|---|---|')
for fa in fa_sps[:15]:
    pe = f'{fa["ProjERA"]:.2f}' if fa['ProjERA'] else 'N/A'
    lines.append(f"| {fa['name']} | {fa['team']} | {fa['G']} | {fa['IP']} | {fa['ERA']} | {fa['WHIP']} | {fa['K9']} | {fa['QS']} | {pe} |")

# FA RP table
lines.append('\n## Top Free Agents — RPs\n')
lines.append('> Active/healthy only, min 2 games.\n')
lines.append('| Name | Team | G | IP | SV | HLD | SVHD | ERA | WHIP | K/9 | ProjSVHD | ProjERA |')
lines.append('|---|---|---|---|---|---|---|---|---|---|---|---|')
for fa in fa_rps[:20]:
    ps = f'{fa["ProjSVHD"]:.0f}' if fa['ProjSVHD'] else 'N/A'
    pe = f'{fa["ProjERA"]:.2f}'  if fa['ProjERA']  else 'N/A'
    lines.append(f"| {fa['name']} | {fa['team']} | {fa['G']} | {fa['IP']} | {fa['SV']} | {fa['HLD']} | {fa['SVHD']} | {fa['ERA']} | {fa['WHIP']} | {fa['K9']} | {ps} | {pe} |")

# 8A recommendations
lines.append('\n## Recommended Moves — Position by Position (8A)\n')
lines.append('> Best swap within each position group. Rules: Batters OPS ≥ .700; SPs ranked QS → WHIP → ERA; RPs ranked ProjSVHD → WHIP → ERA.\n')

if recs_8a_batters:
    lines.append('\n### Batter Replacements\n')
    lines.append('| Drop | Drop Status | Add | Slot | OPS Δ | Cat | pR | pHR | pRBI | pSB |')
    lines.append('|---|---|---|---|---|---|---|---|---|---|')
    for r in recs_8a_batters:
        lines.append(f"| {r['drop']} | {r['drop_status']} | {r['add']} | {r['slot']} | {r['ops_delta']:+.3f} | {r['cat_score']} | {r['pace_r']} | {r['pace_hr']} | {r['pace_rbi']} | {r['pace_sb']} |")

if recs_8a_sps:
    lines.append('\n### SP Replacements\n')
    lines.append('| Drop | Drop Status | Add | QS | WHIP | ERA Δ | K/9 |')
    lines.append('|---|---|---|---|---|---|---|')
    for r in recs_8a_sps:
        lines.append(f"| {r['drop']} | {r['drop_status']} | {r['add']} | {r['qs']} | {r['whip']:.2f} | {r['era_delta']:+.2f} | {r['k9']:.2f} |")

if recs_8a_rps:
    lines.append('\n### RP Replacements\n')
    lines.append('> Ranked by SVHD/G rate desc → WHIP asc → ERA asc. Only FanGraphs closer-role players (Closer / Co-Closer / Closer Committee / Setup Man) are considered.\n')
    lines.append('| Drop | Drop Status | Add | FG Role | SVHD/G | Curr SVHD | Season Pace | WHIP | ERA Δ |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for r in recs_8a_rps:
        lines.append(f"| {r['drop']} | {r['drop_status']} | {r['add']} | {r.get('fg_role','?')} | {r.get('svhd_per_g', 0):.3f} | {r['curr_svhd']} | {r.get('pace_svhd', 0):.0f} | {r['whip']:.2f} | {r['era_delta']:+.2f} |")

if not any([recs_8a_batters, recs_8a_sps, recs_8a_rps]):
    lines.append('_No position-matched upgrades found._')

# 8B recommendations
lines.append('\n## Recommended Moves — Position Agnostic (8B)\n')
lines.append('> Highest-impact swaps regardless of position. Ranked by 5-cat score. Pace projections at full-season rate.\n')

if agnostic_moves:
    bat_adds  = [m for m in agnostic_moves if m['add_type'] == 'BAT']
    rp_adds   = [m for m in agnostic_moves if m['add_type'] == 'RP']
    svhd_lost = sum(m['svhd_lost'] for m in bat_adds)
    lines.append('| Drop | Drop Type | Flags | Drop Status | Add | Add Type | Cat | Composite | Net Category Impact |')
    lines.append('|---|---|---|---|---|---|---|---|---|')
    for m in agnostic_moves:
        comp_s  = f"{m['composite']:.3f}" if m['composite'] else 'N/A'
        flags_s = ', '.join(m['drop_flags']) or '—'
        lines.append(f"| {m['drop']} | {m['drop_type']} | {flags_s} | {m['drop_status']} | {m['add']} | {m['add_type']} | {m['cat_score']} | {comp_s} | {m['impact']} |")
    lines.append(f'\n**Combined scenario ({len(agnostic_moves)} swap(s)):**')
    lines.append(f'- {len(bat_adds)} batter(s) added: {", ".join(m["add"] for m in bat_adds) or "none"}')
    lines.append(f'- {len(rp_adds)} RP upgrade(s): {", ".join(m["add"] for m in rp_adds) or "none"}')
    if svhd_lost > 0:
        lines.append(f'- Projected SVHD given up (batter swaps): {svhd_lost:.0f}')
    lines.append('- Note: Dropping multiple RPs reduces saves/holds coverage — consider a partial swap first')
else:
    lines.append('_No position-agnostic swaps recommended — no active flagged players or no qualifying FAs._')

# Z-Score recommendations (per flagged player)
lines.append('\n## Recommendations — Z-Score Based\n')
lines.append(f'> Players flagged: 28d z < {DROP_Z_THRESH}, or both season z < {WEAK_Z_THRESH} and 28d z < {WEAK_Z_THRESH}. '
             f'FAs ranked by league-wide z-score (ESPN daily, ≥{FA_MIN_Z_GAMES} games). IL excluded.\n')

if z_flagged:
    for fp in sorted(z_flagged, key=lambda x: x['window_z']):
        name   = fp['player_name']
        is_pit = fp['is_pitcher']
        cats   = PITCH_Z_CATS if is_pit else BAT_Z_CATS
        lines.append(f"\n### {name} ({fp['lineup_slot']}) — _{fp['flag_reason']}_\n")

        # Per-category z-score breakdown
        cat_parts = []
        for cat in cats:
            sz = fp.get(f'sz_{cat}')
            wz = fp.get(f'wz_{cat}')
            if sz is not None:
                wz_s = f' / 28d:{wz:+.2f}' if wz is not None else ''
                cat_parts.append(f'**{cat}** {sz:+.2f}{wz_s}')
        if cat_parts:
            lines.append('**Category z-scores (season / 28d):** ' + ' | '.join(cat_parts) + '  ')
        lines.append(f"**Season z:** {fp['season_z']:+.2f} | **28d z:** {fp['window_z']:+.2f} | **28d GP:** {fp['window_gp']}  \n")

        # FA recommendations
        fa_recs = _best_fa_z(name, is_pit, n=3)
        if not fa_recs.empty:
            if not is_pit:
                lines.append('| FA Candidate | GP | z_R | z_HR | z_RBI | z_SB | z_OPS | Season Z |')
                lines.append('|---|---|---|---|---|---|---|---|')
                for _, fa in fa_recs.iterrows():
                    gp = int(fa.get('games_played', fa.get('games', 0)))
                    lines.append(
                        f"| {fa['player_name']} | {gp} "
                        f"| {_fz(fa.get('z_R'))} | {_fz(fa.get('z_HR'))} "
                        f"| {_fz(fa.get('z_RBI'))} | {_fz(fa.get('z_SB'))} "
                        f"| {_fz(fa.get('z_OPS'))} | {fa['z_total']:+.2f} |"
                    )
            else:
                lines.append('| FA Candidate | GP | z_K/9 | z_QS | z_SVHD | z_ERA | z_WHIP | Season Z |')
                lines.append('|---|---|---|---|---|---|---|---|')
                for _, fa in fa_recs.iterrows():
                    gp = int(fa.get('games_played', fa.get('games', 0)))
                    lines.append(
                        f"| {fa['player_name']} | {gp} "
                        f"| {_fz(fa.get('z_K/9'))} | {_fz(fa.get('z_QS'))} "
                        f"| {_fz(fa.get('z_SVHD'))} | {_fz(fa.get('z_ERA'))} "
                        f"| {_fz(fa.get('z_WHIP'))} | {fa['z_total']:+.2f} |"
                    )
        else:
            lines.append('_No qualifying FA replacements found._')
        lines.append('')
else:
    lines.append('_No players flagged by z-score criteria._')

# Key takeaways
lines.append('\n## Key Takeaways\n')
best_bat   = max(batter_data, key=lambda x: x['ops'])
worst_bat  = min(batter_data, key=lambda x: x['ops'])
best_sp    = min(sp_data, key=lambda x: x['stats']['ERA'] if x['stats'] else 99)
active_weak_batters = [b for b in weak_batters if not b['on_il']]
active_weak_sps     = [s for s in weak_sps     if not s['on_il']]
active_weak_rps     = [r for r in weak_rps     if not r['on_il']]

lines.append(f'- **Best batter:** {best_bat["player"].name} ({best_bat["ops"]:.3f} OPS)')
lines.append(f'- **Most urgent batter drop:** {worst_bat["player"].name} ({worst_bat["ops"]:.3f} OPS, {worst_bat["status"]})')
lines.append(f'- **SP anchor:** {best_sp["player"].name} (ERA {best_sp["stats"]["ERA"]:.2f})')
lines.append(f'- **Active weaknesses:** {len(active_weak_batters)} batters, {len(active_weak_sps)} SPs, {len(active_weak_rps)} RPs flagged (IL excluded)')
if active_weak_batters:
    lines.append(f'- **Priority active batter drops:** {", ".join(b["player"].name for b in active_weak_batters[:3])}')
if active_weak_rps:
    lines.append(f'- **RP concern:** {", ".join(r["player"].name for r in active_weak_rps[:2])} — check FG closer role and SVHD/G rate flags')
if agnostic_moves:
    bat_adds = [m for m in agnostic_moves if m['add_type'] == 'BAT']
    lines.append(f'- **Top agnostic adds:** {", ".join(m["add"] for m in bat_adds[:3]) or "see RP upgrades"}')
if z_flagged:
    z_drops = [f['player_name'] for f in z_flagged if f['flag_reason'] == 'Drop candidate']
    z_weak  = [f['player_name'] for f in z_flagged if f['flag_reason'] != 'Drop candidate']
    if z_drops:
        lines.append(f'- **Z-score drop candidates:** {", ".join(z_drops[:3])} (28d z < {DROP_Z_THRESH})')
    if z_weak:
        lines.append(f'- **Z-score underperformers:** {", ".join(z_weak[:3])} (both windows below avg)')
lines.append(f'- **Methods:** 8A/8B use pace projections vs absolute thresholds; Z-Score recs rank vs all league players')

lines.append(f'\n---\n*Generated {TODAY} | Data current through {TODAY} | Active/healthy FAs only (injured and IL filtered)*\n')

with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\nReport saved to: {report_path}')
print('\n=== ANALYSIS COMPLETE ===')
