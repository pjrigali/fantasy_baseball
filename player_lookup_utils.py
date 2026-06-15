"""
Description:
    Utility helpers for resolving player names across data sources.
    Loads player_lookup.csv once and exposes functions to translate between
    ESPN names (plain ASCII) and archive names (accent-encoded UTF-8),
    and to check a player's type (batter/pitcher) from the archive.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/player_lookup.csv

Outputs:
    - In-memory helpers; no files written.

Usage:
    from fantasy_baseball.player_lookup_utils import get_archive_name, get_b_or_p

    archive_name = get_archive_name("Andres Munoz")   # -> "Andrés Muñoz"
    b_or_p       = get_b_or_p("Andres Munoz")         # -> "pitcher"
"""

import csv
import os
import unicodedata

_LOOKUP_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "data-lake",
    "01_Bronze",
    "fantasy_baseball",
    "player_lookup.csv",
)

_SUFFIXES = {" jr.", " sr.", " ii", " iii", " iv"}

# Module-level cache — loaded once on first use
_by_espn: dict[str, dict] = {}
_by_archive: dict[str, dict] = {}


def _normalize(s: str) -> str:
    n = "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    ).lower().strip()
    for suffix in _SUFFIXES:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
            break
    return n


def _load() -> None:
    if _by_espn:
        return
    path = os.path.abspath(_LOOKUP_PATH)
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["espn_name"]:
                _by_espn[_normalize(row["espn_name"])] = row
            if row["archive_name"]:
                _by_archive[_normalize(row["archive_name"])] = row


def get_archive_name(espn_name: str) -> str:
    """Return the accent-encoded archive name for an ESPN name, or the input if not found."""
    _load()
    row = _by_espn.get(_normalize(espn_name))
    if row and row["archive_name"]:
        return row["archive_name"]
    return espn_name  # fall back to the name as-is


def get_espn_name(archive_name: str) -> str:
    """Return the ESPN name for an archive name, or the input if not found."""
    _load()
    row = _by_archive.get(_normalize(archive_name))
    if row and row["espn_name"]:
        return row["espn_name"]
    return archive_name


def get_b_or_p(espn_name: str) -> str:
    """Return 'batter' or 'pitcher' for a player by ESPN name, or '' if not found."""
    _load()
    row = _by_espn.get(_normalize(espn_name))
    return row["b_or_p"] if row else ""


def get_espn_id(espn_name: str) -> str:
    """Return ESPN player ID for a player by name, or '' if not found."""
    _load()
    row = _by_espn.get(_normalize(espn_name))
    return row["espn_player_id"] if row else ""


def get_statcast_id(espn_name: str) -> str:
    """Return Statcast/MLB player ID for a player by ESPN name, or '' if not found."""
    _load()
    row = _by_espn.get(_normalize(espn_name))
    return row["statcast_player_id"] if row else ""
