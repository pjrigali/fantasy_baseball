"""Step 9: Generate markdown roster analysis report."""
import json, os
from datetime import date

with open(r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_analysis_results.json', encoding='utf-8') as f:
    res = json.load(f)

today = date.today().isoformat()
out_dir = r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\reports'
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, f'roster_analysis_{today}.md')

lines = []

def h(txt, level=2): lines.append(f'\n{"#"*level} {txt}\n')
def trow(*cells): lines.append('| ' + ' | '.join(str(c) for c in cells) + ' |')
def sep(*widths): lines.append('|' + '|'.join(['-'*max(w,3) for w in widths]) + '|')

lines.append(f'# Fantasy Roster Analysis — {today}')
lines.append(f'\n**Team:** Datalickmyballs | **League:** 5x5 H2H Each Category | **Season:** 2026\n')
lines.append('> IL players are shown for completeness but excluded from active replacement priority.\n')

# ── Batter Stats ─────────────────────────────────────────────────────────────
h('My Roster — Batter Stats')
trow('Name','Pos','G','AB','R','HR','RBI','SB','OPS','AVG','ProjOPS','PrevOPS','AvgBO','Status','Flag')
sep(25,12,4,4,4,4,4,4,6,6,8,8,6,12,4)
for b in res['batter_stats']:
    bo   = res['batter_bo'].get(b['name'])
    bo_s = f'{bo:.1f}' if bo else 'N/A'
    flag = '⚠' if (b['OPS'] < 0.650 or b['AVG'] < 0.180) and not b.get('onIL') else ''
    il   = '[IL]' if b.get('onIL') else b.get('injuryStatus','ACTIVE') if b.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(b['name'], b['slots'], b['G'], b['AB'], b['R'], b['HR'], b['RBI'], b['SB'],
         f'{b["OPS"]:.3f}', f'{b["AVG"]:.3f}', f'{b["ProjOPS"]:.3f}', f'{b["PrevOPS"]:.3f}',
         bo_s, il, flag)

# ── SP Stats ──────────────────────────────────────────────────────────────────
h('My Roster — SP Stats')
trow('Name','G','GS','IP','ERA','WHIP','K/9','QS','ProjERA','PrevERA','Status','Flag')
sep(22,4,4,6,6,6,6,4,8,8,14,4)
for s in res['sp_stats']:
    flag = '⚠' if (s['ERA'] > 5.0 or s['WHIP'] > 1.50 or s['K9'] < 6.0) and not s.get('onIL') else ''
    il   = '[IL]' if s.get('onIL') else s.get('injuryStatus','ACTIVE') if s.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(s['name'], s['G'], s['GS'], f'{s["IP"]:.1f}', f'{s["ERA"]:.2f}',
         f'{s["WHIP"]:.2f}', f'{s["K9"]:.2f}', s['QS'],
         f'{s["ProjERA"]:.2f}', f'{s["PrevERA"]:.2f}', il, flag)

# ── RP Stats ──────────────────────────────────────────────────────────────────
h('My Roster — RP Stats')
trow('Name','G','IP','SV','HLD','SVHD','ERA','WHIP','K/9','Status','Flag')
sep(22,4,6,4,5,6,6,6,6,14,4)
for r in res['rp_stats']:
    flag = '⚠' if (r['ERA'] > 5.0 or r['WHIP'] > 1.50 or r['SVHD'] < 5) and not r.get('onIL') else ''
    il   = '[IL]' if r.get('onIL') else r.get('injuryStatus','ACTIVE') if r.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(r['name'], r['G'], f'{r["IP"]:.1f}', r['SV'], r['HLD'], r['SVHD'],
         f'{r["ERA"]:.2f}', f'{r["WHIP"]:.2f}', f'{r["K9"]:.2f}', il, flag)

# ── Batting Order Summary ─────────────────────────────────────────────────────
h('Batting Order Summary (Last 7 Days)')
trow('Name','Avg BO Position','Games in Lineup','Status')
sep(25,16,16,12)
for b in res['batter_stats']:
    bo   = res['batter_bo'].get(b['name'])
    bo_s = f'{bo:.1f}' if bo else 'N/A'
    il   = '[IL]' if b.get('onIL') else 'Active'
    trow(b['name'], bo_s, res['batter_bo'].get(b['name']+'_games', 'N/A') if False else '—', il)

# ── Weakest Players ───────────────────────────────────────────────────────────
h('Weakest Players')
lines.append('> Active underperformers listed first. IL players are valid drop candidates but not replacement priorities.\n')

h('Weak Batters', 3)
trow('Name','OPS','AVG','R','HR','RBI','SB','Status','Reason')
sep(25,6,6,4,4,4,4,14,45)
for b in res['weak_batters']:
    il = '[IL]' if b.get('onIL') else b.get('injuryStatus','Active') if b.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(b['name'], f'{b["OPS"]:.3f}', f'{b["AVG"]:.3f}',
         b['R'], b['HR'], b['RBI'], b['SB'], il, b['reasons'])

h('Weak SPs', 3)
trow('Name','ERA','WHIP','K/9','QS','GS','Status','Reason')
sep(22,6,6,6,4,4,14,40)
for s in res['weak_sps']:
    il = '[IL]' if s.get('onIL') else s.get('injuryStatus','Active') if s.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(s['name'], f'{s["ERA"]:.2f}', f'{s["WHIP"]:.2f}',
         f'{s["K9"]:.2f}', s['QS'], s['GS'], il, s['reasons'])

h('Weak RPs', 3)
trow('Name','ERA','WHIP','SVHD','Status','Reason')
sep(22,6,6,6,14,40)
for r in res['weak_rps']:
    il = '[IL]' if r.get('onIL') else r.get('injuryStatus','Active') if r.get('injuryStatus') not in ('ACTIVE','') else 'Active'
    trow(r['name'], f'{r["ERA"]:.2f}', f'{r["WHIP"]:.2f}', r['SVHD'], il, r['reasons'])

# ── Top FAs ───────────────────────────────────────────────────────────────────
lines.append('\n> All free agents listed below are **active/healthy** — injured and IL players are excluded.\n')

lines.append('> pR/pHR/pRBI/pSB = full-season pace projections from current stats. Cat = categories scored (R>=60, HR>=15, RBI>=55, SB>=10, OPS>=.750). LU = lineup appearances (last 14 days).\n')
h('Top Free Agents — Batters')
trow('Name','Team','Pos','AB','pR','pHR','pRBI','pSB','OPS','ProjOPS','Cat','Comp','AvgBO','LU','Note')
sep(25,6,10,4,4,4,5,4,6,8,4,6,6,4,12)
for fa in res['fa_batters']:
    note = 'small sample' if fa['ab'] < 15 else ''
    bo_s = f'{fa["avg_bo"]:.1f}' if fa.get('avg_bo') else 'N/A'
    trow(fa['name'], fa['team'], fa['pos'], int(fa['ab']),
         fa.get('pace_r', int(fa['r'])), fa.get('pace_hr', int(fa['hr'])),
         fa.get('pace_rbi', int(fa['rbi'])), fa.get('pace_sb', int(fa['sb'])),
         f'{fa["ops"]:.3f}', f'{fa["proj_ops"]:.3f}',
         fa.get('cat_score', '—'), f'{fa["composite"]:.3f}' if 'composite' in fa else '—',
         bo_s, fa.get('lineup_games', '—'), note)

h('Top Free Agents — SPs')
trow('Name','Team','G','GS','IP','ERA','WHIP','K/9','QS','ProjERA','Note')
sep(25,6,4,4,6,6,6,6,4,8,10)
for fa in res['fa_sps']:
    note = 'small sample' if fa['IP'] < 5 else ''
    trow(fa['name'], fa['team'], fa['G'], fa['GS'], f'{fa["IP"]:.1f}',
         f'{fa["ERA"]:.2f}', f'{fa["WHIP"]:.2f}', f'{fa["K9"]:.2f}',
         fa['QS'], f'{fa["ProjERA"]:.2f}', note)

h('Top Free Agents — RPs')
trow('Name','Team','G','IP','SV','HLD','SVHD','ERA','WHIP','K/9','ProjSVHD')
sep(25,6,4,6,4,5,6,6,6,6,10)
for fa in res['fa_rps']:
    trow(fa['name'], fa['team'], fa['G'], f'{fa["IP"]:.1f}', fa['SV'], fa['HLD'],
         fa['SVHD'], f'{fa["ERA"]:.2f}', f'{fa["WHIP"]:.2f}', f'{fa["K9"]:.2f}',
         f'{fa["ProjSVHD"]:.1f}')

# ── 8A: Position-by-Position ──────────────────────────────────────────────────
h('Recommended Moves — Position by Position (8A)')
lines.append('> Best swap within each position group. Ranked by 5-cat score then composite OPS. IL players on the drop side are lower priority.\n')

h('Batter Replacements', 3)
trow('Drop','Drop Status','Add','Slot','OPS d','Cat','pR','pHR','pRBI','pSB','Note')
sep(25,12,25,8,8,4,4,4,5,4,20)
for r in res.get('recs_8a_batters', []):
    trow(r['drop'], r['drop_status'], r['add'], r['slot'],
         f'{r["ops_delta"]:+.3f}', r['cat_score'],
         r['pace_r'], r['pace_hr'], r['pace_rbi'], r['pace_sb'], r.get('note',''))

h('SP Replacements', 3)
trow('Drop','Drop Status','Add','ERA d','K/9','QS','Note')
sep(22,16,25,8,6,4,20)
for r in res.get('recs_8a_sps', []):
    trow(r['drop'], r['drop_status'], r['add'],
         f'{r["era_delta"]:+.2f}', f'{r["k9"]:.2f}', r['qs'], r.get('note',''))

h('RP Replacements', 3)
trow('Drop','Drop Status','Add','SVHD d','ERA d','Note')
sep(22,12,25,8,8,30)
for r in res.get('recs_8a_rps', []):
    trow(r['drop'], r['drop_status'], r['add'],
         f'{r["svhd_delta"]:+}', f'{r["era_delta"]:+.2f}', r.get('note',''))

# ── 8B: Position-Agnostic ────────────────────────────────────────────────────
h('Recommended Moves — Position Agnostic (8B)')
lines.append('> Highest-impact swaps regardless of position. Ranked by 5-cat score. Pace projections at full-season rate.\n')

trow('Drop','Drop Type','Drop Status','Add','Add Type','Cat','Comp','Net Category Impact')
sep(25,10,12,25,10,4,6,60)
for r in res.get('recs_8b', []):
    bo_s = f'{r["avg_bo"]:.1f}' if r.get('avg_bo') else 'N/A'
    trow(r['drop'], r['drop_type'], r['drop_status'], r['add'], r['add_type'],
         r['cat_score'], f'{r["composite"]:.3f}' if r['composite'] else 'N/A', r['impact'])

recs_8b_data = res.get('recs_8b', [])
bat_adds = [r for r in recs_8b_data if r['add_type'] == 'BAT']
rp_adds  = [r for r in recs_8b_data if r['add_type'] == 'RP']
svhd_lost = sum(int(r.get('svhd_lost', 0)) for r in recs_8b_data if r['add_type'] == 'BAT')
lines.append('\n**Combined scenario (all agnostic swaps):**')
lines.append(f'- {len(bat_adds)} batters added: {", ".join(r["add"] for r in bat_adds)}')
lines.append(f'- {len(rp_adds)} RP(s) upgraded: {", ".join(r["add"] for r in rp_adds) or "none"}')
lines.append('- Note: Dropping multiple RPs reduces saves/holds coverage — consider a partial swap first')

# ── Key Takeaways ─────────────────────────────────────────────────────────────
h('Key Takeaways')
takeaways = [
    '**Drop Edwin Diaz immediately.** He is on the IL with a 10.50 ERA and 2.33 WHIP. No reason to hold. Jakob Junis (1.76 ERA, 8 SVHD) or Hogan Harris (2.79 ERA, 7 SVHD, ProjSVHD=18) are strong active replacements sitting on waivers.',
    '**Trevor Story and Brenton Doyle are the most urgent active batter drops.** Story at .529 OPS and Doyle at .555 OPS are dragging down R, HR, and OPS categories. Ezequiel Duran (SS, .889 OPS, 4 SB) and Carson Kelly (C, .826 OPS) are direct active upgrades.',
    '**Giancarlo Stanton and Luis Robert Jr. are on IL — monitor their return timelines.** If either is out more than 2 more weeks, they become drop candidates. For now hold if you have IL slots occupied; add Kyle Isbel or Dominic Canzone as temporary fill-ins if needed.',
    '**Logan Webb is Day-to-Day with a 5.06 ERA — watch closely.** His 3.31 ProjERA suggests talent is there, but if he misses a start, Nick Martinez (1.71 ERA, 4 QS) is a strong active FA pickup to bridge the gap.',
    '**Your RP corps has real upside concerns.** Garrett Whitlock (ProjSVHD=33) and Brad Keller (ProjSVHD=28) are the highest-ceiling active RPs available. Adding one by dropping Santana or Hoffman meaningfully upgrades your SVHD ceiling without gutting the bullpen.',
]
for i, t in enumerate(takeaways, 1):
    lines.append(f'\n{i}. {t}')

lines.append(f'\n---\n*Generated {today} | Data current through {today} | Active FAs only*\n')

with open(out_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f'Report saved to: {out_path}')
