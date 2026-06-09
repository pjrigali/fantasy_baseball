"""
Description:
    Verifies all Bronze-layer output files produced by the fantasy-collect-all-data
    workflow. Checks that each expected file exists, prints its total row count,
    full date range, and last recorded date. Used as Step 7 of the
    /fantasy-collect-all-data workflow.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/stats_espn_daily_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/activity_espn_season_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/lineups_mlb_batters_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/skipped_mlb_daily_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/rankings_espn_daily_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/closer_depth_mlb_<YEAR>.csv

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
    BASE = os.path.join(root, '.data_lake', '01_Bronze', 'fantasy_baseball')

FILES = {
    'ESPN Daily Stats': f'stats_espn_daily_{YEAR}.csv',
    'ESPN Activity':    f'activity_espn_season_{YEAR}.csv',
    'MLB Lineups':      f'lineups_mlb_batters_{YEAR}.csv',
    'MLB Game Logs':    f'stats_mlb_boxscore_{YEAR}.csv',
    'MLB Skipped':      f'skipped_mlb_daily_{YEAR}.csv',
    'ESPN Rankings':    f'rankings_espn_daily_{YEAR}.csv',
    'MLB Closer Depth': f'closer_depth_mlb_{YEAR}.csv',
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
