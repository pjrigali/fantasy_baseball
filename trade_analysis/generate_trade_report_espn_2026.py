"""
Trade Finder Report — ESPN Fantasy Baseball 2026

Description:
    Human-readable wrapper over analyze_trade_finder_espn_2026.csv.
    For each mutually beneficial trade, prints a formatted block showing:
      - Which player each team gives and receives
      - Key projected stats for each player
      - Per-category rank changes for both teams (with up/down indicators)
      - A plain-English summary of what each side gains
    Optionally filters by team name and limits the number of trades shown.

Source Data:
    data-lake/01_Bronze/fantasy_baseball/analyze_trade_finder_espn_2026.csv

Outputs:
    stdout  (pipe to a file to save)

Usage:
    python generate_trade_report_espn_2026.py                  # top 25 trades
    python generate_trade_report_espn_2026.py --top 10
    python generate_trade_report_espn_2026.py --team "Datalickmyballs"
    python generate_trade_report_espn_2026.py --team "All Rise" --top 5
"""

import csv
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ─── Config ───────────────────────────────────────────────────────────────────

DEFAULT_TOP   = 25
ALL_CATS      = ['R', 'HR', 'RBI', 'SB', 'OPS', 'K/9', 'QS', 'SVHD', 'ERA', 'WHIP']
LOWER_BETTER  = {'ERA', 'WHIP'}

BATTER_STATS  = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHER_STATS = ['K/9', 'QS', 'SVHD', 'ERA', 'WHIP']


# ─── Path resolver ────────────────────────────────────────────────────────────

def _csv_path(year):
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(root, 'data-lake', '01_Bronze', 'fantasy_baseball',
                     f'analyze_trade_finder_espn_{year}.csv')
    if os.path.isfile(p):
        return p
    raise FileNotFoundError(f"Trade finder CSV not found: {p}\n"
                             "Run analyze_trade_finder_espn_*.py first.")


# ─── Rank-change indicator ────────────────────────────────────────────────────

def rank_indicator(cat, before, after):
    """
    Return a display string showing rank movement.
    Rank 1 = best, so a lower number after = improvement.
    For ERA/WHIP (lower is better) the logic is the same — rank 1 still = best.
    """
    delta = int(before) - int(after)   # positive = moved up in standings
    if delta > 0:
        return f"{before:>2} -> {after:<2}  [+{delta} UP  ]"
    elif delta < 0:
        return f"{before:>2} -> {after:<2}  [{delta} DOWN]"
    else:
        return f"{before:>2} -> {after:<2}  [  same  ]"


def rank_symbol(before, after):
    delta = int(before) - int(after)
    if delta > 0:
        return "(+)"
    elif delta < 0:
        return "(-)"
    return "( )"


# ─── Player stat summary line ─────────────────────────────────────────────────

def player_stat_line(row, prefix, ptype):
    """Build a compact projected-stats string for one player."""
    stats = BATTER_STATS if ptype == 'batter' else PITCHER_STATS
    parts = []
    for s in stats:
        val = row.get(f'{prefix}_proj_{s}', '')
        if val == '':
            continue
        try:
            f = float(val)
            if s == 'OPS' or s == 'ERA' or s == 'WHIP':
                parts.append(f"{s}:{f:.3f}")
            elif s == 'K/9':
                parts.append(f"K/9:{f:.1f}")
            else:
                parts.append(f"{s}:{int(round(f))}")
        except (ValueError, TypeError):
            pass
    return '  '.join(parts)


# ─── Category change summary ──────────────────────────────────────────────────

def cat_summary_line(row, side, ptype):
    """
    One-line plain English: 'Gains R(8->6), HR(6->5)  |  Loses SB(3->5)'
    Only lists categories that actually changed.
    """
    gained, lost, neutral = [], [], []
    cats = BATTER_STATS if ptype == 'batter' else PITCHER_STATS
    for c in cats:
        before = int(row[f'{side}_{c}_rank_before'])
        after  = int(row[f'{side}_{c}_rank_after'])
        delta  = before - after   # positive = improved rank
        if delta > 0:
            gained.append(f"{c}({before}->{after})")
        elif delta < 0:
            lost.append(f"{c}({before}->{after})")
    parts = []
    if gained:
        parts.append("GAINS " + ", ".join(gained))
    if lost:
        parts.append("LOSES " + ", ".join(lost))
    return "  |  ".join(parts) if parts else "No change in relevant categories"


# ─── Format one trade ─────────────────────────────────────────────────────────

def format_trade(row, idx):
    team_a = row['team_a_name']
    team_b = row['team_b_name']
    gives_a = row['player_a_gives']
    gives_b = row['player_b_gives']
    ptype  = row['player_type']
    net_a  = int(row['a_net_cats'])
    net_b  = int(row['b_net_cats'])
    imp_a  = int(row['a_cats_improved'])
    wor_a  = int(row['a_cats_worsened'])
    imp_b  = int(row['b_cats_improved'])
    wor_b  = int(row['b_cats_worsened'])
    combo  = int(row['combined_net_cats'])
    src_a  = row.get('player_a_gives_source', '')
    src_b  = row.get('player_b_gives_source', '')

    width = 70
    sep   = "-" * width

    lines = []
    lines.append("")
    lines.append("=" * width)
    lines.append(f"  TRADE #{idx}   [{ptype.upper()} SWAP]   Combined net: +{combo} categories")
    lines.append(sep)

    # Who gives what
    lines.append(f"  {team_a:<33}  gives  {gives_a}")
    lines.append(f"  {team_b:<33}  gives  {gives_b}")

    # Projected stats
    stats_a = player_stat_line(row, 'a_gives', ptype)
    stats_b = player_stat_line(row, 'b_gives', ptype)
    src_tag_a = "(proj)" if src_a == 'proj' else "(ytd-scaled)"
    src_tag_b = "(proj)" if src_b == 'proj' else "(ytd-scaled)"
    lines.append("")
    lines.append(f"  {gives_a} {src_tag_a}")
    lines.append(f"    {stats_a if stats_a else 'no projection data'}")
    lines.append(f"  {gives_b} {src_tag_b}")
    lines.append(f"    {stats_b if stats_b else 'no projection data'}")

    # Category rank changes — two-column layout
    lines.append("")
    lines.append(f"  {'CATEGORY':<8}  "
                 f"{'  ' + team_a[:24]:<28}  "
                 f"{'  ' + team_b[:24]:<28}")
    lines.append(f"  {'':<8}  {'(gives ' + gives_a.split()[0] + ')':<28}  "
                 f"{'(gives ' + gives_b.split()[0] + ')':<28}")
    lines.append(f"  {'-'*8}  {'-'*28}  {'-'*28}")

    relevant = BATTER_STATS if ptype == 'batter' else PITCHER_STATS
    for c in relevant:
        ba = row[f'a_{c}_rank_before']
        aa = row[f'a_{c}_rank_after']
        bb = row[f'b_{c}_rank_before']
        ab = row[f'b_{c}_rank_after']
        sym_a = rank_symbol(ba, aa)
        sym_b = rank_symbol(bb, ab)
        col_a = f"rank {ba:>2} -> {aa:<2}  {sym_a}"
        col_b = f"rank {bb:>2} -> {ab:<2}  {sym_b}"
        lines.append(f"  {c:<8}  {col_a:<28}  {col_b:<28}")

    # Verdict
    lines.append("")
    lines.append(f"  {team_a}: net +{net_a}  "
                 f"({imp_a} improved, {wor_a} worsened)")
    lines.append(f"    {cat_summary_line(row, 'a', ptype)}")
    lines.append(f"  {team_b}: net +{net_b}  "
                 f"({imp_b} improved, {wor_b} worsened)")
    lines.append(f"    {cat_summary_line(row, 'b', ptype)}")

    return "\n".join(lines)


# ─── Per-team summary ─────────────────────────────────────────────────────────

def team_summary(rows):
    """Count how many mutually beneficial trades each team appears in."""
    from collections import defaultdict, Counter
    counts  = Counter()
    partners = defaultdict(set)
    for r in rows:
        a, b = r['team_a_name'], r['team_b_name']
        counts[a] += 1
        counts[b] += 1
        partners[a].add(b)
        partners[b].add(a)

    lines = []
    lines.append("")
    lines.append("=" * 70)
    lines.append("  TRADE OPPORTUNITIES BY TEAM")
    lines.append("-" * 70)
    for team, n in counts.most_common():
        plist = ", ".join(sorted(partners[team]))
        lines.append(f"  {team:<32}  {n:>3} trades  (with: {plist})")
    return "\n".join(lines)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    from datetime import datetime
    # ── Parse simple args ──────────────────────────────────────────────────────
    args = sys.argv[1:]
    filter_team = None
    top_n = DEFAULT_TOP
    year = datetime.now().year

    i = 0
    while i < len(args):
        if args[i] == '--team' and i + 1 < len(args):
            filter_team = args[i + 1].lower()
            i += 2
        elif args[i] == '--top' and i + 1 < len(args):
            top_n = int(args[i + 1])
            i += 2
        elif args[i] == '--year' and i + 1 < len(args):
            year = int(args[i + 1])
            i += 2
        else:
            i += 1

    # ── Load CSV ───────────────────────────────────────────────────────────────
    csv_path = _csv_path(year)
    with open(csv_path, encoding='utf-8') as f:
        all_rows = list(csv.DictReader(f))

    # ── Filter ─────────────────────────────────────────────────────────────────
    if filter_team:
        rows = [r for r in all_rows
                if filter_team in r['team_a_name'].lower()
                or filter_team in r['team_b_name'].lower()]
    else:
        rows = all_rows

    display_rows = rows[:top_n]

    # ── Header ─────────────────────────────────────────────────────────────────
    print("=" * 70)
    print(f"  MUTUALLY BENEFICIAL TRADE REPORT — {year} ESPN Fantasy Baseball")
    if filter_team:
        print(f"  Filter: teams containing '{filter_team}'")
    print(f"  Showing {len(display_rows)} of {len(rows)} trades "
          f"(sorted by combined net category gain)")
    print(f"  Rank scale: 1 = best in league, 10 = worst  |  (+) = rank improved")
    print("=" * 70)

    # ── Trades ─────────────────────────────────────────────────────────────────
    for idx, row in enumerate(display_rows, 1):
        print(format_trade(row, idx))

    # ── Team summary ───────────────────────────────────────────────────────────
    if not filter_team:
        print(team_summary(all_rows))

    print()


if __name__ == '__main__':
    main()
