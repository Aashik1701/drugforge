"""
Agent HTTP service -- AgentRunner (agents/runner.py, present since Pass 3)
behind endpoints.

  POST /api/agent/runs                 queue a run, return run_id immediately
  GET  /api/agent/runs/{run_id}        status + live ToolCall audit trail + budget
  GET  /api/agent/runs/{run_id}/result full AgentResult (409 until terminal)
  POST /api/agent/runs/{run_id}/cancel cancel run + any in-flight child job
  GET  /api/agent/tools                the registry, shaped for a planner + a human

Handlers stay thin: validate via agents/catalog + agents/service, create the
parent Job, spawn the executor task, return. No LLM, no planner, no
tool-selection -- the sequence is the caller's. See
docs/development/agent-service.md.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException

from agents import service
from schemas.agent import AgentRunAccepted, AgentRunRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _job_store():
    from main import job_store
    return job_store


@router.get("/tools")
async def agent_tools() -> list[dict]:
    """The tool registry, machine-readable (JSON-Schema args) and human-readable.
    This is what a Phase-4 planner reads to choose a sequence."""
    catalog = service.get_catalog()
    return [catalog[name].as_dict() for name in sorted(catalog)]


@router.post("/runs", response_model=AgentRunAccepted)
async def start_agent_run(req: AgentRunRequest) -> AgentRunAccepted:
    # --- budget: clamp client input to the server ceilings (never raise) ---
    try:
        effective, ceilings, clamped = service.clamp_budget(
            req.budget.model_dump(exclude_none=True) if req.budget else None
        )
    except service.AgentInputError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)

    # --- validate the whole sequence before any Job row exists ---
    try:
        heavy = service.validate_submission(req.requests, effective)
    except service.AgentInputError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail)

    job_store = _job_store()

    # one agent run at a time (AgentBudget.max_concurrent_runs_local)
    active = await job_store.count_active("agent")
    if active >= effective.max_concurrent_runs_local:
        raise HTTPException(
            status_code=503,
            detail=f"an agent run is already active ({active}/{effective.max_concurrent_runs_local}); "
                   f"only one at a time",
        )

    # a run_funnel step cannot start while a funnel is already running
    if "run_funnel" in heavy and await job_store.count_active("funnel") > 0:
        raise HTTPException(
            status_code=400,
            detail="the sequence contains run_funnel but a funnel run is already active; "
                   "nothing was started",
        )

    run_id = f"agent_{uuid.uuid4().hex[:12]}"
    job_input = {
        "goal": req.goal,
        "requests": [r.model_dump() for r in req.requests],
        "effective_budget": {
            "max_candidates": effective.max_candidates,
            "max_docking_jobs": effective.max_docking_jobs,
            "max_steps": effective.max_steps,
            "max_tool_calls": effective.max_tool_calls,
            "max_retries": effective.max_retries,
            "max_concurrent_runs_local": effective.max_concurrent_runs_local,
        },
        "ceilings": ceilings,
        "clamped": clamped,
    }
    await job_store.create_job(job_type="agent", job_input=job_input, job_id=run_id)

    task = asyncio.create_task(service.execute_run(run_id))
    task.add_done_callback(
        lambda t: t.exception() and logger.error("agent task crashed run_id=%s: %r", run_id, t.exception())
    )

    logger.info("agent_run_queued run_id=%s steps=%d heavy=%d", run_id, len(req.requests), len(heavy))
    return AgentRunAccepted(
        run_id=run_id,
        status="queued",
        accepted_steps=len(req.requests),
        heavy_steps=len(heavy),
        budget={"effective": job_input["effective_budget"], "ceilings": ceilings, "clamped": clamped},
        message=f"agent run queued ({len(req.requests)} steps, {len(heavy)} heavy)",
    )


@router.get("/runs/{run_id}")
async def agent_run_status(run_id: str) -> dict:
    job = await _job_store().get_job(run_id)
    if job is None or job.type != "agent":
        raise HTTPException(status_code=404, detail=f"no agent run '{run_id}'")
    o = job.output or {}
    return {
        "run_id": job.id,
        "status": o.get("status", job.status.value),
        "job_status": job.status.value,
        "goal": o.get("goal", job.input.get("goal", "")),
        "current_step": o.get("current_step", 0),
        "total_steps": o.get("total_steps", len(job.input.get("requests", []))),
        "tool_calls": o.get("tool_calls", []),
        "budget": o.get("budget", {}),
        "current_child": o.get("current_child"),
        "elapsed_s": o.get("elapsed_s"),
        "error": job.error or o.get("error"),
    }


@router.get("/runs/{run_id}/result")
async def agent_run_result(run_id: str) -> dict:
    from jobs.models import JobStatus

    job = await _job_store().get_job(run_id)
    if job is None or job.type != "agent":
        raise HTTPException(status_code=404, detail=f"no agent run '{run_id}'")
    if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        raise HTTPException(
            status_code=409,
            detail=f"run '{run_id}' is {job.status.value} at step "
                   f"{(job.output or {}).get('current_step', 0)}; result not ready",
        )
    result = (job.output or {}).get("result")
    if result is None:
        raise HTTPException(status_code=409, detail=f"run '{run_id}' has no result document yet")
    return result


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str) -> dict:
    return await service.cancel_run(run_id)
