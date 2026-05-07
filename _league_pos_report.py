"""
League Position Analysis — Report Generation.

Description: Reads _league_pos_results.json and produces a markdown league position
             overview covering positional averages, my team comparison, league rankings,
             and current matchup projections.
Source Data: fantasy_baseball/_league_pos_results.json
Outputs:     fantasy_baseball/reports/league_position_analysis_<YYYY-MM-DD>.md
"""
import json, os
from datetime import date

RESULTS = r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_league_pos_results.json'
OUT_DIR = r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\reports'

with open(RESULTS, encoding='utf-8') as f:
    res = json.load(f)

os.makedirs(OUT_DIR, exist_ok=True)
today = date.today().isoformat()
out_path = os.path.join(OUT_DIR, f'league_position_analysis_{today}.md')

lines = []

def h(txt, level=2):
    lines.append(f'\n{"#" * level} {txt}\n')

def trow(*cells):
    lines.append('| ' + ' | '.join(str(c) for c in cells) + ' |')

def sep(*widths):
    lines.append('|' + '|'.join(['-' * max(w, 3) for w in widths]) + '|')


meta        = res['meta']
my_team     = meta['my_team']
lg_bat      = res['league_bat_ytd']
lg_pit      = res['league_pit_ytd']
my_bat_cmp  = res['my_bat_comparison']
my_pit_cmp  = res['my_pit_comparison']
team_stats  = res['team_stats']
profiles    = res['team_profiles']
rankings    = res['rankings']
projections = res.get('matchup_projections', [])

BAT_SLOT_ORDER = ['C', '1B', '1B/3B', '2B', '2B/SS', '3B', 'SS', 'OF', 'UTIL']
PIT_SLOT_ORDER = ['SP', 'RP']
CATS_ORDER     = ['R', 'HR', 'RBI', 'SB', 'OPS', 'ERA', 'WHIP', 'K9', 'QS', 'SVHD']

# ── Title ─────────────────────────────────────────────────────────────────────
lines.append(f'# Fantasy Baseball — League Position Overview — {today}')
lines.append(
    f'\n**My Team:** {my_team} | **League:** 5x5 H2H Each Category | '
    f'**Season:** {meta["season"]} | **Data through:** {meta["latest_data"]} | '
    f'**Days tracked:** {meta["total_days"]}\n'
)
lines.append(
    '> Stats are from **active roster slots only** — Bench (BE) and IL rows are excluded. '
    'Rate stats (OPS, ERA, WHIP, K/9) are computed from aggregated counting components, '
    'not averaged.\n'
)

# ── Section 1a: League Position Averages — YTD ───────────────────────────────
h('League Position Averages — Year to Date')
lines.append(
    '> Total production accumulated in each lineup slot across all 12 teams. '
    'Use this to understand the scale of contribution expected from each slot.\n'
)

h('Batting Slots', 3)
trow('Slot', 'Slot-Days', 'R', 'HR', 'RBI', 'SB', 'OPS')
sep(12, 10, 6, 6, 6, 6, 7)
for slot in BAT_SLOT_ORDER:
    s = lg_bat.get(slot)
    if not s:
        continue
    trow(slot, s['slot_days'], s['R'], s['HR'], s['RBI'], s['SB'], f'{s["OPS"]:.3f}')

h('Pitching Slots', 3)
trow('Slot', 'Slot-Days', 'ERA', 'WHIP', 'K/9', 'QS', 'SVHD')
sep(6, 10, 7, 7, 7, 6, 7)
for slot in PIT_SLOT_ORDER:
    s = lg_pit.get(slot)
    if not s:
        continue
    trow(slot, s['slot_days'], f'{s["ERA"]:.2f}', f'{s["WHIP"]:.2f}',
         f'{s["K9"]:.2f}', s['QS'], s['SVHD'])

# ── Section 1b: League Position Averages — Daily ─────────────────────────────
h('League Position Averages — Per Slot-Day')
lines.append(
    '> YTD totals divided by slot-days. '
    'This is the expected stat contribution per team per day for each slot.\n'
)

h('Batting Slots', 3)
trow('Slot', 'Slot-Days', 'R/day', 'HR/day', 'RBI/day', 'SB/day', 'OPS')
sep(12, 10, 7, 7, 8, 7, 7)
for slot in BAT_SLOT_ORDER:
    s = lg_bat.get(slot)
    if not s or s['slot_days'] == 0:
        continue
    d = s['slot_days']
    trow(slot, d, f'{s["R"]/d:.3f}', f'{s["HR"]/d:.3f}',
         f'{s["RBI"]/d:.3f}', f'{s["SB"]/d:.3f}', f'{s["OPS"]:.3f}')

h('Pitching Slots', 3)
trow('Slot', 'Slot-Days', 'ERA', 'WHIP', 'K/9', 'QS/day', 'SVHD/day')
sep(6, 10, 7, 7, 7, 8, 9)
for slot in PIT_SLOT_ORDER:
    s = lg_pit.get(slot)
    if not s or s['slot_days'] == 0:
        continue
    d = s['slot_days']
    trow(slot, d, f'{s["ERA"]:.2f}', f'{s["WHIP"]:.2f}',
         f'{s["K9"]:.2f}', f'{s["QS"]/d:.3f}', f'{s["SVHD"]/d:.3f}')

# ── Section 2: My Team vs League ─────────────────────────────────────────────
h(f'My Team — {my_team} vs League Average')
lines.append(
    '> **League avg** = league total / 12 teams (per-team average). '
    'Rate stats (OPS, ERA, WHIP, K/9) use aggregated components — the same rate the league '
    'achieves as a whole.\n'
    '> **Fill Rate** = % of season days where the slot had a player actively rostered. '
    '**Empty Days** = days that slot had no stats collected (no game or slot unfilled).\n'
    '> ⚠ = Fill Rate below 80% or 3+ scoring categories below league average.\n'
)

h('Batting Slots', 3)
trow('Slot', 'Fill%', 'EmptyDays',
     'R (me/lg)', 'HR (me/lg)', 'RBI (me/lg)', 'SB (me/lg)', 'OPS (me/lg)', 'Deficits')
sep(12, 6, 10, 12, 12, 13, 12, 15, 9)
weak_bat = []
for slot in BAT_SLOT_ORDER:
    c = my_bat_cmp.get(slot)
    if not c:
        continue
    my_s, lg_s = c['my'], c['lg']
    fill  = c['fill_rate']
    empty = c['empty_days']
    defs  = c['deficits']
    flag  = ' ⚠' if fill < 80 or defs >= 3 else ''
    if fill < 80 or defs >= 3:
        weak_bat.append((slot, fill, defs, empty))
    trow(
        f'{slot}{flag}', f'{fill}%', empty,
        f'{my_s["R"]}/{lg_s["R"]}',
        f'{my_s["HR"]}/{lg_s["HR"]}',
        f'{my_s["RBI"]}/{lg_s["RBI"]}',
        f'{my_s["SB"]}/{lg_s["SB"]}',
        f'{my_s["OPS"]:.3f}/{lg_s["OPS"]:.3f}',
        f'{defs}/5',
    )

h('Pitching Slots', 3)
trow('Slot', 'Fill%', 'EmptyDays',
     'ERA (me/lg)', 'WHIP (me/lg)', 'K/9 (me/lg)', 'QS (me/lg)', 'SVHD (me/lg)', 'Deficits')
sep(6, 6, 10, 14, 14, 14, 13, 14, 9)
weak_pit = []
for slot in PIT_SLOT_ORDER:
    c = my_pit_cmp.get(slot)
    if not c:
        continue
    my_s, lg_s = c['my'], c['lg']
    fill  = c['fill_rate']
    empty = c['empty_days']
    defs  = c['deficits']
    flag  = ' ⚠' if fill < 80 or defs >= 3 else ''
    if fill < 80 or defs >= 3:
        weak_pit.append((slot, fill, defs, empty))
    trow(
        f'{slot}{flag}', f'{fill}%', empty,
        f'{my_s["ERA"]:.2f}/{lg_s["ERA"]:.2f}',
        f'{my_s["WHIP"]:.2f}/{lg_s["WHIP"]:.2f}',
        f'{my_s["K9"]:.2f}/{lg_s["K9"]:.2f}',
        f'{my_s["QS"]}/{lg_s["QS"]}',
        f'{my_s["SVHD"]}/{lg_s["SVHD"]}',
        f'{defs}/5',
    )

h('Positional Weakness Summary', 3)
if weak_bat or weak_pit:
    for slot, fill, defs, empty in weak_bat:
        lines.append(
            f'- **{slot}** (batting): {defs}/5 categories below league avg, '
            f'{fill}% fill rate, {empty} empty days'
        )
    for slot, fill, defs, empty in weak_pit:
        lines.append(
            f'- **{slot}** (pitching): {defs}/5 categories below league avg, '
            f'{fill}% fill rate, {empty} empty days'
        )
else:
    lines.append('- No significant positional weaknesses detected.')

# ── Section 3: League Category Rankings ──────────────────────────────────────
h('League Category Rankings')
lines.append(
    '> Rank 1 = best in league for each category. ERA and WHIP: lower rank = lower (better) value. '
    f'**{my_team}** is highlighted.\n'
)

trow('Team', *CATS_ORDER)
sep(30, *([7] * len(CATS_ORDER)))
for team in sorted(team_stats.keys()):
    marker = ' **' if team == my_team else ''
    rank_cells = [f'#{rankings[c][team]}' for c in CATS_ORDER]
    trow(f'{team}{marker}', *rank_cells)

lines.append('')

h('Team Strength Profiles', 3)
lines.append(
    '> Top 3 = categories where each team ranks highest. Bottom 3 = weakest categories.\n'
)
for team in sorted(profiles.keys()):
    prof   = profiles[team]
    marker = ' *(my team)*' if team == my_team else ''
    top    = ', '.join(f'{c} (#{prof["ranks"][c]})' for c in prof['top3'])
    bot    = ', '.join(f'{c} (#{prof["ranks"][c]})' for c in prof['bot3'])
    lines.append(f'\n**{team}**{marker}  ')
    lines.append(f'Strong: {top}  ')
    lines.append(f'Weak:   {bot}')

# ── Section 4: Current Matchup Projections ────────────────────────────────────
h('Current Matchup Projections')
if not projections:
    lines.append('> Matchup data unavailable — ESPN API fetch failed.\n')
else:
    mp_period  = meta.get('matchup_period', projections[0].get('matchup_period', '?'))
    proj_days  = meta.get('proj_days', 7)
    mp_end     = meta.get('matchup_end', '')
    end_note   = f', through {mp_end}' if mp_end else ''
    lines.append(
        f'> **Week {mp_period}** — {proj_days} day(s) remaining{end_note}. '
        'Projected totals based on each team\'s season daily average. '
        'Counting stats (R, HR, RBI, SB, QS, SVHD) = daily avg x remaining days. '
        'Rate stats (OPS, ERA, WHIP, K/9) = season aggregate rate. '
        '**W** marks the projected category winner.\n'
    )
    for m in projections:
        home      = m['home']
        away      = m['away']
        home_wins = m['home_wins']
        away_wins = m['away_wins']
        h(f'{home} vs {away}', 3)
        trow('Category', home, away, 'Edge')
        sep(8, 30, 30, 30)
        for c in m['categories']:
            hv   = c['home_val']
            av   = c['away_val']
            edge = c['edge']
            fmt  = '.3f' if isinstance(hv, float) and hv != int(hv) else 'd' if isinstance(hv, int) else ''
            hv_s = (f'{hv:.3f}' if c['cat'] in ('OPS', 'ERA', 'WHIP', 'K9') else str(hv))
            av_s = (f'{av:.3f}' if c['cat'] in ('OPS', 'ERA', 'WHIP', 'K9') else str(av))
            hv_s += ' **W**' if edge == home else ''
            av_s += ' **W**' if edge == away else ''
            trow(c['cat'], hv_s, av_s, edge if edge != 'Tie' else 'Tie')
        lines.append(
            f'\n**Projected: {home} {home_wins} — {away_wins} {away}**\n'
        )

lines.append(
    f'\n---\n'
    f'*Generated {today} | '
    f'Data through {meta["latest_data"]} | '
    f'Active roster slots only (BE/IL excluded)*\n'
)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Report saved to: {out_path}')
