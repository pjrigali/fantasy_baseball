"""
Description:
    Production wrapper for the Idea 17 multi-method waiver signal watchlist.
    Scores the current FREE-AGENT pool only — players already on a league
    team's roster are excluded before scoring so results are immediately
    actionable. Scoring logic (methods A-I, confidence scores, Idea 16 gate)
    is imported from the idea_17_multi_method_signals package.

    The ideas-folder original (watch_multi_method_signals.py) scores ALL
    players regardless of roster status and is kept as a greenfield research
    surface. This script is what the daily workflow runs.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_rankings_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_roster_season.csv
    - 2026 game logs / lineups / closers (via waiver_features)
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv

Outputs:
    - data-lake/01_Bronze/fantasy_baseball/2026_local_multi_method_watchlist.csv
    - stdout ranked top-N add candidates (true free agents only)
"""

import os
import sys
import csv
import argparse
from datetime import date

# ---------------------------------------------------------------------------
# Resolve the idea_17 package so its imports work without PYTHONPATH tricks
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_IDEA17_DIR = os.path.join(_SCRIPT_DIR, 'ideas', 'idea_17_multi_method_signals')
if _IDEA17_DIR not in sys.path:
    sys.path.insert(0, _IDEA17_DIR)

import numpy as np  # noqa: E402 — numpy is used by idea_17 internals

from waiver_common import (  # noqa: E402
    DATA_DIR, IDEA16_DIR, RANKINGS_FILE, BEST_PICKUPS_FILE,
    load_pickups, label_quartiles, parse_date, safe_float, fmt,
)
import waiver_features as wf  # noqa: E402
import multi_method_flags as mmf  # noqa: E402
from method_h_opportunity import load_closers_by_name  # noqa: E402

if IDEA16_DIR not in sys.path:
    sys.path.insert(0, IDEA16_DIR)
from analyze_waiver_signals_espn_2026 import find_optimal_threshold  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ROSTER_FILE = os.path.join(DATA_DIR, '2026_espn_roster_season.csv')
OUT_FILE    = os.path.join(DATA_DIR, '2026_local_multi_method_watchlist.csv')
PRIMARY     = {'batter': ('ops_14d', 'higher'), 'pitcher': ('k9_14d', 'higher')}
PITCHER_POS = {'SP', 'RP', 'P'}


# ---------------------------------------------------------------------------
# Roster filter
# ---------------------------------------------------------------------------

def _rostered_player_ids():
    """Return set of player_id strings currently on any league team."""
    rostered = set()
    if not os.path.exists(ROSTER_FILE):
        return rostered
    with open(ROSTER_FILE, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            pid = (r.get('player_id') or '').strip()
            if pid:
                rostered.add(pid)
    return rostered


def latest_fa_pool(max_owned):
    """Return (as_of_date, FA player dicts) — rostered players excluded."""
    rostered = _rostered_player_ids()
    rows = []
    with open(RANKINGS_FILE, encoding='utf-8', errors='replace') as f:
        for r in csv.DictReader(f):
            d = parse_date(r.get('date', ''))
            if d:
                r['_date'] = d
                rows.append(r)
    as_of = max(r['_date'] for r in rows)
    pool = []
    seen = set()
    for r in rows:
        if r['_date'] != as_of:
            continue
        pid = (r.get('player_id') or '').strip()
        owned = safe_float(r.get('pct_owned'), 0.0)
        if not pid or pid in seen or owned is None or owned >= max_owned:
            continue
        if pid in rostered:
            continue
        seen.add(pid)
        pos = (r.get('player_position') or '').strip()
        ptype = 'pitcher' if pos in PITCHER_POS else 'batter'
        pool.append({
            'player_id': pid,
            'player_name': r.get('player_name', ''),
            'player_type': ptype,
            'player_position': pos,
            'pct_owned': owned,
            'acquisition_date': as_of.isoformat(),
        })
    return as_of, pool, len(rostered)


# ---------------------------------------------------------------------------
# Idea 16 rule helpers (identical to ideas original)
# ---------------------------------------------------------------------------

def idea16_rule(train_group):
    ptype = train_group[0]['player_type'] if train_group else 'batter'
    feat, direction = PRIMARY[ptype]
    top = [p['_features'].get(feat) for p in train_group if p['_label'] == 'top'
           and p['_features'].get(feat) is not None]
    bottom = [p['_features'].get(feat) for p in train_group if p['_label'] == 'bottom'
              and p['_features'].get(feat) is not None]
    if len(top) < 3 or len(bottom) < 3:
        return None
    thr, *_ = find_optimal_threshold(top, bottom, direction)
    return feat, direction, thr


def passes_idea16(player, rule):
    if not rule:
        return False
    feat, direction, thr = rule
    v = player['_features'].get(feat)
    if v is None:
        return False
    return (v >= thr) if direction == 'higher' else (v <= thr)


def score_pool(pool, ctx, train_group, feats, closers, rule):
    if not pool:
        return []
    flags = mmf.compute_all_flags(pool, ctx, feats, closers, train_pool=train_group)
    scores = mmf.confidence_scores(pool, flags)
    out = []
    for p in pool:
        pid = p['player_id'].strip()
        fired = [m.split('_')[0] for m in mmf.METHOD_NAMES if pid in flags[m]]
        out.append({
            'player': p,
            'score': scores[pid],
            'methods': fired,
            'idea16': passes_idea16(p, rule),
        })
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-owned', type=float, default=80.0,
                    help='only score players below this pct_owned (default 80)')
    ap.add_argument('--top', type=int, default=25, help='rows to print to stdout')
    ap.add_argument('--dry-run', action='store_true',
                    help='compute and print but do not write the watchlist CSV')
    args = ap.parse_args()

    print('Multi-method runtime watchlist')
    print('Loading 2026 data + training labels...')
    ctx = wf.load_all_2026()
    closers = load_closers_by_name()

    train = load_pickups(BEST_PICKUPS_FILE)
    train_b = [p for p in train if p['player_type'] == 'batter']
    train_p = [p for p in train if p['player_type'] == 'pitcher']
    label_quartiles(train_b)
    label_quartiles(train_p)
    for p in train:
        p['_features'] = wf.build_window_features(p, ctx)
    rule_b = idea16_rule(train_b)
    rule_p = idea16_rule(train_p)

    as_of, pool, n_rostered = latest_fa_pool(args.max_owned)
    print(f'  as-of date: {as_of}  |  FA pool (< {args.max_owned:.0f}% owned, {n_rostered} rostered excluded): {len(pool)}')
    for p in pool:
        p['_features'] = wf.build_window_features(p, ctx)

    pool_b = [p for p in pool if p['player_type'] == 'batter']
    pool_p = [p for p in pool if p['player_type'] == 'pitcher']

    print('Scoring batters...')
    res = score_pool(pool_b, ctx, train_b, wf.BATTER_FEATURES, closers, rule_b)
    print('Scoring pitchers...')
    res += score_pool(pool_p, ctx, train_p, wf.PITCHER_FEATURES, closers, rule_p)

    res.sort(key=lambda r: (-int(r['idea16']), -r['score'], r['player']['pct_owned']))

    print(f'\n=== Top {args.top} multi-method add candidates (as of {as_of}) ===')
    print(f'{"Player":<24}{"Pos":<5}{"Own%":>6}{"Score":>6}{"I16":>5}  Methods')
    for r in res[:args.top]:
        p = r['player']
        print(f"{p['player_name'][:23]:<24}{p['player_position']:<5}"
              f"{p['pct_owned']:>6.1f}{r['score']:>6}{'Y' if r['idea16'] else '':>5}  "
              f"{', '.join(r['methods'])}")

    if not args.dry_run:
        with open(OUT_FILE, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['as_of_date', 'player_id', 'player_name', 'player_position',
                        'player_type', 'pct_owned', 'confidence_score', 'passes_idea16',
                        'methods_fired'])
            for r in res:
                p = r['player']
                w.writerow([as_of.isoformat(), p['player_id'], p['player_name'],
                            p['player_position'], p['player_type'], f"{p['pct_owned']:.1f}",
                            r['score'], int(r['idea16']), '|'.join(r['methods'])])
        print(f'\nWatchlist written to: {OUT_FILE}  ({len(res)} players)')
    else:
        print('\n[dry-run] watchlist CSV not written.')


if __name__ == '__main__':
    main()
