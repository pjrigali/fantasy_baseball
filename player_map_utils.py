"""
Description:
    Canonical loader for the single source of truth player identity file
    (player_map.csv). Supersedes player_lookup_utils.py. Loads the file once and
    resolves a player by ESPN id, MLBAM id, or name, exposing ID-centric getters
    plus the ESPN<->MLBAM bridge that lets downstream code join ESPN data and MLB
    stats BY ID instead of by fuzzy name.

    The legacy name-centric helpers (get_archive_name, get_b_or_p, get_espn_name,
    get_espn_id, get_statcast_id) are kept as thin aliases so existing consumers
    migrate with a one-line import swap.

Source Data:
    - data-lake/01_Bronze/fantasy_baseball/player_map.csv
      Columns: mlbam_player_id, espn_player_id, mlb_name, espn_name,
               normalized_name, b_or_p, primary_position, eligible_slots, pro_team,
               id_source, seen_in, first_seen_year, last_seen_year, last_verified_date

Outputs:
    - In-memory helpers; no files written.

Usage:
    from fantasy_baseball.player_map_utils import (
        get_mlbam_id, get_espn_id, get_mlb_name, get_b_or_p,
        espn_id_to_mlbam, mlbam_to_record,
    )

    mlbam = get_mlbam_id(espn_player_id="41217")   # ESPN Rocchio -> "677587"
    rec   = resolve(mlbam_id="677587")             # full identity record
    borp  = get_b_or_p("Andres Munoz")             # "pitcher"
"""

import csv
import os
import unicodedata

_MAP_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data-lake", "01_Bronze",
    "fantasy_baseball", "player_map.csv",
)

_SUFFIXES = (" jr.", " sr.", " ii", " iii", " iv")

# Module-level caches (loaded once)
_rows = []
_by_espn = {}      # espn_player_id -> row
_by_mlbam = {}     # mlbam_player_id -> row
_by_norm = {}      # normalized_name -> row (first wins)


def _normalize(s):
    n = "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower().strip()
    for suf in _SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
            break
    return n


def _load():
    if _rows:
        return
    path = os.path.abspath(_MAP_PATH)
    with open(path, encoding="utf-8", errors="replace") as f:
        for row in csv.DictReader(f):
            _rows.append(row)
            eid = (row.get("espn_player_id") or "").strip()
            mid = (row.get("mlbam_player_id") or "").strip()
            norm = (row.get("normalized_name") or "").strip() or _normalize(
                row.get("mlb_name") or row.get("espn_name") or "")
            if eid:
                _by_espn[eid] = row
            if mid:
                _by_mlbam[mid] = row
            if norm:
                _by_norm.setdefault(norm, row)
            # also index the ESPN spelling so an ESPN name lookup resolves
            en = _normalize(row.get("espn_name") or "")
            if en:
                _by_norm.setdefault(en, row)


# ── Core resolver ──────────────────────────────────────────────────────────────
def resolve(espn_id=None, mlbam_id=None, name=None):
    """Return the identity row for a player by ESPN id, MLBAM id, or name (in that
    priority). Returns None if not found."""
    _load()
    if espn_id is not None:
        r = _by_espn.get(str(espn_id).strip())
        if r:
            return r
    if mlbam_id is not None:
        r = _by_mlbam.get(str(mlbam_id).strip())
        if r:
            return r
    if name is not None:
        r = _by_norm.get(_normalize(name))
        if r:
            return r
    return None


# ── ID-centric getters (the intended canonical API) ────────────────────────────
def get_mlbam_id(espn_id=None, name=None):
    """MLBAM/statcast id for a player by ESPN id or name; '' if unknown."""
    r = resolve(espn_id=espn_id, name=name)
    return (r.get("mlbam_player_id") or "") if r else ""


def get_espn_id_by_mlbam(mlbam_id):
    """ESPN id for a player by MLBAM id; '' if unknown."""
    r = resolve(mlbam_id=mlbam_id)
    return (r.get("espn_player_id") or "") if r else ""


def get_mlb_name(espn_id=None, name=None):
    """Accented MLB/archive name by ESPN id or (ESPN/MLB) name; '' if unknown."""
    r = resolve(espn_id=espn_id, name=name)
    return (r.get("mlb_name") or "") if r else ""


def get_record_b_or_p(espn_id=None, mlbam_id=None, name=None):
    r = resolve(espn_id=espn_id, mlbam_id=mlbam_id, name=name)
    return (r.get("b_or_p") or "") if r else ""


# ── Bridge dictionaries (build joins BY ID) ────────────────────────────────────
def espn_id_to_mlbam():
    """dict: espn_player_id (str) -> mlbam_player_id (str), only where both exist."""
    _load()
    return {r["espn_player_id"].strip(): r["mlbam_player_id"].strip()
            for r in _rows
            if (r.get("espn_player_id") or "").strip() and (r.get("mlbam_player_id") or "").strip()}


def mlbam_to_record():
    """dict: mlbam_player_id (str) -> full identity row."""
    _load()
    return dict(_by_mlbam)


def espn_id_to_norm_name():
    """dict: espn_player_id (str) -> normalized MLB name.

    Backward-compatible replacement for the old player_lookup_utils
    `espn_id -> normalize(archive_name)` map, for name-keyed game-log joins."""
    _load()
    out = {}
    for r in _rows:
        eid = (r.get("espn_player_id") or "").strip()
        norm = (r.get("normalized_name") or "").strip() or _normalize(r.get("mlb_name") or "")
        if eid and norm:
            out[eid] = norm
    return out


# ── Legacy aliases (drop-in for player_lookup_utils.py) ────────────────────────
def get_archive_name(espn_name):
    """Accented MLB name for an ESPN name, or the input if not found."""
    r = resolve(name=espn_name)
    return (r.get("mlb_name") or espn_name) if r else espn_name


def get_espn_name(archive_name):
    """ESPN name for an accented MLB name, or the input if not found."""
    r = resolve(name=archive_name)
    return (r.get("espn_name") or archive_name) if r else archive_name


def get_b_or_p(espn_name):
    """'batter' / 'pitcher' / 'both' for a player by name; '' if not found."""
    r = resolve(name=espn_name)
    return (r.get("b_or_p") or "") if r else ""


def get_espn_id(espn_name):
    """ESPN id for a player by name; '' if not found."""
    r = resolve(name=espn_name)
    return (r.get("espn_player_id") or "") if r else ""


def get_statcast_id(espn_name):
    """Statcast/MLBAM id for a player by name; '' if not found.
    (Statcast id == MLBAM id in this dataset.)"""
    r = resolve(name=espn_name)
    return (r.get("mlbam_player_id") or "") if r else ""
