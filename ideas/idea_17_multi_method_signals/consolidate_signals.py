"""
Description:
    Idea 17 - Consolidation. Runs all nine method-class flaggers on the labeled
    pickup set, builds a per-player MULTI-METHOD CONFIDENCE SCORE (how many independent
    method classes flagged the player), and validates it against the Idea 15 composite_z
    ground truth. Also ranks the individual methods by predictive lift, cross-checks
    method ranking stability against 2025, fuses with the Idea 16 supervised threshold
    rule (the highest-confidence tier = Idea 16 rule AND >=3 Idea 17 methods), and emits
    a retrospective audit of which methods fired for the top pickups.

Source Data:
    - waiver_features 2026 + 2025 bundles; method_*.py flag primitives via
      multi_method_flags.

Outputs:
    - stdout summary.
    - reports/multi_method_signals_2026.md  (the consolidated deliverable)
"""

import os
import sys
import numpy as np

from waiver_common import (
    REPORTS_DIR, IDEA16_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt, safe_float,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, evaluate_scores, format_metrics_line
import multi_method_flags as mmf
from method_h_opportunity import load_closers_by_name

if IDEA16_DIR not in sys.path:
    sys.path.insert(0, IDEA16_DIR)
from analyze_waiver_signals_espn_2026 import find_optimal_threshold  # noqa: E402

REPORT_FILE = os.path.join(REPORTS_DIR, 'multi_method_signals_2026.md')

PRIMARY = {'batter': ('ops_14d', 'higher'), 'pitcher': ('k9_14d', 'higher')}


def idea16_flag(group, feats_unused):
    """Idea-16-style supervised single-feature F1-optimal threshold on the top feature."""
    ptype = group[0]['player_type'] if group else 'batter'
    feat, direction = PRIMARY[ptype]
    top = [p['_features'].get(feat) for p in group if p['_label'] == 'top'
           and p['_features'].get(feat) is not None]
    bottom = [p['_features'].get(feat) for p in group if p['_label'] == 'bottom'
              and p['_features'].get(feat) is not None]
    if len(top) < 3 or len(bottom) < 3:
        return set(), None
    thr, prec, rec, f1 = find_optimal_threshold(top, bottom, direction)
    flagged = set()
    for p in group:
        v = p['_features'].get(feat)
        if v is None:
            continue
        if (direction == 'higher' and v >= thr) or (direction == 'lower' and v <= thr):
            flagged.add(p['player_id'].strip())
    return flagged, (feat, direction, thr, f1)


def analyze_type(group, feats, ctx, closers, ptype_label, lines, season_tag):
    A = lines.append
    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    flags = mmf.compute_all_flags(group, ctx, feats, closers)
    scores = mmf.confidence_scores(group, flags)          # excludes weak G
    scores_all = mmf.confidence_scores(group, flags, include_weak=True)

    # per-method lift
    method_metrics = {m: evaluate_flags(group, flags[m]) for m in mmf.METHOD_NAMES}

    # confidence-score validation
    cs_r = evaluate_scores(group, scores, higher_is_better=True)['r']

    print(f'\n--- {ptype_label} [{season_tag}] ---  base={base:.2f}, conf-score r={fmt(cs_r,3)}')
    print('  per-method lift: ' + ', '.join(
        f"{m.split('_')[0]}={method_metrics[m]['lift']:.2f}" for m in mmf.METHOD_NAMES))

    A(f'### {ptype_label}')
    A('')
    A(f'- Eval pool: **{len(top)}** top + **{len(bottom)}** bottom | base top-rate: **{base:.2f}**')
    A(f'- Confidence-score rank-biserial r = `{fmt(cs_r,3)}` '
      '(higher score → more likely top quartile)')
    A('')
    A('**Individual method predictive power (in-sample):**')
    A('')
    A('| Method | Flagged | Precision | Recall | F1 | Lift |')
    A('|--------|---------|-----------|--------|----|------|')
    for m in mmf.METHOD_NAMES:
        mm = method_metrics[m]
        weak = ' _(weak)_' if m in mmf.WEAK_METHODS else ''
        A(f"| {m}{weak} | {mm['n_flagged']} | {mm['precision']:.2f} | {mm['recall']:.2f}"
          f" | {mm['f1']:.2f} | {mm['lift']:.2f} |")
    A('')

    # confidence tiers
    A('**Multi-method confidence score (excludes weak G):**')
    A('')
    A('| Score >= | n flagged (top+bottom) | Precision | Recall | Lift |')
    A('|----------|------------------------|-----------|--------|------|')
    for t in range(1, 8):
        flagged = {pid for pid, s in scores.items() if s >= t}
        m = evaluate_flags(group, flagged)
        if m['tp'] + m['fp'] == 0 and t > 1:
            break
        A(f"| {t} | {m['n_flagged']} | {m['precision']:.2f} | {m['recall']:.2f} | {m['lift']:.2f} |")
    A('')

    # fuse with idea 16
    i16, rule = idea16_flag(group, feats)
    if rule:
        feat, direction, thr, f1 = rule
        op = '>=' if direction == 'higher' else '<='
        hi_conf = {pid for pid, s in scores.items() if s >= 3 and pid in i16}
        hc_m = evaluate_flags(group, hi_conf)
        i16_m = evaluate_flags(group, i16)
        A('**Fusion with Idea 16 supervised rule:**')
        A('')
        A(f"- Idea 16 rule: `{feat}` {op} {fmt(thr,3)} "
          f"(P={i16_m['precision']:.2f}, R={i16_m['recall']:.2f}, lift={i16_m['lift']:.2f})")
        A(f"- **Highest-confidence tier** (Idea 16 rule AND >=3 Idea 17 methods): "
          f"{hc_m['n_flagged']} flagged, P={hc_m['precision']:.2f}, lift={hc_m['lift']:.2f}")
        A('')

    # retrospective audit
    A('**Retrospective audit — top pickups & methods that fired:**')
    A('')
    A('| Player | Acq Date | Z | Score | Methods Fired |')
    A('|--------|----------|---|-------|---------------|')
    top_sorted = sorted(top, key=lambda p: safe_float(p.get('composite_z'), 0.0), reverse=True)
    for p in top_sorted[:12]:
        pid = p['player_id'].strip()
        fired = [m.split('_')[0] for m in mmf.METHOD_NAMES if pid in flags[m]]
        z = fmt(safe_float(p.get('composite_z')), 2)
        A(f"| {p['player_name']} | {p['acquisition_date']} | {z} | {scores[pid]} | "
          f"{', '.join(fired) if fired else '—'} |")
    A('')

    return {'base': base, 'cs_r': cs_r, 'method_metrics': method_metrics,
            'scores': scores}


def run_season(pickups_path, ctx, closers, season_label, season_tag, lines):
    lines.append(f'## {season_label}')
    lines.append('')
    pickups = load_pickups(pickups_path)
    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']
    label_quartiles(batters)
    label_quartiles(pitchers)
    for p in pickups:
        p['_features'] = wf.build_window_features(p, ctx)
    b = analyze_type(batters, wf.BATTER_FEATURES, ctx, closers, 'Batters', lines, season_tag)
    p = analyze_type(pitchers, wf.PITCHER_FEATURES, ctx, closers, 'Pitchers', lines, season_tag)
    return {'batters': b, 'pitchers': p}


def build_method_ranking_section(res26, res25, lines):
    A = lines.append
    A('## Cross-Season Method Ranking (Stability = Robustness)')
    A('')
    A('Mean lift across player types per season. Methods with high lift in **both** '
      'seasons are the robust core to build the watchlist around.')
    A('')
    A('| Method | 2026 mean lift | 2025 mean lift | Robust? |')
    A('|--------|----------------|----------------|---------|')

    def mean_lift(res, m):
        vals = []
        for t in ('batters', 'pitchers'):
            if res.get(t):
                vals.append(res[t]['method_metrics'][m]['lift'])
        return np.mean(vals) if vals else float('nan')

    ranked = sorted(mmf.METHOD_NAMES, key=lambda m: -mean_lift(res26, m))
    for m in ranked:
        l26 = mean_lift(res26, m)
        l25 = mean_lift(res25, m) if res25 else float('nan')
        robust = '✓' if (l26 >= 1.15 and (np.isnan(l25) or l25 >= 1.15)) else ''
        A(f"| {m} | {l26:.2f} | {fmt(l25,2) if not np.isnan(l25) else 'n/a'} | {robust} |")
    A('')


def main():
    print('Consolidation — Multi-Method Confidence Score')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    closers = load_closers_by_name()

    lines = ['# Idea 17 — Multi-Method Waiver Signal Consolidation', '',
             '**Analysis date:** 2026-06-19  ',
             'Runs all nine method classes (A–I) on the Idea 15 labeled pickup set, '
             'scores each player by how many independent methods flag them (the '
             '**multi-method confidence score**), and validates that score against '
             'composite_z. Method G (market) is reported but excluded from the default '
             'score (validated lift < 1 — ownership hype attaches to busts too).', '',
             '> All methods are unsupervised or relative; the table values are in-sample '
             'on the labeled set, with 2025 used to confirm the method ranking is stable.',
             '', '---', '']

    res26 = run_season(BEST_PICKUPS_FILE, ctx26, closers, '2026 (primary)', '2026', lines)

    res25 = None
    if os.path.exists(BEST_PICKUPS_2025_FILE):
        print('\nLoading 2025 cross-check...')
        ctx25 = wf.load_all_2025()
        lines.append('---'); lines.append('')
        res25 = run_season(BEST_PICKUPS_2025_FILE, ctx25, {}, '2025 (cross-season)', '2025', lines)

    lines.append('---'); lines.append('')
    build_method_ranking_section(res26, res25, lines)

    lines.append('## How to Use This')
    lines.append('')
    lines.append('1. Run `watch_multi_method_signals.py` weekly to score the current '
                 'free-agent pool.')
    lines.append('2. Prioritize players with **confidence score >= 3** — and especially '
                 'those that also pass the Idea 16 supervised threshold (highest tier).')
    lines.append('3. Treat the robust-core methods (✓ above) as the trustworthy signals; '
                 'down-weight the rest.')
    lines.append('')

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'\nConsolidated report written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
