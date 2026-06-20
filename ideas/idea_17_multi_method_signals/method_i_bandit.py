"""
Description:
    Idea 17 - Section I: Multi-Armed Bandit. Frames the weekly waiver claim as an
    explore/exploit decision under uncertainty, using the Section A archetype cluster
    as the bandit "context".
      1. Thompson sampling - maintain a Beta(top, bottom) posterior over each archetype's
         add-quality (P[top-quartile]); sample to rank clusters, claim from the highest.
         Naturally balances exploration and exploitation.
      2. Epsilon-greedy - exploit the best-expected-value cluster with prob 1-eps,
         explore otherwise.
      3. Contextual reward - each player's expected reward = posterior mean of its
         cluster; validated by rank-biserial and top-N selection precision.
    Hand-rolled k-means (no sklearn) for the context assignment, scipy Beta for the
    posteriors.

Source Data:
    - Pre-pickup feature matrix from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout summary.
    - reports/method_i_bandit.md
"""

import os
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, evaluate_scores, format_metrics_line
from method_a_clustering import kmeans, silhouette_score

np.random.seed(17)
REPORT_FILE = os.path.join(REPORTS_DIR, 'method_i_bandit.md')


def cluster_posteriors(group, idx, labels, prior_a=1.0, prior_b=1.0):
    """Beta(top+a, bottom+b) per cluster from observed quartile labels."""
    post = {}
    for c in np.unique(labels):
        members = [group[idx[i]] for i in range(len(idx)) if labels[i] == c]
        ntop = sum(1 for p in members if p['_label'] == 'top')
        nbot = sum(1 for p in members if p['_label'] == 'bottom')
        post[c] = (prior_a + ntop, prior_b + nbot, len(members))
    return post


def analyze_type(group, feat_list, ptype_label, lines):
    A = lines.append
    X_full, kept, mask = wf.build_matrix(group, feat_list)
    idx = [i for i in range(len(group)) if mask[i]]
    X = X_full[mask]
    if len(idx) < 12:
        A(f'### {ptype_label}\n\n_Insufficient data ({len(idx)} rows)._\n')
        return None

    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    # pick k by silhouette (context arms)
    best = None
    for k in range(3, 7):
        if k >= len(idx):
            continue
        labels, _, _ = kmeans(X, k)
        sil = silhouette_score(X, labels)
        if best is None or sil > best[0]:
            best = (sil, k, labels)
    labels = best[2]
    k = best[1]

    post = cluster_posteriors(group, idx, labels)

    # expected reward per player = posterior mean of its cluster
    exp_reward = {}
    for i in range(len(idx)):
        a, b, _ = post[labels[i]]
        exp_reward[group[idx[i]]['player_id'].strip()] = a / (a + b)
    er_r = evaluate_scores(group, exp_reward, higher_is_better=True)['r']

    # Thompson sampling: average selection rate over many rounds, then flag the
    # players in clusters chosen above their fair share -> "claim" set.
    rounds = 2000
    pick_counts = {c: 0 for c in post}
    for _ in range(rounds):
        samples = {c: np.random.beta(a, b) for c, (a, b, _) in post.items()}
        pick_counts[max(samples, key=samples.get)] += 1
    ts_best_cluster = max(pick_counts, key=pick_counts.get)

    # epsilon-greedy exploit set = clusters whose posterior mean > base (the "add" arms)
    exploit_clusters = [c for c, (a, b, _) in post.items() if a / (a + b) > base]
    eg_flagged = {group[idx[i]]['player_id'].strip()
                  for i in range(len(idx)) if labels[i] in exploit_clusters}
    eg_m = evaluate_flags(group, eg_flagged)

    # Thompson "claim" = players in the most-sampled cluster
    ts_flagged = {group[idx[i]]['player_id'].strip()
                  for i in range(len(idx)) if labels[i] == ts_best_cluster}
    ts_m = evaluate_flags(group, ts_flagged)

    print(f'\n--- {ptype_label} ---  (rows={len(idx)}, k={k}, base={base:.2f})')
    print(f'  contextual expected-reward rank-biserial r={fmt(er_r,3)}')
    print(f'  Thompson top cluster={ts_best_cluster} '
          f'(picked {pick_counts[ts_best_cluster]}/{rounds})')
    print('  ' + format_metrics_line('Epsilon-greedy exploit arms', eg_m))
    print('  ' + format_metrics_line('Thompson single-claim', ts_m))

    A(f'### {ptype_label}')
    A('')
    A(f'- Context arms (archetypes): **{k}** | rows: **{len(idx)}** | base top-rate: **{base:.2f}**')
    A(f'- Contextual expected-reward rank-biserial r = `{fmt(er_r,3)}` '
      '(does the cluster add-quality estimate rank top pickups above bottom?)')
    A('')
    A('**Arm (archetype) posteriors:**')
    A('')
    A('| Arm | n | top | bottom | posterior mean | Thompson pick-share |')
    A('|-----|---|-----|--------|----------------|---------------------|')
    for c in sorted(post):
        a, b, n = post[c]
        A(f"| {c} | {n} | {int(a-1)} | {int(b-1)} | {a/(a+b):.2f} | "
          f"{pick_counts[c]/rounds:.2f} |")
    A('')
    A('| Policy | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|--------|-----------|--------|----|------|----|----|----|')
    for nm, m in [('Epsilon-greedy (exploit arms)', eg_m),
                  ('Thompson (single best arm)', ts_m)]:
        A(f"| {nm} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f}"
          f" | {m['lift']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    A('')
    return {'epsilon_greedy': eg_m, 'thompson': ts_m, 'er_r': er_r,
            'flagged_eg': eg_flagged}


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
    print('Section I — Multi-Armed Bandit')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section I — Multi-Armed Bandit (Explore/Exploit)', '',
             'Frames the weekly claim as a bandit over Section A archetypes. Thompson '
             'sampling and epsilon-greedy maintain Beta posteriors on each archetype\'s '
             'add-quality and choose which arm (player type profile) to claim from.', '']
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
