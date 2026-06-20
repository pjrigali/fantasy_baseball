"""
compare_mlb_boxscore.py
========================
Description: Compares {year}_mlb_stats_daily.csv against {year}_mlb_stats_boxscore.csv
             for a given date and team. Reports players only in one source, players in
             both, and any stat-level differences.

Source Data: data-lake/01_Bronze/fantasy_baseball/{year}_mlb_stats_daily.csv
             data-lake/01_Bronze/fantasy_baseball/{year}_mlb_stats_boxscore.csv

Outputs: Printed comparison report to stdout.
"""

import csv
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

STAT_COLS = [
    'G', 'AB', 'R', 'H', '2B', '3B', 'HR', 'RBI', 'SB', 'CS', 'B_BB', 'SO', 'HBP', 'SF', 'TB',
    'GS', 'W', 'L', 'SV', 'HLD', 'SVHD', 'OUTS', 'P_H', 'P_R', 'ER', 'P_HR', 'P_BB', 'K', 'QS',
]


def load(path, date_filter, team_filter):
    rows = {}
    with open(path, encoding='utf-8') as f:
        for r in csv.DictReader(f):
            if r['date'] == date_filter and r['team_name'] == team_filter:
                rows[(r['player_name'], r['b_or_p'])] = r
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True, help='YYYY-MM-DD')
    parser.add_argument('--team', default='Chicago Cubs')
    parser.add_argument('--year', type=int, default=2026)
    args = parser.parse_args()

    daily_path    = os.path.join(mp.DATA_PATH, f'{args.year}_mlb_stats_daily.csv')
    boxscore_path = os.path.join(mp.DATA_PATH, f'{args.year}_mlb_stats_boxscore.csv')

    daily    = load(daily_path,    args.date, args.team)
    boxscore = load(boxscore_path, args.date, args.team)

    all_keys      = sorted(set(daily) | set(boxscore))
    only_daily    = [k for k in all_keys if k in daily    and k not in boxscore]
    only_boxscore = [k for k in all_keys if k in boxscore and k not in daily]
    in_both       = [k for k in all_keys if k in daily    and k in boxscore]

    print(f'{args.team}  |  {args.date}')
    print(f'  daily    rows : {len(daily)}')
    print(f'  boxscore rows : {len(boxscore)}')
    print()

    print(f'Only in daily ({len(only_daily)}):')
    for k in only_daily:
        print(f'  {k[1]:8s}  {k[0]}')

    print()
    print(f'Only in boxscore ({len(only_boxscore)}):')
    for k in only_boxscore:
        r = boxscore[k]
        print(f'  {k[1]:8s}  {k[0]}  did_play={r.get("did_play")}')

    print()
    print(f'In both ({len(in_both)}) — stat diffs:')
    diffs_found = False
    for k in in_both:
        d, b = daily[k], boxscore[k]
        mismatches = []
        for col in STAT_COLS:
            dv = d.get(col, '') or '0'
            bv = b.get(col, '') or '0'
            try:
                if float(dv) != float(bv):
                    mismatches.append(f'{col}: daily={dv} box={bv}')
            except ValueError:
                if dv != bv:
                    mismatches.append(f'{col}: daily={dv!r} box={bv!r}')
        if mismatches:
            diffs_found = True
            sep = ' | '
            print(f'  {k[1]:8s}  {k[0]}: {sep.join(mismatches)}')

    if not diffs_found:
        print('  No stat diffs — all shared players match exactly.')


if __name__ == '__main__':
    main()
