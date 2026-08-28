"""
Funnel path (advanced) — cheap LOCAL screening narrows the set, then ONLY the
top-N get the expensive HEAVY_LOCAL dock.

  candidates
    -> parse_smiles          (LOCAL)      # drop invalid
    -> calculate_descriptors (LOCAL)      # drug-likeness hard filter
    -> 9 ADMET + binding     (LOCAL)      # toxicity hard filter
    -> multi-objective rank_score         # FunnelPolicy.rank_score
    -> top-N (N = policy.top_n)
    -> dock top-N            (HEAVY_LOCAL, 4 seeds each)
    -> rank_docked  (SAME function the baseline uses)

Every tool call goes through funnel.fabric -> tool_registry.get() ->
compute_router.execute(). Every threshold / weight comes from
funnel.policy.FunnelPolicy (the seam). This module has no magic numbers.

Run:  cd backend/app && ../venv/bin/python -m funnel.funnel
      --dry-run  runs the LOCAL stages only (no docking) and prints the table
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import platform
import time
import uuid
from pathlib import Path

os.environ.setdefault("COMPUTE_MODE", "balanced")

from funnel.candidate_set import load_candidate_set
from funnel.fabric import (
    call_local, dock_candidate, descriptors_fabric, local_worker_process,
    predict_all_fabric, validate_smiles_fabric,
)
from funnel.policy import DEFAULT_POLICY, FunnelPolicy
from funnel.ranking import rank_docked
from funnel.schema import (
    SCHEMA_VERSION, DockingParams, FilteredOut, RunRecord, StageCount,
)

SEEDS = [1, 42, 2024, 31337]
EXHAUSTIVENESS = 8
CONFORMER_SEED = 42
NUM_MODES = 5
TARGET = "cox2"


async def screen(candidates, policy: FunnelPolicy):
    """Run the LOCAL stages. Returns (survivors, filtered_out, per_candidate, stages)."""
    filtered: list[FilteredOut] = []
    per_candidate: dict[str, dict] = {}

    # --- Stage: SMILES validation ---
    valid = []
    for c in candidates:
        ok = await validate_smiles_fabric(c.smiles)
        per_candidate[c.ligand_id] = {"smiles": c.smiles, "name": c.name, "docked": False}
        if ok:
            valid.append(c)
        else:
            filtered.append(FilteredOut(c.ligand_id, c.smiles, "smiles_validation", "RDKit parse failed"))
    stage_valid = StageCount("smiles_validation", len(candidates), len(valid))

    # --- Stage: descriptors + drug-likeness hard filter ---
    passed_desc = []
    for c in valid:
        desc = await descriptors_fabric(c.smiles)
        per_candidate[c.ligand_id]["descriptors"] = {k: round(v, 3) for k, v in desc.items()}
        ok, reason = policy.descriptors_pass(desc)
        if ok:
            passed_desc.append(c)
        else:
            filtered.append(FilteredOut(c.ligand_id, c.smiles, "druglikeness", reason))
            per_candidate[c.ligand_id]["drop_reason"] = f"druglikeness: {reason}"
    stage_desc = StageCount("druglikeness_filter", len(valid), len(passed_desc))

    # --- Stage: 9 ADMET + binding predictions + toxicity hard filter ---
    passed_tox = []
    for c in passed_desc:
        preds = await predict_all_fabric(c.smiles)
        per_candidate[c.ligand_id]["predictions"] = {k: round(v, 4) for k, v in preds.items()}
        mol = await call_local("parse_smiles", c.smiles)
        feat = {
            "predictions": preds,
            "descriptors": per_candidate[c.ligand_id]["descriptors"],
            "heavy_atoms": int(mol.GetNumHeavyAtoms()),
        }
        ok, reason = policy.tox_pass(preds)
        if ok:
            passed_tox.append((c, feat))
        else:
            filtered.append(FilteredOut(c.ligand_id, c.smiles, "toxicity", reason))
            per_candidate[c.ligand_id]["drop_reason"] = f"toxicity: {reason}"
    stage_tox = StageCount("toxicity_filter", len(passed_desc), len(passed_tox))

    stages = [stage_valid, stage_desc, stage_tox]
    return passed_tox, filtered, per_candidate, stages


def score_and_select(passed_tox, policy: FunnelPolicy, per_candidate: dict):
    """Rank over survivors via policy.rank_score; return (ranked_list, top_n, meta).

    `passed_tox` items are (candidate, feat) with feat = {predictions, descriptors,
    heavy_atoms}. `scored` items are (candidate, feat, score)."""
    binding_vals = [f["predictions"]["binding_score"] for _, f in passed_tox]
    if binding_vals:
        b_min, b_max = min(binding_vals), max(binding_vals)
    else:
        b_min = b_max = 0.0
    span = (b_max - b_min) or 1.0

    def bnorm(x: float) -> float:
        frac = (x - b_min) / span
        return (1.0 - frac) if policy.binding_lower_is_better else frac

    scored = []
    for c, feat in passed_tox:
        bn = bnorm(feat["predictions"]["binding_score"])
        s = policy.rank_score(feat, bn)
        per_candidate[c.ligand_id]["binding_norm"] = round(bn, 4)
        per_candidate[c.ligand_id]["rank_score"] = round(s, 4)
        scored.append((c, feat, s))
    scored.sort(key=lambda t: t[2], reverse=True)  # higher score = better
    for i, (c, _, _) in enumerate(scored, 1):
        per_candidate[c.ligand_id]["prescreen_rank"] = i
    top = scored[: policy.top_n]
    for c, _, _ in top:
        per_candidate[c.ligand_id]["selected_for_docking"] = True
    meta = {"binding_min": b_min, "binding_max": b_max,
            "binding_lower_is_better": policy.binding_lower_is_better,
            "ranker": policy.ranker, "filter_mode": policy.filter_mode}
    return scored, top, meta


async def dock_top(top, per_candidate: dict):
    results = []
    dock_wall = 0.0
    jobs = 0
    for idx, (c, _preds, _s) in enumerate(top, 1):
        print(f"[funnel dock {idx}/{len(top)}] {c.ligand_id} ({c.name[:24]}) x{len(SEEDS)} ...", flush=True)
        dr = await dock_candidate(
            c.ligand_id, c.smiles, SEEDS,
            target=TARGET, exhaustiveness=EXHAUSTIVENESS,
            conformer_seed=CONFORMER_SEED, num_modes=NUM_MODES,
        )
        results.append(dr)
        per_candidate[c.ligand_id]["docked"] = True
        dock_wall += dr.wall_s_total
        jobs += dr.jobs_submitted
        aff = f"{dr.mean_affinity:+.3f}" if dr.mean_affinity is not None else "FAILED"
        print(f"    mean={aff}  sd={dr.seed_stdev}  wall={dr.wall_s_total:.1f}s", flush=True)
    return results, dock_wall, jobs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="LOCAL stages only, no docking")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    policy = DEFAULT_POLICY
    cs = load_candidate_set()
    run_id = uuid.uuid4().hex[:12]
    dp = DockingParams(exhaustiveness=EXHAUSTIVENESS, seeds=SEEDS, cpu=1,
                       target=TARGET, num_modes=NUM_MODES, conformer_seed=CONFORMER_SEED)

    print(f"funnel run_id={run_id}  set={cs.set_id} ({len(cs)} candidates, "
          f"sha={cs.content_sha256[:12]})  top_n={policy.top_n}", flush=True)

    # Per-run private job store. MUST be set before the first get_fabric_async()
    # (which builds main.job_store from this env var) so the parent and the
    # LocalWorker subprocess agree on which SQLite file the docking jobs live in.
    job_db = f"/tmp/funnel_{run_id}.db"
    os.environ["JOB_STORE_PATH"] = job_db

    from utils.vina_env import resolved_vina_version

    t0 = time.perf_counter()

    async def _local_phase():
        passed_tox, filtered, per_candidate, stages = await screen(cs.candidates, policy)
        scored, top, bmeta = score_and_select(passed_tox, policy, per_candidate)
        return passed_tox, filtered, per_candidate, stages, scored, top, bmeta

    passed_tox, filtered, per_candidate, stages, scored, top, bmeta = asyncio.run(_local_phase())

    print("\n--- prescreen ranking (survivors, by rank_score desc) ---", flush=True)
    for c, feat, s in scored:
        preds = feat["predictions"]
        mark = "  <== dock" if any(cc.ligand_id == c.ligand_id for cc, _, _ in top) else ""
        print(f"  score={s:+.3f}  cox2={preds['cox2']:.2f} bind={preds['binding_score']:+.2f} "
              f"tox={preds['toxicity']:.2f} sol={preds['solubility']:+.2f}  {c.ligand_id} "
              f"{c.name[:20]}{mark}", flush=True)

    vina_version = resolved_vina_version()

    if args.dry_run:
        total_wall = time.perf_counter() - t0
        print(f"\n[dry-run] {len(passed_tox)} survivors, would dock top-{policy.top_n}: "
              f"{[c.ligand_id for c, _, _ in top]}")
        print(f"[dry-run] binding_norm meta: {bmeta}")
        print(f"[dry-run] local phase wall: {total_wall:.1f}s")
        return 0

    with local_worker_process({"COMPUTE_MODE": "balanced", "JOB_STORE_PATH": job_db}):
        os.environ["JOB_STORE_PATH"] = job_db
        results, dock_wall, jobs = asyncio.run(dock_top(top, per_candidate))
    total_wall = time.perf_counter() - t0

    entries = rank_docked(results)
    stages.append(StageCount("dock_top_n", len(passed_tox), len(top),
                             f"{jobs} jobs = {len(top)} x {len(SEEDS)} seeds"))

    rec = RunRecord(
        run_id=run_id, path_name="funnel", schema_version=SCHEMA_VERSION,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        platform=platform.platform(), vina_version=vina_version,
        docking_params=dp, candidate_set_id=cs.set_id, candidate_set_size=len(cs),
        stage_survivors=stages,
        total_docking_jobs_submitted=jobs,
        total_docking_wall_s=round(dock_wall, 2),
        total_run_wall_s=round(total_wall, 2),
        results=entries,
        filtered_out=filtered,
        funnel_policy=policy.as_dict(),
        per_candidate=per_candidate,
        notes=[
            f"candidate_set_sha256={cs.content_sha256}",
            f"job_store={job_db}",
            f"binding_norm: min={bmeta['binding_min']:.4f} max={bmeta['binding_max']:.4f} "
            f"lower_is_better={bmeta['binding_lower_is_better']} "
            "(min-max feature scaling over survivors, not threshold tuning)",
            "ranking identical to baseline (funnel.ranking.rank_docked); "
            "only the docked subset differs.",
        ],
    )
    out = Path(args.out) if args.out else None
    path = rec.save(filename=out.name if out else f"funnel_{cs.set_id}.json",
                    out_dir=out.parent if out else None)
    print(f"\nwrote {path}")
    print(f"docking jobs submitted : {jobs}")
    print(f"docking wall-clock     : {dock_wall:.1f}s")
    print(f"total run wall-clock   : {total_wall:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
