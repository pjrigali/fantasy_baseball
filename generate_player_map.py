"""
Description:
    Single source of truth builder for player identity in the fantasy_baseball
    project. Establishes the canonical universe of MLB players who have appeared
    since 2023 (inclusion gate), enriches each with ESPN league identifiers, and
    resolves the ESPN <-> MLBAM id bridge so downstream joins are BY ID, not by
    fuzzy name. Replaces the old two-file system (player_map.csv legacy schema +
    player_lookup.csv) and the generate_player_lookup.py / crosscheck_player_lookup.py
    builders.

    Three systems are queried (per user directive: "call MLB, ESPN and statcast"):
      * MLB Stats API   - statsapi.mlb.com/api/v1/sports/1/players?season=YYYY for
                          2023..present gives the authoritative MLB universe with the
                          MLBAM id, full (accented) name, primary position, current
                          team and debut date. The authoritative primaryPosition is
                          also used to set b_or_p (this cleanly fixes the historical
                          Aroldis Chapman batter/pitcher mislabel).
      * ESPN            - the live ESPN league player_map (id <-> name universe) plus
                          all data-lake espn_* files and the preserved ESPN reference
                          (espn_player_universe.csv) for eligible_slots / pro_team /
                          any curated statcast ids.
      * statcast/people - statsapi people/search resolves MLBAM ids for the handful of
                          lineup-only names (no id in the lineups file) and bridges any
                          ESPN player whose accent-normalized name did not match.

    Inclusion gate: a player is written ONLY if they appear in at least one MLB stats
    source dated 2023+ (live season roster pull OR a data-lake MLB stats file).
    ESPN-only players with no 2023+ MLB presence (prospects, speculative adds) and
    pre-2023 retirees are EXCLUDED and reported, never written.

Source Data:
    LIVE:
      - https://statsapi.mlb.com/api/v1/sports/1/players?season={2023..present}
      - https://statsapi.mlb.com/api/v1/teams?sportId=1   (team id -> abbreviation)
      - https://statsapi.mlb.com/api/v1/people/search?names=... (bridge fallback)
      - ESPN fantasy league (via mlb_processing.setup_league / config.ini)
    DATA LAKE (data-lake/01_Bronze/fantasy_baseball/):
      MLB gate/provenance: {2023,2024,2025}_mlb_stats_daily.csv,
        2026_mlb_stats_daily_archive.csv, 2026_mlb_stats_boxscore.csv,
        {2023,2024,2025}_mlb_hitting_season_*.csv, *_mlb_pitching_season_*.csv,
        2026_mlb_closers_depth.csv, {2023..2026}_mlb_transactions_season.csv,
        2026_mlb_lineups_batters.csv
      ESPN enrichment: espn_player_universe.csv (preserved legacy map),
        2026_espn_rankings_daily.csv, {2025,2026}_espn_roster_season.csv / history,
        2026_espn_activity_season.csv, 2026_espn_draft_results.csv,
        2026_espn_best_pickups.csv, {2025,2026}_espn_stats_daily.csv

Outputs:
    - data-lake/01_Bronze/fantasy_baseball/player_map.csv   (canonical, overwritten)
      Columns: mlbam_player_id, espn_player_id, mlb_name, espn_name,
               normalized_name, b_or_p, primary_position, eligible_slots, pro_team,
               id_source, seen_in, first_seen_year, last_seen_year, last_verified_date
    - data-lake/00_Logs/fantasy_baseball/generate_player_map_{DATE}.log

Usage:
    python generate_player_map.py            # full build (calls all three systems)
    python generate_player_map.py --offline  # skip all network calls (data-lake only)
    python generate_player_map.py --dry-run  # compute + report, do NOT write the csv

Notes:
    No pandas (csv module only; rows are list[dict]). Idempotent: stable sort by
    normalized_name then mlbam id, deduped on mlbam id; safe to re-run as seasons
    and files arrive.
"""

import argparse
import csv
import glob
import json
import os
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO = r"C:\Users\peter.rigali\Desktop\acn_repo"
BASE = os.path.join(REPO, "data-lake", "01_Bronze", "fantasy_baseball")
LOG_DIR = os.path.join(REPO, "data-lake", "00_Logs", "fantasy_baseball")
OUT_PATH = os.path.join(BASE, "player_map.csv")
ESPN_REF_PATH = os.path.join(BASE, "espn_player_universe.csv")

FIRST_YEAR = 2023
CURRENT_YEAR = date.today().year

FIELDNAMES = [
    "mlbam_player_id", "espn_player_id", "mlb_name", "espn_name",
    "normalized_name", "b_or_p", "primary_position", "eligible_slots",
    "pro_team", "id_source", "seen_in", "first_seen_year", "last_seen_year",
    "last_verified_date",
]

_SUFFIXES = (" jr.", " sr.", " ii", " iii", " iv")
_USER_AGENT = {"User-Agent": "Mozilla/5.0"}

_log_lines = []


def log(msg=""):
    print(msg)
    _log_lines.append(str(msg))


# ── Name normalization (shared with the old lookup so coverage is comparable) ──
def strip_accents(s):
    return "".join(
        c for c in unicodedata.normalize("NFD", s or "")
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


def normalize(s):
    n = strip_accents(s)
    for suf in _SUFFIXES:
        if n.endswith(suf):
            n = n[: -len(suf)].strip()
            break
    return n


# ── Team abbreviation normalization ────────────────────────────────────────────
# ESPN and the MLB Stats API disagree on a handful of abbreviations and on case
# (ESPN "Sea"/"Oak"/"ChW" vs MLB "SEA"/"ATH"/"CWS"). Without canonicalizing both
# sides, the namesake pro_team tiebreaker in bridge() never fires and same-name
# players (e.g. the two Julio Rodriguezes) get assigned by recency guess. Map both
# sides to a common token; "FA"/blank collapse to "" so they never count as a match.
_TEAM_ALIAS = {
    "CHW": "CWS", "CWS": "CWS",
    "OAK": "ATH", "ATH": "ATH",
    "AZ": "ARI", "ARI": "ARI",
    "WSN": "WSH", "WSH": "WSH",
    "SDP": "SD", "SFG": "SF", "TBR": "TB", "KCR": "KC",
}


def normalize_team(t):
    u = (t or "").strip().upper()
    if u in ("", "FA", "--", "N/A", "NA", "NONE"):
        return ""
    return _TEAM_ALIAS.get(u, u)


def team_match(espn_rec, mlb_rec):
    a = normalize_team(espn_rec.get("pro_team"))
    b = normalize_team(mlb_rec.get("pro_team"))
    return bool(a) and a == b


def detect_encoding(path):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(path, encoding=enc) as f:
                f.read(8192)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def read_rows(path):
    if not os.path.exists(path):
        return None
    enc = detect_encoding(path)
    with open(path, encoding=enc, errors="replace") as f:
        return list(csv.DictReader(f))


def http_json(url):
    req = urllib.request.Request(url, headers=_USER_AGENT)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 2:
                log(f"  [!] giving up on {url}: {e}")
                return None
            time.sleep(2 ** attempt)
    return None


def year_from_filename(fname):
    base = os.path.basename(fname)
    if len(base) >= 4 and base[:4].isdigit():
        return int(base[:4])
    return None


# ── Data-lake MLB stats catalogue (gate + provenance). (id_col, name_col) ──────
def mlb_datalake_catalogue():
    cat = []
    patterns = [
        ("*_mlb_stats_daily.csv", "playerId", "playerName"),
        ("2026_mlb_stats_daily_archive.csv", "player_id", "player_name"),
        ("2026_mlb_stats_boxscore.csv", "player_id", "player_name"),
        ("*_mlb_hitting_season_*.csv", "player_id", "player_name"),
        ("*_mlb_pitching_season_*.csv", "player_id", "player_name"),
        ("*_mlb_closers_depth.csv", "player_id", "player_name"),
        ("*_mlb_transactions_season.csv", "player_id", "player_name"),
    ]
    for pat, idc, namec in patterns:
        for path in sorted(glob.glob(os.path.join(BASE, pat))):
            y = year_from_filename(path)
            if y is None or y < FIRST_YEAR:
                continue
            cat.append((path, idc, namec, y))
    return cat


def borp_from_filename(fname):
    f = os.path.basename(fname)
    if "hitting" in f:
        return "batter"
    if "pitching" in f or "closers" in f:
        return "pitcher"
    return ""


# ── Stage 1: MLB universe ──────────────────────────────────────────────────────
def borp_from_position(pos):
    """Map an MLB primaryPosition dict to b_or_p ('pitcher'|'batter'|'both')."""
    ptype = (pos or {}).get("type", "")
    abbr = (pos or {}).get("abbreviation", "")
    if ptype == "Two-Way Player" or abbr == "TWP":
        return "both"
    if ptype == "Pitcher" or abbr == "P":
        return "pitcher"
    return "batter"


def build_mlb_universe(offline, teams_map):
    """mlbam_id (str) -> record dict. Returns (universe, lineup_only_names)."""
    universe = {}

    def ensure(mlbam, name):
        rec = universe.get(mlbam)
        if rec is None:
            rec = {
                "mlbam_player_id": mlbam,
                "mlb_name": name,
                "normalized_name": normalize(name),
                "b_or_p": "",
                "primary_position": "",
                "pro_team": "",
                "years": set(),
                "seen_in": set(),
                "_borp_votes": defaultdict(int),
            }
            universe[mlbam] = rec
        return rec

    # 1a. Live MLB Stats API — authoritative per-season roster + position
    if not offline:
        for season in range(FIRST_YEAR, CURRENT_YEAR + 1):
            url = f"https://statsapi.mlb.com/api/v1/sports/1/players?season={season}"
            data = http_json(url)
            people = (data or {}).get("people", [])
            log(f"  MLB API sports/1/players season={season}: {len(people)} players")
            for p in people:
                mlbam = str(p.get("id", "")).strip()
                name = (p.get("fullName") or "").strip()
                if not mlbam or not name:
                    continue
                rec = ensure(mlbam, name)
                rec["mlb_name"] = name
                rec["normalized_name"] = normalize(name)
                pos = p.get("primaryPosition", {})
                borp = borp_from_position(pos)
                if borp:
                    # authoritative source gets a strong vote (fixes Chapman)
                    rec["_borp_votes"][borp] += 100
                if pos.get("abbreviation"):
                    rec["primary_position"] = pos.get("abbreviation")
                tid = (p.get("currentTeam") or {}).get("id")
                if tid and tid in teams_map:
                    rec["pro_team"] = teams_map[tid]
                rec["years"].add(season)
                rec["seen_in"].add(f"mlb_api:{season}")

    # 1b. Data-lake MLB stats files — gate union + provenance + b_or_p cross-check
    for path, idc, namec, y in mlb_datalake_catalogue():
        rows = read_rows(path)
        if not rows:
            continue
        fname = os.path.basename(path)
        file_borp = borp_from_filename(path)
        seen = 0
        for r in rows:
            mlbam = (r.get(idc) or "").strip()
            name = (r.get(namec) or "").strip()
            if not mlbam or not name:
                continue
            rec = ensure(mlbam, name)
            if not rec["mlb_name"]:
                rec["mlb_name"] = name
                rec["normalized_name"] = normalize(name)
            rec["years"].add(y)
            rec["seen_in"].add(fname)
            row_borp = (r.get("b_or_p") or "").strip() or file_borp
            if row_borp in ("batter", "pitcher"):
                rec["_borp_votes"][row_borp] += 1
            seen += 1
        log(f"  data-lake {fname:42s}: {seen} rows")

    # Resolve b_or_p: prefer pitcher on a batter/pitcher tie (Chapman safety net).
    for rec in universe.values():
        votes = rec["_borp_votes"]
        if votes.get("both", 0):
            rec["b_or_p"] = "both"
        elif votes.get("pitcher", 0) >= votes.get("batter", 0) and votes.get("pitcher", 0) > 0:
            rec["b_or_p"] = "pitcher"
        elif votes.get("batter", 0) > 0:
            rec["b_or_p"] = "batter"
        else:
            rec["b_or_p"] = ""

    # 1c. Lineup-only names (the lineups file has no id column)
    lineup_only = {}
    lu = read_rows(os.path.join(BASE, "2026_mlb_lineups_batters.csv"))
    if lu:
        by_norm = {rec["normalized_name"]: mlbam for mlbam, rec in universe.items()}
        for r in lu:
            nm = (r.get("player_name") or "").strip()
            if not nm:
                continue
            n = normalize(nm)
            if n not in by_norm:
                lineup_only.setdefault(n, nm)
    return universe, lineup_only


# ── Stage 2: ESPN side (espn_id -> name/slots/team, plus statcast bridge) ───────
def build_espn_side(offline):
    """Returns (by_norm, by_statcast, by_id) records: {espn_id, espn_name, eligible_slots, pro_team, statcast}."""
    by_id = {}

    def ensure(eid, name):
        rec = by_id.get(eid)
        if rec is None:
            rec = {"espn_player_id": eid, "espn_name": name,
                   "eligible_slots": "", "pro_team": "", "statcast": "", "borp": ""}
            by_id[eid] = rec
        elif name and not rec["espn_name"]:
            rec["espn_name"] = name
        return rec

    def set_borp(rec, raw, explicit):
        """Record b_or_p for an ESPN player. explicit=True for a literal
        batter/pitcher value; otherwise infer from a position abbreviation."""
        if rec["borp"]:
            return
        v = (raw or "").strip().lower()
        if not v:
            return
        if explicit:
            if v.startswith("p"):
                rec["borp"] = "pitcher"
            elif v.startswith("b") or v.startswith("h"):
                rec["borp"] = "batter"
        else:
            rec["borp"] = "pitcher" if v.upper() in ("P", "SP", "RP") else "batter"

    # 2a. Preserved legacy reference (richest: slots, pro_team, curated statcast)
    ref = read_rows(ESPN_REF_PATH) or read_rows(OUT_PATH) or []
    for r in ref:
        eid = (r.get("espn_player_id") or "").strip()
        name = (r.get("full_name") or r.get("espn_name") or "").strip()
        if not eid:
            continue
        rec = ensure(eid, name)
        slots = (r.get("player_eligible_slots") or r.get("eligible_slots") or "").strip()
        team = (r.get("player_pro_team") or r.get("pro_team") or "").strip()
        sc = (r.get("statcast_player_id") or "").strip()
        if slots and not rec["eligible_slots"]:
            rec["eligible_slots"] = slots
        if team and not rec["pro_team"]:
            rec["pro_team"] = team
        if sc and not rec["statcast"]:
            rec["statcast"] = sc
    log(f"  ESPN reference rows: {len(by_id)}")

    # 2b. Data-lake ESPN files — fill name/slots/team/borp gaps, add new espn ids.
    #     (fname, id_col, name_col, slot_col, team_col, borp_col, borp_explicit)
    espn_files = [
        ("2026_espn_best_pickups.csv", "player_id", "player_name", None, None, "player_type", True),
        ("2026_espn_stats_daily.csv", "player_id", "player_name", "eligible_slots", "pro_team", "player_type", True),
        ("2025_espn_stats_daily.csv", "playerId", "playerName", None, None, "b_or_p", True),
        ("2026_espn_rankings_daily.csv", "player_id", "player_name", "eligible_slots", "pro_team", "player_position", False),
        ("2026_espn_roster_season.csv", "player_id", "player_name", "player_eligible_slots", "player_pro_team", "player_position", False),
        ("2026_espn_activity_season.csv", "player_id", "player_name", None, None, None, False),
        ("2026_espn_draft_results.csv", "player_id", "player_name", None, None, None, False),
        ("2026_espn_roster_history.csv", "player_id", "player_name", None, None, None, False),
        ("2025_espn_roster_history.csv", "player_id", "player_name", None, None, None, False),
    ]
    for fname, idc, namec, slotc, teamc, borpc, borp_exp in espn_files:
        rows = read_rows(os.path.join(BASE, fname))
        if not rows:
            continue
        for r in rows:
            eid = (r.get(idc) or "").strip()
            name = (r.get(namec) or "").strip()
            if not eid:
                continue
            rec = ensure(eid, name)
            if slotc and (r.get(slotc) or "").strip() and not rec["eligible_slots"]:
                rec["eligible_slots"] = (r.get(slotc) or "").strip()
            if teamc and (r.get(teamc) or "").strip() and not rec["pro_team"]:
                rec["pro_team"] = (r.get(teamc) or "").strip()
            if borpc:
                set_borp(rec, r.get(borpc), borp_exp)

    # 2c. Live ESPN league universe (id <-> name) — augment with anyone missing
    if not offline:
        try:
            sys.path.insert(0, REPO)
            from fantasy_baseball import mlb_processing as mp
            cfg = mp.load_config()
            lg = mp.setup_league(cfg, year=CURRENT_YEAR)
            added = 0
            for k, v in getattr(lg, "player_map", {}).items():
                # espn_api player_map holds both id->name and name->id; keep id->name
                if isinstance(k, int) and isinstance(v, str):
                    eid = str(k)
                    if eid not in by_id:
                        ensure(eid, v)
                        added += 1
            log(f"  ESPN live league.player_map: +{added} new espn ids")
        except Exception as e:
            log(f"  [!] ESPN live fetch skipped: {e!r}")

    by_norm = {}
    by_statcast = {}
    for rec in by_id.values():
        n = normalize(rec["espn_name"])
        if n:
            by_norm.setdefault(n, rec)
        if rec["statcast"]:
            by_statcast.setdefault(rec["statcast"], rec)
    return by_norm, by_statcast, by_id


# ── Stage 3: bridge ESPN <-> MLBAM, attach to universe rows ────────────────────
def _espn_borp(espn_rec):
    """batter/pitcher for an ESPN player: explicit captured value if present,
    else inferred from eligible slots."""
    if espn_rec.get("borp"):
        return espn_rec["borp"]
    slots = (espn_rec.get("eligible_slots") or "").upper().split("|")
    if any(s in slots for s in ("P", "SP", "RP")):
        return "pitcher"
    return "batter"


def bridge(universe, lineup_only, espn_by_norm, espn_by_statcast, espn_by_id, offline):
    matched_espn = set()

    def attach(rec, espn, src):
        rec["espn_player_id"] = espn["espn_player_id"]
        rec["espn_name"] = espn["espn_name"]
        if espn["eligible_slots"]:
            rec["eligible_slots"] = espn["eligible_slots"]
        if espn["pro_team"] and not rec["pro_team"]:
            rec["pro_team"] = espn["pro_team"]
        rec["id_source"] = src
        matched_espn.add(espn["espn_player_id"])

    # init
    for rec in universe.values():
        rec["espn_player_id"] = ""
        rec["espn_name"] = ""
        rec["id_source"] = "mlb_only"

    # ESPN candidates grouped by normalized name (namesakes share a key)
    cand_by_norm = defaultdict(list)
    for rec in espn_by_id.values():
        n = normalize(rec["espn_name"])
        if n:
            cand_by_norm[n].append(rec)

    # 1. DIRECT: curated statcast id from the ESPN reference is authoritative.
    for mlbam, rec in universe.items():
        espn = espn_by_statcast.get(mlbam)
        if espn and espn["espn_player_id"] not in matched_espn:
            attach(rec, espn, "direct")

    # 2. NAME MATCH with namesake disambiguation. Two passes so that team-confirmed
    #    assignments are locked in GLOBALLY before any greedy fallback can grab a
    #    shared ESPN id. (A single per-mlbam greedy loop lets a wrong-team namesake
    #    that happens to be processed first claim an ESPN id that belongs to a
    #    team-matching player processed later -- the Luis Garcia HOU/MIN failure mode.)
    #    Each ESPN id is claimed at most once -> guarantees espn_player_id uniqueness.

    def borp_ok(e, rec):
        return (not rec["b_or_p"]) or rec["b_or_p"] == "both" or _espn_borp(e) == rec["b_or_p"]

    # 2a. TEAM-CONFIRMED pass: assign only where the ESPN player's team matches the
    #     MLB player's team (and b_or_p is compatible). This is the high-confidence
    #     signal and resolves namesakes (Julio Rodriguez SEA, the two Luis Garcias).
    for mlbam, rec in universe.items():
        if rec["espn_player_id"]:
            continue
        cands = [e for e in cand_by_norm.get(rec["normalized_name"], [])
                 if e["espn_player_id"] not in matched_espn
                 and team_match(e, rec) and borp_ok(e, rec)]
        if not cands:
            continue
        # almost always 1; if a team genuinely has two same-name same-hand players,
        # prefer the one whose b_or_p matches, else just take the first.
        cands.sort(key=lambda e: 1 if _espn_borp(e) == rec["b_or_p"] else 0, reverse=True)
        attach(rec, cands[0], "name_match")

    # 2b. FALLBACK pass: for still-unmatched players, take a unique-name match, or a
    #     b_or_p-matched namesake ranked by team (normalized) then recency.
    for mlbam, rec in universe.items():
        if rec["espn_player_id"]:
            continue
        cands = [e for e in cand_by_norm.get(rec["normalized_name"], [])
                 if e["espn_player_id"] not in matched_espn]
        if not cands:
            continue
        if len(cands) == 1:
            best = cands[0]
        else:
            # multiple namesakes: require a b_or_p match to avoid mis-assignment
            matching = [e for e in cands if _espn_borp(e) == rec["b_or_p"]]
            if not matching:
                continue
            last_year = max(rec.get("years") or {0})
            matching.sort(key=lambda e: (
                1 if team_match(e, rec) else 0,
                last_year,
            ), reverse=True)
            best = matching[0]
        attach(rec, best, "name_match")

    # 3. API bridge for ESPN players still unmatched: people/search their name and
    #    attach to a universe row that has no espn yet (catches spelling variants).
    #    Pre-filter to ESPN players whose surname matches an un-bridged MLB player's
    #    surname -- otherwise we'd fire thousands of searches at excluded prospects.
    if not offline:
        unbridged_surnames = set()
        for rec in universe.values():
            if not rec.get("espn_player_id"):
                toks = rec["normalized_name"].split()
                if toks:
                    unbridged_surnames.add(toks[-1])

        def surname_candidate(name):
            toks = normalize(name).split()
            return bool(toks) and toks[-1] in unbridged_surnames

        unmatched = [r for eid, r in espn_by_id.items()
                     if eid not in matched_espn and surname_candidate(r["espn_name"])]
        log(f"  API bridge candidates (surname pre-filter): {len(unmatched)}")
        resolved = 0
        for r in unmatched:
            name = r["espn_name"]
            if not name:
                continue
            url = "https://statsapi.mlb.com/api/v1/people/search?names=" + urllib.parse.quote(name)
            data = http_json(url)
            for person in (data or {}).get("people", []):
                mlbam = str(person.get("id", "")).strip()
                urec = universe.get(mlbam)
                # guard: don't attach a pitcher's ESPN id to a batter row (or vice
                # versa) -- prevents namesake mis-bridges (e.g. closer vs infielder).
                ub = (urec or {}).get("b_or_p") or ""
                borp_ok = ub in ("", "both") or _espn_borp(r) == ub
                if urec and not urec["espn_player_id"] and borp_ok:
                    urec["espn_player_id"] = r["espn_player_id"]
                    urec["espn_name"] = name
                    if r["eligible_slots"]:
                        urec["eligible_slots"] = r["eligible_slots"]
                    if r["pro_team"] and not urec["pro_team"]:
                        urec["pro_team"] = r["pro_team"]
                    urec["id_source"] = "api"
                    matched_espn.add(r["espn_player_id"])
                    resolved += 1
                    break
        log(f"  API bridge (people/search) attached: {resolved} ESPN players")

    # 4. Resolve lineup-only names to a NEW universe row via people/search.
    if not offline:
        added = 0
        for n, raw in lineup_only.items():
            url = "https://statsapi.mlb.com/api/v1/people/search?names=" + urllib.parse.quote(raw)
            data = http_json(url)
            for person in (data or {}).get("people", []):
                mlbam = str(person.get("id", "")).strip()
                if mlbam and mlbam not in universe:
                    universe[mlbam] = {
                        "mlbam_player_id": mlbam,
                        "mlb_name": person.get("fullName", raw),
                        "normalized_name": normalize(person.get("fullName", raw)),
                        "b_or_p": borp_from_position(person.get("primaryPosition", {})),
                        "primary_position": (person.get("primaryPosition", {}) or {}).get("abbreviation", ""),
                        "pro_team": "",
                        "years": {CURRENT_YEAR},
                        "seen_in": {"2026_mlb_lineups_batters.csv(api)"},
                        "espn_player_id": "",
                        "espn_name": "",
                        "eligible_slots": "",
                        "id_source": "api",
                    }
                    added += 1
                break
        log(f"  lineup-only names resolved via API: {added}")

    excluded = [r for eid, r in espn_by_id.items() if eid not in matched_espn]
    return excluded


# ── Stage 4: assemble + write ──────────────────────────────────────────────────
def to_output_row(rec, verified):
    years = rec.get("years") or set()
    return {
        "mlbam_player_id": rec.get("mlbam_player_id", ""),
        "espn_player_id": rec.get("espn_player_id", ""),
        "mlb_name": rec.get("mlb_name", ""),
        "espn_name": rec.get("espn_name", ""),
        "normalized_name": rec.get("normalized_name", ""),
        "b_or_p": rec.get("b_or_p", ""),
        "primary_position": rec.get("primary_position", ""),
        "eligible_slots": rec.get("eligible_slots", ""),
        "pro_team": rec.get("pro_team", ""),
        "id_source": rec.get("id_source", ""),
        "seen_in": ";".join(sorted(rec.get("seen_in", set()))),
        "first_seen_year": min(years) if years else "",
        "last_seen_year": max(years) if years else "",
        "last_verified_date": verified,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip all network calls")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, do not write")
    args = ap.parse_args()

    verified = date.today().isoformat()
    log("=" * 78)
    log(f"generate_player_map.py  (offline={args.offline}, dry_run={args.dry_run})")
    log("=" * 78)

    teams_map = {}
    if not args.offline:
        td = http_json("https://statsapi.mlb.com/api/v1/teams?sportId=1")
        for t in (td or {}).get("teams", []):
            teams_map[t.get("id")] = t.get("abbreviation", "")
        log(f"MLB teams map: {len(teams_map)} teams")

    log("\n[1] Building MLB universe (inclusion gate: MLB stats 2023+)...")
    universe, lineup_only = build_mlb_universe(args.offline, teams_map)
    log(f"  -> {len(universe)} distinct MLBAM ids; {len(lineup_only)} lineup-only names")

    log("\n[2] Building ESPN side...")
    espn_by_norm, espn_by_statcast, espn_by_id = build_espn_side(args.offline)
    log(f"  -> {len(espn_by_id)} distinct ESPN ids")

    log("\n[3] Bridging ESPN <-> MLBAM...")
    excluded = bridge(universe, lineup_only, espn_by_norm, espn_by_statcast,
                      espn_by_id, args.offline)

    # Assemble, dedup on mlbam, stable sort
    rows = [to_output_row(rec, verified) for rec in universe.values()]
    rows.sort(key=lambda r: (r["normalized_name"], str(r["mlbam_player_id"])))

    # ── Validation report ──────────────────────────────────────────────────────
    log("\n" + "=" * 78)
    log("VALIDATION")
    log("=" * 78)
    log(f"  Total players written:        {len(rows)}")
    by_year = defaultdict(int)
    for rec in universe.values():
        for y in (rec.get("years") or set()):
            by_year[y] += 1
    for y in sorted(by_year):
        log(f"    seen in {y}: {by_year[y]}")
    with_mlbam = sum(1 for r in rows if r["mlbam_player_id"])
    with_espn = sum(1 for r in rows if r["espn_player_id"])
    log(f"  mlbam_player_id populated:    {with_mlbam} ({100*with_mlbam/max(1,len(rows)):.1f}%)")
    log(f"  espn_player_id populated:     {with_espn} ({100*with_espn/max(1,len(rows)):.1f}%)")
    src_counts = defaultdict(int)
    for r in rows:
        src_counts[r["id_source"]] += 1
    log("  id_source breakdown:")
    for s, c in sorted(src_counts.items(), key=lambda x: -x[1]):
        log(f"    {s:12s} {c}")
    log(f"  ESPN players EXCLUDED (no 2023+ MLB stats): {len(excluded)}")
    for r in sorted(excluded, key=lambda x: x["espn_name"])[:10]:
        log(f"    {r['espn_player_id']:10s} {r['espn_name']}")

    # Spot checks
    log("\n  Spot checks:")
    idx = {r["mlbam_player_id"]: r for r in rows}
    for label, mlbam in [("Rocchio", "677587"), ("Seiya Suzuki", "673548")]:
        r = idx.get(mlbam)
        log(f"    {label:14s} mlbam={mlbam}: " +
            (f"espn={r['espn_player_id']!r} borp={r['b_or_p']} src={r['id_source']}" if r else "MISSING"))

    # Namesake disambiguation regression checks (the 2026-06-22 mislink fixes).
    # expected espn id (or "" for "should be blank — true id absent from ESPN feeds").
    log("\n  Namesake disambiguation checks (expected espn_player_id):")
    namesakes = [
        ("Julio Rodriguez (SEA OF)", "677594", "41044"),
        ("Will Smith (LAD C)", "669257", "38309"),
        ("Luis Garcia Jr. (WSH)", "671277", "40459"),
        ("Luis Garcia (MIN RP)", "472610", "33089"),
    ]
    for label, mlbam, expected in namesakes:
        r = idx.get(mlbam)
        got = r["espn_player_id"] if r else "MISSING"
        flag = "OK" if got == expected else "*** MISMATCH ***"
        log(f"    {label:26s} mlbam={mlbam}: espn={got!r} (expected {expected!r})  {flag}")
    chap = [r for r in rows if "chapman" in r["normalized_name"] and "aroldis" in r["normalized_name"]]
    for r in chap:
        log(f"    Aroldis Chapman mlbam={r['mlbam_player_id']}: b_or_p={r['b_or_p']!r} "
            f"(must be 'pitcher')")

    # ── Write ──────────────────────────────────────────────────────────────────
    if args.dry_run:
        log("\n[dry-run] not writing player_map.csv")
    else:
        with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()
            w.writerows(rows)
        log(f"\nWrote {len(rows)} rows -> {OUT_PATH}")

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"generate_player_map_{verified.replace('-', '')}.log")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(_log_lines))
    print(f"Log -> {log_path}")


if __name__ == "__main__":
    main()
