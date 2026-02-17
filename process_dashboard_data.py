"""
Fantasy Baseball In-Season Dashboard — Data Collection & HTML Generation

Collects roster, league, and free agent data from ESPN API,
saves it as an appendable CSV (one row per player per date),
generates a standalone HTML dashboard, and pushes to GitHub Pages.

Features:
    - Appends daily snapshots to a CSV without duplicates
    - Detects missed days and backfills them on next run
    - Auto-commits and pushes the dashboard HTML to the website repo

Usage:
    # Live mode (hits ESPN API):
    python -m fantasy_baseball.collect_dashboard_data

    # Dry-run mode (uses 2025 daily_player_stats CSV for testing):
    python -m fantasy_baseball.collect_dashboard_data --dry-run

    # Skip git push:
    python -m fantasy_baseball.collect_dashboard_data --no-push

Output:
    - .data_lake/01_bronze/fantasy_baseball/dashboard_snapshots.csv  (appendable)
    - website/pjrigali.github.io/pages/17_Fantasy_Baseball_Dashboard.html
"""

import os
import sys
import csv
import json
import argparse
import subprocess
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# --- Constants ---
MY_TEAM_ID = 2
YEAR = 2026
BATTER_STATS = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHER_STATS = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
ALL_STATS = BATTER_STATS + PITCHER_STATS
INVERSE_STATS = {'ERA', 'WHIP'}

BATTER_POSITIONS = ['C', '1B', '2B', '3B', 'SS', 'OF', 'DH']
PITCHER_POSITIONS = ['SP', 'RP']
ALL_POSITIONS = BATTER_POSITIONS + PITCHER_POSITIONS

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBSITE_DIR = os.path.join(PROJECT_ROOT, 'website', 'pjrigali.github.io')
DASHBOARD_OUTPUT = os.path.join(WEBSITE_DIR, 'pages', '17_Fantasy_Baseball_Dashboard.html')
TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dashboard_template.html')
CSV_PATH = os.path.join(mp.DATA_PATH, 'dashboard_snapshots.csv')

# CSV columns — flat structure, one row per player per date
CSV_COLUMNS = [
    'date', 'player_name', 'player_id', 'position', 'pro_team',
    'injury_status', 'owner', 'owner_type',
    'season_R', 'season_HR', 'season_RBI', 'season_SB', 'season_OPS',
    'season_K/9', 'season_QS', 'season_SVHD', 'season_ERA', 'season_WHIP',
    'last7_R', 'last7_HR', 'last7_RBI', 'last7_SB', 'last7_OPS',
    'last7_K/9', 'last7_QS', 'last7_SVHD', 'last7_ERA', 'last7_WHIP',
    'last15_R', 'last15_HR', 'last15_RBI', 'last15_SB', 'last15_OPS',
    'last15_K/9', 'last15_QS', 'last15_SVHD', 'last15_ERA', 'last15_WHIP',
    'last30_R', 'last30_HR', 'last30_RBI', 'last30_SB', 'last30_OPS',
    'last30_K/9', 'last30_QS', 'last30_SVHD', 'last30_ERA', 'last30_WHIP',
    'pct_owned', 'pct_started', 'pct_change',
]


def classify_position(eligible_slots):
    """Determine primary dashboard position from eligible slots list."""
    if isinstance(eligible_slots, str):
        try:
            eligible_slots = eval(eligible_slots)
        except Exception:
            eligible_slots = [eligible_slots]

    priority = ['C', '1B', '2B', '3B', 'SS', 'OF', 'SP', 'RP', 'DH']
    for pos in priority:
        if pos in eligible_slots:
            return pos
    return 'UTIL'


# --- CSV Functions ---

def get_existing_dates():
    """Read existing CSV and return the set of dates already collected."""
    if not os.path.exists(CSV_PATH):
        return set()
    dates = set()
    with open(CSV_PATH, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            dates.add(row['date'])
    return dates


def get_missing_dates(existing_dates, lookback_days=7):
    """
    Determine which dates in the last N days are missing from the CSV.
    Returns a list of date strings (YYYY-MM-DD) that need to be collected.
    """
    today = datetime.now().date()
    missing = []
    for i in range(lookback_days):
        d = today - timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        if d_str not in existing_dates:
            missing.append(d_str)
    return sorted(missing)  # oldest first


def flatten_player_to_row(date_str, player_dict):
    """Convert a player dict into a flat CSV row dict."""
    stats = player_dict.get('stats', {})
    season = stats.get('season', {})
    last7 = stats.get('last7days', {})
    last15 = stats.get('last15days', {})
    last30 = stats.get('last30days', {})

    row = {
        'date': date_str,
        'player_name': player_dict.get('name', ''),
        'player_id': player_dict.get('playerId', ''),
        'position': player_dict.get('position', ''),
        'pro_team': player_dict.get('proTeam', ''),
        'injury_status': player_dict.get('injuryStatus', 'ACTIVE'),
        'owner': player_dict.get('owner', ''),
        'owner_type': player_dict.get('owner_type', ''),
    }

    # Season stats
    for stat in ALL_STATS:
        row[f'season_{stat}'] = season.get(stat, '')
    # Last 7
    for stat in ALL_STATS:
        row[f'last7_{stat}'] = last7.get(stat, '')
    # Last 15
    for stat in ALL_STATS:
        row[f'last15_{stat}'] = last15.get(stat, '')
    # Last 30
    for stat in ALL_STATS:
        row[f'last30_{stat}'] = last30.get(stat, '')

    # Ownership
    ownership = player_dict.get('ownership', {})
    row['pct_owned'] = ownership.get('percentOwned', '')
    row['pct_started'] = ownership.get('percentStarted', '')
    row['pct_change'] = ownership.get('percentChange', '')

    return row


def append_rows_to_csv(rows):
    """Append rows to the CSV file, creating it with headers if it doesn't exist."""
    file_exists = os.path.exists(CSV_PATH)
    os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)

    with open(CSV_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"  Appended {len(rows)} rows to {CSV_PATH}")


def load_csv_for_dashboard(dates_to_use=None):
    """
    Load the CSV into a dashboard-ready structure.
    Uses the most recent date available (or a specific list of dates).
    Returns the dashboard data dict expected by the HTML template.
    """
    if not os.path.exists(CSV_PATH):
        return None

    # Read all rows
    all_rows = []
    with open(CSV_PATH, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            all_rows.append(row)

    if not all_rows:
        return None

    # Find the latest date
    all_dates = sorted(set(r['date'] for r in all_rows))
    latest_date = all_dates[-1]
    print(f"  CSV has {len(all_rows)} total rows across {len(all_dates)} dates")
    print(f"  Using latest date: {latest_date}")

    # Filter to latest date only (dashboard shows current state)
    latest_rows = [r for r in all_rows if r['date'] == latest_date]

    # Determine my team name from the data
    my_team_name = ''
    for r in latest_rows:
        if r['owner_type'] == 'mine':
            my_team_name = r['owner']
            break
    if not my_team_name:
        my_team_name = f'Team {MY_TEAM_ID}'

    # Build positions structure
    positions_data = {pos: {'my_players': [], 'league_players': [], 'free_agents': []}
                      for pos in ALL_POSITIONS}

    for r in latest_rows:
        pos = r.get('position', '')
        if pos not in positions_data:
            continue

        # Reconstruct stats dict from flat columns
        stats = {'season': {}, 'last7days': {}, 'last15days': {}, 'last30days': {}}
        for stat in ALL_STATS:
            for prefix, key in [('season_', 'season'), ('last7_', 'last7days'),
                                ('last15_', 'last15days'), ('last30_', 'last30days')]:
                val = r.get(f'{prefix}{stat}', '')
                if val != '':
                    try:
                        stats[key][stat] = float(val)
                    except (ValueError, TypeError):
                        pass

        player = {
            'name': r['player_name'],
            'playerId': r['player_id'],
            'position': pos,
            'proTeam': r.get('pro_team', ''),
            'injuryStatus': r.get('injury_status', 'ACTIVE'),
            'injured': r.get('injury_status', 'ACTIVE') in ('IL', 'INJURY_RESERVE'),
            'owner': r.get('owner', ''),
            'stats': stats,
        }

        # Ownership
        if r.get('pct_owned', ''):
            try:
                player['ownership'] = {
                    'percentOwned': float(r.get('pct_owned', 0)),
                    'percentStarted': float(r.get('pct_started', 0)),
                    'percentChange': float(r.get('pct_change', 0)),
                }
            except (ValueError, TypeError):
                pass

        owner_type = r.get('owner_type', '')
        if owner_type == 'mine':
            positions_data[pos]['my_players'].append(player)
        elif owner_type == 'league':
            positions_data[pos]['league_players'].append(player)
        elif owner_type == 'free_agent':
            positions_data[pos]['free_agents'].append(player)

    return {
        'generated_at': latest_date,
        'my_team_id': MY_TEAM_ID,
        'my_team_name': my_team_name,
        'season': YEAR,
        'positions': positions_data,
    }


# --- Data Collection ---

def collect_live_snapshot(date_str):
    """Collect one day's snapshot from ESPN API. Returns list of flat row dicts."""
    print(f"\n--- Collecting snapshot for {date_str} ---")
    config = mp.load_config()
    league = mp.setup_league(config, year=YEAR)

    # Identify my team
    my_team = None
    team_names = {}
    for team in league.teams:
        team_names[team.team_id] = team.team_name
        if team.team_id == MY_TEAM_ID:
            my_team = team

    if not my_team:
        raise ValueError(f"Team ID {MY_TEAM_ID} not found in league.")

    rows = []

    # --- Rostered players ---
    print("  Fetching league rosters...")
    for team in league.teams:
        for player in team.roster:
            pos = classify_position(player.eligibleSlots)
            if pos == 'UTIL':
                pos = 'DH'
            if pos not in ALL_POSITIONS:
                continue

            owner_type = 'mine' if team.team_id == MY_TEAM_ID else 'league'
            stats_data = {
                'season': {},
                'projected': {},
            }
            stats_data['season']['total_points'] = player.total_points or 0
            stats_data['projected']['total_points'] = player.projected_total_points or 0

            player_dict = {
                'name': player.name,
                'playerId': player.playerId,
                'position': pos,
                'proTeam': player.proTeam,
                'injuryStatus': player.injuryStatus or 'ACTIVE',
                'injured': player.injured,
                'owner': team.team_name,
                'owner_type': owner_type,
                'stats': stats_data,
            }
            rows.append(flatten_player_to_row(date_str, player_dict))

    # --- Free agents ---
    print("  Fetching free agents by position...")
    fa_by_pos = mp.get_all_free_agents_by_position(league, size=25)

    for pos_name, fa_list in fa_by_pos.items():
        if pos_name not in ALL_POSITIONS:
            continue
        for fa in fa_list:
            stats = fa.get('stats', {})
            stats_data = {}
            period_key_map = {
                'season': str(YEAR),
                'last7days': 'last7days',
                'last15days': 'last15days',
                'last30days': 'last30days',
            }
            for period_name, period_key in period_key_map.items():
                period_stats = stats.get(period_key, {})
                stats_data[period_name] = {}
                for stat in ALL_STATS:
                    if stat in period_stats:
                        stats_data[period_name][stat] = round(period_stats[stat], 3)

            research = fa.get('research', {})
            player_dict = {
                'name': fa['name'],
                'playerId': fa['playerId'],
                'position': pos_name,
                'proTeam': fa['proTeam'],
                'injuryStatus': fa['injuryStatus'] or 'ACTIVE',
                'injured': fa['injured'],
                'owner': 'Free Agent',
                'owner_type': 'free_agent',
                'stats': stats_data,
                'ownership': {
                    'percentOwned': round(research.get('percentOwned', 0), 1),
                    'percentStarted': round(research.get('percentStarted', 0), 1),
                    'percentChange': round(research.get('percentChange', 0), 1),
                } if research else {},
            }
            rows.append(flatten_player_to_row(date_str, player_dict))

    print(f"  Collected {len(rows)} player rows for {date_str}")
    return rows


def collect_dry_run_snapshot():
    """
    Build snapshot rows from existing 2025 CSV data for testing.
    Uses the most recent date from 2025 daily stats as the snapshot date.
    """
    import pandas as pd
    print("\n--- Dry Run: Building snapshot from 2025 CSV Data ---")

    stats_path = os.path.join(mp.DATA_PATH, 'stats_espn_daily_2025.csv')
    roster_path = os.path.join(mp.DATA_PATH, 'roster_espn_season_2025.csv')
    teams_path = os.path.join(mp.DATA_PATH, 'teams_espn_season_2025.csv')

    for p in [stats_path, roster_path]:
        if not os.path.exists(p):
            raise FileNotFoundError(f"Required file not found: {p}")

    roster_df = pd.read_csv(roster_path)
    stats_df = pd.read_csv(stats_path)
    print(f"  Loaded {len(roster_df)} roster records, {len(stats_df)} daily stats")

    # Team names
    team_names = {}
    if os.path.exists(teams_path):
        teams_df = pd.read_csv(teams_path)
        for _, row in teams_df.iterrows():
            team_names[row['team_id']] = row.get('team_name', row.get('team_abbrev', f"Team {row['team_id']}"))

    # Compute aggregates
    sum_cols = ['R', 'HR', 'RBI', 'SB', 'QS', 'SVHD', 'AB', 'H', 'B_BB', 'PA',
                'TB', 'OUTS', 'ER', 'P_H', 'P_BB', 'K', 'SV', 'HLD', 'W', 'L', 'G', 'GS']
    existing_sum_cols = [c for c in sum_cols if c in stats_df.columns]

    def compute_rate_stats(df):
        """Add rate stats to an aggregated DataFrame."""
        if 'AB' in df.columns and 'H' in df.columns:
            df['AVG'] = (df['H'] / df['AB'].replace(0, float('nan'))).round(3)
        if 'PA' in df.columns and 'H' in df.columns and 'B_BB' in df.columns:
            df['OBP'] = ((df['H'] + df['B_BB']) / df['PA'].replace(0, float('nan'))).round(3)
        if 'AB' in df.columns and 'TB' in df.columns:
            df['SLG'] = (df['TB'] / df['AB'].replace(0, float('nan'))).round(3)
        if 'OBP' in df.columns and 'SLG' in df.columns:
            df['OPS'] = (df['OBP'] + df['SLG']).round(3)
        if 'OUTS' in df.columns and 'ER' in df.columns:
            ip = df['OUTS'] / 3
            df['ERA'] = (df['ER'] * 9 / ip.replace(0, float('nan'))).round(3)
        if 'OUTS' in df.columns and 'P_H' in df.columns and 'P_BB' in df.columns:
            ip = df['OUTS'] / 3
            df['WHIP'] = ((df['P_H'] + df['P_BB']) / ip.replace(0, float('nan'))).round(3)
        if 'OUTS' in df.columns and 'K' in df.columns:
            ip = df['OUTS'] / 3
            df['K/9'] = (df['K'] * 9 / ip.replace(0, float('nan'))).round(3)
        return df

    # Season totals
    player_season = stats_df.groupby(['playerId', 'playerName', 'teamId'])[existing_sum_cols].sum().reset_index()
    player_season = compute_rate_stats(player_season)

    # Rolling windows
    max_sp = stats_df['scoring_period'].max()
    rolling_data = {}
    for window_name, offset in [('last7days', 6), ('last15days', 14), ('last30days', 29)]:
        start_sp = max(1, max_sp - offset)
        window_df = stats_df[stats_df['scoring_period'] >= start_sp]
        agg = window_df.groupby('playerId')[existing_sum_cols].sum().reset_index()
        agg = compute_rate_stats(agg)
        rolling_data[window_name] = agg.set_index('playerId')

    # Position and team mapping
    player_positions = {}
    roster_team_map = {}
    for _, row in roster_df.iterrows():
        pname = row.get('player_name', '')
        slots = row.get('player_eligible_slots', '[]')
        player_positions[pname] = classify_position(slots)
        roster_team_map[pname] = row.get('team_id', None)

    bp_map = stats_df.drop_duplicates('playerId').set_index('playerId')['b_or_p'].to_dict()
    team_abbrev_map = stats_df.drop_duplicates('playerId').set_index('playerId')['team_abbrev'].to_dict()
    my_team_name = team_names.get(MY_TEAM_ID, f'Team {MY_TEAM_ID}')

    # Use today as the snapshot date for dry run
    date_str = datetime.now().strftime('%Y-%m-%d')
    rows = []

    for _, row in player_season.iterrows():
        pid = row['playerId']
        pname = row['playerName']

        # Position
        pos = player_positions.get(pname, None)
        if not pos:
            bp = bp_map.get(pid, 'batter')
            pos = 'SP' if bp == 'pitcher' else 'OF'
        if pos == 'UTIL':
            pos = 'DH'
        if pos not in ALL_POSITIONS:
            continue

        # Ownership
        roster_tid = roster_team_map.get(pname, None)
        if roster_tid == MY_TEAM_ID:
            owner_type = 'mine'
            owner_name = my_team_name
        elif roster_tid is not None:
            owner_type = 'league'
            owner_name = team_names.get(roster_tid, f'Team {roster_tid}')
        else:
            owner_type = 'free_agent'
            owner_name = 'Free Agent'

        # Build stats
        stats_data = {'season': {}, 'last7days': {}, 'last15days': {}, 'last30days': {}}
        for stat in ALL_STATS:
            if stat in row and pd.notna(row[stat]):
                stats_data['season'][stat] = round(float(row[stat]), 3)
        for wname in ['last7days', 'last15days', 'last30days']:
            if pid in rolling_data[wname].index:
                wrow = rolling_data[wname].loc[pid]
                for stat in ALL_STATS:
                    if stat in wrow and pd.notna(wrow[stat]):
                        stats_data[wname][stat] = round(float(wrow[stat]), 3)

        player_dict = {
            'name': pname,
            'playerId': pid,
            'position': pos,
            'proTeam': team_abbrev_map.get(pid, ''),
            'injuryStatus': 'ACTIVE',
            'owner': owner_name,
            'owner_type': owner_type,
            'stats': stats_data,
        }
        rows.append(flatten_player_to_row(date_str, player_dict))

    # Sort free agents and keep top 25 per position
    fa_rows = [r for r in rows if r['owner_type'] == 'free_agent']
    non_fa_rows = [r for r in rows if r['owner_type'] != 'free_agent']

    fa_by_pos = {}
    for r in fa_rows:
        fa_by_pos.setdefault(r['position'], []).append(r)

    trimmed_fa = []
    for pos, pos_fa in fa_by_pos.items():
        if pos in BATTER_POSITIONS:
            pos_fa.sort(key=lambda x: float(x.get('season_OPS', 0) or 0), reverse=True)
        else:
            pos_fa.sort(key=lambda x: float(x.get('season_ERA', 99) or 99))
        trimmed_fa.extend(pos_fa[:25])

    rows = non_fa_rows + trimmed_fa
    print(f"  Built {len(rows)} player rows for {date_str}")
    return rows, date_str


# --- HTML Generation ---

def generate_html(dashboard_data):
    """Generate the dashboard HTML file from the template."""
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")

    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        template = f.read()

    json_data = json.dumps(dashboard_data, indent=None)
    html = template.replace('/*__DASHBOARD_DATA__*/', json_data)

    os.makedirs(os.path.dirname(DASHBOARD_OUTPUT), exist_ok=True)
    with open(DASHBOARD_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\nDashboard written to: {DASHBOARD_OUTPUT}")


# --- Git Push ---

def git_push_dashboard():
    """Commit and push the updated dashboard to GitHub Pages."""
    print("\n--- Pushing dashboard to GitHub Pages ---")
    dashboard_rel = os.path.relpath(DASHBOARD_OUTPUT, WEBSITE_DIR)
    today = datetime.now().strftime('%Y-%m-%d')

    try:
        # Stage the dashboard file
        subprocess.run(
            ['git', '-C', WEBSITE_DIR, 'add', dashboard_rel],
            check=True, capture_output=True, text=True
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ['git', '-C', WEBSITE_DIR, 'diff', '--cached', '--quiet'],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            print("  No changes to commit — dashboard is already up to date.")
            return

        # Commit
        subprocess.run(
            ['git', '-C', WEBSITE_DIR, 'commit', '-m',
             f'Update fantasy baseball dashboard ({today})'],
            check=True, capture_output=True, text=True
        )
        print("  Committed.")

        # Push
        subprocess.run(
            ['git', '-C', WEBSITE_DIR, 'push'],
            check=True, capture_output=True, text=True
        )
        print("  Pushed to remote. Dashboard is live!")

    except subprocess.CalledProcessError as e:
        print(f"  Git error: {e}")
        if e.stderr:
            print(f"  stderr: {e.stderr}")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description='Fantasy Baseball Dashboard Data Collector')
    parser.add_argument('--dry-run', action='store_true',
                        help='Use 2025 CSV data instead of hitting ESPN API')
    parser.add_argument('--no-push', action='store_true',
                        help='Skip git commit/push of the dashboard')
    args = parser.parse_args()

    # Check existing data
    existing_dates = get_existing_dates()
    print(f"Existing snapshot dates in CSV: {len(existing_dates)}")
    if existing_dates:
        print(f"  Latest: {max(existing_dates)}")

    if args.dry_run:
        # Dry run: build from 2025 data, save one snapshot
        rows, date_str = collect_dry_run_snapshot()
        if date_str not in existing_dates:
            append_rows_to_csv(rows)
        else:
            print(f"  Date {date_str} already exists in CSV, skipping append.")

    else:
        # Live mode: check for missing dates and backfill
        missing = get_missing_dates(existing_dates, lookback_days=7)
        today_str = datetime.now().strftime('%Y-%m-%d')

        if not missing:
            print("All recent dates are already collected.")
        else:
            print(f"Missing dates to collect: {missing}")

            for date_str in missing:
                # ESPN API doesn't support historical snapshots per day, so
                # we can only fetch "current" data. For backfill, we tag it
                # with the actual run date since the data reflects "now".
                if date_str == today_str:
                    rows = collect_live_snapshot(date_str)
                    append_rows_to_csv(rows)
                else:
                    # For past missed dates, we still fetch current data
                    # but tag it with today's date only (no true backfill).
                    # This avoids fake historical data.
                    print(f"  Skipping {date_str} (ESPN API only returns current state).")

            # Always collect today if not already done
            if today_str not in existing_dates and today_str not in missing:
                rows = collect_live_snapshot(today_str)
                append_rows_to_csv(rows)

    # Rebuild dashboard from latest CSV data
    print("\n--- Generating Dashboard HTML ---")
    dashboard_data = load_csv_for_dashboard()
    if dashboard_data:
        # Set season year correctly for dry run
        if args.dry_run:
            dashboard_data['season'] = 2025
        generate_html(dashboard_data)
    else:
        print("No data available to generate dashboard.")
        return

    # Summary
    print("\n--- Dashboard Summary ---")
    for pos, pdata in dashboard_data['positions'].items():
        my_count = len(pdata['my_players'])
        league_count = len(pdata['league_players'])
        fa_count = len(pdata['free_agents'])
        print(f"  {pos:3s}: Mine={my_count}, League={league_count}, FA={fa_count}")

    # Git push
    if not args.no_push:
        git_push_dashboard()
    else:
        print("\n  --no-push flag set, skipping git push.")


if __name__ == '__main__':
    main()
