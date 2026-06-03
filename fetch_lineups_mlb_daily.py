"""
fetch_lineups_mlb_daily.py
==========================
Scrapes MLB lineups via mlb_processing.scrape_mlb_lineups() and appends
them to the Bronze data lake CSV. Automatically detects and backfills any
gap between the last recorded date and today — no need to run daily.

Output file:
  data-lake/01_Bronze/fantasy_baseball/lineups_mlb_batters_<YEAR>.csv

Primary keys (deduplication):
  batters  — (date, team_tricode, player_name, batting_order)

Usage:
    python fetch_lineups_mlb_daily.py [--date YYYY-MM-DD] [--year YYYY]

    --date  Collect a specific date only (skips auto-backfill).
            Default: auto-detect last recorded date and backfill to today.
    --year  Season year for the output filename (default: current year).
"""

import os
import sys
import csv
import time
import argparse
from datetime import datetime, date, timedelta

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from fantasy_baseball import mlb_processing as mp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATA_PATH = mp.DATA_PATH

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

SEASON_START = {2025: date(2025, 3, 27), 2026: date(2026, 3, 26)}


def get_last_recorded_date(csv_path: str) -> date | None:
    """Return the most recent date in the CSV, or None if file doesn't exist / is empty."""
    if not os.path.exists(csv_path):
        return None
    with open(csv_path, 'r', newline='', encoding='utf-8') as f:
        dates = [row['date'] for row in csv.DictReader(f) if row.get('date')]
    return date.fromisoformat(max(dates)) if dates else None


def fetch_date(ds: str, batter_path: str, existing_keys: set, dry_run: bool = False) -> int:
    """Scrape one date, append new rows (or preview in dry-run). Returns count written/previewed."""
    try:
        batters = mp.scrape_mlb_lineups(ds)
    except Exception as e:
        print(f'[ERROR] fetch_lineups_mlb_daily: {ds} — {e}')
        return 0
    if not batters:
        return 0
    key_fn = lambda r: (r.get('date', ''), r.get('team_tricode', ''),
                        r.get('player_name', ''), str(r.get('batting_order', '')))
    if dry_run:
        new = [r for r in batters if key_fn(r) not in existing_keys]
        for r in new:
            existing_keys.add(key_fn(r))
        return len(new)
    return append_rows(batter_path, batters, existing_keys, BATTER_FIXED_COLS, key_fn=key_fn)


def main():
    parser = argparse.ArgumentParser(description='Fetch MLB lineups, auto-backfilling any gaps.')
    parser.add_argument('--date', type=str, default=None,
                        help='Collect a specific date only (skips auto-backfill)')
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year used in output filename (default: current year)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview rows that would be written without saving to disk')
    args = parser.parse_args()

    year = args.year
    today = date.today()

    # Time-based end date when no explicit --date is given.
    # Before noon → stop at yesterday (lineups incomplete for today);
    # noon or later → include today.
    if args.date is None:
        end_date = (today - timedelta(days=1)) if datetime.now().hour < 12 else today
    else:
        end_date = None  # handled per-branch below

    os.makedirs(DATA_PATH, exist_ok=True)
    batter_path = os.path.join(DATA_PATH, f'lineups_mlb_batters_{year}.csv')
    existing_keys = load_existing_batter_keys(batter_path)

    total_written = 0
    tag = "[DRY-RUN]" if args.dry_run else "[OK]   "
    verb = "rows would be written" if args.dry_run else "rows written"

    if args.date:
        total_written = fetch_date(args.date, batter_path, existing_keys, dry_run=args.dry_run)
        print(f'{tag} fetch_lineups_mlb_daily: {total_written} {verb} | {args.date}')
        _log_last_date = args.date
    else:
        last = get_last_recorded_date(batter_path)
        season_open = SEASON_START.get(year, date(year, 3, 27))
        start = (last + timedelta(days=1)) if last else season_open

        if start > end_date:
            print(f'{tag} fetch_lineups_mlb_daily: already current through {end_date}, nothing to do')
            return

        dates_to_fetch = []
        d = start
        while d <= end_date:
            dates_to_fetch.append(d)
            d += timedelta(days=1)

        for i, d in enumerate(dates_to_fetch):
            total_written += fetch_date(d.strftime('%Y-%m-%d'), batter_path, existing_keys, dry_run=args.dry_run)
            if i < len(dates_to_fetch) - 1:
                time.sleep(0.5)

        print(f'{tag} fetch_lineups_mlb_daily: {total_written} {verb} | {start} → {end_date} ({len(dates_to_fetch)} dates)')
        _log_last_date = str(end_date)

    # ── Write run log ─────────────────────────────────────────────────────────
    if not args.dry_run:
        try:
            import json as _json
            from datetime import datetime as _dt
            _log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                    'data-lake', '00_Logs', 'fantasy_baseball')
            os.makedirs(_log_dir, exist_ok=True)
            _csv_rows = sum(1 for _ in open(batter_path, encoding='utf-8')) - 1
            _entry = {
                'ts'             : _dt.now().isoformat(timespec='seconds'),
                'workflow'       : 'fantasy-collect-mlb-lineups',
                'status'         : 'ok',
                'csv_path'       : batter_path,
                'csv_total_rows' : _csv_rows,
                'rows_written'   : total_written,
                'last_date_in_csv': _log_last_date,
            }
            with open(os.path.join(_log_dir, 'fantasy-collect-mlb-lineups.jsonl'), 'a', encoding='utf-8') as _f:
                _f.write(_json.dumps(_entry) + '\n')
        except Exception as _e:
            print(f'[WARN] run-log write failed: {_e}')


if __name__ == '__main__':
    main()
