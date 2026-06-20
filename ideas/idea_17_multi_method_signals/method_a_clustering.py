"""
Description:
    Idea 17 - Section A: Unsupervised Clustering / Archetype Discovery. Runs PCA,
    K-means (k chosen by silhouette), hand-rolled DBSCAN, and SciPy hierarchical
    clustering on the standardized pre-pickup feature matrix WITHOUT looking at
    post-pickup outcomes. Then overlays the Idea 15 composite_z labels to see which
    discovered archetypes are predictive of top-quartile pickups. No scikit-learn:
    PCA via numpy SVD, K-means via Lloyd's algorithm, DBSCAN hand-rolled,
    hierarchical via scipy.cluster.hierarchy.

Source Data:
    - Pre-pickup feature matrix from waiver_features (2026 best_pickups + boxscore +
      rankings + lineups). 2025 used as a cross-season sanity check.

Outputs:
    - stdout validation summary.
    - fantasy_baseball/ideas/idea_17_multi_method_signals/reports/method_a_clustering.md
"""

import os
import numpy as np
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, format_metrics_line

np.random.seed(17)
REPORT_FILE = os.path.join(REPORTS_DIR, 'method_a_clustering.md')

# ---------------------------------------------------------------------------
# Hand-rolled primitives (no sklearn)
# ---------------------------------------------------------------------------

def pca(X, n_components=3):
    """Return (scores, components, explained_variance_ratio) via SVD on centered X."""
    Xc = X - X.mean(axis=0)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    comps = Vt[:n_components]
    scores = Xc @ comps.T
    var = (S ** 2) / (X.shape[0] - 1)
    evr = var / var.sum()
    return scores, comps, evr[:n_components]


def kmeans(X, k, n_init=10, max_iter=200):
    """Lloyd's algorithm with k-means++ init; returns (labels, centroids, inertia)."""
    best = None
    n = X.shape[0]
    for _ in range(n_init):
        # k-means++ seeding
        centers = [X[np.random.randint(n)]]
        for _c in range(1, k):
            d2 = np.min([np.sum((X - c) ** 2, axis=1) for c in centers], axis=0)
            probs = d2 / d2.sum() if d2.sum() > 0 else np.ones(n) / n
            centers.append(X[np.random.choice(n, p=probs)])
        centers = np.array(centers)
        labels = np.zeros(n, dtype=int)
        for _it in range(max_iter):
            dists = np.array([np.sum((X - c) ** 2, axis=1) for c in centers]).T
            new_labels = dists.argmin(axis=1)
            if np.array_equal(new_labels, labels) and _it > 0:
                break
            labels = new_labels
            for j in range(k):
                pts = X[labels == j]
                if len(pts) > 0:
                    centers[j] = pts.mean(axis=0)
        inertia = sum(np.sum((X[labels == j] - centers[j]) ** 2) for j in range(k))
        if best is None or inertia < best[2]:
            best = (labels, centers, inertia)
    return best


def silhouette_score(X, labels):
    """Mean silhouette over all points. O(n^2); fine for a few hundred rows."""
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    D = squareform(pdist(X))
    sils = []
    for i in range(len(X)):
        same = labels == labels[i]
        same[i] = False
        if same.sum() == 0:
            sils.append(0.0)
            continue
        a = D[i, same].mean()
        b = np.inf
        for c in uniq:
            if c == labels[i]:
                continue
            b = min(b, D[i, labels == c].mean())
        sils.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return float(np.mean(sils))


def dbscan(X, eps, min_pts):
    """Hand-rolled DBSCAN. Returns labels (-1 = noise/outlier)."""
    n = X.shape[0]
    D = squareform(pdist(X))
    labels = np.full(n, -2, dtype=int)  # -2 = unvisited
    cid = -1
    for i in range(n):
        if labels[i] != -2:
            continue
        neigh = np.where(D[i] <= eps)[0]
        if len(neigh) < min_pts:
            labels[i] = -1  # noise (may later become border)
            continue
        cid += 1
        labels[i] = cid
        seeds = list(neigh)
        idx = 0
        while idx < len(seeds):
            q = seeds[idx]
            idx += 1
            if labels[q] == -1:
                labels[q] = cid  # border point
            if labels[q] != -2:
                continue
            labels[q] = cid
            q_neigh = np.where(D[q] <= eps)[0]
            if len(q_neigh) >= min_pts:
                seeds.extend(q_neigh.tolist())
    return labels

# ---------------------------------------------------------------------------
# Archetype overlay + validation
# ---------------------------------------------------------------------------

def cluster_top_rate(pickups, idx, labels):
    """For each cluster, fraction of its top+bottom members that are 'top'."""
    rates = {}
    for c in np.unique(labels):
        members = [pickups[idx[i]] for i in range(len(idx)) if labels[i] == c]
        tb = [p for p in members if p['_label'] in ('top', 'bottom')]
        ntop = sum(1 for p in tb if p['_label'] == 'top')
        rates[c] = {
            'n': len(members),
            'n_eval': len(tb),
            'top_rate': (ntop / len(tb)) if tb else None,
            'n_top': ntop,
        }
    return rates


def flag_predictive_clusters(pickups, idx, labels, base_rate):
    """Flag player_ids in clusters whose top-rate exceeds the base rate."""
    rates = cluster_top_rate(pickups, idx, labels)
    flagged = set()
    good_clusters = []
    for c, info in rates.items():
        if c == -1:  # DBSCAN noise handled separately
            continue
        if info['top_rate'] is not None and info['n_eval'] >= 3 and info['top_rate'] > base_rate:
            good_clusters.append(c)
            for i in range(len(idx)):
                if labels[i] == c:
                    flagged.add(pickups[idx[i]]['player_id'].strip())
    return flagged, rates, good_clusters


def raw_centroid(pickups, idx, labels, cluster, feat_list):
    """Mean of each feature (original units) for a cluster, ignoring missing."""
    members = [pickups[idx[i]] for i in range(len(idx)) if labels[i] == cluster]
    out = {}
    for f in feat_list:
        vals = [p['_features'].get(f) for p in members if p['_features'].get(f) is not None]
        out[f] = (sum(vals) / len(vals)) if vals else None
    return out

# ---------------------------------------------------------------------------
# Per-type analysis
# ---------------------------------------------------------------------------

def analyze_type(group, feat_list, ptype_label, lines):
    A = lines.append
    valid = [i for i, p in enumerate(group)
             if any(p['_features'].get(f) is not None for f in feat_list)]
    X_full, kept, mask = wf.build_matrix(group, feat_list)
    idx = [i for i in range(len(group)) if mask[i]]
    X = X_full[mask]
    if len(idx) < 10:
        A(f'### {ptype_label}\n\n_Insufficient data ({len(idx)} valid rows)._\n')
        return None

    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    # --- PCA ---
    scores, comps, evr = pca(X, n_components=min(3, X.shape[1]))

    # --- K-means: pick k by silhouette ---
    candidates = range(3, 8)
    km_results = {}
    for k in candidates:
        if k >= len(idx):
            continue
        labels, centers, inertia = kmeans(X, k)
        sil = silhouette_score(X, labels)
        km_results[k] = (sil, inertia, labels)
    best_k = max(km_results, key=lambda k: km_results[k][0])
    km_labels = km_results[best_k][2]
    km_flagged, km_rates, km_good = flag_predictive_clusters(group, idx, km_labels, base)
    km_metrics = evaluate_flags(group, km_flagged)

    # --- DBSCAN: scan eps; pick the eps giving the best silhouette w/ >=2 clusters ---
    db_best = None
    min_pts = max(3, int(np.log(len(idx))) + 1)
    for eps in np.linspace(1.0, 4.0, 13):
        dlabels = dbscan(X, eps, min_pts)
        nclust = len(set(dlabels) - {-1})
        if nclust < 2:
            continue
        core = dlabels != -1
        if core.sum() < 3:
            continue
        sil = silhouette_score(X[core], dlabels[core]) if len(set(dlabels[core])) > 1 else -1
        if db_best is None or sil > db_best[0]:
            db_best = (sil, eps, dlabels, nclust)
    db_metrics = None
    n_outliers = 0
    if db_best is not None:
        dlabels = db_best[2]
        n_outliers = int((dlabels == -1).sum())
        db_flagged, db_rates, db_good = flag_predictive_clusters(group, idx, dlabels, base)
        db_metrics = evaluate_flags(group, db_flagged)

    # --- Hierarchical (Ward) at the same cluster count as best_k ---
    Z = linkage(X, method='ward')
    h_labels = fcluster(Z, t=best_k, criterion='maxclust') - 1
    h_flagged, h_rates, h_good = flag_predictive_clusters(group, idx, h_labels, base)
    h_metrics = evaluate_flags(group, h_flagged)

    # ---- stdout ----
    print(f'\n--- {ptype_label} ---  (valid rows={len(idx)}, base top-rate={base:.2f})')
    print(f'  PCA explained var (top {len(evr)}): '
          + ', '.join(f'{e:.2f}' for e in evr) + f'  (cum {evr.sum():.2f})')
    print(f'  K-means best k={best_k} (silhouette {km_results[best_k][0]:.3f})')
    print('  ' + format_metrics_line('K-means archetypes', km_metrics))
    if db_metrics:
        print(f'  DBSCAN eps={db_best[1]:.2f} clusters={db_best[3]} outliers={n_outliers}')
        print('  ' + format_metrics_line('DBSCAN archetypes', db_metrics))
    print('  ' + format_metrics_line('Hierarchical (Ward)', h_metrics))

    # ---- report ----
    A(f'### {ptype_label}')
    A('')
    A(f'- Valid rows clustered: **{len(idx)}** | base top-rate (top / top+bottom): **{base:.2f}**')
    A(f'- PCA explained variance (first {len(evr)} PCs): '
      + ', '.join(f'`{e:.2f}`' for e in evr) + f' (cumulative `{evr.sum():.2f}`)')
    A('')
    A('**PCA loadings (which features define each axis):**')
    A('')
    A('| PC | ' + ' | '.join(f'`{f}`' for f in kept) + ' |')
    A('|----|' + '|'.join('---' for _ in kept) + '|')
    for pc in range(len(comps)):
        A(f'| PC{pc+1} | ' + ' | '.join(f'{comps[pc][j]:+.2f}' for j in range(len(kept))) + ' |')
    A('')
    A('**Method validation (flag = member of a cluster with above-base top-rate):**')
    A('')
    A('| Method | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|--------|-----------|--------|----|------|----|----|----|')
    A(f"| K-means (k={best_k}) | {km_metrics['precision']:.2f} | {km_metrics['recall']:.2f}"
      f" | {km_metrics['f1']:.2f} | {km_metrics['lift']:.2f}"
      f" | {km_metrics['tp']} | {km_metrics['fp']} | {km_metrics['fn']} |")
    if db_metrics:
        A(f"| DBSCAN (eps={db_best[1]:.2f}) | {db_metrics['precision']:.2f} | {db_metrics['recall']:.2f}"
          f" | {db_metrics['f1']:.2f} | {db_metrics['lift']:.2f}"
          f" | {db_metrics['tp']} | {db_metrics['fp']} | {db_metrics['fn']} |")
    A(f"| Hierarchical (Ward, {best_k}) | {h_metrics['precision']:.2f} | {h_metrics['recall']:.2f}"
      f" | {h_metrics['f1']:.2f} | {h_metrics['lift']:.2f}"
      f" | {h_metrics['tp']} | {h_metrics['fp']} | {h_metrics['fn']} |")
    A('')

    # archetype profiles from K-means
    A(f'**K-means archetype profiles (k={best_k}, original-unit centroids):**')
    A('')
    profile_feats = [f for f in kept]
    header = '| Cluster | n | top-rate | ' + ' | '.join(f'`{f}`' for f in profile_feats[:8]) + ' |'
    A(header)
    A('|' + '|'.join('---' for _ in range(3 + min(8, len(profile_feats)))) + '|')
    for c in sorted(np.unique(km_labels)):
        info = km_rates[c]
        cen = raw_centroid(group, idx, km_labels, c, profile_feats)
        tr = fmt(info['top_rate'], 2) if info['top_rate'] is not None else 'n/a'
        star = ' ⭐' if c in km_good else ''
        row = f"| {c}{star} | {info['n']} | {tr} | " + \
              ' | '.join(fmt(cen[f], 2) if cen[f] is not None else '—' for f in profile_feats[:8]) + ' |'
        A(row)
    A('')
    A('⭐ = predictive archetype (top-rate above base). DBSCAN isolated '
      f'**{n_outliers}** outlier players (novel opportunity types worth manual inspection).')
    A('')

    return {
        'kmeans': km_metrics, 'dbscan': db_metrics, 'hierarchical': h_metrics,
        'best_k': best_k, 'flagged_kmeans': km_flagged,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_season(pickups_path, ctx, season_label, lines):
    A = lines.append
    A(f'## {season_label}')
    A('')
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
    print('Section A — Unsupervised Clustering / Archetype Discovery')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()

    lines = ['# Section A — Unsupervised Clustering (Archetype Discovery)', '',
             'Clusters the standardized pre-pickup feature space **without** outcome '
             'labels, then overlays Idea 15 composite_z to find which archetypes predict '
             'top-quartile pickups. PCA/K-means/DBSCAN hand-rolled (no sklearn); '
             'hierarchical via SciPy.', '']
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
