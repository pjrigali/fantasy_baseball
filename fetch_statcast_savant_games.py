"""
fetch_statcast_savant_games.py
==============================
Description: Builds GAME-LEVEL Statcast tracking aggregates for every MLB batter
             and pitcher, for rolling-window analysis (hot-hand, change-point,
             stuff/velocity trends). Speed comes from querying Baseball Savant's
             pitch-level search ONE DATE AT A TIME, league-wide — a single request
             returns every pitch of every game that day (~4,400 rows / ~8s), the
             same per-date incremental shape as fetch_stats_mlb_boxscore.py. Each
             day's pitches are aggregated locally to one row per (game_date, player)
             for batters and, separately, for pitchers.

             This is the game-level counterpart to fetch_statcast_savant_season.py
             (the season leaderboard). The season file is one row per player per
             season; this is one row per player per game, so rolling 7/14-day
             windows can be computed. It can eventually supersede the weekly
             season pulls for analysis that needs granularity.

             Flow:
               1. Determine the date range incrementally: start from the last
                  game_date already in the batter file (1-day overlap, re-aggregated
                  for completeness), end at yesterday (before noon) or today (after).
               2. For each date: GET statcast_search/csv?game_date_gt=D&game_date_lt=D
                  (regular season), one request, all teams.
               3. Aggregate the day's pitches to per-(game_date, batter) and
                  per-(game_date, pitcher) rows. Names resolved via player_map.csv
                  (MLBAM id -> mlb_name).
               4. Merge: keep existing rows before the refetch window, replace the
                  window's dates with fresh aggregates (handles partial last day).

Source Data: Baseball Savant pitch-level search
               https://baseballsavant.mlb.com/statcast_search/csv
               ?all=true&type=details&hfGT=R%7C&game_date_gt=D&game_date_lt=D
             player_map.csv (MLBAM id -> name)

Outputs (data-lake/01_Bronze/fantasy_baseball/):
    - {year}_mlb_bat_tracking_games.csv    one row per (game_date, batter)
    - {year}_mlb_pitch_tracking_games.csv  one row per (game_date, pitcher)
    Both dedup on (game_date, mlbam_id). Safe to re-run; incremental.

Usage:
    python fetch_statcast_savant_games.py                 # incremental from last date
    python fetch_statcast_savant_games.py --backfill      # from season start
    python fetch_statcast_savant_games.py --start-date 2026-06-01 --date 2026-06-10
    python fetch_statcast_savant_games.py --dry-run
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fantasy_baseball import mlb_processing as mp

HEADERS = {"User-Agent": "Mozilla/5.0 (acn fantasy_baseball statcast-games; contact peter.rigali)"}

SEASON_START = {2023: date(2023, 3, 30), 2024: date(2024, 3, 20),
                2025: date(2025, 3, 20), 2026: date(2026, 3, 26)}
# Regular-season end per season (hfGT=R| excludes postseason anyway; this just bounds
# a past-season backfill so it doesn't iterate empty dates through to today).
SEASON_END = {2023: date(2023, 10, 2), 2024: date(2024, 9, 30), 2025: date(2025, 9, 29)}

SEARCH_URL = ("https://baseballsavant.mlb.com/statcast_search/csv"
              "?all=true&type=details&hfGT=R%7C"
              "&game_date_gt={d}&game_date_lt={d}")

HARD_SWING_MPH = 75.0   # Savant "fast swing" threshold (== hard_swing_rate definition)
HARD_HIT_MPH = 95.0     # Savant hard-hit threshold (exit velocity)
BARREL_CODE = 6         # launch_speed_angle code for a barrel
FASTBALLS = {"FF", "SI"}  # true fastballs for fb velo/spin
WHIFF_DESC = {"swinging_strike", "swinging_strike_blocked"}

BAT_COLS = ["game_date", "scoring_period", "mlbam_id", "player_name", "game_pks",
            "pitches_seen", "swings", "avg_bat_speed", "max_bat_speed", "avg_swing_length",
            "hard_swings", "hard_swing_rate", "batted_balls", "avg_launch_speed",
            "max_launch_speed", "hard_hits", "hard_hit_rate", "barrels", "barrel_rate",
            "hr", "pa"]
PIT_COLS = ["game_date", "scoring_period", "mlbam_id", "player_name", "game_pks",
            "pitches", "fb_count", "fb_velo_avg", "fb_velo_max", "fb_spin_avg",
            "velo_avg_all", "swinging_strikes", "called_strikes", "csw_rate",
            "pa_against", "k", "hr_allowed"]


def fnum(v):
    v = (v or "").strip()
    if v in ("", "null", "NA", "nan"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def scoring_period(d, season):
    start = SEASON_START.get(season, date(season, 3, 26))
    try:
        return max(1, (datetime.strptime(d, "%Y-%m-%d").date() - start).days + 1)
    except ValueError:
        return 0


def load_name_map():
    path = os.path.join(mp.DATA_PATH, "player_map.csv")
    names = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                mid = (r.get("mlbam_player_id") or "").strip()
                if mid:
                    names[mid] = r.get("mlb_name") or r.get("espn_name") or ""
    return names


def fetch_day(d):
    """Return list of pitch dicts for a single date, or [] on empty/error."""
    url = SEARCH_URL.format(d=d)
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=120)
            resp.raise_for_status()
            text = resp.content.decode("utf-8-sig", "replace")
            rows = list(csv.DictReader(text.splitlines()))
            # Savant occasionally echoes a header-only or error body; guard it.
            return [r for r in rows if r.get("game_pk")]
        except Exception as e:  # noqa: BLE001
            if attempt == 2:
                print(f"    [!] {d}: giving up after error: {e}")
                return []
            time.sleep(2 ** attempt)
    return []


def aggregate_day(pitches, season, names):
    """Aggregate one day's pitch rows into (bat_rows, pit_rows)."""
    bat = defaultdict(list)
    pit = defaultdict(list)
    for r in pitches:
        b = (r.get("batter") or "").strip()
        p = (r.get("pitcher") or "").strip()
        if b:
            bat[b].append(r)
        if p:
            pit[p].append(r)

    d = pitches[0]["game_date"]
    sp = scoring_period(d, season)
    bat_rows, pit_rows = [], []

    for mid, rs in bat.items():
        bs = [fnum(r.get("bat_speed")) for r in rs]
        bs = [v for v in bs if v is not None]
        sl = [fnum(r.get("swing_length")) for r in rs if fnum(r.get("swing_length")) is not None]
        ls = [fnum(r.get("launch_speed")) for r in rs if fnum(r.get("launch_speed")) is not None]
        barrels = sum(1 for r in rs if fnum(r.get("launch_speed_angle")) == BARREL_CODE)
        hard_sw = sum(1 for v in bs if v >= HARD_SWING_MPH)
        hard_hit = sum(1 for v in ls if v >= HARD_HIT_MPH)
        evs = [(r.get("events") or "").strip() for r in rs]
        evs = [e for e in evs if e]
        bat_rows.append({
            "game_date": d, "scoring_period": sp, "mlbam_id": mid,
            "player_name": names.get(mid, (rs[0].get("player_name") or "")),
            "game_pks": len({r.get("game_pk") for r in rs}),
            "pitches_seen": len(rs), "swings": len(bs),
            "avg_bat_speed": round(sum(bs) / len(bs), 2) if bs else "",
            "max_bat_speed": round(max(bs), 2) if bs else "",
            "avg_swing_length": round(sum(sl) / len(sl), 2) if sl else "",
            "hard_swings": hard_sw,
            "hard_swing_rate": round(hard_sw / len(bs), 3) if bs else "",
            "batted_balls": len(ls),
            "avg_launch_speed": round(sum(ls) / len(ls), 1) if ls else "",
            "max_launch_speed": round(max(ls), 1) if ls else "",
            "hard_hits": hard_hit,
            "hard_hit_rate": round(hard_hit / len(ls), 3) if ls else "",
            "barrels": barrels,
            "barrel_rate": round(barrels / len(ls), 3) if ls else "",
            "hr": sum(1 for e in evs if e == "home_run"),
            "pa": len(evs),
        })

    for mid, rs in pit.items():
        velo_all = [fnum(r.get("release_speed")) for r in rs if fnum(r.get("release_speed")) is not None]
        fb = [r for r in rs if (r.get("pitch_type") or "").strip() in FASTBALLS]
        fb_v = [fnum(r.get("release_speed")) for r in fb if fnum(r.get("release_speed")) is not None]
        fb_s = [fnum(r.get("release_spin_rate")) for r in fb if fnum(r.get("release_spin_rate")) is not None]
        descs = [(r.get("description") or "").strip() for r in rs]
        swstr = sum(1 for x in descs if x in WHIFF_DESC)
        called = sum(1 for x in descs if x == "called_strike")
        evs = [(r.get("events") or "").strip() for r in rs]
        evs = [e for e in evs if e]
        pit_rows.append({
            "game_date": d, "scoring_period": sp, "mlbam_id": mid,
            "player_name": names.get(mid, ""),
            "game_pks": len({r.get("game_pk") for r in rs}),
            "pitches": len(rs), "fb_count": len(fb),
            "fb_velo_avg": round(sum(fb_v) / len(fb_v), 1) if fb_v else "",
            "fb_velo_max": round(max(fb_v), 1) if fb_v else "",
            "fb_spin_avg": round(sum(fb_s) / len(fb_s), 0) if fb_s else "",
            "velo_avg_all": round(sum(velo_all) / len(velo_all), 1) if velo_all else "",
            "swinging_strikes": swstr, "called_strikes": called,
            "csw_rate": round((swstr + called) / len(rs), 3) if rs else "",
            "pa_against": len(evs),
            "k": sum(1 for e in evs if e in ("strikeout", "strikeout_double_play")),
            "hr_allowed": sum(1 for e in evs if e == "home_run"),
        })

    return bat_rows, pit_rows


def load_existing(path):
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    return rows


def last_valid_date(rows, season, min_players=20):
    """Most recent game_date with >= min_players rows and not in the future."""
    today = date.today().strftime("%Y-%m-%d")
    counts = defaultdict(int)
    for r in rows:
        counts[r["game_date"]] += 1
    valid = [d for d, c in counts.items() if d <= today and c >= min_players]
    return max(valid) if valid else None


def merge(existing, new_rows, refetch_from):
    """Keep existing rows strictly before refetch_from; append fresh new_rows; sort."""
    kept = [r for r in existing if r["game_date"] < refetch_from]
    out = kept + new_rows
    out.sort(key=lambda r: (r["game_date"], str(r["mlbam_id"])))
    return out


def write_csv(path, rows, cols, existed):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Game-level Statcast tracking aggregates (batters + pitchers)")
    ap.add_argument("--year", type=int, default=datetime.now().year)
    ap.add_argument("--start-date", type=str, default=None, help="override start YYYY-MM-DD")
    ap.add_argument("--date", type=str, default=None, help="override end YYYY-MM-DD")
    ap.add_argument("--backfill", action="store_true", help="start from season start")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    season = args.year
    bat_path = os.path.join(mp.DATA_PATH, f"{season}_mlb_bat_tracking_games.csv")
    pit_path = os.path.join(mp.DATA_PATH, f"{season}_mlb_pitch_tracking_games.csv")

    # end date: explicit override > past-season regular-season end > time-of-day (current)
    if args.date:
        end = args.date
    elif season < datetime.now().year:
        end = SEASON_END.get(season, date(season, 10, 15)).strftime("%Y-%m-%d")
    elif datetime.now().hour < 12:
        end = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        end = date.today().strftime("%Y-%m-%d")

    existing_bat = load_existing(bat_path)
    existing_pit = load_existing(pit_path)

    season_start = SEASON_START.get(season, date(season, 3, 26)).strftime("%Y-%m-%d")
    if args.start_date:
        start = args.start_date
    elif args.backfill:
        start = season_start
    else:
        lv = last_valid_date(existing_bat, season)
        start = lv if lv else season_start  # 1-day overlap (re-aggregated)

    if start > end:
        print(f"[OK]    fetch_statcast_savant_games: nothing to do (start {start} > end {end})")
        return

    # iterate dates
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    names = load_name_map()
    new_bat, new_pit = [], []
    days = (d1 - d0).days + 1
    print(f"  Range {start} -> {end} ({days} dates){' [DRY-RUN]' if args.dry_run else ''}")
    for i in range(days):
        d = (d0 + timedelta(days=i)).strftime("%Y-%m-%d")
        pitches = fetch_day(d)
        if not pitches:
            print(f"    {d}: no games")
            time.sleep(1.0)
            continue
        b, p = aggregate_day(pitches, season, names)
        new_bat.extend(b)
        new_pit.extend(p)
        print(f"    {d}: {len(pitches)} pitches -> {len(b)} batters, {len(p)} pitchers")
        time.sleep(1.0)

    out_bat = merge(existing_bat, new_bat, start)
    out_pit = merge(existing_pit, new_pit, start)

    if args.dry_run:
        print(f"[DRY-RUN] batters: +{len(new_bat)} new rows (total would be {len(out_bat)})")
        print(f"[DRY-RUN] pitchers: +{len(new_pit)} new rows (total would be {len(out_pit)})")
        return

    write_csv(bat_path, out_bat, BAT_COLS, bool(existing_bat))
    write_csv(pit_path, out_pit, PIT_COLS, bool(existing_pit))
    print(f"[OK]    fetch_statcast_savant_games: batters {len(new_bat)} new / {len(out_bat)} total | "
          f"pitchers {len(new_pit)} new / {len(out_pit)} total | {start} -> {end}")

    # run log
    try:
        import json
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "data-lake", "00_Logs", "fantasy_baseball")
        os.makedirs(log_dir, exist_ok=True)
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "workflow": "fantasy-collect-statcast-games",
            "status": "ok",
            "bat_rows_written": len(new_bat), "bat_total": len(out_bat),
            "pit_rows_written": len(new_pit), "pit_total": len(out_pit),
            "range_start": start, "range_end": end,
        }
        with open(os.path.join(log_dir, "fantasy-collect-statcast-games.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[WARN] run-log write failed: {e}")


if __name__ == "__main__":
    main()
