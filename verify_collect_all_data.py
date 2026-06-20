"""
Description:
    Verifies all Bronze-layer output files produced by the fantasy-collect-all-data
    workflow. Checks that each expected file exists, prints its total row count,
    full date range, and last recorded date. Used as Step 7 of the
    /fantasy-collect-all-data workflow.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_stats_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_activity_season.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_mlb_lineups_batters.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_mlb_stats_boxscore.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_mlb_stats_daily_skipped.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_espn_rankings_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/<YEAR>_mlb_closers_depth.csv

Outputs:
    Prints a verification summary to stdout. No files written.
"""

import csv
import os
import sys
from datetime import date

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

YEAR = date.today().year

root = os.getcwd()
if os.path.exists(os.path.join(root, 'data-lake')):
    BASE = os.path.join(root, 'data-lake', '01_Bronze', 'fantasy_baseball')
else:
    BASE = os.path.join(root, 'data-lake', '01_Bronze', 'fantasy_baseball')

FILES = {
    'ESPN Daily Stats': f'{YEAR}_espn_stats_daily.csv',
    'ESPN Activity':    f'{YEAR}_espn_activity_season.csv',
    'MLB Lineups':      f'{YEAR}_mlb_lineups_batters.csv',
    'MLB Game Logs':    f'{YEAR}_mlb_stats_boxscore.csv',
    'MLB Skipped':      f'{YEAR}_mlb_stats_daily_skipped.csv',
    'ESPN Rankings':    f'{YEAR}_espn_rankings_daily.csv',
    'MLB Closer Depth': f'{YEAR}_mlb_closers_depth.csv',
}

DATE_COL_OVERRIDES = {
    'MLB Skipped':      'date_ran',
    'MLB Closer Depth': 'date_scraped',
}

# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

missing = []
for label, fname in FILES.items():
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        print(f'[MISSING] {label}: {fname}')
        missing.append(label)
        continue

    with open(path, encoding='utf-8') as f:
        rows = list(csv.DictReader(f))

    col = DATE_COL_OVERRIDES.get(label, 'date')
    if rows and col in rows[0]:
        dates = sorted(set(r[col][:10] for r in rows))
        date_range = f'{dates[0]} to {dates[-1]}'
        last = dates[-1]
    else:
        date_range = 'N/A'
        last = 'N/A'

    print(f'{label}:')
    print(f'  Rows       : {len(rows)}')
    print(f'  Date range : {date_range}')
    print(f'  Last date  : {last}')
    print()

if missing:
    print(f'WARNING: {len(missing)} file(s) not found: {", ".join(missing)}')
    sys.exit(1)
else:
    print('All files verified.')
