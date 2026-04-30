"""
Quick Lineup Impact Analysis
Evaluates whether using ESPN's Quick Lineup feature costs teams points
across all 10 teams in the league.

Methodology:
- For each bench/IL batter on each day, the LAST recorded move that placed
  them in their current bench slot determines attribution:
    'quick'   - CPU, CPU_USER_INITIATED, or NightlyLeagueUpdateTaskProcessor placed them there
    'manual'  - GUID session placed them there
    'default' - No recorded move to bench (drafted/acquired onto bench,
                or carried over with no explicit slot change)
- Missed stats are the counting stats (R, HR, RBI, SB) those bench batters
  actually produced on that day, per the ESPN stats CSV.
- Active pitcher QS/SVHD are compared across QL vs manual DAYS (day-level
  classification still used for pitchers since bench pitcher data is sparse).

All grouping uses team_id (not team_name) to handle mid-season renames.
Display names use the most recent name seen per team_id.
"""

import pandas as pd
import numpy as np
from collections import defaultdict

ACTIVITY_PATH = "data-lake/01_Bronze/fantasy_baseball/activity_espn_season_2026.csv"
STATS_PATH    = "data-lake/01_Bronze/fantasy_baseball/stats_espn_daily_2026.csv"

BATTING_COUNTING  = ["R", "HR", "RBI", "SB"]
PITCHING_COUNTING = ["QS", "SVHD"]
PITCHING_RATE     = ["K/9", "ERA", "WHIP"]

ACTIVE_BATTER_SLOTS  = {"C", "1B", "2B", "3B", "SS", "2B/SS", "1B/3B", "OF", "UTIL"}
ACTIVE_PITCHER_SLOTS = {"SP", "RP", "P"}
BENCH_SLOTS          = {"BE", "IL"}

QUICK_SOURCES = {"CPU", "NightlyLeagueUpdateTaskProcessor", "CPU_USER_INITIATED"}


# -- 1. Load data --------------------------------------------------------------

def load_data():
    act = pd.read_csv(ACTIVITY_PATH)
    act["date_only"] = pd.to_datetime(act["date"]).dt.date
    act = act.sort_values("date")           # chronological for history lookup

    stats = pd.read_csv(STATS_PATH, low_memory=False)
    stats["date"] = pd.to_datetime(stats["date"]).dt.date
    return act, stats


def build_team_name_map(stats: pd.DataFrame) -> dict:
    """Most recent name per team_id — handles mid-season renames."""
    latest = (
        stats.sort_values("date")
        .drop_duplicates(subset=["team_id"], keep="last")[["team_id", "team_name"]]
    )
    return dict(zip(latest["team_id"], latest["team_name"]))


# -- 2. Player-level bench placement attribution --------------------------------

def build_move_history(act: pd.DataFrame) -> dict:
    """
    {(team_id, player_name): [(date, position_to, source), ...]} sorted asc.
    Used to find the last move that placed a player in a bench slot.
    """
    history = defaultdict(list)
    for _, row in act.iterrows():
        history[(int(row["team_id"]), row["player_name"])].append(
            (row["date_only"], row["position_to"], row["source"])
        )
    return history


def get_placement(team_id: int, player_name: str, bench_slot: str,
                  stats_date, history: dict) -> str:
    """
    Returns 'quick', 'manual', or 'default' for a bench player on a given day.

    Scans the player's move history for the most recent move that placed them
    in bench_slot on or before stats_date. The source of that move determines
    attribution. If no such move exists, returns 'default'.
    """
    last_source = None
    for move_date, pos_to, source in history.get((team_id, player_name), []):
        if move_date <= stats_date and pos_to == bench_slot:
            last_source = source          # keep updating — last match wins
    if last_source is None:
        return "default"
    return "quick" if last_source in QUICK_SOURCES else "manual"


# -- 3. Build bench performance table ------------------------------------------

def build_bench_performances(stats: pd.DataFrame, history: dict) -> pd.DataFrame:
    """
    Returns one row per bench/IL batter per day, with placement attribution
    and actual counting stats. Only includes rows where the player had a game
    (R is not null — ESPN only populates stats for players with games).

    Columns: date, team_id, player_name, lineup_slot, placement,
             R, HR, RBI, SB, OPS, AB, counting_total
    """
    bench = stats[
        stats["lineup_slot"].isin(BENCH_SLOTS) &
        stats["player_type"].eq("batter") &
        stats["R"].notna()
    ].copy()

    bench["placement"] = bench.apply(
        lambda r: get_placement(
            int(r["team_id"]), r["player_name"], r["lineup_slot"], r["date"], history
        ),
        axis=1
    )

    for col in BATTING_COUNTING:
        bench[col] = bench[col].fillna(0)

    bench["counting_total"] = bench[BATTING_COUNTING].sum(axis=1)
    return bench[["date", "team_id", "player_name", "lineup_slot",
                  "placement", "R", "HR", "RBI", "SB", "OPS", "AB",
                  "counting_total"]].reset_index(drop=True)


# -- 4. Classify QL vs manual DAYS (for pitcher analysis) ----------------------

def classify_lineup_days(act: pd.DataFrame) -> pd.DataFrame:
    """Day-level QL classification per team_id (used for pitcher stats)."""
    ql_moves = act[act["source"].isin(QUICK_SOURCES)]
    ql_days = (
        ql_moves.groupby(["team_id", "date_only"])
        .size().reset_index(name="ql_moves")
    )
    ql_days["lineup_type"] = "quick"
    ql_days = ql_days[["team_id", "date_only", "lineup_type"]].rename(
        columns={"date_only": "date"}
    )
    all_days = (
        act.groupby(["team_id", "date_only"])
        .size().reset_index(name="n")
    ).rename(columns={"date_only": "date"})
    merged = all_days.merge(ql_days, on=["team_id", "date"], how="left")
    merged["lineup_type"] = merged["lineup_type"].fillna("manual")
    return merged[["team_id", "date", "lineup_type"]]


# -- 5. Active pitcher stats per (team_id, date) -------------------------------

def compute_pitcher_stats(stats: pd.DataFrame) -> pd.DataFrame:
    results = []
    pit = stats[stats["player_type"] == "pitcher"]
    for (dt, team_id), group in pit.groupby(["date", "team_id"]):
        active = group[group["lineup_slot"].isin(ACTIVE_PITCHER_SLOTS)]
        row = {"date": dt, "team_id": team_id}
        for stat in PITCHING_COUNTING:
            row[f"active_pit_{stat}"] = active[stat].fillna(0).sum()
        for stat in PITCHING_RATE:
            pitched = active[active[stat].notna()]
            row[f"active_pit_{stat}"] = pitched[stat].mean() if not pitched.empty else np.nan
        results.append(row)
    return pd.DataFrame(results)


# -- 6. Summarize --------------------------------------------------------------

def summarize(bench_perf: pd.DataFrame, pit_df: pd.DataFrame,
              lineup_days: pd.DataFrame, team_name_map: dict) -> None:

    name = lambda tid: team_name_map.get(tid, str(tid))

    print("=" * 70)
    print("QUICK LINEUP IMPACT ANALYSIS - 2026 Season")
    print("=" * 70)

    # --- Bench batter missed stats by placement type -------------------------
    print("\n-- League-wide missed batting stats by bench placement type ------")
    print("   (only bench batters who had a game that day)")
    agg = bench_perf.groupby("placement")[BATTING_COUNTING].agg(
        total=("R", "sum")  # placeholder — done properly below
    )
    agg = bench_perf.groupby("placement")[BATTING_COUNTING].sum()
    agg["total"] = agg.sum(axis=1)
    agg_avg = bench_perf.groupby("placement")[BATTING_COUNTING].mean().round(3)
    agg_avg.columns = [f"avg_{c}" for c in BATTING_COUNTING]
    print(pd.concat([agg, agg_avg], axis=1).to_string())

    # --- Per-team missed stats by placement ----------------------------------
    print("\n-- Per-team season totals: missed batting stats by placement -----")
    team_agg = bench_perf.groupby(["team_id", "placement"])[BATTING_COUNTING].sum()
    team_agg["total"] = team_agg.sum(axis=1)
    team_agg.index = team_agg.index.set_levels(
        [pd.Index([name(t) for t in team_agg.index.get_level_values("team_id").unique()]),
         team_agg.index.get_level_values("placement").unique()],
        level=[0, 1]
    )
    # simpler: reset and remap
    team_agg = bench_perf.groupby(["team_id", "placement"])[BATTING_COUNTING].sum().reset_index()
    team_agg["total"] = team_agg[BATTING_COUNTING].sum(axis=1)
    team_agg["team_name"] = team_agg["team_id"].map(team_name_map)
    team_agg = team_agg.set_index(["team_name", "placement"]).drop(columns="team_id")
    print(team_agg.sort_values(["team_name", "placement"]).to_string())

    # --- Active pitcher stats by day-level QL classification -----------------
    pit_merged = pit_df.merge(lineup_days, on=["team_id", "date"], how="left")
    pit_merged["lineup_type"] = pit_merged["lineup_type"].fillna("manual")
    print("\n-- Avg active pitching stats by lineup type (day-level) ----------")
    pit_cols = [f"active_pit_{s}" for s in PITCHING_COUNTING + PITCHING_RATE]
    pit_agg = pit_merged.groupby("lineup_type")[pit_cols].mean().round(3)
    pit_agg.columns = PITCHING_COUNTING + PITCHING_RATE
    print(pit_agg.to_string())


def per_team_top_misses(bench_perf: pd.DataFrame, team_name_map: dict,
                        n: int = 5) -> None:
    print("\n" + "=" * 70)
    print("TOP MISSED PERFORMANCES BY TEAM AND PLACEMENT TYPE")
    print("=" * 70)

    for team_id in sorted(bench_perf["team_id"].unique()):
        team_name = team_name_map.get(team_id, str(team_id))
        t = bench_perf[bench_perf["team_id"] == team_id]

        ql_days   = t[t["placement"] == "quick"]["date"].nunique()
        man_days  = t[t["placement"] == "manual"]["date"].nunique()
        def_days  = t[t["placement"] == "default"]["date"].nunique()

        print(f"\n{'-'*60}")
        print(f"  {team_name}  (id={team_id})")
        print(f"  Bench appearances with game: "
              f"QL-placed={len(t[t['placement']=='quick'])}  "
              f"Manual-placed={len(t[t['placement']=='manual'])}  "
              f"Default={len(t[t['placement']=='default'])}")

        for label, placement in [("Quick Lineup placement", "quick"),
                                  ("Manual placement",       "manual"),
                                  ("Default/carried-over",  "default")]:
            subset = t[t["placement"] == placement].nlargest(n, "counting_total")
            if subset.empty:
                print(f"\n  [{label}] — no bench appearances with game stats")
                continue
            total = t[t["placement"] == placement][BATTING_COUNTING].sum()
            print(f"\n  [{label}] season missed: "
                  f"R={total['R']:.0f}  HR={total['HR']:.0f}  "
                  f"RBI={total['RBI']:.0f}  SB={total['SB']:.0f}  "
                  f"total={total.sum():.0f}")
            print(f"  Top {n}:")
            cols = ["date", "player_name", "R", "HR", "RBI", "SB", "OPS", "counting_total"]
            print(subset[cols].to_string(index=False))


# -- Main ----------------------------------------------------------------------

def main():
    print("Loading data...")
    act, stats = load_data()

    print("Building team name map...")
    team_name_map = build_team_name_map(stats)
    for tid, name in sorted(team_name_map.items()):
        print(f"  {tid}: {name}")

    print("Building player move history...")
    history = build_move_history(act)

    print("Tagging bench batter placements...")
    bench_perf = build_bench_performances(stats, history)
    print(f"  {len(bench_perf)} bench batter game-days with stats")
    print("  Placement breakdown:")
    print(bench_perf["placement"].value_counts().to_string())

    print("Computing active pitcher stats...")
    pit_df = compute_pitcher_stats(stats)

    print("Classifying lineup days (for pitcher analysis)...")
    lineup_days = classify_lineup_days(act)

    summarize(bench_perf, pit_df, lineup_days, team_name_map)
    per_team_top_misses(bench_perf, team_name_map, n=5)

    # Save outputs
    bench_perf.to_csv(
        "data-lake/01_Bronze/fantasy_baseball/quick_lineup_bench_performances_2026.csv",
        index=False
    )
    print("\nBench performances saved.")


if __name__ == "__main__":
    main()
