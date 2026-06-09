"""
Description: Analyzes whether treating saves and holds as separate dimensions
             (sv_rate, hld_rate) gives better role separation than combined svhd_rate
             for MLB relief pitchers.
Source Data: closer_depth_fangraphs_2026.csv (snapshot 2026-06-01),
             stats_mlb_boxscore_2026.csv (full season, relief appearances only)
Outputs: Printed tables answering 5 analytical questions.
"""
import csv
from collections import defaultdict

# ── 1. Load FanGraphs snapshot 2026-06-01 ──────────────────────────────────────
TARGET_ROLES = {"Closer", "Closer Committee", "Setup Man", "Middle Reliever"}
fg = {}
with open(r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\closer_depth_fangraphs_2026.csv") as f:
    for row in csv.DictReader(f):
        if row["date_scraped"] == "2026-06-01" and row["role"] in TARGET_ROLES:
            name = row["player_name"].strip().lower()
            fg[name] = row["role"]

print(f"FG pitchers loaded: {len(fg)}")
role_counts = defaultdict(int)
for r in fg.values():
    role_counts[r] += 1
print("By role:", dict(role_counts))

# ── 2. Aggregate boxscore stats ────────────────────────────────────────────────
stats = defaultdict(lambda: {"games": 0, "total_sv": 0, "total_hld": 0, "total_outs": 0})
with open(r"C:\Users\peter.rigali\Desktop\acn_repo\data-lake\01_Bronze\fantasy_baseball\stats_mlb_boxscore_2026.csv") as f:
    for row in csv.DictReader(f):
        if row["b_or_p"] != "pitcher":
            continue
        if row["did_play"] != "1":
            continue
        gs = row["GS"].strip() if row["GS"].strip() else "0"
        if gs != "0":
            continue
        name = row["player_name"].strip().lower()
        s = stats[name]
        s["games"] += 1
        sv_val = row["SV"].strip()
        hld_val = row["HLD"].strip()
        outs_val = row["OUTS"].strip()
        s["total_sv"] += int(sv_val) if sv_val else 0
        s["total_hld"] += int(hld_val) if hld_val else 0
        s["total_outs"] += int(outs_val) if outs_val else 0

print(f"Pitchers in boxscore: {len(stats)}")

# ── 3. Match & compute rates ───────────────────────────────────────────────────
MIN_GAMES = 5
records = []
matched = 0
for name, role in fg.items():
    if name not in stats:
        continue
    s = stats[name]
    g = s["games"]
    if g < MIN_GAMES:
        continue
    sv_rate = s["total_sv"] / g
    hld_rate = s["total_hld"] / g
    avg_outs = s["total_outs"] / g
    matched += 1
    records.append({
        "name": name, "role": role, "games": g,
        "total_sv": s["total_sv"], "total_hld": s["total_hld"],
        "sv_rate": sv_rate, "hld_rate": hld_rate, "avg_outs": avg_outs
    })

print(f"Matched with >=5 games: {matched}")

# ── 4. Quadrant assignment ─────────────────────────────────────────────────────
SV_THRESH = 0.15
HLD_THRESH = 0.15

def quadrant(r):
    if r["sv_rate"] >= SV_THRESH and r["hld_rate"] < HLD_THRESH:
        return "Save Specialist"
    if r["sv_rate"] < SV_THRESH and r["hld_rate"] >= HLD_THRESH:
        return "Hold Specialist"
    if r["sv_rate"] >= SV_THRESH and r["hld_rate"] >= HLD_THRESH:
        return "Dual Role"
    return "Low Leverage"

for r in records:
    r["quadrant"] = quadrant(r)

# ── Q1: Quadrant % by role ─────────────────────────────────────────────────────
QUADS = ["Save Specialist", "Hold Specialist", "Dual Role", "Low Leverage"]
ROLES = ["Closer", "Closer Committee", "Setup Man", "Middle Reliever"]

role_quad = defaultdict(lambda: defaultdict(int))
for r in records:
    role_quad[r["role"]][r["quadrant"]] += 1

print("\n" + "=" * 90)
print("Q1: QUADRANT DISTRIBUTION BY ROLE  (sv_rate>=0.15 / hld_rate>=0.15 thresholds)")
print("=" * 90)
header = f"{'Role':<22}" + "".join(f"{q:>18}" for q in QUADS) + f"{'Total':>8}"
print(header)
print("-" * 90)
for role in ROLES:
    total = sum(role_quad[role].values())
    if total == 0:
        continue
    row_str = f"{role:<22}"
    for q in QUADS:
        pct = 100 * role_quad[role][q] / total
        row_str += f"{pct:>16.1f}%"
    row_str += f"{total:>8}"
    print(row_str)

# ── Q2: sv_hld_ratio ──────────────────────────────────────────────────────────
def median(lst):
    s = sorted(lst)
    n = len(s)
    if n == 0:
        return float("nan")
    return s[n // 2] if n % 2 == 1 else (s[n // 2 - 1] + s[n // 2]) / 2

ratios_by_role = defaultdict(list)
for r in records:
    denom = r["sv_rate"] + r["hld_rate"]
    if denom == 0:
        r["sv_hld_ratio"] = None
    else:
        ratio = r["sv_rate"] / denom
        r["sv_hld_ratio"] = ratio
        ratios_by_role[r["role"]].append(ratio)

print("\n" + "=" * 60)
print("Q2: sv_hld_ratio BY ROLE  (sv_rate / (sv_rate + hld_rate))")
print("=" * 60)
print(f"{'Role':<22} {'Mean':>8} {'Median':>8} {'N':>6}")
print("-" * 48)
for role in ROLES:
    vals = ratios_by_role[role]
    if not vals:
        print(f"{role:<22} {'n/a':>8} {'n/a':>8} {'0':>6}")
        continue
    mn = sum(vals) / len(vals)
    med = median(vals)
    print(f"{role:<22} {mn:>8.3f} {med:>8.3f} {len(vals):>6}")

# Best threshold to separate Closer vs Setup Man
closer_ratios = ratios_by_role["Closer"]
setup_ratios = ratios_by_role["Setup Man"]
best_thresh = None
best_acc = 0
for t_int in range(10, 96):
    t = t_int / 100
    tp = sum(1 for v in closer_ratios if v >= t)
    tn = sum(1 for v in setup_ratios if v < t)
    total_n = len(closer_ratios) + len(setup_ratios)
    acc = (tp + tn) / total_n if total_n else 0
    if acc > best_acc:
        best_acc = acc
        best_thresh = t

print(f"\nBest sv_hld_ratio threshold separating Closer vs Setup Man: {best_thresh:.2f}  (accuracy {best_acc:.1%})")
if best_thresh:
    tp = sum(1 for v in closer_ratios if v >= best_thresh)
    fp = sum(1 for v in setup_ratios if v >= best_thresh)
    print(f"  Closers >= {best_thresh:.2f}: {tp}/{len(closer_ratios)}  |  Setup Men >= {best_thresh:.2f}: {fp}/{len(setup_ratios)}")

# ── Q3: Closer Committee breakdown ────────────────────────────────────────────
print("\n" + "=" * 60)
print("Q3: CLOSER COMMITTEE BREAKDOWN")
print("=" * 60)
comm = [r for r in records if r["role"] == "Closer Committee"]
n_comm = len(comm)
if n_comm:
    dual_10 = sum(1 for r in comm if r["sv_rate"] >= 0.10 and r["hld_rate"] >= 0.10)
    for q in QUADS:
        cnt = sum(1 for r in comm if r["quadrant"] == q)
        print(f"  {q:<22}: {cnt:>3}  ({100*cnt/n_comm:.1f}%)")
    print(f"  {'--- dual role (>=0.10/0.10)':<24}: {dual_10:>3}  ({100*dual_10/n_comm:.1f}%)")
    comm_ratios = [r["sv_hld_ratio"] for r in comm if r.get("sv_hld_ratio") is not None]
    if comm_ratios:
        mn = sum(comm_ratios) / len(comm_ratios)
        med = median(comm_ratios)
        print(f"  sv_hld_ratio  mean={mn:.3f}  median={med:.3f}  N={len(comm_ratios)}")
    print(f"  Total committee pitchers: {n_comm}")

print("\nMean sv_hld_ratio by role (for comparison):")
for role in ROLES:
    vals = ratios_by_role[role]
    if vals:
        mn = sum(vals) / len(vals)
        print(f"  {role:<22}: {mn:.3f}")

# ── Q4: Middle Reliever vs Setup Man hld_rate boundary ───────────────────────
print("\n" + "=" * 70)
print("Q4: MIDDLE RELIEVER vs SETUP MAN — hld_rate thresholds")
print("=" * 70)
setup_all = [r for r in records if r["role"] == "Setup Man"]
mid_all = [r for r in records if r["role"] == "Middle Reliever"]
for thresh in [0.15, 0.20, 0.25]:
    s_above = sum(1 for r in setup_all if r["hld_rate"] >= thresh)
    m_above = sum(1 for r in mid_all if r["hld_rate"] >= thresh)
    s_pct = 100 * s_above / len(setup_all) if setup_all else 0
    m_pct = 100 * m_above / len(mid_all) if mid_all else 0
    print(f"  hld_rate >= {thresh:.2f}:  Setup Man {s_above}/{len(setup_all)} ({s_pct:.1f}%)   Middle Reliever {m_above}/{len(mid_all)} ({m_pct:.1f}%)")

# ── Q5: avg_outs by quadrant ──────────────────────────────────────────────────
print("\n" + "=" * 60)
print("Q5: MEAN avg_outs BY QUADRANT")
print("=" * 60)
quad_outs = defaultdict(list)
quad_roles_detail = defaultdict(lambda: defaultdict(list))
for r in records:
    quad_outs[r["quadrant"]].append(r["avg_outs"])
    quad_roles_detail[r["quadrant"]][r["role"]].append(r["avg_outs"])

print(f"{'Quadrant':<22} {'Mean avg_outs':>14} {'N':>6}")
print("-" * 44)
for q in QUADS:
    vals = quad_outs[q]
    if not vals:
        print(f"{q:<22} {'n/a':>14} {'0':>6}")
        continue
    mn = sum(vals) / len(vals)
    print(f"{q:<22} {mn:>14.2f} {len(vals):>6}")

print("\nMean avg_outs by role within each quadrant:")
for q in QUADS:
    print(f"  {q}:")
    for role in ROLES:
        vals = quad_roles_detail[q][role]
        if vals:
            mn = sum(vals) / len(vals)
            print(f"    {role:<22}: {mn:.2f}  (N={len(vals)})")

# ── Supplemental: sv_rate / hld_rate means by role ───────────────────────────
print("\n" + "=" * 65)
print("SUPPLEMENTAL: mean sv_rate and hld_rate by role")
print("=" * 65)
sv_by_role = defaultdict(list)
hld_by_role = defaultdict(list)
for r in records:
    sv_by_role[r["role"]].append(r["sv_rate"])
    hld_by_role[r["role"]].append(r["hld_rate"])

print(f"{'Role':<22} {'mean sv_rate':>14} {'mean hld_rate':>14} {'N':>6}")
print("-" * 58)
for role in ROLES:
    sv_vals = sv_by_role[role]
    hld_vals = hld_by_role[role]
    if not sv_vals:
        continue
    print(f"{role:<22} {sum(sv_vals)/len(sv_vals):>14.3f} {sum(hld_vals)/len(hld_vals):>14.3f} {len(sv_vals):>6}")
