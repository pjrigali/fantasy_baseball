"""
Scrape MLB player stats from the official MLB Stats API.

Fetches all hitting and pitching stats for a given season and playerPool,
paginating through the API results, and saves each to a CSV file.

Usage:
    python scrape_mlb_stats.py                    # defaults: 2025, ALL
    python scrape_mlb_stats.py --season 2024
    python scrape_mlb_stats.py --player-pool QUALIFIED
"""

import argparse
import csv
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

# -- Column definitions matching mlb.com/stats table --------------------------

HITTING_COLS = [
    "rank", "player_id", "player_name", "team", "league", "position",
    "age", "gamesPlayed", "atBats", "runs", "hits", "doubles", "triples",
    "homeRuns", "rbi", "baseOnBalls", "strikeOuts", "stolenBases",
    "caughtStealing", "avg", "obp", "slg", "ops", "plateAppearances",
    "totalBases", "groundIntoDoublePlay", "hitByPitch", "sacBunts",
    "sacFlies", "babip", "intentionalWalks",
]

PITCHING_COLS = [
    "rank", "player_id", "player_name", "team", "league", "position",
    "age", "gamesPlayed", "gamesStarted", "wins", "losses",
    "era", "inningsPitched", "hits", "runs", "earnedRuns", "homeRuns",
    "baseOnBalls", "strikeOuts", "saves", "blownSaves", "holds",
    "whip", "saveOpportunities", "completeGames", "shutouts",
    "hitByPitch", "wildPitches", "balks", "battersFaced",
    "strikeoutsPer9Inn", "walksPer9Inn", "hitsPer9Inn",
    "strikeoutWalkRatio", "gamesFinished",
]


def write_csv(rows: list, columns: list, filepath: str) -> None:
    """Write rows to CSV, keeping only the specified columns."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"  [OK] Saved {len(rows)} rows -> {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Scrape MLB stats to CSV")
    parser.add_argument("--season", type=int, default=2025, help="MLB season year")
    parser.add_argument(
        "--player-pool",
        default="ALL",
        choices=["ALL", "QUALIFIED", "ROOKIES"],
        help="Player pool filter",
    )
    args = parser.parse_args()

    season = args.season
    pool = args.player_pool
    today = datetime.now().strftime("%Y%m%d")

    out_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", ".data_lake", "01_Bronze", "fantasy_baseball",
    )

    print(f"=== MLB Stats Scraper ===")
    print(f"Season: {season} | Pool: {pool}\n")

    # -- Hitting ---------------------------------------------------------------
    print(">> Scraping HITTING stats...")
    hitting_rows = mp.scrape_mlb_stats("hitting", season, pool)
    hitting_path = os.path.join(out_dir, f"stats_mlb_season_hitting_{season}_{today}.csv")
    write_csv(hitting_rows, HITTING_COLS, hitting_path)

    # -- Pitching --------------------------------------------------------------
    print("\n>> Scraping PITCHING stats...")
    pitching_rows = mp.scrape_mlb_stats("pitching", season, pool)
    pitching_path = os.path.join(out_dir, f"stats_mlb_season_pitching_{season}_{today}.csv")
    write_csv(pitching_rows, PITCHING_COLS, pitching_path)

    print(f"\n=== Done! ===")
    print(f"Hitting:  {hitting_path}")
    print(f"Pitching: {pitching_path}")


if __name__ == "__main__":
    main()
