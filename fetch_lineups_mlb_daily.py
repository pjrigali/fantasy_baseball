"""
fetch_lineups_mlb_daily.py
==========================
Scrapes today's MLB lineups via mlb_processing.scrape_mlb_lineups()
and appends them to the Bronze data lake CSV.

Output file:
  data-lake/01_Bronze/fantasy_baseball/lineups_mlb_batters_<YEAR>.csv

Primary keys (deduplication):
  batters  — (date, team_tricode, player_name, batting_order)

Usage:
    python fetch_lineups_mlb_daily.py [--date YYYY-MM-DD] [--year YYYY]
"""

import os
import sys
import csv
import argparse
from datetime import datetime

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = os.path.join(PROJECT_ROOT, 'data-lake', '01_Bronze', 'fantasy_baseball')

BATTER_FIXED_COLS = ['date', 'team_tricode', 'batting_order', 'player_name', 'player_position']


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

def load_existing_batter_keys(csv_path: str) -> set:
    """Return a set of (date, team_tricode, player_name, batting_order) tuples."""
    keys = set()
    if not os.path.exists(csv_path):
        return keys
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((row.get('date', ''), row.get('team_tricode', ''),
                      row.get('player_name', ''), str(row.get('batting_order', ''))))
    return keys


def append_rows(csv_path: str, rows: list, existing_keys: set,
                fixed_cols: list, key_fn) -> int:
    """
    Append new rows to csv_path, skipping duplicates detected via key_fn.
    Creates the file with headers if it doesn't exist.
    Returns the count of rows written.
    """
    if not rows:
        return 0

    # Determine full column list
    all_cols = list(fixed_cols)  # copy
    for r in rows:
        for k in r.keys():
            if k not in all_cols:
                all_cols.append(k)

    file_exists = os.path.exists(csv_path) and os.path.getsize(csv_path) > 0
    if file_exists:
        with open(csv_path, 'r', newline='', encoding='utf-8') as f:
            existing_cols = csv.DictReader(f).fieldnames or []
        # Merge: keep existing order, append any new cols
        new_cols = [c for c in all_cols if c not in existing_cols]
        all_cols = existing_cols + new_cols

    written = 0
    mode = 'a' if file_exists else 'w'
    with open(csv_path, mode, newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=all_cols, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        for r in rows:
            key = key_fn(r)
            if key in existing_keys:
                continue
            writer.writerow(r)
            existing_keys.add(key)
            written += 1
    return written


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description='Fetch daily MLB lineups.')
    parser.add_argument('--date', type=str, default=None,
                        help='Target date in YYYY-MM-DD format (default: today)')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year used in output filename (default: current year)')
    args = parser.parse_args()

    year = args.year
    target_date = args.date or datetime.now().strftime('%Y-%m-%d')

    print(f'=== MLB Daily Lineup Fetch ===')
    print(f'  Year  : {year}')
    print(f'  Date  : {target_date}')

    # 1. Scrape MLB.com
    print('  Scraping lineups...')
    try:
        batters = mp.scrape_mlb_lineups(target_date)
        print(f'  Raw batters: {len(batters)}')
    except Exception as e:
        print(f'  ERROR scraping lineups: {e}')
        return

    if not batters:
        print('  No lineup data returned. Lineups may not be posted yet.')
        return

    # 2. Output paths
    os.makedirs(DATA_PATH, exist_ok=True)
    batter_path = os.path.join(DATA_PATH, f'lineups_mlb_batters_{year}.csv')

    # 3. Load existing keys
    existing_batter_keys = load_existing_batter_keys(batter_path)
    print(f'  Existing batter rows : {len(existing_batter_keys)}')

    # 4. Append with dedup
    b_written = append_rows(
        batter_path, batters, existing_batter_keys, BATTER_FIXED_COLS,
        key_fn=lambda r: (r.get('date', ''), r.get('team_tricode', ''), r.get('player_name', ''), str(r.get('batting_order', '')))
    )

    print(f'  Batters  — fetched: {len(batters)}, new: {b_written}, skipped: {len(batters) - b_written}')
    print(f'  Batter CSV : {batter_path}')
    print('=== Done ===')


if __name__ == '__main__':
    main()
