"""
funnel.surrogate -- does a regressor trained on THIS target's own real Vina
mean-affinities rank better than the frozen v7 prescreen?

Offline. Zero docking. Nothing here changes the frozen v7 policy, the docking
params, or the ComputeRouter / ResourceManager / JobStore / tool-registry
contracts. ace2 data is not read.

Training set
    runs/baseline_cox2_v1.json -- 45 molecules, each with a mean best-affinity
    over 4 Vina seeds. That is a labelled dataset for exactly the quantity the
    cheap prescreen fails to predict.

Features (no new featurisation this pass)
    ECFP4 Morgan fingerprint, radius 2, 1024 bits -- identical to
    utils/rdkit_helper.extract_features and
    ml/training/train_all_models.smiles_to_fingerprint -- concatenated with the
    10 RDKit descriptors already cached in runs/features_cox2_v1.json.
    => 1034 features, n = 45.

Honest evaluation
    Leave-one-out. Every molecule's predicted affinity comes from a model refit
    on the other 44. The full-fit in-sample number is reported ONLY as a
    clearly-labelled leaked upper bound, never as the result.

    The surrogate is then used as a RANKER (sort ascending on predicted
    affinity) and scored with the existing recall@5 / recall@10 / frontier
    metrics against runs/baseline_cox2_v1.json, side by side with the frozen v7
    policy (runs/frontier_cox2_v1.csv).

Three model variants, fixed hyper-parameters, NO grid search, all reported
including losers. The primary is chosen by leave-one-out affinity Spearman
(a ranking-relevant regression metric) BEFORE any recall number is looked at.

  cd backend/app && ../venv/bin/python -m funnel.surrogate
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem
from sklearn.ensemble import RandomForestRegressor
from sklearn.kernel_ridge import KernelRidge
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from funnel.policy import DEFAULT_POLICY, DESCRIPTOR_NAMES
from funnel.schema import RUNS_DIR, RunRecord

RDLogger.DisableLog("rdApp.*")

SET_ID = "cox2_v1"
FP_RADIUS = 2
FP_BITS = 1024
NAMED_FAILURE = "CHEMBL2315019"   # baseline #1, -7.56, cox2 P=0.05, binding_score 5.35

# Three variants. One-line justification each. Hyper-parameters are fixed by
# convention, not searched.
VARIANTS = {
    "ridge": "linear L2 baseline; alpha=10 fixed, strong regularisation for p=1034 >> n=45",
    "rf": "the project's own model family; 300 trees, per-split feature subsampling handles p>>n, no scaling, fixed seed",
    "krr_tanimoto": "similarity regression, the textbook tiny-n fingerprint method; KernelRidge alpha=1.0 on a Tanimoto Gram matrix (fingerprint bits only)",
}


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------
def morgan_bits(smiles: str) -> np.ndarray:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"unparseable SMILES: {smiles}")
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, FP_RADIUS, nBits=FP_BITS)
    arr = np.zeros((FP_BITS,), dtype=np.float64)
    AllChem.DataStructs.ConvertToNumpyArray(fp, arr)
    return arr


def _tanimoto(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Pairwise Tanimoto (Jaccard) similarity between two binary bit matrices."""
    inter = A @ B.T
    a = A.sum(axis=1)[:, None]
    b = B.sum(axis=1)[None, :]
    return inter / (a + b - inter + 1e-12)


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------
def _fit_predict(kind: str, fp_tr, x_tr, y_tr, fp_te, x_te) -> np.ndarray:
    if kind == "ridge":
        m = make_pipeline(StandardScaler(), Ridge(alpha=10.0))
        m.fit(x_tr, y_tr)
        return m.predict(x_te)
    if kind == "rf":
        m = RandomForestRegressor(n_estimators=300, random_state=0, n_jobs=-1)
        m.fit(x_tr, y_tr)
        return m.predict(x_te)
    if kind == "krr_tanimoto":
        k_tr = _tanimoto(fp_tr, fp_tr)
        k_te = _tanimoto(fp_te, fp_tr)
        m = KernelRidge(kernel="precomputed", alpha=1.0)
        m.fit(k_tr, y_tr)
        return m.predict(k_te)
    raise ValueError(kind)


def loo_predict(kind: str, fp: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Leave-one-out out-of-fold predictions. Every fold refits on 44, predicts 1.
    Any preprocessing (scaling, the kernel) is refit inside the fold."""
    n = len(y)
    oof = np.full(n, np.nan)
    for i in range(n):
        tr = np.ones(n, dtype=bool)
        tr[i] = False
        oof[i] = _fit_predict(kind, fp[tr], x[tr], y[tr], fp[i:i + 1], x[i:i + 1])[0]
    assert not np.isnan(oof).any()
    return oof


def insample_predict(kind: str, fp: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Fit on everything, predict everything. LEAKED. Upper bound only."""
    return _fit_predict(kind, fp, x, y, fp, x)


# ---------------------------------------------------------------------------
# metrics
# ---------------------------------------------------------------------------
def _rankdata(a) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    order = a.argsort()
    ranks = np.empty(len(a), dtype=float)
    ranks[order] = np.arange(1, len(a) + 1)
    _, inv, counts = np.unique(a, return_inverse=True, return_counts=True)
    sums = np.zeros(len(counts))
    np.add.at(sums, inv, ranks)
    return (sums / counts)[inv]


def spearman(x, y) -> float:
    return float(np.corrcoef(_rankdata(x), _rankdata(y))[0, 1])


def regression_metrics(y_true, y_pred) -> dict:
    yt = np.asarray(y_true, float)
    yp = np.asarray(y_pred, float)
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    return {
        "r2": 1.0 - ss_res / ss_tot,
        "mae": float(np.mean(np.abs(yt - yp))),
        "rmse": float(np.sqrt(np.mean((yt - yp) ** 2))),
        "spearman": spearman(yt, yp),
        "pearson": float(np.corrcoef(yt, yp)[0, 1]),
    }


# ---------------------------------------------------------------------------
# recall / frontier against the cached baseline (same logic as funnel.frontier)
# ---------------------------------------------------------------------------
def _tie_partners(baseline: RunRecord) -> dict:
    groups: dict[str, set] = {}
    for e in baseline.results:
        if e.tie_group:
            groups.setdefault(e.tie_group, set()).add(e.ligand_id)
    return {e.ligand_id: (groups.get(e.tie_group, set()) - {e.ligand_id} if e.tie_group else set())
            for e in baseline.results}


def build_scorers(baseline: RunRecord):
    ties = _tie_partners(baseline)
    b_top5 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 5]
    b_top10 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 10]
    wall = {e.ligand_id: (e.dock_wall_s or 0.0) for e in baseline.results}
    full_wall = baseline.total_docking_wall_s

    def recall(target, docked, credited):
        if credited:
            return sum(1 for m in target if m in docked or (ties.get(m, set()) & docked))
        return sum(1 for m in target if m in docked)

    def frontier(order, nmax):
        rows = []
        for n in range(1, nmax + 1):
            d = set(order[:n])
            est = round(sum(wall[l] for l in d), 1)
            rows.append({
                "N": n, "docked": len(d),
                "r5l": recall(b_top5, d, False), "r5t": recall(b_top5, d, True),
                "r10l": recall(b_top10, d, False), "r10t": recall(b_top10, d, True),
                "est_wall_s": est,
                "speedup": round(full_wall / est, 1) if est else None,
            })
        return rows

    return recall, frontier, b_top5, b_top10


# ---------------------------------------------------------------------------
# plot (hand-written SVG, same house style as funnel.frontier)
# ---------------------------------------------------------------------------
def write_svg(path: Path, v7_rows, surr_rows, cap_n, named_enters_n) -> None:
    W, H = 780, 470
    ml, mr, mt, mb = 70, 30, 44, 58
    pw, ph = W - ml - mr, H - mt - mb
    xmax = max(r["N"] for r in surr_rows + v7_rows)
    ymax = 5

    def X(n):
        return ml + pw * (n / xmax)

    def Y(v):
        return mt + ph * (1 - v / ymax)

    def poly(rows, key):
        return " ".join(f"{X(r['N']):.1f},{Y(r[key]):.1f}" for r in rows)

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="20" text-anchor="middle" font-size="14" font-weight="600">'
        f'Surrogate vs frozen v7 -- recall@5 vs docking budget (cox2_v1, LOO, offline)</text>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333"/>',
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333"/>',
    ]
    for v in range(0, ymax + 1):
        p.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{ml+pw}" y2="{Y(v):.1f}" stroke="#eee"/>'
                 f'<text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end">{v}</text>')
    for n in range(0, xmax + 1, 5):
        p.append(f'<text x="{X(n):.1f}" y="{mt+ph+18:.1f}" text-anchor="middle">{n}</text>')
    p.append(f'<text x="{ml+pw/2}" y="{H-14}" text-anchor="middle">docking budget N (jobs = 4N)</text>')
    p.append(f'<text x="16" y="{mt+ph/2}" text-anchor="middle" '
             f'transform="rotate(-90 16 {mt+ph/2})">baseline top-5 recovered</text>')
    p.append(f'<line x1="{X(cap_n):.1f}" y1="{mt}" x2="{X(cap_n):.1f}" y2="{mt+ph}" '
             f'stroke="#c00" stroke-dasharray="4 3"/>'
             f'<text x="{X(cap_n):.1f}" y="{mt-6}" text-anchor="middle" fill="#c00">v7 filter cap N={cap_n}</text>')
    if named_enters_n:
        p.append(f'<line x1="{X(named_enters_n):.1f}" y1="{mt}" x2="{X(named_enters_n):.1f}" y2="{mt+ph}" '
                 f'stroke="#888" stroke-dasharray="2 2"/>'
                 f'<text x="{X(named_enters_n):.1f}" y="{mt+ph+40:.1f}" text-anchor="middle" fill="#666">'
                 f'surrogate docks {NAMED_FAILURE} at N={named_enters_n}</text>')
    p.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="2.5" points="{poly(surr_rows, "r5l")}"/>')
    p.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="2" stroke-dasharray="6 3" points="{poly(surr_rows, "r5t")}"/>')
    p.append(f'<polyline fill="none" stroke="#999" stroke-width="2" points="{poly(v7_rows, "r5l")}"/>')
    p.append(f'<polyline fill="none" stroke="#999" stroke-width="1.5" stroke-dasharray="6 3" points="{poly(v7_rows, "r5t")}"/>')
    lx, ly = ml + 20, mt + 14
    legend = [
        ("#1f77b4", "2.5", "", "surrogate recall@5 literal"),
        ("#1f77b4", "2", "6 3", "surrogate recall@5 tie-credited"),
        ("#999", "2", "", "v7 recall@5 literal"),
        ("#999", "1.5", "6 3", "v7 recall@5 tie-credited"),
    ]
    for i, (col, wdt, dash, lbl) in enumerate(legend):
        yy = ly + i * 17
        da = f' stroke-dasharray="{dash}"' if dash else ""
        p.append(f'<line x1="{lx}" y1="{yy}" x2="{lx+22}" y2="{yy}" stroke="{col}" stroke-width="{wdt}"{da}/>'
                 f'<text x="{lx+28}" y="{yy+4}">{lbl}</text>')
    p.append("</svg>")
    path.write_text("\n".join(p))


# ---------------------------------------------------------------------------
def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    feats_json = json.loads((RUNS_DIR / f"features_{SET_ID}.json").read_text())
    feats = feats_json["features"]

    entries = sorted(baseline.results, key=lambda e: e.rank)
    ligand_ids = [e.ligand_id for e in entries]
    smiles = {e.ligand_id: e.smiles for e in entries}
    y = np.array([e.mean_affinity for e in entries], dtype=float)
    assert len(ligand_ids) == 45 and not np.isnan(y).any()

    fp = np.vstack([morgan_bits(smiles[l]) for l in ligand_ids])
    desc = np.vstack([[feats[l]["descriptors"][k] for k in DESCRIPTOR_NAMES] for l in ligand_ids])
    x = np.hstack([fp, desc])
    assert x.shape == (45, FP_BITS + len(DESCRIPTOR_NAMES))

    # v7 hard-filter survivors (frozen policy, from the cached features)
    survivors = [l for l in ligand_ids
                 if DEFAULT_POLICY.descriptors_pass(feats[l]["descriptors"])[0]
                 and DEFAULT_POLICY.tox_pass(feats[l]["predictions"])[0]]
    dropped = [l for l in ligand_ids if l not in survivors]
    print(f"v7 hard-filter: {len(survivors)}/45 survive; dropped {dropped}")

    recall, frontier, b_top5, b_top10 = build_scorers(baseline)
    b_rank = {e.ligand_id: e.rank for e in entries}
    print(f"baseline true top-5: {[(l, b_rank[l]) for l in b_top5]}")
    print(f"named failure mode:  {NAMED_FAILURE}  (baseline #{b_rank[NAMED_FAILURE]}, "
          f"true {dict((e.ligand_id, e.mean_affinity) for e in entries)[NAMED_FAILURE]:+.2f} kcal/mol)\n")

    # ---- fit the 3 variants, LOO + leaked in-sample ----
    idx = {l: i for i, l in enumerate(ligand_ids)}
    results = {}
    for kind, why in VARIANTS.items():
        oof = loo_predict(kind, fp, x, y)
        ins = insample_predict(kind, fp, x, y)
        loo_m = regression_metrics(y, oof)
        ins_m = regression_metrics(y, ins)

        order_all = [l for l, _ in sorted(zip(ligand_ids, oof), key=lambda t: t[1])]
        order_surv = [l for l in order_all if l in set(survivors)]
        named_rank_all = order_all.index(NAMED_FAILURE) + 1
        named_rank_surv = order_surv.index(NAMED_FAILURE) + 1 if NAMED_FAILURE in order_surv else None
        named_pred = float(oof[idx[NAMED_FAILURE]])

        fr_all = frontier(order_all, 45)
        fr_surv = frontier(order_surv, len(order_surv))
        # in-sample (leaked) ranking, upper bound only
        ins_order_surv = [l for l, _ in sorted(zip(ligand_ids, ins), key=lambda t: t[1]) if l in set(survivors)]
        ins_r5l_at5 = recall(b_top5, set(ins_order_surv[:5]), False)
        ins_r5t_at5 = recall(b_top5, set(ins_order_surv[:5]), True)

        results[kind] = dict(
            why=why, oof=oof.tolist(), loo=loo_m, insample=ins_m,
            order_all=order_all, order_surv=order_surv,
            named_rank_all=named_rank_all, named_rank_surv=named_rank_surv, named_pred=named_pred,
            fr_all=fr_all, fr_surv=fr_surv,
            leaked_r5_at5=(ins_r5l_at5, ins_r5t_at5),
        )

    # ---- primary chosen by LOO affinity Spearman, BEFORE looking at recall ----
    primary = max(results, key=lambda k: results[k]["loo"]["spearman"])

    print("=== affinity regression (leave-one-out) -- all 3 variants ===")
    print(f"{'variant':<14} {'R2':>7} {'MAE':>7} {'RMSE':>7} {'Spearman':>9} {'Pearson':>8}   why")
    for kind, why in VARIANTS.items():
        m = results[kind]["loo"]
        star = "  <- primary (best LOO Spearman)" if kind == primary else ""
        print(f"{kind:<14} {m['r2']:>7.3f} {m['mae']:>7.3f} {m['rmse']:>7.3f} "
              f"{m['spearman']:>9.3f} {m['pearson']:>8.3f}   {why[:44]}{star}")

    print("\n=== LEAKED upper bound (fit on all 45, predict all 45 -- NOT the result) ===")
    for kind in VARIANTS:
        m = results[kind]["insample"]
        l5, t5 = results[kind]["leaked_r5_at5"]
        print(f"{kind:<14} in-sample R2={m['r2']:>6.3f} Spearman={m['spearman']:>6.3f}   "
              f"leaked recall@5 (N=5, v7-survivors) = {l5}/5 literal, {t5}/5 tie-credited")

    print(f"\n=== {NAMED_FAILURE} under each surrogate (LOO) -- the headline ===")
    print(f"{'variant':<14} {'LOO pred':>9} {'true':>7}   {'rank / 45 (all)':>16}   {'rank / 41 (v7 surv)':>20}")
    for kind in VARIANTS:
        r = results[kind]
        print(f"{kind:<14} {r['named_pred']:>+9.2f} {y[idx[NAMED_FAILURE]]:>+7.2f}   "
              f"{r['named_rank_all']:>16} {str(r['named_rank_surv']):>20}")

    # ---- side-by-side frontier vs v7 (filter-matched: surrogate over the 41 survivors) ----
    v7_csv = list(csv.DictReader((RUNS_DIR / f"frontier_{SET_ID}.csv").open()))
    v7_rows = [{"N": int(r["N"]),
                "r5l": int(r["recall5_literal"]), "r5t": int(r["recall5_tiecredit"]),
                "r10l": int(r["recall10_literal"]), "r10t": int(r["recall10_tiecredit"]),
                "speedup": float(r["speedup_vs_full"])} for r in v7_csv]
    v7_by_n = {r["N"]: r for r in v7_rows}
    surr = results[primary]
    surv_by_n = {r["N"]: r for r in surr["fr_surv"]}
    all_by_n = {r["N"]: r for r in surr["fr_all"]}
    nmax = 45

    print(f"\n=== frontier: frozen v7  vs  surrogate ({primary}), recall@5 [literal/tie] at every N ===")
    print("(v7 and surrogate-41 both rank only the 41 v7-survivors; surrogate-45 has no filter)\n")
    print(f"{'N':>3} {'v7 lit/tie':>11} {'surr41 lit/tie':>15} {'surr45 lit/tie':>15} "
          f"{'v7 r@10':>9} {'surr41 r@10':>12} {'speedup':>8}")
    print("-" * 92)
    for n in range(1, nmax + 1):
        v = v7_by_n.get(n)
        s41 = surv_by_n.get(n)
        s45 = all_by_n.get(n)
        if not v or not s45:
            continue
        s41txt = f"{s41['r5l']}/{s41['r5t']}" if s41 else "  -  "
        sp = s41["speedup"] if s41 else s45["speedup"]
        changed = (n == 1
                   or v7_by_n.get(n - 1, {}).get("r5l") != v["r5l"]
                   or v7_by_n.get(n - 1, {}).get("r5t") != v["r5t"]
                   or (surv_by_n.get(n - 1) or {}).get("r5l") != (s41 or {}).get("r5l")
                   or (surv_by_n.get(n - 1) or {}).get("r5t") != (s41 or {}).get("r5t")
                   or (all_by_n.get(n - 1) or {}).get("r5l") != s45["r5l"])
        if n <= 12 or n % 5 == 0 or changed or n == nmax:
            print(f"{n:>3} {v['r5l']:>5}/{v['r5t']:<5} {s41txt:>15} "
                  f"{s45['r5l']}/{s45['r5t']:<13} {v['r10l']:>4}/{v['r10t']:<4} "
                  f"{(str(s41['r10l'])+'/'+str(s41['r10t'])) if s41 else '-':>12} "
                  f"{(str(sp)+'x') if sp else '-':>8}")

    # first N to reach each recall@5 level
    def first_n(rows, key, lvl):
        r = next((x for x in rows if x[key] >= lvl), None)
        return r["N"] if r else None

    print("\nfirst N to reach recall@5:")
    print(f"{'level':>7} {'v7 lit':>8} {'v7 tie':>8} {'surr41 lit':>11} {'surr41 tie':>11} {'surr45 lit':>11} {'surr45 tie':>11}")
    for lvl in range(1, 6):
        print(f"{lvl:>5}/5 "
              f"{str(first_n(v7_rows, 'r5l', lvl)):>8} {str(first_n(v7_rows, 'r5t', lvl)):>8} "
              f"{str(first_n(surr['fr_surv'], 'r5l', lvl)):>11} {str(first_n(surr['fr_surv'], 'r5t', lvl)):>11} "
              f"{str(first_n(surr['fr_all'], 'r5l', lvl)):>11} {str(first_n(surr['fr_all'], 'r5t', lvl)):>11}")

    # ---- write artifacts ----
    out_csv = RUNS_DIR / f"frontier_surrogate_{SET_ID}.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["N", "v7_r5_literal", "v7_r5_tiecredit", "v7_r10_literal", "v7_r10_tiecredit",
                    f"surr41_{primary}_r5_literal", f"surr41_{primary}_r5_tiecredit",
                    f"surr41_{primary}_r10_literal", f"surr41_{primary}_r10_tiecredit",
                    f"surr45_{primary}_r5_literal", f"surr45_{primary}_r5_tiecredit",
                    f"surr45_{primary}_r10_literal", f"surr45_{primary}_r10_tiecredit",
                    "surr41_speedup_vs_full"])
        for n in range(1, nmax + 1):
            v = v7_by_n.get(n)
            s41 = surv_by_n.get(n)
            s45 = all_by_n.get(n)
            if not v or not s45:
                continue
            w.writerow([n, v["r5l"], v["r5t"], v["r10l"], v["r10t"],
                        s41["r5l"] if s41 else "", s41["r5t"] if s41 else "",
                        s41["r10l"] if s41 else "", s41["r10t"] if s41 else "",
                        s45["r5l"], s45["r5t"], s45["r10l"], s45["r10t"],
                        s41["speedup"] if s41 else ""])
    print(f"\nwrote {out_csv}")

    named_enters = next((r["N"] for r in surr["fr_surv"] if NAMED_FAILURE in set(surr["order_surv"][:r["N"]])), None)
    out_svg = RUNS_DIR / f"frontier_surrogate_{SET_ID}.svg"
    write_svg(out_svg, v7_rows, surr["fr_surv"], cap_n=len(survivors), named_enters_n=named_enters)
    print(f"wrote {out_svg}")

    out_json = RUNS_DIR / f"surrogate_{SET_ID}.json"
    out_json.write_text(json.dumps({
        "set_id": SET_ID,
        "n": 45,
        "features": f"ECFP4 radius {FP_RADIUS} / {FP_BITS} bits + {len(DESCRIPTOR_NAMES)} RDKit descriptors",
        "label": "mean best-affinity over 4 Vina seeds (runs/baseline_cox2_v1.json)",
        "cv": "leave-one-out (45 folds)",
        "primary": primary,
        "primary_selection_rule": "best leave-one-out affinity Spearman, chosen before any recall number",
        "v7_hard_filter_survivors": survivors,
        "v7_hard_filter_dropped": dropped,
        "ligand_ids_by_baseline_rank": ligand_ids,
        "true_mean_affinity": y.tolist(),
        "variants": {
            k: {
                "why": results[k]["why"],
                "loo_affinity": results[k]["loo"],
                "insample_affinity_LEAKED": results[k]["insample"],
                "oof_pred": results[k]["oof"],
                "order_all45": results[k]["order_all"],
                "order_41survivors": results[k]["order_surv"],
                f"{NAMED_FAILURE}_rank_of_45": results[k]["named_rank_all"],
                f"{NAMED_FAILURE}_rank_of_41": results[k]["named_rank_surv"],
                f"{NAMED_FAILURE}_loo_pred": results[k]["named_pred"],
                "frontier_all45": results[k]["fr_all"],
                "frontier_41survivors": results[k]["fr_surv"],
            } for k in VARIANTS
        },
    }, indent=2))
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
