"""
Description: Post-season league-wide roster management analysis. Computes the optimal
             evaluation window (days of trailing stats most predictive of future performance),
             team churn rate (adds per week), roster patience (avg days held before dropping),
             and total value generated per team. Generates a markdown report with Mermaid
             charts comparing each team's management style vs the top performers.
             Identity (mlbam game-log id -> espn roster id) is resolved through the
             canonical player_map.csv (mlbam_player_id <-> espn_player_id bridge).
Source Data: 2025_espn_roster_history.csv, 2025_mlb_stats_daily.csv, player_map.csv
Outputs:     fantasy_baseball/reports/league_roster_analysis_2025.md (markdown + Mermaid)

Notes: csv + numpy only (no pandas). Rows loaded as list[dict].
"""

import csv
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

SEASON = 2025
BASE_PATH = mp.DATA_PATH
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(SCRIPT_DIR, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(REPORT_DIR, f'league_roster_analysis_{SEASON}.md')

BATTER_STATS = ['R', 'HR', 'RBI', 'SB']
PITCHER_POSITIVE = ['QS', 'SVHD', 'K']


def read_csv(path):
    with open(path, encoding='utf-8-sig', errors='replace') as f:
        return list(csv.DictReader(f))


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y'):
        try:
            return datetime.strptime(s[:19], fmt).date()
        except ValueError:
            continue
    return None


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def zscores(values):
    arr = np.array(values, dtype=float)
    mean = arr.mean()
    std = arr.std(ddof=1) if len(arr) > 1 else 0.0
    std = std if std else 1.0
    return (arr - mean) / std


def main():
    print("Loading data...")
    roster_rows = read_csv(os.path.join(BASE_PATH, f'{SEASON}_espn_roster_history.csv'))
    stats_rows = read_csv(os.path.join(BASE_PATH, f'{SEASON}_mlb_stats_daily.csv'))
    map_rows = read_csv(os.path.join(BASE_PATH, 'player_map.csv'))

    # mlbam -> (espn_id, name)
    mlbam_to_espn = {}
    for r in map_rows:
        mlbam = (r.get('mlbam_player_id') or '').strip()
        espn = (r.get('espn_player_id') or '').strip()
        if mlbam and espn:
            mlbam_to_espn[mlbam] = (espn, (r.get('espn_name') or r.get('mlb_name') or '').strip())

    # ── Parse stats, attach espn id, group by date ───────────────────────────────
    rows_by_date = defaultdict(list)
    max_date = None
    for r in stats_rows:
        d = parse_date(r.get('date'))
        if d is None:
            continue
        mlbam = (r.get('playerId') or '').strip()
        bridge = mlbam_to_espn.get(mlbam)
        if not bridge:
            continue
        espn_id, name = bridge
        r['_date'] = d
        r['_espn_id'] = espn_id
        r['_name'] = name or (r.get('playerName') or '')
        rows_by_date[d].append(r)
        if max_date is None or d > max_date:
            max_date = d

    # ── Per-date Daily_Value -> sum per (date, espn_id) ──────────────────────────
    print("Calculating Daily Value (league wide)...")
    daily_value = defaultdict(float)
    name_of = {}
    for d, rows in rows_by_date.items():
        contrib = np.zeros(len(rows))
        for col in BATTER_STATS + PITCHER_POSITIVE:
            if rows and col in rows[0]:
                contrib += zscores([to_float(r.get(col)) for r in rows])
        if rows and 'P_H' in rows[0] and 'P_BB' in rows[0]:
            contrib -= zscores([to_float(r.get('P_H')) + to_float(r.get('P_BB')) for r in rows])
        if rows and 'ER' in rows[0]:
            contrib -= zscores([to_float(r.get('ER')) for r in rows])
        for r, c in zip(rows, contrib):
            daily_value[(d, r['_espn_id'])] += float(c)
            name_of[r['_espn_id']] = r['_name']

    # ── Build date x player matrix (0-filled, like pivot.fillna(0)) ──────────────
    dates = sorted({d for (d, _) in daily_value})
    players = sorted({p for (_, p) in daily_value})
    date_idx = {d: i for i, d in enumerate(dates)}
    pcol = {p: j for j, p in enumerate(players)}
    M = np.zeros((len(dates), len(players)))
    for (d, p), v in daily_value.items():
        M[date_idx[d], pcol[p]] = v
    n_dates = len(dates)

    def rolling_mean(window):
        """[date,player] trailing mean of `window` rows; NaN before enough rows."""
        out = np.full(M.shape, np.nan)
        csum = np.cumsum(M, axis=0)
        for i in range(n_dates):
            if i >= window - 1:
                prev = csum[i - window] if i - window >= 0 else 0
                out[i] = (csum[i] - prev) / window
        return out

    # ── Optimal evaluation window (3..90) vs next-7-day performance ──────────────
    print("Calculating Optimal Evaluation Window (3-90 days)...")
    roll7 = rolling_mean(7)
    future_7 = np.full(M.shape, np.nan)        # future_7[i] = mean(next 7 days) = roll7[i+7]
    for i in range(n_dates):
        if i + 7 < n_dates:
            future_7[i] = roll7[i + 7]

    windows = list(range(3, 91, 3))
    correlations = {}
    for w in windows:
        past_w = rolling_mean(w)
        lo, hi = w - 1, n_dates - 8           # rows where both past_w and future_7 exist
        if hi < lo:
            correlations[w] = float('nan')
            continue
        past_vals = past_w[lo:hi + 1].ravel()
        fut_vals = future_7[lo:hi + 1].ravel()
        mask = ~np.isnan(past_vals) & ~np.isnan(fut_vals)
        if mask.sum() < 2 or np.std(past_vals[mask]) == 0 or np.std(fut_vals[mask]) == 0:
            correlations[w] = float('nan')
        else:
            correlations[w] = float(np.corrcoef(past_vals[mask], fut_vals[mask])[0, 1])

    valid_corrs = {w: c for w, c in correlations.items() if not np.isnan(c)}
    max_corr = max(valid_corrs.values())
    threshold = 0.90 * max_corr
    best_window, best_corr = 90, 0.0
    for w in sorted(valid_corrs):
        if valid_corrs[w] >= threshold:
            best_window, best_corr = w, valid_corrs[w]
            break
    print(f"Max Correlation: {max_corr:.4f}")
    print(f"Aggressive Optimal Window (>= 90% of max): {best_window} days (Corr: {best_corr:.4f})")

    # ── Parse rosters ────────────────────────────────────────────────────────────
    rosters = []
    season_start = None
    for r in roster_rows:
        sd = parse_date(r.get('start_date'))
        ed = parse_date(r.get('end_date')) or max_date
        if sd is None:
            continue
        rosters.append({
            'team_abbrev': (r.get('team_abbrev') or '').strip(),
            'player_id': (r.get('player_id') or '').strip(),
            'days_held': to_float(r.get('days_held')),
            'start_date': sd, 'end_date': ed,
        })
        if season_start is None or sd < season_start:
            season_start = sd

    # ── Roster patience (dropped players) ────────────────────────────────────────
    print("Analyzing Roster Patience...")
    drop_buffer = max_date - timedelta(days=3)
    held_by_team = defaultdict(list)
    for r in rosters:
        if r['end_date'] < drop_buffer:
            held_by_team[r['team_abbrev']].append(min(r['days_held'], 180.0))
    patience = {}
    for t, vals in held_by_team.items():
        a = np.array(vals)
        patience[t] = {
            'Drops': len(a),
            'Avg_Hold_Days': float(a.mean()) if len(a) else 0.0,
            'Median_Hold_Days': float(np.percentile(a, 50)) if len(a) else 0.0,
            'Std_Dev': float(a.std(ddof=1)) if len(a) > 1 else 0.0,
        }

    # ── Churn (adds per week) ────────────────────────────────────────────────────
    print("Analyzing Churn Rate...")
    total_weeks = (max_date - season_start).days / 7 if season_start else 1
    adds_by_team = defaultdict(int)
    for r in rosters:
        if r['start_date'] > season_start + timedelta(days=7):
            adds_by_team[r['team_abbrev']] += 1
    churn = {t: {'Total_Adds': c, 'Adds_Per_Week': c / total_weeks}
             for t, c in adds_by_team.items()}

    # ── Team success (total value over active roster-days) ───────────────────────
    print("Calculating Team Success...")
    team_values = defaultdict(float)
    teams = sorted({r['team_abbrev'] for r in rosters})
    for t in teams:
        team_values[t] = 0.0
    n_days = (max_date - season_start).days + 1
    day = season_start
    while day <= max_date:
        di = date_idx.get(day)
        active = [r for r in rosters if r['start_date'] <= day <= r['end_date']]
        for r in active:
            j = pcol.get(r['player_id'])
            if di is not None and j is not None:
                team_values[r['team_abbrev']] += M[di, j]
        day += timedelta(days=1)

    # ── Combine metrics ──────────────────────────────────────────────────────────
    metrics = {}
    for t in teams:
        if t not in patience or t not in churn:
            continue
        metrics[t] = {
            'Total_Value': team_values[t],
            'Value_Per_Day': team_values[t] / n_days,
            **patience[t],
            **churn[t],
        }
    ranked = sorted(metrics.items(), key=lambda kv: kv[1]['Total_Value'], reverse=True)
    top3 = ranked[:3]
    optimal_churn = np.mean([m['Adds_Per_Week'] for _, m in top3]) if top3 else 0.0
    optimal_hold = np.mean([m['Avg_Hold_Days'] for _, m in top3]) if top3 else 0.0
    for t, m in metrics.items():
        m['Churn_Diff'] = m['Adds_Per_Week'] - optimal_churn

    # ── Report ───────────────────────────────────────────────────────────────────
    print("Generating report...")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write("# League-Wide Roster Analysis (Deep Dive)\n\n")
        f.write("## 1. Optimal Evaluation Window\n")
        f.write(f"**Selected Window:** {best_window} Days\n")
        f.write(f"Correlation with future performance: **{best_corr:.4f}**\n")
        f.write("*(Analysis performed on all players across the entire league)*\n\n")
        f.write("### Sensitivity Analysis (Correlation by Window):\n")
        selected = {w: c for w, c in valid_corrs.items()
                    if w % 15 == 0 or w == best_window or w == 3 or w == 90}
        for w in sorted(selected):
            pre = "**" if w == best_window else ""
            suf = "** (Selected)" if w == best_window else ""
            f.write(f"- {pre}{w} Days{pre}: {selected[w]:.4f}{suf}\n")
        f.write("\n")

        f.write("## 2. Optimal Roster Cadence\n")
        avg_top3 = np.mean([m['Total_Value'] for _, m in top3]) if top3 else 0.0
        f.write(f"Based on the Top 3 Teams (Average Value: {avg_top3:.1f}):\n")
        f.write(f"- **Optimal Churn Rate**: {optimal_churn:.1f} adds per week\n")
        f.write(f"- **Target Hold Time (Drops)**: {optimal_hold:.1f} days\n\n")
        f.write("### Member Breakdown (vs Optimal)\n")
        f.write("| Team | Total Value | Adds/Week | vs Optimal Churn | Avg Hold | Median Hold |\n")
        f.write("|---|---|---|---|---|---|\n")
        for t, m in ranked:
            if t not in metrics:
                continue
            f.write(f"| {t} | {m['Total_Value']:.1f} | {m['Adds_Per_Week']:.1f} | "
                    f"{m['Churn_Diff']:+.1f} | {m['Avg_Hold_Days']:.1f}d | {m['Median_Hold_Days']:.1f}d |\n")

        # Visualizations
        f.write("\n## Visualizations\n\n")
        display_windows = [w for w in sorted(valid_corrs)]
        f.write("### Evaluation Window Sensitivity\n")
        f.write("The curve shows the predictive power of different lookback windows.\n\n")
        f.write("```mermaid\nxychart-beta\n")
        f.write("    title \"Predictive Power vs Lookback Window\"\n")
        f.write(f"    x-axis \"Days\" [{', '.join(map(str, display_windows))}]\n")
        min_y = min(valid_corrs.values()) * 0.95
        max_y = max(valid_corrs.values()) * 1.05
        f.write(f"    y-axis \"Correlation\" {min_y:.3f} --> {max_y:.3f}\n")
        f.write(f"    line [{', '.join(f'{valid_corrs[w]:.4f}' for w in display_windows)}]\n")
        f.write("```\n\n")

        f.write("### Manager Style: Patience vs. Value\n\n")
        f.write("```mermaid\nquadrantChart\n")
        f.write("    title \"Roster Management Style\"\n")
        f.write("    x-axis \"Patience (Avg Hold Time)\" --> \"Stubborness\"\n")
        f.write("    y-axis \"Low Value\" --> \"High Value\"\n")
        f.write("    quadrant-1 \"Diamond Hands (High Value)\"\n")
        f.write("    quadrant-2 \"Churn & Burn (High Value)\"\n")
        f.write("    quadrant-3 \"Panic Dropper (Low Value)\"\n")
        f.write("    quadrant-4 \"Sleeping at Wheel (Low Value)\"\n")
        holds = [m['Avg_Hold_Days'] for m in metrics.values()]
        vals = [m['Total_Value'] for m in metrics.values()]
        max_hold, min_hold = max(holds), min(holds)
        max_val, min_val = max(vals), min(vals)
        for t, m in metrics.items():
            nx = (m['Avg_Hold_Days'] - min_hold) / (max_hold - min_hold) if max_hold > min_hold else 0.5
            ny = (m['Total_Value'] - min_val) / (max_val - min_val) if max_val > min_val else 0.5
            f.write(f"    {t}: [{0.05 + nx * 0.9:.2f}, {0.05 + ny * 0.9:.2f}]\n")
        f.write("```\n")

    print(f"Report saved to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
