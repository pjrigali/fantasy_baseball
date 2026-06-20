"""
League Position Analysis — Steps 1-5.

Description: Computes league-wide positional averages by lineup slot, compares my team
             against those averages with slot coverage metrics, ranks all league members
             across the 5x5 scoring categories, and projects current matchup winners.
Source Data: data-lake/01_Bronze/fantasy_baseball/<year>_espn_stats_daily.csv
Outputs:     fantasy_baseball/_league_pos_results.json
"""
import sys, csv, os, json, math, datetime
from datetime import date
from collections import defaultdict

sys.path.insert(0, r'C:\Users\peter.rigali\Desktop\acn_repo')
from fantasy_baseball import mlb_processing as mp

YEAR = 2026
BASE = r'C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball'
CSV_PATH = os.path.join(BASE, f'{YEAR}_espn_stats_daily.csv')
NUM_TEAMS = 12

BATTING_SLOTS  = {'C', '1B', '1B/3B', '2B', '2B/SS', '3B', 'SS', 'OF', 'UTIL', 'DH'}
PITCHING_SLOTS = {'SP', 'RP'}
SKIP_SLOTS     = {'BE', 'IL'}
BAT_SLOT_ORDER = ['C', '1B', '1B/3B', '2B', '2B/SS', '3B', 'SS', 'OF', 'UTIL']
PIT_SLOT_ORDER = ['SP', 'RP']
CATS_ORDER     = ['R', 'HR', 'RBI', 'SB', 'OPS', 'ERA', 'WHIP', 'K9', 'QS', 'SVHD']
LOWER_IS_BETTER = {'ERA', 'WHIP'}


def safe_float(x, default=0.0):
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except Exception:
        return default


def make_bat_accum():
    return dict(slot_days=0, R=0.0, HR=0.0, RBI=0.0, SB=0.0,
                AB=0.0, H=0.0, TB=0.0, BB=0.0, HBP=0.0, SF=0.0)


def make_pit_accum():
    return dict(slot_days=0, QS=0.0, SVHD=0.0,
                OUTS=0.0, K=0.0, ER=0.0, P_H=0.0, P_BB=0.0)


def add_bat(a, r):
    a['slot_days'] += 1
    a['R']   += safe_float(r.get('R'))
    a['HR']  += safe_float(r.get('HR'))
    a['RBI'] += safe_float(r.get('RBI'))
    a['SB']  += safe_float(r.get('SB'))
    a['AB']  += safe_float(r.get('AB'))
    a['H']   += safe_float(r.get('H'))
    a['TB']  += safe_float(r.get('TB'))
    a['BB']  += safe_float(r.get('B_BB'))
    a['HBP'] += safe_float(r.get('HBP'))
    a['SF']  += safe_float(r.get('SF'))


def add_pit(a, r):
    a['slot_days'] += 1
    a['QS']   += safe_float(r.get('QS'))
    a['SVHD'] += safe_float(r.get('SV')) + safe_float(r.get('HLD'))
    a['OUTS'] += safe_float(r.get('OUTS'))
    a['K']    += safe_float(r.get('K'))
    a['ER']   += safe_float(r.get('ER'))
    a['P_H']  += safe_float(r.get('P_H'))
    a['P_BB'] += safe_float(r.get('P_BB'))


def ops_from_accum(a):
    denom = a['AB'] + a['BB'] + a['HBP'] + a['SF']
    obp = (a['H'] + a['BB'] + a['HBP']) / denom if denom > 0 else 0.0
    slg = a['TB'] / a['AB'] if a['AB'] > 0 else 0.0
    return round(obp + slg, 3)


def pit_rates(a):
    outs = a['OUTS']
    ip = outs / 3.0
    era  = round(a['ER'] * 27.0 / outs, 2) if outs > 0 else 0.0
    whip = round((a['P_H'] + a['P_BB']) / ip, 2) if ip > 0 else 0.0
    k9   = round(a['K'] * 27.0 / outs, 2) if outs > 0 else 0.0
    return era, whip, k9


def bat_summary(a):
    return dict(
        slot_days=a['slot_days'],
        R=round(a['R']), HR=round(a['HR']), RBI=round(a['RBI']), SB=round(a['SB']),
        OPS=ops_from_accum(a),
    )


def pit_summary(a):
    era, whip, k9 = pit_rates(a)
    return dict(
        slot_days=a['slot_days'],
        ERA=era, WHIP=whip, K9=k9,
        QS=round(a['QS']), SVHD=round(a['SVHD']),
    )


# ── Step 1: Load and filter ──────────────────────────────────────────────────
print('=== Step 1: Load Data ===')

config = mp.load_config()
league = mp.setup_league(config, year=YEAR)
my_team_id = int(config['BASEBALL']['BB_MY_TEAM_ID'])

# Build canonical team name per team_id: use the most recent name seen for each id
tid_name_dates = defaultdict(list)
with open(CSV_PATH, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        tid_name_dates[r['team_id']].append((r['date'], r['team_name']))

team_id_to_name = {
    tid: sorted(entries, reverse=True)[0][1]
    for tid, entries in tid_name_dates.items()
}
name_to_canonical = {}
for tid, entries in tid_name_dates.items():
    canonical = team_id_to_name[tid]
    for _, name in entries:
        name_to_canonical[name] = canonical

my_team_obj  = next(t for t in league.teams if t.team_id == my_team_id)
my_team_name = team_id_to_name.get(str(my_team_id), my_team_obj.team_name)

rows = []
with open(CSV_PATH, encoding='utf-8') as f:
    for r in csv.DictReader(f):
        slot = r['lineup_slot']
        if slot in SKIP_SLOTS:
            continue
        # Normalize generic pitcher slot
        if slot == 'P':
            slot = 'SP' if safe_float(r.get('GS')) > 0 else 'RP'
        r['_slot'] = slot
        r['_team'] = name_to_canonical.get(r['team_name'], r['team_name'])
        rows.append(r)

all_dates = sorted(set(r['date'] for r in rows))
total_days = len(all_dates)
latest_date = all_dates[-1] if all_dates else str(date.today())
all_teams = sorted(set(r['_team'] for r in rows))

print(f'  {len(rows)} active rows | {all_dates[0]} to {latest_date} ({total_days} days) | {len(all_teams)} teams')
print(f'  My team: {my_team_name}')


# ── Step 2: League position averages ─────────────────────────────────────────
print('\n=== Step 2: League Position Averages ===')

lg_bat_acc = defaultdict(make_bat_accum)
lg_pit_acc = defaultdict(make_pit_accum)

for r in rows:
    slot = r['_slot']
    pt   = r.get('player_type', '')
    if slot in BATTING_SLOTS and pt == 'batter':
        add_bat(lg_bat_acc[slot], r)
    elif slot in PITCHING_SLOTS and pt == 'pitcher':
        add_pit(lg_pit_acc[slot], r)

lg_bat_ytd = {s: bat_summary(a) for s, a in lg_bat_acc.items()}
lg_pit_ytd = {s: pit_summary(a) for s, a in lg_pit_acc.items()}

print('Batting (league-wide YTD):')
print(f'  {"Slot":<10} {"Days":>5} {"R":>5} {"HR":>5} {"RBI":>5} {"SB":>5} {"OPS":>6}')
for s in BAT_SLOT_ORDER:
    if s in lg_bat_ytd:
        x = lg_bat_ytd[s]
        print(f'  {s:<10} {x["slot_days"]:>5} {x["R"]:>5} {x["HR"]:>5} {x["RBI"]:>5} {x["SB"]:>5} {x["OPS"]:>6.3f}')

print('Pitching (league-wide YTD):')
print(f'  {"Slot":<6} {"Days":>5} {"ERA":>6} {"WHIP":>6} {"K/9":>6} {"QS":>5} {"SVHD":>6}')
for s in PIT_SLOT_ORDER:
    if s in lg_pit_ytd:
        x = lg_pit_ytd[s]
        print(f'  {s:<6} {x["slot_days"]:>5} {x["ERA"]:>6.2f} {x["WHIP"]:>6.2f} {x["K9"]:>6.2f} {x["QS"]:>5} {x["SVHD"]:>6}')


# ── Step 3: My team vs league ─────────────────────────────────────────────────
print('\n=== Step 3: My Team Comparison ===')

my_bat_acc  = defaultdict(make_bat_accum)
my_pit_acc  = defaultdict(make_pit_accum)
# Track unique dates per slot to compute fill rate correctly for multi-player slots
my_slot_dates = defaultdict(set)

for r in rows:
    if r['_team'] != my_team_name:
        continue
    slot = r['_slot']
    pt   = r.get('player_type', '')
    if slot in BATTING_SLOTS and pt == 'batter':
        add_bat(my_bat_acc[slot], r)
        my_slot_dates[slot].add(r['date'])
    elif slot in PITCHING_SLOTS and pt == 'pitcher':
        add_pit(my_pit_acc[slot], r)
        my_slot_dates[slot].add(r['date'])

my_bat_stats = {s: bat_summary(a) for s, a in my_bat_acc.items()}
my_pit_stats = {s: pit_summary(a) for s, a in my_pit_acc.items()}


def lg_per_team_bat(slot):
    """League aggregate divided by NUM_TEAMS for per-team avg. Rate stats use aggregated components."""
    a = lg_bat_acc[slot]
    n = NUM_TEAMS
    return dict(
        slot_days=round(a['slot_days'] / n),
        R=round(a['R'] / n), HR=round(a['HR'] / n),
        RBI=round(a['RBI'] / n), SB=round(a['SB'] / n),
        OPS=ops_from_accum(a),   # rate from all PAs — league-wide avg rate
    )


def lg_per_team_pit(slot):
    a = lg_pit_acc[slot]
    n = NUM_TEAMS
    era, whip, k9 = pit_rates(a)
    return dict(
        slot_days=round(a['slot_days'] / n),
        ERA=era, WHIP=whip, K9=k9,
        QS=round(a['QS'] / n), SVHD=round(a['SVHD'] / n),
    )


my_bat_cmp = {}
for slot in BAT_SLOT_ORDER:
    if slot not in lg_bat_ytd:
        continue
    my_s = my_bat_stats.get(slot, dict(slot_days=0, R=0, HR=0, RBI=0, SB=0, OPS=0.0))
    lg_s = lg_per_team_bat(slot)
    # Fill rate = unique days my team had anyone in this slot (handles multi-player slots)
    active_dates = len(my_slot_dates[slot])
    fill_rate    = round(active_dates / total_days * 100) if total_days else 0
    empty_days   = total_days - active_dates
    deficits   = sum([
        my_s['R']   < lg_s['R'],
        my_s['HR']  < lg_s['HR'],
        my_s['RBI'] < lg_s['RBI'],
        my_s['SB']  < lg_s['SB'],
        my_s['OPS'] < lg_s['OPS'],
    ])
    my_bat_cmp[slot] = dict(my=my_s, lg=lg_s, fill_rate=fill_rate,
                             empty_days=empty_days, deficits=deficits)

my_pit_cmp = {}
for slot in PIT_SLOT_ORDER:
    if slot not in lg_pit_ytd:
        continue
    my_s = my_pit_stats.get(slot, dict(slot_days=0, ERA=0.0, WHIP=0.0, K9=0.0, QS=0, SVHD=0))
    lg_s = lg_per_team_pit(slot)
    active_dates = len(my_slot_dates[slot])
    fill_rate    = round(active_dates / total_days * 100) if total_days else 0
    empty_days   = total_days - active_dates
    deficits   = sum([
        (my_s['ERA']  > lg_s['ERA']  and lg_s['ERA']  > 0),
        (my_s['WHIP'] > lg_s['WHIP'] and lg_s['WHIP'] > 0),
        my_s['K9']   < lg_s['K9'],
        my_s['QS']   < lg_s['QS'],
        my_s['SVHD'] < lg_s['SVHD'],
    ])
    my_pit_cmp[slot] = dict(my=my_s, lg=lg_s, fill_rate=fill_rate,
                             empty_days=empty_days, deficits=deficits)

print('Batting (me vs league avg per team):')
for slot, c in my_bat_cmp.items():
    flag = ' !!!' if c['fill_rate'] < 80 or c['deficits'] >= 3 else ''
    print(f'  {slot:<10} fill={c["fill_rate"]:>3}% empty={c["empty_days"]:>2} '
          f'R={c["my"]["R"]}/{c["lg"]["R"]}  HR={c["my"]["HR"]}/{c["lg"]["HR"]}  '
          f'OPS={c["my"]["OPS"]:.3f}/{c["lg"]["OPS"]:.3f}  deficits={c["deficits"]}/5{flag}')

print('Pitching:')
for slot, c in my_pit_cmp.items():
    flag = ' !!!' if c['fill_rate'] < 80 or c['deficits'] >= 3 else ''
    print(f'  {slot:<6} fill={c["fill_rate"]:>3}% empty={c["empty_days"]:>2} '
          f'ERA={c["my"]["ERA"]:.2f}/{c["lg"]["ERA"]:.2f}  '
          f'SVHD={c["my"]["SVHD"]}/{c["lg"]["SVHD"]}  deficits={c["deficits"]}/5{flag}')


# ── Step 4: League member rankings ───────────────────────────────────────────
print('\n=== Step 4: League Member Rankings ===')

team_bat_acc = defaultdict(make_bat_accum)
team_pit_acc = defaultdict(make_pit_accum)

for r in rows:
    slot = r['_slot']
    team = r['_team']
    pt   = r.get('player_type', '')
    if slot in BATTING_SLOTS and pt == 'batter':
        add_bat(team_bat_acc[team], r)
    elif slot in PITCHING_SLOTS and pt == 'pitcher':
        add_pit(team_pit_acc[team], r)

team_stats = {}
for team in all_teams:
    ba = team_bat_acc[team]
    pa = team_pit_acc[team]
    era, whip, k9 = pit_rates(pa)
    team_stats[team] = dict(
        R=round(ba['R']), HR=round(ba['HR']), RBI=round(ba['RBI']),
        SB=round(ba['SB']), OPS=ops_from_accum(ba),
        ERA=era, WHIP=whip, K9=k9,
        QS=round(pa['QS']), SVHD=round(pa['SVHD']),
    )


def rank_teams(cat):
    lower = cat in LOWER_IS_BETTER
    vals = sorted(all_teams, key=lambda t: team_stats[t][cat],
                  reverse=not lower)
    return {team: i + 1 for i, team in enumerate(vals)}


rankings = {cat: rank_teams(cat) for cat in CATS_ORDER}

team_profiles = {}
for team in all_teams:
    team_ranks = {cat: rankings[cat][team] for cat in CATS_ORDER}
    top3 = sorted(CATS_ORDER, key=lambda c: team_ranks[c])[:3]
    bot3 = sorted(CATS_ORDER, key=lambda c: team_ranks[c], reverse=True)[:3]
    team_profiles[team] = dict(ranks=team_ranks, top3=top3, bot3=bot3,
                                stats=team_stats[team])

print(f'  {"Team":<28}' + ''.join(f'{c:>7}' for c in CATS_ORDER))
for team in all_teams:
    row = ''.join(f'  #{rankings[c][team]:<3}' for c in CATS_ORDER)
    marker = ' *' if team == my_team_name else ''
    print(f'  {team+marker:<29} {row}')


# ── Step 5: Matchup projections ──────────────────────────────────────────────
print('\n=== Step 5: Matchup Projections ===')

# Project remaining days in the current matchup period (Mon–Sun weeks, ends Sunday).
# today_sp = scoringPeriodId - 1 (the API advances 1 ahead of today's SP).
# Map SP to calendar date using season start, then compute days left through Sunday.
SEASON_START = datetime.date(YEAR, 3, 26)
today_sp   = league.scoringPeriodId - 1
today_date = SEASON_START + datetime.timedelta(days=today_sp - league.firstScoringPeriod)
PROJ_DAYS  = (6 - today_date.weekday()) % 7 + 1   # days from today through Sunday inclusive
matchup_period = league.currentMatchupPeriod
COUNTING_CATS = {'R', 'HR', 'RBI', 'SB', 'QS', 'SVHD'}

proj_stats = {}
for team in all_teams:
    s = team_stats[team]
    proj_stats[team] = {
        cat: round(s[cat] / total_days * PROJ_DAYS, 1) if cat in COUNTING_CATS else s[cat]
        for cat in CATS_ORDER
    }

print(f'  Matchup {matchup_period} — projecting {PROJ_DAYS} remaining day(s) '
      f'(today={today_date}, ends Sunday | {total_days} days of season data):')
print(f'  {"Team":<28}' + ''.join(f'{c:>7}' for c in CATS_ORDER))
for team in all_teams:
    vals = ''.join(
        f'{proj_stats[team][c]:>7.1f}' if c in COUNTING_CATS
        else f'{proj_stats[team][c]:>7.3f}'
        for c in CATS_ORDER
    )
    marker = ' *' if team == my_team_name else ''
    print(f'  {team+marker:<29} {vals}')

matchup_projections = []
try:
    matchups_raw = league.box_scores()

    for m in matchups_raw:
        home = name_to_canonical.get(m.home_team.team_name, m.home_team.team_name)
        away = name_to_canonical.get(m.away_team.team_name, m.away_team.team_name)
        cats_result = []
        home_wins = away_wins = 0

        for cat in CATS_ORDER:
            hv = proj_stats.get(home, {}).get(cat, 0)
            av = proj_stats.get(away, {}).get(cat, 0)
            lower = cat in LOWER_IS_BETTER
            if lower:
                if hv > 0 and av > 0:
                    edge = home if hv < av else (away if av < hv else 'Tie')
                elif hv > 0:
                    edge = home
                elif av > 0:
                    edge = away
                else:
                    edge = 'Tie'
            else:
                edge = home if hv > av else (away if av > hv else 'Tie')

            if edge == home:
                home_wins += 1
            elif edge == away:
                away_wins += 1
            cats_result.append(dict(cat=cat, home_val=hv, away_val=av, edge=edge))

        matchup_projections.append(dict(
            home=home, away=away,
            home_wins=home_wins, away_wins=away_wins,
            categories=cats_result,
            matchup_period=matchup_period,
        ))
        print(f'  {home} {home_wins} — {away_wins} {away}  (proj)')

except Exception as e:
    print(f'  Matchup fetch failed: {e}')


# ── Save ─────────────────────────────────────────────────────────────────────
results = dict(
    meta=dict(
        season=YEAR,
        generated=str(date.today()),
        latest_data=latest_date,
        total_days=total_days,
        my_team=my_team_name,
        all_teams=all_teams,
        matchup_period=matchup_period,
        proj_days=PROJ_DAYS,
        matchup_end=str(today_date + datetime.timedelta(days=PROJ_DAYS - 1)),
    ),
    league_bat_ytd=lg_bat_ytd,
    league_pit_ytd=lg_pit_ytd,
    my_bat_comparison=my_bat_cmp,
    my_pit_comparison=my_pit_cmp,
    team_stats=team_stats,
    team_profiles=team_profiles,
    rankings=rankings,
    matchup_projections=matchup_projections,
)

out = r'C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\_league_pos_results.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(results, f, indent=2, default=str)
print(f'\nSaved to {out}')
