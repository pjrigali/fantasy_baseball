"""
Description:
    Shared validation harness for Idea 17. Every method section (A-I) emits a set of
    "flagged" pickups; this module scores those flags against the Idea 15 composite_z
    ground truth (top-quartile = positive class) and returns precision / recall / F1 /
    lift. Also provides a helper to score a continuous method-score against the labels
    via the same Mann-Whitney rank-biserial r used in Idea 16, so ranked outputs and
    binary flags are comparable.

Source Data:
    - None directly. Operates on in-memory pickup dicts that already carry '_label'
      (from waiver_common.label_quartiles).

Outputs:
    - None. Library module returning metric dicts.
"""

from waiver_common import safe_float


def evaluate_flags(group, flagged_ids):
    """
    group       : list of pickup dicts, each with '_label' in {top, bottom, middle}.
    flagged_ids : set/iterable of player_id strings the method flagged as add candidates.

    Positive class = top quartile. Middle-quartile pickups are excluded from the
    precision/recall denominators (consistent with Idea 16), but a flagged middle
    player still counts as a non-top flag for precision via the bottom comparison —
    here we keep it strict: precision is over top+bottom flagged only.

    Returns dict with tp, fp, fn, precision, recall, f1, lift, n_flagged.
    """
    flagged = set(flagged_ids)
    top    = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    eval_pool = top + bottom

    tp = sum(1 for p in top    if p['player_id'].strip() in flagged)
    fp = sum(1 for p in bottom if p['player_id'].strip() in flagged)
    fn = sum(1 for p in top    if p['player_id'].strip() not in flagged)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # lift: precision relative to the base rate of top within the eval pool
    base = len(top) / len(eval_pool) if eval_pool else 0.0
    lift = (precision / base) if base > 0 else 0.0

    return {
        'tp': tp, 'fp': fp, 'fn': fn,
        'precision': precision, 'recall': recall, 'f1': f1,
        'lift': lift, 'n_flagged': len([p for p in eval_pool
                                        if p['player_id'].strip() in flagged]),
        'n_top': len(top), 'n_bottom': len(bottom),
    }


def mann_whitney_r(group1, group2):
    """Rank-biserial correlation r in [-1, 1]. r>0 -> group1 tends higher."""
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


def evaluate_scores(group, scores_by_id, higher_is_better=True):
    """
    Score a continuous method output (e.g. anomaly score, forecast value) against the
    labels via rank-biserial r between top-quartile and bottom-quartile scores.

    scores_by_id : dict player_id -> float score.
    Returns dict with r, n_top, n_bottom (None r if a group is empty).
    """
    top_vals    = [scores_by_id[p['player_id'].strip()] for p in group
                   if p['_label'] == 'top' and p['player_id'].strip() in scores_by_id]
    bottom_vals = [scores_by_id[p['player_id'].strip()] for p in group
                   if p['_label'] == 'bottom' and p['player_id'].strip() in scores_by_id]
    if not higher_is_better:
        top_vals    = [-v for v in top_vals]
        bottom_vals = [-v for v in bottom_vals]
    r = mann_whitney_r(top_vals, bottom_vals)
    return {'r': r, 'n_top': len(top_vals), 'n_bottom': len(bottom_vals)}


def format_metrics_line(name, m):
    """One-line human summary of an evaluate_flags result."""
    return (f"{name:<28} P={m['precision']:.2f} R={m['recall']:.2f} "
            f"F1={m['f1']:.2f} lift={m['lift']:.2f} "
            f"(tp={m['tp']} fp={m['fp']} fn={m['fn']})")
