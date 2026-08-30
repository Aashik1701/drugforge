"""
Computational-funnel HTTP service.

  POST /api/funnel/start           queue a run, return run_id immediately
  GET  /api/funnel/status/{run_id} stage, survivor counts, docks, partial results
  GET  /api/funnel/result/{run_id} full RunRecord v1.0.0 (409 until done)
  POST /api/funnel/cancel/{run_id} cancel run + in-flight Vina subprocess
  GET  /api/funnel/sets            committed candidate sets + content hashes
  GET  /api/funnel/frontier/{set}  cached recall-vs-budget curve

Handlers stay thin: validate cheaply, look the tool up, hand it to
ComputeRouter, spawn the executor task, return. The resource decision stays in
ComputeRouter / ResourceManager. See docs/development/funnel-service.md.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException

from compute.router import ComputeRejected
from funnel import service
from schemas.funnel import (
    CandidateSetInfo, FunnelStartRequest, FunnelStartResponse, FunnelStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _job_store():
    from main import job_store
    return job_store


def _tool_registry():
    from main import tool_registry
    return tool_registry


def _compute_router():
    from main import compute_router
    return compute_router


@router.post("/start", response_model=FunnelStartResponse)
async def start_funnel(req: FunnelStartRequest) -> FunnelStartResponse:
    # --- cheap validation, before any Job row exists (Task 4) ---
    try:
        set_id, sha, candidates, _ = service.resolve_candidates(req.candidate_set_id, req.smiles)
        eff_n = service.validate_start(req.policy_id, req.budget_n, len(candidates))
    except service.FunnelInputError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)

    job_store = _job_store()
    if await job_store.count_active("funnel") > 0:
        raise HTTPException(status_code=503,
                            detail="a funnel run is already active; only one at a time")

    run_id = f"funnel_{uuid.uuid4().hex[:12]}"
    tool = _tool_registry().get("run_funnel")
    if tool is None:
        raise HTTPException(status_code=500, detail="run_funnel tool not registered")

    job_input = {
        "candidate_set_id": set_id, "content_sha256": sha,
        "target": req.target, "budget_n": eff_n, "policy_id": req.policy_id,
        "candidates": [{"ligand_id": c.ligand_id, "name": c.name, "smiles": c.smiles}
                       for c in candidates],
    }
    try:
        job = await _compute_router().execute(
            tool, _job_store=job_store, _job_type="funnel", _job_id=run_id, _job_input=job_input,
        )
    except ComputeRejected as exc:
        raise HTTPException(status_code=503, detail=exc.reason)

    task = asyncio.create_task(service.execute_run(run_id))
    task.add_done_callback(
        lambda t: t.exception() and logger.error("funnel task crashed run_id=%s: %r", run_id, t.exception())
    )

    logger.info("funnel_run_queued run_id=%s set=%s target=%s budget_n=%d",
                run_id, set_id, req.target, eff_n)
    return FunnelStartResponse(
        run_id=job.id, status="queued", candidate_set_id=set_id, target=req.target,
        budget_n=eff_n, policy_id=req.policy_id, candidates_in=len(candidates),
        message=f"funnel run queued (dock top {eff_n} of {len(candidates)}, 4 seeds each)",
    )


@router.get("/status/{run_id}", response_model=FunnelStatusResponse)
async def funnel_status(run_id: str) -> FunnelStatusResponse:
    job = await _job_store().get_job(run_id)
    if job is None or job.type != "funnel":
        raise HTTPException(status_code=404, detail=f"no funnel run '{run_id}'")
    o = job.output or {}
    return FunnelStatusResponse(
        run_id=job.id, status=job.status.value, stage=o.get("stage", "queued"),
        candidate_set_id=o.get("candidate_set_id", job.input.get("candidate_set_id", "")),
        target=o.get("target", job.input.get("target", "")),
        budget_n=o.get("budget_n", job.input.get("budget_n", 0)),
        policy_id=o.get("policy_id", job.input.get("policy_id", "")),
        candidates_in=o.get("candidates_in", len(job.input.get("candidates", []))),
        stage_survivors=o.get("stage_survivors", []),
        prescreen_selected=o.get("prescreen_selected", []),
        docks_submitted=o.get("docks_submitted", 0),
        docks_total=o.get("docks_total", 0),
        docks_completed=o.get("docks_completed", 0),
        docks_failed=o.get("docks_failed", 0),
        current_dock_job_id=o.get("current_dock_job_id"),
        partial_results=o.get("partial_results", []),
        elapsed_s=o.get("elapsed_s"),
        error=job.error or o.get("error"),
    )


@router.get("/result/{run_id}")
async def funnel_result(run_id: str) -> dict:
    job = await _job_store().get_job(run_id)
    if job is None or job.type != "funnel":
        raise HTTPException(status_code=404, detail=f"no funnel run '{run_id}'")
    rec = (job.output or {}).get("run_record")
    if not rec:
        raise HTTPException(
            status_code=409,
            detail=f"run '{run_id}' is {job.status.value} at stage "
                   f"'{(job.output or {}).get('stage', 'queued')}'; result not ready")
    return rec


@router.post("/cancel/{run_id}")
async def cancel_funnel(run_id: str) -> dict:
    return await service.cancel_run(run_id)


@router.get("/sets", response_model=list[CandidateSetInfo])
async def funnel_sets() -> list[CandidateSetInfo]:
    return [CandidateSetInfo(**s) for s in service.list_sets()]


@router.get("/frontier/{set_id}")
async def funnel_frontier(set_id: str) -> dict:
    rows = service.load_frontier(set_id)
    if rows is None:
        raise HTTPException(status_code=404,
                            detail=f"no cached frontier for '{set_id}' (runs/frontier_{set_id}.csv)")
    return {"set_id": set_id, "rows": rows}
