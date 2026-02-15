"""
Backfill the matchup_period column in daily_player_stats_2025.csv.

The ESPN API doesn't reliably return the scoring_period-to-matchup_period mapping
for completed seasons. Instead, we derive it from the league's weekly schedule:
 - 18 regular season matchup periods + 2 playoff matchup periods = 20 total
 - Each matchup period is ~1 week (Monday-to-Sunday)
 - ESPN scoring periods are 1-indexed days starting from the fantasy season start

The MLB 2025 regular season runs March 20 - Sept 28 (approx 193 days).
The fantasy scoring period 1 corresponds to Opening Day / league start.
With 167 total scoring periods and 20 matchup periods:
  - 18 regular season matchups of ~8 days each
  - 2 playoff matchups at the end
"""

import sys
import os
import pandas as pd
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fantasy_baseball.mlb_processing as mp


def build_matchup_map(total_scoring_periods=167, reg_season_matchups=18, playoff_matchups=2):
    """
    Build scoring_period->matchup_period mapping.

    Strategy:
    - Calculate days per regular matchup: floor(total_sp / total_matchups)
    - Distribute evenly, with any extra days added to the last regular season matchup
    - Playoff matchups split the remaining days

    Args:
        total_scoring_periods: Final scoring period (167 for 2025)
        reg_season_matchups: Number of regular season matchup periods (18)
        playoff_matchups: Number of playoff matchup periods (2)
    """
    total_matchups = reg_season_matchups + playoff_matchups  # 20
    days_per_matchup = total_scoring_periods // total_matchups  # 8
    remainder = total_scoring_periods % total_matchups  # 7

    mp_map = {}
    sp = 1

    for matchup in range(1, total_matchups + 1):
        # Base days for this matchup
        days = days_per_matchup
        # Distribute remainder across the first N matchups (1 extra day each)
        if matchup <= remainder:
            days += 1

        for _ in range(days):
            if sp <= total_scoring_periods:
                mp_map[sp] = matchup
                sp += 1

    return mp_map


def main():
    print("Setting up league connection...")
    config = mp.load_config("config.ini")
    league = mp.setup_league(config, year=2025)

    # Get key league info
    final_sp = 167
    reg_season = league.settings.reg_season_count  # 18
    total_matchups = 20  # 18 regular + 2 playoff

    print(f"League: reg_season_count={reg_season}, finalScoringPeriod={final_sp}, totalMatchups={total_matchups}")

    # Build the matchup map using even distribution
    print("\nBuilding matchup period mapping (even weekly distribution)...")
    matchup_map = build_matchup_map(
        total_scoring_periods=final_sp,
        reg_season_matchups=reg_season,
        playoff_matchups=total_matchups - reg_season,
    )

    # Print summary
    mp_to_sps = defaultdict(list)
    for sp, mp_id in sorted(matchup_map.items()):
        mp_to_sps[mp_id].append(sp)

    print(f"\nMatchup period mapping ({len(matchup_map)} scoring periods -> {len(mp_to_sps)} matchups):")
    for mp_id in sorted(mp_to_sps.keys()):
        sps = mp_to_sps[mp_id]
        print(f"  Matchup {mp_id:2d}: SP {sps[0]:3d}-{sps[-1]:3d} ({len(sps)} days)")

    # Load CSV
    file_path = os.path.join(mp.DATA_PATH, "daily_player_stats_2025.csv")
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return

    print(f"\nLoading data from {file_path}...")
    df = pd.read_csv(file_path)
    print(f"Loaded {len(df)} rows.")

    # Apply mapping
    print("Updating matchup_period column...")
    df["matchup_period"] = df["scoring_period"].map(matchup_map)

    # Report
    filled = df["matchup_period"].notna().sum()
    missing = df["matchup_period"].isna().sum()
    print(f"Filled: {filled}, Missing: {missing}")

    if missing > 0:
        unmapped_sps = sorted(df[df["matchup_period"].isna()]["scoring_period"].unique())
        print(f"Unmapped scoring periods: {unmapped_sps}")

    # Convert to integer
    df["matchup_period"] = df["matchup_period"].astype("Int64")

    # Save
    print(f"\nSaving to {file_path}...")
    df.to_csv(file_path, index=False)
    print("Done!")


if __name__ == "__main__":
    main()
