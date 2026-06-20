"""
Description:
    Central pre-pickup feature builder for Idea 17 (Multi-Method Waiver Signal
    Detection). One module, three views of the same player-week so every method
    section (A-I) draws from a single source of truth:
      1. Window aggregates  - 7/14/21-day rolling stats + ownership + batting order
                              + opportunity context (for clustering, anomaly,
                              Bayesian, market, bandit sections).
      2. Per-game series    - per-game OPS (batters) / per-outing ERA & K9 (pitchers)
                              in a lookback window (for changepoint, sequential,
                              forecasting sections).
      3. Standardized matrix- imputed, z-scored numeric matrix + feature names + a
                              row-validity mask (for the ML-style methods).
    Reuses the pure stat helpers from the Idea 16 script (compute_ops, compute_k9,
    etc.) rather than reimplementing them. 2026 game logs come from the boxscore
    file (keyed by player_id, includes bench players); 2025 cross-check uses the
    name-keyed mlb_stats_daily file.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_stats_boxscore.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_rankings_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_lineups_batters.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_closers_depth.csv
    - data-lake/01_Bronze/fantasy_baseball/player_map.csv (canonical identity; was player_lookup.csv)
    - data-lake/01_Bronze/fantasy_baseball/2025_espn_best_pickups.csv  (cross-check)
    - data-lake/01_Bronze/fantasy_baseball/2025_mlb_stats_daily.csv    (cross-check)

Outputs:
    - None. Library module consumed by the method_*.py scripts.
"""

import os
import sys
import csv
from datetime import timedelta
from collections import defaultdict

import numpy as np

from waiver_common import (
    DATA_DIR, IDEA16_DIR, BOXSCORE_FILE, RANKINGS_FILE, LINEUPS_FILE,
    CLOSERS_FILE, PLAYER_LOOKUP_FILE, MLB_DAILY_2025_FILE,
    parse_date, normalize_name, safe_float, safe_int,
)

# Reuse the pure stat helpers from Idea 16 (no reimplementation).
if IDEA16_DIR not in sys.path:
    sys.path.insert(0, IDEA16_DIR)
from analyze_waiver_signals_espn_2026 import (   # noqa: E402
    compute_ops, compute_k9, compute_era, compute_whip,
    compute_svhd_per_app, compute_ab_per_game,
    ownership_slope, batting_slot_mode, top_order_rate,
)

WINDOWS = (7, 14, 21)
SERIES_LOOKBACK_DAYS = 30   # how far back to pull the per-game series

# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_player_lookup():
    """espn_player_id (str) -> normalized MLB name (str).

    Backed by the canonical player_map.csv. The accented MLB name lives in the
    mlb_name column (was archive_name); normalize_name(mlb_name) is the same join
    key the game-log loaders use, so this is a drop-in with broader coverage."""
    lookup = {}
    with open(PLAYER_LOOKUP_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            eid = row['espn_player_id'].strip()
            aname = (row.get('mlb_name') or '').strip()
            if eid and aname:
                lookup[eid] = normalize_name(aname)
    return lookup


def load_boxscore_by_name():
    """
    2026 game logs keyed by normalized player name. NOTE: the boxscore's player_id
    column is the MLB Stats API id, NOT the ESPN id used in best_pickups/rankings --
    so we resolve via name (best_pickups espn_id -> player_lookup archive_name ->
    normalized), the same path the 2025 cross-check uses. Only rows that actually
    played are kept (did_play=1), which still includes bench-eligible players who
    appeared, unlike the legacy per-player archive.
    """
    by_name = defaultdict(list)
    with open(BOXSCORE_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            if safe_int(row.get('did_play', 0)) == 0:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name', ''))
            if key:
                by_name[key].append(row)
    for key in by_name:
        by_name[key].sort(key=lambda r: r['_date'])
    return by_name


def load_mlb_daily_by_name(path):
    """Prior-season game logs keyed by normalized player name (no player_id link)."""
    by_name = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name') or row.get('playerName', ''))
            if key:
                by_name[key].append(row)
    for key in by_name:
        by_name[key].sort(key=lambda r: r['_date'])
    return by_name


def load_rankings_by_id():
    """player_id (str) -> ownership rows sorted by date."""
    by_id = defaultdict(list)
    with open(RANKINGS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            pid = (row.get('player_id') or '').strip()
            if pid:
                by_id[pid].append(row)
    for pid in by_id:
        by_id[pid].sort(key=lambda r: r['_date'])
    return by_id


def load_lineups_by_name():
    """normalized player name -> batting-order rows sorted by date."""
    by_name = defaultdict(list)
    with open(LINEUPS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name', ''))
            if key:
                by_name[key].append(row)
    for key in by_name:
        by_name[key].sort(key=lambda r: r['_date'])
    return by_name


def load_closers_depth():
    """
    Opportunity context for the saves cascade (section H).
    Returns dict player_id -> latest closers-depth row (most recent date_scraped).
    """
    latest = {}
    if not os.path.exists(CLOSERS_FILE):
        return latest
    with open(CLOSERS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            pid = (row.get('player_id') or '').strip()
            d = parse_date(row.get('date_scraped', ''))
            if not pid or d is None:
                continue
            if pid not in latest or d > latest[pid]['_date']:
                row['_date'] = d
                latest[pid] = row
    return latest


def load_all_2026():
    """Convenience bundle of every 2026 source the feature builder needs."""
    return {
        'player_lookup': load_player_lookup(),
        'game_logs':     load_boxscore_by_name(),    # keyed by name (MLB id != ESPN id)
        'rankings':      load_rankings_by_id(),       # keyed by ESPN player_id
        'lineups':       load_lineups_by_name(),      # keyed by name
        'closers':       load_closers_depth(),        # keyed by ESPN player_id
        'keyed_by':      'name',
    }


def load_all_2025():
    """Cross-season bundle: 2025 has only name-keyed game logs."""
    return {
        'player_lookup': load_player_lookup(),
        'game_logs':     load_mlb_daily_by_name(MLB_DAILY_2025_FILE),  # keyed by name
        'rankings':      defaultdict(list),
        'lineups':       defaultdict(list),
        'closers':       {},
        'keyed_by':      'name',
    }

# ---------------------------------------------------------------------------
# Per-pickup window lookup helpers
# ---------------------------------------------------------------------------

def _game_log_key(pickup, ctx):
    """Resolve the key to look up a pickup's game logs given the bundle's keying."""
    if ctx['keyed_by'] == 'player_id':
        return (pickup.get('player_id') or '').strip()
    return ctx['player_lookup'].get((pickup.get('player_id') or '').strip())


def _windowed(rows, acq_date, days, inclusive_end=False):
    lo = acq_date - timedelta(days=days)
    if inclusive_end:
        return [r for r in rows if lo <= r['_date'] <= acq_date]
    return [r for r in rows if lo <= r['_date'] < acq_date]

# ---------------------------------------------------------------------------
# View 1 — window aggregate features
# ---------------------------------------------------------------------------

def build_window_features(pickup, ctx):
    """
    7/14/21-day rolling aggregates + ownership + batting order + opportunity.
    Mirrors Idea 16's build_features (reusing its compute_* helpers) and extends it
    with the 21-day window and a few opportunity signals. Returns a flat dict of
    {feature_name: float|None}.
    """
    acq_date = parse_date(pickup['acquisition_date'])
    ptype    = pickup['player_type']
    if acq_date is None:
        return {}

    glog_key = _game_log_key(pickup, ctx)
    pid      = (pickup.get('player_id') or '').strip()
    glog     = ctx['game_logs'].get(glog_key, []) if glog_key else []
    rank_all = ctx['rankings'].get(pid, [])
    name_key = ctx['player_lookup'].get(pid)
    lu_all   = ctx['lineups'].get(name_key, []) if name_key else []

    feats = {}
    for w in WINDOWS:
        arch = _windowed(glog, acq_date, w)
        rank = _windowed(rank_all, acq_date, w, inclusive_end=True)

        if ptype == 'batter':
            feats[f'ops_{w}d']         = compute_ops(arch)
            feats[f'ab_per_game_{w}d'] = compute_ab_per_game(arch)
            n = len(arch)
            if n > 0:
                feats[f'hr_per_game_{w}d']  = sum(safe_int(r.get('HR', 0)) for r in arch) / n
                feats[f'sb_per_game_{w}d']  = sum(safe_int(r.get('SB', 0)) for r in arch) / n
                feats[f'r_per_game_{w}d']   = sum(safe_int(r.get('R', 0))  for r in arch) / n
                feats[f'rbi_per_game_{w}d'] = sum(safe_int(r.get('RBI', 0)) for r in arch) / n
                feats[f'games_played_{w}d'] = float(n)
            else:
                for k in ('hr_per_game', 'sb_per_game', 'r_per_game', 'rbi_per_game', 'games_played'):
                    feats[f'{k}_{w}d'] = None
        else:
            feats[f'k9_{w}d']           = compute_k9(arch)
            feats[f'era_{w}d']          = compute_era(arch)
            feats[f'whip_{w}d']         = compute_whip(arch)
            feats[f'svhd_per_app_{w}d'] = compute_svhd_per_app(arch)
            appearances = sum(1 for r in arch if safe_int(r.get('OUTS', 0)) > 0)
            feats[f'appearances_{w}d']  = float(appearances) if arch else None
            feats[f'qs_{w}d']           = float(sum(safe_int(r.get('QS', 0)) for r in arch)) if arch else None

        if rank:
            feats['pct_owned_at_pickup']   = safe_float(rank[-1].get('pct_owned'))
            feats[f'pct_change_mean_{w}d'] = (
                sum(safe_float(r.get('pct_change', 0), 0.0) for r in rank) / len(rank)
            )
            feats[f'ownership_slope_{w}d'] = ownership_slope(rank)

    if ptype == 'batter':
        lu7 = _windowed(lu_all, acq_date, 7)
        feats['batting_slot_mode_7d'] = batting_slot_mode(lu7)
        feats['top_order_rate_7d']    = top_order_rate(lu7)
        # lineup promotion: slot 7d ago vs slot now (negative = moved up)
        lu14 = _windowed(lu_all, acq_date, 14)
        early = batting_slot_mode([r for r in lu14 if r['_date'] < acq_date - timedelta(days=7)])
        late  = batting_slot_mode(lu7)
        if early is not None and late is not None:
            feats['lineup_promotion_7d'] = float(early - late)  # >0 means promoted (lower number)
    else:
        # saves opportunity context from closers depth
        cl = ctx['closers'].get(pid)
        if cl:
            feats['closer_sv_hld_ratio'] = safe_float(cl.get('sv_hld_ratio'))
            feats['closer_recent_svhd']  = (safe_float(cl.get('recent_sv'), 0.0) or 0.0) + \
                                           (safe_float(cl.get('recent_hld'), 0.0) or 0.0)

    return feats

# ---------------------------------------------------------------------------
# View 2 — per-game time series
# ---------------------------------------------------------------------------

def build_game_series(pickup, ctx, lookback_days=SERIES_LOOKBACK_DAYS):
    """
    Per-game performance series in the lookback window before acquisition.
    Batters  -> list of (date, single-game OPS) for games with a plate appearance.
    Pitchers -> dict with 'era' and 'k9' lists of (date, per-outing value).
    Used by changepoint, sequential, and forecasting sections.
    """
    acq_date = parse_date(pickup['acquisition_date'])
    ptype    = pickup['player_type']
    if acq_date is None:
        return {'dates': [], 'values': []}

    glog_key = _game_log_key(pickup, ctx)
    glog = ctx['game_logs'].get(glog_key, []) if glog_key else []
    window = _windowed(glog, acq_date, lookback_days)

    if ptype == 'batter':
        dates, vals = [], []
        for r in window:
            if safe_int(r.get('AB', 0)) + safe_int(r.get('B_BB', 0)) + \
               safe_int(r.get('HBP', 0)) + safe_int(r.get('SF', 0)) == 0:
                continue
            ops = compute_ops([r])
            if ops is not None:
                dates.append(r['_date'])
                vals.append(ops)
        return {'dates': dates, 'values': vals, 'stat': 'ops'}
    else:
        dates, era_vals, k9_vals = [], [], []
        for r in window:
            if safe_int(r.get('OUTS', 0)) <= 0:
                continue
            era = compute_era([r])
            k9  = compute_k9([r])
            dates.append(r['_date'])
            era_vals.append(era if era is not None else 0.0)
            k9_vals.append(k9 if k9 is not None else 0.0)
        return {'dates': dates, 'era': era_vals, 'k9': k9_vals, 'stat': 'pitching'}

def get_primary_series(pickup, ctx, lookback_days=SERIES_LOOKBACK_DAYS):
    """
    One good-direction per-game series per pickup, unified across player types so the
    changepoint / sequential / forecasting sections share logic:
      batters  -> per-game OPS  (higher is better)
      pitchers -> per-outing K9 (higher is better)
    Returns (dates, values). Higher always means 'better' so an upward shift is the
    add signal in every case.
    """
    s = build_game_series(pickup, ctx, lookback_days)
    if pickup['player_type'] == 'batter':
        return s['dates'], s['values']
    return s['dates'], s.get('k9', [])


# ---------------------------------------------------------------------------
# View 3 — standardized numeric matrix
# ---------------------------------------------------------------------------

# Canonical feature lists per player type (excludes high-missingness extras;
# method scripts can request a subset).
BATTER_FEATURES = [
    'ops_7d', 'ops_14d', 'ops_21d',
    'ab_per_game_7d', 'ab_per_game_14d',
    'hr_per_game_14d', 'sb_per_game_14d', 'r_per_game_14d', 'rbi_per_game_14d',
    'games_played_14d',
    'pct_owned_at_pickup', 'pct_change_mean_7d', 'ownership_slope_7d',
    'batting_slot_mode_7d', 'top_order_rate_7d',
]
PITCHER_FEATURES = [
    'k9_7d', 'k9_14d', 'k9_21d',
    'era_7d', 'era_14d', 'era_21d',
    'whip_7d', 'whip_14d',
    'svhd_per_app_14d', 'appearances_14d', 'qs_14d',
    'pct_owned_at_pickup', 'pct_change_mean_7d', 'ownership_slope_7d',
]


def build_matrix(pickups, feature_list, standardize=True):
    """
    Assemble a numeric matrix from a list of pickups (each must already carry
    '_features'). Missing values are median-imputed per column; columns are then
    z-scored (mean 0, std 1) when standardize=True.

    Returns (X, kept_features, valid_mask) where:
      X            : np.ndarray, shape (n_pickups, n_kept_features)
      kept_features: feature names retained (those with >=1 non-missing value)
      valid_mask   : np.bool_ array, True where the pickup had >=1 real feature value
    """
    n = len(pickups)
    raw = np.full((n, len(feature_list)), np.nan, dtype=float)
    for i, p in enumerate(pickups):
        feats = p.get('_features', {})
        for j, fname in enumerate(feature_list):
            v = feats.get(fname)
            if v is not None:
                raw[i, j] = float(v)

    # drop all-nan columns
    keep_cols = [j for j in range(len(feature_list)) if not np.all(np.isnan(raw[:, j]))]
    kept_features = [feature_list[j] for j in keep_cols]
    raw = raw[:, keep_cols]

    valid_mask = ~np.all(np.isnan(raw), axis=1)

    # median impute per column
    X = raw.copy()
    for j in range(X.shape[1]):
        col = X[:, j]
        med = np.nanmedian(col)
        if np.isnan(med):
            med = 0.0
        col[np.isnan(col)] = med
        X[:, j] = col

    if standardize:
        mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd == 0] = 1.0
        X = (X - mu) / sd

    return X, kept_features, valid_mask
