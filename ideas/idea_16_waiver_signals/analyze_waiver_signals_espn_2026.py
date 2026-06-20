"""
Description:
    Waiver Wire Signal Detection — Pre-Pickup Indicators of Breakout Pickups (Idea 16).
    Works backwards from best_pickups_espn_{YEAR}.csv (idea 15 ground truth) to identify
    what pre-pickup metrics predict top-quartile vs bottom-quartile waiver adds. Runs on
    both 2026 (full feature set: game logs + ownership + batting order) and 2025 (game-log
    features only — no prior-year rankings or lineups in the data lake). Cross-year
    comparison isolates which game-stat signals hold across both seasons.

Source Data (2026):
    - data-lake/01_Bronze/fantasy_baseball/best_pickups_espn_2026.csv
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_daily_2026_archive.csv
    - data-lake/01_Bronze/fantasy_baseball/rankings_espn_daily_2026.csv
    - data-lake/01_Bronze/fantasy_baseball/lineups_mlb_batters_2026.csv
    - data-lake/01_Bronze/fantasy_baseball/player_lookup.csv

Source Data (2025 cross-validation):
    - data-lake/01_Bronze/fantasy_baseball/best_pickups_espn_2025.csv
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_daily_2025.csv

Outputs:
    - fantasy_baseball/ideas/idea_16_waiver_signals/reports/waiver_signals_2026.md
"""

import csv
import os
import unicodedata
from datetime import datetime, timedelta
from collections import defaultdict

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..', '..', '..'))
DATA_DIR = os.path.join(BASE_DIR, 'data-lake', '01_Bronze', 'fantasy_baseball')
REPORTS_DIR = os.path.join(SCRIPT_DIR, 'reports')
os.makedirs(REPORTS_DIR, exist_ok=True)

BEST_PICKUPS_FILE  = os.path.join(DATA_DIR, 'best_pickups_espn_2026.csv')
MLB_ARCHIVE_FILE   = os.path.join(DATA_DIR, 'stats_mlb_daily_2026_archive.csv')
RANKINGS_FILE      = os.path.join(DATA_DIR, 'rankings_espn_daily_2026.csv')
LINEUPS_FILE       = os.path.join(DATA_DIR, 'lineups_mlb_batters_2026.csv')
PLAYER_LOOKUP_FILE = os.path.join(DATA_DIR, 'player_lookup.csv')

BEST_PICKUPS_2025_FILE = os.path.join(DATA_DIR, 'best_pickups_espn_2025.csv')
MLB_ARCHIVE_2025_FILE  = os.path.join(DATA_DIR, 'stats_mlb_daily_2025.csv')

REPORT_FILE = os.path.join(REPORTS_DIR, 'waiver_signals_2026.md')

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def parse_date(s):
    for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y/%m/%d'):
        try:
            return datetime.strptime(s.strip(), fmt).date()
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
        return int(v)
    except (ValueError, TypeError):
        return default


def fmt(val, decimals=3):
    if val is None:
        return 'N/A'
    return f'{val:.{decimals}f}'


def percentile(values, p):
    """p-th percentile of a list (linear interpolation)."""
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
# Data loaders
# ---------------------------------------------------------------------------

def load_player_lookup():
    """Returns dict: espn_player_id (str) -> archive_name_normalized (str)."""
    lookup = {}
    with open(PLAYER_LOOKUP_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            eid = row['espn_player_id'].strip()
            aname = row.get('archive_name', '').strip()
            if eid and aname:
                lookup[eid] = normalize_name(aname)
    return lookup


def load_mlb_archive(path=None):
    """Returns dict: player_name_normalized -> list of rows sorted by date."""
    path = path or MLB_ARCHIVE_FILE
    by_player = defaultdict(list)
    with open(path, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            # 2025 file uses 'playerName'; 2026 archive uses 'player_name'
            key = normalize_name(row.get('player_name') or row.get('playerName', ''))
            if key:
                by_player[key].append(row)
    for key in by_player:
        by_player[key].sort(key=lambda r: r['_date'])
    return by_player


def load_rankings():
    """Returns dict: player_id (str) -> list of rows sorted by date."""
    by_player = defaultdict(list)
    with open(RANKINGS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            pid = row.get('player_id', '').strip()
            if pid:
                by_player[pid].append(row)
    for key in by_player:
        by_player[key].sort(key=lambda r: r['_date'])
    return by_player


def load_lineups():
    """Returns dict: player_name_normalized -> list of rows sorted by date."""
    by_player = defaultdict(list)
    with open(LINEUPS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            d = parse_date(row.get('date', ''))
            if d is None:
                continue
            row['_date'] = d
            key = normalize_name(row.get('player_name', ''))
            if key:
                by_player[key].append(row)
    for key in by_player:
        by_player[key].sort(key=lambda r: r['_date'])
    return by_player

# ---------------------------------------------------------------------------
# Stat computation
# ---------------------------------------------------------------------------

def compute_ops(rows):
    total_h   = sum(safe_int(r.get('H', 0))   for r in rows)
    total_ab  = sum(safe_int(r.get('AB', 0))  for r in rows)
    total_bb  = sum(safe_int(r.get('B_BB', 0)) for r in rows)
    total_hbp = sum(safe_int(r.get('HBP', 0)) for r in rows)
    total_sf  = sum(safe_int(r.get('SF', 0))  for r in rows)
    total_tb  = sum(safe_int(r.get('TB', 0))  for r in rows)
    obp_denom = total_ab + total_bb + total_hbp + total_sf
    if obp_denom == 0:
        return None
    obp = (total_h + total_bb + total_hbp) / obp_denom
    slg = total_tb / total_ab if total_ab > 0 else 0.0
    return obp + slg


def compute_k9(rows):
    total_k    = sum(safe_int(r.get('K', 0))    for r in rows)
    total_outs = sum(safe_int(r.get('OUTS', 0)) for r in rows)
    if total_outs == 0:
        return None
    return total_k * 27.0 / total_outs


def compute_era(rows):
    total_er   = sum(safe_int(r.get('ER', 0))   for r in rows)
    total_outs = sum(safe_int(r.get('OUTS', 0)) for r in rows)
    if total_outs == 0:
        return None
    return total_er * 27.0 / total_outs


def compute_whip(rows):
    total_ph   = sum(safe_int(r.get('P_H', 0))  for r in rows)
    total_pbb  = sum(safe_int(r.get('P_BB', 0)) for r in rows)
    total_outs = sum(safe_int(r.get('OUTS', 0)) for r in rows)
    if total_outs == 0:
        return None
    ip = total_outs / 3.0
    return (total_ph + total_pbb) / ip


def compute_svhd_per_app(rows):
    total_svhd  = sum(safe_int(r.get('SVHD', 0)) for r in rows)
    appearances = sum(1 for r in rows if safe_int(r.get('OUTS', 0)) > 0)
    if appearances == 0:
        return None
    return total_svhd / appearances


def compute_ab_per_game(rows):
    games_played = sum(1 for r in rows if safe_int(r.get('AB', 0)) > 0)
    if games_played == 0:
        return None
    return sum(safe_int(r.get('AB', 0)) for r in rows) / games_played


def ownership_slope(rows):
    """Linear OLS slope of pct_owned across ranked rows."""
    ys = [safe_float(r.get('pct_owned', 0), 0.0) for r in rows]
    n = len(ys)
    if n < 2:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    den = sum((xs[i] - mean_x) ** 2 for i in range(n))
    return num / den if den != 0 else 0.0


def batting_slot_mode(lineup_rows):
    slots = [safe_int(r.get('batting_order', 0)) for r in lineup_rows
             if safe_int(r.get('batting_order', 0)) > 0]
    if not slots:
        return None
    counts = defaultdict(int)
    for s in slots:
        counts[s] += 1
    return max(counts, key=counts.get)


def top_order_rate(lineup_rows):
    """Fraction of games where batting_order <= 3."""
    slots = [safe_int(r.get('batting_order', 0)) for r in lineup_rows
             if safe_int(r.get('batting_order', 0)) > 0]
    if not slots:
        return None
    return sum(1 for s in slots if s <= 3) / len(slots)

# ---------------------------------------------------------------------------
# Feature builder
# ---------------------------------------------------------------------------

def build_features(pickup, player_lookup, mlb_archive, rankings_data, lineups_data):
    pid       = pickup['player_id'].strip()
    acq_date  = parse_date(pickup['acquisition_date'])
    ptype     = pickup['player_type']
    if acq_date is None:
        return {}

    archive_key = player_lookup.get(pid)

    def archive_window(days):
        if not archive_key:
            return []
        rows = mlb_archive.get(archive_key, [])
        lo = acq_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] < acq_date]

    def rank_window(days):
        rows = rankings_data.get(pid, [])
        lo = acq_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] <= acq_date]

    def lineup_window(days):
        if not archive_key:
            return []
        rows = lineups_data.get(archive_key, [])
        lo = acq_date - timedelta(days=days)
        return [r for r in rows if lo <= r['_date'] < acq_date]

    feats = {}

    for w in (7, 14):
        arch = archive_window(w)
        rank = rank_window(w)

        if ptype == 'batter':
            feats[f'ops_{w}d']          = compute_ops(arch)
            feats[f'ab_per_game_{w}d']  = compute_ab_per_game(arch)
            n = len(arch)
            if n > 0:
                feats[f'hr_per_game_{w}d'] = sum(safe_int(r.get('HR', 0)) for r in arch) / n
                feats[f'sb_per_game_{w}d'] = sum(safe_int(r.get('SB', 0)) for r in arch) / n
                feats[f'r_per_game_{w}d']  = sum(safe_int(r.get('R', 0))  for r in arch) / n
                feats[f'games_played_{w}d'] = n
            else:
                feats[f'hr_per_game_{w}d']  = None
                feats[f'sb_per_game_{w}d']  = None
                feats[f'r_per_game_{w}d']   = None
                feats[f'games_played_{w}d'] = None
        else:
            feats[f'k9_{w}d']            = compute_k9(arch)
            feats[f'era_{w}d']           = compute_era(arch)
            feats[f'whip_{w}d']          = compute_whip(arch)
            feats[f'svhd_per_app_{w}d']  = compute_svhd_per_app(arch)
            appearances = sum(1 for r in arch if safe_int(r.get('OUTS', 0)) > 0)
            feats[f'appearances_{w}d'] = appearances if arch else None

        if rank:
            feats['pct_owned_at_pickup']    = safe_float(rank[-1].get('pct_owned'))
            feats[f'pct_change_mean_{w}d']  = (
                sum(safe_float(r.get('pct_change', 0), 0.0) for r in rank) / len(rank)
            )
            feats[f'ownership_slope_{w}d']  = ownership_slope(rank)

    if ptype == 'batter':
        lu7 = lineup_window(7)
        feats['batting_slot_mode_7d'] = batting_slot_mode(lu7)
        feats['top_order_rate_7d']    = top_order_rate(lu7)

    return feats

# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def mann_whitney_r(group1, group2):
    """Rank-biserial correlation r ∈ [−1, 1]. r > 0 → group1 tends higher."""
    n1, n2 = len(group1), len(group2)
    if n1 == 0 or n2 == 0:
        return None
    u = 0.0
    for x in group1:
        for y in group2:
            if x > y:
                u += 1
            elif x == y:
                u += 0.5
    return (2 * u) / (n1 * n2) - 1


def find_optimal_threshold(top_vals, bottom_vals, direction):
    """
    Single-feature decision boundary that maximises F1 (top = positive class).
    Returns (threshold, precision, recall, f1).
    """
    candidates = sorted(set(top_vals + bottom_vals))
    best = (None, 0.0, 0.0, 0.0)
    for thresh in candidates:
        if direction == 'higher':
            tp = sum(1 for v in top_vals    if v >= thresh)
            fp = sum(1 for v in bottom_vals if v >= thresh)
            fn = sum(1 for v in top_vals    if v <  thresh)
        else:
            tp = sum(1 for v in top_vals    if v <= thresh)
            fp = sum(1 for v in bottom_vals if v <= thresh)
            fn = sum(1 for v in top_vals    if v >  thresh)
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec  = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        if f1 > best[3]:
            best = (thresh, prec, rec, f1)
    return best


def label_quartiles(group):
    """Label each pickup as top/bottom/middle quartile by composite_z within the group."""
    zs = [safe_float(p['composite_z']) for p in group if safe_float(p['composite_z']) is not None]
    q25 = percentile(zs, 25)
    q75 = percentile(zs, 75)
    for p in group:
        z = safe_float(p['composite_z'])
        if z is None:
            p['_label'] = 'middle'
        elif z >= q75:
            p['_label'] = 'top'
        elif z <= q25:
            p['_label'] = 'bottom'
        else:
            p['_label'] = 'middle'
    return q25, q75


def has_archive_data(p):
    feats = p['_features']
    if p['player_type'] == 'batter':
        return feats.get('ops_7d') is not None or feats.get('ops_14d') is not None
    return feats.get('k9_7d') is not None or feats.get('k9_14d') is not None


def analyze_group(group):
    """Compare top vs bottom quartile across all features; return ranked results."""
    top    = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    if not top or not bottom:
        return []

    all_features = set()
    for p in group:
        all_features.update(p['_features'].keys())

    results = []
    for feat in sorted(all_features):
        top_vals    = [p['_features'][feat] for p in top    if p['_features'].get(feat) is not None]
        bottom_vals = [p['_features'][feat] for p in bottom if p['_features'].get(feat) is not None]
        if len(top_vals) < 3 or len(bottom_vals) < 3:
            continue

        r = mann_whitney_r(top_vals, bottom_vals)
        if r is None:
            continue

        direction = 'higher' if r >= 0 else 'lower'
        thresh, prec, rec, f1 = find_optimal_threshold(top_vals, bottom_vals, direction)

        results.append({
            'feature':        feat,
            'r':              r,
            'abs_r':          abs(r),
            'direction':      direction,
            'top_median':     percentile(top_vals, 50),
            'bottom_median':  percentile(bottom_vals, 50),
            'threshold':      thresh,
            'precision':      prec,
            'recall':         rec,
            'f1':             f1,
            'n_top':          len(top_vals),
            'n_bottom':       len(bottom_vals),
        })

    results.sort(key=lambda x: x['abs_r'], reverse=True)
    return results

# ---------------------------------------------------------------------------
# Audit: which signals fired for each top pickup
# ---------------------------------------------------------------------------

def audit_signals(pickup, top_features, n=6):
    """Return list of (feature, value, threshold, direction) for firing signals."""
    feats = pickup['_features']
    firing = []
    for res in top_features[:n]:
        val = feats.get(res['feature'])
        if val is None or res['threshold'] is None:
            continue
        fired = (res['direction'] == 'higher' and val >= res['threshold']) or \
                (res['direction'] == 'lower'  and val <= res['threshold'])
        if fired:
            firing.append((res['feature'], val, res['threshold'], res['direction']))
    return firing

# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def build_cross_year_section(batter_results_26, pitcher_results_26,
                              batter_results_25, pitcher_results_25):
    """Returns markdown lines comparing 2026 vs 2025 effect sizes for shared game-log features."""
    lines = []
    A = lines.append
    A('## Cross-Year Validation — 2026 vs 2025 (Game-Log Features Only)')
    A('')
    A('2025 signals use only `stats_mlb_daily_2025.csv` (no ownership or batting-order data).')
    A('Features that show **consistent direction and similar |r|** across both seasons are the most robust.')
    A('')

    for player_type, res_26, res_25 in [
        ('Batters',  batter_results_26,  batter_results_25),
        ('Pitchers', pitcher_results_26, pitcher_results_25),
    ]:
        A(f'### {player_type}')
        A('')
        A('| Feature | r 2026 | Dir 26 | r 2025 | Dir 25 | Consistent? |')
        A('|---------|--------|--------|--------|--------|-------------|')

        # Index 2025 results by feature name
        res_25_by_feat = {r['feature']: r for r in res_25}

        # Only show game-log features (no ownership/lineups — those don't exist in 2025)
        ownership_and_lineup = {'pct_owned_at_pickup', 'pct_change_mean_7d', 'pct_change_mean_14d',
                                 'ownership_slope_7d', 'ownership_slope_14d',
                                 'batting_slot_mode_7d', 'top_order_rate_7d'}
        shared = [r for r in res_26 if r['feature'] not in ownership_and_lineup
                  and r['feature'] in res_25_by_feat]
        shared.sort(key=lambda x: x['abs_r'], reverse=True)

        for res in shared[:12]:
            r25 = res_25_by_feat[res['feature']]
            consistent = '✓' if (res['r'] >= 0) == (r25['r'] >= 0) else '✗'
            sym26 = '↑' if res['direction'] == 'higher' else '↓'
            sym25 = '↑' if r25['direction'] == 'higher' else '↓'
            A(f"| `{res['feature']}` | {fmt(res['r'],3)} | {sym26} | {fmt(r25['r'],3)} | {sym25} | {consistent} |")
        A('')

    return lines


def build_report(batters, pitchers, batter_results, pitcher_results,
                 batter_q25, batter_q75, pitcher_q25, pitcher_q75,
                 total_pickups, coverage_batters, coverage_pitchers,
                 batter_results_25=None, pitcher_results_25=None):
    lines = []
    A = lines.append

    A('# Waiver Wire Signal Detection — Pre-Pickup Indicator Analysis (2026)')
    A('')
    A('**Analysis date:** 2026-06-19  ')
    A('**Ground truth source:** `best_pickups_espn_2026.csv` (Idea 15)  ')
    A(f'**Total pickups:** {total_pickups} '
      f'({len(batters)} batters, {len(pitchers)} pitchers)  ')
    A(f'**Archive coverage:** {coverage_batters:.0%} of batters, '
      f'{coverage_pitchers:.0%} of pitchers had pre-pickup game log data  ')
    A('')
    A('---')
    A('')
    A('## Methodology')
    A('')
    A('1. **Label quartiles** — top-quartile: composite_z ≥ 75th pct (within player type);'
      ' bottom-quartile: composite_z ≤ 25th pct; middle excluded from testing')
    A('2. **Build pre-pickup features** — 7-day and 14-day rolling windows before `acquisition_date`'
      ' from `stats_mlb_daily_2026_archive`, `rankings_espn_daily`, and `lineups_mlb_batters`')
    A('3. **Rank features** — Mann-Whitney U rank-biserial correlation r ∈ [−1, 1]:'
      ' |r| near 1 means the feature consistently separates top from bottom pickups')
    A('4. **Find thresholds** — single-feature decision boundary that maximises F1 score'
      ' (top-quartile = positive class)')
    A('')
    A('> **Note on cross-season validation:** Prior-year `activity_espn_season` and'
      ' `rankings_espn_daily` are not in the data lake, so 2024/2025 back-testing is'
      ' deferred. The signals here are single-season observations — treat effect sizes'
      ' as directional, not definitive.')
    A('')
    A('---')
    A('')

    # ---- BATTERS ----
    top_b    = [p for p in batters if p['_label'] == 'top']
    bottom_b = [p for p in batters if p['_label'] == 'bottom']
    A('## Batter Signals')
    A('')
    A(f'- **Top quartile ({len(top_b)} pickups):** composite_z ≥ {fmt(batter_q75, 2)}')
    A(f'- **Bottom quartile ({len(bottom_b)} pickups):** composite_z ≤ {fmt(batter_q25, 2)}')
    A('')
    A('### Signal Importance — Batters')
    A('')
    A('| # | Feature | r | Direction | Threshold | Precision | Recall | F1 | Top Median | Bot Median |')
    A('|---|---------|---|-----------|-----------|-----------|--------|-----|------------|------------|')
    for i, res in enumerate(batter_results[:15], 1):
        sym = '↑' if res['direction'] == 'higher' else '↓'
        op  = '≥' if res['direction'] == 'higher' else '≤'
        A(f"| {i} | `{res['feature']}` | {fmt(res['r'],3)} | {sym} {res['direction']}"
          f" | {op} {fmt(res['threshold'],3)}"
          f" | {fmt(res['precision'],2)} | {fmt(res['recall'],2)} | {fmt(res['f1'],2)}"
          f" | {fmt(res['top_median'],3)} | {fmt(res['bottom_median'],3)} |")
    A('')
    A('### Prescriptive Rules — Batters')
    A('')
    A('Rules from the top 8 discriminating features. Each threshold maximises F1 on the 2026 labeled set.')
    A('')
    for res in batter_results[:8]:
        op = '≥' if res['direction'] == 'higher' else '≤'
        A(f"- **`{res['feature']}` {op} {fmt(res['threshold'],3)}**"
          f"  (r = {fmt(res['r'],3)}, precision = {fmt(res['precision'],2)},"
          f" recall = {fmt(res['recall'],2)}, F1 = {fmt(res['f1'],2)})")
    A('')
    A('---')
    A('')

    # ---- PITCHERS ----
    top_p    = [p for p in pitchers if p['_label'] == 'top']
    bottom_p = [p for p in pitchers if p['_label'] == 'bottom']
    A('## Pitcher Signals')
    A('')
    A(f'- **Top quartile ({len(top_p)} pickups):** composite_z ≥ {fmt(pitcher_q75, 2)}')
    A(f'- **Bottom quartile ({len(bottom_p)} pickups):** composite_z ≤ {fmt(pitcher_q25, 2)}')
    A('')
    A('### Signal Importance — Pitchers')
    A('')
    A('| # | Feature | r | Direction | Threshold | Precision | Recall | F1 | Top Median | Bot Median |')
    A('|---|---------|---|-----------|-----------|-----------|--------|-----|------------|------------|')
    for i, res in enumerate(pitcher_results[:15], 1):
        sym = '↑' if res['direction'] == 'higher' else '↓'
        op  = '≥' if res['direction'] == 'higher' else '≤'
        A(f"| {i} | `{res['feature']}` | {fmt(res['r'],3)} | {sym} {res['direction']}"
          f" | {op} {fmt(res['threshold'],3)}"
          f" | {fmt(res['precision'],2)} | {fmt(res['recall'],2)} | {fmt(res['f1'],2)}"
          f" | {fmt(res['top_median'],3)} | {fmt(res['bottom_median'],3)} |")
    A('')
    A('### Prescriptive Rules — Pitchers')
    A('')
    A('Rules from the top 8 discriminating features.')
    A('')
    for res in pitcher_results[:8]:
        op = '≥' if res['direction'] == 'higher' else '≤'
        A(f"- **`{res['feature']}` {op} {fmt(res['threshold'],3)}**"
          f"  (r = {fmt(res['r'],3)}, precision = {fmt(res['precision'],2)},"
          f" recall = {fmt(res['recall'],2)}, F1 = {fmt(res['f1'],2)})")
    A('')
    A('---')
    A('')

    # ---- RETROSPECTIVE AUDIT ----
    A('## Retrospective Audit — Top Pickups')
    A('')
    A('Which of the top 6 signals were already firing in the pre-pickup window for each'
      ' top-quartile pickup. A signal "fires" when the player\'s pre-pickup value meets'
      ' the F1-optimal threshold.')
    A('')

    for label, group, results in [('Batters', batters, batter_results),
                                   ('Pitchers', pitchers, pitcher_results)]:
        top_grp = sorted(
            [p for p in group if p['_label'] == 'top'],
            key=lambda p: safe_float(p.get('composite_z'), 0.0),
            reverse=True
        )
        if not top_grp:
            continue
        A(f'### {label}')
        A('')
        A('| Player | Team | Acq Date | Z | Signals Firing |')
        A('|--------|------|----------|---|----------------|')
        for p in top_grp[:15]:
            firing = audit_signals(p, results, n=6)
            sig_strs = [f'`{f}` ({fmt(v,2)} {">=" if d=="higher" else "<="} {fmt(t,2)})' for f, v, t, d in firing]
            sigs = ', '.join(sig_strs) if sig_strs else '—'
            z = fmt(safe_float(p.get('composite_z')), 2)
            A(f"| {p['player_name']} | {p['team_name']} | {p['acquisition_date']} | {z} | {sigs} |")
        A('')

    # ---- CROSS-YEAR SECTION ----
    if batter_results_25 is not None and pitcher_results_25 is not None:
        A('---')
        A('')
        for line in build_cross_year_section(batter_results, pitcher_results,
                                              batter_results_25, pitcher_results_25):
            A(line)

    A('---')
    A('')
    A('## Limitations & Next Steps')
    A('')
    A('- **Sample size:** ~30–35 players per quartile group per type — effect sizes are directional, not definitive.')
    A('- **2025 cross-validation:** Game-log features only — no prior-year ownership or batting-order data in the lake.')
    A('- **Name coverage:** Players without a `player_lookup.csv` entry have no archive features.')
    A('- **Archive gaps:** `stats_mlb_daily_2026_archive.csv` is the legacy per-player fetcher; bench players not included.')
    A('')
    A('**Next steps:**')
    A('1. Build the weekly runtime watchlist script that applies these thresholds to the current available player pool')
    A('2. Progress to Idea 17 for unsupervised clustering, changepoint detection, and anomaly detection methods')

    return '\n'.join(lines)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print('Loading data...')
    player_lookup  = load_player_lookup()
    mlb_archive    = load_mlb_archive()
    rankings_data  = load_rankings()
    lineups_data   = load_lineups()

    pickups = []
    with open(BEST_PICKUPS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            pickups.append(row)

    print(f'  {len(player_lookup):,} entries in player_lookup')
    print(f'  {len(mlb_archive):,} players in MLB archive')
    print(f'  {len(rankings_data):,} players in rankings')
    print(f'  {len(lineups_data):,} players in lineups')
    print(f'  {len(pickups):,} pickups in best_pickups_espn_2026.csv')

    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']

    # --- Label quartiles ---
    batter_q25,  batter_q75  = label_quartiles(batters)
    pitcher_q25, pitcher_q75 = label_quartiles(pitchers)

    print(f'\n  Batters  — top: {sum(1 for b in batters  if b["_label"]=="top"):>3},'
          f' bottom: {sum(1 for b in batters  if b["_label"]=="bottom"):>3}')
    print(f'  Pitchers — top: {sum(1 for p in pitchers if p["_label"]=="top"):>3},'
          f' bottom: {sum(1 for p in pitchers if p["_label"]=="bottom"):>3}')

    # --- Build features ---
    print('\nBuilding pre-pickup features...')
    for p in pickups:
        p['_features'] = build_features(
            p, player_lookup, mlb_archive, rankings_data, lineups_data
        )

    # Coverage: % of pickups with at least one archive stat
    cov_b = sum(1 for p in batters  if has_archive_data(p)) / max(len(batters),  1)
    cov_p = sum(1 for p in pitchers if has_archive_data(p)) / max(len(pitchers), 1)
    print(f'  Archive coverage: batters {cov_b:.0%}, pitchers {cov_p:.0%}')

    # --- Statistical analysis ---
    print('\nRunning statistical analysis...')
    batter_results  = analyze_group(batters)
    pitcher_results = analyze_group(pitchers)

    print(f'  {len(batter_results)} batter features ranked')
    print(f'  {len(pitcher_results)} pitcher features ranked')

    print('\n=== TOP BATTER SIGNALS ===')
    for i, res in enumerate(batter_results[:10], 1):
        op = '>=' if res['direction'] == 'higher' else '<='
        print(f"  {i:2d}. {res['feature']:<35} r={res['r']:+.3f}"
              f"  thresh {op} {fmt(res['threshold'],3)}"
              f"  F1={fmt(res['f1'],2)}")

    print('\n=== TOP PITCHER SIGNALS ===')
    for i, res in enumerate(pitcher_results[:10], 1):
        op = '>=' if res['direction'] == 'higher' else '<='
        print(f"  {i:2d}. {res['feature']:<35} r={res['r']:+.3f}"
              f"  thresh {op} {fmt(res['threshold'],3)}"
              f"  F1={fmt(res['f1'],2)}")

    # --- 2025 cross-year validation (game-log features only) ---
    batter_results_25 = pitcher_results_25 = None
    if os.path.exists(BEST_PICKUPS_2025_FILE) and os.path.exists(MLB_ARCHIVE_2025_FILE):
        print('\nLoading 2025 data for cross-year validation...')
        mlb_archive_25 = load_mlb_archive(MLB_ARCHIVE_2025_FILE)

        pickups_25 = []
        with open(BEST_PICKUPS_2025_FILE, encoding='utf-8', errors='replace') as f:
            for row in csv.DictReader(f):
                pickups_25.append(row)

        batters_25  = [p for p in pickups_25 if p['player_type'] == 'batter']
        pitchers_25 = [p for p in pickups_25 if p['player_type'] == 'pitcher']
        label_quartiles(batters_25)
        label_quartiles(pitchers_25)

        empty_rank = defaultdict(list)
        empty_lineup = defaultdict(list)
        for p in pickups_25:
            p['_features'] = build_features(p, player_lookup, mlb_archive_25,
                                             empty_rank, empty_lineup)

        cov_b25 = sum(1 for p in batters_25  if has_archive_data(p)) / max(len(batters_25), 1)
        cov_p25 = sum(1 for p in pitchers_25 if has_archive_data(p)) / max(len(pitchers_25), 1)
        print(f'  2025 archive coverage: batters {cov_b25:.0%}, pitchers {cov_p25:.0%}')

        batter_results_25  = analyze_group(batters_25)
        pitcher_results_25 = analyze_group(pitchers_25)
        print(f'  {len(batter_results_25)} batter features ranked (2025)')
        print(f'  {len(pitcher_results_25)} pitcher features ranked (2025)')

    # --- Generate report ---
    report = build_report(
        batters, pitchers,
        batter_results, pitcher_results,
        batter_q25, batter_q75,
        pitcher_q25, pitcher_q75,
        total_pickups=len(pickups),
        coverage_batters=cov_b,
        coverage_pitchers=cov_p,
        batter_results_25=batter_results_25,
        pitcher_results_25=pitcher_results_25,
    )

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f'\nReport written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
