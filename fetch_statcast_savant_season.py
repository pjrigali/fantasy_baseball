"""
Fetch Baseball Savant Statcast leaderboards (bat tracking + pitch arsenals) per season.

Description:
    Pulls season-level Statcast leaderboards from Baseball Savant for the
    fantasy_baseball project (origin: Idea 12 — bat tracking & Statcast predictors).
    Two leaderboards:
      1. Bat tracking (batters): swing speed, squared-up %, blast rate, swing
         length, whiff/swing, etc. Available 2023+ (2020-2022 return empty).
      2. Pitch arsenals (pitchers): per-pitch-type average velocity and average
         spin, merged into one row per pitcher-season.
    Each leaderboard is a season-to-date AGGREGATE that Savant refreshes daily but
    that moves slowly once players accrue a few weeks of data — so this is run
    WEEKLY, not daily, as a gated step of fantasy-collect-all-data. The response
    carries a UTF-8 BOM (decoded utf-8-sig). The player id columns (`id` for
    batters, `pitcher` for pitchers) are MLBAM ids — the join key to player_map.csv.

    Default scope is the CURRENT season only (historical seasons are static); pass
    --backfill to (re)pull 2023..current. Empty/failed seasons are logged and
    skipped, never fatal.

Source Data:
    - https://baseballsavant.mlb.com/leaderboard/bat-tracking?...&csv=true  (batters)
    - https://baseballsavant.mlb.com/leaderboard/pitch-arsenals?...&csv=true (pitchers)

Outputs (data-lake/01_Bronze/fantasy_baseball/):
    - {YEAR}_mlb_bat_tracking_season.csv   - raw bat-tracking leaderboard per season
    - {YEAR}_mlb_pitch_tracking_season.csv - per-pitcher velocity+spin merged per season
    Run log: data-lake/00_Logs/fantasy_baseball/fetch_statcast_savant_<timestamp>.log

Usage:
    python fetch_statcast_savant_season.py                 # current season only
    python fetch_statcast_savant_season.py --year 2026     # explicit season
    python fetch_statcast_savant_season.py --backfill      # 2023..current (historical)
    python fetch_statcast_savant_season.py --weekly        # skip if run within 7 days
    python fetch_statcast_savant_season.py --dry-run       # fetch + count, write nothing
"""

import argparse
import csv
import glob
import io
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

FIRST_YEAR = 2023
CURRENT_YEAR = date.today().year

REPO_ROOT = Path(__file__).resolve().parents[1]
BRONZE = REPO_ROOT / "data-lake" / "01_Bronze" / "fantasy_baseball"
LOG_DIR = REPO_ROOT / "data-lake" / "00_Logs" / "fantasy_baseball"

USER_AGENT = "Mozilla/5.0 (acn fantasy_baseball statcast research; contact peter.rigali)"
REQUEST_DELAY_S = 2.0
TIMEOUT_S = 90

BAT_URL = (
    "https://baseballsavant.mlb.com/leaderboard/bat-tracking"
    "?attempts=50&minSwings=q&minGroupSwings=1"
    "&seasonStart={y}&seasonEnd={y}&type=batter&sort=4&sortDir=desc&csv=true"
)
ARSENAL_URL = (
    "https://baseballsavant.mlb.com/leaderboard/pitch-arsenals"
    "?year={y}&min=100&type={metric}&hand=&csv=true"
)

_log_lines = []


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line)
    _log_lines.append(line)


def recent_run_within(days):
    """True if a fetch_statcast_savant_*.log exists with a timestamp newer than `days` ago."""
    cutoff = datetime.now() - timedelta(days=days)
    newest = None
    for p in glob.glob(str(LOG_DIR / "fetch_statcast_savant_*.log")):
        m = re.search(r"(\d{8}_\d{6})", os.path.basename(p))
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
        except ValueError:
            continue
        if newest is None or ts > newest:
            newest = ts
    return (newest is not None and newest >= cutoff), newest


def fetch_csv(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    raw = urllib.request.urlopen(req, timeout=TIMEOUT_S).read().decode("utf-8-sig", "replace")
    return list(csv.DictReader(io.StringIO(raw)))


def write_rows(path, rows):
    if not rows:
        return 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def fetch_bat_tracking(year, dry_run):
    rows = fetch_csv(BAT_URL.format(y=year))
    if not rows:
        log(f"  bat-tracking {year}: 0 rows (no data this season) - skipped")
        return
    if dry_run:
        log(f"  [DRY-RUN] bat-tracking {year}: {len(rows)} rows (not written)")
        return
    out = BRONZE / f"{year}_mlb_bat_tracking_season.csv"
    log(f"  bat-tracking {year}: {write_rows(out, rows)} rows -> {out.name}")


def fetch_pitch_arsenals(year, dry_run):
    velo = fetch_csv(ARSENAL_URL.format(y=year, metric="avg_speed"))
    time.sleep(REQUEST_DELAY_S)
    spin = fetch_csv(ARSENAL_URL.format(y=year, metric="avg_spin"))
    if not velo and not spin:
        log(f"  pitch-arsenals {year}: 0 rows (no data this season) - skipped")
        return
    merged = {}
    for r in velo:
        pid = (r.get("pitcher") or "").strip()
        if pid:
            merged[pid] = dict(r)
    for r in spin:
        pid = (r.get("pitcher") or "").strip()
        if not pid:
            continue
        if pid in merged:
            for k, v in r.items():
                if k not in ("pitcher", "last_name, first_name"):
                    merged[pid][k] = v
        else:
            merged[pid] = dict(r)
    rows = list(merged.values())
    if dry_run:
        log(f"  [DRY-RUN] pitch-arsenals {year}: velo={len(velo)} spin={len(spin)} merged={len(rows)} (not written)")
        return
    out = BRONZE / f"{year}_mlb_pitch_tracking_season.csv"
    log(f"  pitch-arsenals {year}: velo={len(velo)} spin={len(spin)} merged={write_rows(out, rows)} -> {out.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=CURRENT_YEAR, help="season to fetch (default: current)")
    ap.add_argument("--backfill", action="store_true", help="fetch all seasons 2023..current")
    ap.add_argument("--weekly", action="store_true", help="skip if a run log exists within the last 7 days")
    ap.add_argument("--dry-run", action="store_true", help="fetch and count rows but write nothing")
    args = ap.parse_args()

    if args.weekly:
        recent, when = recent_run_within(7)
        if recent:
            print(f"[statcast] last run {when:%Y-%m-%d %H:%M} (< 7 days ago) — weekly gate: skipping.")
            return 0

    seasons = list(range(FIRST_YEAR, CURRENT_YEAR + 1)) if args.backfill else [args.year]
    BRONZE.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Fetch start - seasons {seasons}{' [DRY-RUN]' if args.dry_run else ''}")

    for year in seasons:
        log(f"Season {year}")
        try:
            fetch_bat_tracking(year, args.dry_run)
        except Exception as e:  # noqa: BLE001 - log and continue per season
            log(f"  bat-tracking {year}: ERROR {type(e).__name__}: {e}")
        time.sleep(REQUEST_DELAY_S)
        try:
            fetch_pitch_arsenals(year, args.dry_run)
        except Exception as e:  # noqa: BLE001
            log(f"  pitch-arsenals {year}: ERROR {type(e).__name__}: {e}")
        time.sleep(REQUEST_DELAY_S)

    log("Fetch complete")
    if not args.dry_run:
        log_path = LOG_DIR / f"fetch_statcast_savant_{datetime.now():%Y%m%d_%H%M%S}.log"
        log_path.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
        print(f"Log written: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
