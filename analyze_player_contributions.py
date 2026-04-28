"""
Player Contribution Analysis
-----------------------------
For a target team, identifies players not contributing to the 5x5 H2H scoring
categories and suggests free-agent replacements from the same position group.

Evaluation window: 28 days (based on prior rolling-correlation analysis showing
this captures ~82% of the max predictive signal — see analyze_roster_churn.ipynb)

Pace score: actual per-game/rate vs full-season projection. >1.0 = ahead of pace.
Start rate: fraction of MLB games in which the player appeared in the lineup.

Usage:
    python analyze_player_contributions.py
"""

import sys
import io
import os
import re
import unicodedata
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CSV_PATH      = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\stats_espn_daily_2026.csv"
LINEUP_PATH   = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\lineups_mlb_batters_2026.csv"
PROJ_LU_PATH  = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\projected_lineups_2026.csv"
PROJ_BAT_PATH = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\player_batter_projections_2026.csv"
PROJ_PIT_PATH = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\player_pitcher_projections_2026.csv"
REPORTS_DIR   = r"C:\Users\peter.rigali\Desktop\acn_repo\fantasy_baseball\reports"
TARGET_TEAM   = "Datalickmyballs"
EVAL_WINDOW   = 28
WEAK_Z_THRESH = -0.3
DROP_Z_THRESH = -0.5
FA_MIN_GAMES  = 5

MIN_BAT_WINDOW_GAMES   = 10
MIN_PITCH_WINDOW_GAMES = 3

CATEGORIES      = ["R", "HR", "RBI", "SB", "OPS", "K/9", "QS", "SVHD", "ERA", "WHIP"]
LOWER_IS_BETTER = {"ERA", "WHIP"}
BAT_CATS        = ["R", "HR", "RBI", "SB", "OPS"]
PITCH_CATS      = ["K/9", "QS", "SVHD", "ERA", "WHIP"]

ACTIVE_SLOTS = {"1B", "2B", "3B", "SS", "OF", "C", "UTIL", "DH",
                "SP", "RP", "P", "1B/3B", "2B/SS", "IF"}

# ---------------------------------------------------------------------------
# Load main data
# ---------------------------------------------------------------------------
print("Loading data...")
df = pd.read_csv(CSV_PATH, low_memory=False)
df["date"] = pd.to_datetime(df["date"])

num_cols = ["R","HR","RBI","SB","OPS","QS","SVHD","K","OUTS","ER","P_BB","P_H","AB","OBP","SLG","HLD","SV"]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

df["IP"]         = df["OUTS"] / 3.0
df["is_pitcher"] = df["eligible_slots"].str.contains("SP|RP", na=False)

# ---------------------------------------------------------------------------
# Eligible-slot sets
# ---------------------------------------------------------------------------
GENERIC_SLOTS = {"BE", "IL", "UTIL", "P", "IF", "DH"}

def parse_slots(slot_str):
    if pd.isna(slot_str):
        return set()
    return {s.strip() for s in slot_str.split("|")} - GENERIC_SLOTS

slot_map = (
    df.groupby("player_name")["eligible_slots"]
    .agg(lambda x: x.mode().iloc[0] if not x.mode().empty else "")
    .apply(parse_slots)
)

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------
def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()

def _abbrev_key(full_name):
    parts = _norm(full_name).split()
    if len(parts) < 2:
        return _norm(full_name)
    suffix = ""
    if parts[-1] in ("jr", "sr", "ii", "iii", "iv"):
        suffix = " " + parts[-1]
        parts  = parts[:-1]
    return parts[0][0] + " " + " ".join(parts[1:]) + suffix

# ---------------------------------------------------------------------------
# Load projections
# ---------------------------------------------------------------------------
def _clean_proj_name(raw):
    raw = str(raw).replace("\xa0", " ")
    return re.sub(r"\s*\(.*", "", raw).strip()

def _load_proj(path, num_cols):
    d = pd.read_csv(path)
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["player_name"] = d["Player"].apply(_clean_proj_name)
    for col in num_cols:
        if col in d.columns:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)
    return d

bat_proj_df = _load_proj(PROJ_BAT_PATH, ["AB", "R", "HR", "RBI", "SB", "OPS"])
bat_proj_df["proj_g"] = (bat_proj_df["AB"] / 4.0).clip(lower=1)
_bat_proj = {_norm(n): row for n, row in bat_proj_df.set_index("player_name").iterrows()}

pit_proj_df = _load_proj(PROJ_PIT_PATH, ["IP", "K", "ERA", "WHIP"])
pit_proj_df["K/9"] = (pit_proj_df["K"] * 9) / pit_proj_df["IP"].replace(0, np.nan)
_pit_proj = {_norm(n): row for n, row in pit_proj_df.set_index("player_name").iterrows()}

def get_proj(player_name, is_pit):
    return (_pit_proj if is_pit else _bat_proj).get(_norm(player_name))

# ---------------------------------------------------------------------------
# Pace computation
# ---------------------------------------------------------------------------
def compute_pace(player_name, is_pit, s_row):
    """
    Compare actual per-game/rate vs projection.
    Returns (per-cat dict, overall pace score). pace > 1.0 = ahead of projection.
    Counting stats: actual/game vs projected/game.
    Rate stats (OPS, K/9, ERA, WHIP): actual rate vs projected rate (ERA/WHIP inverted).
    """
    proj = get_proj(player_name, is_pit)
    if proj is None or s_row is None or s_row.empty:
        return {}, None

    ratios = {}

    if not is_pit:
        gp = float(s_row["games_played"].values[0])
        if gp < 1:
            return {}, None
        proj_g = max(float(proj["proj_g"]), 1)

        for cat in ["R", "HR", "RBI", "SB"]:
            pv = float(proj.get(cat, 0))
            if pv <= 0:
                continue
            av = float(s_row[cat].values[0]) if cat in s_row.columns else 0
            ratios[cat] = (av / gp) / (pv / proj_g)

        pops = float(proj.get("OPS", 0))
        if pops > 0 and "OPS" in s_row.columns:
            aops = s_row["OPS"].values[0]
            if not pd.isna(aops) and float(aops) > 0:
                ratios["OPS"] = float(aops) / pops

    else:
        actual_ip = float(s_row["IP"].values[0]) if "IP" in s_row.columns else 0
        if actual_ip < 1:
            return {}, None

        pk9 = proj.get("K/9", np.nan)
        pk9 = float(pk9) if not pd.isna(pk9) else 0
        if pk9 > 0 and "K/9" in s_row.columns:
            ak9 = s_row["K/9"].values[0]
            if not pd.isna(ak9):
                ratios["K/9"] = float(ak9) / pk9

        pera = float(proj.get("ERA", 0))
        if pera > 0 and "ERA" in s_row.columns:
            aera = s_row["ERA"].values[0]
            if not pd.isna(aera) and float(aera) > 0:
                ratios["ERA"] = pera / float(aera)  # inverted: lower ERA = higher pace

        pwhip = float(proj.get("WHIP", 0))
        if pwhip > 0 and "WHIP" in s_row.columns:
            awhip = s_row["WHIP"].values[0]
            if not pd.isna(awhip) and float(awhip) > 0:
                ratios["WHIP"] = pwhip / float(awhip)  # inverted

    if not ratios:
        return {}, None

    return ratios, round(float(np.mean(list(ratios.values()))), 2)

def pace_label(pace):
    if pace is None:
        return "—"
    pct = (pace - 1) * 100
    return f"+{pct:.0f}%" if pct >= 0 else f"{pct:.0f}%"

# ---------------------------------------------------------------------------
# Batting order data
# ---------------------------------------------------------------------------
lineup_df = pd.read_csv(LINEUP_PATH, low_memory=False)
lineup_df["_key"] = lineup_df["player_name"].apply(lambda n: _norm(n))

TOTAL_LINEUP_DAYS = lineup_df["date"].nunique()

_order_stats = (
    lineup_df.groupby("_key")
    .agg(
        lineup_games=("date",          "nunique"),
        avg_order   =("batting_order", "mean"),
        pct_top3    =("batting_order", lambda x: (x <= 3).mean()),
        pct_top5    =("batting_order", lambda x: (x <= 5).mean()),
    )
    .reset_index()
)
_order_key_map = _order_stats.set_index("_key").to_dict("index")

_proj_df  = pd.read_csv(PROJ_LU_PATH, low_memory=False)
_proj_map = {}
for _, row in _proj_df.iterrows():
    k = _abbrev_key(str(row.get("Player", "")))
    _proj_map[k] = int(row.get("Slot", 5))

def get_order_stats(player_name):
    # Primary: full normalized name (lineup CSV now uses full names from URL slug)
    full_key = _norm(player_name)
    if full_key in _order_key_map:
        s = _order_key_map[full_key]
        return int(s["lineup_games"]), round(s["avg_order"], 1), round(s["pct_top3"], 2), round(s["pct_top5"], 2)
    # Fallback: abbreviated key (legacy / edge cases)
    abbrev_key = _norm(_abbrev_key(player_name))
    if abbrev_key in _order_key_map:
        s = _order_key_map[abbrev_key]
        return int(s["lineup_games"]), round(s["avg_order"], 1), round(s["pct_top3"], 2), round(s["pct_top5"], 2)
    # Projected lineup fallback
    ab_key = _abbrev_key(player_name)
    if ab_key in _proj_map:
        slot = _proj_map[ab_key]
        return 0, float(slot), float(slot <= 3), float(slot <= 5)
    return 0, None, None, None

def lineup_bonus(avg_order):
    if avg_order is None: return 0.0
    if avg_order <= 2:    return  0.6
    if avg_order <= 3:    return  0.4
    if avg_order <= 5:    return  0.2
    if avg_order <= 6:    return  0.0
    return -0.3

def start_bonus(start_pct):
    """Bonus for players in the lineup consistently."""
    if start_pct is None or pd.isna(start_pct): return 0.0
    if start_pct >= 0.85: return  0.4
    if start_pct >= 0.70: return  0.2
    if start_pct >= 0.50: return  0.0
    return -0.3

# ---------------------------------------------------------------------------
# Active/bench/IL flags
# ---------------------------------------------------------------------------
df["is_active"] = df["lineup_slot"].isin(ACTIVE_SLOTS)
df["is_bench"]  = df["lineup_slot"] == "BE"
df["is_il"]     = df["lineup_slot"] == "IL"

latest_date  = df["date"].max()
window_start = latest_date - timedelta(days=EVAL_WINDOW)
season_start = df["date"].min()

print(f"Season: {season_start.date()} → {latest_date.date()} | Eval window: last {EVAL_WINDOW} days")
print(f"Target team: {TARGET_TEAM}\n")

# ---------------------------------------------------------------------------
# Current roster
# ---------------------------------------------------------------------------
current_roster = df[df["date"] == latest_date][
    ["player_name","team_name","lineup_slot","injury_status","is_pitcher","is_active","is_bench","is_il"]
].copy().drop_duplicates("player_name")

my_roster    = current_roster[current_roster["team_name"] == TARGET_TEAM].copy()
all_rostered = set(current_roster["player_name"].unique())

# ---------------------------------------------------------------------------
# Per-player season aggregation
# ---------------------------------------------------------------------------
def aggregate_players(data):
    bat = data[~data["is_pitcher"]].copy()
    pit = data[data["is_pitcher"]].copy()
    bat["_played"] = bat["AB"]   > 0
    pit["_played"] = pit["OUTS"] > 0

    bat_agg = (
        bat.groupby("player_name")
        .agg(
            team_name   =("team_name",  "last"),
            games       =("date",       "nunique"),
            games_played=("_played",    "sum"),
            R           =("R",          "sum"),
            HR          =("HR",         "sum"),
            RBI         =("RBI",        "sum"),
            SB          =("SB",         "sum"),
            _ops_num    =("OPS",        lambda x: (x * bat.loc[x.index, "AB"]).sum()),
            _ab         =("AB",         "sum"),
        )
        .reset_index()
    )
    bat_agg["OPS"]        = bat_agg["_ops_num"] / bat_agg["_ab"].replace(0, np.nan)
    bat_agg["is_pitcher"] = False
    bat_agg.drop(columns=["_ops_num","_ab"], inplace=True)

    pit_agg = (
        pit.groupby("player_name")
        .agg(
            team_name   =("team_name",  "last"),
            games       =("date",       "nunique"),
            games_played=("_played",    "sum"),
            QS          =("QS",         "sum"),
            SVHD        =("SVHD",       "sum"),
            IP          =("IP",         "sum"),
            K           =("K",          "sum"),
            ER          =("ER",         "sum"),
            _BB         =("P_BB",       "sum"),
            _H          =("P_H",        "sum"),
        )
        .reset_index()
    )
    pit_agg["K/9"]  = (pit_agg["K"]  * 9) / pit_agg["IP"].replace(0, np.nan)
    pit_agg["ERA"]  = (pit_agg["ER"] * 9) / pit_agg["IP"].replace(0, np.nan)
    pit_agg["WHIP"] = (pit_agg["_BB"] + pit_agg["_H"]) / pit_agg["IP"].replace(0, np.nan)
    pit_agg["is_pitcher"] = True
    pit_agg.drop(columns=["K","ER","_BB","_H"], inplace=True)  # keep IP for pace

    return bat_agg, pit_agg


season_bat, season_pit = aggregate_players(df)
window_bat, window_pit = aggregate_players(df[df["date"] >= window_start])

# ---------------------------------------------------------------------------
# Z-scores
# ---------------------------------------------------------------------------
BAT_Z_CATS   = ["R", "HR", "RBI", "SB", "OPS"]
PITCH_Z_CATS = ["K/9", "QS", "SVHD", "ERA", "WHIP"]

def add_zscores(agg_df, cats, lower_better):
    for cat in cats:
        if cat not in agg_df.columns:
            continue
        col  = agg_df[cat].copy()
        mean = col.mean()
        std  = col.std()
        if pd.isna(std) or std == 0:
            std = 1
        z = (col - mean) / std
        if cat in lower_better:
            z = -z
        agg_df[f"z_{cat}"] = z.fillna(0)
    z_cols = [f"z_{c}" for c in cats if f"z_{c}" in agg_df.columns]
    agg_df["z_total"] = agg_df[z_cols].sum(axis=1)
    return agg_df

season_bat = add_zscores(season_bat, BAT_Z_CATS,   LOWER_IS_BETTER)
season_pit = add_zscores(season_pit, PITCH_Z_CATS, LOWER_IS_BETTER)
window_bat = add_zscores(window_bat, BAT_Z_CATS,   LOWER_IS_BETTER)
window_pit = add_zscores(window_pit, PITCH_Z_CATS, LOWER_IS_BETTER)

# ---------------------------------------------------------------------------
# Build player profiles
# ---------------------------------------------------------------------------
def build_profile(player_name, is_pit, roster_row):
    s_df = season_pit if is_pit else season_bat
    w_df = window_pit if is_pit else window_bat
    cats = PITCH_Z_CATS if is_pit else BAT_Z_CATS

    s_row = s_df[s_df["player_name"] == player_name]
    w_row = w_df[w_df["player_name"] == player_name]

    lu_games, avg_ord, pct3, pct5 = get_order_stats(player_name)
    pace_ratios, pace_score       = compute_pace(player_name, is_pit, s_row if not s_row.empty else None)
    start_pct = round(lu_games / TOTAL_LINEUP_DAYS, 2) if TOTAL_LINEUP_DAYS > 0 and not is_pit else None

    profile = {
        "player_name":   player_name,
        "lineup_slot":   roster_row["lineup_slot"],
        "injury_status": roster_row["injury_status"],
        "is_active":     roster_row["is_active"],
        "is_bench":      roster_row["is_bench"],
        "is_il":         roster_row["is_il"],
        "is_pitcher":    is_pit,
        "eligible_slots":slot_map.get(player_name, set()),
        "lu_games":      lu_games,
        "avg_order":     avg_ord,
        "pct_top3":      pct3,
        "pct_top5":      pct5,
        "pace_score":    pace_score,
        "pace_ratios":   pace_ratios,
        "start_pct":     start_pct,
    }

    if not s_row.empty:
        profile["season_games"]        = int(s_row["games"].values[0])
        profile["season_games_played"] = int(s_row["games_played"].values[0])
        profile["season_z_total"]      = round(float(s_row["z_total"].values[0]), 3)
        for cat in cats:
            if cat in s_row.columns:
                v = s_row[cat].values[0]
                profile[f"s_{cat}"] = round(float(v), 3) if not pd.isna(v) else None
            if f"z_{cat}" in s_row.columns:
                profile[f"sz_{cat}"] = round(float(s_row[f"z_{cat}"].values[0]), 3)
    else:
        profile["season_games"]        = 0
        profile["season_games_played"] = 0
        profile["season_z_total"]      = 0.0

    if not w_row.empty:
        profile["window_games"]        = int(w_row["games"].values[0])
        profile["window_games_played"] = int(w_row["games_played"].values[0])
        profile["window_z_total"]      = round(float(w_row["z_total"].values[0]), 3)
        for cat in cats:
            if f"z_{cat}" in w_row.columns:
                profile[f"wz_{cat}"] = round(float(w_row[f"z_{cat}"].values[0]), 3)
    else:
        profile["window_games"]        = 0
        profile["window_games_played"] = 0
        profile["window_z_total"]      = 0.0

    return profile


profiles = []
for _, r in my_roster.iterrows():
    profiles.append(build_profile(r["player_name"], r["is_pitcher"], r))

profiles_df = pd.DataFrame(profiles)

# ---------------------------------------------------------------------------
# Flagging
# ---------------------------------------------------------------------------
profiles_df["min_games"]     = profiles_df.apply(
    lambda r: MIN_PITCH_WINDOW_GAMES if r["is_pitcher"] else MIN_BAT_WINDOW_GAMES, axis=1)
profiles_df["enough_sample"] = profiles_df["window_games_played"] >= profiles_df["min_games"]

poor_perf = profiles_df[
    (~profiles_df["is_il"]) &
    (
        (profiles_df["window_z_total"] < DROP_Z_THRESH) |
        (
            (profiles_df["window_z_total"] < WEAK_Z_THRESH) &
            (profiles_df["season_z_total"] < WEAK_Z_THRESH)
        )
    )
].copy()

def assign_flag(r):
    if not r["enough_sample"]:
        return f"Low sample ({int(r['window_games_played'])}/{int(r['min_games'])} games in {EVAL_WINDOW}d)"
    return "Drop candidate" if r["window_z_total"] < DROP_Z_THRESH else "Underperforming"

poor_perf["flag_reason"] = poor_perf.apply(assign_flag, axis=1)

bench_flagged = profiles_df[
    profiles_df["is_bench"] &
    profiles_df["enough_sample"] &
    (profiles_df["season_z_total"] < WEAK_Z_THRESH)
].copy()
bench_flagged["flag_reason"] = "Bench — below average season"

all_flagged = pd.concat([poor_perf, bench_flagged]).drop_duplicates("player_name")

# ---------------------------------------------------------------------------
# Free agent pool
# ---------------------------------------------------------------------------
def build_fa_pool(season_bat, season_pit, all_rostered):
    bat_fa = season_bat[~season_bat["player_name"].isin(all_rostered)].copy()
    pit_fa = season_pit[~season_pit["player_name"].isin(all_rostered)].copy()
    bat_fa["is_pitcher"] = False
    pit_fa["is_pitcher"] = True
    fa = pd.concat([bat_fa, pit_fa], ignore_index=True)
    fa = fa[fa["games"] >= FA_MIN_GAMES].copy()
    fa["eligible_slots"] = fa["player_name"].map(slot_map)

    fa[["lu_games","avg_order","pct_top3","pct_top5"]] = fa["player_name"].apply(
        lambda n: pd.Series(get_order_stats(n))
    )
    fa["start_pct"] = fa.apply(
        lambda r: round(max(int(r["lu_games"] or 0), 0) / TOTAL_LINEUP_DAYS, 2)
        if not r["is_pitcher"] and TOTAL_LINEUP_DAYS > 0 else None,
        axis=1
    )

    def _pace(row):
        agg = season_pit if row["is_pitcher"] else season_bat
        sr  = agg[agg["player_name"] == row["player_name"]]
        _, p = compute_pace(row["player_name"], row["is_pitcher"], sr if not sr.empty else None)
        return p
    fa["pace_score"] = fa.apply(_pace, axis=1)

    return fa

fa_pool = build_fa_pool(season_bat, season_pit, all_rostered)


def best_fa_for_player(player_profile, fa_pool, n=3):
    is_pit       = player_profile["is_pitcher"]
    lineup_slot  = player_profile.get("lineup_slot", "")
    player_slots = slot_map.get(player_profile["player_name"], set())

    candidates = fa_pool[fa_pool["is_pitcher"] == is_pit].copy()

    if lineup_slot == "UTIL":
        matched = candidates[candidates["eligible_slots"].apply(
            lambda s: isinstance(s, set) and len(s) > 0)]
    else:
        def _overlap(fa_slots):
            return len(player_slots & fa_slots) if isinstance(fa_slots, set) else 0
        candidates["_overlap"] = candidates["eligible_slots"].apply(_overlap)
        matched = candidates[candidates["_overlap"] > 0]
        if matched.empty:
            matched = candidates

    matched = matched.copy()
    if not is_pit:
        matched["_composite"] = (
            matched["z_total"]
            + matched["avg_order"].apply(lineup_bonus)
            + matched["start_pct"].apply(lambda x: start_bonus(x) if pd.notna(x) else 0.0)
        )
        return matched.sort_values("_composite", ascending=False).head(n)

    return matched.sort_values("z_total", ascending=False).head(n)

# ---------------------------------------------------------------------------
# Report helpers
# ---------------------------------------------------------------------------
today    = datetime.today().strftime("%Y-%m-%d")
out_path = os.path.join(REPORTS_DIR, f"player_contributions_{today}.md")

CATS_DISPLAY = {True: PITCH_Z_CATS, False: BAT_Z_CATS}

def z_bar(z, width=10):
    filled = min(abs(int(round(z * 2))), width)
    return ("▓" if z >= 0 else "░") * filled + "·" * (width - filled)

def grade_z(z):
    if z >=  1.0: return "Elite"
    if z >=  0.3: return "Strong"
    if z >= -0.3: return "Average"
    if z >= -0.7: return "Weak"
    return "Poor"

lines = []
def w(s=""): lines.append(s)

# ---------------------------------------------------------------------------
# Report: header
# ---------------------------------------------------------------------------
w(f"# Player Contribution Report — {TARGET_TEAM}")
w(f"*Generated: {today} | Season: {season_start.date()} → {latest_date.date()} | Eval window: last {EVAL_WINDOW} days*")
w()
w("## Scoring Categories")
w("**Batting:** R, HR, RBI, SB, OPS  |  **Pitching:** K/9, QS, SVHD, ERA, WHIP")
w()
w("**Pace** = actual rate vs full-season projection (+% = ahead, -% = behind).  "
  "**Start%** = fraction of MLB games player appeared in starting lineup.")
w()

# ---------------------------------------------------------------------------
# Report: Full Roster Scorecard
# ---------------------------------------------------------------------------
w("---")
w("## Full Roster Scorecard")
w()

for role, is_pit in [("Batters", False), ("Pitchers", True)]:
    role_df = profiles_df[profiles_df["is_pitcher"] == is_pit].copy()
    if role_df.empty:
        continue
    cats = CATS_DISPLAY[is_pit]
    w(f"### {role}")
    w()

    if not is_pit:
        hdr = (f"| {'Player':<26} | {'Slot':<8} | {'Gm':>3} | {'GP':>3} |"
               + "".join(f" {'z_'+c:>8} |" for c in cats)
               + f" {'z_Tot':>6} | {'28d z':>6} | {'28dGP':>5} | {'Pace':>6} | {'Start%':>6} | {'AvgOrd':>6} | {'%Top3':>5} | {'%Top5':>5} | Grade |")
        sep = (f"| {'-'*26} | {'-'*8} | {'-'*3} | {'-'*3} |"
               + "".join(f" {'-'*8} |" for _ in cats)
               + f" {'-'*6} | {'-'*6} | {'-'*5} | {'-'*6} | {'-'*6} | {'-'*6} | {'-'*5} | {'-'*5} | ----- |")
    else:
        hdr = (f"| {'Player':<26} | {'Slot':<8} | {'Gm':>3} | {'GP':>3} |"
               + "".join(f" {'z_'+c:>8} |" for c in cats)
               + f" {'z_Tot':>6} | {'28d z':>6} | {'28dGP':>5} | {'Pace':>6} | Grade |")
        sep = (f"| {'-'*26} | {'-'*8} | {'-'*3} | {'-'*3} |"
               + "".join(f" {'-'*8} |" for _ in cats)
               + f" {'-'*6} | {'-'*6} | {'-'*5} | {'-'*6} | ----- |")

    w(hdr)
    w(sep)

    for _, r in role_df.sort_values("season_z_total", ascending=False).iterrows():
        slot_str = str(r["lineup_slot"]) + (" 🤕" if r["is_il"] else "")
        gm    = int(r.get("season_games", 0))
        gp    = int(r.get("season_games_played", 0))
        w_gp  = int(r.get("window_games_played", 0))
        z_tot = r.get("season_z_total", 0)
        w_tot = r.get("window_z_total",  0)
        pace  = pace_label(r.get("pace_score"))

        cat_zs = "".join(
            f" {r[f'sz_{cat}']:>+8.2f} |" if r.get(f"sz_{cat}") is not None else f" {'—':>8} |"
            for cat in cats
        )

        if not is_pit:
            avg_o = r.get("avg_order")
            p3    = r.get("pct_top3")
            p5    = r.get("pct_top5")
            sp    = r.get("start_pct")
            o_str = (f" {avg_o:>6.1f} | {p3:>5.0%} | {p5:>5.0%} |"
                     if avg_o is not None else "      — |     — |     — |")
            sp_str = f" {sp:>5.0%}" if sp is not None else "      —"
            row = (f"| {r['player_name']:<26} | {slot_str:<8} | {gm:>3} | {gp:>3} |"
                   f"{cat_zs} {z_tot:>+6.2f} | {w_tot:>+6.2f} | {w_gp:>5} | {pace:>6} |{sp_str} | {o_str} {grade_z(z_tot)} |")
        else:
            row = (f"| {r['player_name']:<26} | {slot_str:<8} | {gm:>3} | {gp:>3} |"
                   f"{cat_zs} {z_tot:>+6.2f} | {w_tot:>+6.2f} | {w_gp:>5} | {pace:>6} | {grade_z(z_tot)} |")
        w(row)
    w()

# ---------------------------------------------------------------------------
# Report: Flagged Players
# ---------------------------------------------------------------------------
w("---")
w("## Flagged Players (Non-Contributors / Drop Candidates)")
w()
w(f"Criteria: season z < {WEAK_Z_THRESH} AND 28d z < {WEAK_Z_THRESH}, or 28d z < {DROP_Z_THRESH}. Excludes IL.")
w()

if all_flagged.empty:
    w("*No players currently flagged.*")
else:
    for _, fp in all_flagged.sort_values("window_z_total").iterrows():
        name   = fp["player_name"]
        is_pit = fp["is_pitcher"]
        cats   = CATS_DISPLAY[is_pit]

        w(f"### {name}  `{fp['lineup_slot']}` — _{fp['flag_reason']}_")
        w()

        # Per-category breakdown including pace
        pr = fp.get("pace_ratios") or {}
        if not isinstance(pr, dict):
            pr = {}

        cat_rows = []
        for cat in cats:
            val = fp.get(f"s_{cat}")
            sz  = fp.get(f"sz_{cat}")
            wz  = fp.get(f"wz_{cat}")
            p_r = pr.get(cat)
            if val is None and sz is None:
                continue
            cat_rows.append(
                f"| {cat:<6} | {(f'{val:.2f}' if val is not None else '—'):>8} |"
                f" {(f'{sz:+.2f}' if sz is not None else '—'):>7} |"
                f" {(f'{wz:+.2f}' if wz is not None else '—'):>7} |"
                f" {pace_label(p_r):>7} | `{z_bar(sz if sz is not None else 0)}` |"
            )

        if cat_rows:
            w(f"| Cat   | Season   | z_ssn   | z_{EVAL_WINDOW}d   | Pace    | Trend      |")
            w( "|-------|----------|---------|---------|---------|------------|")
            for cr in cat_rows:
                w(cr)
        w()

        pace_s = pace_label(fp.get("pace_score"))
        sp_s   = f"{fp['start_pct']:.0%}" if fp.get("start_pct") is not None else "—"
        ao_s   = f"{fp['avg_order']:.1f}"  if fp.get("avg_order") is not None else "—"
        gp_s   = int(fp.get("season_games_played", 0))
        gp_w   = int(fp.get("window_games_played",  0))
        req    = int(fp.get("min_games", 0))

        w(f"**Season z:** {fp.get('season_z_total', 0):+.2f} | "
          f"**28d z:** {fp.get('window_z_total', 0):+.2f} | "
          f"**GP:** {gp_s} season / {gp_w} last 28d (min: {req})")
        w(f"**Pace vs projection:** {pace_s} | **Start rate:** {sp_s} | **Avg batting order:** {ao_s}")
        w()

        # FA recommendations
        fa_recs = best_fa_for_player(fp, fa_pool, n=3)
        if not fa_recs.empty:
            role_cats = PITCH_Z_CATS if is_pit else BAT_Z_CATS
            w(f"**Top FA replacements (min {FA_MIN_GAMES} games — ranked by z + lineup fit):**")
            w()
            if not is_pit:
                w(f"| {'FA Candidate':<26} | GP | z_Total | Pace | Start% | AvgOrd | %Top3 | %Top5 |"
                  + " | ".join(f"{c:>7}" for c in role_cats) + " |")
                w(f"| {'-'*26} | -- | ------- | ---- | ------ | ------ | ----- | ----- |"
                  + " | ".join(["-------"] * len(role_cats)) + " |")
            else:
                w(f"| {'FA Candidate':<26} | GP | z_Total | Pace |"
                  + " | ".join(f"{c:>7}" for c in role_cats) + " |")
                w(f"| {'-'*26} | -- | ------- | ---- |"
                  + " | ".join(["-------"] * len(role_cats)) + " |")

            for _, fa in fa_recs.iterrows():
                gm_fa   = int(fa.get("games_played", fa.get("games", 0)))
                zt_fa   = fa.get("z_total", 0)
                pace_fa = pace_label(fa.get("pace_score"))
                cat_vals = " | ".join(
                    f"{fa[cat]:>7.2f}" if fa.get(cat) is not None and not pd.isna(fa.get(cat)) else f"{'—':>7}"
                    for cat in role_cats
                )
                if not is_pit:
                    avg_o = fa.get("avg_order")
                    p3    = fa.get("pct_top3")
                    p5    = fa.get("pct_top5")
                    sp    = fa.get("start_pct")
                    o_fa  = (f" {avg_o:>6.1f} | {p3:>5.0%} | {p5:>5.0%} |"
                             if avg_o is not None else "      — |     — |     — |")
                    sp_fa = f" {sp:>5.0%}" if sp is not None else "      —"
                    w(f"| {fa['player_name']:<26} | {gm_fa:>2} | {zt_fa:>+7.2f} | {pace_fa:>4} |{sp_fa} |{o_fa} {cat_vals} |")
                else:
                    w(f"| {fa['player_name']:<26} | {gm_fa:>2} | {zt_fa:>+7.2f} | {pace_fa:>4} | {cat_vals} |")
            w()
        w("---")
        w()

# ---------------------------------------------------------------------------
# Report: Summary
# ---------------------------------------------------------------------------
w("## Summary")
w()
n_drop = len(all_flagged[all_flagged["flag_reason"] == "Drop candidate"])
n_weak = len(all_flagged[all_flagged["flag_reason"] != "Drop candidate"])
w(f"- **Drop candidates** (28d z < {DROP_Z_THRESH}): {n_drop}")
w(f"- **Underperforming** (both windows z < {WEAK_Z_THRESH}): {n_weak}")
w(f"- **FA pool**: {len(fa_pool)} players (≥ {FA_MIN_GAMES} games)")
w()
w("### Notes")
w(f"- Pace compares actual per-game rate to full-season projection (batters: R/HR/RBI/SB/OPS; pitchers: K/9/ERA/WHIP).")
w(f"- Start% = MLB lineup appearances / {TOTAL_LINEUP_DAYS} lineup days tracked.")
w(f"- FA composite score = z_total + lineup order bonus + start rate bonus.")
w(f"- Eval window: {EVAL_WINDOW} days (~82% of max predictive signal per analyze_roster_churn.ipynb).")

# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------
os.makedirs(REPORTS_DIR, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Report saved → {out_path}")
print(f"Flagged players: {len(all_flagged)}")
print(f"  Drop candidates : {n_drop}")
print(f"  Underperforming : {n_weak}")
print(f"FA pool size      : {len(fa_pool)}")
