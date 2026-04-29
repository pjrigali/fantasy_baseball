"""
Backfill daily MLB game-log stats from Opening Day 2026 to today.
Inputs : MLB Stats API (no credentials needed)
Outputs: .data_lake/01_bronze/fantasy_baseball/stats_mlb_daily_2026.csv
"""

import sys, os, csv, time, json
from datetime import date, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball.mlb_processing import scrape_mlb_stats, DATA_PATH

YEAR = 2026
SEASON_START = date(2026, 3, 23)
TODAY = date.today()
HEADERS = {'User-Agent': 'Mozilla/5.0'}
CSV_PATH = os.path.join(DATA_PATH, f'stats_mlb_daily_{YEAR}.csv')


def date_to_scoring_period(d):
    return max(1, (d - SEASON_START).days + 1)


def fetch_game_logs(player_id, group):
    url = (
        f'https://statsapi.mlb.com/api/v1/people/{player_id}/stats'
        f'?stats=gameLog&season={YEAR}&group={group}'
    )
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json().get('stats', [{}])[0].get('splits', [])
    except Exception as e:
        print(f'  [!] Error fetching logs for {player_id}: {e}')
        return []


def build_batter_row(log, pid, name):
    stat = log.get('stat', {})
    d = log.get('date', '')
    return {
        'date': d,
        'scoring_period': date_to_scoring_period(date.fromisoformat(d)),
        'player_id': pid,
        'player_name': name,
        'team_id': log.get('team', {}).get('id', ''),
        'team_name': log.get('team', {}).get('name', ''),
        'opponent_id': log.get('opponent', {}).get('id', ''),
        'is_home': log.get('isHome', False),
        'game_id': log.get('game', {}).get('gamePk', ''),
        'b_or_p': 'batter',
        'G': 1,
        'AB': stat.get('atBats', 0),
        'R': stat.get('runs', 0),
        'H': stat.get('hits', 0),
        '2B': stat.get('doubles', 0),
        '3B': stat.get('triples', 0),
        'HR': stat.get('homeRuns', 0),
        'RBI': stat.get('rbi', 0),
        'SB': stat.get('stolenBases', 0),
        'CS': stat.get('caughtStealing', 0),
        'BB': stat.get('baseOnBalls', 0),
        'SO': stat.get('strikeOuts', 0),
        'HBP': stat.get('hitByPitch', 0),
        'SF': stat.get('sacFlies', 0),
        'TB': stat.get('totalBases', 0),
    }


def build_pitcher_row(log, pid, name):
    stat = log.get('stat', {})
    d = log.get('date', '')
    ip_str = str(stat.get('inningsPitched', '0.0'))
    innings, partial = ip_str.split('.') if '.' in ip_str else (ip_str, '0')
    outs = int(innings) * 3 + int(partial)
    gs = stat.get('gamesStarted', 0)
    er = stat.get('earnedRuns', 0)
    sv = stat.get('saves', 0)
    hld = stat.get('holds', 0)
    return {
        'date': d,
        'scoring_period': date_to_scoring_period(date.fromisoformat(d)),
        'player_id': pid,
        'player_name': name,
        'team_id': log.get('team', {}).get('id', ''),
        'team_name': log.get('team', {}).get('name', ''),
        'opponent_id': log.get('opponent', {}).get('id', ''),
        'is_home': log.get('isHome', False),
        'game_id': log.get('game', {}).get('gamePk', ''),
        'b_or_p': 'pitcher',
        'G': 1,
        'GS': gs,
        'W': stat.get('wins', 0),
        'L': stat.get('losses', 0),
        'QS': 1 if (gs == 1 and outs >= 18 and er <= 3) else 0,
        'SV': sv,
        'HLD': hld,
        'SVHD': sv + hld,
        'OUTS': outs,
        'H': stat.get('hits', 0),
        'R': stat.get('runs', 0),
        'ER': er,
        'HR': stat.get('homeRuns', 0),
        'BB': stat.get('baseOnBalls', 0),
        'K': stat.get('strikeOuts', 0),
    }


def load_existing_keys(path):
    if not os.path.exists(path):
        return set()
    with open(path, 'r', encoding='utf-8') as f:
        return {(r['date'], str(r['player_id']), r['b_or_p']) for r in csv.DictReader(f)}


def append_rows(path, rows, existing_keys):
    if not rows:
        return 0
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    ordered = ['date', 'scoring_period', 'player_id', 'player_name', 'team_id', 'team_name',
               'opponent_id', 'is_home', 'game_id', 'b_or_p', 'G']
    fieldnames = ordered + sorted(k for k in all_keys if k not in ordered)
    file_exists = os.path.exists(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    # Build date range
    date_range = set()
    d = SEASON_START
    while d <= TODAY:
        date_range.add(d.strftime('%Y-%m-%d'))
        d += timedelta(days=1)

    print(f'=== MLB Daily Stats Backfill {YEAR} ===')
    print(f'Date range: {SEASON_START} to {TODAY} ({len(date_range)} days)')
    print(f'Output    : {CSV_PATH}')

    existing_keys = load_existing_keys(CSV_PATH)
    print(f'Existing rows: {len(existing_keys)}\n')

    # Get player rosters
    print('Fetching hitter roster...')
    hitters = scrape_mlb_stats('hitting', YEAR, 'ALL')
    unique_hitters = {str(p['player_id']): p['player_name'] for p in hitters if p['player_id']}
    print(f'Hitters: {len(unique_hitters)}')

    print('Fetching pitcher roster...')
    pitchers = scrape_mlb_stats('pitching', YEAR, 'ALL')
    unique_pitchers = {str(p['player_id']): p['player_name'] for p in pitchers if p['player_id']}
    print(f'Pitchers: {len(unique_pitchers)}\n')

    all_new_rows = []

    print('--- Processing Hitters ---')
    for i, (pid, name) in enumerate(unique_hitters.items(), 1):
        logs = fetch_game_logs(pid, 'hitting')
        for log in logs:
            d_str = log.get('date', '')
            if d_str not in date_range:
                continue
            key = (d_str, pid, 'batter')
            if key in existing_keys:
                continue
            all_new_rows.append(build_batter_row(log, pid, name))
            existing_keys.add(key)
        if i % 100 == 0:
            print(f'  [{i}/{len(unique_hitters)}] hitters processed, {len(all_new_rows)} rows so far')
        time.sleep(0.5)

    print(f'Hitters done. Rows so far: {len(all_new_rows)}\n')

    print('--- Processing Pitchers ---')
    for i, (pid, name) in enumerate(unique_pitchers.items(), 1):
        logs = fetch_game_logs(pid, 'pitching')
        for log in logs:
            d_str = log.get('date', '')
            if d_str not in date_range:
                continue
            key = (d_str, pid, 'pitcher')
            if key in existing_keys:
                continue
            all_new_rows.append(build_pitcher_row(log, pid, name))
            existing_keys.add(key)
        if i % 100 == 0:
            print(f'  [{i}/{len(unique_pitchers)}] pitchers processed, {len(all_new_rows)} rows so far')
        time.sleep(0.5)

    print(f'Pitchers done. Total new rows: {len(all_new_rows)}\n')

    written = append_rows(CSV_PATH, all_new_rows, set())
    print(f'=== DONE === Wrote {written} rows to {CSV_PATH}')


if __name__ == '__main__':
    main()
