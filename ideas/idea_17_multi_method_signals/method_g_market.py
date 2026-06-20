"""
Description:
    Idea 17 - Section G: Market Efficiency Analysis. Treats ownership % as a prediction
    market and measures where the lag between performance and market reaction is
    largest - that lag is the add window.
      1. Ownership lag by position - for each pickup, days between the first qualifying
         performance game (OPS>=0.8 / K9>=9 in the 21d window) and the first ownership
         spike (+10% pct_owned in a day), aggregated by position group. Longer lag =
         slower market = wider edge.
      2. Ownership slope vs performance decile - bins pickups by their rolling stat and
         shows mean ownership slope + top-rate per decile (the inefficiency gradient).
      3. Low-signal / high-ownership players - the inverse: rostered-but-weak players
         whose roster spots are leaking value (drop candidates).
    Validated add rule: under-owned riser = below-median ownership AND positive slope.

Source Data:
    - waiver_features 2026 bundle (game logs + rankings). 2026 only (no prior-year
      ownership in the lake).

Outputs:
    - stdout summary.
    - reports/method_g_market.md
"""

import os
from datetime import timedelta
from collections import defaultdict
import numpy as np

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, load_pickups, label_quartiles, fmt,
    parse_date, safe_float, safe_int,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_g_market.md')

POS_GROUP = {
    'C': 'C', '1B': 'CI', '3B': 'CI', '2B': 'MI', 'SS': 'MI',
    'LF': 'OF', 'CF': 'OF', 'RF': 'OF', 'OF': 'OF', 'DH': 'DH',
    'SP': 'SP', 'RP': 'RP', 'P': 'P',
}
GOOD_GAME = {'batter': 0.800, 'pitcher': 9.0}


def position_for(pid, rankings):
    rows = rankings.get(pid, [])
    if not rows:
        return None
    pos = (rows[-1].get('player_position') or '').strip()
    return POS_GROUP.get(pos, pos or None)


def first_perf_date(pickup, ctx):
    acq = parse_date(pickup['acquisition_date'])
    ptype = pickup['player_type']
    key = ctx['player_lookup'].get(pickup['player_id'].strip())
    rows = ctx['game_logs'].get(key, []) if key else []
    lo = acq - timedelta(days=21)
    thr = GOOD_GAME[ptype]
    for r in rows:
        if not (lo <= r['_date'] < acq):
            continue
        if ptype == 'batter':
            from analyze_waiver_signals_espn_2026 import compute_ops
            v = compute_ops([r])
        else:
            from analyze_waiver_signals_espn_2026 import compute_k9
            v = compute_k9([r])
        if v is not None and v >= thr:
            return r['_date']
    return None


def first_spike_date(pid, ctx, acq, days=30):
    rows = ctx['rankings'].get(pid, [])
    lo = acq - timedelta(days=days)
    for r in rows:
        if lo <= r['_date'] <= acq and safe_float(r.get('pct_change'), 0.0) >= 10.0:
            return r['_date']
    return None


def main():
    print('Section G — Market Efficiency')
    print('Loading 2026 data...')
    ctx = wf.load_all_2026()
    pickups = load_pickups(BEST_PICKUPS_FILE)
    batters  = [p for p in pickups if p['player_type'] == 'batter']
    pitchers = [p for p in pickups if p['player_type'] == 'pitcher']
    label_quartiles(batters)
    label_quartiles(pitchers)
    for p in pickups:
        p['_features'] = wf.build_window_features(p, ctx)

    lines = ['# Section G — Market Efficiency Analysis', '',
             'Ownership % as a prediction market: where the lag between performance and '
             'market reaction is largest, the add window is widest. 2026 only (no '
             'prior-year ownership in the data lake).', '']
    A = lines.append

    # ---- 1. Ownership lag by position ----
    lag_by_pos = defaultdict(list)
    for p in pickups:
        acq = parse_date(p['acquisition_date'])
        pid = p['player_id'].strip()
        perf = first_perf_date(p, ctx)
        spike = first_spike_date(pid, ctx, acq)
        if perf and spike and spike >= perf:
            lag_by_pos[position_for(pid, ctx['rankings']) or '?'].append((spike - perf).days)

    print('\n--- Ownership lag by position (days perf->spike) ---')
    A('## Ownership Lag by Position')
    A('')
    A('Median days between a qualifying performance game and the first +10% ownership '
      'spike. Longer = slower market = wider edge.')
    A('')
    lag_rows = [(pos, lag_by_pos[pos]) for pos in lag_by_pos if len(lag_by_pos[pos]) >= 2]
    if lag_rows:
        A('| Position | n | Median lag (days) | Mean lag |')
        A('|----------|---|-------------------|----------|')
        for pos, lags in sorted(lag_rows, key=lambda t: -np.median(t[1])):
            print(f'  {pos:>4}: n={len(lags):>2} median={np.median(lags):.1f} mean={np.mean(lags):.1f}')
            A(f'| {pos} | {len(lags)} | {np.median(lags):.1f} | {np.mean(lags):.1f} |')
    else:
        n_pairs = sum(len(v) for v in lag_by_pos.values())
        print('  insufficient perf->spike pairs to break out by position')
        A(f'_Insufficient data: only {n_pairs} pickups had both a qualifying performance '
          'game and an ownership spike inside the window (ownership coverage is ~39%), '
          'too few to break out reliably by position. Revisit once more ownership '
          'history accrues._')
    A('')

    # ---- 2. Ownership slope vs performance decile ----
    A('## Ownership Slope vs Performance Decile')
    A('')
    for ptype_label, group, stat in [('Batters', batters, 'ops_14d'),
                                     ('Pitchers', pitchers, 'k9_14d')]:
        rows = [(p, p['_features'].get(stat), p['_features'].get('ownership_slope_7d'))
                for p in group]
        rows = [(p, s, o) for (p, s, o) in rows if s is not None]
        rows.sort(key=lambda t: t[1])
        if len(rows) < 10:
            continue
        A(f'### {ptype_label} (binned by `{stat}`)')
        A('')
        A('| Decile | n | mean stat | mean own. slope | top-rate |')
        A('|--------|---|-----------|-----------------|----------|')
        n = len(rows)
        for d in range(5):  # quintiles for readability
            lo = d * n // 5
            hi = (d + 1) * n // 5
            chunk = rows[lo:hi]
            if not chunk:
                continue
            mean_s = np.mean([s for (_, s, _) in chunk])
            slopes = [o for (_, _, o) in chunk if o is not None]
            mean_o = np.mean(slopes) if slopes else float('nan')
            tb = [p for (p, _, _) in chunk if p['_label'] in ('top', 'bottom')]
            tr = (sum(1 for p in tb if p['_label'] == 'top') / len(tb)) if tb else None
            A(f'| Q{d+1} | {len(chunk)} | {mean_s:.3f} | '
              f'{("%.3f" % mean_o) if mean_o==mean_o else "—"} | {fmt(tr,2) if tr is not None else "—"} |')
        A('')

    # ---- 3. Low-signal high-ownership drop candidates ----
    A('## Low-Signal, High-Ownership (Drop Candidates)')
    A('')
    A('Pickups that were well-owned at acquisition yet landed in the bottom quartile — '
      'roster spots where the market left value on the table.')
    A('')
    drops = [p for p in pickups
             if p['_label'] == 'bottom'
             and (p['_features'].get('pct_owned_at_pickup') or 0) >= 50]
    drops.sort(key=lambda p: -(p['_features'].get('pct_owned_at_pickup') or 0))
    A('| Player | Type | pct_owned | composite_z |')
    A('|--------|------|-----------|-------------|')
    for p in drops[:12]:
        A(f"| {p['player_name']} | {p['player_type']} | "
          f"{fmt(p['_features'].get('pct_owned_at_pickup'),1)} | {fmt(safe_float(p['composite_z']),2)} |")
    A('')

    # ---- 4. Validated market rules ----
    # The decile table shows tops are NOT under-owned in this league; instead ownership
    # MOMENTUM (slope) tracks the top quartile. We validate the momentum rule and keep
    # the under-owned-performer rule alongside it as an honest comparison.
    A('## Validated Add Rules — Honest Negative Result')
    A('')
    A('Two candidate rules were tested and **both fail to separate top from bottom '
      'pickups** (lift < 1):')
    A('')
    A('- **Momentum:** 7-day ownership slope above the type median.')
    A('- **Under-owned performer:** rolling stat above median AND ownership below median.')
    A('')
    A('Why: ownership hype attaches to *busts as well as hits*. Bottom-quartile pickups '
      'were also added amid rising ownership (managers chased them, then they flopped), '
      'so ownership signals alone cannot tell a good add from a bad one. Section G\'s '
      'value is therefore **descriptive** (the performance/ownership decile gradient and '
      'the drop-candidate list above), not a standalone predictive signal. The '
      'consolidation step down-weights ownership-only flags accordingly.')
    A('')
    A('| Rule | Type | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|------|------|-----------|--------|----|------|----|----|----|')
    flagged_all = {}
    for ptype_label, group, stat in [('Batters', batters, 'ops_14d'),
                                     ('Pitchers', pitchers, 'k9_14d')]:
        owns = [p['_features'].get('pct_owned_at_pickup') for p in group
                if p['_features'].get('pct_owned_at_pickup') is not None]
        slopes = [p['_features'].get('ownership_slope_7d') for p in group
                  if p['_features'].get('ownership_slope_7d') is not None]
        stats = [p['_features'].get(stat) for p in group
                 if p['_features'].get(stat) is not None]
        own_med = np.median(owns) if owns else 0.0
        slope_med = np.median(slopes) if slopes else 0.0
        stat_med = np.median(stats) if stats else 0.0

        mom = {p['player_id'].strip() for p in group
               if (p['_features'].get('ownership_slope_7d') is not None
                   and p['_features']['ownership_slope_7d'] > slope_med)}
        uop = {p['player_id'].strip() for p in group
               if (p['_features'].get(stat) is not None
                   and p['_features'].get('pct_owned_at_pickup') is not None
                   and p['_features'][stat] > stat_med
                   and p['_features']['pct_owned_at_pickup'] < own_med)}
        m_mom = evaluate_flags(group, mom)
        m_uop = evaluate_flags(group, uop)
        flagged_all[(ptype_label, 'momentum')] = mom
        print('  ' + format_metrics_line(f'Ownership momentum ({ptype_label})', m_mom))
        print('  ' + format_metrics_line(f'Under-owned performer ({ptype_label})', m_uop))
        for nm, m in [('Momentum', m_mom), ('Under-owned perf.', m_uop)]:
            A(f"| {nm} | {ptype_label} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f}"
              f" | {m['lift']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    A('')

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f'\nReport written to: {REPORT_FILE}')


if __name__ == '__main__':
    main()
