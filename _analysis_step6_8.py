"""Steps 6-8: weakest players, FA scan, recommendations."""
import sys, csv, os, json
from datetime import date, timedelta
from collections import defaultdict
sys.path.insert(0, r'C:\Users\peter.rigali\Desktop\acn_repo')
from fantasy_baseball import mlb_processing as mp

year = 2026
base = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'

with open(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_analysis_results.json', encoding='utf-8') as f:
    res = json.load(f)
batter_stats = res['batter_stats']
sp_stats     = res['sp_stats']
rp_stats     = res['rp_stats']
batter_bo    = res['batter_bo']

config = mp.load_config()
league = mp.setup_league(config, year=2026)
league_prev = mp.setup_league(config, year=2025)

def safe_float(x, default=0.0):
    try: return float(x)
    except: return default

def prev_ops(name):
    try:
        prev = next((p for t in league_prev.teams for p in t.roster if p.name == name), None)
        return safe_float(prev.stats.get(0, {}).get('breakdown', {}).get('OPS', 0)) if prev else 0.0
    except: return 0.0

def prev_era(name):
    try:
        prev = next((p for t in league_prev.teams for p in t.roster if p.name == name), None)
        return safe_float(prev.stats.get(0, {}).get('breakdown', {}).get('ERA', 0)) if prev else 0.0
    except: return 0.0

# ── Step 6: Weakest players ──────────────────────────────────────────────────
print('=== Step 6: Weakest Players ===')
print('(IL players shown as drop candidates but excluded from active replacement priority)')
print()

def il_tag(p): return ' [IL]' if p.get('onIL') else ''
def inj_note(p):
    s = p.get('injuryStatus', 'ACTIVE')
    return f' ({s})' if s not in ('ACTIVE', '') and not p.get('onIL') else ''

weak_batters = []
for b in batter_stats:
    reasons = []
    if b.get('onIL'):
        reasons.append('On IL — drop candidate if replaceable')
    else:
        if b['OPS'] < 0.650:  reasons.append(f'OPS {b["OPS"]:.3f}')
        if b['AVG'] < 0.180:  reasons.append(f'AVG {b["AVG"]:.3f}')
        if b['HR'] == 0 and b['RBI'] == 0 and b['SB'] == 0: reasons.append('0 HR/RBI/SB')
        bo = batter_bo.get(b['name'])
        if bo and bo >= 7: reasons.append(f'BO avg {bo}')
    if reasons:
        weak_batters.append({**b, 'reasons': ', '.join(reasons)})

# Sort: active weak players first, IL players after
weak_batters.sort(key=lambda x: (x.get('onIL', False), x['OPS']))

weak_sps = []
for s in sp_stats:
    reasons = []
    if s.get('onIL'):
        reasons.append('On IL — drop candidate if replaceable')
    else:
        if s['ERA'] > 5.0:  reasons.append(f'ERA {s["ERA"]:.2f}')
        if s['WHIP'] > 1.5: reasons.append(f'WHIP {s["WHIP"]:.2f}')
        if s['K9'] < 6.0:   reasons.append(f'K/9 {s["K9"]:.2f}')
        if s['GS'] > 0 and s['QS'] / s['GS'] < 0.40: reasons.append(f'QS% {s["QS"]}/{s["GS"]}')
    if reasons:
        weak_sps.append({**s, 'reasons': ', '.join(reasons)})

weak_rps = []
for r in rp_stats:
    reasons = []
    if r.get('onIL'):
        reasons.append('On IL — drop candidate if replaceable')
    else:
        if r['ERA'] > 5.0:  reasons.append(f'ERA {r["ERA"]:.2f}')
        if r['WHIP'] > 1.5: reasons.append(f'WHIP {r["WHIP"]:.2f}')
        if r['SVHD'] < 5:   reasons.append(f'SVHD {r["SVHD"]} (low)')
    if reasons:
        weak_rps.append({**r, 'reasons': ', '.join(reasons)})

print('Weak Batters (active first, IL after):')
for b in weak_batters:
    print(f'  {b["name"]:<25} OPS={b["OPS"]:.3f}{il_tag(b)}{inj_note(b)} | {b["reasons"]}')
print()
print('Weak SPs:')
for s in weak_sps:
    print(f'  {s["name"]:<22} ERA={s["ERA"]:.2f} WHIP={s["WHIP"]:.2f}{il_tag(s)}{inj_note(s)} | {s["reasons"]}')
print()
print('Weak RPs:')
for r in weak_rps:
    print(f'  {r["name"]:<22} ERA={r["ERA"]:.2f} SVHD={r["SVHD"]}{il_tag(r)}{inj_note(r)} | {r["reasons"]}')

# ── Step 7: FA scan ──────────────────────────────────────────────────────────
print()
print('=== Step 7: Free Agent Scan ===')

hitter_slots = {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH'}

# Season pace multiplier for projecting full-season counting stats
season_start = date(2026, 3, 26)
days_played = max((date.today() - season_start).days, 1)
season_days = 183
pace_mult = season_days / days_played

# 5x5 category thresholds — used to score each FA batter's category contributions
CAT_THRESHOLDS = {'r': 60, 'hr': 15, 'rbi': 55, 'sb': 10, 'ops': 0.750}

def cat_score_fa(r, hr, rbi, sb, composite):
    """Return (cat_score 0-5, pace_r, pace_hr, pace_rbi, pace_sb)."""
    pr  = round(r  * pace_mult)
    phr = round(hr * pace_mult)
    prbi= round(rbi* pace_mult)
    psb = round(sb * pace_mult)
    score = sum([
        pr   >= CAT_THRESHOLDS['r'],
        phr  >= CAT_THRESHOLDS['hr'],
        prbi >= CAT_THRESHOLDS['rbi'],
        psb  >= CAT_THRESHOLDS['sb'],
        composite >= CAT_THRESHOLDS['ops'],
    ])
    return score, pr, phr, prbi, psb

# Build FA batting order lookup from lineups CSV (last 14 days for more signal)
cutoff = (date.today() - timedelta(days=14)).isoformat()
lineup_csv = os.path.join(base, f'lineups_mlb_batters_{year}.csv')
fa_bo_data = defaultdict(list)
with open(lineup_csv, encoding='utf-8') as f:
    for row in csv.DictReader(f):
        if row['date'] >= cutoff:
            try:
                bo = float(row.get('batting_order', 0))
                if bo > 0:
                    fa_bo_data[mp.normalize_player_name(row['player_name'])].append(bo)
            except: pass

def fa_lineup_info(name):
    """Return (avg_bo, games_in_lineup) for an FA from recent lineups."""
    norm = mp.normalize_player_name(name)
    positions = fa_bo_data.get(norm, [])
    avg_bo = round(sum(positions) / len(positions), 1) if positions else None
    return avg_bo, len(positions)

# Batters — call league.free_agents directly to access injuryStatus
print('Fetching FA batters...')
_fa_raw = league.free_agents(size=200)
fa_batters = []
for p in _fa_raw:
    if mp.is_pitcher(p): continue
    bd = p.stats.get(0, {}).get('breakdown', {})
    if bd.get('AB', 0) < 10: continue
    # Skip injured / IL players — not useful as add targets
    if getattr(p, 'injured', False) or getattr(p, 'injuryStatus', 'ACTIVE') not in ('ACTIVE', ''):
        continue
    proj_ops = safe_float(p.stats.get(0, {}).get('projected_breakdown', {}).get('OPS', 0.0))
    curr_ops = safe_float(bd.get('OPS', 0.0))
    avg_bo, lineup_games = fa_lineup_info(p.name)
    # Composite score: 60% current OPS, 40% projected OPS (if available)
    composite = (0.6 * curr_ops + 0.4 * proj_ops) if proj_ops > 0 else curr_ops
    r   = safe_float(bd.get('R', 0))
    hr  = safe_float(bd.get('HR', 0))
    rbi = safe_float(bd.get('RBI', 0))
    sb  = safe_float(bd.get('SB', 0))
    cscore, pace_r, pace_hr, pace_rbi, pace_sb = cat_score_fa(r, hr, rbi, sb, composite)
    fa_batters.append({
        'name': p.name, 'pos': p.position, 'team': p.proTeam,
        'g': bd.get('G', 0), 'ab': bd.get('AB', 0), 'h': bd.get('H', 0),
        'hr': hr, 'r': r, 'rbi': rbi, 'sb': sb, 'avg': bd.get('AVG', 0.0),
        'ops': curr_ops, 'proj_ops': proj_ops, 'composite': composite,
        'cat_score': cscore,
        'pace_r': pace_r, 'pace_hr': pace_hr, 'pace_rbi': pace_rbi, 'pace_sb': pace_sb,
        'avg_bo': avg_bo, 'lineup_games': lineup_games,
    })

# Sort: lineup-present first, then by cat_score desc, then composite desc
fa_batters.sort(key=lambda x: (
    0 if x['lineup_games'] > 0 else 1,    # lineup presence first
    -x['cat_score'],
    -x['composite']
))
print(f'  {len(fa_batters)} active FA batters (pace mult {pace_mult:.2f}x, {days_played} days played)')

# Pitchers — use get_free_agents with SP(14) and RP(15) position IDs
print('Fetching FA pitchers (SP+RP)...')
fa_pitchers_raw = mp.get_free_agents(league, position_ids=[14, 15], size=200)
print(f'  {len(fa_pitchers_raw)} FA pitcher entries')

def pitcher_from_fa_dict(d):
    """Extract stats from get_free_agents dict format."""
    s = d.get('stats', {}).get(str(year), {})
    p = d.get('stats', {}).get(f'{year}Projected', {})
    outs = safe_float(s.get('OUTS', 0))
    ip   = outs / 3 if outs > 0 else safe_float(s.get('IP', 0))
    er   = safe_float(s.get('ER', 0))
    h    = safe_float(s.get('H', 0))
    bb   = safe_float(s.get('BB', 0))
    k    = safe_float(s.get('K', s.get('SO', 0)))
    sv   = int(s.get('SV', 0))
    hld  = int(s.get('HLD', 0))
    svhd = int(s.get('SVHD', sv + hld))
    gs   = int(s.get('GS', 0))
    qs   = int(s.get('QS', 0))
    era  = round((er * 27 / outs), 2) if outs > 0 else 0.0
    whip = round(((h + bb) / ip), 2) if ip > 0 else 0.0
    k9   = round((k * 27 / outs), 2) if outs > 0 else 0.0
    return {
        'name': d['name'], 'team': d['proTeam'],
        'slots': d.get('eligibleSlots', []),
        'G': int(s.get('G', 0)), 'GS': gs, 'IP': round(ip, 1),
        'SV': sv, 'HLD': hld, 'SVHD': svhd, 'QS': qs,
        'ERA': era, 'WHIP': whip, 'K9': k9,
        'ProjERA': safe_float(p.get('ERA', 0)),
        'ProjSVHD': safe_float(p.get('SVHD', sv + hld)),
    }

fa_sps_proc, fa_rps_proc = [], []
for d in fa_pitchers_raw:
    # Skip injured / IL FA pitchers — not useful as add targets
    if d.get('injured', False) or d.get('injuryStatus', 'ACTIVE') not in ('ACTIVE', ''):
        continue
    slots = d.get('eligibleSlots', [])
    stats_yr = d.get('stats', {}).get(str(year), {})
    if not stats_yr: continue
    outs = safe_float(stats_yr.get('OUTS', 0))
    ip = outs / 3 if outs > 0 else safe_float(stats_yr.get('IP', 0))
    if ip < 3.0: continue
    pd = pitcher_from_fa_dict(d)
    if 'SP' in slots and pd['GS'] > 0:
        fa_sps_proc.append(pd)
    elif 'RP' in slots:
        fa_rps_proc.append(pd)

fa_sps_proc.sort(key=lambda x: x['ERA'] if x['ERA'] > 0 else 99)
fa_rps_proc.sort(key=lambda x: (-x['SVHD'], x['ERA'] if x['ERA'] > 0 else 99))

print()
print('-- Top 20 FA Batters (5-cat score; lineup-present first; OPS composite = 60% curr + 40% proj) --')
print(f'{"Name":<25} {"Team":<5} {"Pos":<8} {"AB":>3} {"pR":>4} {"pHR":>4} {"pRBI":>5} {"pSB":>4} {"OPS":>5} {"ProjOPS":>7} {"Cat":>4} {"Comp":>6} {"AvgBO":>6} {"LU":>4}')
print('-'*115)
for fa in fa_batters[:20]:
    bo_s  = f'{fa["avg_bo"]:.1f}' if fa['avg_bo'] else ' N/A'
    flag  = ' *' if fa['ab'] < 15 else ''
    no_lu = ' !' if fa['lineup_games'] == 0 else ''
    print(f'{fa["name"]:<25} {str(fa["team"]):<5} {fa["pos"]:<8} {int(fa["ab"]):>3} '
          f'{fa["pace_r"]:>4} {fa["pace_hr"]:>4} {fa["pace_rbi"]:>5} {fa["pace_sb"]:>4} '
          f'{fa["ops"]:>5.3f} {fa["proj_ops"]:>7.3f} {fa["cat_score"]:>4} {fa["composite"]:>6.3f} '
          f'{bo_s:>6} {fa["lineup_games"]:>4}{flag}{no_lu}')
print(f'  pR/pHR/pRBI/pSB = full-season pace ({pace_mult:.1f}x). Thresholds: R>=60, HR>=15, RBI>=55, SB>=10, OPS>=.750')
print('  (! = not seen in lineups last 14 days — treat with caution)')

print()
print('-- Top 15 FA SPs (by ERA) --')
print(f'{"Name":<25} {"Team":<5} {"G":>3} {"GS":>3} {"IP":>5} {"ERA":>5} {"WHIP":>5} {"K/9":>5} {"QS":>3} {"ProjERA":>7}')
print('-'*80)
for fa in fa_sps_proc[:15]:
    flag = ' *' if fa['IP'] < 5 else ''
    print(f'{fa["name"]:<25} {str(fa["team"]):<5} {fa["G"]:>3} {fa["GS"]:>3} {fa["IP"]:>5.1f} {fa["ERA"]:>5.2f} {fa["WHIP"]:>5.2f} {fa["K9"]:>5.2f} {fa["QS"]:>3} {fa["ProjERA"]:>7.2f}{flag}')

print()
print('-- Top 20 FA RPs (by SVHD then ERA) --')
print(f'{"Name":<25} {"Team":<5} {"G":>3} {"IP":>5} {"SV":>3} {"HLD":>4} {"SVHD":>5} {"ERA":>5} {"WHIP":>5} {"K/9":>5} {"ProjSVHD":>9}')
print('-'*92)
for fa in fa_rps_proc[:20]:
    print(f'{fa["name"]:<25} {str(fa["team"]):<5} {fa["G"]:>3} {fa["IP"]:>5.1f} {fa["SV"]:>3} {fa["HLD"]:>4} {fa["SVHD"]:>5} {fa["ERA"]:>5.2f} {fa["WHIP"]:>5.2f} {fa["K9"]:>5.2f} {fa["ProjSVHD"]:>9.1f}')

# ── Step 8A: Position-by-position ────────────────────────────────────────────
print()
print('=== Step 8A: Position-by-Position Replacements ===')

my_batter_slots = {b['name']: set(b['slots'].split(',')) if b['slots'] else set() for b in batter_stats}

print(f'{"Drop":<25} {"Add":<25} {"Slot":<8} {"OPS d":>7} {"Cat":>4} {"pR":>4} {"pHR":>4} {"pRBI":>5} {"pSB":>4}  Note')
print('-'*110)
recs_8a_batters = []
for b in weak_batters:
    my_slots = my_batter_slots.get(b['name'], set())
    for fa in fa_batters:
        fa_pos = fa.get('pos', '')
        shared = {fa_pos} & my_slots if fa_pos in my_slots else set()
        if not shared:
            for ms in my_slots:
                if ms == fa_pos or (fa_pos == 'OF' and ms in {'LF','CF','RF','OF'}):
                    shared = {ms}
                    break
        if not shared: continue
        delta = fa['ops'] - b['OPS']
        if delta < 0.10: continue
        bo_s = f'{fa["avg_bo"]:.1f}' if fa['avg_bo'] else 'N/A'
        notes = []
        if fa['ab'] < 15: notes.append('small sample')
        if fa['lineup_games'] == 0: notes.append('not in recent lineups')
        elif fa['lineup_games'] < 5: notes.append(f'only {fa["lineup_games"]} lineup apps')
        note_str = ', '.join(notes)
        slot_str = ','.join(sorted(shared))
        print(f'{b["name"]:<25} {fa["name"]:<25} {slot_str:<8} {delta:>+7.3f} '
              f'{fa["cat_score"]:>4} {fa["pace_r"]:>4} {fa["pace_hr"]:>4} {fa["pace_rbi"]:>5} {fa["pace_sb"]:>4}  {note_str}')
        recs_8a_batters.append({
            'drop': b['name'], 'drop_status': '[IL]' if b.get('onIL') else b.get('injuryStatus','Active') if b.get('injuryStatus') not in ('ACTIVE','') else 'Active',
            'add': fa['name'], 'slot': slot_str, 'ops_delta': round(delta, 3),
            'cat_score': fa['cat_score'], 'pace_r': fa['pace_r'], 'pace_hr': fa['pace_hr'],
            'pace_rbi': fa['pace_rbi'], 'pace_sb': fa['pace_sb'], 'composite': round(fa['composite'], 3),
            'note': note_str,
        })
        break

print()
print('SP Replacements:')
print(f'{"Drop":<22} {"Add":<25} {"ERA d":>7} {"K/9":>5} {"QS":>3}')
print('-'*65)
recs_8a_sps = []
shown_sp_adds = set()
for s in weak_sps:
    # Prefer an FA not yet shown; fall back to any qualifying FA if all used
    pick = None
    for fa in fa_sps_proc[:15]:
        if fa['ERA'] <= 0: continue
        delta = s['ERA'] - fa['ERA']
        if delta > 0 and fa['K9'] >= 6.0:
            if fa['name'] not in shown_sp_adds:
                pick = fa; break
            elif pick is None:
                pick = fa  # fallback duplicate
    if pick:
        delta = s['ERA'] - pick['ERA']
        print(f'{s["name"]:<22} {pick["name"]:<25} {delta:>+7.2f} {pick["K9"]:>5.2f} {pick["QS"]:>3}')
        shown_sp_adds.add(pick['name'])
        recs_8a_sps.append({
            'drop': s['name'], 'drop_status': '[IL]' if s.get('onIL') else s.get('injuryStatus','Active') if s.get('injuryStatus') not in ('ACTIVE','') else 'Active',
            'add': pick['name'], 'era_delta': round(delta, 2), 'k9': pick['K9'], 'qs': pick['QS'],
            'note': '',
        })

print()
print('RP Replacements (by SVHD gain or ERA improvement):')
print(f'{"Drop":<22} {"Add":<25} {"SVHD d":>7} {"ERA d":>7}')
print('-'*65)
recs_8a_rps = []
shown_rp_adds = set()
for r in weak_rps:
    # Prefer an FA not yet shown; fall back to any qualifying FA if all used
    pick = None
    for fa in fa_rps_proc[:20]:
        svhd_delta = fa['SVHD'] - r['SVHD']
        era_delta  = r['ERA'] - fa['ERA'] if fa['ERA'] > 0 else 0
        if svhd_delta > 0 or era_delta > 1.0:
            if fa['name'] not in shown_rp_adds:
                pick = fa; break
            elif pick is None:
                pick = fa  # fallback duplicate
    if pick:
        svhd_delta = pick['SVHD'] - r['SVHD']
        era_delta  = r['ERA'] - pick['ERA'] if pick['ERA'] > 0 else 0
        print(f'{r["name"]:<22} {pick["name"]:<25} {svhd_delta:>+7} {era_delta:>+7.2f}')
        shown_rp_adds.add(pick['name'])
        recs_8a_rps.append({
            'drop': r['name'], 'drop_status': '[IL]' if r.get('onIL') else r.get('injuryStatus','Active') if r.get('injuryStatus') not in ('ACTIVE','') else 'Active',
            'add': pick['name'], 'svhd_delta': svhd_delta, 'era_delta': round(era_delta, 2),
            'note': '',
        })

# ── Step 8B: Position-agnostic ───────────────────────────────────────────────
print()
print('=== Step 8B: Position-Agnostic Replacements ===')
print('(Drop low-ceiling RPs / weak batters for highest-impact FAs regardless of position)')
print()

# Low-ceiling RP drop candidates: SVHD < 7 or ERA > 5 — active players first
drop_candidates = sorted(
    [r for r in rp_stats if r['SVHD'] < 7 or r['ERA'] > 5.0],
    key=lambda x: (x.get('onIL', False), x['SVHD'], -x['ERA'])
)
# Weakest active batters (IL batters included but sorted last)
drop_candidates += sorted(
    [b for b in weak_batters],
    key=lambda x: (x.get('onIL', False), x['OPS'])
)[:3]

# Best available FAs across all types — composite score + lineup presence required
best_fas = []
for fa in fa_batters[:15]:
    best_fas.append({
        'name': fa['name'], 'type': 'BAT',
        'ops': fa['ops'], 'proj_ops': fa['proj_ops'], 'composite': fa['composite'],
        'cat_score': fa['cat_score'],
        'hr': fa['hr'], 'r': fa['r'], 'rbi': fa['rbi'], 'sb': fa['sb'], 'svhd': 0,
        'pace_r': fa['pace_r'], 'pace_hr': fa['pace_hr'],
        'pace_rbi': fa['pace_rbi'], 'pace_sb': fa['pace_sb'],
        'avg_bo': fa['avg_bo'], 'lineup_games': fa['lineup_games'],
    })
for fa in fa_rps_proc[:10]:
    if fa['SVHD'] >= 5:
        best_fas.append({'name': fa['name'], 'type': 'RP', 'ops': 0, 'hr': 0, 'r': 0, 'rbi': 0, 'sb': 0,
                         'svhd': fa['SVHD'], 'era': fa['ERA'], 'cat_score': 0,
                         'pace_r': 0, 'pace_hr': 0, 'pace_rbi': 0, 'pace_sb': 0})

print(f'{"Drop":<25} {"Type":<4} {"Add":<25} {"Type":<4} {"Cat":>4} {"Comp":>6} {"AvgBO":>6} {"LU":>4}  {"Net Category Impact"}')
print('-'*125)
shown_adds = set()
shown_drops = set()
recs = []
recs_8b = []
for drop in drop_candidates:
    if drop['name'] in shown_drops: continue
    drop_type = 'RP' if drop.get('type') == 'RP' or drop in rp_stats or 'SVHD' in drop else 'BAT'
    drop_svhd = drop.get('SVHD', 0)
    drop_status = '[IL]' if drop.get('onIL') else drop.get('injuryStatus','Active') if drop.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    for fa in best_fas:
        if fa['name'] in shown_adds: continue
        if fa['type'] == 'BAT':
            # Build per-category impact using pace-projected counting stats
            cats = []
            if fa['pace_r']   >= CAT_THRESHOLDS['r']:   cats.append(f'+R({fa["pace_r"]})')
            if fa['pace_hr']  >= CAT_THRESHOLDS['hr']:  cats.append(f'+HR({fa["pace_hr"]})')
            if fa['pace_rbi'] >= CAT_THRESHOLDS['rbi']: cats.append(f'+RBI({fa["pace_rbi"]})')
            if fa['pace_sb']  >= CAT_THRESHOLDS['sb']:  cats.append(f'+SB({fa["pace_sb"]})')
            if fa['composite'] >= CAT_THRESHOLDS['ops']: cats.append(f'+OPS({fa["composite"]:.3f})')
            if drop_svhd > 0:  cats.append(f'-SVHD({drop_svhd})')
            if fa['cat_score'] >= 2:
                bo_s = f'{fa["avg_bo"]:.1f}' if fa['avg_bo'] else 'N/A'
                impact = ', '.join(cats) if cats else f'OPS {fa["composite"]:.3f}'
                print(f'{drop["name"]:<25} {drop_type:<4} {fa["name"]:<25} BAT  {fa["cat_score"]:>4} {fa["composite"]:>6.3f} {bo_s:>6} {fa["lineup_games"]:>4}  {impact}')
                shown_adds.add(fa['name'])
                shown_drops.add(drop['name'])
                recs.append((drop, fa))
                recs_8b.append({
                    'drop': drop['name'], 'drop_type': drop_type, 'drop_status': drop_status,
                    'add': fa['name'], 'add_type': 'BAT',
                    'cat_score': fa['cat_score'], 'composite': round(fa['composite'], 3),
                    'avg_bo': fa.get('avg_bo'), 'lineup_games': fa.get('lineup_games', 0),
                    'impact': impact,
                })
                break
        elif fa['type'] == 'RP' and drop_type in ('RP', 'BAT'):
            svhd_gain = fa['svhd'] - drop_svhd
            if svhd_gain >= 3:
                impact = f'+SVHD({svhd_gain:+}), ERA {fa["era"]:.2f}'
                print(f'{drop["name"]:<25} {drop_type:<4} {fa["name"]:<25} RP     N/A    N/A  N/A  N/A  {impact}')
                shown_adds.add(fa['name'])
                shown_drops.add(drop['name'])
                recs.append((drop, fa))
                recs_8b.append({
                    'drop': drop['name'], 'drop_type': drop_type, 'drop_status': drop_status,
                    'add': fa['name'], 'add_type': 'RP',
                    'cat_score': 0, 'composite': 0.0,
                    'avg_bo': None, 'lineup_games': 0,
                    'impact': impact,
                })
                break

print()
print('Combined scenario if all position-agnostic swaps made:')
bat_adds = [fa for _, fa in recs if fa['type'] == 'BAT']
rp_adds  = [fa for _, fa in recs if fa['type'] == 'RP']
svhd_lost = sum(d.get('SVHD', 0) for d, fa in recs if fa['type'] == 'BAT')
svhd_gained = sum(fa['svhd'] for _, fa in recs if fa['type'] == 'RP')
print(f'  Batters added: {len(bat_adds)} ({", ".join(f["name"] for f in bat_adds)})')
print(f'  RPs upgraded:  {len(rp_adds)} ({", ".join(f["name"] for f in rp_adds)})')
print(f'  SVHD surrendered from bat swaps: ~{svhd_lost}')
print(f'  SVHD gained from RP upgrades:    ~{svhd_gained}')
print(f'  Net SVHD change: {svhd_gained - svhd_lost:+}')

# ── Save all for Step 9 report ───────────────────────────────────────────────
all_results = {
    'batter_stats': batter_stats,
    'sp_stats': sp_stats,
    'rp_stats': rp_stats,
    'batter_bo': batter_bo,
    'weak_batters': weak_batters,
    'weak_sps': weak_sps,
    'weak_rps': weak_rps,
    'fa_batters': fa_batters[:20],
    'fa_sps': fa_sps_proc[:15],
    'fa_rps': fa_rps_proc[:20],
    'recs_8a_batters': recs_8a_batters,
    'recs_8a_sps': recs_8a_sps,
    'recs_8a_rps': recs_8a_rps,
    'recs_8b': recs_8b,
}
with open(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_analysis_results.json', 'w', encoding='utf-8') as f:
    json.dump(all_results, f, indent=2, default=str)
print()
print('Results saved.')
