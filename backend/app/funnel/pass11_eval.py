"""
funnel.pass11_eval -- Pass 11, the FINAL pass. Are F1 (ligand-only ECFP4+desc)
and F3 (pharmacophore x pocket) complementary as rankers, or is the funnel
prescreen investigation closed?

Three combination methods, pre-registered in CHANGELOG Pass 11:
  C1  rank-average of the two LOO orderings
  C2  concat features -> single rf, LOO
  C3  F1 order, its top-K re-sorted by F3's LOO prediction (K = F1's own
      first-N-to-recall@10-10/10: 22 on cox2, 21 on ACE2)

Declared margin (both targets simultaneously): LOO Spearman > better single
family by >= 0.05 AND full recall@10 literal reached >= 3 N earlier.

LOO exactly as Pass 5 (rf 300 trees, random_state=0, refit per fold). No tuning
against recall. No new docking. Frozen contracts untouched. Published numbers
are appended to, not edited.

  cd backend/app && ../venv/bin/python -m funnel.pass11_eval
"""

from __future__ import annotations

import json

import numpy as np

from funnel.pass10_eval import HARD, load_family, loo, reg_metrics, scorers, spearman
from funnel.schema import RUNS_DIR, RunRecord
from funnel.surrogate import _fit_predict, _rankdata

K_C3 = {"cox2_v1": 22, "ace2_v1": 21}   # F1's first N to recall@10 10/10 (Pass 10), fixed before this pass
MARGIN_SPEARMAN = 0.05
MARGIN_N = 3


def order_from_pred(ids, pred):
    return [i for i, _ in sorted(zip(ids, pred), key=lambda t: t[1])]


def first_n(rows, key, lvl):
    r = next((x for x in rows if x[key] >= lvl), None)
    return r["N"] if r else None


def eval_target(set_id: str) -> dict:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{set_id}.json")
    aff = {e.ligand_id: e.mean_affinity for e in baseline.results if e.mean_affinity is not None}

    def matrix(fam):
        ids_all, X_all, _ = load_family(set_id, fam)
        ids = [i for i in ids_all if i in aff]
        idx = [ids_all.index(i) for i in ids]
        return ids, np.nan_to_num(X_all[idx], nan=0.0, posinf=0.0, neginf=0.0)

    ids1, X1 = matrix("F1")
    ids3, X3 = matrix("F3")
    assert ids1 == ids3
    ids = ids1
    y = np.array([aff[i] for i in ids])

    oof1 = loo(X1, y)
    oof3 = loo(X3, y)
    ord1 = order_from_pred(ids, oof1)
    ord3 = order_from_pred(ids, oof3)

    # C1 rank-average
    r1 = {i: k for k, i in enumerate(ord1)}
    r3 = {i: k for k, i in enumerate(ord3)}
    avg_rank = np.array([(r1[i] + r3[i]) / 2 for i in ids])
    ordC1 = order_from_pred(ids, avg_rank)

    # C2 concat + single rf
    Xc = np.hstack([X1, X3])
    oofC2 = loo(Xc, y)
    ordC2 = order_from_pred(ids, oofC2)

    # C3 F1 order, top-K re-sorted by F3 pred
    K = K_C3[set_id]
    head = ord1[:K]
    head_resorted = [i for i, _ in sorted(((i, oof3[ids.index(i)]) for i in head), key=lambda t: t[1])]
    ordC3 = head_resorted + ord1[K:]

    b_rank, frontier, _fn = scorers(baseline, ord1)

    def summarise(name, order, oof=None):
        fr = frontier(order)
        # ranking-quality Spearman: final position vs true-affinity position
        pos = np.array([order.index(i) for i in ids], dtype=float)
        sp = spearman(-pos, -y)  # both ascending-better -> correlation of "goodness"
        row = {
            "name": name,
            "loo_spearman": float(sp) if oof is None else spearman(oof, y),
            "r2": (reg_metrics(y, oof)["r2"] if oof is not None else None),
            "mae": (reg_metrics(y, oof)["mae"] if oof is not None else None),
            "first_n": {
                "r10l_10": first_n(fr, "r10l", 10), "r10t_10": first_n(fr, "r10t", 10),
                "r5l_5": first_n(fr, "r5l", 5), "r5t_5": first_n(fr, "r5t", 5),
                "r10l_5": first_n(fr, "r10l", 5),
            },
            "hard_ranks": {h: (order.index(h) + 1 if h in order else None) for h in HARD[set_id]},
            "order": order,
        }
        return row

    rows = [
        summarise("F1", ord1, oof1),
        summarise("F3", ord3, oof3),
        summarise("C1_rank_avg", ordC1, None),
        summarise("C2_concat_rf", ordC2, oofC2),
        summarise("C3_f1_then_f3_rerank_topK", ordC3, None),
    ]
    return {"set_id": set_id, "n": len(y), "K_C3": K, "rows": {r["name"]: r for r in rows}}


def main() -> int:
    res = {s: eval_target(s) for s in ("cox2_v1", "ace2_v1")}

    for s in ("cox2_v1", "ace2_v1"):
        t = res[s]
        print("\n" + "=" * 104)
        print(f"TARGET {s}  (n={t['n']}, C3 K={t['K_C3']})")
        print("=" * 104)
        print(f"{'method':<28} {'LOO Spearman':>13} {'R^2':>8} {'MAE':>7}   "
              f"{'r@10 10/10':>11} {'r@10t 10/10':>12} {'r@5 5/5':>9}   hard-molecule ranks")
        for name in ("F1", "F3", "C1_rank_avg", "C2_concat_rf", "C3_f1_then_f3_rerank_topK"):
            r = t["rows"][name]
            r2 = f"{r['r2']:.3f}" if r["r2"] is not None else "  n/a"
            mae = f"{r['mae']:.3f}" if r["mae"] is not None else "  n/a"
            fn = r["first_n"]
            print(f"{name:<28} {r['loo_spearman']:>13.3f} {r2:>8} {mae:>7}   "
                  f"{str(fn['r10l_10']):>11} {str(fn['r10t_10']):>12} {str(fn['r5l_5']):>9}   {r['hard_ranks']}")

    # --- declared-margin check, both targets simultaneously ---
    print("\n" + "=" * 104)
    print("DECLARED-MARGIN CHECK (pre-registered Pass 11): both targets, "
          f"LOO Spearman > better-single by >= {MARGIN_SPEARMAN}  AND  recall@10 literal 10/10 reached >= {MARGIN_N} N earlier")
    print("=" * 104)
    verdicts = {}
    for method in ("C1_rank_avg", "C2_concat_rf", "C3_f1_then_f3_rerank_topK"):
        per_target = {}
        for s in ("cox2_v1", "ace2_v1"):
            t = res[s]["rows"]
            best_sp = max(t["F1"]["loo_spearman"], t["F3"]["loo_spearman"])
            best_n = min(x for x in (t["F1"]["first_n"]["r10l_10"], t["F3"]["first_n"]["r10l_10"]) if x is not None)
            m_sp = t[method]["loo_spearman"]
            m_n = t[method]["first_n"]["r10l_10"]
            d_sp = m_sp - best_sp
            d_n = (best_n - m_n) if m_n is not None else -99
            per_target[s] = {"d_spearman": d_sp, "d_N": d_n,
                             "clears": (d_sp >= MARGIN_SPEARMAN and d_n >= MARGIN_N)}
        both = per_target["cox2_v1"]["clears"] and per_target["ace2_v1"]["clears"]
        verdicts[method] = {"per_target": per_target, "clears_both": both}
        print(f"\n{method}")
        for s in ("cox2_v1", "ace2_v1"):
            p = per_target[s]
            print(f"  {s:<9}  d(Spearman)={p['d_spearman']:+.3f}  d(N to r@10 10/10)={p['d_N']:+d}  "
                  f"-> {'clears' if p['clears'] else 'does NOT clear'}")
        print(f"  BOTH TARGETS: {'CLEARS THE DECLARED MARGIN' if both else 'does not clear'}")

    any_clear = any(v["clears_both"] for v in verdicts.values())
    print("\n" + "=" * 104)
    print("OUTCOME:", "a method cleared the margin -- see above" if any_clear
          else "NO method clears the declared margin on both targets. F1 and F3 are NOT complementary.")
    print("=" * 104)

    out = RUNS_DIR / "pass11_eval.json"
    out.write_text(json.dumps({"targets": res, "margin_check": verdicts,
                               "margin": {"spearman": MARGIN_SPEARMAN, "N": MARGIN_N},
                               "any_method_clears_both": any_clear}, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
