"""
Description:
    Idea 17 - Section E: Anomaly Detection. Learns the distribution of "normal"
    pre-pickup player-weeks and flags players whose recent feature vector is unusual
    relative to the population - a breakout (or collapse). Two estimators, no
    scikit-learn:
      1. Isolation Forest - hand-rolled ensemble of random isolation trees; anomaly
         score = 2^(-E[path]/c(n)). Higher = more anomalous.
      2. Mahalanobis one-class - fit mean/covariance on the bulk of the population;
         distance beyond a chi-square cutoff = outside the "normal" region.
    Anomalies are split by direction (good vs bad) using the sign of the primary
    rolling stat versus the population median, so only "good-direction" anomalies are
    flagged as add candidates.

Source Data:
    - Pre-pickup feature matrix from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout validation summary.
    - fantasy_baseball/ideas/idea_17_multi_method_signals/reports/method_e_anomaly.md
"""

import os
import math
import numpy as np
from scipy.stats import chi2

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, evaluate_scores, format_metrics_line

np.random.seed(17)
REPORT_FILE = os.path.join(REPORTS_DIR, 'method_e_anomaly.md')

# Primary stat that defines the "good" direction per player type.
GOOD_DIR = {
    'batter':  ('ops_14d',  'higher'),
    'pitcher': ('era_14d',  'lower'),
}

# ---------------------------------------------------------------------------
# Isolation Forest (hand-rolled)
# ---------------------------------------------------------------------------

def _c_factor(n):
    if n <= 1:
        return 1.0
    H = math.log(n - 1) + 0.5772156649
    return 2 * H - 2 * (n - 1) / n


def _build_itree(X, depth, max_depth):
    n = X.shape[0]
    if depth >= max_depth or n <= 1:
        return {'size': n}
    # pick a feature with non-zero spread
    feats = list(range(X.shape[1]))
    np.random.shuffle(feats)
    for f in feats:
        col = X[:, f]
        lo, hi = col.min(), col.max()
        if hi > lo:
            split = np.random.uniform(lo, hi)
            left = X[col < split]
            right = X[col >= split]
            return {'f': f, 'split': split,
                    'left': _build_itree(left, depth + 1, max_depth),
                    'right': _build_itree(right, depth + 1, max_depth)}
    return {'size': n}


def _path_length(x, node, depth):
    if 'size' in node:
        return depth + _c_factor(node['size'])
    if x[node['f']] < node['split']:
        return _path_length(x, node['left'], depth + 1)
    return _path_length(x, node['right'], depth + 1)


def isolation_forest_scores(X, n_trees=150, sample_size=None):
    n = X.shape[0]
    sample_size = sample_size or min(256, n)
    max_depth = math.ceil(math.log2(max(sample_size, 2)))
    trees = []
    for _ in range(n_trees):
        sub = X[np.random.choice(n, sample_size, replace=False)] if n > sample_size else X
        trees.append(_build_itree(sub, 0, max_depth))
    c = _c_factor(sample_size)
    scores = np.zeros(n)
    for i in range(n):
        avg = np.mean([_path_length(X[i], t, 0) for t in trees])
        scores[i] = 2 ** (-avg / c)
    return scores

# ---------------------------------------------------------------------------
# Mahalanobis one-class
# ---------------------------------------------------------------------------

def mahalanobis_scores(X):
    """Robust-ish Mahalanobis distance to the population centroid."""
    mu = np.median(X, axis=0)
    cov = np.cov(X, rowvar=False)
    cov += np.eye(cov.shape[0]) * 1e-6  # regularize
    inv = np.linalg.pinv(cov)
    diff = X - mu
    d2 = np.einsum('ij,jk,ik->i', diff, inv, diff)
    return d2  # squared distance

# ---------------------------------------------------------------------------
# Analysis per type
# ---------------------------------------------------------------------------

def good_direction_mask(group, idx, feat_list):
    """Boolean over idx: True if the player's primary stat is on the 'good' side."""
    ptype = group[0]['player_type'] if group else 'batter'
    stat, direction = GOOD_DIR[ptype]
    vals = []
    for i in idx:
        v = group[i]['_features'].get(stat)
        vals.append(v)
    present = [v for v in vals if v is not None]
    med = np.median(present) if present else 0.0
    mask = np.zeros(len(idx), dtype=bool)
    for j, v in enumerate(vals):
        if v is None:
            continue
        mask[j] = (v >= med) if direction == 'higher' else (v <= med)
    return mask


def analyze_type(group, feat_list, ptype_label, lines):
    A = lines.append
    X_full, kept, mask = wf.build_matrix(group, feat_list)
    idx = [i for i in range(len(group)) if mask[i]]
    X = X_full[mask]
    if len(idx) < 10:
        A(f'### {ptype_label}\n\n_Insufficient data ({len(idx)} valid rows)._\n')
        return None

    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    iso = isolation_forest_scores(X)
    mah = mahalanobis_scores(X)
    good = good_direction_mask(group, idx, feat_list)

    # rank-biserial of raw scores (expect ~0: both breakouts & busts are anomalous)
    iso_by_id = {group[idx[j]]['player_id'].strip(): iso[j] for j in range(len(idx))}
    iso_raw_r = evaluate_scores(group, iso_by_id, higher_is_better=True)['r']
    # directional anomaly score: anomaly magnitude signed by good direction
    dir_sign = np.where(good, 1.0, -1.0)
    iso_dir = iso * dir_sign
    isodir_by_id = {group[idx[j]]['player_id'].strip(): iso_dir[j] for j in range(len(idx))}
    iso_dir_r = evaluate_scores(group, isodir_by_id, higher_is_better=True)['r']

    # flags: top-tercile anomaly AND good direction
    iso_thr = np.quantile(iso, 0.67)
    iso_flagged = {group[idx[j]]['player_id'].strip()
                   for j in range(len(idx)) if iso[j] >= iso_thr and good[j]}
    iso_metrics = evaluate_flags(group, iso_flagged)

    mah_cut = chi2.ppf(0.90, df=X.shape[1])
    mah_flagged = {group[idx[j]]['player_id'].strip()
                   for j in range(len(idx)) if mah[j] >= mah_cut and good[j]}
    mah_metrics = evaluate_flags(group, mah_flagged)

    n_iso_out = int((iso >= iso_thr).sum())
    n_mah_out = int((mah >= mah_cut).sum())

    print(f'\n--- {ptype_label} ---  (valid rows={len(idx)}, base top-rate={base:.2f})')
    print(f'  iso raw rank-biserial r={fmt(iso_raw_r,3)} (undirected),'
          f' directional r={fmt(iso_dir_r,3)}')
    print(f'  iForest outliers={n_iso_out}, Mahalanobis outliers={n_mah_out}')
    print('  ' + format_metrics_line('iForest good-dir flags', iso_metrics))
    print('  ' + format_metrics_line('Mahalanobis good-dir flags', mah_metrics))

    A(f'### {ptype_label}')
    A('')
    A(f'- Valid rows: **{len(idx)}** | base top-rate: **{base:.2f}**')
    A(f'- Undirected iForest rank-biserial r = `{fmt(iso_raw_r,3)}` '
      '(near 0 expected — anomalies include both breakouts and collapses)')
    A(f'- Direction-signed iForest r = `{fmt(iso_dir_r,3)}` '
      '(positive = good-direction anomalies skew toward top pickups)')
    A('')
    A('| Method | Outliers | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|--------|----------|-----------|--------|----|------|----|----|----|')
    A(f"| Isolation Forest (top-tercile + good dir) | {n_iso_out} | {iso_metrics['precision']:.2f}"
      f" | {iso_metrics['recall']:.2f} | {iso_metrics['f1']:.2f} | {iso_metrics['lift']:.2f}"
      f" | {iso_metrics['tp']} | {iso_metrics['fp']} | {iso_metrics['fn']} |")
    A(f"| Mahalanobis (chi2 p90 + good dir) | {n_mah_out} | {mah_metrics['precision']:.2f}"
      f" | {mah_metrics['recall']:.2f} | {mah_metrics['f1']:.2f} | {mah_metrics['lift']:.2f}"
      f" | {mah_metrics['tp']} | {mah_metrics['fp']} | {mah_metrics['fn']} |")
    A('')

    return {'isoforest': iso_metrics, 'mahalanobis': mah_metrics,
            'iso_dir_r': iso_dir_r, 'flagged_iso': iso_flagged}


def run_season(pickups_path, ctx, season_label, lines):
    lines.append(f'## {season_label}')
    lines.append('')
    pickups = load_pickups(pickups_path)
    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']
    label_quartiles(batters)
    label_quartiles(pitchers)
    for p in pickups:
        p['_features'] = wf.build_window_features(p, ctx)
    b = analyze_type(batters, wf.BATTER_FEATURES, 'Batters', lines)
    p = analyze_type(pitchers, wf.PITCHER_FEATURES, 'Pitchers', lines)
    return {'batters': b, 'pitchers': p}


def main():
    print('Section E — Anomaly Detection')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section E — Anomaly Detection', '',
             'Flags players whose recent pre-pickup feature vector is unusual relative '
             'to the population, split by direction so only good-direction anomalies '
             'count as add candidates. Isolation Forest and Mahalanobis one-class are '
             'both hand-rolled (no sklearn).', '']
    run_season(BEST_PICKUPS_FILE, ctx26, '2026 (primary)', lines)

    if os.path.exists(BEST_PICKUPS_2025_FILE):
        print('\nLoading 2025 cross-check...')
        ctx25 = wf.load_all_2025()
        lines.append('---')
        lines.append('')
        run_season(BEST_PICKUPS_2025_FILE, ctx25, '2025 (cross-season, game-log features only)', lines)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'\nReport written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
