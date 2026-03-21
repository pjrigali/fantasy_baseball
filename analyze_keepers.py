import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import fantasy_baseball.mlb_processing as mp

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════════════════════════════════════════
YEAR = 2025
DRAFT_YEAR = 2026
MY_TEAM_ID = 2  # Datalickmyballs (Peter Rigali)
NUM_KEEPERS = 5

# Keeper costs: player name -> round it costs to keep them
MY_KEEPERS = {
    'Logan Webb': 13,
    'Bryce Harper': 4,
    'Cody Bellinger': 18,
    'Manny Machado': 2,
    'Jazz Chisholm Jr.': 11,
}

# PA/IP thresholds for 2025 Z-score inclusion
MIN_PA = 200
MIN_IP = 50

# Blend: 40% backward (2025 actuals) + 60% forward (2026 projections)
PROJECTION_WEIGHT = 0.60
DISCOUNT_NO_PROJECTION = 0.70  # Penalty for players with no 2026 projection

# League categories (5x5 H2H)
BATTING_CATS = ['R', 'HR', 'RBI', 'SB', 'OPS']
PITCHING_CATS = ['ERA', 'WHIP', 'K/9', 'QS', 'SVHD']
PITCHING_LOWER_BETTER = ['ERA', 'WHIP']


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════
def parse_projection_name(raw):
    """'Shohei Ohtani (LAD - SP,DH)' -> 'Shohei Ohtani'"""
    return raw.split('(')[0].strip() if '(' in str(raw) else str(raw).strip()


def calculate_z_scores(df, categories, ascending_cats):
    """Z-score each category; invert for lower-is-better stats. Returns df with Total_Z."""
    out = df.copy()
    z_cols = []
    for cat in categories:
        z_col = f"z_{cat}"
        z_cols.append(z_col)
        if cat not in out.columns:
            out[z_col] = 0.0
            continue
        mean, std = out[cat].mean(), out[cat].std()
        out[z_col] = ((out[cat] - mean) / std) if std > 0 else 0.0
        if cat in ascending_cats:
            out[z_col] *= -1
    out['Total_Z'] = out[z_cols].sum(axis=1)
    return out


def fuzzy_match(name, lookup):
    """Try exact, then strip suffixes, then case-insensitive."""
    if name in lookup:
        return lookup[name]
    # Normalize Jr/Sr
    variants = [
        name.replace(' Jr.', '').replace(' Sr.', '').strip(),
        name.replace(' Jr.', ' Jr').strip(),
        name + ' Jr.',
        name.rstrip('.'),
    ]
    for v in variants:
        if v in lookup:
            return lookup[v]
    # Case insensitive
    name_lower = name.lower().replace(' jr.', '').replace(' jr', '').strip()
    for k, val in lookup.items():
        k_clean = k.lower().replace(' jr.', '').replace(' jr', '').strip()
        if k_clean == name_lower:
            return val
    return None


def adp_to_round(adp_rank, num_teams=10):
    """Convert ADP rank to draft round."""
    if adp_rank <= 0 or pd.isna(adp_rank):
        return 99
    return int((adp_rank - 1) // num_teams) + 1


# ═══════════════════════════════════════════════════════════════════════════════
# Data Loading
# ═══════════════════════════════════════════════════════════════════════════════
def load_2025_stats():
    """Load and aggregate ESPN daily stats into season totals per player."""
    path = os.path.join(mp.DATA_PATH, 'stats_espn_daily_2025.csv')
    if not os.path.exists(path):
        print(f"ERROR: {path} not found"); return None

    print(f"Loading 2025 stats from {os.path.basename(path)}...")
    df = pd.read_csv(path)

    # Counting stats to sum
    sum_cols = ['R', 'HR', 'RBI', 'SB', 'H', 'AB', 'B_BB', 'HBP', 'SF',
                'TB', 'PA', 'ER', 'OUTS', 'P_BB', 'P_H', 'K', 'QS', 'SVHD']
    for c in sum_cols:
        if c not in df.columns:
            df[c] = 0

    agg = {
        'playerName': 'first',
        'teamId': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[-1],
        'team_abbrev': 'last',
        'b_or_p': lambda x: x.mode().iloc[0] if not x.mode().empty else x.iloc[0],
    }
    for c in sum_cols:
        agg[c] = 'sum'

    stats = df.groupby('playerId').agg(agg)

    # Recalculate rate stats from season totals
    stats['OBP'] = (stats['H'] + stats['B_BB'] + stats['HBP']) / stats['PA'].replace(0, np.nan)
    stats['SLG'] = stats['TB'] / stats['AB'].replace(0, np.nan)
    stats['OPS'] = stats['OBP'].fillna(0) + stats['SLG'].fillna(0)
    stats['IP']  = stats['OUTS'] / 3.0
    stats['ERA'] = (stats['ER'] * 9) / stats['IP'].replace(0, np.nan)
    stats['WHIP'] = (stats['P_BB'] + stats['P_H']) / stats['IP'].replace(0, np.nan)
    stats['K/9'] = (stats['K'] * 9) / stats['IP'].replace(0, np.nan)
    stats = stats.replace([np.inf, -np.inf], np.nan).fillna(0)
    return stats


def load_current_rosters():
    """Load the most recent ESPN roster snapshot."""
    path = os.path.join(mp.DATA_PATH, 'roster_espn_season_2025.csv')
    if not os.path.exists(path):
        print("WARNING: No current roster file found"); return None
    df = pd.read_csv(path)
    print(f"Loaded {len(df)} roster entries (snapshot: {df['date'].iloc[0]})")
    return df


def load_team_map():
    """team_id -> {name, abbrev, owner}"""
    path = os.path.join(mp.DATA_PATH, 'teams_espn_season_2025.csv')
    if not os.path.exists(path):
        return {}
    tdf = pd.read_csv(path).sort_values('date')  # latest row wins
    mapping = {}
    for _, r in tdf.iterrows():
        mapping[int(r['team_id'])] = {
            'name': r['team_name'], 'abbrev': r['team_abbrev'],
            'owner': r.get('team_owner_display_name', ''),
        }
    return mapping


def load_projections():
    """Load 2026 batter + pitcher projections keyed by clean player name."""
    proj = {}
    bp = os.path.join(mp.DATA_PATH, f'player_batter_projections_{DRAFT_YEAR}.csv')
    if os.path.exists(bp):
        bdf = pd.read_csv(bp)
        for _, r in bdf.iterrows():
            name = parse_projection_name(r['Player'])
            proj[name] = {
                'type': 'batter',
                'R': float(r.get('R', 0)), 'HR': float(r.get('HR', 0)),
                'RBI': float(r.get('RBI', 0)), 'SB': float(r.get('SB', 0)),
                'OPS': float(r.get('OPS', 0)),
            }
    pp = os.path.join(mp.DATA_PATH, f'player_pitcher_projections_{DRAFT_YEAR}.csv')
    if os.path.exists(pp):
        pdf = pd.read_csv(pp)
        for _, r in pdf.iterrows():
            name = parse_projection_name(r['Player'])
            ip = float(r.get('IP', 0))
            proj[name] = {
                'type': 'pitcher',
                'ERA': float(r.get('ERA', 0)), 'WHIP': float(r.get('WHIP', 0)),
                'K/9': round((float(r.get('K', 0)) * 9) / ip, 2) if ip > 0 else 0,
                'QS': 0, 'SVHD': float(r.get('SV', 0)),
            }
    return proj


def load_adp():
    """ADP lookup keyed by clean player name."""
    path = os.path.join(mp.DATA_PATH, f'overall_ADP_{DRAFT_YEAR}.csv')
    if not os.path.exists(path):
        return {}
    adf = pd.read_csv(path)
    adp = {}
    for _, r in adf.iterrows():
        name = parse_projection_name(str(r.get('Player (Team)', '')))
        adp[name] = {'rank': int(r.get('Rank', 999)), 'avg': float(r.get('AVG', 999))}
    return adp


def load_draft_costs():
    """player_id (str) -> round drafted in 2025 (proxy for keeper cost)."""
    path = os.path.join(mp.DATA_PATH, 'draft_results_espn_2025.csv')
    if not os.path.exists(path):
        return {}
    ddf = pd.read_csv(path)
    return {str(r['player_id']): int(r['round']) for _, r in ddf.iterrows()}


def load_draft_order():
    """team_name -> first-round pick number."""
    path = os.path.join(mp.DATA_PATH, 'draft_order_2026.csv')
    if not os.path.exists(path):
        return {}
    odf = pd.read_csv(path)
    r1 = odf[odf['round'] == 1]
    return {r['team_name'].strip(): int(r['round_pick']) for _, r in r1.iterrows()}


# ═══════════════════════════════════════════════════════════════════════════════
# Main Analysis
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print("=" * 72)
    print("  FANTASY BASEBALL KEEPER ANALYSIS — 2026 DRAFT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 72)

    # ── 1. Load Data ───────────────────────────────────────────────────
    stats = load_2025_stats()
    if stats is None:
        return
    rosters = load_current_rosters()
    team_map = load_team_map()
    projections = load_projections()
    adp_data = load_adp()
    draft_costs = load_draft_costs()
    draft_order = load_draft_order()
    num_teams = len(team_map) if team_map else 10

    print(f"\n  {len(stats)} players w/ 2025 stats | {len(projections)} projections "
          f"| {len(adp_data)} ADP entries | {len(draft_costs)} draft costs")

    # ── 2. Cross-reference Current Rosters ─────────────────────────────
    if rosters is not None:
        roster_lookup = {}  # pid_str -> {team_id, name, position, acq}
        for _, r in rosters.iterrows():
            pid = str(r['player_id'])
            roster_lookup[pid] = {
                'team_id': int(r['team_id']),
                'name': r['player_name'],
                'position': r.get('player_position', ''),
                'acq': r.get('player_acquisition_type', ''),
            }

        # Update team assignment to CURRENT roster
        for pid in stats.index:
            info = roster_lookup.get(str(pid))
            if info:
                stats.at[pid, 'teamId'] = info['team_id']

        # Add rostered players missing from 2025 stats (injured / new)
        for pid_str, info in roster_lookup.items():
            pid_int = int(pid_str) if pid_str.isdigit() else pid_str
            if pid_int not in stats.index:
                new = pd.Series(0, index=stats.columns, dtype=object)
                new['playerName'] = info['name']
                new['teamId'] = info['team_id']
                new['team_abbrev'] = team_map.get(info['team_id'], {}).get('abbrev', '')
                new['b_or_p'] = 'pitcher' if info['position'] in ('SP', 'RP', 'P') else 'batter'
                stats.loc[pid_int] = new

        # Filter to only currently rostered players
        rostered_ids = {int(p) if p.isdigit() else p for p in roster_lookup}
        stats = stats[stats.index.isin(rostered_ids)]
        print(f"  Filtered to {len(stats)} currently rostered players")

    # ── 3. Calculate 2025 Z-Scores ─────────────────────────────────────
    batters = stats[(stats['b_or_p'] == 'batter') & (stats['PA'] >= MIN_PA)].copy()
    pitchers = stats[(stats['b_or_p'] == 'pitcher') & (stats['IP'] >= MIN_IP)].copy()
    bat_below = stats[(stats['b_or_p'] == 'batter') & (stats['PA'] < MIN_PA)].copy()
    pit_below = stats[(stats['b_or_p'] == 'pitcher') & (stats['IP'] < MIN_IP)].copy()

    batters_z = calculate_z_scores(batters, BATTING_CATS, [])
    pitchers_z = calculate_z_scores(pitchers, PITCHING_CATS, PITCHING_LOWER_BETTER)
    for d in [bat_below, pit_below]:
        d['Total_Z'] = 0.0

    all_players = pd.concat([batters_z, pitchers_z, bat_below, pit_below])
    all_players.rename(columns={'Total_Z': 'Z_2025'}, inplace=True)

    # ── 4. Blend 2026 Projections ──────────────────────────────────────
    print("\n  Blending 2026 projections...")
    all_players['proj_Z'] = 0.0
    all_players['has_proj'] = False

    # Build projection Z-scores from projection pool
    batter_proj_list, pitcher_proj_list = [], []
    for idx, row in all_players.iterrows():
        proj = fuzzy_match(str(row['playerName']), projections)
        if proj:
            all_players.at[idx, 'has_proj'] = True
            entry = proj.copy()
            entry['_idx'] = idx
            (batter_proj_list if proj['type'] == 'batter' else pitcher_proj_list).append(entry)

    # Z-score batter projections as a group
    if batter_proj_list:
        bpdf = pd.DataFrame(batter_proj_list)
        for cat in BATTING_CATS:
            if cat in bpdf.columns:
                m, s = bpdf[cat].mean(), bpdf[cat].std()
                bpdf[f'z_{cat}'] = ((bpdf[cat] - m) / s) if s > 0 else 0.0
            else:
                bpdf[f'z_{cat}'] = 0.0
        bpdf['_pz'] = sum(bpdf[f'z_{c}'] for c in BATTING_CATS)
        for _, r in bpdf.iterrows():
            all_players.at[r['_idx'], 'proj_Z'] = r['_pz']

    # Z-score pitcher projections as a group
    if pitcher_proj_list:
        ppdf = pd.DataFrame(pitcher_proj_list)
        for cat in PITCHING_CATS:
            if cat in ppdf.columns:
                m, s = ppdf[cat].mean(), ppdf[cat].std()
                ppdf[f'z_{cat}'] = ((ppdf[cat] - m) / s) if s > 0 else 0.0
                if cat in PITCHING_LOWER_BETTER:
                    ppdf[f'z_{cat}'] *= -1
            else:
                ppdf[f'z_{cat}'] = 0.0
        ppdf['_pz'] = sum(ppdf[f'z_{c}'] for c in PITCHING_CATS)
        for _, r in ppdf.iterrows():
            all_players.at[r['_idx'], 'proj_Z'] = r['_pz']

    # Blended Z-score
    w = PROJECTION_WEIGHT
    all_players['Blend_Z'] = (1 - w) * all_players['Z_2025'] + w * all_players['proj_Z']
    # Discount players with no projection
    no_proj = ~all_players['has_proj']
    all_players.loc[no_proj, 'Blend_Z'] = all_players.loc[no_proj, 'Z_2025'] * DISCOUNT_NO_PROJECTION

    # ── 5. Add ADP + Keeper Cost + Surplus ─────────────────────────────
    print("  Calculating ADP surplus values...")
    all_players['ADP_Rank'] = 999.0
    all_players['ADP_Round'] = 99
    all_players['Keeper_Cost'] = 99
    all_players['Surplus'] = 0

    for idx, row in all_players.iterrows():
        name = str(row['playerName'])

        # ADP
        adp = fuzzy_match(name, adp_data)
        if adp:
            all_players.at[idx, 'ADP_Rank'] = adp['avg']
            all_players.at[idx, 'ADP_Round'] = adp_to_round(adp['rank'], num_teams)

        # Keeper cost (draft round from 2025)
        pid_str = str(idx)
        if pid_str in draft_costs:
            all_players.at[idx, 'Keeper_Cost'] = draft_costs[pid_str]

        # Override with user-provided keeper costs
        matched_cost = fuzzy_match(name, MY_KEEPERS)
        if matched_cost is not None:
            all_players.at[idx, 'Keeper_Cost'] = matched_cost

    all_players['Surplus'] = all_players['Keeper_Cost'] - all_players['ADP_Round']

    # ── 6. Generate Report ─────────────────────────────────────────────
    lines = []
    lines.append("=" * 72)
    lines.append("  KEEPER ANALYSIS — 2026 DRAFT")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"  Blend: {int((1-w)*100)}% 2025 Actuals + {int(w*100)}% 2026 Projections")
    lines.append(f"  5x5 H2H: R/HR/RBI/SB/OPS × ERA/WHIP/K9/QS/SVHD")
    lines.append("=" * 72)

    all_results = []
    teams_sorted = sorted(all_players['teamId'].unique())

    for tid in teams_sorted:
        tid = int(tid)
        info = team_map.get(tid, {'name': f'Team {tid}', 'abbrev': str(tid), 'owner': ''})
        team_df = all_players[all_players['teamId'] == tid].copy()
        if team_df.empty:
            continue
        team_df = team_df.sort_values('Blend_Z', ascending=False)

        # Draft order lookup
        pick_str = ""
        for dname, dpick in draft_order.items():
            # Fuzzy match team name
            if dname.strip().lower() in info['name'].lower() or info['name'].lower() in dname.strip().lower():
                pick_str = f"  Round 1 Pick: #{dpick}"
                break

        is_mine = (tid == MY_TEAM_ID)
        marker = " ★ YOUR TEAM" if is_mine else ""

        lines.append("")
        lines.append("─" * 72)
        lines.append(f"  {info['name']} ({info['owner']}){marker}")
        if pick_str:
            lines.append(pick_str)
        lines.append("─" * 72)

        hdr = f"  {'#':<3} {'Player':<24} {'Pos':<4} {'2025Z':>6} {'ProjZ':>6} {'Blend':>6} {'ADP':>5} {'Cost':>5} {'Surplus':>8}  {'Note'}"
        lines.append(hdr)
        sep = f"  {'─'*3} {'─'*24} {'─'*4} {'─'*6} {'─'*6} {'─'*6} {'─'*5} {'─'*5} {'─'*8}  {'─'*15}"
        lines.append(sep)

        # Show top 8 (top 5 marked with ►)
        top5_bat, top5_pit = 0, 0
        display_count = min(8, len(team_df))
        for rank, (idx, row) in enumerate(team_df.head(display_count).iterrows(), 1):
            pos = 'BAT' if row['b_or_p'] == 'batter' else 'PIT'
            pname = str(row['playerName'])[:23]

            z25 = f"{row['Z_2025']:+.1f}" if row['Z_2025'] != 0 else "  n/a"
            pz  = f"{row['proj_Z']:+.1f}" if row['has_proj'] else "  n/a"
            bz  = f"{row['Blend_Z']:+.1f}"

            adp_r = f"R{int(row['ADP_Round'])}" if row['ADP_Round'] < 99 else "  --"
            cost  = f"R{int(row['Keeper_Cost'])}" if row['Keeper_Cost'] < 99 else "  --"

            surplus_val = row['Surplus']
            if row['ADP_Round'] < 99 and row['Keeper_Cost'] < 99:
                surplus_str = f"{surplus_val:+.0f} rnds"
            else:
                surplus_str = "     --"

            note = ""
            if rank <= NUM_KEEPERS:
                if pos == 'BAT': top5_bat += 1
                else: top5_pit += 1
                if surplus_val >= 5:
                    note = "← STRONG KEEP"
                elif surplus_val >= 2:
                    note = "← GOOD KEEP"
                elif row['ADP_Round'] < 99 and surplus_val <= 0:
                    note = "← NO SURPLUS"

            icon = "►" if rank <= NUM_KEEPERS else " "
            lines.append(f"  {icon}{rank:<2} {pname:<24} {pos:<4} {z25:>6} {pz:>6} {bz:>6} {adp_r:>5} {cost:>5} {surplus_str:>8}  {note}")

        # Save ALL players to CSV (not just displayed top 8)
        for rank, (idx, row) in enumerate(team_df.iterrows(), 1):
            all_results.append({
                'Team_ID': tid, 'Team': info['name'], 'Owner': info['owner'],
                'Rank': rank, 'Player': row['playerName'], 'Type': row['b_or_p'],
                'Z_2025': round(row['Z_2025'], 2),
                'Proj_Z': round(row['proj_Z'], 2),
                'Blend_Z': round(row['Blend_Z'], 2),
                'ADP_Rank': row['ADP_Rank'],
                'ADP_Round': int(row['ADP_Round']),
                'Keeper_Cost': int(row['Keeper_Cost']),
                'Surplus_Rounds': int(row['Surplus']),
            })

        # Balance warning
        if top5_bat >= NUM_KEEPERS:
            lines.append(f"\n  ⚠️  Balance: {top5_bat}B / {top5_pit}P — consider swapping a batter for a pitcher")
        elif top5_pit >= NUM_KEEPERS - 1:
            lines.append(f"\n  ⚠️  Balance: {top5_bat}B / {top5_pit}P — heavy on pitching")
        else:
            lines.append(f"\n  ✓ Balance: {top5_bat}B / {top5_pit}P")

    # ── 7. Save Outputs ───────────────────────────────────────────────
    report = '\n'.join(lines)
    print(report)

    # CSV
    results_df = pd.DataFrame(all_results)
    csv_path = os.path.join(mp.DATA_PATH, 'projected_keepers_2026.csv')
    results_df.to_csv(csv_path, index=False)
    print(f"\n📊 CSV saved: {csv_path}")

    # Text report
    report_path = os.path.join(mp.DATA_PATH, 'keeper_report_2026.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"📋 Report saved: {report_path}")


if __name__ == "__main__":
    main()
