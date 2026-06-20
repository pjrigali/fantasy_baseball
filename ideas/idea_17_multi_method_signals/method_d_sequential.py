"""
Description:
    Idea 17 - Section D: Sequential Testing for earliest-possible signal detection.
    SPRT and one-sided CUSUM are designed to reach a decision (real shift vs noise)
    with as few games as possible - critical because the waiver add window is short.
      1. SPRT (Sequential Probability Ratio Test) - tests H0 (player at population
         mean) vs H1 (player elevated by a meaningful delta). Walks the per-game
         series and fires the moment the log-likelihood ratio crosses the upper
         boundary set by (alpha, beta) error rates.
      2. One-sided CUSUM alarm - fires the first game the cumulative deviation crosses
         a control threshold.
    The headline output is LEAD TIME: for each top-quartile pickup, how many days
    before the acquisition date the signal would have fired - i.e. how long the edge
    sat on the wire before the league reacted.

Source Data:
    - Per-game series from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout validation + lead-time summary.
    - reports/method_d_sequential.md
"""

import os
import math
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt, parse_date,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_d_sequential.md')
MIN_GAMES = 4

# ---------------------------------------------------------------------------
# Sequential detectors -> first-firing index (or None)
# ---------------------------------------------------------------------------

def sprt_first_fire(values, mu0, sigma, delta, alpha=0.05, beta=0.20):
    """
    Gaussian SPRT: H0 mean=mu0 vs H1 mean=mu0+delta, known sigma. Returns the index of
    the first game at which the cumulative log-LR crosses the upper boundary B=log((1-
    beta)/alpha). Lower boundary (accept H0) just stops the test without a signal.
    """
    if sigma <= 0 or delta <= 0 or len(values) < MIN_GAMES:
        return None
    A_lo = math.log(beta / (1 - alpha))     # lower (accept H0)
    B_hi = math.log((1 - beta) / alpha)     # upper (accept H1 -> signal)
    llr = 0.0
    for i, x in enumerate(values):
        # per-sample log-LR for Gaussian shift in mean
        llr += (delta / sigma ** 2) * (x - mu0 - delta / 2.0)
        if llr >= B_hi:
            return i
        if llr <= A_lo:
            llr = 0.0  # reset rather than terminate -- allow later regime to re-trigger
    return None


def cusum_first_fire(values, mu0, sigma, k_sigma=0.5, h_sigma=4.0):
    if len(values) < MIN_GAMES or sigma <= 0:
        return None
    k = k_sigma * sigma
    h = h_sigma * sigma
    s = 0.0
    for i, x in enumerate(values):
        s = max(0.0, s + (x - mu0) - k)
        if s > h:
            return i
    return None

# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze_type(group, ctx, ptype_label, lines):
    A = lines.append
    ptype = group[0]['player_type'] if group else 'batter'
    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    # population baseline (mu0, sigma) from all per-game values in the group
    all_vals = []
    series_cache = {}
    for p in group:
        dates, vals = wf.get_primary_series(p, ctx)
        series_cache[p['player_id'].strip()] = (dates, vals, parse_date(p['acquisition_date']))
        all_vals.extend(vals)
    if len(all_vals) < 10:
        A(f'### {ptype_label}\n\n_Insufficient series data._\n')
        return None
    mu0 = float(np.mean(all_vals))
    sigma = float(np.std(all_vals)) or 1.0
    delta = sigma  # alternative = one std above baseline

    sprt_flagged, cusum_flagged = set(), set()
    sprt_leads, cusum_leads = [], []
    n_series = 0
    for p in group:
        pid = p['player_id'].strip()
        dates, vals, acq = series_cache[pid]
        if len(vals) < MIN_GAMES:
            continue
        n_series += 1

        si = sprt_first_fire(vals, mu0, sigma, delta)
        if si is not None:
            sprt_flagged.add(pid)
            if acq and p['_label'] == 'top':
                lead = (acq - dates[si]).days
                if lead >= 0:
                    sprt_leads.append(lead)

        ci = cusum_first_fire(vals, mu0, sigma)
        if ci is not None:
            cusum_flagged.add(pid)
            if acq and p['_label'] == 'top':
                lead = (acq - dates[ci]).days
                if lead >= 0:
                    cusum_leads.append(lead)

    sprt_m = evaluate_flags(group, sprt_flagged)
    cusum_m = evaluate_flags(group, cusum_flagged)
    sprt_med = float(np.median(sprt_leads)) if sprt_leads else None
    cusum_med = float(np.median(cusum_leads)) if cusum_leads else None

    print(f'\n--- {ptype_label} ---  (series>={MIN_GAMES}: {n_series}, base={base:.2f},'
          f' mu0={mu0:.3f}, sigma={sigma:.3f})')
    print('  ' + format_metrics_line('SPRT', sprt_m)
          + f'  median lead={fmt(sprt_med,1)}d')
    print('  ' + format_metrics_line('CUSUM alarm', cusum_m)
          + f'  median lead={fmt(cusum_med,1)}d')

    A(f'### {ptype_label}')
    A('')
    A(f'- Usable series (>= {MIN_GAMES} games): **{n_series}** | base top-rate: **{base:.2f}**')
    A(f'- Population baseline: mu0 = `{mu0:.3f}`, sigma = `{sigma:.3f}`, '
      f'alternative delta = `{delta:.3f}` (1 sigma above baseline)')
    A('')
    A('| Test | Precision | Recall | F1 | Lift | Median lead (top picks) |')
    A('|------|-----------|--------|----|------|--------------------------|')
    A(f"| SPRT | {sprt_m['precision']:.2f} | {sprt_m['recall']:.2f} | {sprt_m['f1']:.2f}"
      f" | {sprt_m['lift']:.2f} | {fmt(sprt_med,1)} days |")
    A(f"| CUSUM alarm | {cusum_m['precision']:.2f} | {cusum_m['recall']:.2f} | {cusum_m['f1']:.2f}"
      f" | {cusum_m['lift']:.2f} | {fmt(cusum_med,1)} days |")
    A('')
    A(f'> **Lead time** = median days between the signal first firing and the actual '
      f'acquisition date for top-quartile pickups: the edge was visible **~'
      f'{fmt(sprt_med,0)} days (SPRT) / {fmt(cusum_med,0)} days (CUSUM)** before the '
      f'league reacted.')
    A('')
    return {'sprt': sprt_m, 'cusum': cusum_m,
            'sprt_lead': sprt_med, 'cusum_lead': cusum_med,
            'flagged_sprt': sprt_flagged}


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
    print('Section D — Sequential Testing')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section D — Sequential Testing (Earliest Signal + Lead Time)', '',
             'SPRT and one-sided CUSUM reach a real-shift-vs-noise decision in as few '
             'games as possible, then report how many days before the acquisition date '
             'the signal would have fired for top-quartile pickups.', '']
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
