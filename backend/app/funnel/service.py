"""
funnel.service -- the computational funnel behind HTTP.

Moves existing behaviour (funnel.funnel's screen -> score_and_select -> serial
dock -> rank_docked -> RunRecord) into an in-process asyncio task, driven by a
parent Job of type "funnel" in the shared JobStore. Every dock is a child Job of
type "docking" created through ComputeRouter exactly as /api/dock/start does, so
MAX_DOCKING_CONCURRENT is respected globally. See docs/development/funnel-service.md.

Nothing here changes the frozen v7 policy, the docking params, or the funnel's
scientific logic -- screen() and score_and_select() are imported unchanged from
funnel.funnel; rank_docked from funnel.ranking; RunRecord from funnel.schema.
ComputeRouter / ResourceManager / JobStore / the tool-registry contract are not
modified.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import hashlib
import logging
import os
import platform
import signal
import time
from pathlib import Path

from rdkit import Chem, RDLogger

from funnel.candidate_set import Candidate, CandidateSet, load_candidate_set
from funnel.fabric import DockResult, SeedDock
from funnel.funnel import (
    CONFORMER_SEED, EXHAUSTIVENESS, NUM_MODES, SEEDS,
    score_and_select, screen,
)
from funnel.policy import DEFAULT_POLICY
from funnel.ranking import rank_docked
from funnel.schema import SCHEMA_VERSION, DockingParams, RunRecord, StageCount

RDLogger.DisableLog("rdApp.*")
logger = logging.getLogger("funnel.service")

DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
RUNS_DIR = Path(__file__).resolve().parents[3] / "runs"

FROZEN_POLICY_ID = "v7_binding_weak_cox2"
MAX_UPLOAD = int(os.getenv("FUNNEL_MAX_UPLOAD", "100"))
MAX_BUDGET_N = int(os.getenv("FUNNEL_MAX_BUDGET_N", "50"))
DOCK_POLL_TIMEOUT = int(os.getenv("FUNNEL_DOCK_POLL_TIMEOUT", os.getenv("DOCKING_TIMEOUT_SECONDS", "600")))
DOCK_POLL_INTERVAL = float(os.getenv("FUNNEL_DOCK_POLL_INTERVAL", "2"))
COMPUTE_REJECT_RETRIES = int(os.getenv("FUNNEL_COMPUTE_REJECT_RETRIES", "120"))
COMPUTE_REJECT_SLEEP = float(os.getenv("FUNNEL_COMPUTE_REJECT_SLEEP", "2"))


class FunnelInputError(ValueError):
    """Bad request -- mapped to 400/413 by the router. Raised before any Job row is created."""

    def __init__(self, message: str, status: int = 400, detail: object | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail if detail is not None else message


def _init_fabric() -> None:
    """funnel.fabric.get_fabric_async() re-runs main.startup_event() unless told
    the app is already up. In the API process it always is (lifespan ran)."""
    import funnel.fabric as _fab
    _fab._STARTED = True


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


# ---------------------------------------------------------------------------
# candidate-set resolution (Task 4 guards live here -- before any expensive work)
# ---------------------------------------------------------------------------
def _dataset_csv(set_id: str) -> Path:
    return DATASETS_DIR / f"{set_id.replace('_v1', '')}_candidates_v1.csv"


def list_sets() -> list[dict]:
    out = []
    for p in sorted(DATASETS_DIR.glob("*_candidates_v1.csv")):
        set_id = p.name.replace("_candidates_v1.csv", "") + "_v1"
        cs = load_candidate_set(csv_path=p, set_id=set_id)
        out.append({
            "set_id": set_id, "size": len(cs),
            "n_reference": sum(1 for c in cs.candidates if c.is_reference),
            "content_sha256": cs.content_sha256, "csv": str(p.relative_to(p.parents[3])),
        })
    return out


def load_frontier(set_id: str) -> list[dict] | None:
    p = RUNS_DIR / f"frontier_{set_id}.csv"
    if not p.exists():
        return None
    rows = []
    for r in csv.DictReader(p.open()):
        row: dict = {}
        for k, v in r.items():
            if v == "" or v is None:
                row[k] = None
            elif k in ("est_dock_wall_s", "speedup_vs_full"):
                row[k] = float(v)
            else:
                row[k] = int(v)
        rows.append(row)
    return rows


def resolve_candidates(candidate_set_id: str | None, smiles: list[str] | None
                       ) -> tuple[str, str, list[Candidate], list[dict]]:
    """Return (set_id, content_sha256, candidates, parse_failures). Raises
    FunnelInputError on anything that should stop the request cold."""
    if bool(candidate_set_id) == bool(smiles):
        raise FunnelInputError("provide exactly one of candidate_set_id or smiles")

    if candidate_set_id:
        csv_path = _dataset_csv(candidate_set_id)
        if not csv_path.exists():
            raise FunnelInputError(
                f"unknown candidate_set_id '{candidate_set_id}'; see GET /api/funnel/sets", status=404)
        cs: CandidateSet = load_candidate_set(csv_path=csv_path, set_id=candidate_set_id)
        return cs.set_id, cs.content_sha256, list(cs.candidates), []

    # ---- uploaded list: size-cap, then RDKit-validate every entry ----
    smiles = [s.strip() for s in smiles if s and s.strip()]
    if not smiles:
        raise FunnelInputError("smiles list is empty")
    if len(smiles) > MAX_UPLOAD:
        raise FunnelInputError(
            f"uploaded {len(smiles)} SMILES; the cap is {MAX_UPLOAD}", status=413)

    candidates: list[Candidate] = []
    failures: list[dict] = []
    for i, smi in enumerate(smiles):
        mol = Chem.MolFromSmiles(smi)
        if mol is None:
            failures.append({"index": i, "smiles": smi, "error": "RDKit could not parse"})
            continue
        try:
            canon = Chem.MolToSmiles(mol)
        except Exception as exc:  # noqa: BLE001
            failures.append({"index": i, "smiles": smi, "error": f"canonicalisation failed: {exc}"})
            continue
        candidates.append(Candidate(
            ligand_id=f"UP_{i:03d}", name="", smiles=canon, source="upload",
            chembl_id="", activity_pchembl_max="", activity_note="", is_reference=False))

    if failures:
        raise FunnelInputError(
            f"{len(failures)}/{len(smiles)} uploaded SMILES failed to parse; fix and resubmit "
            f"(nothing was dropped or started)", status=400,
            detail={"parse_failures": failures, "n_valid": len(candidates)})

    blob = "\n".join(sorted(c.smiles for c in candidates)).encode()
    sha = hashlib.sha256(blob).hexdigest()
    return f"upload_{sha[:12]}", sha, candidates, []


def validate_start(policy_id: str, budget_n: int, n_candidates: int) -> int:
    if policy_id != FROZEN_POLICY_ID:
        raise FunnelInputError(
            f"policy_id must be '{FROZEN_POLICY_ID}' (the frozen v7 policy); "
            f"no other policy is served", status=400)
    if budget_n < 1 or budget_n > MAX_BUDGET_N:
        raise FunnelInputError(
            f"budget_n must be in [1, {MAX_BUDGET_N}]; got {budget_n}", status=413)
    return min(budget_n, n_candidates)


# ---------------------------------------------------------------------------
# the run (asyncio task in the API process)
# ---------------------------------------------------------------------------
async def _patch(job_store, run_id: str, t0: float, **fields) -> None:
    job = await job_store.get_job(run_id)
    out = dict(job.output or {})
    out.update(fields)
    out["elapsed_s"] = round(time.perf_counter() - t0, 2)
    await job_store.update_job(run_id, output=out)


async def _is_cancelled(job_store, run_id: str) -> bool:
    from jobs.models import JobStatus
    job = await job_store.get_job(run_id)
    return job is None or job.status == JobStatus.CANCELLED


async def _dock_seed(job_store, tool_registry, compute_router, run_id: str, t0: float,
                     child_id: str, smiles: str, target: str, seed: int,
                     dock_number: int) -> SeedDock:
    """One (candidate, seed) dock: submit through ComputeRouter as HEAVY_LOCAL
    'docking' (back off + retry on ComputeRejected -- never bypass the limit),
    then poll to a terminal state on a monotonic deadline. `dock_number` is this
    dock's 1-based position in the run, written to `docks_submitted` the moment
    the child Job is created so `/status` reflects an in-flight dock."""
    from compute.router import ComputeRejected

    tool = tool_registry.get("run_docking")
    s0 = time.perf_counter()
    await _patch(job_store, run_id, t0, current_dock_job_id=child_id)

    for _ in range(COMPUTE_REJECT_RETRIES):
        if await _is_cancelled(job_store, run_id):
            return SeedDock(seed, None, time.perf_counter() - s0, "cancelled")
        try:
            await compute_router.execute(
                tool, _job_store=job_store, _job_type="docking", _job_id=child_id,
                _job_input={
                    "smiles": smiles, "target": target, "exhaustiveness": EXHAUSTIVENESS,
                    "seed": seed, "conformer_seed": CONFORMER_SEED, "num_modes": NUM_MODES,
                    "funnel_run_id": run_id,
                },
            )
            await _patch(job_store, run_id, t0, docks_submitted=dock_number)
            break
        except ComputeRejected:
            await asyncio.sleep(COMPUTE_REJECT_SLEEP)
    else:
        return SeedDock(seed, None, time.perf_counter() - s0, "rejected",
                        "ComputeRejected retry budget exhausted")

    deadline = time.monotonic() + DOCK_POLL_TIMEOUT
    while True:
        if await _is_cancelled(job_store, run_id):
            # parent cancelled while we were waiting -- stop this dock too
            await job_store.cancel_job(child_id)
            child = await job_store.get_job(child_id)
            if child and child.worker_pid:
                try:
                    os.kill(child.worker_pid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
            return SeedDock(seed, None, time.perf_counter() - s0, "cancelled")
        job = await job_store.get_job(child_id)
        if job and job.status.value in ("completed", "failed", "cancelled"):
            wall = time.perf_counter() - s0
            if job.status.value == "completed":
                aff = (job.output or {}).get("affinity_kcal_mol")
                return SeedDock(seed, float(aff) if aff is not None else None, wall, "completed")
            return SeedDock(seed, None, wall, job.status.value, job.error)
        if time.monotonic() > deadline:
            return SeedDock(seed, None, time.perf_counter() - s0, "timeout",
                            f"no terminal state in {DOCK_POLL_TIMEOUT}s of active runtime")
        await asyncio.sleep(DOCK_POLL_INTERVAL)


async def execute_run(run_id: str) -> None:
    """Body of the asyncio task spawned by POST /api/funnel/start. Reads its own
    parent Job from the store; writes stage progress to output as it goes."""
    _init_fabric()
    import main
    from jobs.models import JobStatus
    from utils.vina_env import resolved_vina_version

    job_store = main.job_store
    tool_registry = main.tool_registry
    compute_router = main.compute_router

    parent = await job_store.get_job(run_id)
    inp = parent.input
    target = inp["target"]
    budget_n = inp["budget_n"]
    policy = DEFAULT_POLICY  # v7, frozen
    candidates = [
        Candidate(ligand_id=c["ligand_id"], name=c.get("name", ""), smiles=c["smiles"],
                  source="", chembl_id="", activity_pchembl_max="", activity_note="",
                  is_reference=False)
        for c in inp["candidates"]
    ]

    t0 = time.perf_counter()
    await job_store.update_job(run_id, status=JobStatus.RUNNING, started_at=_utcnow())
    await _patch(
        job_store, run_id, t0,
        stage="screening", candidates_in=len(candidates),
        candidate_set_id=inp["candidate_set_id"], target=target,
        budget_n=budget_n, policy_id=inp["policy_id"],
        started_at=_utcnow().isoformat(),
        stage_survivors=[], prescreen_selected=[],
        docks_submitted=0, docks_completed=0, docks_failed=0,
        current_dock_job_id=None, partial_results=[], run_record=None,
    )

    try:
        if await _is_cancelled(job_store, run_id):
            return await _patch(job_store, run_id, t0, stage="cancelled")

        passed_tox, filtered, per_candidate, stages = await screen(candidates, policy)
        await _patch(job_store, run_id, t0, stage="prescreen",
                     stage_survivors=[{"stage": s.stage, "in": s.survivors_in, "out": s.survivors_out}
                                      for s in stages])

        scored, _top_ignored, bmeta = score_and_select(passed_tox, policy, per_candidate)
        eff_n = min(budget_n, len(scored))
        top = scored[:eff_n]
        selected = [c.ligand_id for c, _, _ in top]
        await _patch(job_store, run_id, t0, stage="docking", prescreen_selected=selected,
                     docks_total=len(top) * len(SEEDS))

        results: list[DockResult] = []
        dock_wall = 0.0
        jobs = 0
        docks_completed = 0
        docks_failed = 0
        partial: list[dict] = []

        total_docks = len(top) * len(SEEDS)
        for ci, (c, _feat, _s) in enumerate(top):
            if await _is_cancelled(job_store, run_id):
                return await _patch(job_store, run_id, t0, stage="cancelled")
            dr = DockResult(ligand_id=c.ligand_id, smiles=c.smiles)
            for seed in SEEDS:
                jobs += 1
                sd = await _dock_seed(job_store, tool_registry, compute_router, run_id, t0,
                                      f"{run_id}__c{ci}s{seed}", c.smiles, target, seed,
                                      dock_number=jobs)
                dr.per_seed.append(sd)
                dr.jobs_submitted += 1
                dr.wall_s_total += sd.wall_s
                if sd.status == "completed":
                    docks_completed += 1
                elif sd.status in ("cancelled",):
                    return await _patch(job_store, run_id, t0, stage="cancelled")
                else:
                    docks_failed += 1
                await _patch(job_store, run_id, t0,
                             docks_submitted=jobs, docks_total=total_docks,
                             docks_completed=docks_completed, docks_failed=docks_failed)
            results.append(dr)
            per_candidate[c.ligand_id]["docked"] = True
            dock_wall += dr.wall_s_total
            partial.append({"ligand_id": c.ligand_id, "seeds_done": len(dr.per_seed),
                            "mean_affinity": (round(dr.mean_affinity, 4)
                                              if dr.mean_affinity is not None else None)})
            await _patch(job_store, run_id, t0, partial_results=list(partial),
                         current_dock_job_id=None)

        if await _is_cancelled(job_store, run_id):
            return await _patch(job_store, run_id, t0, stage="cancelled")

        await _patch(job_store, run_id, t0, stage="ranking")
        entries = rank_docked(results)
        stages.append(StageCount("dock_top_n", len(passed_tox), len(top),
                                 f"{jobs} jobs = {len(top)} x {len(SEEDS)} seeds"))

        rec = RunRecord(
            run_id=run_id, path_name="funnel", schema_version=SCHEMA_VERSION,
            timestamp=_utcnow().isoformat(), platform=platform.platform(),
            vina_version=resolved_vina_version(),
            docking_params=DockingParams(exhaustiveness=EXHAUSTIVENESS, seeds=SEEDS, cpu=1,
                                         target=target, num_modes=NUM_MODES,
                                         conformer_seed=CONFORMER_SEED),
            candidate_set_id=inp["candidate_set_id"], candidate_set_size=len(candidates),
            stage_survivors=stages, total_docking_jobs_submitted=jobs,
            total_docking_wall_s=round(dock_wall, 2),
            total_run_wall_s=round(time.perf_counter() - t0, 2),
            results=entries, filtered_out=filtered, funnel_policy=policy.as_dict(),
            per_candidate=per_candidate,
            notes=[
                f"candidate_set_sha256={inp['content_sha256']}",
                "served via POST /api/funnel/start (funnel.service)",
                f"binding_norm: min={bmeta['binding_min']:.4f} max={bmeta['binding_max']:.4f} "
                f"lower_is_better={bmeta['binding_lower_is_better']} "
                "(min-max feature scaling over survivors, not threshold tuning)",
                "ranking identical to baseline (funnel.ranking.rank_docked); "
                "only the docked subset differs.",
            ],
        )
        await _patch(job_store, run_id, t0, stage="done",
                     docks_completed=docks_completed, docks_failed=docks_failed,
                     current_dock_job_id=None, run_record=rec.to_dict())
        await job_store.update_job(run_id, status=JobStatus.COMPLETED, completed_at=_utcnow())
        logger.info("funnel_run_done run_id=%s docks=%d/%d failed=%d wall_s=%.1f",
                    run_id, docks_completed, jobs, docks_failed, time.perf_counter() - t0)

    except Exception as exc:  # noqa: BLE001
        logger.exception("funnel_run_failed run_id=%s", run_id)
        await _patch(job_store, run_id, t0, stage="failed", error=str(exc), current_dock_job_id=None)
        await job_store.update_job(run_id, status=JobStatus.FAILED, error=str(exc),
                                   completed_at=_utcnow())


async def cancel_run(run_id: str) -> dict:
    """Cancel the parent funnel Job and any in-flight child docking subprocess."""
    import main
    from jobs.models import JobStatus

    job_store = main.job_store
    parent = await job_store.get_job(run_id)
    if parent is None or parent.type != "funnel":
        return {"run_id": run_id, "cancelled": False, "message": "no such funnel run"}
    if parent.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return {"run_id": run_id, "cancelled": False,
                "message": f"run already {parent.status.value}"}

    await job_store.cancel_job(run_id)

    child_id = (parent.output or {}).get("current_dock_job_id")
    killed = False
    if child_id:
        child = await job_store.get_job(child_id)
        if child and child.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            await job_store.cancel_job(child_id)
            if child.worker_pid:
                try:
                    os.kill(child.worker_pid, signal.SIGKILL)
                    killed = True
                except (ProcessLookupError, OSError):
                    pass
    logger.info("funnel_run_cancelled run_id=%s child=%s killed_vina=%s", run_id, child_id, killed)
    return {"run_id": run_id, "cancelled": True, "in_flight_dock_cancelled": bool(child_id),
            "vina_subprocess_killed": killed, "message": "funnel run cancelled"}
