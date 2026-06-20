"""
Description:
    Idea 17 - Section C: Bayesian Updating. Correctly weights small-sample hot streaks
    by shrinking each player's recent "good-game rate" toward a population prior:
      1. Empirical-Bayes Beta-Binomial - fit a Beta prior to the population of player
         good-game rates (method of moments), then compute each player's posterior
         mean rate. Hot streaks on few games shrink toward the prior; streaks on many
         games barely move.
      2. Regression-to-mean - compares the raw rolling rate to the shrunk posterior to
         quantify how much of the streak is expected to persist; flags players whose
         shrunk rate stays above the population posterior median.
    A "good game" = single-game OPS >= 0.800 (batters) / per-outing K9 >= 9.0
    (pitchers). Uses scipy only for the Beta where convenient; math is explicit.

Source Data:
    - Per-game series from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout validation summary.
    - reports/method_c_bayesian.md
"""

import os
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, evaluate_scores, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_c_bayesian.md')
MIN_GAMES = 4
GOOD_GAME = {'batter': 0.800, 'pitcher': 9.0}   # OPS / K9 threshold for a "good game"

# ---------------------------------------------------------------------------
# Empirical Bayes
# ---------------------------------------------------------------------------

def fit_beta_prior(rates, weights):
    """
    Method-of-moments Beta(alpha, beta) fit to a set of observed rates (weighted by
    sample size so noisy 1-game rates don't dominate the prior).
    """
    rates = np.asarray(rates, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if rates.size == 0 or weights.sum() == 0:
        return 1.0, 1.0
    mean = np.average(rates, weights=weights)
    var = np.average((rates - mean) ** 2, weights=weights)
    if var <= 1e-9 or not (0 < mean < 1):
        return 1.0, 1.0
    common = mean * (1 - mean) / var - 1
    alpha = max(mean * common, 0.1)
    beta = max((1 - mean) * common, 0.1)
    return alpha, beta


def player_rate(values, ptype):
    """Return (successes, trials) of good games for a player's series."""
    thr = GOOD_GAME[ptype]
    trials = len(values)
    succ = sum(1 for v in values if v >= thr)
    return succ, trials

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_type(group, ctx, ptype_label, lines):
    A = lines.append
    ptype = group[0]['player_type'] if group else 'batter'
    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    # gather per-player (succ, trials)
    records = []
    for p in group:
        _, vals = wf.get_primary_series(p, ctx)
        if len(vals) < MIN_GAMES:
            continue
        s, n = player_rate(vals, ptype)
        records.append((p, s, n))

    if not records:
        A(f'### {ptype_label}\n\n_No usable series._\n')
        return None

    rates = [s / n for (_, s, n) in records]
    weights = [n for (_, s, n) in records]
    alpha0, beta0 = fit_beta_prior(rates, weights)

    # posterior mean per player
    post = {}
    raw = {}
    for (p, s, n) in records:
        pm = (alpha0 + s) / (alpha0 + beta0 + n)
        post[p['player_id'].strip()] = pm
        raw[p['player_id'].strip()] = s / n

    post_median = float(np.median(list(post.values())))
    raw_median = float(np.median(list(raw.values())))

    flagged = {pid for pid, pm in post.items() if pm > post_median}
    metrics = evaluate_flags(group, flagged)

    # also a naive raw-rate flag for comparison (shows shrinkage value)
    raw_flagged = {pid for pid, rv in raw.items() if rv > raw_median}
    raw_metrics = evaluate_flags(group, raw_flagged)

    post_r = evaluate_scores(group, post, higher_is_better=True)['r']
    raw_r = evaluate_scores(group, raw, higher_is_better=True)['r']

    print(f'\n--- {ptype_label} ---  (players={len(records)}, base={base:.2f})')
    print(f'  Beta prior: alpha0={alpha0:.2f} beta0={beta0:.2f} '
          f'(prior mean {alpha0/(alpha0+beta0):.3f})')
    print(f'  posterior-mean rank-biserial r={fmt(post_r,3)}  vs raw-rate r={fmt(raw_r,3)}')
    print('  ' + format_metrics_line('Posterior > median', metrics))
    print('  ' + format_metrics_line('Raw rate > median', raw_metrics))

    A(f'### {ptype_label}')
    A('')
    A(f'- Players with usable series (>= {MIN_GAMES} games): **{len(records)}** '
      f'| base top-rate: **{base:.2f}**')
    A(f'- Fitted Beta prior: `alpha0={alpha0:.2f}`, `beta0={beta0:.2f}` '
      f'(prior good-game rate `{alpha0/(alpha0+beta0):.3f}`)')
    A(f'- Posterior-mean rank-biserial r = `{fmt(post_r,3)}`; '
      f'raw-rate r = `{fmt(raw_r,3)}` — shrinkage '
      f'{"improves" if (post_r or 0) > (raw_r or 0) else "does not improve"} separation.')
    A('')
    A('| Estimate | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|----------|-----------|--------|----|------|----|----|----|')
    for nm, m in [('Empirical-Bayes posterior > median', metrics),
                  ('Naive raw rate > median', raw_metrics)]:
        A(f"| {nm} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f}"
          f" | {m['lift']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    A('')
    return {'posterior': metrics, 'raw': raw_metrics, 'post_r': post_r,
            'flagged_posterior': flagged}


def run_season(pickups_path, ctx, season_label, lines):
    lines.append(f'## {season_label}')
    lines.append('')
    pickups = load_pickups(pickups_path)
    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']
    label_quartiles(batters)
    label_quartiles(pitchers)
    b = analyze_type(batters, ctx, 'Batters', lines)
    p = analyze_type(pitchers, ctx, 'Pitchers', lines)
    return {'batters': b, 'pitchers': p}


def main():
    print('Section C — Bayesian Updating')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section C — Bayesian Updating (Small-Sample Shrinkage)', '',
             'Shrinks each player\'s recent good-game rate toward an empirical-Bayes '
             'Beta prior so short hot streaks are weighted correctly. Compares the '
             'shrunk posterior against the naive raw rate to show the value of '
             'regression-to-mean.', '']
    run_season(BEST_PICKUPS_FILE, ctx26, '2026 (primary)', lines)

    if os.path.exists(BEST_PICKUPS_2025_FILE):
        print('\nLoading 2025 cross-check...')
        ctx25 = wf.load_all_2025()
        lines.append('---'); lines.append('')
        run_season(BEST_PICKUPS_2025_FILE, ctx25, '2025 (cross-season)', lines)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'\nReport written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
