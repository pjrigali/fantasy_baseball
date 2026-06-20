"""
Description:
    Idea 17 - Runtime watchlist. Each run, scores the current free-agent pool with all
    nine method classes and ranks players by their MULTI-METHOD CONFIDENCE SCORE (how
    many independent methods flag them). The label-dependent methods (clustering,
    bandit) are fit on the Idea 15 labeled pickup set and applied out-of-sample to the
    current pool; the rest score the pool directly. Players passing the Idea 16
    supervised threshold are marked as the highest-confidence tier.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_rankings_daily.csv (current FA pool)
    - 2026 game logs / lineups / closers via waiver_features
    - data-lake/01_Bronze/fantasy_baseball/2026_espn_best_pickups.csv (training labels)

Outputs:
    - data-lake/01_Bronze/fantasy_baseball/2026_local_multi_method_watchlist.csv
    - stdout ranked top-N add candidates
"""

import os
import sys
import csv
import argparse
from datetime import date
import numpy as np

from waiver_common import (
    DATA_DIR, IDEA16_DIR, RANKINGS_FILE, BEST_PICKUPS_FILE,
    load_pickups, label_quartiles, parse_date, safe_float, fmt,
)
import waiver_features as wf
import multi_method_flags as mmf
from method_h_opportunity import load_closers_by_name

if IDEA16_DIR not in sys.path:
    sys.path.insert(0, IDEA16_DIR)
from analyze_waiver_signals_espn_2026 import find_optimal_threshold  # noqa: E402

OUT_FILE = os.path.join(DATA_DIR, '2026_local_multi_method_watchlist.csv')
PRIMARY = {'batter': ('ops_14d', 'higher'), 'pitcher': ('k9_14d', 'higher')}
PITCHER_POS = {'SP', 'RP', 'P'}


def latest_fa_pool(max_owned):
    """Return (as_of_date, list of FA player dicts) from the latest rankings snapshot."""
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
        seen.add(pid)
        pos = (r.get('player_position') or '').strip()
        ptype = 'pitcher' if pos in PITCHER_POS else 'batter'
        pool.append({
            'player_id': pid,
            'player_name': r.get('player_name', ''),
            'player_type': ptype,
            'player_position': pos,
            'pct_owned': owned,
            'acquisition_date': as_of.isoformat(),  # "as-of" date: windows look back from here
        })
    return as_of, pool


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

    # training labels
    train = load_pickups(BEST_PICKUPS_FILE)
    train_b = [p for p in train if p['player_type'] == 'batter']
    train_p = [p for p in train if p['player_type'] == 'pitcher']
    label_quartiles(train_b)
    label_quartiles(train_p)
    for p in train:
        p['_features'] = wf.build_window_features(p, ctx)
    rule_b = idea16_rule(train_b)
    rule_p = idea16_rule(train_p)

    as_of, pool = latest_fa_pool(args.max_owned)
    print(f'  as-of date: {as_of}  |  FA pool (< {args.max_owned:.0f}% owned): {len(pool)}')
    for p in pool:
        p['_features'] = wf.build_window_features(p, ctx)

    pool_b = [p for p in pool if p['player_type'] == 'batter']
    pool_p = [p for p in pool if p['player_type'] == 'pitcher']

    print('Scoring batters...')
    res = score_pool(pool_b, ctx, train_b, wf.BATTER_FEATURES, closers, rule_b)
    print('Scoring pitchers...')
    res += score_pool(pool_p, ctx, train_p, wf.PITCHER_FEATURES, closers, rule_p)

    # rank: idea16 pass first, then score, then ownership ascending
    res.sort(key=lambda r: (-int(r['idea16']), -r['score'], r['player']['pct_owned']))

    # stdout
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
