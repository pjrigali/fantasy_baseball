"""
Description:
    Shared utilities for Idea 17 (Multi-Method Waiver Signal Detection). Holds the
    path constants, small parsing/statistics helpers, and the quartile-labeling logic
    used by every method script (A-I) and the consolidation step. Pure-Python; no
    third-party dependencies so it can be imported anywhere in the pipeline.

Source Data:
    - None directly. Defines paths into data-lake/01_Bronze/fantasy_baseball/ that the
      feature builder and method scripts read from.

Outputs:
    - None. Library module (helpers + constants only).
"""

import os
import csv
import unicodedata
from datetime import datetime

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
BASE_DIR    = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
DATA_DIR    = os.path.join(BASE_DIR, 'data-lake', '01_Bronze', 'fantasy_baseball')
REPORTS_DIR = os.path.join(SCRIPT_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

# Idea 16 module dir (we reuse its pure stat helpers).
IDEA16_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'idea_16_waiver_signals'))

# 2026 (primary season — full feature set)
BEST_PICKUPS_FILE  = os.path.join(DATA_DIR, '2026_espn_best_pickups.csv')
BOXSCORE_FILE      = os.path.join(DATA_DIR, '2026_mlb_stats_boxscore.csv')
RANKINGS_FILE      = os.path.join(DATA_DIR, '2026_espn_rankings_daily.csv')
LINEUPS_FILE       = os.path.join(DATA_DIR, '2026_mlb_lineups_batters.csv')
CLOSERS_FILE       = os.path.join(DATA_DIR, '2026_mlb_closers_depth.csv')
# Canonical single source of truth (was player_lookup.csv). Column mlb_name is the
# accented MLB/archive name; normalize_name(mlb_name) reproduces the old key.
PLAYER_LOOKUP_FILE = os.path.join(DATA_DIR, 'player_map.csv')

# 2025 (cross-season check — game-log features only, name-keyed)
BEST_PICKUPS_2025_FILE = os.path.join(DATA_DIR, '2025_espn_best_pickups.csv')
MLB_DAILY_2025_FILE    = os.path.join(DATA_DIR, '2025_mlb_stats_daily.csv')

# ---------------------------------------------------------------------------
# Parsing / formatting helpers
# ---------------------------------------------------------------------------

def parse_date(s):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def normalize_name(name):
    """Strip accents and lowercase for fuzzy name matching."""
    nfkd = unicodedata.normalize('NFKD', str(name))
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


def safe_float(v, default=None):
    try:
        f = float(v)
        return f if (f == f) else default  # exclude NaN
    except (ValueError, TypeError):
        return default


def safe_int(v, default=0):
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return default


def fmt(val, decimals=3):
    if val is None:
        return 'N/A'
    return f'{val:.{decimals}f}'


def percentile(values, p):
    """p-th percentile of a list (linear interpolation). None-safe."""
    sorted_vals = sorted(v for v in values if v is not None)
    if not sorted_vals:
        return None
    idx = (len(sorted_vals) - 1) * p / 100.0
    lo = int(idx)
    hi = lo + 1
    frac = idx - lo
    if hi >= len(sorted_vals):
        return sorted_vals[lo]
    return sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo])

# ---------------------------------------------------------------------------
# Ground-truth loading + quartile labeling
# ---------------------------------------------------------------------------

def load_pickups(path):
    """Load a *_espn_best_pickups.csv into a list of dict rows."""
    rows = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def label_quartiles(group):
    """
    Tag each pickup '_label' = top / bottom / middle by composite_z within the group.
    Returns (q25, q75). Mutates the dicts in place (matches Idea 16 semantics).
    """
    zs = [safe_float(p['composite_z']) for p in group
          if safe_float(p['composite_z']) is not None]
    q25 = percentile(zs, 25)
    q75 = percentile(zs, 75)
    for p in group:
        z = safe_float(p['composite_z'])
        if z is None or q25 is None or q75 is None:
            p['_label'] = 'middle'
        elif z >= q75:
            p['_label'] = 'top'
        elif z <= q25:
            p['_label'] = 'bottom'
        else:
            p['_label'] = 'middle'
    return q25, q75
