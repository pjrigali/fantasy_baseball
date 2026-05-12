
import requests
import time
import csv
import os
import sys
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def fetch_game_logs(player_id, group, season):
    """Fetch game logs for a player."""
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&season={season}&group={group}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            return response.json().get('stats', [{}])[0].get('splits', [])
        else:
            print(f"  Error fetching logs for {player_id}: Status {response.status_code}")
            return []
    except Exception as e:
        print(f"  Exception fetching logs for {player_id}: {e}")
        return []

def process_hitting_log(log, player_info, get_scoring_period_fn=None):
    """Process a single hitting game log."""
    stat = log.get('stat', {})
    game = log.get('game', {})

    date_str = log.get('date', '1900-01-01')

    row = {
        'date': date_str,
        'scoring_period': get_scoring_period_fn(date_str) if get_scoring_period_fn else 0,
        'player_id': player_info['id'],
        'player_name': player_info['name'],
        'team_id': log.get('team', {}).get('id'),
        'team_name': log.get('team', {}).get('name'),
        'opponent_id': log.get('opponent', {}).get('id'),
        'is_home': log.get('isHome', False),
        'game_id': game.get('gamePk'),
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
        'B_BB': stat.get('baseOnBalls', 0),
        'SO': stat.get('strikeOuts', 0),
        'HBP': stat.get('hitByPitch', 0),
        'SF': stat.get('sacFlies', 0),
        'TB': stat.get('totalBases', 0),
    }
    return row

def process_pitching_log(log, player_info, get_scoring_period_fn=None):
    """Process a single pitching game log."""
    stat = log.get('stat', {})
    game = log.get('game', {})

    date_str = log.get('date', '1900-01-01')

    # Calculate IP as outs
    ip_str = str(stat.get('inningsPitched', '0.0'))
    if '.' in ip_str:
        innings, partial = ip_str.split('.')
        outs = int(innings) * 3 + int(partial)
    else:
        outs = int(ip_str) * 3
        
    # QS Calculation
    # start = 1 if gamesStarted > 0
    gs = stat.get('gamesStarted', 0)
    er = stat.get('earnedRuns', 0)
    is_qs = 1 if (gs == 1 and outs >= 18 and er <= 3) else 0 # 18 outs = 6.0 IP
    
    # SVHD
    sv = stat.get('saves', 0)
    hld = stat.get('holds', 0)
    svhd = sv + hld
    
    row = {
        'date': date_str,
        'scoring_period': get_scoring_period_fn(date_str) if get_scoring_period_fn else 0,
        'player_id': player_info['id'],
        'player_name': player_info['name'],
        'team_id': log.get('team', {}).get('id'),
        'team_name': log.get('team', {}).get('name'),
        'opponent_id': log.get('opponent', {}).get('id'),
        'is_home': log.get('isHome', False),
        'game_id': game.get('gamePk'),
        'b_or_p': 'pitcher',
        'G': 1,
        'GS': gs,
        'W': stat.get('wins', 0),
        'L': stat.get('losses', 0),
        'QS': is_qs,
        'SV': sv,
        'HLD': hld,
        'SVHD': svhd,
        'OUTS': outs,
        'P_H': stat.get('hits', 0),
        'P_R': stat.get('runs', 0),
        'ER': er,
        'P_HR': stat.get('homeRuns', 0),
        'P_BB': stat.get('baseOnBalls', 0),
        'K': stat.get('strikeOuts', 0),
    }
    return row


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Generate daily stats')
    parser.add_argument('--year', type=int, default=datetime.now().year, help='Season year (default: current year)')
    parser.add_argument('--date', type=str, default=datetime.now().strftime('%Y-%m-%d'), help='Fetch logs up to this date (YYYY-MM-DD, default: today)')
    parser.add_argument('--limit', type=int, help='Limit number of players to process')
    args = parser.parse_args()

    limit = args.limit
    season = args.year
    target_date = args.date

    output_file = os.path.join(mp.DATA_PATH, f'stats_mlb_daily_{season}.csv')
    season_start = date(season, 3, 23)

    def get_scoring_period_local(game_date_str):
        try:
            game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
            days_diff = (game_date - season_start).days
            return max(1, days_diff + 1)
        except ValueError:
            return 0

    # Load existing CSV to determine start date and dedup keys
    existing_keys = set()
    existing_rows = []
    existing_headers = None
    start_date = f'{season}-03-23'

    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            existing_headers = reader.fieldnames
            for row in reader:
                existing_rows.append(row)
                existing_keys.add((row['date'], str(row['player_id']), row['b_or_p']))
        if existing_rows:
            last_date = max(r['date'] for r in existing_rows)
            start_date = last_date  # one day overlap, dedup handles it
    hitting_players = mp.scrape_mlb_stats("hitting", season, "ALL")
    pitching_players = mp.scrape_mlb_stats("pitching", season, "ALL")

    unique_hitters = {p['player_id']: p['player_name'] for p in hitting_players if p['player_id']}
    unique_pitchers = {p['player_id']: p['player_name'] for p in pitching_players if p['player_id']}

    new_rows = []

    hitters_items = list(unique_hitters.items())
    if limit:
        hitters_items = hitters_items[:limit]

    for pid, name in hitters_items:
        logs = fetch_game_logs(pid, "hitting", season)
        for log in logs:
            row = process_hitting_log(log, {'id': pid, 'name': name}, get_scoring_period_local)
            if start_date <= row['date'] <= target_date:
                key = (row['date'], str(row['player_id']), row['b_or_p'])
                if key not in existing_keys:
                    new_rows.append(row)
                    existing_keys.add(key)
        time.sleep(0.5)

    pitchers_items = list(unique_pitchers.items())
    if limit:
        pitchers_items = pitchers_items[:limit]

    for pid, name in pitchers_items:
        logs = fetch_game_logs(pid, "pitching", season)
        for log in logs:
            row = process_pitching_log(log, {'id': pid, 'name': name}, get_scoring_period_local)
            if start_date <= row['date'] <= target_date:
                key = (row['date'], str(row['player_id']), row['b_or_p'])
                if key not in existing_keys:
                    new_rows.append(row)
                    existing_keys.add(key)
        time.sleep(0.5)

    if new_rows:
        all_keys = set()
        for r in existing_rows + new_rows:
            all_keys.update(r.keys())
        ordered_keys = ['date', 'scoring_period', 'player_id', 'player_name', 'team_id', 'team_name', 'opponent_id', 'is_home', 'game_id', 'b_or_p']
        remaining = [k for k in all_keys if k not in ordered_keys]
        final_headers = existing_headers if existing_headers else (ordered_keys + sorted(remaining))

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=final_headers, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(existing_rows)
            writer.writerows(new_rows)

    print(f"[OK]    fetch_stats_mlb_daily: {len(new_rows)} rows written | {start_date} → {target_date} | {len(unique_hitters)} hitters, {len(unique_pitchers)} pitchers")

if __name__ == "__main__":
    main()
