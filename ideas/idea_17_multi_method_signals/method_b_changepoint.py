"""
Description:
    Idea 17 - Section B: Statistical Change Detection. Pinpoints the game where a
    player's performance regime shifted, rather than smoothing over it with a fixed
    rolling window. Three detectors on each player's good-direction per-game series
    (batter OPS / pitcher K9), no ruptures dependency:
      1. CUSUM - one-sided cumulative-sum control chart; fires on sustained upward
         drift (not a single outlier game).
      2. Binary-segmentation changepoint (PELT-style) - hand-rolled exact single
         changepoint via maximal mean-shift; reports the shift date + magnitude.
      3. Bayesian changepoint - posterior probability that a change occurred in the
         recent window, robust to the small samples in short pre-pickup windows.
    A player is flagged when a recent, sustained, upward shift is detected.

Source Data:
    - Per-game series from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout validation summary.
    - reports/method_b_changepoint.md
"""

import os
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_b_changepoint.md')
MIN_GAMES = 5

# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def cusum_upward(values, k_sigma=0.5, h_sigma=4.0):
    """
    One-sided upward CUSUM. Returns (fired, peak_index). Slack k and threshold h are
    scaled by the series std. Fires when the cumulative positive deviation from the
    early-baseline mean crosses h.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < MIN_GAMES:
        return False, None
    base = x[:max(2, n // 3)]
    mu = base.mean()
    sd = x.std() or 1.0
    k = k_sigma * sd
    h = h_sigma * sd
    s = 0.0
    for i in range(n):
        s = max(0.0, s + (x[i] - mu) - k)
        if s > h:
            return True, i
    return False, None


def best_changepoint(values):
    """
    Exact single changepoint by maximal reduction in within-segment SSE (PELT/binary-
    segmentation core). Returns (cp_index, mean_before, mean_after, gain) or None.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < MIN_GAMES:
        return None
    total_sse = np.sum((x - x.mean()) ** 2)
    best = None
    for cp in range(2, n - 1):
        left, right = x[:cp], x[cp:]
        sse = np.sum((left - left.mean()) ** 2) + np.sum((right - right.mean()) ** 2)
        gain = total_sse - sse
        if best is None or gain > best[3]:
            best = (cp, left.mean(), right.mean(), gain)
    return best


def bayesian_change_prob(values):
    """
    Simple Bayesian single-changepoint posterior. For each candidate split, score the
    two-segment Gaussian model marginal vs the no-change model; return the posterior
    probability mass on 'a change occurred in the second half' (recent upward shift).
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < MIN_GAMES:
        return 0.0, None
    sd = x.std() or 1.0

    def seg_loglik(seg):
        if len(seg) == 0:
            return 0.0
        mu = seg.mean()
        return -0.5 * np.sum((seg - mu) ** 2) / (sd ** 2)

    null_ll = seg_loglik(x)
    log_post = []
    cps = list(range(2, n - 1))
    for cp in cps:
        ll = seg_loglik(x[:cp]) + seg_loglik(x[cp:]) - 0.5 * np.log(n)  # BIC-ish penalty
        log_post.append(ll)
    # include the null hypothesis
    all_ll = np.array(log_post + [null_ll])
    all_ll -= all_ll.max()
    w = np.exp(all_ll)
    w /= w.sum()
    cp_w = w[:-1]
    if cp_w.sum() == 0:
        return 0.0, None
    map_idx = int(np.argmax(cp_w))
    cp = cps[map_idx]
    # posterior mass on a change located in the recent (second) half, upward
    recent_up = sum(cp_w[i] for i, c in enumerate(cps)
                    if c >= n // 2 and x[c:].mean() > x[:c].mean())
    return float(recent_up), cp

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_type(group, ctx, ptype_label, lines):
    A = lines.append
    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    cusum_flagged, pelt_flagged, bayes_flagged = set(), set(), set()
    n_series = 0
    pelt_gains = []
    for p in group:
        dates, vals = wf.get_primary_series(p, ctx)
        if len(vals) < MIN_GAMES:
            continue
        n_series += 1
        pid = p['player_id'].strip()

        fired, _ = cusum_upward(vals)
        if fired:
            cusum_flagged.add(pid)

        cp = best_changepoint(vals)
        if cp and cp[2] > cp[1]:  # mean after > mean before (upward)
            # require the shift to be in the latter half (recent regime)
            if cp[0] >= len(vals) / 2:
                pelt_flagged.add(pid)
                pelt_gains.append(cp[3])

        prob, _ = bayesian_change_prob(vals)
        if prob >= 0.5:
            bayes_flagged.add(pid)

    cusum_m = evaluate_flags(group, cusum_flagged)
    pelt_m  = evaluate_flags(group, pelt_flagged)
    bayes_m = evaluate_flags(group, bayes_flagged)

    print(f'\n--- {ptype_label} ---  (series>={MIN_GAMES} games: {n_series}, base={base:.2f})')
    print('  ' + format_metrics_line('CUSUM upward', cusum_m))
    print('  ' + format_metrics_line('PELT recent up-shift', pelt_m))
    print('  ' + format_metrics_line('Bayesian changepoint', bayes_m))

    A(f'### {ptype_label}')
    A('')
    A(f'- Players with a usable per-game series (>= {MIN_GAMES} games): **{n_series}** '
      f'| base top-rate: **{base:.2f}**')
    A('')
    A('| Detector | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|----------|-----------|--------|----|------|----|----|----|')
    for nm, m in [('CUSUM (sustained upward drift)', cusum_m),
                  ('PELT (recent upward regime shift)', pelt_m),
                  ('Bayesian changepoint (P>=0.5)', bayes_m)]:
        A(f"| {nm} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f}"
          f" | {m['lift']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    A('')
    return {'cusum': cusum_m, 'pelt': pelt_m, 'bayesian': bayes_m,
            'flagged_cusum': cusum_flagged}


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
    print('Section B — Statistical Change Detection')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section B — Statistical Change Detection', '',
             'Finds the game where a regime shifted (vs smoothing it over with a rolling '
             'window). CUSUM, an exact single-changepoint (PELT-style), and a Bayesian '
             'changepoint posterior run on each good-direction per-game series. A flag = '
             'recent, sustained, upward shift. All hand-rolled (no ruptures).', '']
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
