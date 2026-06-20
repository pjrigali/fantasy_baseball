"""
Description: Evaluates weekly roster checkpoints for a target team by comparing each
             rostered player's trailing 28-day z-score value against available free agents.
             Flags players where a significantly better FA exists (value delta > 0.75).
             Identity (mlbam game-log id -> espn roster id) is resolved through the
             canonical player_map.csv via its mlbam_player_id <-> espn_player_id bridge.
Source Data: {YEAR}_mlb_stats_boxscore.csv, {YEAR}_espn_roster_history.csv, player_map.csv
Outputs:     fantasy_baseball/reports/roster_analysis_report_{YEAR}.md

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

# Configuration
SEASON = 2026
WINDOW = 28
TEAM_ABBREV = 'PJR'
VALUE_DELTA = 0.75

BASE_PATH = mp.DATA_PATH
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_DIR = os.path.join(SCRIPT_DIR, 'reports')
os.makedirs(REPORT_DIR, exist_ok=True)
OUTPUT_PATH = os.path.join(REPORT_DIR, f'roster_analysis_report_{SEASON}.md')

ROSTER_PATH = os.path.join(BASE_PATH, f'{SEASON}_espn_roster_history.csv')
STATS_PATH = os.path.join(BASE_PATH, f'{SEASON}_mlb_stats_boxscore.csv')
MAP_PATH = os.path.join(BASE_PATH, 'player_map.csv')

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


def main():
    print(f"Running Analysis for {SEASON}")
    print(f"Data Path: {BASE_PATH}")

    if not os.path.exists(ROSTER_PATH) or not os.path.exists(STATS_PATH):
        print(f"\n[WARNING] Data files for {SEASON} not found.")
        print(f"Expected:\n - {ROSTER_PATH}\n - {STATS_PATH}")
        print("Skipping analysis (likely pre-season).")
        sys.exit(0)

    print("Loading data...")
    roster_rows = read_csv(ROSTER_PATH)
    stats_rows = read_csv(STATS_PATH)
    map_rows = read_csv(MAP_PATH)

    # mlbam game-log id -> (espn_id, name) bridge from the canonical file
    mlbam_to_espn = {}
    for r in map_rows:
        mlbam = (r.get('mlbam_player_id') or '').strip()
        espn = (r.get('espn_player_id') or '').strip()
        if mlbam and espn:
            mlbam_to_espn[mlbam] = (espn, (r.get('espn_name') or r.get('mlb_name') or '').strip())

    # ── Parse stats; attach espn id; group rows by date ──────────────────────────
    rows_by_date = defaultdict(list)
    max_date = None
    for r in stats_rows:
        d = parse_date(r.get('date'))
        if d is None:
            continue
        mlbam = (r.get('player_id') or '').strip()
        bridge = mlbam_to_espn.get(mlbam)
        if not bridge:
            continue  # no espn mapping -> excluded (same as old how='left' + dropna on key)
        espn_id, name = bridge
        r['_date'] = d
        r['_espn_id'] = espn_id
        r['_name'] = name or (r.get('player_name') or '')
        rows_by_date[d].append(r)
        if max_date is None or d > max_date:
            max_date = d

    # ── Per-date z-score Daily_Value, aggregated to (date, espn_id) ───────────────
    print("Computing per-day z-score values...")
    # daily_value[(date, espn_id)] = summed value; name_of[espn_id] = name
    daily_value = defaultdict(float)
    name_of = {}
    for d, rows in rows_by_date.items():
        def zscores(values):
            arr = np.array(values, dtype=float)
            mean = arr.mean()
            std = arr.std(ddof=1) if len(arr) > 1 else 0.0
            std = std if std else 1.0
            return (arr - mean) / std

        n = len(rows)
        contrib = np.zeros(n)
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

    # ── 28-day rolling mean over the sorted distinct dates ───────────────────────
    print(f"Calculating {WINDOW}-day rolling value...")
    dates = sorted({d for (d, _) in daily_value})
    players = sorted({p for (_, p) in daily_value})
    date_idx = {d: i for i, d in enumerate(dates)}
    # matrix [date, player] of daily value (0-filled like the old pivot.fillna(0))
    mat = np.zeros((len(dates), len(players)))
    pcol = {p: j for j, p in enumerate(players)}
    for (d, p), v in daily_value.items():
        mat[date_idx[d], pcol[p]] = v

    # rolling mean: row i uses rows [i-WINDOW+1, i]; NaN until WINDOW rows available
    rolling = np.full(mat.shape, np.nan)
    csum = np.cumsum(mat, axis=0)
    for i in range(len(dates)):
        if i >= WINDOW - 1:
            window_sum = csum[i] - (csum[i - WINDOW] if i - WINDOW >= 0 else 0)
            rolling[i] = window_sum / WINDOW

    def rolling_value(d, espn_id):
        i = date_idx.get(d)
        j = pcol.get(espn_id)
        if i is None or j is None:
            return None
        v = rolling[i, j]
        return None if np.isnan(v) else float(v)

    # ── Parse roster history ─────────────────────────────────────────────────────
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
            'player_name': (r.get('player_name') or '').strip(),
            'start_date': sd, 'end_date': ed,
        })
        if season_start is None or sd < season_start:
            season_start = sd

    # ── Weekly Monday checkpoints ────────────────────────────────────────────────
    print("Analyzing Roster moves (Weekly Checkpoints)...")
    mondays = []
    if season_start and max_date:
        d = season_start + timedelta(days=(7 - season_start.weekday()) % 7)  # first Monday >= start
        while d <= max_date:
            mondays.append(d)
            d += timedelta(days=7)

    recommendations = []
    for check_date in mondays:
        active = [r for r in rosters if r['start_date'] <= check_date <= r['end_date']]
        pjr = [r for r in active if r['team_abbrev'] == TEAM_ABBREV]
        if not pjr:
            continue
        rostered_ids = {r['player_id'] for r in active}

        # FA pool: players with a rolling value this date, not rostered by anyone
        fa = []
        for p in players:
            if p in rostered_ids:
                continue
            rv = rolling_value(check_date, p)
            if rv is not None:
                fa.append((p, rv))
        fa.sort(key=lambda x: x[1], reverse=True)
        top_fas = fa[:20]

        for r in pjr:
            my_val = rolling_value(check_date, r['player_id'])
            if my_val is None:
                my_val = -999.0
            better = [(p, v) for (p, v) in top_fas if v > my_val + VALUE_DELTA]
            if better:
                opts = [f"{name_of.get(p, p)} ({v:.2f})" for p, v in better[:2]]
                recommendations.append({
                    'Date': check_date.strftime('%Y-%m-%d'),
                    'My_Player': r['player_name'],
                    'My_Value': f"{my_val:.2f}",
                    'Better_FA': ", ".join(opts),
                })

    # ── Report ───────────────────────────────────────────────────────────────────
    print("Generating report...")
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(f"# Roster Checkpoint Report for {TEAM_ABBREV}\n\n")
        f.write(f"**Evaluation Window:** {WINDOW} Days (Trailing)\n")
        f.write("**Methodology:** On every Monday, compared trailing 28-day performance of your roster vs. available Free Agents.\n")
        f.write(f"**Threshold:** FA Value must be > My Player Value + {VALUE_DELTA} Z-Score.\n\n")
        f.write("| Date | Drop Consideration | Value | Better Available Options (Value) |\n")
        f.write("|---|---|---|---|\n")
        if not recommendations:
            f.write("\nNo clear missed opportunities found based on the criteria.\n")
        for r in recommendations:
            f.write(f"| {r['Date']} | {r['My_Player']} | {r['My_Value']} | {r['Better_FA']} |\n")

    print(f"Report saved to {OUTPUT_PATH}")


if __name__ == '__main__':
    main()
