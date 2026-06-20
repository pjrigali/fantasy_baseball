"""
Description: Builds {YEAR}_espn_roster_history.csv tracking each player's ownership period on
             each fantasy team. Reconstructs periods from draft picks (initial roster) and
             activity events (FA ADDED opens a period, DROPPED closes it). MOVED events
             (lineup slot changes) are ignored. Players still on a roster get end_date = ''.
Source Data: {YEAR}_espn_draft_results.csv, {YEAR}_espn_activity_season.csv
Outputs:     data-lake/01_Bronze/fantasy_baseball/{YEAR}_espn_roster_history.csv
"""

import csv, os, sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

YEAR       = 2026
DRAFT_DATE = f'{YEAR}-03-23'
BASE       = mp.DATA_PATH

draft_path    = os.path.join(BASE, f'{YEAR}_espn_draft_results.csv')
activity_path = os.path.join(BASE, f'{YEAR}_espn_activity_season.csv')
out_path      = os.path.join(BASE, f'{YEAR}_espn_roster_history.csv')

# ── Build team_id → team_abbrev map from activity ─────────────────────────────
team_abbrev_map = {}
with open(activity_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['team_id'] and r['team_abbrev']:
            team_abbrev_map[r['team_id']] = r['team_abbrev']

# ── Load and sort activity events (FA ADDED / DROPPED only) ───────────────────
events = []
with open(activity_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['action'] in ('FA ADDED', 'DROPPED'):
            events.append(r)
events.sort(key=lambda r: r['date'])

# ── Build periods list ────────────────────────────────────────────────────────
# open_stack: (player_id, team_id) → list of indices into all_periods that are open.
# Stack approach handles the rare case of drop + re-add to the same team.
all_periods = []
open_stack  = defaultdict(list)

# Seed with draft picks
with open(draft_path, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        pid = r['player_id']
        tid = r['team_id']
        idx = len(all_periods)
        all_periods.append({
            'player_id':   pid,
            'player_name': r['player_name'],
            'team_id':     tid,
            'team_abbrev': team_abbrev_map.get(tid, ''),
            'start_date':  DRAFT_DATE,
            'end_date':    '',
            'source':      'Draft',
            'days_held':   0,
        })
        open_stack[(pid, tid)].append(idx)

# Process transaction events
for ev in events:
    pid        = ev['player_id']
    tid        = ev['team_id']
    key        = (pid, tid)
    ev_date    = ev['date'][:10]
    abbrev     = team_abbrev_map.get(tid, ev.get('team_abbrev', ''))

    if ev['action'] == 'DROPPED':
        if open_stack[key]:
            idx = open_stack[key].pop()
            all_periods[idx]['end_date'] = ev_date

    elif ev['action'] == 'FA ADDED':
        idx = len(all_periods)
        all_periods.append({
            'player_id':   pid,
            'player_name': ev['player_name'],
            'team_id':     tid,
            'team_abbrev': abbrev,
            'start_date':  ev_date,
            'end_date':    '',
            'source':      'Free Agent',
            'days_held':   0,
        })
        open_stack[key].append(idx)

# ── Calculate days_held ───────────────────────────────────────────────────────
today_str = date.today().isoformat()
for p in all_periods:
    end = p['end_date'] or today_str
    try:
        delta = (datetime.strptime(end, '%Y-%m-%d') -
                 datetime.strptime(p['start_date'], '%Y-%m-%d')).days
        p['days_held'] = max(0, delta)
    except ValueError:
        p['days_held'] = 0

# ── Write output ──────────────────────────────────────────────────────────────
FIELDNAMES = ['player_id', 'player_name', 'team_id', 'team_abbrev',
              'start_date', 'end_date', 'source', 'days_held']

with open(out_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(all_periods)

still_active = sum(1 for p in all_periods if not p['end_date'])
print(f'Wrote {len(all_periods)} periods to {out_path}')
print(f'  Draft picks  : {sum(1 for p in all_periods if p["source"] == "Draft")}')
print(f'  FA pickups   : {sum(1 for p in all_periods if p["source"] == "Free Agent")}')
print(f'  Still active : {still_active}')
