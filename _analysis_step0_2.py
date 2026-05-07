import sys, csv, os
from datetime import date
sys.path.insert(0, r'C:\Users\peter.rigali\Desktop\acn_repo')
from fantasy_baseball import mlb_processing as mp

# Step 0 - freshness check
today = date.today().isoformat()
year = 2026
base = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'
files = {
    'ESPN Daily Stats' : f'stats_espn_daily_{year}.csv',
    'ESPN Activity'    : f'activity_espn_season_{year}.csv',
    'MLB Lineups'      : f'lineups_mlb_batters_{year}.csv',
    'MLB Game Logs'    : f'stats_mlb_daily_{year}.csv',
}
print('=== Step 0: Data Freshness ===')
for label, fname in files.items():
    path = os.path.join(base, fname)
    if not os.path.exists(path):
        print(f'[MISSING] {label}')
        continue
    with open(path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    date_col = next((k for k in (rows[0] if rows else {}) if 'date' in k.lower()), None)
    last = max(r[date_col] for r in rows)[:10] if date_col and rows else 'unknown'
    status = '[OK]' if last == today else '[STALE]'
    print(f'  {status} {label}: last={last}')

# Steps 1-2 - league init + roster classification
print()
print('=== Steps 1-2: League Init + Roster ===')
config = mp.load_config()
league = mp.setup_league(config, year=2026)
league_prev = mp.setup_league(config, year=2025)
my_team_id = int(config['BASEBALL']['BB_MY_TEAM_ID'])
my_team_obj = next(t for t in league.teams if t.team_id == my_team_id)
my_roster = my_team_obj.roster
print(f'Team: {my_team_obj.team_name} (id={my_team_id})')
print(f'Roster size: {len(my_roster)}')

hitter_slots = {'C','1B','2B','3B','SS','OF','LF','CF','RF','DH'}
my_batters = [p for p in my_roster if not mp.is_pitcher(p)]
my_sps = [p for p in my_roster if 'SP' in p.eligibleSlots and not any(s in hitter_slots for s in p.eligibleSlots)]
my_rps = [p for p in my_roster if 'RP' in p.eligibleSlots and 'SP' not in p.eligibleSlots and not any(s in hitter_slots for s in p.eligibleSlots)]

print(f'Batters: {len(my_batters)} | SPs: {len(my_sps)} | RPs: {len(my_rps)}')
print()
print('Batters:', [p.name for p in my_batters])
print('SPs:    ', [p.name for p in my_sps])
print('RPs:    ', [p.name for p in my_rps])
