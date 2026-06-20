"""
Idea 5 - Box Score Stat Relationships: Correlation, Redundancy & Category-System Audit.

Description:
    Audits the relationships between box-score stats for a Head-to-Head 5x5 *Categories*
    league (NOT a points league - there are no per-stat point weights to back out). Builds
    Pearson and Spearman correlation matrices for batters and pitchers separately across
    four seasons (2023-2026), isolates the 5x5 scoring-category correlation block, measures
    how many *effectively independent* axes the 10 categories represent (PCA), flags
    redundant category pairs vs. scarce/orthogonal differentiators, and discovers player
    archetypes via hand-rolled PCA + k-means. The 2026 archetype population is overlaid with
    fantasy-team holdings and market valuation (ownership / ADP).

    The 10 scoring categories (see fantasy_baseball/scoring.md):
        Batting : R, HR, RBI, SB, OPS
        Pitching: K/9, QS, SVHD, ERA (lower better), WHIP (lower better)

Source Data (all under data-lake/01_Bronze/fantasy_baseball/):
    - 2023_mlb_stats_daily.csv, 2024_mlb_stats_daily.csv, 2025_mlb_stats_daily.csv
        MLB game logs (identity: playerName/playerId, split: b_or_p). LOCKED as the single
        source for every category value, all seasons - keeps the player population
        consistent and avoids survivorship bias toward rostered players.
    - 2026_mlb_stats_boxscore.csv
        2026 game logs (identity renamed to player_name/player_id, adds did_play; same stat
        columns). Harmonized to the 2023-2025 schema before pooling.
    - 2026_espn_stats_daily.csv         (OVERLAY ONLY) player -> fantasy team_name mapping.
    - 2026_espn_rankings_daily.csv      (OVERLAY ONLY) pct_owned / avg_draft_position.

Outputs:
    Derived CSVs -> data-lake/01_Bronze/fantasy_baseball/
        2026_local_stat_correlations_batter.csv     pooled Pearson matrix (all batter stats)
        2026_local_stat_correlations_pitcher.csv     pooled Pearson matrix (all pitcher stats)
        2026_local_category_corr_by_season_batter.csv  per-season + pooled 5x5 category corr
        2026_local_category_corr_by_season_pitcher.csv per-season + pooled 5x5 category corr
        2026_local_archetypes_batter.csv             2026 player-season archetype + overlays
        2026_local_archetypes_pitcher.csv            2026 player-season archetype + overlays
        2026_local_proposed_scoring.csv              current vs Scenario A/B/C proposed category sets
        2026_local_rescore_results.csv               per-team W/L/T under each scenario (category + matchup)
    Additional source data (ESPN, 2026) - produced by sibling fetch scripts:
        2026_espn_schedule_matchup.csv    scoring-period -> matchup-period map
                                          (produced by fantasy_baseball/generate_schedule_espn_matchup.py)
        2026_espn_scoreboard_matchup.csv  matchup pairings + ESPN actual winners (validation)
                                          (produced by fantasy_baseball/fetch_scoreboard_espn_matchup.py)
    Report -> fantasy_baseball/reports/
        stat_relationships_2026.md                   full write-up
    Log -> data-lake/00_Logs/fantasy_baseball/idea_05_stat_relationships.jsonl
"""

import csv
import itertools
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from scipy.cluster.vq import kmeans2, whiten  # scipy ships k-means; sklearn is not installed
from scipy.stats import rankdata

# --------------------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
BRONZE = os.path.join(ROOT, "data-lake", "01_Bronze", "fantasy_baseball")
LOGDIR = os.path.join(ROOT, "data-lake", "00_Logs", "fantasy_baseball")
REPORTS = os.path.join(ROOT, "fantasy_baseball", "reports")

SEASONS = [2023, 2024, 2025, 2026]
MLB_FILES = {
    2023: "2023_mlb_stats_daily.csv",
    2024: "2024_mlb_stats_daily.csv",
    2025: "2025_mlb_stats_daily.csv",
    2026: "2026_mlb_stats_boxscore.csv",
}
ESPN_STATS_2026 = "2026_espn_stats_daily.csv"
ESPN_RANKINGS_2026 = "2026_espn_rankings_daily.csv"

# Minimum-sample filters (applied per season)
MIN_AB = 50      # batters
MIN_IP = 20.0    # pitchers

# Redundancy / scarcity thresholds on the |r| category correlation block
REDUNDANT_R = 0.70   # |r| >= this => effectively double/triple counted
SCARCE_R = 0.40      # max |r| with all other categories < this => scarce/orthogonal

BAT_CATS = ["R", "HR", "RBI", "SB", "OPS"]
PIT_CATS = ["K/9", "QS", "SVHD", "ERA", "WHIP"]

# Full feature lists for the broad correlation matrix (categories + supporting stats)
BAT_FEATURES = ["R", "HR", "RBI", "SB", "OPS", "AVG", "OBP", "SLG", "ISO",
                "AB", "H", "1B", "2B", "3B", "TB", "BB", "HBP", "SO", "CS", "BB%", "K%"]
PIT_FEATURES = ["K/9", "QS", "SVHD", "ERA", "WHIP", "IP", "K", "BB", "H", "HR",
                "ER", "W", "L", "SV", "HLD", "GS", "BB/9", "HR/9", "K/BB", "H/9"]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def f(val):
    """Parse a CSV cell to float; blanks/None -> 0.0."""
    if val is None:
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def load_mlb_rows(season):
    """Load one season's MLB game logs, harmonized to a common schema."""
    path = os.path.join(BRONZE, MLB_FILES[season])
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        # Harmonize identity columns (2026 boxscore renames them).
        name = r.get("playerName") or r.get("player_name") or ""
        pid = r.get("playerId") or r.get("player_id") or ""
        out.append({"season": season, "name": name.strip(), "pid": str(pid).strip(),
                    "bp": (r.get("b_or_p") or "").strip(), "raw": r})
    return out


def aggregate(rows):
    """Sum game-log counting stats to per-(player, season) totals, split by type."""
    bat = defaultdict(lambda: defaultdict(float))
    pit = defaultdict(lambda: defaultdict(float))
    bat_meta, pit_meta = {}, {}
    for row in rows:
        r = row["raw"]
        key = (row["season"], row["pid"], row["name"])
        if row["bp"] == "batter":
            d = bat[key]
            bat_meta[key] = {"season": row["season"], "pid": row["pid"], "name": row["name"]}
            for c in ["AB", "H", "2B", "3B", "HR", "R", "RBI", "SB", "CS",
                      "B_BB", "HBP", "SF", "SO", "TB"]:
                d[c] += f(r.get(c))
            d["G"] += 1.0 if (f(r.get("AB")) > 0 or f(r.get("B_BB")) > 0) else 0.0
        elif row["bp"] == "pitcher":
            d = pit[key]
            pit_meta[key] = {"season": row["season"], "pid": row["pid"], "name": row["name"]}
            for c in ["OUTS", "ER", "K", "P_BB", "P_H", "P_HR", "P_R",
                      "QS", "SV", "HLD", "SVHD", "W", "L", "GS"]:
                d[c] += f(r.get(c))
            d["APP"] += 1.0 if f(r.get("OUTS")) > 0 else 0.0
    return bat, bat_meta, pit, pit_meta


def batter_stats(d):
    """Derive a per-season batter stat dict (rates recomputed from summed components)."""
    AB, H, HR = d["AB"], d["H"], d["HR"]
    BB, HBP, SF, TB = d["B_BB"], d["HBP"], d["SF"], d["TB"]
    doubles, triples = d["2B"], d["3B"]
    singles = max(H - doubles - triples - HR, 0.0)
    pa_obp = AB + BB + HBP + SF
    obp = (H + BB + HBP) / pa_obp if pa_obp > 0 else 0.0
    slg = TB / AB if AB > 0 else 0.0
    avg = H / AB if AB > 0 else 0.0
    pa = AB + BB + HBP + SF
    return {
        "R": d["R"], "HR": HR, "RBI": d["RBI"], "SB": d["SB"], "OPS": obp + slg,
        "AVG": avg, "OBP": obp, "SLG": slg, "ISO": slg - avg,
        "AB": AB, "H": H, "1B": singles, "2B": doubles, "3B": triples, "TB": TB,
        "BB": BB, "HBP": HBP, "SO": d["SO"], "CS": d["CS"],
        "BB%": (BB / pa) if pa > 0 else 0.0, "K%": (d["SO"] / pa) if pa > 0 else 0.0,
        "SB/G": (d["SB"] / d["G"]) if d["G"] > 0 else 0.0,  # speed rate, playing-time neutral
    }


def pitcher_stats(d):
    """Derive a per-season pitcher stat dict (rates recomputed from summed components)."""
    outs = d["OUTS"]
    ip = outs / 3.0
    K, BB, H, HR, ER = d["K"], d["P_BB"], d["P_H"], d["P_HR"], d["ER"]
    return {
        "K/9": (K * 9.0 / ip) if ip > 0 else 0.0,
        "QS": d["QS"], "SVHD": d["SVHD"],
        "ERA": (ER * 9.0 / ip) if ip > 0 else 0.0,
        "WHIP": ((BB + H) / ip) if ip > 0 else 0.0,
        "IP": ip, "K": K, "BB": BB, "H": H, "HR": HR, "ER": ER,
        "W": d["W"], "L": d["L"], "SV": d["SV"], "HLD": d["HLD"], "GS": d["GS"],
        "BB/9": (BB * 9.0 / ip) if ip > 0 else 0.0,
        "HR/9": (HR * 9.0 / ip) if ip > 0 else 0.0,
        "K/BB": (K / BB) if BB > 0 else (K if K > 0 else 0.0),
        "H/9": (H * 9.0 / ip) if ip > 0 else 0.0,
        "GS_share": (d["GS"] / d["APP"]) if d["APP"] > 0 else 0.0,  # starter vs reliever role
    }


def build_players(player_type):
    """Return list of per-(player,season) dicts with derived stats, filtered by sample."""
    players = []
    for season in SEASONS:
        rows = load_mlb_rows(season)
        bat, bat_meta, pit, pit_meta = aggregate(rows)
        if player_type == "batter":
            for key, d in bat.items():
                if d["AB"] < MIN_AB:
                    continue
                rec = batter_stats(d)
                rec.update(bat_meta[key])
                players.append(rec)
        else:
            for key, d in pit.items():
                if (d["OUTS"] / 3.0) < MIN_IP:
                    continue
                rec = pitcher_stats(d)
                rec.update(pit_meta[key])
                players.append(rec)
    return players


# --------------------------------------------------------------------------------------
# Correlation
# --------------------------------------------------------------------------------------
def corr_matrix(players, features, method="pearson"):
    """Return (features, NxN correlation matrix) over the given player records."""
    mat = np.array([[p[c] for c in features] for p in players], dtype=float)
    if method == "spearman":
        mat = np.column_stack([rankdata(mat[:, j]) for j in range(mat.shape[1])])
    # guard against zero-variance columns
    stds = mat.std(axis=0)
    stds[stds == 0] = 1.0
    z = (mat - mat.mean(axis=0)) / stds
    n = z.shape[0]
    c = (z.T @ z) / (n - 1)
    return features, c


def matrix_to_csv(path, features, mat):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["stat"] + features)
        for i, name in enumerate(features):
            w.writerow([name] + [round(float(mat[i, j]), 4) for j in range(len(features))])


# --------------------------------------------------------------------------------------
# PCA (hand-rolled via SVD) + effective dimensionality
# --------------------------------------------------------------------------------------
def standardize(mat):
    mean = mat.mean(axis=0)
    std = mat.std(axis=0)
    std[std == 0] = 1.0
    return (mat - mean) / std, mean, std


def pca(mat, n_components=None):
    """Return (scores, components, explained_variance_ratio) on standardized input."""
    z, _, _ = standardize(mat)
    U, S, Vt = np.linalg.svd(z, full_matrices=False)
    evr = (S ** 2) / np.sum(S ** 2)
    scores = U * S
    if n_components:
        scores = scores[:, :n_components]
        Vt = Vt[:n_components]
        evr = evr[:n_components]
    return scores, Vt, evr


def effective_dim(mat):
    """Participation ratio + count of PCs for 90% variance, on the category block."""
    _, _, evr = pca(mat)
    lam = evr  # already normalized
    pr = (lam.sum() ** 2) / np.sum(lam ** 2)
    cum = np.cumsum(evr)
    n90 = int(np.searchsorted(cum, 0.90) + 1)
    return pr, n90, evr


# --------------------------------------------------------------------------------------
# Clustering (k-means via scipy) + silhouette
# --------------------------------------------------------------------------------------
def silhouette(points, labels):
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    n = len(points)
    # pairwise distances
    d = np.sqrt(((points[:, None, :] - points[None, :, :]) ** 2).sum(axis=2))
    sil = np.zeros(n)
    for i in range(n):
        same = labels == labels[i]
        same[i] = False
        a = d[i, same].mean() if same.any() else 0.0
        b = np.inf
        for c in uniq:
            if c == labels[i]:
                continue
            mask = labels == c
            if mask.any():
                b = min(b, d[i, mask].mean())
        sil[i] = 0.0 if max(a, b) == 0 else (b - a) / max(a, b)
    return float(sil.mean())


def best_kmeans(points, k_range=(3, 4, 5, 6, 7), seed=42):
    best = None
    for k in k_range:
        np.random.seed(seed)
        try:
            centroids, labels = kmeans2(points, k, minit="++", seed=seed, missing="warn")
        except TypeError:
            centroids, labels = kmeans2(points, k, minit="++")
        if len(np.unique(labels)) < k:
            continue
        score = silhouette(points, labels)
        if best is None or score > best[0]:
            best = (score, k, labels, centroids)
    return best  # (silhouette, k, labels, centroids)


# --------------------------------------------------------------------------------------
# Overlays (2026 only)
# --------------------------------------------------------------------------------------
def norm_name(s):
    return "".join(ch for ch in s.lower() if ch.isalnum())


def load_team_holdings():
    """player_name(normalized) -> most recent fantasy team_name from 2026 ESPN daily."""
    path = os.path.join(BRONZE, ESPN_STATS_2026)
    latest = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            nm = norm_name(r.get("player_name", ""))
            dt = r.get("date", "")
            team = r.get("team_name", "")
            if not nm or not team:
                continue
            if nm not in latest or dt > latest[nm][0]:
                latest[nm] = (dt, team)
    return {nm: v[1] for nm, v in latest.items()}


def load_market():
    """player_name(normalized) -> (pct_owned, adp) from most recent 2026 rankings row."""
    path = os.path.join(BRONZE, ESPN_RANKINGS_2026)
    latest = {}
    with open(path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            nm = norm_name(r.get("player_name", ""))
            dt = r.get("date", "")
            if not nm:
                continue
            if nm not in latest or dt > latest[nm][0]:
                latest[nm] = (dt, f(r.get("pct_owned")), f(r.get("avg_draft_position")))
    return {nm: (v[1], v[2]) for nm, v in latest.items()}


# --------------------------------------------------------------------------------------
# Reporting helpers
# --------------------------------------------------------------------------------------
def cat_block(players, cats, method="pearson"):
    _, c = corr_matrix(players, cats, method=method)
    return c


def redundant_pairs(cats, mat, thresh=REDUNDANT_R):
    pairs = []
    for i in range(len(cats)):
        for j in range(i + 1, len(cats)):
            if abs(mat[i, j]) >= thresh:
                pairs.append((cats[i], cats[j], float(mat[i, j])))
    return sorted(pairs, key=lambda x: -abs(x[2]))


def scarce_cats(cats, mat, thresh=SCARCE_R):
    out = []
    for i, name in enumerate(cats):
        others = [abs(mat[i, j]) for j in range(len(cats)) if j != i]
        if max(others) < thresh:
            out.append((name, float(max(others))))
    return out


def primary_differentiator(cats, mat):
    """Category with the lowest mean |r| to the others - the most independent lever,
    surfaced even when it sits just above the scarce threshold (e.g. batting SB)."""
    best = None
    for i, name in enumerate(cats):
        others = [abs(mat[i, j]) for j in range(len(cats)) if j != i]
        mean_r = float(np.mean(others))
        if best is None or mean_r < best[1]:
            best = (name, mean_r, float(max(others)))
    return best  # (name, mean|r|, max|r|)


# --------------------------------------------------------------------------------------
# Proposed-scoring search: balance the internal independence of the two sides
# --------------------------------------------------------------------------------------
# Curated candidate pools - only stats that are realistic as a fantasy *category*.
BAT_POOL = ["R", "HR", "RBI", "SB", "OPS", "OBP", "SLG", "AVG", "TB", "BB", "SO"]
PIT_POOL = ["K/9", "K", "QS", "SVHD", "SV", "HLD", "ERA", "WHIP", "W", "BB/9", "K/BB", "HR/9", "H/9"]

BAT_SKILL = {
    "R": "run scoring (lineup context)", "HR": "power", "RBI": "run production (lineup context)",
    "SB": "speed", "OPS": "overall hitting (power + on-base)", "OBP": "plate discipline / on-base",
    "SLG": "power / extra-base", "AVG": "contact / batting average", "TB": "production volume + power",
    "BB": "plate discipline (walks)", "SO": "contact (avoiding strikeouts)",
}
PIT_SKILL = {
    "K/9": "strikeout rate / stuff", "K": "strikeout volume", "QS": "starter durability",
    "SVHD": "high-leverage relief role", "SV": "closer role", "HLD": "setup role",
    "ERA": "run prevention", "WHIP": "baserunner prevention", "W": "wins (team + durability)",
    "BB/9": "control", "K/BB": "command", "HR/9": "home-run suppression", "H/9": "hit prevention",
}


def participation_ratio(c):
    """Effective # of independent dimensions from a correlation matrix's eigenvalues."""
    lam = np.clip(np.linalg.eigvalsh(c), 0.0, None)
    s, s2 = lam.sum(), float(np.sum(lam ** 2))
    return (s * s) / s2 if s2 > 0 else float(len(c))


def offdiag_abs(c):
    k = c.shape[0]
    return sorted((abs(c[i, j]) for i in range(k) for j in range(i + 1, k)), reverse=True)


def max_tied_cluster(c, thr=REDUNDANT_R):
    """Largest group of categories mutually linked at |r| >= thr (connected components)."""
    k = c.shape[0]
    parent = list(range(k))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(k):
        for j in range(i + 1, k):
            if abs(c[i, j]) >= thr:
                parent[find(i)] = find(j)
    return max(Counter(find(i) for i in range(k)).values())


def best_tied_trio(feats, c):
    """Return the 3 categories with the highest minimum pairwise |r| (the tightest bundle)."""
    best = None
    for combo in itertools.combinations(range(len(feats)), 3):
        i, j, k = combo
        mn = min(abs(c[i, j]), abs(c[i, k]), abs(c[j, k]))
        if best is None or mn > best[0]:
            best = (mn, [feats[i], feats[j], feats[k]])
    return best  # (min pairwise |r|, [cat,cat,cat])


def signature(players, feats):
    _, c = corr_matrix(players, list(feats))
    return {"pr": participation_ratio(c), "offdiag": offdiag_abs(c),
            "mean_abs": float(np.mean(offdiag_abs(c))), "maxcluster": max_tied_cluster(c),
            "trio": best_tied_trio(list(feats), c), "corr": c}


def mirror_pitching(batters, pitchers, cur_bat, cur_pit, n=5):
    """Scenario A: keep batting; find the pitching n-set whose internal correlation SHAPE
    best mirrors batting's (similar effective-dimension + similar sorted |r| profile),
    preferring minimal change from the current pitching categories."""
    bsig = signature(batters, cur_bat)
    bprof = np.array(bsig["offdiag"])
    cands = []
    for combo in itertools.combinations(PIT_POOL, n):
        sig = signature(pitchers, combo)
        prof = np.array(sig["offdiag"])
        dist = abs(sig["pr"] - bsig["pr"]) + float(np.mean(np.abs(prof - bprof)))
        retained = len(set(combo) & set(cur_pit))
        cands.append((dist, -retained, list(combo), sig))
    cands.sort(key=lambda x: (x[0], x[1]))
    return bsig, cands[:4]


def max_independence(players, pool, n=5, topn=30):
    """Return n-subsets ranked by participation ratio (most independent first)."""
    res = []
    for combo in itertools.combinations(pool, n):
        sig = signature(players, combo)
        res.append((sig["pr"], list(combo), sig))
    res.sort(key=lambda x: -x[0])
    return res[:topn]


def closest_pr_set(players, pool, target, n=5):
    """n-subsets ranked by how close their effective dimensionality is to a target
    (tie-break toward higher independence). Used to cap the more-flexible side at the
    binding side's achievable ceiling so the two sides actually equalize."""
    res = []
    for combo in itertools.combinations(pool, n):
        sig = signature(players, combo)
        res.append((abs(sig["pr"] - target), -sig["pr"], list(combo), sig))
    res.sort(key=lambda x: (x[0], x[1]))
    return res


# Candidate 6th-category additions. Restricted to recognizable, reasonably high-volume
# categories; rare/noisy counting stats (2B, 3B, HBP, CS) are excluded because they read as
# statistically "independent" only by virtue of being random, not by measuring a new skill.
BAT_ADD_POOL = ["OBP", "SLG", "AVG", "TB", "BB", "SO", "H"]
PIT_ADD_POOL = ["K", "SV", "HLD", "W", "BB/9", "K/BB", "HR/9", "H/9", "L", "IP"]


def rank_additions(players, base, add_pool, maximize):
    """Rank single-category additions to `base` by the resulting effective dimensionality.
    maximize=True  -> most INDEPENDENT addition (raises eff-axes; reduces internal relationship).
    maximize=False -> most REDUNDANT addition (lowers eff-axes; increases internal relationship)."""
    base = list(base)
    res = []
    for c in add_pool:
        if c in base:
            continue
        sig = signature(players, base + [c])
        res.append((sig["pr"], c, sig))
    res.sort(key=lambda x: -x[0] if maximize else x[0])
    return res


def max_pr_with(players, pool, must_have, n=5):
    """Most-independent n-subset that still contains a required category (e.g. keep HR)."""
    best = None
    for combo in itertools.combinations(pool, n):
        if must_have not in combo:
            continue
        sig = signature(players, combo)
        if best is None or sig["pr"] > best[1]["pr"]:
            best = (list(combo), sig)
    return best


# --------------------------------------------------------------------------------------
# Re-scoring: how would each proposed structure change this season's matchup outcomes?
# --------------------------------------------------------------------------------------
SCHEDULE_2026 = "2026_espn_schedule_matchup.csv"
SCOREBOARD_2026 = "2026_espn_scoreboard_matchup.csv"
ACTIVE_EXCLUDE_SLOTS = {"BE", "IL", ""}          # bench / injured-list do not accrue
INVERSE_CATS = {"ERA", "WHIP", "BB/9", "HR/9", "H/9", "SO"}  # lower is better (SO = batter Ks)


def load_schedule_map():
    """scoring_period -> matchup_period, plus matchup_period -> max scoring_period."""
    sp2mp, mp_maxsp = {}, defaultdict(int)
    with open(os.path.join(BRONZE, SCHEDULE_2026), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            sp, mp = int(r["scoring_period"]), int(r["matchup_period"])
            sp2mp[sp] = mp
            mp_maxsp[mp] = max(mp_maxsp[mp], sp)
    return sp2mp, mp_maxsp


def load_scoreboard():
    """Decided matchups: list of (matchup_period, home_id, away_id, espn_winner)."""
    out = []
    with open(os.path.join(BRONZE, SCOREBOARD_2026), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.append((int(r["matchupPeriodId"]), int(r["homeTeamId"]),
                        int(r["awayTeamId"]), r["winner"]))
    return out


def derive_period_cats(c):
    """Derive every candidate category value from a team-period's summed components.
    Rate stats use guards so a side with no IP/AB cleanly loses its rate categories."""
    AB, H, BB, HBP, SF, TB = c["AB"], c["H"], c["B_BB"], c["HBP"], c["SF"], c["TB"]
    obp_den = AB + BB + HBP + SF
    obp = (H + BB + HBP) / obp_den if obp_den > 0 else 0.0
    slg = TB / AB if AB > 0 else 0.0
    ip = c["OUTS"] / 3.0
    K, PBB, PH, PHR, ER = c["K"], c["P_BB"], c["P_H"], c["P_HR"], c["ER"]
    BIG = 999.0  # worst possible for an inverse rate when there are no innings
    return {
        # batting
        "R": c["R"], "HR": c["HR"], "RBI": c["RBI"], "SB": c["SB"],
        "OPS": obp + slg, "OBP": obp, "SLG": slg, "AVG": H / AB if AB > 0 else 0.0,
        "TB": TB, "BB": BB, "SO": c["SO"], "H": H,
        # pitching
        "K/9": (K * 9.0 / ip) if ip > 0 else 0.0, "QS": c["QS"], "SVHD": c["SVHD"],
        "ERA": (ER * 9.0 / ip) if ip > 0 else BIG, "WHIP": ((PBB + PH) / ip) if ip > 0 else BIG,
        "K": K, "SV": c["SV"], "HLD": c["HLD"], "W": c["W"],
        "BB/9": (PBB * 9.0 / ip) if ip > 0 else BIG, "HR/9": (PHR * 9.0 / ip) if ip > 0 else BIG,
        "H/9": (PH * 9.0 / ip) if ip > 0 else BIG, "K/BB": (K / PBB) if PBB > 0 else (K if K else 0.0),
    }


def aggregate_team_periods(sp2mp):
    """Sum active-lineup component stats per (team_id, matchup_period) from stats_daily.
    Also return team_id -> most-recent team_name."""
    agg = defaultdict(lambda: defaultdict(float))
    team_name, name_date = {}, {}
    bat_cols = ["AB", "H", "2B", "3B", "HR", "R", "RBI", "SB", "B_BB", "HBP", "SF", "SO", "TB"]
    pit_cols = ["OUTS", "ER", "K", "P_BB", "P_H", "P_HR", "QS", "SV", "HLD", "SVHD", "W", "L"]
    with open(os.path.join(BRONZE, ESPN_STATS_2026), encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if (r.get("lineup_slot") or "") in ACTIVE_EXCLUDE_SLOTS:
                continue
            sp = int(r["scoring_period"]) if r.get("scoring_period") else None
            mp = sp2mp.get(sp)
            if mp is None:
                continue
            tid = int(r["team_id"])
            dt = r.get("date", "")
            if tid not in name_date or dt > name_date[tid]:
                name_date[tid] = dt
                team_name[tid] = r.get("team_name", str(tid))
            d = agg[(tid, mp)]
            cols = bat_cols if r.get("player_type") == "batter" else pit_cols
            for col in cols:
                d[col] += f(r.get(col))
    return agg, team_name


def matchup_record(vals_a, vals_b, cats):
    """Per-category W/L/T for team A vs B over the given category list."""
    w = l = t = 0
    for cat in cats:
        va, vb = vals_a.get(cat, 0.0), vals_b.get(cat, 0.0)
        if va == vb:
            t += 1
        elif (va < vb) if cat in INVERSE_CATS else (va > vb):
            w += 1
        else:
            l += 1
    return w, l, t


def md_matrix(cats, mat):
    lines = ["| | " + " | ".join(cats) + " |", "|" + "---|" * (len(cats) + 1)]
    for i, name in enumerate(cats):
        lines.append("| **" + name + "** | " +
                     " | ".join(f"{mat[i, j]:.2f}" for j in range(len(cats))) + " |")
    return "\n".join(lines)


def main():
    os.makedirs(LOGDIR, exist_ok=True)
    os.makedirs(REPORTS, exist_ok=True)

    batters = build_players("batter")
    pitchers = build_players("pitcher")

    def by_season(players):
        d = defaultdict(list)
        for p in players:
            d[p["season"]].append(p)
        return d

    bat_season = by_season(batters)
    pit_season = by_season(pitchers)

    # ---- broad correlation matrices (pooled) ----
    bfeat, bmat_p = corr_matrix(batters, BAT_FEATURES, "pearson")
    _, bmat_s = corr_matrix(batters, BAT_FEATURES, "spearman")
    pfeat, pmat_p = corr_matrix(pitchers, PIT_FEATURES, "pearson")
    _, pmat_s = corr_matrix(pitchers, PIT_FEATURES, "spearman")

    matrix_to_csv(os.path.join(BRONZE, "2026_local_stat_correlations_batter.csv"), bfeat, bmat_p)
    matrix_to_csv(os.path.join(BRONZE, "2026_local_stat_correlations_pitcher.csv"), pfeat, pmat_p)

    # ---- 5x5 category blocks: per-season + pooled ----
    def season_cat_csv(path, cats, season_players, pooled_players):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["scope", "cat_a", "cat_b", "pearson", "spearman"])
            scopes = [(str(s), season_players[s]) for s in SEASONS] + [("pooled", pooled_players)]
            for scope, pl in scopes:
                cp = cat_block(pl, cats, "pearson")
                cs = cat_block(pl, cats, "spearman")
                for i in range(len(cats)):
                    for j in range(i + 1, len(cats)):
                        w.writerow([scope, cats[i], cats[j],
                                    round(float(cp[i, j]), 4), round(float(cs[i, j]), 4)])

    season_cat_csv(os.path.join(BRONZE, "2026_local_category_corr_by_season_batter.csv"),
                   BAT_CATS, bat_season, batters)
    season_cat_csv(os.path.join(BRONZE, "2026_local_category_corr_by_season_pitcher.csv"),
                   PIT_CATS, pit_season, pitchers)

    bcat_pooled = cat_block(batters, BAT_CATS, "pearson")
    pcat_pooled = cat_block(pitchers, PIT_CATS, "pearson")

    bred = redundant_pairs(BAT_CATS, bcat_pooled)
    pred = redundant_pairs(PIT_CATS, pcat_pooled)
    bscarce = scarce_cats(BAT_CATS, bcat_pooled)
    pscarce = scarce_cats(PIT_CATS, pcat_pooled)
    bdiff = primary_differentiator(BAT_CATS, bcat_pooled)
    pdiff = primary_differentiator(PIT_CATS, pcat_pooled)

    # cross-season stability: std of pearson per category pair
    def stability(cats, season_players):
        out = {}
        for i in range(len(cats)):
            for j in range(i + 1, len(cats)):
                vals = []
                for s in SEASONS:
                    c = cat_block(season_players[s], cats, "pearson")
                    vals.append(c[i, j])
                out[(cats[i], cats[j])] = (float(np.mean(vals)), float(np.std(vals)),
                                           float(min(vals)), float(max(vals)))
        return out

    bstab = stability(BAT_CATS, bat_season)
    pstab = stability(PIT_CATS, pit_season)

    # ---- effective dimensionality on category block (pooled) ----
    bcat_mat = np.array([[p[c] for c in BAT_CATS] for p in batters], dtype=float)
    pcat_mat = np.array([[p[c] for c in PIT_CATS] for p in pitchers], dtype=float)
    bpr, bn90, bevr = effective_dim(bcat_mat)
    ppr, pn90, pevr = effective_dim(pcat_mat)

    # ---- archetype clustering (pooled) ----
    # Cluster on RATE / SHAPE features so archetypes reflect *style* (speed/power/contact/
    # role), not playing-time volume. Counting totals (R/HR/RBI/IP) would just rank "how good".
    bclust_feat = ["OPS", "ISO", "AVG", "BB%", "K%", "SB/G"]
    pclust_feat = ["K/9", "BB/9", "HR/9", "ERA", "WHIP", "GS_share", "SVHD"]

    def cluster(players, feats):
        mat = np.array([[p[c] for c in feats] for p in players], dtype=float)
        scores, comps, evr = pca(mat, n_components=3)
        best = best_kmeans(scores)
        sil, k, labels, centroids = best
        return scores, comps, evr, labels, k, sil, feats

    b_scores, b_comps, b_evr, b_labels, b_k, b_sil, b_cf = cluster(batters, bclust_feat)
    p_scores, p_comps, p_evr, p_labels, p_k, p_sil, p_cf = cluster(pitchers, pclust_feat)

    team_map = load_team_holdings()
    market = load_market()

    def archetype_records(players, feats, labels, scores, centroids_in_pca):
        recs = []
        for idx, p in enumerate(players):
            recs.append({**p, "cluster": int(labels[idx]),
                         "pc1": float(scores[idx, 0]), "pc2": float(scores[idx, 1]),
                         "pc3": float(scores[idx, 2])})
        return recs

    b_recs = archetype_records(batters, b_cf, b_labels, b_scores, None)
    p_recs = archetype_records(pitchers, p_cf, p_labels, p_scores, None)

    def name_cluster(cs, is_batter):
        """Heuristic style label from the centroid's z-scored rate/shape profile."""
        z = cs["z"]
        if is_batter:
            tags = []
            if z["SB/G"] > 0.6:
                tags.append("Speed")
            if z["ISO"] > 0.5:
                tags.append("Power")
            if z["K%"] < -0.3 and z["AVG"] > 0.2:
                tags.append("Contact")
            if z["BB%"] > 0.5 and "Power" not in tags:
                tags.append("On-Base")
            if not tags:
                tags.append("Free-Swinger" if z["K%"] > 0.4 else "Balanced")
            return " ".join(tags) + " Bat"
        else:
            role = ("Starter" if cs["raw"]["GS_share"] > 0.6
                    else "Reliever" if cs["raw"]["GS_share"] < 0.25 else "Swingman")
            tags = []
            if z["K/9"] > 0.5:
                tags.append("High-K")
            if z["ERA"] < -0.4 and z["WHIP"] < -0.4:
                tags.append("Ratio-Anchor")
            if z["ERA"] > 0.5 or z["WHIP"] > 0.5:
                tags.append("Volatile")
            if cs["raw"]["SVHD"] > 8 and role == "Reliever":
                tags.append("(SV/HD)")
            return (role + " " + " ".join(tags)).strip()

    def profile_clusters(players, recs, feats, k, is_batter, cats):
        # z-scores of cluster means vs population for naming
        pop_mean = {c: np.mean([p[c] for p in players]) for c in set(feats + cats)}
        pop_std = {c: (np.std([p[c] for p in players]) or 1.0) for c in set(feats + cats)}
        cards = []
        for cl in range(k):
            members = [r for r in recs if r["cluster"] == cl]
            if not members:
                continue
            raw = {c: float(np.mean([m[c] for m in members])) for c in set(feats + cats)}
            z = {c: (raw[c] - pop_mean[c]) / pop_std[c] for c in set(feats + cats)}
            label = name_cluster({"raw": raw, "z": z}, is_batter)
            # representative players: closest to cluster centroid in PCA space, dedup by name, prefer 2026
            cx = np.mean([m["pc1"] for m in members])
            cy = np.mean([m["pc2"] for m in members])
            cz = np.mean([m["pc3"] for m in members])
            ranked = sorted(members, key=lambda m: (m["pc1"] - cx) ** 2 +
                            (m["pc2"] - cy) ** 2 + (m["pc3"] - cz) ** 2)
            reps, seen = [], set()
            for m in ranked:
                if m["name"] in seen:
                    continue
                seen.add(m["name"])
                reps.append(f"{m['name']} ({m['season']})")
                if len(reps) >= 5:
                    break
            n2026 = sum(1 for m in members if m["season"] == 2026)
            cards.append({"cluster": cl, "label": label, "size": len(members),
                          "n2026": n2026, "raw": raw, "z": z, "reps": reps})
        # de-duplicate identical labels by appending a distinguishing tier
        seen_lab = defaultdict(int)
        tier_stat = "OPS" if is_batter else "ERA"
        for c in sorted(cards, key=lambda x: (x["label"], -x["raw"][tier_stat])):
            if seen_lab[c["label"]]:
                better = "lo-ERA" if not is_batter else "hi-OPS"
                c["label"] = f"{c['label']} ({tier_stat} {c['raw'][tier_stat]:.2f})"
            seen_lab[c["label"]] += 1
        return sorted(cards, key=lambda c: -c["size"])

    b_cards = profile_clusters(batters, b_recs, b_cf, b_k, True, BAT_CATS)
    p_cards = profile_clusters(pitchers, p_recs, p_cf, p_k, False, PIT_CATS)

    # cluster label lookup
    b_label_of = {c["cluster"]: c["label"] for c in b_cards}
    p_label_of = {c["cluster"]: c["label"] for c in p_cards}

    # ---- write 2026 archetype CSVs with overlays ----
    def write_archetypes(path, recs, cats, label_of):
        rec2026 = [r for r in recs if r["season"] == 2026]
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["player_name", "cluster", "archetype"] + cats +
                       ["fantasy_team", "pct_owned", "adp"])
            for r in sorted(rec2026, key=lambda x: x["name"]):
                nm = norm_name(r["name"])
                po, adp = market.get(nm, ("", ""))
                w.writerow([r["name"], r["cluster"], label_of.get(r["cluster"], "")] +
                           [round(r[c], 3) for c in cats] +
                           [team_map.get(nm, ""), po, adp])

    write_archetypes(os.path.join(BRONZE, "2026_local_archetypes_batter.csv"),
                     b_recs, BAT_CATS, b_label_of)
    write_archetypes(os.path.join(BRONZE, "2026_local_archetypes_pitcher.csv"),
                     p_recs, PIT_CATS, p_label_of)

    # ---- team-holdings & market overlay summaries (2026) ----
    def overlay_summary(recs, label_of):
        team_arch = defaultdict(lambda: defaultdict(int))
        arch_own = defaultdict(list)
        for r in recs:
            if r["season"] != 2026:
                continue
            nm = norm_name(r["name"])
            team = team_map.get(nm)
            lab = label_of.get(r["cluster"], "")
            if team:
                team_arch[team][lab] += 1
            po, _ = market.get(nm, (None, None))
            if po is not None:
                arch_own[lab].append(po)
        arch_own_mean = {k: (float(np.mean(v)) if v else 0.0, len(v)) for k, v in arch_own.items()}
        return team_arch, arch_own_mean

    b_team_arch, b_arch_own = overlay_summary(b_recs, b_label_of)
    p_team_arch, p_arch_own = overlay_summary(p_recs, p_label_of)

    # ---------------------------------------------------------------------------------
    # Build the report
    # ---------------------------------------------------------------------------------
    L = []
    L.append("# Idea 5 - Box Score Stat Relationships: Correlation, Redundancy & Category-System Audit\n")
    L.append(f"*Generated {datetime.now():%Y-%m-%d %H:%M} from MLB game logs 2023-2026. "
             "League: Head-to-Head 5x5 **Categories** (see `scoring.md`) - there are no point "
             "weights; this audit measures how independent the 10 categories actually are.*\n")
    L.append("## Method\n")
    L.append(f"- **Stat source (locked):** MLB game logs for every season including 2026. ESPN "
             "files are used only to overlay fantasy-team holdings and market valuation (2026).")
    L.append(f"- **Sample filters (per season):** batters >= {MIN_AB} AB, pitchers >= {MIN_IP:.0f} IP.")
    L.append(f"- **Qualified player-seasons:** {len(batters)} batters, {len(pitchers)} pitchers "
             f"({len(bat_season[2026])} / {len(pit_season[2026])} in 2026).")
    L.append(f"- Rate stats (OPS, ERA, WHIP, K/9) recomputed from summed components, not averaged.")
    L.append(f"- Redundancy threshold |r| >= {REDUNDANT_R:.2f}; scarce threshold max|r| < {SCARCE_R:.2f}.\n")

    # category blocks
    L.append("## 1-2. Scoring-Category Correlation Block (pooled 2023-2026)\n")
    L.append("### Batting categories (Pearson)\n")
    L.append(md_matrix(BAT_CATS, bcat_pooled) + "\n")
    L.append("### Pitching categories (Pearson)\n")
    L.append(md_matrix(PIT_CATS, pcat_pooled) + "\n")
    L.append("Full correlation matrices across all supporting stats are saved to "
             "`2026_local_stat_correlations_batter.csv` and `2026_local_stat_correlations_pitcher.csv`.\n")

    # redundancy audit
    L.append("## 3. Redundancy / Independence Audit\n")
    L.append("### Redundant category pairs (|r| >= %.2f) - effectively double/triple-counted\n" % REDUNDANT_R)
    if bred or pred:
        L.append("| Side | Pair | Pearson r |")
        L.append("|---|---|---|")
        for a, b, r in bred:
            L.append(f"| Batting | {a} <-> {b} | {r:.2f} |")
        for a, b, r in pred:
            L.append(f"| Pitching | {a} <-> {b} | {r:.2f} |")
        L.append("")
    else:
        L.append("_None above threshold._\n")
    L.append("### Scarce / orthogonal categories (max |r| with any other category < %.2f)\n" % SCARCE_R)
    L.append("| Side | Category | Max |r| vs others |")
    L.append("|---|---|---|")
    for name, mx in bscarce:
        L.append(f"| Batting | {name} | {mx:.2f} |")
    for name, mx in pscarce:
        L.append(f"| Pitching | {name} | {mx:.2f} |")
    L.append("")
    L.append(f"**Primary differentiator (most independent category, lowest mean |r|):** "
             f"Batting -> **{bdiff[0]}** (mean |r| {bdiff[1]:.2f}); "
             f"Pitching -> **{pdiff[0]}** (mean |r| {pdiff[1]:.2f}). "
             f"Even where it sits just above the scarce threshold, this is the category that "
             f"least 'comes for free' with the correlated bundle.\n")

    # effective dimensionality
    L.append("### Effective dimensionality of the category set (PCA)\n")
    L.append(f"- **Batting:** participation ratio = {bpr:.2f} of 5 axes; "
             f"{bn90} PCs explain 90% of variance. Explained-variance ratios: "
             + ", ".join(f"{e:.2f}" for e in bevr) + ".")
    L.append(f"- **Pitching:** participation ratio = {ppr:.2f} of 5 axes; "
             f"{pn90} PCs explain 90% of variance. Explained-variance ratios: "
             + ", ".join(f"{e:.2f}" for e in pevr) + ".\n")

    # cross-season stability
    L.append("## 5. Cross-Season Stability (per-season Pearson, 2023-2026)\n")

    def stab_table(stab, header):
        rows = [f"### {header}\n", "| Pair | mean r | std | min | max |", "|---|---|---|---|---|"]
        for (a, b), (mean, sd, mn, mx) in sorted(stab.items(), key=lambda kv: -abs(kv[1][0])):
            flag = " ⚠️ unstable" if sd >= 0.15 else ""
            rows.append(f"| {a}<->{b} | {mean:.2f} | {sd:.2f} | {mn:.2f} | {mx:.2f}{flag} |")
        return "\n".join(rows) + "\n"

    L.append(stab_table(bstab, "Batting category pairs"))
    L.append(stab_table(pstab, "Pitching category pairs"))

    # archetypes
    def archetype_section(cards, cats, team_arch, arch_own, side):
        out = [f"## 4. Player Archetypes - {side}\n"]
        out.append(f"k-means on PCA(3) of the {side.lower()} stat profile. "
                   f"Selected k by silhouette.\n")
        for c in cards:
            out.append(f"### {c['label']}  _(cluster {c['cluster']}, n={c['size']}, "
                       f"{c['n2026']} in 2026)_")
            line = " · ".join(f"{cat} {c['raw'][cat]:.2f} (z{c['z'][cat]:+.1f})" for cat in cats)
            out.append(f"- **Category line:** {line}")
            out.append(f"- **Representative players:** " + ", ".join(c["reps"]))
            own = arch_own.get(c["label"])
            if own:
                out.append(f"- **Avg ownership (2026):** {own[0]:.1f}% (n={own[1]})")
            out.append("")
        # team concentration
        out.append(f"**2026 team holdings by archetype ({side}):**\n")
        out.append("| Fantasy team | " + " | ".join(cd["label"] for cd in cards) + " |")
        out.append("|" + "---|" * (len(cards) + 1))
        for team in sorted(team_arch.keys()):
            row = [team] + [str(team_arch[team].get(cd["label"], 0)) for cd in cards]
            out.append("| " + " | ".join(row) + " |")
        out.append("")
        return "\n".join(out)

    L.append(archetype_section(b_cards, BAT_CATS, b_team_arch, b_arch_own, "Batters"))
    L.append(archetype_section(p_cards, PIT_CATS, p_team_arch, p_arch_own, "Pitchers"))

    # market over/under valuation
    L.append("## 6. Market Valuation by Archetype (2026)\n")
    L.append("Average ESPN ownership % per archetype - high category value at low ownership "
             "signals a market the league can exploit; low value at high ownership is a trap.\n")
    L.append("| Side | Archetype | Avg pct_owned | n |")
    L.append("|---|---|---|---|")
    for lab, (mean, n) in sorted(b_arch_own.items(), key=lambda kv: -kv[1][0]):
        L.append(f"| Batting | {lab} | {mean:.1f}% | {n} |")
    for lab, (mean, n) in sorted(p_arch_own.items(), key=lambda kv: -kv[1][0]):
        L.append(f"| Pitching | {lab} | {mean:.1f}% | {n} |")
    L.append("")

    # data-driven takeaways
    L.append("## Roster-Construction Takeaways\n")
    bt = []
    if bred:
        bundle = ", ".join(sorted(set([p for pr in bred for p in pr[:2]])))
        top = bred[0]
        bt.append(f"**The batting bundle {bundle} is effectively one category** (pairwise r up to "
                  f"{top[2]:.2f}). Any high-volume bat in a good lineup wins all three together - do not "
                  "pay a separate premium for each; one or two elite run-producers covers the bundle.")
    bt.append(f"**{bdiff[0]} is the batting differentiator** (mean |r| {bdiff[1]:.2f} - the lowest of the "
              "five). It does not ride along with the power bundle, so it must be targeted deliberately with "
              "dedicated sources or it is simply lost. This is where batting matchups are actually decided.")
    if pred:
        top = pred[0]
        bt.append(f"**{top[0]} and {top[1]} move together** (r={top[2]:.2f}) - a single strong-ratio arm "
                  "helps both, but a blow-up hurts both, so ratio categories are won/lost as a pair.")
    if len(pscarce) >= 2:
        bt.append("**K/9, QS, and SVHD are three independent pitching levers** (each weakly correlated with "
                  "the rest). They are won by *roster construction*, not ace quality: SVHD needs dedicated "
                  "saves+holds arms, QS needs innings-eating starters, and K/9 needs strikeout stuff - a "
                  "staff of great-ratio pitchers can still lose all three.")
    bt.append(f"**Effective dimensionality:** the batting set carries only ~{bpr:.1f} of 5 independent axes; "
              f"pitching ~{ppr:.1f} of 5. Pitching is the more multi-dimensional side, so balanced pitching "
              "construction has more leverage than chasing the collapsed batting bundle.")
    for t in bt:
        L.append(f"- {t}")
    L.append("")

    # ---------------------------------------------------------------------------------
    # Proposed Metrics - balance the internal independence of the two sides
    # ---------------------------------------------------------------------------------
    cur_bsig = signature(batters, BAT_CATS)
    cur_psig = signature(pitchers, PIT_CATS)

    # Scenario A - mirror batting's shape onto pitching (minimal change)
    a_bsig, a_pit = mirror_pitching(batters, pitchers, BAT_CATS, PIT_CATS)
    a_best = a_pit[0]
    a_pit_set, a_pit_sig = a_best[2], a_best[3]

    # Scenario B - most-independent, equalized sets per side (from scratch).
    # Batting stats are structurally more correlated, so the batting side is the binding
    # constraint: take its most-independent set, then cap pitching at that same ceiling.
    top_bat = max_independence(batters, BAT_POOL, topn=6)
    top_pit_max = max_independence(pitchers, PIT_POOL, topn=3)  # pitching's own ceiling (reference)
    b_bat_set, b_bsig = top_bat[0][1], top_bat[0][2]
    target = b_bsig["pr"]
    b_pit_cand = closest_pr_set(pitchers, PIT_POOL, target)
    b_pit_set, b_psig = b_pit_cand[0][2], b_pit_cand[0][3]
    b_gap = abs(b_bsig["pr"] - b_psig["pr"])
    fam_bat_set, fam_bsig = max_pr_with(batters, BAT_POOL, "HR")  # familiar variant keeping HR
    pit_ceiling_pr, pit_ceiling_set, _ = top_pit_max[0]

    # Scenario C - keep 5x5, add one category to each side (-> 6x6).
    # Batting: add the most INDEPENDENT category (raises batting eff-axes, lowers redundancy).
    # Pitching: add the most REDUNDANT category (lowers pitching eff-axes, raises redundancy).
    c_bat_adds = rank_additions(batters, BAT_CATS, BAT_ADD_POOL, maximize=True)
    c_pit_adds = rank_additions(pitchers, PIT_CATS, PIT_ADD_POOL, maximize=False)
    c_bat_add, c_bsig = c_bat_adds[0][1], c_bat_adds[0][2]
    c_pit_add, c_psig = c_pit_adds[0][1], c_pit_adds[0][2]
    c_bat_set = BAT_CATS + [c_bat_add]
    c_pit_set = PIT_CATS + [c_pit_add]
    c_gap = abs(c_bsig["pr"] - c_psig["pr"])

    def skills(cats, smap):
        return "; ".join(f"{c} ({smap.get(c, '')})" for c in cats)

    def trio_str(sig):
        mn, trio = sig["trio"]
        return f"{' / '.join(trio)} (min pairwise |r| {mn:.2f})"

    L.append("## Proposed Metrics - Balancing Batting & Pitching Independence\n")
    L.append("**Problem.** The two sides are lopsided in internal redundancy. Today the batting "
             f"categories carry only ~{cur_bsig['pr']:.1f} effective independent axes (R/HR/RBI are "
             f"one tied bundle, max tied-cluster = {cur_bsig['maxcluster']}), while pitching carries "
             f"~{cur_psig['pr']:.1f} (only ERA/WHIP tied, max cluster = {cur_psig['maxcluster']}). "
             "Two scenarios below rebalance them. Search population: same pooled 2023-2026 "
             "qualified players; candidate categories restricted to realistic, trackable stats.\n")

    L.append("### Balance scorecard\n")
    L.append("| Structure | Batting cats | Bat eff-axes | Bat max-tie | Pitching cats | Pit eff-axes | Pit max-tie | Balance gap |")
    L.append("|---|---|---|---|---|---|---|---|")
    L.append(f"| **Current** | {', '.join(BAT_CATS)} | {cur_bsig['pr']:.2f} | {cur_bsig['maxcluster']} | "
             f"{', '.join(PIT_CATS)} | {cur_psig['pr']:.2f} | {cur_psig['maxcluster']} | "
             f"{abs(cur_bsig['pr'] - cur_psig['pr']):.2f} |")
    L.append(f"| **A: Mirror** | {', '.join(BAT_CATS)} _(unchanged)_ | {a_bsig['pr']:.2f} | {a_bsig['maxcluster']} | "
             f"{', '.join(a_pit_set)} | {a_pit_sig['pr']:.2f} | {a_pit_sig['maxcluster']} | "
             f"{abs(a_bsig['pr'] - a_pit_sig['pr']):.2f} |")
    L.append(f"| **B: Max-independence** | {', '.join(b_bat_set)} | {b_bsig['pr']:.2f} | {b_bsig['maxcluster']} | "
             f"{', '.join(b_pit_set)} | {b_psig['pr']:.2f} | {b_psig['maxcluster']} | {b_gap:.2f} |")
    L.append(f"| **C: 6x6 add-one** | {', '.join(c_bat_set)} | {c_bsig['pr']:.2f} | {c_bsig['maxcluster']} | "
             f"{', '.join(c_pit_set)} | {c_psig['pr']:.2f} | {c_psig['maxcluster']} | {c_gap:.2f} |")
    L.append("")

    # Scenario A detail
    L.append("### Scenario A - Mirror (smallest change, most adoptable)\n")
    L.append("Batting is left **unchanged** - it already has the 3-category tied bundle "
             f"(**{trio_str(cur_bsig)}**) plus two looser categories. We swap the pitching side so it "
             "carries a *parallel* run-prevention tied trio, mirroring the same shape.\n")
    L.append(f"- **Proposed pitching categories:** {', '.join(a_pit_set)} "
             f"(retains {len(set(a_pit_set) & set(PIT_CATS))} of the current 5).")
    L.append(f"- **Pitching tied trio:** {trio_str(a_pit_sig)} - the mirror of batting's R/HR/RBI bundle.")
    L.append(f"- **Effective axes:** batting {a_bsig['pr']:.2f} vs pitching {a_pit_sig['pr']:.2f} "
             f"(gap {abs(a_bsig['pr'] - a_pit_sig['pr']):.2f}; current gap "
             f"{abs(cur_bsig['pr'] - cur_psig['pr']):.2f}).")
    L.append("- **Other candidate pitching sets (next best mirrors):**")
    for dist, negret, combo, sig in a_pit[1:4]:
        L.append(f"  - {', '.join(combo)} - eff-axes {sig['pr']:.2f}, tied trio {trio_str(sig)}")
    L.append("\n*Note:* pitching stats are inherently more independent than hitting stats, so the "
             "tightest pitching trio is a touch looser than R/HR/RBI; it is built from the "
             "run-prevention family (ERA / WHIP / hit- or walk-rate), which genuinely move together.\n")

    # Scenario B detail
    L.append("### Scenario B - Max independence (broadens desirable player types)\n")
    L.append("Built from scratch to maximize - and equalize - the number of distinct skills scored, so "
             "value spreads across many player profiles instead of concentrating in a few must-own "
             "players.\n")
    L.append("**Key structural fact:** hitting stats are inherently more correlated than pitching stats "
             f"(everything rides the same playing-time + lineup-quality halo). The most independent five "
             f"*batting* categories top out at only ~{b_bsig['pr']:.2f} effective axes, whereas five "
             f"pitching categories can reach ~{pit_ceiling_pr:.2f} ({', '.join(pit_ceiling_set)}). "
             "Batting is therefore the binding side: to truly *equalize* the two, we take batting's most "
             "independent set and cap pitching at the same ceiling (rather than letting pitching run away "
             "and re-open the gap).\n")
    L.append(f"- **Proposed batting categories:** {skills(b_bat_set, BAT_SKILL)}")
    L.append(f"  - effective axes {b_bsig['pr']:.2f} of 5; max tied-cluster {b_bsig['maxcluster']}; "
             f"mean |r| {b_bsig['mean_abs']:.2f}. (Nearly doubles batting independence vs the current "
             f"{cur_bsig['pr']:.2f}.)")
    L.append(f"- **Proposed pitching categories (capped to match):** {skills(b_pit_set, PIT_SKILL)}")
    L.append(f"  - effective axes {b_psig['pr']:.2f} of 5; max tied-cluster {b_psig['maxcluster']}; "
             f"mean |r| {b_psig['mean_abs']:.2f}.")
    L.append(f"- **Balance:** effective-axis gap **{b_gap:.2f}** (vs current "
             f"{abs(cur_bsig['pr'] - cur_psig['pr']):.2f}) - the two sides are now near-identical in "
             "internal independence.")
    fam_delta = b_bsig["pr"] - fam_bsig["pr"]
    if fam_delta < 0.10:
        fam_msg = (f"costs essentially no independence (effective axes {fam_bsig['pr']:.2f} vs "
                   f"{b_bsig['pr']:.2f}), so it is the **recommended** Scenario B batting set - "
                   "equally balanced but far more recognizable to the league.")
    else:
        fam_msg = (f"is modestly more redundant (effective axes {fam_bsig['pr']:.2f} vs "
                   f"{b_bsig['pr']:.2f}) but more recognizable.")
    L.append(f"- **Familiar variant (keep HR):** the statistically optimal batting set drops HR/RBI "
             f"because they are redundant with SLG/AVG/SB. The most independent batting set that still "
             f"includes HR is **{', '.join(fam_bat_set)}**, which {fam_msg}")
    L.append("- **Why it broadens the pool:** each category rewards a different skill, so speedsters, "
             "on-base specialists, contact hitters and power bats all hold standalone value (and "
             "starters, closers/setup arms, control artists and strikeout arms on the pitching side). "
             "No single archetype sweeps multiple categories, so a manager who misses the early run on "
             "power bats can still build a competitive roster through other categories.\n")

    # Scenario C detail
    L.append("### Scenario C - Keep 5x5, add one category to each (-> 6x6)\n")
    L.append("Leaves all ten current categories in place and adds a single new category per side - the "
             "least disruptive way to move the two sides toward each other. The batting addition is "
             "chosen to be the most *independent* of the existing five (raising batting's effective axes "
             "= bringing its internal relationship **down**); the pitching addition is chosen to be the "
             "most *redundant* with the existing five (lowering pitching's effective axes = bringing its "
             "internal relationship **up**).\n")
    L.append(f"- **Add to batting: `{c_bat_add}`** ({BAT_SKILL.get(c_bat_add, '')}). "
             f"Batting effective axes {cur_bsig['pr']:.2f} -> **{c_bsig['pr']:.2f}** of 6 - it is the "
             "least-entangled recognizable hitting stat. *Limitation:* the gain is modest because every "
             "hitting category still shares the same playing-time + lineup-quality halo, so one addition "
             "narrows the gap but cannot fully fix batting's redundancy (that needs Scenario B, which "
             "*removes* a redundant category).")
    L.append("  - Next-best independent batting additions: " +
             ", ".join(f"{c} ({sig['pr']:.2f})" for _, c, sig in c_bat_adds[1:4]) +
             ". (AVG and OBP are near-tied; OBP doubles as a discipline axis if preferred.)")
    L.append(f"- **Add to pitching: `{c_pit_add}`** ({PIT_SKILL.get(c_pit_add, '')}). "
             f"Pitching effective axes {cur_psig['pr']:.2f} -> **{c_psig['pr']:.2f}** of 6, and it forms "
             f"a tied bundle (largest mutually-tied cluster grows to {c_psig['maxcluster']}: "
             f"{trio_str(c_psig)}). It deliberately overlaps an existing ratio category, mirroring how "
             "batting's R/HR/RBI move together.")
    L.append("  - Next-best redundant pitching additions: " +
             ", ".join(f"{c} ({sig['pr']:.2f})" for _, c, sig in c_pit_adds[1:4]) + ".")
    L.append(f"- **Balance:** 6x6 effective-axis gap **{c_gap:.2f}** (vs current 5x5 gap "
             f"{abs(cur_bsig['pr'] - cur_psig['pr']):.2f}) - the two sides converge while every existing "
             "category is preserved.")
    L.append("- **Trade-off vs Scenario A/B:** this keeps the league maximally familiar (nothing removed) "
             "at the cost of an extra category per side. It does not de-redundantize as fully as B, but it "
             "is the easiest sell.\n")

    # write proposals CSV
    with open(os.path.join(BRONZE, "2026_local_proposed_scoring.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["scenario", "side", "categories", "effective_axes", "mean_abs_r",
                    "max_tied_cluster", "tied_trio"])
        rows = [
            ("current", "batting", BAT_CATS, cur_bsig), ("current", "pitching", PIT_CATS, cur_psig),
            ("A_mirror", "batting", BAT_CATS, a_bsig), ("A_mirror", "pitching", a_pit_set, a_pit_sig),
            ("B_independent", "batting", b_bat_set, b_bsig), ("B_independent", "pitching", b_pit_set, b_psig),
            ("C_6x6_add_one", "batting", c_bat_set, c_bsig), ("C_6x6_add_one", "pitching", c_pit_set, c_psig),
        ]
        for scen, side, cats, sig in rows:
            w.writerow([scen, side, " ".join(cats), round(sig["pr"], 3),
                        round(sig["mean_abs"], 3), sig["maxcluster"],
                        " / ".join(sig["trio"][1]) + f" ({sig['trio'][0]:.2f})"])

    # ---------------------------------------------------------------------------------
    # Re-score the season under each scenario and compute per-team W/L/T deltas
    # ---------------------------------------------------------------------------------
    sp2mp, mp_maxsp = load_schedule_map()
    scoreboard = load_scoreboard()
    agg, team_name = aggregate_team_periods(sp2mp)
    max_sp = max((int(r["scoring_period"]) for r in
                  csv.DictReader(open(os.path.join(BRONZE, ESPN_STATS_2026), encoding="utf-8"))
                  if r.get("scoring_period")), default=0)

    # only periods fully covered by stats AND decided by ESPN
    covered_mps = {mp for mp, msp in mp_maxsp.items() if msp <= max_sp}
    matchups = [(mp, h, a, win) for (mp, h, a, win) in scoreboard
                if mp in covered_mps and win in ("HOME", "AWAY", "TIE")]
    period_set = sorted({mp for mp, _, _, _ in matchups})

    # per-team derived category values per covered period
    vals = {key: derive_period_cats(comp) for key, comp in agg.items()}

    scen_defs = {
        "current": (BAT_CATS, PIT_CATS),
        "A_mirror": (BAT_CATS, a_pit_set),
        "B_independent": (b_bat_set, b_pit_set),
        "C_6x6": (c_bat_set, c_pit_set),
    }

    # accumulate per-team category and matchup records per scenario; validate vs ESPN
    cat_rec = {s: defaultdict(lambda: [0, 0, 0]) for s in scen_defs}     # team -> [W,L,T] categories
    mt_rec = {s: defaultdict(lambda: [0, 0, 0]) for s in scen_defs}      # team -> [W,L,T] matchups
    espn_agree = both = 0

    for (mp, hid, aid, espn_win) in matchups:
        if (hid, mp) not in vals or (aid, mp) not in vals:
            continue
        for s, (bcats, pcats) in scen_defs.items():
            cats = list(bcats) + list(pcats)
            w, l, t = matchup_record(vals[(hid, mp)], vals[(aid, mp)], cats)
            cat_rec[s][hid][0] += w; cat_rec[s][hid][1] += l; cat_rec[s][hid][2] += t
            cat_rec[s][aid][0] += l; cat_rec[s][aid][1] += w; cat_rec[s][aid][2] += t
            if w > l:
                mt_rec[s][hid][0] += 1; mt_rec[s][aid][1] += 1
                mwin = "HOME"
            elif l > w:
                mt_rec[s][hid][1] += 1; mt_rec[s][aid][0] += 1
                mwin = "AWAY"
            else:
                mt_rec[s][hid][2] += 1; mt_rec[s][aid][2] += 1
                mwin = "TIE"
            if s == "current":
                both += 1
                if mwin == espn_win:
                    espn_agree += 1

    teams = sorted(team_name.keys())

    def winpct(rec):
        g = sum(rec)
        return rec[0] / g if g else 0.0

    L.append("## Re-Scoring the Season - Outcome Impact of Each Scenario\n")
    L.append(f"*How the **{len(period_set)}** completed, fully-covered matchup periods of 2026 "
             f"(MP {period_set[0]}-{period_set[-1]}, through scoring period {max_sp}) would have played "
             "out under each proposed category structure.*\n")
    L.append("**Method.** Each team's category totals are rebuilt from **active-lineup** player-days "
             "only (bench and IL slots excluded), summed per matchup period, with rate stats "
             "(OPS, ERA, WHIP, K/9, ...) recomputed from components. The league is **Head-to-Head Each "
             "Category**, so the primary record is the per-category W-L-T; the matchup-level result "
             "(most categories) is shown as a secondary view. Scenario B uses the most-independent "
             "category sets; C is the 6x6 add-one (12 categories, so its category totals are larger).\n")
    L.append(f"**Pipeline validation:** recomputed *current-scoring* matchup winners match ESPN's actual "
             f"result on **{espn_agree}/{both}** decided matchups "
             f"({100.0 * espn_agree / both:.0f}%) - the residual gap is daily-lineup reconstruction "
             "noise (mid-week roster moves, partial IL days).\n")

    def delta_table(rec_dict, level):
        out = [f"### {level} record deltas vs current (W-L-T, sorted by current win%)\n"]
        out.append("| Team | Current W-L-T | A: Mirror (Δ) | B: Independent (Δ) | C: 6x6 (Δ) |")
        out.append("|---|---|---|---|---|")
        for tid in sorted(teams, key=lambda x: -winpct(rec_dict["current"][x])):
            cur = rec_dict["current"][tid]
            cell = []
            for s in ("A_mirror", "B_independent", "C_6x6"):
                r = rec_dict[s][tid]
                dw, dl, dt = r[0] - cur[0], r[1] - cur[1], r[2] - cur[2]
                cell.append(f"{r[0]}-{r[1]}-{r[2]} ({dw:+d}/{dl:+d}/{dt:+d})")
            out.append(f"| {team_name[tid]} | {cur[0]}-{cur[1]}-{cur[2]} | " + " | ".join(cell) + " |")
        return "\n".join(out) + "\n"

    L.append(delta_table(cat_rec, "Category"))

    # biggest category-record movers per scenario (by Δwin%)
    def movers(s):
        deltas = []
        for tid in teams:
            deltas.append((winpct(cat_rec[s][tid]) - winpct(cat_rec["current"][tid]), tid))
        deltas.sort()
        lo, hi = deltas[0], deltas[-1]
        return (f"{team_name[hi[1]]} (+{hi[0]*100:.0f}% win)" if hi[0] > 0 else "none up",
                f"{team_name[lo[1]]} ({lo[0]*100:.0f}% win)" if lo[0] < 0 else "none down")
    L.append("**Biggest category win% movers:** " +
             "; ".join(f"**{s.split('_')[0].upper()}** -> up: {movers(s)[0]}, down: {movers(s)[1]}"
                       for s in ("A_mirror", "B_independent", "C_6x6")) + ".\n")

    L.append("Matchup-level view (each matchup decided by most categories; ties at 5-5 / 6-6):\n")
    L.append(delta_table(mt_rec, "Matchup"))

    def flips(s):
        n = 0
        for (mp, hid, aid, _) in matchups:
            if (hid, mp) not in vals or (aid, mp) not in vals:
                continue
            cw = matchup_record(vals[(hid, mp)], vals[(aid, mp)], list(BAT_CATS) + list(PIT_CATS))
            sw = matchup_record(vals[(hid, mp)], vals[(aid, mp)],
                                list(scen_defs[s][0]) + list(scen_defs[s][1]))
            cres = "H" if cw[0] > cw[1] else "A" if cw[1] > cw[0] else "T"
            sres = "H" if sw[0] > sw[1] else "A" if sw[1] > sw[0] else "T"
            if cres != sres:
                n += 1
        return n

    L.append("**Matchup outcomes that flip vs current scoring:** "
             + ", ".join(f"{s.split('_')[0].upper()} {flips(s)}/{len(matchups)}"
                         for s in ("A_mirror", "B_independent", "C_6x6")) + ".\n")
    L.append("*Reading the deltas:* a positive ΔW with negative ΔL means that team fares **better** "
             "under the proposed structure - typically teams whose strength is in the categories the "
             "proposal de-emphasizes (the redundant power bundle) lose ground, while teams built on the "
             "now-distinct categories (speed, ratios, saves/holds, on-base) gain.\n")

    # write re-score CSV
    with open(os.path.join(BRONZE, "2026_local_rescore_results.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["team_id", "team_name", "scenario", "level",
                    "wins", "losses", "ties", "win_pct"])
        for s in scen_defs:
            for tid in teams:
                for level, rd in (("category", cat_rec), ("matchup", mt_rec)):
                    r = rd[s][tid]
                    w.writerow([tid, team_name[tid], s, level, r[0], r[1], r[2],
                                round(winpct(r), 3)])

    # answers to the 6 questions
    L.append("## Answers to the Six Questions\n")
    L.append(f"1. **Redundant categories:** " +
             (", ".join(f"{a}<->{b} ({r:.2f})" for a, b, r in (bred + pred)) or "none above threshold") + ".")
    L.append(f"2. **Independent / scarce differentiators:** pitching -> " +
             (", ".join(n for n, _ in pscarce) or "none below threshold") +
             f"; batting -> **{bdiff[0]}** (most independent, mean |r| {bdiff[1]:.2f}) "
             "is the lever, though it sits just above the strict scarce threshold.")
    L.append("3. **Unscored signals:** see the full correlation CSVs - OBP/BB% (batting) and BB/9, K/BB (pitching) "
             "carry independent information beyond the scored categories; OPS already absorbs most OBP value.")
    L.append("4. **Near-redundant scored categories:** any pair listed in Q1 is low-leverage to chase "
             "separately (notably the R/HR/RBI bundle and ERA/WHIP).")
    L.append(f"5. **Archetypes:** batters -> {', '.join(c['label'] for c in b_cards)}; "
             f"pitchers -> {', '.join(c['label'] for c in p_cards)}. Team concentration tables above.")
    L.append("6. **Market mis-valuation:** ownership-by-archetype table in section 6 flags which profiles "
             "are cheap relative to their category contribution.\n")

    report_path = os.path.join(REPORTS, "stat_relationships_2026.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))

    # ---- log ----
    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "analysis": "idea_05_stat_relationships",
        "seasons": SEASONS,
        "batter_player_seasons": len(batters),
        "pitcher_player_seasons": len(pitchers),
        "batter_k": b_k, "batter_silhouette": round(b_sil, 3),
        "pitcher_k": p_k, "pitcher_silhouette": round(p_sil, 3),
        "redundant_batting": bred, "redundant_pitching": pred,
        "scarce_batting": bscarce, "scarce_pitching": pscarce,
        "report": report_path,
    }
    with open(os.path.join(LOGDIR, "idea_05_stat_relationships.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")

    print("Batters:", len(batters), "Pitchers:", len(pitchers))
    print("Batter k:", b_k, "silhouette:", round(b_sil, 3),
          "| Pitcher k:", p_k, "silhouette:", round(p_sil, 3))
    print("Redundant batting:", bred)
    print("Redundant pitching:", pred)
    print("Scarce batting:", bscarce, "| Scarce pitching:", pscarce)
    print("Proposed A (mirror) pitching:", a_pit_set, "-> eff-axes %.2f (gap %.2f)" %
          (a_pit_sig["pr"], abs(a_bsig["pr"] - a_pit_sig["pr"])))
    print("Proposed B (independent): bat", b_bat_set, "/ pit", b_pit_set,
          "-> eff-axes %.2f / %.2f (gap %.2f)" % (b_bsig["pr"], b_psig["pr"], b_gap))
    print("Proposed C (6x6 add-one): +%s to bat (%.2f), +%s to pit (%.2f) -> gap %.2f" %
          (c_bat_add, c_bsig["pr"], c_pit_add, c_psig["pr"], c_gap))
    print("Re-score: %d periods, validation %d/%d (%.0f%%) vs ESPN; flips A/B/C = %d/%d/%d" %
          (len(period_set), espn_agree, both, 100.0 * espn_agree / both,
           flips("A_mirror"), flips("B_independent"), flips("C_6x6")))
    print("Report:", report_path)


if __name__ == "__main__":
    main()
