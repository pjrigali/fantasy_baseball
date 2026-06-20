"""
Description:
    Idea 17 - shared multi-method flag engine. Centralizes the single canonical "add"
    flag from each of the nine method sections (A-I) so the consolidation report and
    the weekly runtime watchlist apply identical logic. Each method contributes a
    set of flagged player_ids for a given player pool. Label-free methods (B/C/D/E/F/
    G/H) score the pool directly against population baselines; the two methods that
    require learned structure (A clustering, I bandit) are fit on a labeled training
    pool and then applied to the target pool, so the same code path serves both the
    in-sample consolidation and the out-of-sample runtime watchlist.

    Reuses the primitives already written in the per-section method_*.py scripts.

Source Data:
    - Operates on in-memory pickup/player dicts carrying '_features' (and per-game
      series fetched on demand) built by waiver_features.

Outputs:
    - None. Library returning {method_name: set(player_id)} dicts.
"""

import numpy as np

import waiver_features as wf
from waiver_common import safe_float

import method_a_clustering as A
import method_b_changepoint as B
import method_c_bayesian as C
import method_d_sequential as D
import method_e_anomaly as E
import method_f_forecast as F
import method_h_opportunity as H
import method_i_bandit as I

METHOD_NAMES = [
    'A_clustering', 'B_changepoint', 'C_bayesian', 'D_sequential',
    'E_anomaly', 'F_forecast', 'G_market', 'H_opportunity', 'I_bandit',
]
# Methods validated as weak standalone predictors (lift < 1) -> excluded from the
# default confidence score but still reported.
WEAK_METHODS = {'G_market'}

PRIMARY_STAT = {'batter': 'ops_14d', 'pitcher': 'k9_14d'}


# ---------------------------------------------------------------------------
# Scaler (fit on train, apply to pool) -- so clustering/bandit work out-of-sample
# ---------------------------------------------------------------------------

def fit_scaler(train_pool, feats):
    n = len(train_pool)
    raw = np.full((n, len(feats)), np.nan)
    for i, p in enumerate(train_pool):
        for j, f in enumerate(feats):
            v = p['_features'].get(f)
            if v is not None:
                raw[i, j] = float(v)
    keep = [j for j in range(len(feats)) if not np.all(np.isnan(raw[:, j]))]
    kept = [feats[j] for j in keep]
    raw = raw[:, keep]
    med = np.nanmedian(raw, axis=0)
    med = np.where(np.isnan(med), 0.0, med)
    filled = np.where(np.isnan(raw), med, raw)
    mu = filled.mean(axis=0)
    sd = filled.std(axis=0)
    sd[sd == 0] = 1.0
    return {'feats': kept, 'med': med, 'mu': mu, 'sd': sd}


def apply_scaler(pool, scaler):
    feats, med, mu, sd = scaler['feats'], scaler['med'], scaler['mu'], scaler['sd']
    n = len(pool)
    raw = np.full((n, len(feats)), np.nan)
    valid = np.zeros(n, dtype=bool)
    for i, p in enumerate(pool):
        any_v = False
        for j, f in enumerate(feats):
            v = p['_features'].get(f)
            if v is not None:
                raw[i, j] = float(v)
                any_v = True
        valid[i] = any_v
    filled = np.where(np.isnan(raw), med, raw)
    X = (filled - mu) / sd
    return X, valid


# ---------------------------------------------------------------------------
# Per-method flaggers
# ---------------------------------------------------------------------------

def _ensure_series(pool, ctx):
    for p in pool:
        if '_series' not in p:
            _, p['_series'] = wf.get_primary_series(p, ctx)


def flag_clustering(pool, ctx, train_pool, train_ctx, feats):
    """Fit k-means on train, assign pool to nearest centroid, flag predictive archetypes."""
    scaler = fit_scaler(train_pool, feats)
    Xtr, vtr = apply_scaler(train_pool, scaler)
    idx_tr = [i for i in range(len(train_pool)) if vtr[i]]
    if len(idx_tr) < 12:
        return set()
    Xtr_v = Xtr[vtr]
    # pick k by silhouette
    best = None
    for k in range(3, 7):
        if k >= len(idx_tr):
            continue
        labels, centers, _ = A.kmeans(Xtr_v, k)
        sil = A.silhouette_score(Xtr_v, labels)
        if best is None or sil > best[0]:
            best = (sil, k, labels, centers)
    _, k, tr_labels, centers = best
    # train base rate + per-cluster top-rate
    rates = A.cluster_top_rate(train_pool, idx_tr, tr_labels)
    top = sum(1 for p in train_pool if p.get('_label') == 'top')
    bot = sum(1 for p in train_pool if p.get('_label') == 'bottom')
    base = top / (top + bot) if (top + bot) else 0.5
    good_clusters = {c for c, info in rates.items()
                     if c != -1 and info['top_rate'] is not None
                     and info['n_eval'] >= 3 and info['top_rate'] > base}
    # assign pool to nearest centroid
    Xp, vp = apply_scaler(pool, scaler)
    flagged = set()
    for i, p in enumerate(pool):
        if not vp[i]:
            continue
        c = int(np.argmin([np.sum((Xp[i] - cen) ** 2) for cen in centers]))
        if c in good_clusters:
            flagged.add(p['player_id'].strip())
    return flagged


def flag_changepoint(pool, ctx):
    _ensure_series(pool, ctx)
    flagged = set()
    for p in pool:
        vals = p['_series']
        if len(vals) < B.MIN_GAMES:
            continue
        cp = B.best_changepoint(vals)
        if cp and cp[2] > cp[1] and cp[0] >= len(vals) / 2:
            flagged.add(p['player_id'].strip())
    return flagged


def flag_bayesian(pool, ctx, train_pool):
    _ensure_series(pool, ctx)
    _ensure_series(train_pool, ctx)
    ptype = pool[0]['player_type'] if pool else 'batter'
    recs = []
    for p in train_pool:
        v = p.get('_series', [])
        if len(v) >= C.MIN_GAMES:
            s, n = C.player_rate(v, ptype)
            recs.append((s, n))
    if not recs:
        return set()
    rates = [s / n for s, n in recs]
    weights = [n for s, n in recs]
    a0, b0 = C.fit_beta_prior(rates, weights)
    post_vals = []
    pool_post = {}
    for p in pool:
        v = p['_series']
        if len(v) < C.MIN_GAMES:
            continue
        s, n = C.player_rate(v, ptype)
        pm = (a0 + s) / (a0 + b0 + n)
        pool_post[p['player_id'].strip()] = pm
        post_vals.append(pm)
    if not post_vals:
        return set()
    med = float(np.median(post_vals))
    return {pid for pid, pm in pool_post.items() if pm > med}


def flag_sequential(pool, ctx, train_pool):
    _ensure_series(pool, ctx)
    _ensure_series(train_pool, ctx)
    all_vals = [x for p in train_pool for x in p.get('_series', [])]
    if len(all_vals) < 10:
        return set()
    mu0 = float(np.mean(all_vals))
    sigma = float(np.std(all_vals)) or 1.0
    flagged = set()
    for p in pool:
        v = p['_series']
        if len(v) < D.MIN_GAMES:
            continue
        if D.sprt_first_fire(v, mu0, sigma, sigma) is not None:
            flagged.add(p['player_id'].strip())
    return flagged


def flag_anomaly(pool, ctx, feats):
    scaler = fit_scaler(pool, feats)
    X, valid = apply_scaler(pool, scaler)
    idx = [i for i in range(len(pool)) if valid[i]]
    if len(idx) < 10:
        return set()
    Xv = X[valid]
    iso = E.isolation_forest_scores(Xv)
    good = E.good_direction_mask(pool, idx, feats)
    thr = np.quantile(iso, 0.67)
    flagged = set()
    for j, i in enumerate(idx):
        if iso[j] >= thr and good[j]:
            flagged.add(pool[i]['player_id'].strip())
    return flagged


def flag_forecast(pool, ctx, train_pool):
    _ensure_series(pool, ctx)
    _ensure_series(train_pool, ctx)
    fc = {}
    for p in pool:
        v = p['_series']
        if len(v) < F.MIN_GAMES:
            continue
        fc[p['player_id'].strip()] = F.ets_forecast(v)
    if not fc:
        return set()
    med = float(np.median(list(fc.values())))
    return {pid for pid, v in fc.items() if v > med}


def flag_market(pool, ctx):
    """Ownership momentum (weak; reported but excluded from default score)."""
    slopes = [p['_features'].get('ownership_slope_7d') for p in pool
              if p['_features'].get('ownership_slope_7d') is not None]
    if not slopes:
        return set()
    med = float(np.median(slopes))
    return {p['player_id'].strip() for p in pool
            if (p['_features'].get('ownership_slope_7d') or None) is not None
            and p['_features']['ownership_slope_7d'] > med}


def flag_opportunity(pool, ctx, closers_by_name):
    ptype = pool[0]['player_type'] if pool else 'batter'
    flagged = set()
    if ptype == 'batter':
        for p in pool:
            f = p['_features']
            if (f.get('lineup_promotion_7d') or 0) >= 1 or (f.get('top_order_rate_7d') or 0) >= 0.6:
                flagged.add(p['player_id'].strip())
    else:
        for p in pool:
            key = ctx['player_lookup'].get(p['player_id'].strip())
            cl = closers_by_name.get(key) if key else None
            if not cl:
                continue
            role = (cl.get('inferred_role') or cl.get('role') or '').strip().lower()
            recent = (safe_float(cl.get('recent_sv'), 0.0) or 0.0) + \
                     (safe_float(cl.get('recent_hld'), 0.0) or 0.0)
            if role in H.CLOSER_ROLES or recent >= 1:
                flagged.add(p['player_id'].strip())
    return flagged


def flag_bandit(pool, ctx, train_pool, feats):
    """Fit archetype arms + posteriors on train, flag pool members in exploit arms."""
    scaler = fit_scaler(train_pool, feats)
    Xtr, vtr = apply_scaler(train_pool, scaler)
    idx_tr = [i for i in range(len(train_pool)) if vtr[i]]
    if len(idx_tr) < 12:
        return set()
    Xtr_v = Xtr[vtr]
    best = None
    for k in range(3, 7):
        if k >= len(idx_tr):
            continue
        labels, centers, _ = I.kmeans(Xtr_v, k)
        sil = I.silhouette_score(Xtr_v, labels)
        if best is None or sil > best[0]:
            best = (sil, k, labels, centers)
    _, k, tr_labels, centers = best
    post = I.cluster_posteriors(train_pool, idx_tr, tr_labels)
    top = sum(1 for p in train_pool if p.get('_label') == 'top')
    bot = sum(1 for p in train_pool if p.get('_label') == 'bottom')
    base = top / (top + bot) if (top + bot) else 0.5
    exploit = {c for c, (a, b, _) in post.items() if a / (a + b) > base}
    Xp, vp = apply_scaler(pool, scaler)
    flagged = set()
    for i, p in enumerate(pool):
        if not vp[i]:
            continue
        c = int(np.argmin([np.sum((Xp[i] - cen) ** 2) for cen in centers]))
        if c in exploit:
            flagged.add(p['player_id'].strip())
    return flagged


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def compute_all_flags(pool, ctx, feats, closers_by_name,
                      train_pool=None, train_ctx=None):
    """
    Return {method_name: set(player_id)} for one player-type pool.
    train_pool defaults to pool (in-sample, for the consolidation report); pass a
    labeled training pool for out-of-sample runtime scoring.
    """
    train_pool = train_pool if train_pool is not None else pool
    train_ctx = train_ctx if train_ctx is not None else ctx
    return {
        'A_clustering':  flag_clustering(pool, ctx, train_pool, train_ctx, feats),
        'B_changepoint': flag_changepoint(pool, ctx),
        'C_bayesian':    flag_bayesian(pool, ctx, train_pool),
        'D_sequential':  flag_sequential(pool, ctx, train_pool),
        'E_anomaly':     flag_anomaly(pool, ctx, feats),
        'F_forecast':    flag_forecast(pool, ctx, train_pool),
        'G_market':      flag_market(pool, ctx),
        'H_opportunity': flag_opportunity(pool, ctx, closers_by_name),
        'I_bandit':      flag_bandit(pool, ctx, train_pool, feats),
    }


def confidence_scores(pool, flags, include_weak=False):
    """player_id -> count of methods fired (excludes WEAK_METHODS by default)."""
    methods = [m for m in METHOD_NAMES if include_weak or m not in WEAK_METHODS]
    scores = {}
    for p in pool:
        pid = p['player_id'].strip()
        scores[pid] = sum(1 for m in methods if pid in flags.get(m, set()))
    return scores
