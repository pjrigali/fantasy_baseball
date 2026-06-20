"""
Description:
    Idea 17 - Section F: Time Series Forecasting. Instead of describing what a player
    has done, forecast what they will do next. Projects each player's next-game
    good-direction stat (batter OPS / pitcher K9) from their per-game series:
      1. Exponential smoothing (ETS) via statsmodels SimpleExpSmoothing, with a
         hand-rolled EWMA fallback for very short series.
      2. ARIMA(1,0,0) via statsmodels for series long enough to estimate, capturing
         momentum/mean-reversion; falls back to ETS on failure.
    Compares the forecast's separation power against the raw rolling average (the
    Idea 16 input) to test whether a forward-looking feature beats a backward one.

Source Data:
    - Per-game series from waiver_features (2026 + 2025 cross-check).

Outputs:
    - stdout validation summary.
    - reports/method_f_forecast.md
"""

import os
import warnings
import numpy as np

warnings.filterwarnings('ignore')

from waiver_common import (
    REPORTS_DIR, BEST_PICKUPS_FILE, BEST_PICKUPS_2025_FILE,
    load_pickups, label_quartiles, fmt,
)
import waiver_features as wf
from waiver_validation import evaluate_flags, evaluate_scores, format_metrics_line

REPORT_FILE = os.path.join(REPORTS_DIR, 'method_f_forecast.md')
MIN_GAMES = 5


def ewma_forecast(values, alpha=0.4):
    f = values[0]
    for v in values[1:]:
        f = alpha * v + (1 - alpha) * f
    return f


def ets_forecast(values):
    try:
        from statsmodels.tsa.holtwinters import SimpleExpSmoothing
        model = SimpleExpSmoothing(np.asarray(values, dtype=float),
                                   initialization_method='heuristic').fit()
        return float(model.forecast(1)[0])
    except Exception:
        return ewma_forecast(values)


def arima_forecast(values):
    if len(values) < 8:
        return ets_forecast(values)
    try:
        from statsmodels.tsa.arima.model import ARIMA
        model = ARIMA(np.asarray(values, dtype=float), order=(1, 0, 0)).fit()
        return float(model.forecast(1)[0])
    except Exception:
        return ets_forecast(values)


def analyze_type(group, ctx, ptype_label, lines):
    A = lines.append
    top = [p for p in group if p['_label'] == 'top']
    bottom = [p for p in group if p['_label'] == 'bottom']
    base = len(top) / (len(top) + len(bottom)) if (top or bottom) else 0.0

    ets, arima, rawavg = {}, {}, {}
    for p in group:
        _, vals = wf.get_primary_series(p, ctx)
        if len(vals) < MIN_GAMES:
            continue
        pid = p['player_id'].strip()
        ets[pid] = ets_forecast(vals)
        arima[pid] = arima_forecast(vals)
        rawavg[pid] = float(np.mean(vals[-7:]))  # trailing rolling avg (idea 16 style)

    if not ets:
        A(f'### {ptype_label}\n\n_Insufficient series data._\n')
        return None

    ets_r = evaluate_scores(group, ets, higher_is_better=True)['r']
    arima_r = evaluate_scores(group, arima, higher_is_better=True)['r']
    raw_r = evaluate_scores(group, rawavg, higher_is_better=True)['r']

    ets_med = float(np.median(list(ets.values())))
    ets_flagged = {pid for pid, v in ets.items() if v > ets_med}
    ets_m = evaluate_flags(group, ets_flagged)
    arima_med = float(np.median(list(arima.values())))
    arima_flagged = {pid for pid, v in arima.items() if v > arima_med}
    arima_m = evaluate_flags(group, arima_flagged)

    print(f'\n--- {ptype_label} ---  (forecasted players={len(ets)}, base={base:.2f})')
    print(f'  rank-biserial r: ETS={fmt(ets_r,3)}  ARIMA={fmt(arima_r,3)}  '
          f'raw rolling avg={fmt(raw_r,3)}')
    print('  ' + format_metrics_line('ETS forecast > median', ets_m))
    print('  ' + format_metrics_line('ARIMA forecast > median', arima_m))

    A(f'### {ptype_label}')
    A('')
    A(f'- Forecasted players (>= {MIN_GAMES} games): **{len(ets)}** | base top-rate: **{base:.2f}**')
    A(f'- Separation (rank-biserial r): ETS `{fmt(ets_r,3)}`, ARIMA `{fmt(arima_r,3)}`, '
      f'raw rolling avg `{fmt(raw_r,3)}` — forecasting '
      f'{"beats" if (ets_r or 0) > (raw_r or 0) else "does not beat"} the backward-looking average.')
    A('')
    A('| Forecaster | Precision | Recall | F1 | Lift | tp | fp | fn |')
    A('|------------|-----------|--------|----|------|----|----|----|')
    for nm, m in [('ETS (exp. smoothing)', ets_m), ('ARIMA(1,0,0)', arima_m)]:
        A(f"| {nm} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f}"
          f" | {m['lift']:.2f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    A('')
    return {'ets': ets_m, 'arima': arima_m, 'ets_r': ets_r, 'raw_r': raw_r,
            'flagged_ets': ets_flagged}


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
    print('Section F — Time Series Forecasting')
    print('Loading 2026 data...')
    ctx26 = wf.load_all_2026()
    lines = ['# Section F — Time Series Forecasting (Project the Next Game)', '',
             'Forecasts each player\'s next good-direction game via ETS and ARIMA, then '
             'tests whether the forward-looking forecast separates top from bottom '
             'pickups better than the backward-looking rolling average used in Idea 16.', '']
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
