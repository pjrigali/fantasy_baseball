"""
Description:
    Writes a JSONL run-log entry for the fantasy-collect-all-data workflow.
    Reads the current row count of each Bronze output file, compares against
    the prior log entry to compute rows written this run, and appends the
    result. Used as Step 8 of the /fantasy-collect-all-data workflow.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/stats_espn_daily_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/activity_espn_season_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/lineups_mlb_batters_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_boxscore_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/rankings_espn_daily_<YEAR>.csv
    - data-lake/01_Bronze/fantasy_baseball/closer_depth_mlb_<YEAR>.csv
    - data-lake/00_Logs/fantasy_baseball/fantasy-collect-all-data.jsonl (prior entry)

Outputs:
    Appends one JSONL line to:
    data-lake/00_Logs/fantasy_baseball/fantasy-collect-all-data.jsonl
"""

import csv
import json
import os
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

YEAR = date.today().year

root = os.getcwd()
if os.path.exists(os.path.join(root, 'data-lake')):
    BASE    = os.path.join(root, 'data-lake', '01_Bronze', 'fantasy_baseball')
    LOG_DIR = os.path.join(root, 'data-lake', '00_Logs', 'fantasy_baseball')
else:
    BASE    = os.path.join(root, '.data_lake', '01_Bronze', 'fantasy_baseball')
    LOG_DIR = os.path.join(root, '.data_lake', '00_Logs', 'fantasy_baseball')

LOG_PATH = os.path.join(LOG_DIR, 'fantasy-collect-all-data.jsonl')

STEP_FILES = {
    'espn_stats':    f'stats_espn_daily_{YEAR}.csv',
    'espn_activity': f'activity_espn_season_{YEAR}.csv',
    'mlb_lineups':   f'lineups_mlb_batters_{YEAR}.csv',
    'mlb_boxscore':  f'stats_mlb_boxscore_{YEAR}.csv',
    'espn_rankings': f'rankings_espn_daily_{YEAR}.csv',
    'mlb_closers':   f'closer_depth_mlb_{YEAR}.csv',
}

# ---------------------------------------------------------------------------
# Load prior totals
# ---------------------------------------------------------------------------

os.makedirs(LOG_DIR, exist_ok=True)

prior_totals = {}
if os.path.exists(LOG_PATH):
    with open(LOG_PATH, encoding='utf-8') as f:
        lines = [ln for ln in f if ln.strip()]
    if lines:
        prior_totals = json.loads(lines[-1]).get('csv_total_rows', {})

# ---------------------------------------------------------------------------
# Compute current totals and deltas
# ---------------------------------------------------------------------------

steps = {}
csv_total_rows = {}
errors = []

for step, fname in STEP_FILES.items():
    path = os.path.join(BASE, fname)
    if not os.path.exists(path):
        errors.append(step)
        continue
    with open(path, encoding='utf-8') as f:
        n = sum(1 for _ in csv.DictReader(f))
    csv_total_rows[step] = n
    steps[step] = n - prior_totals.get(step, 0)

# ---------------------------------------------------------------------------
# Write log entry
# ---------------------------------------------------------------------------

entry = {
    'ts':              datetime.now().isoformat(timespec='seconds'),
    'workflow':        'fantasy-collect-all-data',
    'status':          'error' if errors else 'ok',
    'steps':           steps,
    'csv_total_rows':  csv_total_rows,
    'errors':          errors,
}

with open(LOG_PATH, 'a', encoding='utf-8') as f:
    f.write(json.dumps(entry) + '\n')

print(f'Logged run: {json.dumps(entry, indent=2)}')
