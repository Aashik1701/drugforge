"""
Baseline path — dock EVERY candidate, 4 seeds each, rank on mean affinity.
No filtering. The only thing that differs from the funnel path is which
candidates are docked; the docking config and the ranking function are
imported from the same modules the funnel uses.

Run:  cd backend/app && ../venv/bin/python -m funnel.baseline
      (add --limit N for a smoke test)
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import platform
import sys
import time
import uuid
from pathlib import Path

# COMPUTE_MODE must be set before `main` is imported (fabric imports it).
os.environ.setdefault("COMPUTE_MODE", "balanced")

from funnel.candidate_set import load_candidate_set
from funnel.fabric import dock_candidate, local_worker_process
from funnel.ranking import rank_docked
from funnel.schema import SCHEMA_VERSION, DockingParams, RunRecord, StageCount

SEEDS = [1, 42, 2024, 31337]
EXHAUSTIVENESS = 8
CONFORMER_SEED = 42
NUM_MODES = 5
TARGET = "cox2"


async def _run(candidates, dp: DockingParams):
    from utils.vina_env import resolved_vina_version
    vina_version = resolved_vina_version()

    results = []
    dock_wall = 0.0
    jobs = 0
    for idx, c in enumerate(candidates, 1):
        print(f"[baseline {idx}/{len(candidates)}] dock {c.ligand_id} ({c.name[:24]}) "
              f"x{len(SEEDS)} seeds ...", flush=True)
        dr = await dock_candidate(
            c.ligand_id, c.smiles, SEEDS,
            target=TARGET, exhaustiveness=EXHAUSTIVENESS,
            conformer_seed=CONFORMER_SEED, num_modes=NUM_MODES,
        )
        results.append(dr)
        dock_wall += dr.wall_s_total
        jobs += dr.jobs_submitted
        aff = f"{dr.mean_affinity:+.3f}" if dr.mean_affinity is not None else "FAILED"
        print(f"    mean={aff}  sd={dr.seed_stdev}  wall={dr.wall_s_total:.1f}s  "
              f"per_seed={dr.per_seed_map}", flush=True)

    return results, dock_wall, jobs, vina_version


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="dock only the first N candidates")
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    cs = load_candidate_set()
    candidates = cs.candidates[: args.limit] if args.limit else cs.candidates
    dp = DockingParams(exhaustiveness=EXHAUSTIVENESS, seeds=SEEDS, cpu=1,
                       target=TARGET, num_modes=NUM_MODES, conformer_seed=CONFORMER_SEED)

    run_id = uuid.uuid4().hex[:12]
    print(f"baseline run_id={run_id}  set={cs.set_id} ({len(candidates)} candidates, "
          f"sha={cs.content_sha256[:12]})  seeds={SEEDS}", flush=True)

    # Set BEFORE the first get_fabric_async() so parent + LocalWorker agree
    # on the job-store file. (funnel.py has the same requirement.)
    job_db = f"/tmp/funnel_baseline_{run_id}.db"
    os.environ["JOB_STORE_PATH"] = job_db

    t0 = time.perf_counter()
    with local_worker_process({"COMPUTE_MODE": "balanced", "JOB_STORE_PATH": job_db}):
        results, dock_wall, jobs, vina_version = asyncio.run(_run(candidates, dp))
    total_wall = time.perf_counter() - t0

    entries = rank_docked(results)

    rec = RunRecord(
        run_id=run_id,
        path_name="baseline",
        schema_version=SCHEMA_VERSION,
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        platform=platform.platform(),
        vina_version=vina_version,
        docking_params=dp,
        candidate_set_id=cs.set_id,
        candidate_set_size=len(candidates),
        stage_survivors=[
            StageCount("input", len(candidates), len(candidates), "no filtering in baseline"),
            StageCount("dock_all", len(candidates), len(candidates),
                       f"{jobs} docking jobs = {len(candidates)} x {len(SEEDS)} seeds"),
        ],
        total_docking_jobs_submitted=jobs,
        total_docking_wall_s=round(dock_wall, 2),
        total_run_wall_s=round(total_wall, 2),
        results=entries,
        filtered_out=[],
        funnel_policy=None,
        per_candidate=None,
        notes=[
            f"candidate_set_sha256={cs.content_sha256}",
            f"job_store={job_db}",
            "baseline docks the full set; ranking identical to the funnel path "
            "(funnel.ranking.rank_docked).",
        ],
    )
    out = Path(args.out) if args.out else None
    path = rec.save(filename=out.name if out else f"baseline_{cs.set_id}.json",
                    out_dir=out.parent if out else None)
    print(f"\nwrote {path}")
    print(f"docking jobs submitted : {jobs}")
    print(f"docking wall-clock     : {dock_wall:.1f}s")
    print(f"total run wall-clock   : {total_wall:.1f}s")
    n_failed = sum(1 for e in entries if e.mean_affinity is None)
    if n_failed:
        print(f"WARNING: {n_failed} candidates failed to dock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
