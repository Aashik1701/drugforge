"""
Offline policy sweep — score a candidate FunnelPolicy against a cached baseline
RunRecord with NO docking (and no model inference: features are pre-cached by
funnel.features). Fast enough to score dozens of policies per second.

  cd backend/app && ../venv/bin/python -m funnel.sweep            # cox2_v1
  cd backend/app && ../venv/bin/python -m funnel.sweep --set X    # another set

Primary metric: recall@5 — of the baseline's true top 5, how many the policy's
top 5 recovers (a baseline top-5 molecule counts as recovered if it OR a
tie-group partner is selected, so a coin-flip tie is not scored as a miss).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.policy import DEFAULT_POLICY, FunnelPolicy, HardFilters, RankWeights
from funnel.schema import RUNS_DIR, RunRecord

TOP_N = 5


# ---------------------------------------------------------------------------
# baseline helpers
# ---------------------------------------------------------------------------
def _tie_map(baseline: RunRecord) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for e in baseline.results:
        if e.tie_group:
            groups.setdefault(e.tie_group, set()).add(e.ligand_id)
    return {lid: (groups[e.tie_group] - {lid}) if e.tie_group else set()
            for e in baseline.results
            for lid in [e.ligand_id]}


def _top_k(baseline: RunRecord, k: int) -> list[str]:
    return [e.ligand_id for e in baseline.results if e.rank and e.rank <= k]


def _rank_of(baseline: RunRecord) -> dict[str, int]:
    return {e.ligand_id: e.rank for e in baseline.results}


# ---------------------------------------------------------------------------
# scoring one policy
# ---------------------------------------------------------------------------
@dataclass
class SweepResult:
    name: str
    ranker: str
    filter_mode: str
    selected: list[str]                      # policy top-5, in policy order
    selected_baseline_ranks: list[int]
    filtered_out: list[str]
    recall_at_5: float
    recall_at_5_hits: list[str]
    recall_at_10: float
    false_negatives: list[str]
    mean_baseline_rank_selected: float
    n_survivors: int
    notes: str = ""


def score_policy(name: str, policy: FunnelPolicy, baseline: RunRecord,
                 features: dict, candidate_ids: list[str]) -> SweepResult:
    feats = features["features"]
    b_rank = _rank_of(baseline)
    ties = _tie_map(baseline)
    b_top5 = _top_k(baseline, 5)
    b_top10 = _top_k(baseline, 10)

    # --- hard filters (from cached features) ---
    survivors: list[str] = []
    filtered: list[str] = []
    for lid in candidate_ids:
        f = feats[lid]
        ok_d, _ = policy.descriptors_pass(f["descriptors"])
        ok_t, _ = policy.tox_pass(f["predictions"])
        if ok_d and ok_t:
            survivors.append(lid)
        else:
            filtered.append(lid)

    # --- binding_norm over survivors (same as funnel.score_and_select) ---
    bvals = [feats[l]["predictions"]["binding_score"] for l in survivors]
    b_min, b_max = (min(bvals), max(bvals)) if bvals else (0.0, 0.0)
    span = (b_max - b_min) or 1.0

    def bnorm(x: float) -> float:
        frac = (x - b_min) / span
        return (1.0 - frac) if policy.binding_lower_is_better else frac

    scored = []
    for lid in survivors:
        f = feats[lid]
        s = policy.rank_score(f, bnorm(f["predictions"]["binding_score"]))
        scored.append((lid, s))
    scored.sort(key=lambda t: t[1], reverse=True)
    policy_top5 = [lid for lid, _ in scored[:TOP_N]]
    policy_top10 = [lid for lid, _ in scored[:10]]

    # --- recall@k with tie credit ---
    def recall(b_top: list[str], p_top: list[str]) -> tuple[float, list[str]]:
        p = set(p_top)
        hits = [m for m in b_top if m in p or (ties.get(m, set()) & p)]
        return (len(hits) / len(b_top) if b_top else 0.0), hits

    r5, r5_hits = recall(b_top5, policy_top5)
    r10, _ = recall(b_top10, policy_top10)

    fn = [m for m in b_top5 if m in set(filtered)]
    sel_ranks = [b_rank[l] for l in policy_top5]
    mean_rank = sum(sel_ranks) / len(sel_ranks) if sel_ranks else float("nan")

    return SweepResult(
        name=name, ranker=policy.ranker, filter_mode=policy.filter_mode,
        selected=policy_top5, selected_baseline_ranks=sel_ranks,
        filtered_out=filtered,
        recall_at_5=r5, recall_at_5_hits=r5_hits, recall_at_10=r10,
        false_negatives=fn, mean_baseline_rank_selected=round(mean_rank, 1),
        n_survivors=len(survivors),
    )


# ---------------------------------------------------------------------------
# the declared variants (hypotheses are in funnel/CHANGELOG.md, written first)
# ---------------------------------------------------------------------------
def variants() -> dict[str, FunnelPolicy]:
    # v1 is pinned to the ORIGINAL multi-objective ranker so this table stays
    # reproducible after DEFAULT_POLICY was moved to v7 (binding_weak_cox2).
    return {
        "v1_original": FunnelPolicy(ranker="v1_multiobjective"),
        "v2_binding_only": FunnelPolicy(ranker="binding_only"),
        "v3_binding_only_tox_filter": FunnelPolicy(ranker="binding_only", filter_mode="tox_only"),
        "v4_descriptor_heuristic": FunnelPolicy(ranker="descriptor_heuristic"),
        "v5_binding_desc_blend": FunnelPolicy(ranker="binding_desc_blend"),
        "v6_ligand_efficiency": FunnelPolicy(ranker="ligand_efficiency"),
        "v7_binding_weak_cox2": FunnelPolicy(ranker="binding_weak_cox2"),
        "v8_binding_only_no_filter": FunnelPolicy(ranker="binding_only", filter_mode="none"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="cox2_v1")
    ap.add_argument("--baseline", default=None)
    args = ap.parse_args()

    set_id = args.set
    baseline_path = Path(args.baseline) if args.baseline else RUNS_DIR / f"baseline_{set_id}.json"
    baseline = RunRecord.load(baseline_path)
    features = load_features(set_id)
    cs = load_candidate_set() if set_id == "cox2_v1" else None
    cand_ids = ([c.ligand_id for c in cs.candidates] if cs
                else list(features["features"].keys()))

    assert features["candidate_set_sha256"] == (cs.content_sha256 if cs else features["candidate_set_sha256"])

    b_top5 = _top_k(baseline, 5)
    print(f"baseline = {baseline_path.name}  ({baseline.candidate_set_size} candidates)")
    print(f"baseline true top-5: {b_top5}")
    print(f"  tie groups: " + ", ".join(
        f"{e.ligand_id}={e.tie_group}" for e in baseline.results if e.rank and e.rank <= 6 and e.tie_group))
    print()

    rows = []
    for name, pol in variants().items():
        rows.append(score_policy(name, pol, baseline, features, cand_ids))

    print(f"{'variant':<28} {'ranker':<22} {'filter':<16} {'surv':>4} "
          f"{'rec@5':>6} {'rec@10':>7} {'FN':>3} {'meanRk':>7}")
    print("-" * 100)
    for r in rows:
        print(f"{r.name:<28} {r.ranker:<22} {r.filter_mode:<16} {r.n_survivors:>4} "
              f"{r.recall_at_5*5:>4.0f}/5 {r.recall_at_10*10:>5.0f}/10 {len(r.false_negatives):>3} "
              f"{r.mean_baseline_rank_selected:>7}")

    print("\n--- per-variant detail (policy top-5 -> baseline rank) ---")
    for r in rows:
        pairs = ", ".join(f"{l}#{rk}" for l, rk in zip(r.selected, r.selected_baseline_ranks))
        fn = f"  FALSE-NEG: {r.false_negatives}" if r.false_negatives else ""
        print(f"  {r.name:<28} recall@5={r.recall_at_5*5:.0f}/5 hits={r.recall_at_5_hits}")
        print(f"  {'':<28} picks: {pairs}{fn}")

    best = max(rows, key=lambda r: (r.recall_at_5, -r.mean_baseline_rank_selected))
    print(f"\nbest on recall@5: {best.name}  ({best.recall_at_5*5:.0f}/5, "
          f"mean baseline rank {best.mean_baseline_rank_selected})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
