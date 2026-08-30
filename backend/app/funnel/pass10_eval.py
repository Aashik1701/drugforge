"""
funnel.pass10_eval -- Pass 10 evaluation. Reads the four feature families cached
by funnel.receptor_features and scores them against both cached baselines.

LOO exactly as Pass 5 (rf, n_estimators=300, random_state=0, refit per fold, no
scaling). No tuning against recall. No new docking. Frozen contracts untouched.

  Task 2  LOO Spearman / R^2 / MAE per family per target; each family as a
          ranker through the frontier logic (recall@10 primary, recall@5
          secondary); ranks of the known-hard molecules.
  Task 3  cross-target transfer: fit on all of one target, predict the other.

F4 (pose-derived) is ACE2-only and CEILING-ONLY -- reported separately, never as
a prescreen candidate.

  cd backend/app && ../venv/bin/python -m funnel.pass10_eval
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from funnel.schema import RUNS_DIR, RunRecord
from funnel.surrogate import _fit_predict, _rankdata

HARD = {
    "cox2_v1": ["CHEMBL2315019"],
    "ace2_v1": ["CHEMBL402987", "CHEMBL252417", "CHEMBL400527"],  # baseline #2/#3/#5
}
PASS5_REF = {  # first N to full recovery, from CHANGELOG Pass 5 / Pass 9
    "cox2_v1": {"v7_r5": 32, "v7_r10": 36, "surrogate_r5": 21, "surrogate_r10": 21},
    "ace2_v1": {"v7_r5": 30, "v7_r10": 35, "surrogate_r5": None, "surrogate_r10": None},
}


def spearman(x, y):
    return float(np.corrcoef(_rankdata(x), _rankdata(y))[0, 1])


def reg_metrics(yt, yp):
    yt, yp = np.asarray(yt, float), np.asarray(yp, float)
    ss_res = float(np.sum((yt - yp) ** 2))
    ss_tot = float(np.sum((yt - yt.mean()) ** 2))
    return {"spearman": spearman(yt, yp), "r2": 1 - ss_res / ss_tot,
            "mae": float(np.mean(np.abs(yt - yp)))}


def loo(X, y):
    n = len(y)
    oof = np.full(n, np.nan)
    for i in range(n):
        tr = np.ones(n, bool); tr[i] = False
        oof[i] = _fit_predict("rf", X[tr], X[tr], y[tr], X[i:i + 1], X[i:i + 1])[0]
    assert not np.isnan(oof).any()
    return oof


# --- frontier / recall against a baseline RunRecord ---------------------------
def scorers(baseline: RunRecord, id_order: list[str]):
    groups: dict[str, set] = {}
    for e in baseline.results:
        if e.tie_group:
            groups.setdefault(e.tie_group, set()).add(e.ligand_id)
    ties = {e.ligand_id: (groups.get(e.tie_group, set()) - {e.ligand_id} if e.tie_group else set())
            for e in baseline.results}
    b_rank = {e.ligand_id: e.rank for e in baseline.results}
    b_top5 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 5]
    b_top10 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 10]

    def recall(target, docked, credited):
        if credited:
            return sum(1 for m in target if m in docked or (ties.get(m, set()) & docked))
        return sum(1 for m in target if m in docked)

    def frontier(order):
        rows = []
        for n in range(1, len(order) + 1):
            d = set(order[:n])
            rows.append({"N": n,
                         "r5l": recall(b_top5, d, False), "r5t": recall(b_top5, d, True),
                         "r10l": recall(b_top10, d, False), "r10t": recall(b_top10, d, True)})
        return rows

    def first_n(rows, key, lvl):
        r = next((x for x in rows if x[key] >= lvl), None)
        return r["N"] if r else None

    return b_rank, frontier, first_n


def load_family(set_id: str, fam: str):
    doc = json.loads((RUNS_DIR / f"features_receptor_{set_id}.json").read_text())
    rows = doc["rows"]
    ids = [lid for lid in rows if rows[lid][fam] is not None]
    X = np.array([rows[lid][fam] for lid in ids], dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    return ids, X, doc["columns"][fam]


def eval_target(set_id: str) -> dict:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{set_id}.json")
    aff = {e.ligand_id: e.mean_affinity for e in baseline.results if e.mean_affinity is not None}
    fams = ["F1", "F2", "F3"] + (["F4"] if set_id == "ace2_v1" else [])
    out = {"set_id": set_id, "families": {}}
    print("\n" + "=" * 96)
    print(f"TARGET {set_id}   (n usable = {len(aff)})")
    print("=" * 96)
    print(f"{'family':<6} {'usable?':<14} {'n':>4} {'LOO Spearman':>13} {'R^2':>8} {'MAE':>7}   "
          f"{'r@10 5/10':>10} {'r@10 10/10':>11} {'r@5 5/5':>9}   hard-molecule ranks")
    for fam in fams:
        ids_all, X_all, cols = load_family(set_id, fam)
        ids = [i for i in ids_all if i in aff]
        idx = [ids_all.index(i) for i in ids]
        X = X_all[idx]
        y = np.array([aff[i] for i in ids])
        oof = loo(X, y)
        m = reg_metrics(y, oof)

        order = [i for i, _ in sorted(zip(ids, oof), key=lambda t: t[1])]
        b_rank, frontier, first_n = scorers(baseline, order)
        fr = frontier(order)
        n_r10_5 = first_n(fr, "r10l", 5)
        n_r10_10 = first_n(fr, "r10l", 10)
        n_r5_5 = first_n(fr, "r5l", 5)
        hard_ranks = {h: (order.index(h) + 1 if h in order else None) for h in HARD[set_id]}
        usable = "prescreen" if fam != "F4" else "CEILING-ONLY"

        out["families"][fam] = {
            "prescreen_usable": fam != "F4", "n": len(y), "n_features": X.shape[1],
            "loo": m, "oof_order": order, "frontier": fr,
            "first_n": {"r10l_5": n_r10_5, "r10l_10": n_r10_10, "r10t_10": first_n(fr, "r10t", 10),
                        "r5l_5": n_r5_5, "r5t_5": first_n(fr, "r5t", 5)},
            "hard_molecule_ranks": hard_ranks,
        }
        print(f"{fam:<6} {usable:<14} {len(y):>4} {m['spearman']:>13.3f} {m['r2']:>8.3f} {m['mae']:>7.3f}   "
              f"{str(n_r10_5):>10} {str(n_r10_10):>11} {str(n_r5_5):>9}   {hard_ranks}")

    ref = PASS5_REF[set_id]
    print(f"\nreference (first N to full recovery): frozen v7  r@10 N={ref['v7_r10']}, r@5 N={ref['v7_r5']}"
          + (f"   Pass-5 surrogate r@10 N={ref['surrogate_r10']}, r@5 N={ref['surrogate_r5']}"
             if ref['surrogate_r10'] else "   (no Pass-5 surrogate reference for ace2)"))
    print("note: families rank the full usable set (no v7 hard filter), so their first-N is not")
    print("      identical-basis to the published v7 (41/38-survivor) frontier; treat as indicative.")
    return out


def cross_target_transfer(results: dict) -> dict:
    print("\n" + "=" * 96)
    print("TASK 3 -- CROSS-TARGET TRANSFER  (fit on all of A, predict all of B; Spearman(pred, true))")
    print("=" * 96)
    base = {s: RunRecord.load(RUNS_DIR / f"baseline_{s}.json") for s in ("cox2_v1", "ace2_v1")}
    aff = {s: {e.ligand_id: e.mean_affinity for e in base[s].results if e.mean_affinity is not None}
           for s in base}
    transfer = {}
    print(f"{'family':<6} {'cox2_v1 -> ace2_v1':>20} {'ace2_v1 -> cox2_v1':>20}   note")
    for fam in ("F1", "F2", "F3"):
        res = {}
        for a, b in (("cox2_v1", "ace2_v1"), ("ace2_v1", "cox2_v1")):
            ida, Xa_all, _ = load_family(a, fam)
            idb, Xb_all, _ = load_family(b, fam)
            ida = [i for i in ida if i in aff[a]]
            idb = [i for i in idb if i in aff[b]]
            Xa = np.nan_to_num(np.array([Xa_all[load_family(a, fam)[0].index(i)] for i in ida], float))
            Xb = np.nan_to_num(np.array([Xb_all[load_family(b, fam)[0].index(i)] for i in idb], float))
            ya = np.array([aff[a][i] for i in ida]); yb = np.array([aff[b][i] for i in idb])
            pred = _fit_predict("rf", Xa, Xa, ya, Xb, Xb)
            res[f"{a}->{b}"] = {"spearman": spearman(pred, yb), "r2": reg_metrics(yb, pred)["r2"]}
        transfer[fam] = res
        note = "ligand-only, no receptor info" if fam == "F1" else "receptor-aware (pocket columns differ per target)"
        print(f"{fam:<6} {res['cox2_v1->ace2_v1']['spearman']:>20.3f} {res['ace2_v1->cox2_v1']['spearman']:>20.3f}   {note}")
    return transfer


def main() -> int:
    results = {s: eval_target(s) for s in ("cox2_v1", "ace2_v1")}
    transfer = cross_target_transfer(results)

    # --- headline read against the pre-registered bar ---
    print("\n" + "=" * 96)
    print("BAR CHECK (pre-registered, CHANGELOG Pass 10)")
    print("=" * 96)
    f1_cox2 = results["cox2_v1"]["families"]["F1"]["loo"]["spearman"]
    f1_ace2 = results["ace2_v1"]["families"]["F1"]["loo"]["spearman"]
    print(f"control F1 LOO Spearman: cox2 {f1_cox2:+.3f}   ace2 {f1_ace2:+.3f}")
    for fam in ("F2", "F3"):
        c = results["cox2_v1"]["families"][fam]["loo"]["spearman"]
        a = results["ace2_v1"]["families"][fam]["loo"]["spearman"]
        beats_cox2 = c > f1_cox2
        ace2_signal = (a > f1_ace2) and (a > 0.2)
        verdict = "CLEARS BAR" if (beats_cox2 and ace2_signal) else "does not clear bar"
        print(f"  {fam}: cox2 {c:+.3f} ({'beats' if beats_cox2 else 'below'} F1)   "
              f"ace2 {a:+.3f} ({'signal' if ace2_signal else 'no signal vs F1/0.2'})  -> {verdict}")
    print("\ntransfer: positive Spearman in >=1 direction for a receptor-aware family, where F1 ~ 0:")
    for fam in ("F1", "F2", "F3"):
        s1 = transfer[fam]["cox2_v1->ace2_v1"]["spearman"]
        s2 = transfer[fam]["ace2_v1->cox2_v1"]["spearman"]
        print(f"  {fam}: cox2->ace2 {s1:+.3f}   ace2->cox2 {s2:+.3f}   "
              f"{'POSITIVE somewhere' if max(s1, s2) > 0.1 else 'no positive transfer'}")
    if "F4" in results["ace2_v1"]["families"]:
        f4 = results["ace2_v1"]["families"]["F4"]["loo"]
        print(f"\nF4 pose ceiling (ace2, NOT a prescreen): LOO Spearman {f4['spearman']:+.3f}, "
              f"R^2 {f4['r2']:+.3f}, MAE {f4['mae']:.3f}")
        print(f"  {'-> pose knowledge DOES linearly carry affinity signal' if f4['r2'] > 0.3 else '-> even the real pose does not linearly predict affinity (R^2 < 0.3): surrogate direction is bounded'}")

    out = RUNS_DIR / "pass10_eval.json"
    out.write_text(json.dumps({"targets": results, "transfer": transfer}, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
