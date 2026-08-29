"""
funnel.heldout_ace2 -- score the FROZEN v7 policy against the held-out ACE2
baseline, one pass, no tuning.

Reads runs/baseline_ace2_v1.json (produced by
`funnel.baseline --set-id ace2_v1 --target ace2`, the corrected Zn-centred
box, identical docking config to cox2). Builds the LOCAL prescreen features
for the 45 ace2 candidates ONCE via the compute fabric (the frozen policy's
cheap input -- computing it is the evaluation, not tuning) and caches them to
runs/features_ace2_v1.json in the same format funnel.features writes.

Then, using the UNCHANGED frozen policy (funnel.policy.DEFAULT_POLICY =
v7_binding_weak_cox2) and the UNCHANGED frontier logic
(funnel.frontier.prescreen_order / _tie_partners):

  Task 1  held-out recall vs docking budget: recall@10 literal + tie-credited
          (primary, per Pass 8), recall@5 literal + tie-credited (secondary),
          false-negative count, mean baseline rank of picks, side by side with
          cox2 at the same N. Pre-registered prediction (Pass 4) checked.
  Task 2  concentration analysis on ace2_v1: the straggler(s), whether the
          difficulty is one dominant molecule or diffuse, the ACE2 analogue of
          CHEMBL2315019 (a top docker invisible to the cheap models) with its
          cheap-model scores and prescreen rank.
  Task 3  run sanity: completion / failures, reference-ligand order + affinity
          vs the box-fix sanity docks, seed-stdev distribution vs cox2 and vs
          TIE_EPSILON.

No new docking. No new policy, surrogate, or seed strategy. Frozen contracts
untouched.

  cd backend/app && COMPUTE_MODE=balanced ../venv/bin/python -m funnel.heldout_ace2
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import statistics
from pathlib import Path

os.environ.setdefault("COMPUTE_MODE", "balanced")

from funnel.candidate_set import load_candidate_set
from funnel.frontier import _tie_partners, prescreen_order
from funnel.policy import DEFAULT_POLICY, DESCRIPTOR_NAMES
from funnel.ranking import TIE_EPSILON
from funnel.schema import RUNS_DIR, RunRecord

SET_ID = "ace2_v1"
ACE2_CSV = Path(__file__).resolve().parent / "datasets" / "ace2_candidates_v1.csv"

# box-fix pass (CHANGELOG Pass 3, Task 2) sanity docks -- same config as this run
BOXFIX_SANITY = {
    "CHEMBL429844": ("MLN-4760 / ORE-1001", -6.00, 0.36),
    "REF_lisinopril": ("lisinopril", -5.80, 0.25),
    "REF_captopril": ("captopril", -4.39, 0.02),
    "REF_ethanol": ("ethanol", -2.65, 0.00),
}


# ---------------------------------------------------------------------------
# features (LOCAL prescreen input) -- mirrors funnel.features._one exactly
# ---------------------------------------------------------------------------
def build_features(cs) -> dict:
    from funnel.fabric import call_local, descriptors_fabric, predict_all_fabric

    async def _one(smiles: str) -> dict:
        desc = await descriptors_fabric(smiles)
        preds = await predict_all_fabric(smiles)
        mol = await call_local("parse_smiles", smiles)
        return {
            "descriptors": {k: round(v, 4) for k, v in desc.items()},
            "predictions": {k: round(v, 5) for k, v in preds.items()},
            "heavy_atoms": int(mol.GetNumHeavyAtoms()),
        }

    async def _all() -> dict:
        out = {}
        for i, c in enumerate(cs.candidates, 1):
            out[c.ligand_id] = await _one(c.smiles)
            print(f"  features [{i:2}/{len(cs)}] {c.ligand_id}", flush=True)
        return out

    feats = asyncio.run(_all())
    return {"set_id": cs.set_id, "candidate_set_sha256": cs.content_sha256,
            "n": len(cs), "features": feats}


def load_or_build_features(cs) -> dict:
    p = RUNS_DIR / f"features_{SET_ID}.json"
    if p.exists():
        d = json.loads(p.read_text())
        if d.get("candidate_set_sha256") == cs.content_sha256 and len(d.get("features", {})) == len(cs):
            print(f"features: reusing {p.name}")
            return d
    print(f"features: building {p.name} via the compute fabric (LOCAL only) ...")
    d = build_features(cs)
    p.write_text(json.dumps(d, indent=2))
    print(f"features: wrote {p}")
    return d


# ---------------------------------------------------------------------------
def recall(target: list[str], docked: set[str], ties: dict, credited: bool) -> int:
    if credited:
        return sum(1 for m in target if m in docked or (ties.get(m, set()) & docked))
    return sum(1 for m in target if m in docked)


def first_n(rows, key, level):
    r = next((x for x in rows if x[key] >= level), None)
    return r["N"] if r else None


def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    cs = load_candidate_set(csv_path=ACE2_CSV, set_id=SET_ID)
    assert cs.content_sha256 == baseline.notes[0].split("=")[1], "candidate-set sha mismatch vs baseline"
    feats_doc = load_or_build_features(cs)
    feats = feats_doc["features"]
    cand_ids = [c.ligand_id for c in cs.candidates]
    names = {c.ligand_id: (c.name or "") for c in cs.candidates}
    is_ref = {c.ligand_id: c.is_reference for c in cs.candidates}

    entries = {e.ligand_id: e for e in baseline.results}
    by_rank = sorted(baseline.results, key=lambda e: e.rank)
    b_rank = {e.ligand_id: e.rank for e in baseline.results}
    failed = [e.ligand_id for e in baseline.results if e.mean_affinity is None]
    docked_ok = [e.ligand_id for e in baseline.results if e.mean_affinity is not None]
    b_top5 = [e.ligand_id for e in by_rank if e.rank <= 5]
    b_top10 = [e.ligand_id for e in by_rank if e.rank <= 10]
    ties = _tie_partners(baseline)
    wall = {e.ligand_id: (e.dock_wall_s or 0.0) for e in baseline.results}
    full_wall = baseline.total_docking_wall_s

    # ======================= TASK 3 -- run sanity =======================
    print("\n" + "=" * 78)
    print("TASK 3 -- RUN SANITY")
    print("=" * 78)
    print(f"candidates: {baseline.candidate_set_size}   jobs: {baseline.total_docking_jobs_submitted}   "
          f"dock wall: {full_wall:.0f}s ({full_wall/3600:.1f} h)   vina: {baseline.vina_version}")
    print(f"completed: {len(docked_ok)}/45   failed: {len(failed)}/45")
    if failed:
        print("  failed (all 6 -- Vina cannot parameterise boron; PDBQT parse error 'Atom type B'):")
        for l in failed:
            print(f"    {l:<15} {names.get(l,''):<12} {entries[l].smiles}")

    print("\nreference ligands vs box-fix (Pass 3 Task 2) sanity docks -- same config:")
    print(f"  {'ligand':<26} {'this run':>9} {'box-fix':>9} {'delta':>7} {'sd(now)':>8}")
    ref_now = []
    for lid, (label, bf_mean, bf_sd) in BOXFIX_SANITY.items():
        e = entries.get(lid)
        if e is None or e.mean_affinity is None:
            print(f"  {label:<26} {'MISSING':>9}")
            continue
        ref_now.append((label, e.mean_affinity))
        print(f"  {label:<26} {e.mean_affinity:>+9.3f} {bf_mean:>+9.2f} {e.mean_affinity-bf_mean:>+7.2f} {e.seed_stdev:>8.3f}")
    order_now = [l for l, _ in sorted(ref_now, key=lambda t: t[1])]
    order_exp = ["MLN-4760 / ORE-1001", "lisinopril", "captopril", "ethanol"]
    print(f"  potency order now : {order_now}")
    print(f"  expected order    : {order_exp}")
    print(f"  ORDER MATCHES: {order_now == order_exp}")

    sd_ace2 = [e.seed_stdev for e in baseline.results if e.seed_stdev is not None]
    cox2 = RunRecord.load(RUNS_DIR / "baseline_cox2_v1.json")
    sd_cox2 = [e.seed_stdev for e in cox2.results if e.seed_stdev is not None]
    print("\nper-candidate seed stdev (kcal/mol):")
    for label, arr in (("cox2_v1", sd_cox2), ("ace2_v1", sd_ace2)):
        arr = sorted(arr)
        print(f"  {label}: n={len(arr)}  median={statistics.median(arr):.3f}  mean={statistics.mean(arr):.3f}  "
              f"p90={arr[int(0.9*len(arr))]:.3f}  max={max(arr):.3f}  "
              f"frac > TIE_EPSILON({TIE_EPSILON}): {sum(1 for x in arr if x > TIE_EPSILON)}/{len(arr)}")
    pooled_ace2 = statistics.median(sd_ace2)
    print(f"  TIE_EPSILON = {TIE_EPSILON}; ace2 median seed sd = {pooled_ace2:.3f}  "
          f"-> tie-epsilon still {'ABOVE' if TIE_EPSILON > pooled_ace2 else 'BELOW'} the ace2 seed-noise floor")

    # ======================= TASK 1 -- held-out eval =======================
    print("\n" + "=" * 78)
    print("TASK 1 -- HELD-OUT EVALUATION (frozen v7 policy, one pass, no tuning)")
    print("=" * 78)
    order = prescreen_order(DEFAULT_POLICY, feats_doc, cand_ids)   # v7, hard-filter survivors
    survivors = set(order)
    dropped = [l for l in cand_ids if l not in survivors]
    fn5 = [l for l in b_top5 if l in set(dropped)]
    fn10 = [l for l in b_top10 if l in set(dropped)]
    print(f"v7 hard-filter survivors: {len(order)}/45   dropped: {dropped}")
    print(f"false negatives (baseline top-k the FILTER dropped): top5={fn5 or 0}  top10={fn10 or 0}")
    # note undockable-in-prescreen: boronic acids that survive the filter still occupy prescreen slots
    boron_in_order = [l for l in order if l in set(failed)]
    print(f"un-dockable candidates that pass the v7 filter (occupy prescreen slots, can never be a hit): "
          f"{boron_in_order}  (prescreen ranks {[order.index(l)+1 for l in boron_in_order]})")

    rows = []
    for n in range(1, len(cand_ids) + 1):
        d = set(order[:n])
        est = sum(wall[l] for l in d)
        rows.append({
            "N": n, "docked": len(d),
            "r5l": recall(b_top5, d, ties, False), "r5t": recall(b_top5, d, ties, True),
            "r10l": recall(b_top10, d, ties, False), "r10t": recall(b_top10, d, ties, True),
            "est_wall_s": round(est, 1),
            "speedup": round(full_wall / est, 1) if est else None,
        })

    # picks at the primary and secondary cut
    def picks_at(n):
        return [(l, b_rank[l]) for l in order[:n]]
    mean_rank_10 = statistics.mean(b_rank[l] for l in order[:10])
    mean_rank_5 = statistics.mean(b_rank[l] for l in order[:5])

    print(f"\nv7 prescreen top-10 (ligand, baseline rank): {picks_at(10)}")
    print(f"  mean baseline rank of top-5 picks : {mean_rank_5:.1f}")
    print(f"  mean baseline rank of top-10 picks: {mean_rank_10:.1f}")

    # cox2 frontier for side-by-side
    cox2_fr = {int(r["N"]): r for r in csv.DictReader((RUNS_DIR / "frontier_cox2_v1.csv").open())}

    print("\n--- recall vs N: ACE2 (held-out) | cox2 (reference) ---")
    print(f"{'N':>3} | {'ace2 r@10 l/t':>13} {'ace2 r@5 l/t':>12} {'ace2 spd':>8} | "
          f"{'cox2 r@10 l/t':>13} {'cox2 r@5 l/t':>12}")
    print("-" * 78)
    for n in range(1, 46):
        a = rows[n - 1]
        c = cox2_fr.get(n, {})
        show = (n <= 12 or n % 5 == 0 or n in (10, len(order), 45)
                or (n > 1 and (rows[n-2]["r10l"] != a["r10l"] or rows[n-2]["r5l"] != a["r5l"])))
        if not show:
            continue
        cx = (f"{int(c['recall10_literal']):>3}/{int(c['recall10_tiecredit']):<3}"
              f"{'':4}{int(c['recall5_literal']):>3}/{int(c['recall5_tiecredit']):<3}") if c else "n/a"
        print(f"{n:>3} | {a['r10l']:>5}/{a['r10t']:<5}{'':2} {a['r5l']:>4}/{a['r5t']:<4}{'':2} "
              f"{(str(a['speedup'])+'x'):>8} | {cx}")

    print("\nfirst N to reach each recall level (ACE2 held-out | cox2 reference):")
    cox2_rows = [{"N": int(r["N"]), "r5l": int(r["recall5_literal"]), "r5t": int(r["recall5_tiecredit"]),
                 "r10l": int(r["recall10_literal"]), "r10t": int(r["recall10_tiecredit"])}
                for r in csv.DictReader((RUNS_DIR / "frontier_cox2_v1.csv").open())]
    for key, lbl, mx in (("r10l", "recall@10 literal (PRIMARY)", 10), ("r10t", "recall@10 tie-credited", 10),
                         ("r5l", "recall@5 literal (secondary)", 5), ("r5t", "recall@5 tie-credited", 5)):
        print(f"  {lbl}")
        for k in range(1, mx + 1):
            na = first_n(rows, key, k)
            nc = first_n(cox2_rows, key, k)
            if na is None and nc is None:
                continue
            amark = "" if na else "  (never; max %d/%d)" % (max(r[key] for r in rows), mx)
            print(f"    {k:>2}/{mx}:  ace2 N={str(na):<4}  cox2 N={str(nc):<4}{amark}")

    # ======================= TASK 2 -- concentration =======================
    print("\n" + "=" * 78)
    print("TASK 2 -- IS ace2_v1's BENCHMARK DEGENERATE THE SAME WAY cox2_v1 IS?")
    print("=" * 78)
    # prescreen rank of every baseline-top-10 member under the single frozen policy
    pr_rank = {l: (order.index(l) + 1 if l in survivors else None) for l in b_top10}
    print("baseline top-10 under the frozen v7 prescreen (one policy -- ace2 has no 34-policy grid):")
    print(f"  {'baseline#':>9} {'ligand':<15} {'true aff':>8} {'v7 prescreen rank':>18} {'binding_score':>13} "
          f"{'P(ace2)':>8} {'P(cox2)':>8}")
    for e in by_rank[:10]:
        l = e.ligand_id
        p = feats[l]["predictions"]
        print(f"  {e.rank:>9} {l:<15} {e.mean_affinity:>+8.2f} {str(pr_rank[l]):>18} "
              f"{p['binding_score']:>13.3f} {p['ace2']:>8.3f} {p['cox2']:>8.3f}")

    ranks_present = sorted(v for v in pr_rank.values() if v is not None)
    print(f"\n  prescreen ranks of baseline top-10 survivors: {ranks_present}")
    if len(ranks_present) >= 2:
        gap_last = ranks_present[-1] - ranks_present[-2]
        print(f"  worst prescreen rank among them: {ranks_present[-1]}  "
              f"(gap to 2nd-worst: {gap_last})")
        print(f"  median prescreen rank of the top-10: {statistics.median(ranks_present):.0f} "
              f"(of {len(order)} survivors)  -> {'diffuse (whole prescreen weak)' if statistics.median(ranks_present) > len(order)/3 else 'concentrated (a few laggards)'}")

    # recovery order: as N grows, in what order do baseline top-10 get picked up
    recovery = []
    seen = set()
    for i, l in enumerate(order, 1):
        if l in set(b_top10) and l not in seen:
            seen.add(l)
            recovery.append((i, l, b_rank[l]))
    print(f"\n  recovery order of baseline top-10 as prescreen budget N grows:")
    for n_at, l, br in recovery:
        print(f"    N={n_at:<3} picks up baseline #{br:<2} ({l})")
    if recovery:
        last_two = [r[0] for r in recovery[-2:]]
        print(f"  last two top-10 members recovered at N={last_two}  "
              f"(extra docks for the final one: {recovery[-1][0]-recovery[-2][0]})")

    # ACE2 analogue of CHEMBL2315019: top-5 docker(s) with weak cheap-model signal + deep prescreen rank
    print("\n  ACE2 analogue of CHEMBL2315019 (baseline top-5 docker invisible to the cheap models):")
    for e in by_rank[:5]:
        l = e.ligand_id
        p = feats[l]["predictions"]
        pr = pr_rank[l]
        flag = " <== analogue" if (pr is not None and pr > len(order) / 2) else ""
        print(f"    baseline #{e.rank} {l} aff={e.mean_affinity:+.2f}  prescreen#{pr}  "
              f"binding_score={p['binding_score']:.2f} P(ace2)={p['ace2']:.2f} P(cox2)={p['cox2']:.2f}{flag}")

    # ======================= write artifacts =======================
    out_csv = RUNS_DIR / f"frontier_{SET_ID}_heldout.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out_csv}")

    out_json = RUNS_DIR / f"heldout_{SET_ID}.json"
    out_json.write_text(json.dumps({
        "set_id": SET_ID,
        "baseline": f"runs/baseline_{SET_ID}.json",
        "policy": "v7_binding_weak_cox2 (frozen, unchanged)",
        "completed": len(docked_ok), "failed": failed,
        "failure_reason": "AutoDock Vina PDBQT parse error: 'Atom type B is not a valid AutoDock type' (all 6 are boronic acids)",
        "reference_order_matches_boxfix": order_now == order_exp,
        "reference_affinities_now": dict(ref_now),
        "seed_sd_ace2_median": statistics.median(sd_ace2),
        "seed_sd_cox2_median": statistics.median(sd_cox2),
        "tie_epsilon": TIE_EPSILON,
        "hard_filter_survivors": len(order), "hard_filter_dropped": dropped,
        "false_negatives_top5": fn5, "false_negatives_top10": fn10,
        "undockable_in_prescreen": boron_in_order,
        "frontier": rows,
        "prescreen_rank_of_baseline_top10": pr_rank,
        "recovery_order_top10": [{"N": n, "ligand": l, "baseline_rank": r} for n, l, r in recovery],
        "mean_baseline_rank_top5_picks": mean_rank_5,
        "mean_baseline_rank_top10_picks": mean_rank_10,
        "first_n": {
            "ace2": {k: {str(i): first_n(rows, k, i) for i in range(1, (10 if "10" in k else 5) + 1)}
                     for k in ("r10l", "r10t", "r5l", "r5t")},
        },
    }, indent=2))
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
