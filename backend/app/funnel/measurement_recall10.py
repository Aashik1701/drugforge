"""
funnel.measurement_recall10 -- fixes the MEASUREMENT, not the policy.

Pass 7 found that 18/34 policies (53%) have their literal recall@5 = 5/5
milestone land on the exact N at which one molecule (CHEMBL2315019) enters the
docked set -- the metric is, to a first approximation, a one-molecule detection
test. This pass asks: is recall@10 less degenerate, or is cox2_v1 degenerate at
every k?

No new docking. No new policy, surrogate, or seed-selection variant. Every
per-molecule docking ORDER used below is recomputed from the exact same frozen,
deterministic functions already executed in Passes 3, 5, 6, and 7
(`funnel.frontier.prescreen_order`, `funnel.two_phase.seed_batch_for_S` +
`fit_phase2`/`phase2_order` with Pass 5's unchanged rf config, and the four
`funnel.seed_diversity` strategies) -- purely to recover which specific target
molecule arrives last, a detail the committed aggregate CSVs (recall counts per
N) don't carry on their own. Every recomputed recall value is asserted equal to
the already-published figure from the corresponding committed artifact, as an
integrity check that this is a re-read of existing results, not a re-run of new
ones.

  cd backend/app && ../venv/bin/python -m funnel.measurement_recall10
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.frontier import _tie_partners, prescreen_order
from funnel.policy import DEFAULT_POLICY, DESCRIPTOR_NAMES
from funnel.schema import RUNS_DIR, RunRecord
from funnel.seed_diversity import STRATEGIES as SEED_STRATEGIES
from funnel.surrogate import morgan_bits
from funnel.two_phase import S_VALUES, SURVIVOR_CAP, fit_phase2, phase2_order, seed_batch_for_S

SET_ID = "cox2_v1"


def literal_recall_curve(order: list[str], target: set[str]) -> list[int]:
    """order[i-1] is the i-th molecule docked. Returns recall@|target| at each N=1..len(order)."""
    seen = 0
    out = []
    for l in order:
        if l in target:
            seen += 1
        out.append(seen)
    return out


def first_n_complete(curve: list[int], k: int) -> int | None:
    for i, v in enumerate(curve, 1):
        if v >= k:
            return i
    return None


def straggler(order: list[str], target: set[str]) -> str:
    """The target member with the highest position (last to be docked)."""
    pos = {l: i for i, l in enumerate(order)}
    return max(target, key=lambda l: pos.get(l, -1))


def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    features = load_features(SET_ID)
    feats = features["features"]
    cs = load_candidate_set()
    cand_ids = [c.ligand_id for c in cs.candidates]

    true_affinity = {e.ligand_id: e.mean_affinity for e in baseline.results}
    b_top5 = {e.ligand_id for e in baseline.results if e.rank and e.rank <= 5}
    b_top10 = {e.ligand_id for e in baseline.results if e.rank and e.rank <= 10}

    v7_order = prescreen_order(DEFAULT_POLICY, features, cand_ids)
    assert len(v7_order) == SURVIVOR_CAP

    smiles_by_id = {c.ligand_id: c.smiles for c in cs.candidates}
    x_by_id: dict[str, np.ndarray] = {}
    for l in v7_order:
        fp = morgan_bits(smiles_by_id[l])
        desc = np.array([feats[l]["descriptors"][k] for k in DESCRIPTOR_NAMES], dtype=float)
        x_by_id[l] = np.concatenate([fp, desc])
    ctx = {"v7_order": v7_order, "v7_scores": None, "x_by_id": x_by_id, "survivors_sorted": sorted(v7_order)}

    policies: dict[str, list[str]] = {}

    # ---- v7 ----
    policies["v7"] = v7_order

    # ---- Pass 5: surrogate variants, cross-checked against surrogate_cox2_v1.json ----
    surr = json.loads((RUNS_DIR / f"surrogate_{SET_ID}.json").read_text())
    for kind, v in surr["variants"].items():
        order = v["order_41survivors"]
        policies[f"P5_surrogate_{kind}"] = order
        stored = {r["N"]: r for r in v["frontier_41survivors"]}
        curve5 = literal_recall_curve(order, b_top5)
        curve10 = literal_recall_curve(order, b_top10)
        for n in (5, 10, 20, 41):
            assert curve5[n - 1] == stored[n]["r5l"], f"P5 {kind} N={n} r5 mismatch"
            assert curve10[n - 1] == stored[n]["r10l"], f"P5 {kind} N={n} r10 mismatch"

    # ---- Pass 6: two-phase control, cross-checked against two_phase_cox2_v1.json/.csv ----
    tp = json.loads((RUNS_DIR / f"two_phase_{SET_ID}.json").read_text())
    tp_grid_by_sn = {(r["S"], r["N"]): r for r in tp["grid"]}
    for S in S_VALUES:
        seed_ids = seed_batch_for_S(v7_order, S)
        remaining = [l for l in v7_order if l not in set(seed_ids)]
        order2, _ = phase2_order(seed_ids, remaining, true_affinity, x_by_id)
        full_order = seed_ids + order2
        policies[f"P6_two_phase_S{S}"] = full_order
        curve5 = literal_recall_curve(full_order, b_top5)
        curve10 = literal_recall_curve(full_order, b_top10)
        for n in (S, S + 5, SURVIVOR_CAP):
            if n > SURVIVOR_CAP:
                continue
            row = tp_grid_by_sn[(S, n)]
            assert curve5[n - 1] == row["r5_lit"], f"P6 S={S} N={n} r5 mismatch"
            assert curve10[n - 1] == row["r10_lit"], f"P6 S={S} N={n} r10 mismatch"

    # ---- Pass 7: seed-diversity strategies, cross-checked against seed_diversity_cox2_v1.json ----
    sd = json.loads((RUNS_DIR / f"seed_diversity_{SET_ID}.json").read_text())
    sd_grid_by_ssn = {(r["strategy"], r["S"], r["N"]): r for r in sd["grid"]}
    for sname, sfn in SEED_STRATEGIES.items():
        for S in S_VALUES:
            seed_ids = sfn(ctx, S)
            remaining = [l for l in v7_order if l not in set(seed_ids)]
            order2, _ = phase2_order(seed_ids, remaining, true_affinity, x_by_id)
            full_order = seed_ids + order2
            policies[f"P7_{sname}_S{S}"] = full_order
            curve5 = literal_recall_curve(full_order, b_top5)
            curve10 = literal_recall_curve(full_order, b_top10)
            for n in (S, SURVIVOR_CAP):
                row = sd_grid_by_ssn[(sname, S, n)]
                assert curve5[n - 1] == row["r5_lit"], f"P7 {sname} S={S} N={n} r5 mismatch"
                assert curve10[n - 1] == row["r10_lit"], f"P7 {sname} S={S} N={n} r10 mismatch"

    print(f"integrity check passed: all {len(policies)} recomputed orders reproduce their "
          f"already-published recall@5 and recall@10 figures exactly.\n")

    # ---- per-policy: first N to complete, straggler identity, at k=5 and k=10 ----
    rows = []
    for label, order in policies.items():
        c5 = literal_recall_curve(order, b_top5)
        c10 = literal_recall_curve(order, b_top10)
        n5 = first_n_complete(c5, 5)
        n10 = first_n_complete(c10, 10)
        s5 = straggler(order, b_top5) if n5 else None
        s10 = straggler(order, b_top10) if n10 else None
        n9of10 = first_n_complete(c10, 9)
        gap10 = (n10 - n9of10) if (n10 is not None and n9of10 is not None) else None
        rows.append({
            "policy": label, "N_at_5of5": n5, "straggler5": s5,
            "N_at_10of10": n10, "straggler10": s10, "gap_9to10": gap10,
        })

    coincide5 = sum(1 for r in rows if r["N_at_5of5"] is not None and r["straggler5"] == "CHEMBL2315019")
    dom5 = Counter(r["straggler5"] for r in rows if r["straggler5"]).most_common(1)
    print(f"recall@5:  dominant straggler = {dom5[0][0]} in {dom5[0][1]}/{len(rows)} "
          f"({100*dom5[0][1]/len(rows):.0f}%)  [Pass 7 published: 18/34, 53%]")

    dom10 = Counter(r["straggler10"] for r in rows if r["straggler10"])
    top10_common = dom10.most_common(3)
    n_determined10 = sum(1 for r in rows if r["straggler10"])
    print(f"recall@10: straggler distribution (top 3 of {len(dom10)} distinct molecules): {top10_common}")
    print(f"recall@10: dominant straggler = {top10_common[0][0]} in {top10_common[0][1]}/{n_determined10} "
          f"({100*top10_common[0][1]/n_determined10:.0f}%)")

    gaps = [r["gap_9to10"] for r in rows if r["gap_9to10"] is not None]
    gaps_sorted = sorted(gaps)
    print(f"\ngap (N_at_10/10 - N_at_9/10) distribution, n={len(gaps)}: "
          f"min={min(gaps)} p25={gaps_sorted[len(gaps)//4]} median={gaps_sorted[len(gaps)//2]} "
          f"p75={gaps_sorted[3*len(gaps)//4]} max={max(gaps)}")

    n5_vals = [r["N_at_5of5"] for r in rows if r["N_at_5of5"] is not None]
    n10_vals = [r["N_at_10of10"] for r in rows if r["N_at_10of10"] is not None]
    print(f"\nspread of completion N -- recall@5: min={min(n5_vals)} max={max(n5_vals)} "
          f"std={np.std(n5_vals):.1f}  |  recall@10: min={min(n10_vals)} max={max(n10_vals)} "
          f"std={np.std(n10_vals):.1f}")

    out_csv = RUNS_DIR / f"measurement_recall10_{SET_ID}.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out_csv}")

    out_json = RUNS_DIR / f"measurement_recall10_{SET_ID}.json"
    out_json.write_text(json.dumps({
        "set_id": SET_ID,
        "n_policies": len(rows),
        "recall5_dominant_straggler": dom5[0],
        "recall5_coincidence_rate": coincide5 / len(rows),
        "recall10_straggler_distribution": dict(dom10),
        "recall10_dominant_straggler": top10_common[0],
        "recall10_coincidence_rate": top10_common[0][1] / n_determined10,
        "gap_9to10_distribution": gaps,
        "n5_spread": {"min": min(n5_vals), "max": max(n5_vals), "std": float(np.std(n5_vals))},
        "n10_spread": {"min": min(n10_vals), "max": max(n10_vals), "std": float(np.std(n10_vals))},
        "rows": rows,
    }, indent=2))
    print(f"wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
