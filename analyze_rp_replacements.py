"""
analyze_rp_replacements.py
===========================
Description: Deep-dive RP replacement analysis. Calculates SVHD, WHIP, ERA,
             and K/9 for every rostered RP and available FA RP across three
             windows (season, last 28 days, last 14 days) using the MLB boxscore
             data. Enriches each pitcher with their FanGraphs closer role where
             available. Flags underperforming rostered RPs and ranks FA
             replacements by the league's RP priority order:
             SVHD desc → WHIP asc → ERA asc.

Source Data: data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_{year}.csv
             data-lake/01_Bronze/fantasy_baseball/closer_depth_fangraphs_{year}.csv
             ESPN API (roster, FA list, injury status)

Outputs: fantasy_baseball/reports/rp_analysis_{YYYY-MM-DD}.md
"""

import csv
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
YEAR        = 2026
TODAY       = date.today()
TODAY_STR   = TODAY.isoformat()
CUT_14      = (TODAY - timedelta(days=14)).isoformat()
CUT_28      = (TODAY - timedelta(days=28)).isoformat()

BASE        = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')

MIN_OUTS_FA     = 15     # minimum season OUTS (~5 IP) to qualify
MIN_APP_FLAG    = 5      # minimum appearances before applying flags
FLAG_SVHD       = 5      # below this season SVHD (with >= MIN_APP_FLAG G) → LOW_SVHD
FLAG_WHIP       = 1.45   # above this → HIGH_WHIP
FLAG_ERA        = 4.50   # above this → HIGH_ERA

HITTER_SLOTS = {'C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'DH'}

# ---------------------------------------------------------------------------
# ESPN setup
# ---------------------------------------------------------------------------
config     = mp.load_config()
league     = mp.setup_league(config, year=YEAR)
my_team_id = int(config['BASEBALL']['BB_MY_TEAM_ID'])
my_team    = next(t for t in league.teams if t.team_id == my_team_id)
my_roster  = my_team.roster

print(f'Team: {my_team.team_name}')

my_rps = [
    p for p in my_roster
    if 'RP' in p.eligibleSlots
    and 'SP' not in p.eligibleSlots
    and not any(s in HITTER_SLOTS for s in p.eligibleSlots)
]

# ---------------------------------------------------------------------------
# FanGraphs role lookup (latest snapshot)
# ---------------------------------------------------------------------------
fg_path = os.path.join(BASE, f'closer_depth_fangraphs_{YEAR}.csv')
fg_role_lookup = {}
fg_date = 'N/A'
if os.path.exists(fg_path):
    with open(fg_path, encoding='utf-8') as f:
        fg_rows = list(csv.DictReader(f))
    if fg_rows:
        fg_date = max(r['date_scraped'] for r in fg_rows)
        for r in fg_rows:
            if r['date_scraped'] == fg_date:
                fg_role_lookup[mp.normalize_player_name(r['player_name'])] = r['role']

def get_role(name):
    return fg_role_lookup.get(mp.normalize_player_name(name), '')

# ---------------------------------------------------------------------------
# Load boxscore — pitcher rows only
# ---------------------------------------------------------------------------
box_path = os.path.join(BASE, f'stats_mlb_boxscore_{YEAR}.csv')
with open(box_path, encoding='utf-8') as f:
    all_pitcher_rows = [r for r in csv.DictReader(f) if r['b_or_p'] == 'pitcher']

name_index = {}
for r in all_pitcher_rows:
    key = mp.normalize_player_name(r['player_name'])
    name_index.setdefault(key, []).append(r)

# ---------------------------------------------------------------------------
# Aggregation helper
# ---------------------------------------------------------------------------
def _safe_int(val):
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0


def agg_rp(name, cutoff=None):
    """
    Aggregate RP stats for a player from the boxscore CSV.
    Counts all pitching appearances (including any spot starts).
    cutoff: ISO date string — only include rows on or after this date.
    Returns None if the player has no qualifying rows.
    """
    norm = mp.normalize_player_name(name)
    rows = name_index.get(norm, [])
    if cutoff:
        rows = [r for r in rows if r['date'] >= cutoff]
    # Only count rows where the pitcher actually appeared (did_play=1 or OUTS > 0)
    rows = [r for r in rows if r.get('did_play') == '1' or _safe_int(r.get('OUTS', 0)) > 0]
    if not rows:
        return None

    g    = len(rows)
    sv   = sum(_safe_int(r.get('SV',   0)) for r in rows)
    hld  = sum(_safe_int(r.get('HLD',  0)) for r in rows)
    svhd = sum(_safe_int(r.get('SVHD', 0)) for r in rows)
    outs = sum(_safe_int(r.get('OUTS', 0)) for r in rows)
    er   = sum(_safe_int(r.get('ER',   0)) for r in rows)
    ph   = sum(_safe_int(r.get('P_H',  0)) for r in rows)
    pbb  = sum(_safe_int(r.get('P_BB', 0)) for r in rows)
    k    = sum(_safe_int(r.get('K',    0)) for r in rows)

    ip     = outs / 3
    era    = (er  * 27) / outs if outs else 0.0
    whip   = (ph + pbb) / ip   if ip   else 0.0
    k9     = (k   * 27) / outs if outs else 0.0
    svhd_g = svhd / g          if g    else 0.0

    return dict(
        G=g, SV=sv, HLD=hld, SVHD=svhd, SVHD_G=round(svhd_g, 3),
        IP=round(ip, 1), OUTS=outs,
        ERA=round(era, 2), WHIP=round(whip, 2), K9=round(k9, 2),
    )


# ---------------------------------------------------------------------------
# Injury / status helper
# ---------------------------------------------------------------------------
def player_status(p):
    inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    on_il = 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION')
    if on_il:   return True,  '[IL]'
    if inj == 'DAY_TO_DAY': return False, 'DTD'
    if inj not in ('ACTIVE', ''): return False, inj
    return False, 'Active'


# ---------------------------------------------------------------------------
# Flag helper
# ---------------------------------------------------------------------------
def get_flags(season_stats):
    if season_stats is None:
        return ['NO_DATA']
    flags = []
    if season_stats['G'] >= MIN_APP_FLAG:
        if season_stats['SVHD'] < FLAG_SVHD:
            flags.append('LOW_SVHD')
        if season_stats['WHIP'] > FLAG_WHIP:
            flags.append('HIGH_WHIP')
        if season_stats['ERA'] > FLAG_ERA:
            flags.append('HIGH_ERA')
    return flags


# ---------------------------------------------------------------------------
# FA RP fetch
# ---------------------------------------------------------------------------
all_fa_raw = mp.get_free_agents(league, position_ids=[14, 15], size=300)

_seen = set()
fa_rps_raw = []
for fa in all_fa_raw:
    if fa['name'] in _seen:
        continue
    _seen.add(fa['name'])
    slots = fa.get('eligibleSlots', [])
    if 'RP' not in slots or 'SP' in slots:
        continue
    inj = (fa.get('injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION'):
        continue
    fa_rps_raw.append(fa)

fa_rps = []
for fa in fa_rps_raw:
    s_all = agg_rp(fa['name'])
    if s_all is None:
        continue
    if s_all['OUTS'] < MIN_OUTS_FA:
        continue
    s_14 = agg_rp(fa['name'], cutoff=CUT_14) or {}
    s_28 = agg_rp(fa['name'], cutoff=CUT_28) or {}
    fa_rps.append(dict(
        name=fa['name'],
        team=fa.get('proTeam', '?'),
        role=get_role(fa['name']),
        season=s_all,
        d14=s_14,
        d28=s_28,
    ))

# Sort: SVHD desc → SVHD/G desc → WHIP asc → ERA asc
fa_rps.sort(key=lambda x: (
    -x['season']['SVHD'],
    -x['season']['SVHD_G'],
     x['season']['WHIP'],
     x['season']['ERA'],
))

# ---------------------------------------------------------------------------
# Build rostered RP data
# ---------------------------------------------------------------------------
rostered_rps = []
for p in my_rps:
    on_il, status = player_status(p)
    s_all = agg_rp(p.name)
    s_14  = agg_rp(p.name, cutoff=CUT_14) or {}
    s_28  = agg_rp(p.name, cutoff=CUT_28) or {}
    flags = get_flags(s_all)
    rostered_rps.append(dict(
        name=p.name,
        status=status,
        on_il=on_il,
        role=get_role(p.name),
        season=s_all,
        d14=s_14,
        d28=s_28,
        flags=flags,
    ))

# Sort: flagged first, then by SVHD desc
rostered_rps.sort(key=lambda x: (0 if x['flags'] else 1, -(x['season'] or {}).get('SVHD', 0)))


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------
def fmt(val, precision=2):
    if val is None or val == '':
        return '  —  '
    if isinstance(val, float):
        return f'{val:.{precision}f}'
    return str(val)


def stat_row(w):
    if not w:
        return '  —   |  — / —  |  —/G  |   —   |   —   |   —   |   —  '
    svhd_g = w.get('SVHD_G')
    svhd_g_str = f"{svhd_g:.3f}" if svhd_g is not None else '  —  '
    return (
        f"{w.get('SVHD', 0):>4} "
        f"({w.get('SV', 0)}sv/{w.get('HLD', 0)}hld) | "
        f"{svhd_g_str:>5} | "
        f"{fmt(w.get('ERA'), 2):>5} | "
        f"{fmt(w.get('WHIP'), 2):>5} | "
        f"{fmt(w.get('K9'), 2):>5} | "
        f"{fmt(w.get('IP'), 1):>5} | "
        f"{w.get('G', 0):>3}G"
    )


HDR_COLS = ' SVHD  (SV/HLD) | SVHD/G |   ERA |  WHIP |   K/9 |    IP |   G'
HDR_DIV  = ' ' + '-' * len(HDR_COLS)


# ---------------------------------------------------------------------------
# Generate report
# ---------------------------------------------------------------------------
lines = []
a = lines.append

a(f'# RP Replacement Analysis — {TODAY_STR}')
a(f'**Team:** {my_team.team_name}')
a(f'**FanGraphs role data:** {fg_date}')
a(f'**Flags:** LOW_SVHD < {FLAG_SVHD} (with ≥{MIN_APP_FLAG}G) | HIGH_WHIP > {FLAG_WHIP} | HIGH_ERA > {FLAG_ERA}')
a(f'**FA minimum:** {MIN_OUTS_FA} OUTS ({MIN_OUTS_FA/3:.1f} IP) season')
a('')

# ── Section 1: My RPs ──────────────────────────────────────────────────────
a('---')
a('## My Relief Pitchers')
a('')
a(f'{"Player":<26} {"Status":<8} {"Role":<20}  {HDR_COLS}  Flags')
a(f'{"------":<26} {"------":<8} {"----":<20}  {HDR_DIV}')

for rp in rostered_rps:
    flag_str = ', '.join(rp['flags']) if rp['flags'] else '✓'
    role_str = rp['role'] or '—'
    a(f"{rp['name']:<26} {rp['status']:<8} {role_str:<20}  {stat_row(rp['season'])}  {flag_str}")
    if rp['d14']:
        a(f"{'  └ Last 14d':<26} {'':8} {'':20}  {stat_row(rp['d14'])}")
    if rp['d28']:
        a(f"{'  └ Last 28d':<26} {'':8} {'':20}  {stat_row(rp['d28'])}")
    a('')

# ── Section 2: Flagged summary ─────────────────────────────────────────────
flagged = [rp for rp in rostered_rps if rp['flags'] and not rp['on_il']]
a('---')
a('## Flagged RPs (Drop Candidates)')
a('')
if not flagged:
    a('No active RPs meet the drop threshold.')
else:
    for rp in flagged:
        s = rp['season'] or {}
        role_note = f"  [{rp['role']}]" if rp['role'] else ''
        a(f"- **{rp['name']}**{role_note} — {', '.join(rp['flags'])}"
          f"  (Season: SVHD {s.get('SVHD', 0)} [{s.get('SV',0)}SV/{s.get('HLD',0)}HLD], "
          f"ERA {fmt(s.get('ERA'), 2)}, WHIP {fmt(s.get('WHIP'), 2)}, K/9 {fmt(s.get('K9'), 2)})")
a('')

# ── Section 3: Top FA RPs ──────────────────────────────────────────────────
a('---')
a(f'## Top Available RPs  (min {MIN_OUTS_FA} OUTS, ranked SVHD → WHIP → ERA)')
a('')
a(f'{"Player":<26} {"Team":<5} {"Role":<20}  {HDR_COLS}')
a(f'{"------":<26} {"----":<5} {"----":<20}  {HDR_DIV}')

for fa in fa_rps[:20]:
    role_str = fa['role'] or '—'
    a(f"{fa['name']:<26} {fa['team']:<5} {role_str:<20}  {stat_row(fa['season'])}")
    if fa['d14']:
        a(f"{'  └ Last 14d':<26} {'':5} {'':20}  {stat_row(fa['d14'])}")
    if fa['d28']:
        a(f"{'  └ Last 28d':<26} {'':5} {'':20}  {stat_row(fa['d28'])}")
    a('')

# ── Section 4: Recommendations ────────────────────────────────────────────
a('---')
a('## Recommendations')
a('')
if not flagged:
    a('No flagged RPs — no urgent replacements needed.')
else:
    for rp in flagged:
        rp_s = rp['season'] or {}
        role_note = f"  [{rp['role']}]" if rp['role'] else ''
        a(f"### Drop candidate: {rp['name']}{role_note}  [{', '.join(rp['flags'])}]")
        a(f"Season: SVHD {rp_s.get('SVHD',0)} [{rp_s.get('SV',0)}SV/{rp_s.get('HLD',0)}HLD] | "
          f"ERA {fmt(rp_s.get('ERA'),2)} | WHIP {fmt(rp_s.get('WHIP'),2)} | K/9 {fmt(rp_s.get('K9'),2)}")
        a('')
        a('Top replacements:')
        for fa in fa_rps[:5]:
            fa_s = fa['season']
            svhd_d   = fa_s['SVHD']   - rp_s.get('SVHD',   0)
            svhd_g_d = fa_s['SVHD_G'] - rp_s.get('SVHD_G', 0.0)
            whip_d   = fa_s['WHIP']   - rp_s.get('WHIP',   0)
            era_d    = fa_s['ERA']     - rp_s.get('ERA',    0)
            role_note_fa = f" [{fa['role']}]" if fa['role'] else ''
            a(f"  ADD **{fa['name']}** ({fa['team']}){role_note_fa}"
              f"  SVHD {fa_s['SVHD']} ({svhd_d:+d}) | "
              f"SVHD/G {fa_s['SVHD_G']:.3f} ({svhd_g_d:+.3f}) | "
              f"WHIP {fa_s['WHIP']} ({whip_d:+.2f}) | "
              f"ERA {fa_s['ERA']} ({era_d:+.2f})")
        a('')

a('---')
a(f'*Generated {TODAY_STR} | Source: stats_mlb_boxscore_{YEAR}.csv + FanGraphs ({fg_date}) + ESPN API*')

# ── Write report ───────────────────────────────────────────────────────────
os.makedirs(REPORTS_DIR, exist_ok=True)
report_path = os.path.join(REPORTS_DIR, f'rp_analysis_{TODAY_STR}.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\nReport saved to: {report_path}')
print(f'Rostered RPs   : {len(rostered_rps)}')
print(f'Flagged RPs    : {len(flagged)}')
print(f'FA RPs ranked  : {len(fa_rps)}')
print('\n=== DONE ===')
