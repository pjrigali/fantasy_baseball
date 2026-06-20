"""
Description:
    Cross-checks player_lookup.csv against every MLB stats file in the data-lake to
    find players that appear in the stats data but are missing from (or mismatched in)
    the lookup table. Also adds any new archive-name entries discovered in files other
    than 2026_mlb_stats_daily_archive.csv and writes an updated player_lookup.csv.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/player_lookup.csv
    - data-lake/01_Bronze/fantasy_baseball/2023_mlb_stats_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2024_mlb_stats_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2025_mlb_stats_daily.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_stats_daily_archive.csv
    - data-lake/01_Bronze/fantasy_baseball/2026_mlb_stats_boxscore.csv
    - data-lake/01_Bronze/fantasy_baseball/2023_mlb_hitting_season_20260216.csv
    - data-lake/01_Bronze/fantasy_baseball/2024_mlb_hitting_season_20260216.csv
    - data-lake/01_Bronze/fantasy_baseball/2025_mlb_hitting_season_20260215.csv
    - data-lake/01_Bronze/fantasy_baseball/2023_mlb_pitching_season_20260216.csv
    - data-lake/01_Bronze/fantasy_baseball/2024_mlb_pitching_season_20260216.csv
    - data-lake/01_Bronze/fantasy_baseball/2025_mlb_pitching_season_20260215.csv

Outputs:
    - data-lake/01_Bronze/fantasy_baseball/player_lookup.csv  (updated in-place)
    - Console report: matched / new / unresolved counts per file
"""

import csv
import os
import unicodedata
from collections import defaultdict

BASE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball"
LOOKUP_PATH = os.path.join(BASE, "player_lookup.csv")

_SUFFIXES = {" jr.", " sr.", " ii", " iii", " iv"}


def normalize(s: str) -> str:
    n = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower().strip()
    for suffix in _SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
            break
    return n


def detect_encoding(path: str) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                f.read(8192)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


# ── File catalogue ────────────────────────────────────────────────────────────
# Each entry: (filename, name_column, id_column, type_hint)
# type_hint: 'batter', 'pitcher', or None (mixed / unknown)
FILE_CATALOGUE = [
    ("2023_mlb_stats_daily.csv",        "playerName", "playerId",   None),
    ("2024_mlb_stats_daily.csv",        "playerName", "playerId",   None),
    ("2025_mlb_stats_daily.csv",        "playerName", "playerId",   None),
    ("2026_mlb_stats_daily_archive.csv","player_name","player_id",  None),
    ("2026_mlb_stats_boxscore.csv",     "player_name","player_id",  None),
    ("2023_mlb_hitting_season_20260216.csv",   "player_name","player_id",  "batter"),
    ("2024_mlb_hitting_season_20260216.csv",   "player_name","player_id",  "batter"),
    ("2025_mlb_hitting_season_20260215.csv",   "player_name","player_id",  "batter"),
    ("2023_mlb_pitching_season_20260216.csv",  "player_name","player_id",  "pitcher"),
    ("2024_mlb_pitching_season_20260216.csv",  "player_name","player_id",  "pitcher"),
    ("2025_mlb_pitching_season_20260215.csv",  "player_name","player_id",  "pitcher"),
]

# ── Load existing lookup ──────────────────────────────────────────────────────
existing_rows: list[dict] = []
by_norm_espn: dict[str, dict] = {}
by_norm_archive: dict[str, dict] = {}

with open(LOOKUP_PATH, encoding="utf-8") as f:
    for row in csv.DictReader(f):
        existing_rows.append(row)
        if row["espn_name"]:
            by_norm_espn[normalize(row["espn_name"])] = row
        if row["archive_name"]:
            by_norm_archive[normalize(row["archive_name"])] = row

print(f"Loaded lookup: {len(existing_rows)} rows")
print(f"  ESPN-keyed entries:    {len(by_norm_espn)}")
print(f"  Archive-keyed entries: {len(by_norm_archive)}")
print()

# ── Cross-check each file ─────────────────────────────────────────────────────
# Collect all unique names from all stats files for deduplication
all_stats_names: dict[str, dict] = {}  # norm -> {raw, sources, b_or_p}

for fname, name_col, id_col, type_hint in FILE_CATALOGUE:
    path = os.path.join(BASE, fname)
    enc = detect_encoding(path)
    file_names: dict[str, tuple[str, str]] = {}  # norm -> (raw, player_id)

    with open(path, encoding=enc) as f:
        for row in csv.DictReader(f):
            raw = row.get(name_col, "").strip()
            pid = row.get(id_col, "").strip()
            if not raw:
                continue
            norm = normalize(raw)
            if norm not in file_names:
                file_names[norm] = (raw, pid)

    matched = sum(1 for n in file_names if n in by_norm_espn or n in by_norm_archive)
    new_names = {n: v for n, v in file_names.items()
                 if n not in by_norm_espn and n not in by_norm_archive}

    print(f"{fname}")
    print(f"  Unique players: {len(file_names):4d} | Matched: {matched:4d} | New (not in lookup): {len(new_names):4d}")

    for norm, (raw, pid) in file_names.items():
        if norm not in all_stats_names:
            all_stats_names[norm] = {
                "raw": raw,
                "player_id": pid,
                "sources": [fname],
                "b_or_p": type_hint or "",
            }
        else:
            if fname not in all_stats_names[norm]["sources"]:
                all_stats_names[norm]["sources"].append(fname)
            # Prefer a definitive type over None
            if not all_stats_names[norm]["b_or_p"] and type_hint:
                all_stats_names[norm]["b_or_p"] = type_hint

print()

# ── Identify new entries to add to lookup ────────────────────────────────────
new_entries: list[dict] = []
for norm, info in sorted(all_stats_names.items()):
    in_espn = norm in by_norm_espn
    in_arch = norm in by_norm_archive

    if not in_espn and not in_arch:
        # Genuinely new — add as archive-only row
        new_entries.append({
            "espn_player_id": "",
            "espn_name": "",
            "archive_name": info["raw"],
            "b_or_p": info["b_or_p"],
            "statcast_player_id": info["player_id"],
        })
    elif not in_arch and in_espn:
        # Known ESPN player but no archive name mapped yet — update the existing row
        existing_row = by_norm_espn[norm]
        if not existing_row["archive_name"]:
            existing_row["archive_name"] = info["raw"]
            if not existing_row["b_or_p"] and info["b_or_p"]:
                existing_row["b_or_p"] = info["b_or_p"]
            if not existing_row["statcast_player_id"] and info["player_id"]:
                existing_row["statcast_player_id"] = info["player_id"]

print(f"Truly new players (not in lookup at all): {len(new_entries)}")
print(f"Existing rows enriched with new archive_name or type: (see below)")

enriched = sum(
    1 for r in existing_rows
    if r["espn_name"] and r["archive_name"]
    and r not in existing_rows  # track in-place mutations above
)

# ── Write updated lookup ──────────────────────────────────────────────────────
all_rows = existing_rows + new_entries
fieldnames = ["espn_player_id", "espn_name", "archive_name", "b_or_p", "statcast_player_id"]

with open(LOOKUP_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

print(f"\nUpdated player_lookup.csv:")
print(f"  Previous rows:  {len(existing_rows)}")
print(f"  New rows added: {len(new_entries)}")
print(f"  Total rows:     {len(all_rows)}")

# ── Summary: players in lookup with ESPN name but still no archive name ────────
still_espn_only = [r for r in all_rows if r["espn_name"] and not r["archive_name"]]
print(f"\nESPN players still with no archive name: {len(still_espn_only)}")
for r in still_espn_only[:20]:
    print(f"  {r['espn_name']}")
if len(still_espn_only) > 20:
    print(f"  ... and {len(still_espn_only) - 20} more")

# ── Summary: players that appear in stats but have no ESPN mapping ─────────────
archive_only = [r for r in all_rows if not r["espn_name"] and r["archive_name"]]
print(f"\nArchive-only players (no ESPN mapping): {len(archive_only)}")
