"""
Trade Summary Report — ESPN Fantasy Baseball 2026

Description:
    Reads 2026_local_trade_finder.csv and writes a markdown file
    with the top 5 mutually beneficial trades for each team.

Source Data:
    data-lake/01_Bronze/fantasy_baseball/2026_local_trade_finder.csv

Outputs:
    fantasy_baseball/reports/trade_summary_espn_2026_{DATE}.md
"""

import csv
import io
import os
import sys
from collections import defaultdict
from datetime import date

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

ALL_CATS     = ['R', 'HR', 'RBI', 'SB', 'OPS', 'K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
BATTER_STATS = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHER_STATS = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
TOP_N = 5


def _paths(year):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    csv_in = None
    for name in ('data-lake', 'data-lake'):
        p = os.path.join(root, name, '01_Bronze', 'fantasy_baseball',
                         f'{year}_local_trade_finder.csv')
        if os.path.isfile(p):
            csv_in = p
            break
    if not csv_in:
        csv_in = os.path.join(root, 'data-lake', '01_Bronze', 'fantasy_baseball',
                              f'{year}_local_trade_finder.csv')
    md_out  = os.path.join(script_dir, f'trade_summary_espn_{year}_{date.today()}.md')
    return csv_in, md_out


def flt(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def stat_snippet(row, prefix, ptype):
    """e.g. 'R:84  HR:27  RBI:88  SB:10  OPS:.850'"""
    stats = BATTER_STATS if ptype == 'batter' else PITCHER_STATS
    parts = []
    for s in stats:
        v = flt(row.get(f'{prefix}_proj_{s}', ''))
        if v is None:
            continue
        if s in ('OPS', 'ERA', 'WHIP'):
            parts.append(f"{s}:{v:.3f}")
        elif s == 'K/9':
            parts.append(f"K/9:{v:.1f}")
        else:
            parts.append(f"{s}:{int(round(v))}")
    return '  '.join(parts)


def gains_losses(row, side, ptype):
    """Returns (gains_str, losses_str) for the relevant category set."""
    stats = BATTER_STATS if ptype == 'batter' else PITCHER_STATS
    gained, lost = [], []
    for c in stats:
        before = int(row[f'{side}_{c}_rank_before'])
        after  = int(row[f'{side}_{c}_rank_after'])
        delta  = before - after
        if delta > 0:
            gained.append(f"{c} {before}→{after}")
        elif delta < 0:
            lost.append(f"{c} {before}→{after}")
    return ', '.join(gained), ', '.join(lost)


def team_trades(all_rows):
    """
    Return {team_name: {'balanced': [...], 'high_impact': [...]}} where each row
    is augmented with 'my_side', 'my_net', and 'opp_net'.

    balanced   — top TOP_N trades sorted to maximize mutual fairness:
                 primary: min(my_net, opp_net) desc (both sides gain as much as possible)
                 secondary: abs(my_net - opp_net) asc (minimize the gap between sides)
                 tertiary: combined_net_cats desc

    high_impact — top 2 trades by combined_net_cats, excluding any already in balanced.
    """
    buckets = defaultdict(list)
    for r in all_rows:
        r_a = dict(r, my_side='a',
                   my_net=int(r['a_net_cats']), opp_net=int(r['b_net_cats']),
                   my_gives=r['player_a_gives'], my_gets=r['player_b_gives'],
                   partner=r['team_b_name'])
        r_b = dict(r, my_side='b',
                   my_net=int(r['b_net_cats']), opp_net=int(r['a_net_cats']),
                   my_gives=r['player_b_gives'], my_gets=r['player_a_gives'],
                   partner=r['team_a_name'])
        buckets[r['team_a_name']].append(r_a)
        buckets[r['team_b_name']].append(r_b)

    result = {}
    for team, rows in buckets.items():
        balanced = sorted(rows, key=lambda r: (
            min(r['my_net'], r['opp_net']),           # higher = both sides gain more
            -abs(r['my_net'] - r['opp_net']),         # negative so smaller gap sorts first
            int(r['combined_net_cats']),
        ), reverse=True)[:TOP_N]

        bal_keys = {(r['my_gives'], r['my_gets'], r['partner']) for r in balanced}
        high_impact = [
            r for r in sorted(rows, key=lambda r: int(r['combined_net_cats']), reverse=True)
            if (r['my_gives'], r['my_gets'], r['partner']) not in bal_keys
        ][:2]

        result[team] = {'balanced': balanced, 'high_impact': high_impact}
    return result


def render_trade_block(r, idx):
    """Render one trade as markdown bullet lines."""
    ptype    = r['player_type']
    my_side  = r['my_side']
    opp_side = 'b' if my_side == 'a' else 'a'
    my_net   = r['my_net']
    opp_net  = int(r['b_net_cats'] if my_side == 'a' else r['a_net_cats'])
    combined = int(r['combined_net_cats'])

    my_gives  = r['my_gives']
    my_gets   = r['my_gets']
    partner   = r['partner']

    my_stats  = stat_snippet(r, f'{my_side}_gives', ptype)
    opp_stats = stat_snippet(r, f'{opp_side}_gives', ptype)

    my_gain, my_loss   = gains_losses(r, my_side, ptype)
    opp_gain, opp_loss = gains_losses(r, opp_side, ptype)

    lines = []
    lines.append(f"### {idx}. Give **{my_gives}**, get **{my_gets}** *(from {partner})*")
    lines.append(f"- **Type:** {ptype}  |  **Combined gain:** +{combined} categories")
    lines.append(f"- **{my_gives}** projections: {my_stats if my_stats else 'n/a'}")
    lines.append(f"- **{my_gets}** projections: {opp_stats if opp_stats else 'n/a'}")

    my_verdict = f"net **+{my_net}**"
    if my_gain:
        my_verdict += f" — gains {my_gain}"
    if my_loss:
        my_verdict += f" — loses {my_loss}"
    lines.append(f"- **Your outcome:** {my_verdict}")

    opp_verdict = f"net **+{opp_net}**"
    if opp_gain:
        opp_verdict += f" — gains {opp_gain}"
    if opp_loss:
        opp_verdict += f" — loses {opp_loss}"
    lines.append(f"- **{partner}'s outcome:** {opp_verdict}")

    return '\n'.join(lines)


def main():
    import argparse
    from datetime import datetime
    parser = argparse.ArgumentParser(description="Generate per-team mutually beneficial trade summary.")
    parser.add_argument('--year', type=int, default=datetime.now().year,
                        help='Season year (default: current calendar year).')
    args = parser.parse_args()
    year = args.year
    csv_path, md_path = _paths(year)

    with open(csv_path, encoding='utf-8') as f:
        all_rows = list(csv.DictReader(f))

    by_team = team_trades(all_rows)

    # Collect baseline ranks from the first appearance of each team in the CSV
    team_baseline = {}
    for r in all_rows:
        for side, tname in (('a', r['team_a_name']), ('b', r['team_b_name'])):
            if tname not in team_baseline:
                team_baseline[tname] = {c: int(r[f'{side}_{c}_rank_before']) for c in ALL_CATS}

    lines = []
    lines.append(f"# Mutually Beneficial Trade Summary — {year} ESPN Fantasy Baseball")
    lines.append(f"*Generated: {date.today()}  |  Source: {year}_local_trade_finder.csv*")
    lines.append(f"*Top {TOP_N} trades per team, sorted by net category gain for that team.*")
    lines.append("")
    lines.append("---")

    for team in sorted(by_team.keys()):
        team_data = by_team[team]
        balanced    = team_data['balanced']
        high_impact = team_data['high_impact']
        baseline = team_baseline.get(team, {})

        # Category profile header
        bat_profile = '  '.join(f"{c}({baseline.get(c,'?')})" for c in BATTER_STATS)
        pit_profile = '  '.join(f"{c}({baseline.get(c,'?')})" for c in PITCHER_STATS)

        lines.append("")
        lines.append(f"## {team}")
        lines.append(f"*Projected rank (1=best): {bat_profile}*")
        lines.append(f"*{' ' * 20}{pit_profile}*")
        lines.append("")

        lines.append("### Most Balanced Trades *(both sides benefit equally)*")
        lines.append("")
        if not balanced:
            lines.append("*No mutually beneficial trades found.*")
        else:
            for i, r in enumerate(balanced, 1):
                lines.append(render_trade_block(r, i))
                lines.append("")

        if high_impact:
            lines.append("### Highest Impact Trades *(largest combined category swing)*")
            lines.append("")
            for i, r in enumerate(high_impact, 1):
                lines.append(render_trade_block(r, i))
                lines.append("")

        lines.append("---")

    md_text = '\n'.join(lines)

    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)

    print(f"Report saved -> {md_path}")


if __name__ == '__main__':
    main()
