"""
Description:
    Idea 17 - Section H: Opportunity Graph / Lineup Dependency Modeling. Some adds are
    about a structural change in opportunity, not the player's own recent stats.
      1. Batting-order opportunity - flags batters promoted up the lineup in the last 7
         days (more run-scoring opportunity) or who occupy a top-of-order slot.
      2. Saves opportunity cascade - joins the closers-depth chart (by name) and flags
         relievers in a closer/setup role or already accumulating recent saves+holds,
         the arms next in line when a closer event occurs.
      3. Platoon detection - noted as a limitation: the data lake has no per-game
         handedness splits, so platoon-partner opportunity can't be derived here.

Source Data:
    - waiver_features 2026 bundle + 2026_mlb_closers_depth.csv (joined by name).

Outputs:
    - stdout summary.
    - reports/method_h_opportunity.md
"""

import os
import csv
from collections import defaultdict
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, CLOSERS_FILE,
    load_pickups, label_quartiles, fmt, parse_date, normalize_name, safe_float,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_h_opportunity.md')
CLOSER_ROLES = {'closer', 'setup', 'high_leverage', 'co_closer', 'closer_committee'}


def load_closers_by_name():
    """Latest closers-depth row per normalized player name (id space != ESPN)."""
    latest = {}
    if not os.path.exists(CLOSERS_FILE):
        return latest
    with open(CLOSERS_FILE, encoding='utf-8', errors='replace') as f:
        for row in csv.DictReader(f):
            key = normalize_name(row.get('player_name', ''))
            d = parse_date(row.get('date_scraped', ''))
            if not key or d is None:
                continue
            if key not in latest or d > latest[key]['_d']:
                row['_d'] = d
                latest[key] = row
    return latest


def main():
    print('Section H — Opportunity Graph')
    print('Loading 2026 data...')
    ctx = wf.load_all_2026()
    closers = load_closers_by_name()
    pickups = load_pickups(BEST_PICKUPS_FILE)
    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']
    label_quartiles(batters)
    label_quartiles(pitchers)
    for p in pickups:
        p['_features'] = wf.build_window_features(p, ctx)

    lines = ['# Section H — Opportunity Graph (Lineup Dependency)', '',
             'Flags structural opportunity changes — lineup promotions and bullpen-role '
             'cascades — that raise a player\'s value before their own stats move.', '']
    A = lines.append

    # ---- Batters: lineup promotion / top-of-order ----
    bat_flagged = set()
    n_promo = 0
    for p in batters:
        f = p['_features']
        promo = (f.get('lineup_promotion_7d') or 0) >= 1
        top_slot = (f.get('top_order_rate_7d') or 0) >= 0.6
        if promo:
            n_promo += 1
        if promo or top_slot:
            bat_flagged.add(p['player_id'].strip())
    bat_m = evaluate_flags(batters, bat_flagged)

    # ---- Pitchers: saves cascade ----
    pit_flagged = set()
    n_closer_ctx = 0
    for p in pitchers:
        key = ctx['player_lookup'].get(p['player_id'].strip())
        cl = closers.get(key) if key else None
        if not cl:
            continue
        n_closer_ctx += 1
        role = (cl.get('inferred_role') or cl.get('role') or '').strip().lower()
        recent = (safe_float(cl.get('recent_sv'), 0.0) or 0.0) + \
                 (safe_float(cl.get('recent_hld'), 0.0) or 0.0)
        if role in CLOSER_ROLES or recent >= 1:
            pit_flagged.add(p['player_id'].strip())
    pit_m = evaluate_flags(pitchers, pit_flagged)

    print(f'  batters promoted/top-of-order flagged: {len(bat_flagged)} (promotions={n_promo})')
    print('  ' + format_metrics_line('Batter lineup opportunity', bat_m))
    print(f'  pitchers with closers-depth context: {n_closer_ctx}')
    print('  ' + format_metrics_line('Pitcher saves cascade', pit_m))

    A('## Batters — Lineup Promotion / Top-of-Order')
    A('')
    A(f'- Flag = moved up >=1 lineup slot in last 7d, or >=60% of starts batting in the '
      f'top 3. Flagged: **{len(bat_flagged)}** (of which {n_promo} were promotions).')
    A('')
    A('| Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|-----------|--------|----|------|----|----|----|')
    A(f"| {bat_m['precision']:.2f} | {bat_m['recall']:.2f} | {bat_m['f1']:.2f} | "
      f"{bat_m['lift']:.2f} | {bat_m['tp']} | {bat_m['fp']} | {bat_m['fn']} |")
    A('')
    A('## Pitchers — Saves Opportunity Cascade')
    A('')
    A(f'- Joined to closers-depth chart by name; **{n_closer_ctx}** of {len(pitchers)} '
      f'pitcher pickups had bullpen-role context.')
    A(f'- Flag = closer/setup/high-leverage role or >=1 recent save+hold. Flagged: '
      f'**{len(pit_flagged)}**.')
    A('')
    A('| Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|-----------|--------|----|------|----|----|----|')
    A(f"| {pit_m['precision']:.2f} | {pit_m['recall']:.2f} | {pit_m['f1']:.2f} | "
      f"{pit_m['lift']:.2f} | {pit_m['tp']} | {pit_m['fp']} | {pit_m['fn']} |")
    A('')
    A('## Platoon Detection — Limitation')
    A('')
    A('The data lake has no per-game batter-handedness or opposing-pitcher-hand splits, '
      'so platoon-partner opportunity (a partner hitting the IL freeing full-time at-bats) '
      'cannot be derived. Deferred until handedness splits are collected.')
    A('')

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'\nReport written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
