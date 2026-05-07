"""Steps 3-5: batter stats, pitcher stats, batting order analysis."""
import sys, csv, os
from datetime import date, timedelta
from collections import defaultdict
sys.path.insert(0, r'C:\Users\peter.rigali\Desktop\acn_repo')
from fantasy_baseball import mlb_processing as mp

year = 2026
base = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'

config = mp.load_config()
league = mp.setup_league(config, year=2026)
league_prev = mp.setup_league(config, year=2025)
my_team_id = int(config['BASEBALL']['BB_MY_TEAM_ID'])
my_team_obj = next(t for t in league.teams if t.team_id == my_team_id)
my_roster = my_team_obj.roster

hitter_slots = {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH'}
my_batters = [p for p in my_roster if not mp.is_pitcher(p)]
my_sps = [p for p in my_roster if 'SP' in p.eligibleSlots and not any(s in hitter_slots for s in p.eligibleSlots)]
my_rps = [p for p in my_roster if 'RP' in p.eligibleSlots and 'SP' not in p.eligibleSlots and not any(s in hitter_slots for s in p.eligibleSlots)]

# ── helpers ──────────────────────────────────────────────────────────────────
def safe_float(x, default=0.0):
    try: return float(x)
    except: return default

def get_espn_stat(player, key, default=0):
    try:
        bd = player.stats.get(0, {}).get('breakdown', {})
        return bd.get(key, default)
    except: return default

def get_proj_stat(player, key, default=0):
    try:
        bd = player.stats.get(0, {}).get('projected_breakdown', {})
        return bd.get(key, default)
    except: return default

def get_prev_stat(player_name, league_p, key, default=0):
    try:
        prev = next((p for t in league_p.teams for p in t.roster if p.name == player_name), None)
        if prev:
            return prev.stats.get(0, {}).get('breakdown', {}).get(key, default)
    except: pass
    return default

# ── Step 3: Batter stats ─────────────────────────────────────────────────────
print('=== Step 3: Batter Stats ===')

# Load MLB game log CSV for counting stats
mlb_csv = os.path.join(base, f'stats_mlb_daily_{year}.csv')
batter_rows = defaultdict(list)
with open(mlb_csv, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['b_or_p'] == 'batter':
            batter_rows[r['player_name']].append(r)

def agg_batter(rows):
    d = defaultdict(float)
    for r in rows:
        for k in ['AB','R','H','2B','3B','HR','RBI','SB','CS','BB','SO','HBP','SF','TB','G']:
            d[k] += safe_float(r.get(k, 0))
    return d

batter_stats = []
for p in my_batters:
    name = p.name
    norm = mp.normalize_player_name(name)
    mlb_match = next((k for k in batter_rows if mp.normalize_player_name(k) == norm), None)
    mlb = agg_batter(batter_rows[mlb_match]) if mlb_match else defaultdict(float)

    ops  = safe_float(get_espn_stat(p, 'OPS'), 0.0)
    avg  = safe_float(get_espn_stat(p, 'AVG'), 0.0)
    obp  = safe_float(get_espn_stat(p, 'OBP'), 0.0)
    proj_ops = safe_float(get_proj_stat(p, 'OPS'), 0.0)
    prev_ops = safe_float(get_prev_stat(name, league_prev, 'OPS'), 0.0)

    injury_status = getattr(p, 'injuryStatus', 'ACTIVE')
    on_il = getattr(p, 'lineupSlot', '').startswith('IL')

    batter_stats.append({
        'name': name,
        'slots': ','.join(s for s in p.eligibleSlots if s in hitter_slots),
        'injuryStatus': injury_status,
        'onIL': on_il,
        'G':    int(mlb['G']),
        'AB':   int(mlb['AB']),
        'R':    int(mlb['R']),
        'HR':   int(mlb['HR']),
        'RBI':  int(mlb['RBI']),
        'SB':   int(mlb['SB']),
        'OPS':  ops,
        'AVG':  avg,
        'OBP':  obp,
        'ProjOPS': proj_ops,
        'PrevOPS': prev_ops,
        '_player': p,
    })

batter_stats.sort(key=lambda x: x['OPS'], reverse=True)
print(f'{"Name":<25} {"Pos":<12} {"G":>3} {"AB":>3} {"R":>3} {"HR":>3} {"RBI":>3} {"SB":>3} {"OPS":>5} {"AVG":>5} {"ProjOPS":>7} {"PrevOPS":>7} {"Status"}')
print('-'*105)
for b in batter_stats:
    il_tag  = ' [IL]' if b['onIL'] else ''
    inj_tag = f' ({b["injuryStatus"]})' if b['injuryStatus'] not in ('ACTIVE', '') and not b['onIL'] else ''
    flag    = ' ⚠' if (b['OPS'] < 0.650 or b['AVG'] < 0.180) and not b['onIL'] else ''
    status  = (il_tag or inj_tag or 'Active').strip()
    print(f'{b["name"]:<25} {b["slots"]:<12} {b["G"]:>3} {b["AB"]:>3} {b["R"]:>3} {b["HR"]:>3} {b["RBI"]:>3} {b["SB"]:>3} {b["OPS"]:>5.3f} {b["AVG"]:>5.3f} {b["ProjOPS"]:>7.3f} {b["PrevOPS"]:>7.3f} {status}{flag}')

# ── Step 4: Pitcher stats ────────────────────────────────────────────────────
print()
print('=== Step 4: Pitcher Stats ===')

pitcher_rows = defaultdict(list)
with open(mlb_csv, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['b_or_p'] == 'pitcher':
            pitcher_rows[r['player_name']].append(r)

def agg_pitcher(rows):
    d = defaultdict(float)
    for r in rows:
        for k in ['G','GS','OUTS','H','R','ER','HR','BB','K','QS','SV','HLD','SVHD']:
            d[k] += safe_float(r.get(k, 0))
    return d

def calc_pitcher_rates(d):
    outs = d['OUTS']
    ip = outs / 3
    era  = (d['ER'] * 27 / outs) if outs > 0 else 0.0
    whip = ((d['H'] + d['BB']) / ip) if ip > 0 else 0.0
    k9   = (d['K'] * 27 / outs) if outs > 0 else 0.0
    return round(ip, 1), round(era, 2), round(whip, 2), round(k9, 2)

pitcher_stats = []
for p in my_sps + my_rps:
    name = p.name
    norm = mp.normalize_player_name(name)
    mlb_match = next((k for k in pitcher_rows if mp.normalize_player_name(k) == norm), None)
    mlb = agg_pitcher(pitcher_rows[mlb_match]) if mlb_match else defaultdict(float)
    ip, era, whip, k9 = calc_pitcher_rates(mlb)

    proj_era  = safe_float(get_proj_stat(p, 'ERA'), 0.0)
    proj_sv   = safe_float(get_proj_stat(p, 'saves'), 0)
    proj_hld  = safe_float(get_proj_stat(p, 'holds'), 0)
    proj_svhd = safe_float(get_proj_stat(p, 'saves_holds'), proj_sv + proj_hld)
    prev_era  = safe_float(get_prev_stat(name, league_prev, 'ERA'), 0.0)
    is_sp     = p in my_sps
    injury_status = getattr(p, 'injuryStatus', 'ACTIVE')
    on_il = getattr(p, 'lineupSlot', '').startswith('IL')

    pitcher_stats.append({
        'name': name,
        'injuryStatus': injury_status,
        'onIL': on_il,
        'type': 'SP' if is_sp else 'RP',
        'G':    int(mlb['G']),
        'GS':   int(mlb['GS']),
        'IP':   ip,
        'ERA':  era,
        'WHIP': whip,
        'K9':   k9,
        'QS':   int(mlb['QS']),
        'SV':   int(mlb['SV']),
        'HLD':  int(mlb['HLD']),
        'SVHD': int(mlb['SVHD']),
        'ProjERA':  proj_era,
        'ProjSV':   proj_sv,
        'ProjSVHD': proj_svhd,
        'PrevERA':  prev_era,
        '_player': p,
    })

sps = [x for x in pitcher_stats if x['type'] == 'SP']
rps = [x for x in pitcher_stats if x['type'] == 'RP']
sps.sort(key=lambda x: x['ERA'])
rps.sort(key=lambda x: (-x['SVHD'], x['ERA']))

print('-- Starting Pitchers --')
print(f'{"Name":<22} {"G":>3} {"GS":>3} {"IP":>5} {"ERA":>5} {"WHIP":>5} {"K/9":>5} {"QS":>3} {"ProjERA":>7} {"PrevERA":>7} {"Status"}')
print('-'*88)
for s in sps:
    il_tag  = ' [IL]' if s['onIL'] else ''
    inj_tag = f' ({s["injuryStatus"]})' if s['injuryStatus'] not in ('ACTIVE', '') and not s['onIL'] else ''
    flag    = ' ⚠' if (s['ERA'] > 5.0 or s['WHIP'] > 1.50 or s['K9'] < 6.0) and not s['onIL'] else ''
    status  = (il_tag or inj_tag or 'Active').strip()
    print(f'{s["name"]:<22} {s["G"]:>3} {s["GS"]:>3} {s["IP"]:>5.1f} {s["ERA"]:>5.2f} {s["WHIP"]:>5.2f} {s["K9"]:>5.2f} {s["QS"]:>3} {s["ProjERA"]:>7.2f} {s["PrevERA"]:>7.2f} {status}{flag}')

print()
print('-- Relief Pitchers --')
print(f'{"Name":<22} {"G":>3} {"IP":>5} {"SV":>3} {"HLD":>4} {"SVHD":>5} {"ERA":>5} {"WHIP":>5} {"K/9":>5} {"ProjSVHD":>9} {"PrevERA":>7} {"Status"}')
print('-'*98)
for r in rps:
    il_tag  = ' [IL]' if r['onIL'] else ''
    inj_tag = f' ({r["injuryStatus"]})' if r['injuryStatus'] not in ('ACTIVE', '') and not r['onIL'] else ''
    flag    = ' ⚠' if (r['ERA'] > 5.0 or r['WHIP'] > 1.50 or r['SVHD'] < 5) and not r['onIL'] else ''
    status  = (il_tag or inj_tag or 'Active').strip()
    print(f'{r["name"]:<22} {r["G"]:>3} {r["IP"]:>5.1f} {r["SV"]:>3} {r["HLD"]:>4} {r["SVHD"]:>5} {r["ERA"]:>5.2f} {r["WHIP"]:>5.2f} {r["K9"]:>5.2f} {r["ProjSVHD"]:>9.1f} {r["PrevERA"]:>7.2f} {status}{flag}')

# ── Step 5: Batting order analysis ──────────────────────────────────────────
print()
print('=== Step 5: Batting Order Analysis (last 7 days) ===')

cutoff = (date.today() - timedelta(days=7)).isoformat()
lineup_csv = os.path.join(base, f'lineups_mlb_batters_{year}.csv')
with open(lineup_csv, encoding='utf-8') as f:
    lineups = [r for r in csv.DictReader(f) if r['date'] >= cutoff]

bo_data = defaultdict(list)
for row in lineups:
    pname = row.get('player_name', '')
    bo    = safe_float(row.get('batting_order', 0))
    if bo > 0:
        bo_data[pname].append(bo)

print(f'{"Name":<25} {"AvgBO":>6} {"Games":>6} {"Slots":>6}')
print('-'*48)
batter_bo = {}
for b in batter_stats:
    norm = mp.normalize_player_name(b['name'])
    match = next((k for k in bo_data if mp.normalize_player_name(k) == norm), None)
    positions = bo_data[match] if match else []
    avg_bo = round(sum(positions) / len(positions), 1) if positions else None
    batter_bo[b['name']] = avg_bo
    avg_str = f'{avg_bo:.1f}' if avg_bo else 'N/A'
    flag = ' ⚠' if (avg_bo and avg_bo >= 7) or not positions else ''
    print(f'{b["name"]:<25} {avg_str:>6} {len(positions):>6}{flag}')

# Persist results for next steps
import json
results = {
    'batter_stats': [{k: v for k, v in b.items() if k != '_player'} for b in batter_stats],
    'sp_stats':     [{k: v for k, v in s.items() if k != '_player'} for s in sps],
    'rp_stats':     [{k: v for k, v in r.items() if k != '_player'} for r in rps],
    'batter_bo':    batter_bo,
}
out = r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_analysis_results.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2)
print()
print(f'Results saved to {out}')
