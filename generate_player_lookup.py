"""
Description:
    Builds player_lookup.csv by cross-referencing player_map.csv (ESPN names / IDs)
    against stats_mlb_daily_2026_archive.csv (accent-encoded archive names).
    Normalizes both sides via accent-stripping + lowercase, then emits one row per
    matched player with both the ESPN name and the archive name. Unmatched players
    from each side are appended as partial rows so nothing is silently dropped.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/player_map.csv
    - data-lake/01_Bronze/fantasy_baseball/stats_mlb_daily_2026_archive.csv

Outputs:
    - data-lake/01_Bronze/fantasy_baseball/player_lookup.csv
      Columns: espn_player_id, espn_name, archive_name, b_or_p, statcast_player_id
"""

import csv
import unicodedata
import os

BASE = r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball"
MAP_PATH = os.path.join(BASE, "player_map.csv")
ARCHIVE_PATH = os.path.join(BASE, "stats_mlb_daily_2026_archive.csv")
OUT_PATH = os.path.join(BASE, "player_lookup.csv")


_SUFFIXES = {" jr.", " sr.", " ii", " iii", " iv"}


def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower().strip()


def normalize(s: str) -> str:
    """Accent-strip, lowercase, remove common name suffixes for matching."""
    n = strip_accents(s)
    for suffix in _SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
            break
    return n


def detect_encoding(path: str) -> str:
    """Try utf-8, fall back to cp1252."""
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                f.read(4096)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


# ── 1. Load player_map: keyed by normalized full_name ───────────────────────
map_enc = detect_encoding(MAP_PATH)
espn_players: dict[str, dict] = {}  # normalized_name -> row
with open(MAP_PATH, encoding=map_enc) as f:
    for row in csv.DictReader(f):
        norm = normalize(row["full_name"])
        espn_players[norm] = row

print(f"player_map rows loaded: {len(espn_players)}  (encoding: {map_enc})")

# ── 2. Load archive: one entry per unique player_name ───────────────────────
arch_enc = detect_encoding(ARCHIVE_PATH)
archive_players: dict[str, tuple[str, str]] = {}  # normalized -> (raw_name, b_or_p)
with open(ARCHIVE_PATH, encoding=arch_enc) as f:
    for row in csv.DictReader(f):
        name = row["player_name"].strip()
        borp = row["b_or_p"].strip()
        norm = normalize(name)
        if norm not in archive_players:
            archive_players[norm] = (name, borp)

print(f"Archive unique players: {len(archive_players)}  (encoding: {arch_enc})")

# ── 3. Match and build output rows ──────────────────────────────────────────
output_rows: list[dict] = []
matched_archive_keys: set[str] = set()

for norm, espn_row in sorted(espn_players.items(), key=lambda x: x[1]["full_name"]):
    espn_name = espn_row["full_name"].strip()
    espn_id = espn_row["espn_player_id"].strip()
    statcast_id = espn_row.get("statcast_player_id", "").strip()

    # Try exact normalized match, then try with common suffixes (archive may add them)
    arch_key = None
    if norm in archive_players:
        arch_key = norm
    else:
        for suffix in (" jr.", " sr.", " ii", " iii"):
            candidate = norm + suffix
            if candidate in archive_players:
                arch_key = candidate
                break

    if arch_key:
        arch_name, borp = archive_players[arch_key]
        matched_archive_keys.add(arch_key)
    else:
        arch_name = ""
        borp = ""

    output_rows.append(
        {
            "espn_player_id": espn_id,
            "espn_name": espn_name,
            "archive_name": arch_name,
            "b_or_p": borp,
            "statcast_player_id": statcast_id,
        }
    )

# Players in archive not in player_map (append with blank ESPN fields)
unmatched_archive = 0
for norm, (arch_name, borp) in sorted(archive_players.items()):
    if norm not in matched_archive_keys:
        output_rows.append(
            {
                "espn_player_id": "",
                "espn_name": "",
                "archive_name": arch_name,
                "b_or_p": borp,
                "statcast_player_id": "",
            }
        )
        unmatched_archive += 1

# ── 4. Write output ──────────────────────────────────────────────────────────
fieldnames = ["espn_player_id", "espn_name", "archive_name", "b_or_p", "statcast_player_id"]
with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(output_rows)

matched = sum(1 for r in output_rows if r["espn_name"] and r["archive_name"])
espn_only = sum(1 for r in output_rows if r["espn_name"] and not r["archive_name"])
print(f"\nResults:")
print(f"  Matched (ESPN + archive):  {matched}")
print(f"  ESPN-only (no archive):    {espn_only}")
print(f"  Archive-only (no ESPN):    {unmatched_archive}")
print(f"  Total rows:                {len(output_rows)}")
print(f"\nOutput: {OUT_PATH}")

# Show the key problem players from the prior session
check_names = [
    "Cristopher Sanchez", "Jesus Luzardo", "Aroldis Chapman",
    "Andres Munoz", "Ronald Acuna", "Julio Rodriguez",
    "Jose Ramirez", "Yandy Diaz", "Hunter Greene", "Travis Bazzana",
]
print("\nSpot-check players from prior session:")
lookup_by_espn = {normalize(r["espn_name"]): r for r in output_rows if r["espn_name"]}
for name in check_names:
    row = lookup_by_espn.get(strip_accents(name))
    if row:
        status = "MATCHED" if row["archive_name"] else "NO ARCHIVE MATCH"
        print(f"  {name:30s} -> archive: {row['archive_name']!r:35s}  [{status}]")
    else:
        print(f"  {name:30s} -> NOT IN player_map")
