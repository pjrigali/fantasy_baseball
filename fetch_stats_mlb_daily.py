
import requests
import time
import csv
import os
import sys
from datetime import datetime, date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# Constants
SEASON = 2023
OUTPUT_FILE = os.path.join(mp.DATA_PATH, f'stats_mlb_daily_{SEASON}.csv')
SEASON_START = date(SEASON, 3, 27) # Approximate start date for scoring period calculation

# Headers for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def get_scoring_period(game_date_str):
    """Calculate scoring period based on game date."""
    try:
        game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
        days_diff = (game_date - SEASON_START).days
        return max(1, days_diff + 1)
    except ValueError:
        return 0

def fetch_game_logs(player_id, group):
    """Fetch game logs for a player."""
    url = f"https://statsapi.mlb.com/api/v1/people/{player_id}/stats?stats=gameLog&season={SEASON}&group={group}"
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

def process_hitting_log(log, player_info):
    """Process a single hitting game log."""
    stat = log.get('stat', {})
    game = log.get('game', {})
    
    date_str = log.get('date', '1900-01-01')
    
    row = {
        'date': date_str,
        'scoring_period': get_scoring_period(date_str),
        'playerId': player_info['id'],
        'playerName': player_info['name'],
        'teamId': log.get('team', {}).get('id'),
        'team_abbrev': log.get('team', {}).get('name'), # This might be full name, abbreviate later if needed
        'opponentId': log.get('opponent', {}).get('id'),
        'isHome': log.get('isHome', False),
        'gameId': game.get('gamePk'),
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
        'B_BB': stat.get('baseOnBalls', 0), # Hitting walks
        'SO': stat.get('strikeOuts', 0),
        'HBP': stat.get('hitByPitch', 0),
        'SF': stat.get('sacFlies', 0),
        'TB': stat.get('totalBases', 0),
    }
    # Rate stats can be calculated later or here. 
    # For now, raw counts are most important for summation.
    return row

def process_pitching_log(log, player_info):
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
        'scoring_period': get_scoring_period(date_str),
        'playerId': player_info['id'],
        'playerName': player_info['name'],
        'teamId': log.get('team', {}).get('id'),
        'team_abbrev': log.get('team', {}).get('name'),
        'opponentId': log.get('opponent', {}).get('id'),
        'isHome': log.get('isHome', False),
        'gameId': game.get('gamePk'),
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
    parser.add_argument('--limit', type=int, help='Limit number of players to process')
    args = parser.parse_args()

    limit = args.limit
    
    print(f"=== Generating Daily Stats for {SEASON} ===")
    if limit:
        print(f"Limit set to {limit} players per group.")
    
    # 1. Get List of Players

    # We'll leverage existing scraping to get player lists for hitting and pitching
    # We only need the IDs.
    
    print("Fetching player lists...")
    # Using 'QUALIFIED' first to test? No, user wants ALL.
    # But getting ALL players via the scrape_mlb_stats page iteration is slow.
    # Is there a faster way? 
    # We can use the 'sports/baseball/mlb/players' endpoint or just wait.
    # Let's stick to the module's function since it works.
    
    hitting_players = mp.scrape_mlb_stats("hitting", SEASON, "ALL")
    pitching_players = mp.scrape_mlb_stats("pitching", SEASON, "ALL")
    
    # Unique IDs
    unique_hitters = {p['player_id']: p['player_name'] for p in hitting_players if p['player_id']}
    unique_pitchers = {p['player_id']: p['player_name'] for p in pitching_players if p['player_id']}
    
    print(f"Found {len(unique_hitters)} hitters and {len(unique_pitchers)} pitchers.")
    
    all_rows = []
    
    # Process Hitters
    print("\n--- Processing Hitters ---")
    count = 0
    hitters_items = list(unique_hitters.items())
    if limit:
        hitters_items = hitters_items[:limit]

    for pid, name in hitters_items:
        count += 1
        print(f"[{count}/{len(hitters_items)}] Fetching logs for {name} ({pid})...")
        logs = fetch_game_logs(pid, "hitting")
        for log in logs:
            all_rows.append(process_hitting_log(log, {'id': pid, 'name': name}))
        time.sleep(0.5) # Rate Limit
        
    # Process Pitchers
    print("\n--- Processing Pitchers ---")
    count = 0
    pitchers_items = list(unique_pitchers.items())
    if limit:
        pitchers_items = pitchers_items[:limit]

    for pid, name in pitchers_items:
        count += 1
        print(f"[{count}/{len(pitchers_items)}] Fetching logs for {name} ({pid})...")
        logs = fetch_game_logs(pid, "pitching")
        for log in logs:
            all_rows.append(process_pitching_log(log, {'id': pid, 'name': name}))
        time.sleep(0.5) # Rate Limit

    # Save to CSV
    if all_rows:
        keys = all_rows[0].keys()
        # Ensure consistent keys if needed (union of all keys)
        all_keys = set()
        for r in all_rows:
            all_keys.update(r.keys())
        
        # Sort keys nicely
        # Prioritize Date, Name, Stats
        ordered_keys = ['date', 'scoring_period', 'playerName', 'playerId', 'teamId', 'b_or_p']
        remaining = [k for k in all_keys if k not in ordered_keys]
        final_headers = ordered_keys + sorted(remaining)
        
        print(f"\nSaving {len(all_rows)} rows to {OUTPUT_FILE}...")
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=final_headers)
            writer.writeheader()
            writer.writerows(all_rows)
        print("Done.")
    else:
        print("No data collected.")

if __name__ == "__main__":
    main()
