"""
analyze_sp_replacements.py
===========================
Description: Deep-dive SP replacement analysis. Calculates QS, WHIP, and K/9
             for every rostered SP and available FA SP across three windows
             (season, last 28 days, last 14 days) using the MLB boxscore data.
             Flags underperforming rostered SPs and ranks FA replacements by
             the league's priority stat order: QS desc → WHIP asc → K/9 desc.

Source Data: data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_{year}.csv
             ESPN API (roster, FA list, injury status)

Outputs: fantasy_baseball/reports/sp_analysis_{YYYY-MM-DD}.md
"""

import csv
import os
import sys
import json
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
YEAR         = 2026
TODAY        = date.today()
TODAY_STR    = TODAY.isoformat()
CUT_14       = (TODAY - timedelta(days=14)).isoformat()
CUT_28       = (TODAY - timedelta(days=28)).isoformat()

BASE         = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'
REPORTS_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reports')

MIN_OUTS_FA      = 20    # minimum season OUTS to qualify as a real SP option
MIN_GS_FLAG      = 3     # minimum starts before applying flags to rostered SPs
FLAG_QS_RATE     = 0.30  # below this QS/GS rate → LOW_QS flag
FLAG_WHIP        = 1.45  # above this → HIGH_WHIP flag
FLAG_K9          = 7.0   # below this → LOW_K9 flag

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

my_sps = [
    p for p in my_roster
    if 'SP' in p.eligibleSlots and not any(s in HITTER_SLOTS for s in p.eligibleSlots)
]


# ---------------------------------------------------------------------------
# Load boxscore — pitcher rows only
# ---------------------------------------------------------------------------
box_path = os.path.join(BASE, f'stats_mlb_boxscore_{YEAR}.csv')
with open(box_path, encoding='utf-8') as f:
    all_pitcher_rows = [
        r for r in csv.DictReader(f)
        if r['b_or_p'] == 'pitcher'
    ]

# Pre-index by normalised name for fast lookup
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


def agg_sp(name, cutoff=None):
    """
    Aggregate SP stats for a player from the boxscore CSV.
    Only counts rows where GS=1 (started games).
    cutoff: ISO date string — only include rows on or after this date.
    Returns None if the player has no qualifying rows.
    """
    norm = mp.normalize_player_name(name)
    rows = name_index.get(norm, [])
    # GS=1 rows are always actual appearances; did_play filter is redundant but explicit
    rows = [r for r in rows if _safe_int(r.get('GS', 0)) == 1 and
            (r.get('did_play') == '1' or _safe_int(r.get('OUTS', 0)) > 0)]
    if cutoff:
        rows = [r for r in rows if r['date'] >= cutoff]
    if not rows:
        return None

    gs   = len(rows)
    qs   = sum(_safe_int(r.get('QS',   0)) for r in rows)
    outs = sum(_safe_int(r.get('OUTS', 0)) for r in rows)
    er   = sum(_safe_int(r.get('ER',   0)) for r in rows)
    ph   = sum(_safe_int(r.get('P_H',  0)) for r in rows)
    pbb  = sum(_safe_int(r.get('P_BB', 0)) for r in rows)
    k    = sum(_safe_int(r.get('K',    0)) for r in rows)

    ip   = outs / 3
    era  = (er  * 27) / outs if outs else 0.0
    whip = (ph + pbb) / ip   if ip   else 0.0
    k9   = (k   * 27) / outs if outs else 0.0
    qs_r = qs / gs           if gs   else 0.0

    return dict(
        GS=gs, QS=qs, QS_rate=round(qs_r, 2),
        IP=round(ip, 1), OUTS=outs,
        ERA=round(era, 2), WHIP=round(whip, 2), K9=round(k9, 2),
    )


# ---------------------------------------------------------------------------
# Player injury / status helper (mirrors run_roster_analysis.py)
# ---------------------------------------------------------------------------
def player_status(p):
    inj = (getattr(p, 'injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    on_il = 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION')
    if on_il:   return True,  '[IL]'
    if inj == 'DAY_TO_DAY': return False, 'DTD'
    if inj not in ('ACTIVE', ''): return False, inj
    return False, 'Active'


# ---------------------------------------------------------------------------
# Flag helper for rostered SPs
# ---------------------------------------------------------------------------
def get_flags(season_stats):
    flags = []
    if season_stats is None:
        return ['NO_DATA']
    if season_stats['GS'] >= MIN_GS_FLAG:
        if season_stats['QS_rate'] < FLAG_QS_RATE:
            flags.append('LOW_QS')
        if season_stats['WHIP'] > FLAG_WHIP:
            flags.append('HIGH_WHIP')
        if season_stats['K9'] < FLAG_K9:
            flags.append('LOW_K9')
    return flags


# ---------------------------------------------------------------------------
# FA SP fetch
# ---------------------------------------------------------------------------
all_fa_raw = mp.get_free_agents(league, position_ids=[14, 15], size=300)

_seen = set()
fa_sps_raw = []
for fa in all_fa_raw:
    if fa['name'] in _seen:
        continue
    _seen.add(fa['name'])
    if 'SP' not in fa.get('eligibleSlots', []):
        continue
    inj = (fa.get('injuryStatus', 'ACTIVE') or 'ACTIVE').upper()
    if 'DL' in inj or inj in ('INJURY_RESERVE', 'OUT', 'SUSPENSION'):
        continue
    fa_sps_raw.append(fa)

# Calculate stats from boxscore for each FA SP
fa_sps = []
for fa in fa_sps_raw:
    s_all = agg_sp(fa['name'])
    if s_all is None:
        continue
    if s_all['OUTS'] < MIN_OUTS_FA:
        continue
    s_14 = agg_sp(fa['name'], cutoff=CUT_14) or {}
    s_28 = agg_sp(fa['name'], cutoff=CUT_28) or {}
    fa_sps.append(dict(
        name=fa['name'],
        team=fa.get('proTeam', '?'),
        season=s_all,
        d14=s_14,
        d28=s_28,
    ))

# Sort: QS desc → WHIP asc → K/9 desc
fa_sps.sort(key=lambda x: (
    -x['season']['QS'],
     x['season']['WHIP'],
    -x['season']['K9'],
))


# ---------------------------------------------------------------------------
# Build rostered SP data
# ---------------------------------------------------------------------------
rostered_sps = []
for p in my_sps:
    on_il, status = player_status(p)
    s_all = agg_sp(p.name)
    s_14  = agg_sp(p.name, cutoff=CUT_14) or {}
    s_28  = agg_sp(p.name, cutoff=CUT_28) or {}
    flags = get_flags(s_all)
    rostered_sps.append(dict(
        name=p.name,
        status=status,
        on_il=on_il,
        season=s_all,
        d14=s_14,
        d28=s_28,
        flags=flags,
    ))

# Sort roster SPs: flagged first, then by season QS desc
rostered_sps.sort(key=lambda x: (0 if x['flags'] else 1, -(x['season'] or {}).get('QS', 0)))


# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------
def fmt_stat(val, precision=2):
    if val is None or val == '':
        return '  —  '
    if isinstance(val, float):
        return f'{val:.{precision}f}'
    return str(val)


def stat_row(window_stats):
    """Format a single stat window into a display string."""
    if not window_stats:
        return '  —   |   —   |   —   |  —  |   —  '
    qs_disp = f"{window_stats.get('QS', 0)}/{window_stats.get('GS', 0)}"
    return (
        f"{qs_disp:>6} "
        f"({fmt_stat(window_stats.get('QS_rate'), 2)}) | "
        f"{fmt_stat(window_stats.get('ERA'), 2):>5} | "
        f"{fmt_stat(window_stats.get('WHIP'), 2):>5} | "
        f"{fmt_stat(window_stats.get('K9'), 2):>5} | "
        f"{fmt_stat(window_stats.get('IP'), 1):>5}"
    )


HDR_COLS = '  QS/GS  (rate) |   ERA |  WHIP |   K/9 |    IP'
HDR_DIV  = '  ' + '-' * len(HDR_COLS)


# ---------------------------------------------------------------------------
# Generate report
# ---------------------------------------------------------------------------
lines = []
a = lines.append

a(f'# SP Replacement Analysis — {TODAY_STR}')
a(f'**Team:** {my_team.team_name}')
a(f'**Flags:** LOW_QS = QS/GS < {FLAG_QS_RATE:.0%} | HIGH_WHIP > {FLAG_WHIP} | LOW_K9 < {FLAG_K9}')
a(f'**FA minimum:** {MIN_OUTS_FA} OUTS ({MIN_OUTS_FA/3:.1f} IP) season  |  At least 1 GS')
a('')

# ── Section 1: My SPs ──────────────────────────────────────────────────────
a('---')
a('## My Starting Pitchers')
a('')
a(f'{"Player":<26} {"Status":<8}  {HDR_COLS}  Flags')
a(f'{"------":<26} {"------":<8}  {HDR_DIV}')

for sp in rostered_sps:
    flag_str = ', '.join(sp['flags']) if sp['flags'] else '✓'
    status   = f"{'[IL] ' if sp['on_il'] else ''}{sp['status']}"
    name_col = f"{sp['name']:<26}"

    # Season
    a(f"{name_col} {status:<8}  {stat_row(sp['season'])}  {flag_str}")
    # 14d
    if sp['d14']:
        a(f"{'  └ Last 14d':<26} {'':8}  {stat_row(sp['d14'])}")
    # 28d
    if sp['d28']:
        a(f"{'  └ Last 28d':<26} {'':8}  {stat_row(sp['d28'])}")
    a('')

# ── Section 2: Flagged summary ─────────────────────────────────────────────
flagged = [sp for sp in rostered_sps if sp['flags'] and not sp['on_il']]
a('---')
a('## Flagged SPs (Drop Candidates)')
a('')
if not flagged:
    a('No active SPs meet the drop threshold.')
else:
    for sp in flagged:
        s = sp['season'] or {}
        a(f"- **{sp['name']}** — {', '.join(sp['flags'])}"
          f"  (Season: QS {s.get('QS',0)}/{s.get('GS',0)}, "
          f"ERA {fmt_stat(s.get('ERA'),2)}, "
          f"WHIP {fmt_stat(s.get('WHIP'),2)}, "
          f"K/9 {fmt_stat(s.get('K9'),2)})")
a('')

# ── Section 3: Top FA SPs ──────────────────────────────────────────────────
a('---')
a(f'## Top Available SPs  (min {MIN_OUTS_FA} OUTS season, ranked QS → WHIP → K/9)')
a('')
a(f'{"Player":<26} {"Team":<5}  {HDR_COLS}')
a(f'{"------":<26} {"----":<5}  {HDR_DIV}')

for fa in fa_sps[:20]:
    team_col = f"{fa['team']:<5}"
    a(f"{fa['name']:<26} {team_col}  {stat_row(fa['season'])}")
    if fa['d14']:
        a(f"{'  └ Last 14d':<26} {'':5}  {stat_row(fa['d14'])}")
    if fa['d28']:
        a(f"{'  └ Last 28d':<26} {'':5}  {stat_row(fa['d28'])}")
    a('')

# ── Section 4: Recommendations ────────────────────────────────────────────
a('---')
a('## Recommendations')
a('')
if not flagged:
    a('No flagged SPs — no urgent replacements needed.')
else:
    for sp in flagged:
        sp_s = sp['season'] or {}
        a(f"### Drop candidate: {sp['name']}  [{', '.join(sp['flags'])}]")
        a(f"Season: QS {sp_s.get('QS',0)}/{sp_s.get('GS',0)} | "
          f"ERA {fmt_stat(sp_s.get('ERA'),2)} | "
          f"WHIP {fmt_stat(sp_s.get('WHIP'),2)} | "
          f"K/9 {fmt_stat(sp_s.get('K9'),2)}")
        a('')
        a('Top replacements:')
        for fa in fa_sps[:5]:
            fa_s = fa['season']
            qs_delta  = fa_s['QS']  - sp_s.get('QS',  0)
            whip_delta= fa_s['WHIP']- sp_s.get('WHIP', 0)
            k9_delta  = fa_s['K9']  - sp_s.get('K9',   0)
            qs_d_str  = f"+{qs_delta}"   if qs_delta  >= 0 else str(qs_delta)
            whip_d_str= f"{whip_delta:+.2f}"
            k9_d_str  = f"{k9_delta:+.2f}"
            a(f"  ADD **{fa['name']}** ({fa['team']})"
              f"  QS {fa_s['QS']} ({qs_d_str}) | "
              f"WHIP {fa_s['WHIP']} ({whip_d_str}) | "
              f"K/9 {fa_s['K9']} ({k9_d_str})")
        a('')

a('---')
a(f'*Generated {TODAY_STR} | Source: stats_mlb_boxscore_{YEAR}.csv + ESPN API*')

# ── Write report ───────────────────────────────────────────────────────────
os.makedirs(REPORTS_DIR, exist_ok=True)
report_path = os.path.join(REPORTS_DIR, f'sp_analysis_{TODAY_STR}.md')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

print(f'\nReport saved to: {report_path}')
print(f'Rostered SPs   : {len(rostered_sps)}')
print(f'Flagged SPs    : {len(flagged)}')
print(f'FA SPs ranked  : {len(fa_sps)}')

# ── Write run log ─────────────────────────────────────────────────────────
try:
    _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'data-lake', '00_Logs', 'fantasy_baseball')
    os.makedirs(_log_dir, exist_ok=True)
    _entry = {
        'ts'               : datetime.now().isoformat(timespec='seconds'),
        'workflow'         : 'fantasy-sp-analysis',
        'status'           : 'ok',
        'report_path'      : report_path,
        'report_size_bytes': os.path.getsize(report_path),
        'flagged_sps'      : len(flagged),
        'fa_sps_ranked'    : len(fa_sps),
    }
    with open(os.path.join(_log_dir, 'fantasy-sp-analysis.jsonl'), 'a', encoding='utf-8') as _f:
        _f.write(json.dumps(_entry) + '\n')
    print(f'Run log updated: {os.path.join(_log_dir, "fantasy-sp-analysis.jsonl")}')
except Exception as _e:
    print(f'[WARN] run-log write failed: {_e}')

print('\n=== DONE ===')
