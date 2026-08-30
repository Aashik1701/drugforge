"""
agents.service -- AgentRunner behind HTTP.

A parent Job of type "agent" is a *record*; the work is an asyncio task in the
API process that walks the caller-supplied tool sequence one step at a time via
AgentRunner.call_tool (its public one-call primitive), writing the ToolCall
audit trail into job.output after every step so it is visible live.

Nothing here changes AgentRunner / AgentState / AgentBudget / ToolCall: the loop
replicates AgentRunner.run()'s stop semantics (BudgetExhausted -> stop; an
individual failed/rejected/unknown call does not stop the run) and constructs
the same objects the runner does. ComputeRouter / ResourceManager / JobStore /
the tool-registry contract are untouched -- see docs/development/agent-service.md.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
import signal
import time
from typing import Any, Optional

from pydantic import BaseModel

from agents import AgentBudget, AgentResult, AgentRunner, AgentState, BudgetExhausted, RunStatus
from agents.types import ToolCall, ToolCallStatus
from agents.catalog import ToolSpec, build_catalog

logger = logging.getLogger("agents.service")

CHILD_POLL_INTERVAL = float(os.getenv("AGENT_CHILD_POLL_INTERVAL", "2"))
CHILD_POLL_TIMEOUT = int(os.getenv("AGENT_CHILD_POLL_TIMEOUT", "7200"))  # minutes..hours

# AgentBudget fields a request may lower (never raise). max_concurrent_runs_local
# is a global, not a per-run property -- server-side only.
CLAMPABLE = ("max_tool_calls", "max_docking_jobs", "max_steps", "max_candidates", "max_retries")

_CATALOG: Optional[dict[str, ToolSpec]] = None


def get_catalog() -> dict[str, ToolSpec]:
    global _CATALOG
    if _CATALOG is None:
        import main
        _CATALOG = build_catalog(main.tool_registry)
    return _CATALOG


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _funnel_service():
    from funnel import service as fs
    return fs


class AgentInputError(ValueError):
    """Bad request -- mapped to a 4xx by the router before any Job row exists."""

    def __init__(self, message: str, status: int = 400, detail: object | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail if detail is not None else message


class _Cancelled(Exception):
    """Internal: the parent agent run was cancelled mid-step."""


# ---------------------------------------------------------------------------
# budget clamping  (client input -> effective AgentBudget, never above ceiling)
# ---------------------------------------------------------------------------
def clamp_budget(requested: Optional[dict]) -> tuple[AgentBudget, dict, dict]:
    """Return (effective AgentBudget, ceilings dict, clamped dict).

    effective[k] = min(requested[k], ceiling[k]) for every clampable field;
    a field asked above its ceiling is recorded in `clamped` and set to the
    ceiling -- the request is neither rejected for it nor granted it."""
    ceiling = AgentBudget.from_env()
    requested = requested or {}
    unknown = set(requested) - set(CLAMPABLE)
    if unknown:
        raise AgentInputError(
            f"unknown budget field(s): {', '.join(sorted(unknown))}; "
            f"settable: {', '.join(CLAMPABLE)}"
        )

    eff: dict[str, int] = {}
    clamped: dict[str, dict] = {}
    for k in CLAMPABLE:
        cap = getattr(ceiling, k)
        val = requested.get(k)
        if val is None:
            eff[k] = cap
            continue
        val = int(val)
        if val < 1:
            raise AgentInputError(f"budget.{k} must be >= 1; got {val}")
        eff[k] = min(val, cap)
        if val > cap:
            clamped[k] = {"requested": val, "ceiling": cap, "effective": cap}

    effective = AgentBudget(
        max_candidates=eff["max_candidates"],
        max_docking_jobs=eff["max_docking_jobs"],
        max_steps=eff["max_steps"],
        max_tool_calls=eff["max_tool_calls"],
        max_retries=eff["max_retries"],
        max_concurrent_runs_local=ceiling.max_concurrent_runs_local,
    )
    ceilings = {k: getattr(ceiling, k) for k in CLAMPABLE}
    ceilings["max_concurrent_runs_local"] = ceiling.max_concurrent_runs_local
    return effective, ceilings, clamped


# ---------------------------------------------------------------------------
# submission validation  (all before any Job row is created)
# ---------------------------------------------------------------------------
def validate_submission(requests: list, effective: AgentBudget) -> list[str]:
    """Raise AgentInputError on anything that should stop the request cold.
    Returns the list of heavy tool names in the sequence."""
    catalog = get_catalog()
    if not requests:
        raise AgentInputError("requests must be a non-empty ordered list of {name, args}")

    names = [r.name for r in requests]
    unknown = sorted({n for n in names if n not in catalog})
    if unknown:
        raise AgentInputError(
            f"unknown tool(s): {', '.join(unknown)}",
            detail={"unknown_tools": unknown, "available": sorted(catalog)},
        )

    bad = []
    for i, r in enumerate(requests):
        errs = catalog[r.name].validate(r.args or {})
        if errs:
            bad.append({"index": i, "name": r.name, "errors": errs})
    if bad:
        raise AgentInputError(
            "one or more steps have invalid arguments; nothing was started",
            detail={"invalid_steps": bad},
        )

    heavy = [n for n in names if catalog[n].heavy]
    if len(heavy) > effective.max_docking_jobs:
        raise AgentInputError(
            f"sequence has {len(heavy)} heavy tool(s) ({', '.join(heavy)}) but the "
            f"effective max_docking_jobs is {effective.max_docking_jobs}; "
            f"nothing was started",
            detail={
                "heavy_steps": len(heavy),
                "heavy_tools": heavy,
                "max_docking_jobs": effective.max_docking_jobs,
            },
        )
    return heavy


# ---------------------------------------------------------------------------
# serialisation helpers
# ---------------------------------------------------------------------------
def _safe_json(obj: Any) -> Any:
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_safe_json(v) for v in obj]
    if isinstance(obj, BaseModel):
        return _safe_json(obj.model_dump())
    # a jobs.models.Job (returned by ComputeRouter for a heavy tool)
    if hasattr(obj, "id") and hasattr(obj, "status") and hasattr(obj, "type"):
        st = obj.status
        return {"job_id": obj.id, "type": obj.type,
                "status": getattr(st, "value", str(st))}
    if hasattr(obj, "tolist"):  # numpy array
        try:
            return _safe_json(obj.tolist())
        except Exception:  # noqa: BLE001
            pass
    text = repr(obj)
    return text if len(text) <= 500 else text[:500] + "…"


def _tc_to_dict(tc: ToolCall, step: int, *, with_result: bool) -> dict:
    d = {
        "step": step,
        "tool_name": tc.tool_name,
        "arguments": _safe_json(tc.arguments),
        "status": tc.status.value,
        "duration_ms": round(tc.duration_ms, 2) if tc.duration_ms is not None else None,
        "error": tc.error,
        "started_at": tc.started_at.isoformat() if tc.started_at else None,
        "finished_at": tc.finished_at.isoformat() if tc.finished_at else None,
    }
    if with_result:
        d["result"] = _safe_json(tc.result)
    else:
        d["result_kind"] = type(tc.result).__name__ if tc.result is not None else None
    return d


def _manual_toolcall(name: str, args: dict, status: ToolCallStatus, error: str) -> ToolCall:
    """A ToolCall built exactly as AgentRunner builds one, for the two outcomes
    the runner cannot produce on its own (funnel-already-active, agent
    docking-budget exhausted)."""
    tc = ToolCall(tool_name=name, arguments={"tool": name, "args": dict(args)})
    tc.status = status
    tc.error = error
    tc.finished_at = _utcnow()
    return tc


# ---------------------------------------------------------------------------
# job.output writer  (audit trail visible live)
# ---------------------------------------------------------------------------
async def _patch(job_store, run_id: str, t0: float, **fields) -> None:
    job = await job_store.get_job(run_id)
    if job is None:
        return
    out = dict(job.output or {})
    out.update(fields)
    out["elapsed_s"] = round(time.perf_counter() - t0, 2)
    await job_store.update_job(run_id, output=out)


def _budget_block(state: AgentState, ceilings: dict) -> dict:
    b = state.budget
    consumed = {
        "tool_calls": len(state.tool_calls),
        "steps": state.steps_taken,
        "docking_jobs": state.docking_jobs_submitted,
    }
    remaining = {
        "tool_calls": max(0, b.max_tool_calls - consumed["tool_calls"]),
        "steps": max(0, b.max_steps - consumed["steps"]),
        "docking_jobs": max(0, b.max_docking_jobs - consumed["docking_jobs"]),
    }
    return {
        "effective": {k: getattr(b, k) for k in CLAMPABLE},
        "ceilings": ceilings,
        "consumed": consumed,
        "remaining": remaining,
    }


async def _flush_trail(job_store, run_id, t0, state, ceilings) -> None:
    """Push just the growing audit trail + budget to job.output, without
    touching current_step/current_child. Used mid heavy-step so the run_funnel
    / run_docking ToolCall is visible the moment it is submitted, not only
    after it finishes."""
    await _patch(
        job_store, run_id, t0,
        status=state.status.value,
        tool_calls=[_tc_to_dict(tc, i, with_result=False) for i, tc in enumerate(state.tool_calls)],
        budget=_budget_block(state, ceilings),
    )


async def _write(job_store, run_id, t0, state, ceilings, *, current_step, total_steps,
                 result=None, current_child="keep") -> None:
    fields: dict[str, Any] = {
        "status": state.status.value,
        "goal": state.goal,
        "current_step": current_step,
        "total_steps": total_steps,
        "tool_calls": [_tc_to_dict(tc, i, with_result=False) for i, tc in enumerate(state.tool_calls)],
        "budget": _budget_block(state, ceilings),
    }
    if result is not None:
        fields["result"] = result
    if current_child != "keep":
        fields["current_child"] = current_child
    await _patch(job_store, run_id, t0, **fields)


# ---------------------------------------------------------------------------
# cancellation
# ---------------------------------------------------------------------------
async def _is_cancelled(job_store, run_id: str) -> bool:
    from jobs.models import JobStatus
    job = await job_store.get_job(run_id)
    return job is None or job.status == JobStatus.CANCELLED


async def _cancel_child(job_store, child: dict) -> tuple[bool, bool]:
    """Cancel an in-flight child job. Returns (child_cancelled, vina_killed)."""
    from jobs.models import JobStatus
    cid = child.get("job_id")
    if not cid:
        return False, False
    cj = await job_store.get_job(cid)
    if cj is None or cj.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        return False, False
    if child.get("type") == "funnel":
        res = await _funnel_service().cancel_run(cid)
        return True, bool(res.get("vina_subprocess_killed"))
    await job_store.cancel_job(cid)
    if cj.worker_pid:
        try:
            os.kill(cj.worker_pid, signal.SIGKILL)
            return True, True
        except (ProcessLookupError, OSError):
            pass
    return True, False


async def cancel_run(run_id: str) -> dict:
    import main
    from jobs.models import JobStatus

    job_store = main.job_store
    parent = await job_store.get_job(run_id)
    if parent is None or parent.type != "agent":
        return {"run_id": run_id, "cancelled": False, "message": "no such agent run"}
    if parent.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return {"run_id": run_id, "cancelled": False,
                "message": f"run already {parent.status.value}"}

    await job_store.cancel_job(run_id)
    child = (parent.output or {}).get("current_child") or {}
    child_cancelled, killed = await _cancel_child(job_store, child)
    logger.info("agent_run_cancelled run_id=%s child=%s killed=%s",
                run_id, child.get("job_id"), killed)
    return {
        "run_id": run_id,
        "cancelled": True,
        "in_flight_child_cancelled": child_cancelled,
        "vina_subprocess_killed": killed,
        "message": "agent run cancelled",
    }


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------
async def _poll_child(job_store, run_id, t0, child_id: str, job_type: str):
    """Wait for a heavy child job to reach a terminal state. Returns the
    terminal Job, or None if the parent agent run was cancelled while waiting.
    Raises TimeoutError if the child never terminates within CHILD_POLL_TIMEOUT."""
    deadline = time.monotonic() + CHILD_POLL_TIMEOUT
    while True:
        if await _is_cancelled(job_store, run_id):
            await _cancel_child(job_store, {"job_id": child_id, "type": job_type})
            return None
        child = await job_store.get_job(child_id)
        if child and child.status.value in ("completed", "failed", "cancelled"):
            return child
        if job_type == "funnel" and child:
            co = child.output or {}
            await _patch(job_store, run_id, t0, current_child={
                "job_id": child_id, "type": "funnel",
                "stage": co.get("stage"),
                "docks_completed": co.get("docks_completed"),
                "docks_total": co.get("docks_total"),
            })
        if time.monotonic() > deadline:
            raise TimeoutError(f"child {job_type} job {child_id} did not terminate in {CHILD_POLL_TIMEOUT}s")
        await asyncio.sleep(CHILD_POLL_INTERVAL)


async def _run_heavy_step(runner, state, job_store, run_id, t0, ceilings,
                          idx: int, name: str, args: dict, spec: ToolSpec) -> None:
    """One HEAVY_LOCAL step: submit a child job through the real ComputeRouter
    (via runner.call_tool, so the ToolCall + any REJECTED is recorded exactly
    as everywhere else), then poll the child to terminal, resolving the async
    outcome onto that same ToolCall."""
    if not state.can_call_tool():
        raise BudgetExhausted(f"{len(state.tool_calls)}/{state.budget.max_tool_calls} tool calls used")

    job_type, job_input = spec.heavy_job(args)
    child_id = f"{run_id}__s{idx}_{name}"

    # funnel's own one-at-a-time rule -- do not start a second funnel
    if job_type == "funnel" and await job_store.count_active("funnel") > 0:
        tc = _manual_toolcall(name, args, ToolCallStatus.FAILED,
                              "a funnel run is already active; only one at a time")
        state.tool_calls.append(tc)
        state.steps_taken += 1
        return

    if not state.can_submit_docking_job():
        tc = _manual_toolcall(name, args, ToolCallStatus.REJECTED,
                              f"agent docking-job budget exhausted "
                              f"({state.docking_jobs_submitted}/{state.budget.max_docking_jobs})")
        state.tool_calls.append(tc)
        state.steps_taken += 1
        return

    tc = await runner.call_tool(
        state, name,
        _job_store=job_store, _job_type=job_type, _job_id=child_id, _job_input=job_input,
    )
    tc.arguments = {"tool": name, "args": dict(args)}  # audit trail shows the caller's args
    if tc.status is not ToolCallStatus.SUCCESS:
        return  # REJECTED by ResourceManager (docking disabled / slot taken) -- recorded, nothing to poll

    state.docking_jobs_submitted += 1
    tc.finished_at = None  # duration_ms == None => "in flight" until the child terminates
    tc.result = {"child_job_id": child_id, "type": job_type, "state": "in_flight"}
    await _patch(job_store, run_id, t0, current_child={"job_id": child_id, "type": job_type})
    await _flush_trail(job_store, run_id, t0, state, ceilings)  # make the heavy call visible now

    if job_type == "funnel":
        task = asyncio.create_task(_funnel_service().execute_run(child_id))
        task.add_done_callback(lambda tk: tk.exception() and logger.error(
            "agent funnel child crashed run_id=%s child=%s: %r", run_id, child_id, tk.exception()))

    try:
        terminal = await _poll_child(job_store, run_id, t0, child_id, job_type)
    except TimeoutError as exc:
        tc.finished_at = _utcnow()
        tc.status = ToolCallStatus.FAILED
        tc.error = str(exc)
        await _patch(job_store, run_id, t0, current_child=None)
        return

    tc.finished_at = _utcnow()
    if terminal is None:
        tc.status = ToolCallStatus.FAILED
        tc.error = "agent run cancelled while this child was in flight"
        tc.result = {"child_job_id": child_id, "cancelled": True}
        raise _Cancelled()

    tc.result = {"child_job_id": child_id, "type": job_type,
                 "child_status": terminal.status.value,
                 "output": _safe_json(terminal.output)}
    if terminal.status.value == "completed":
        tc.status = ToolCallStatus.SUCCESS
    else:
        tc.status = ToolCallStatus.FAILED
        tc.error = terminal.error or f"child {job_type} job ended {terminal.status.value}"
    await _patch(job_store, run_id, t0, current_child=None)


async def execute_run(run_id: str) -> None:
    """Body of the asyncio task spawned by POST /api/agent/runs."""
    import main
    from jobs.models import JobStatus

    job_store = main.job_store
    runner = AgentRunner(main.tool_registry, main.compute_router)
    catalog = get_catalog()

    parent = await job_store.get_job(run_id)
    inp = parent.input
    requests: list[dict] = inp["requests"]
    ceilings: dict = inp["ceilings"]
    budget = AgentBudget(**inp["effective_budget"])
    state = AgentState(run_id=run_id, goal=inp.get("goal", ""), budget=budget)

    t0 = time.perf_counter()
    n = len(requests)
    await job_store.update_job(run_id, status=JobStatus.RUNNING, started_at=_utcnow())
    state.status = RunStatus.RUNNING
    await _write(job_store, run_id, t0, state, ceilings, current_step=0, total_steps=n,
                current_child=None)

    for i, req in enumerate(requests):
        if await _is_cancelled(job_store, run_id):
            state.status = RunStatus.CANCELLED
            break

        name = req["name"]
        args = req.get("args") or {}
        spec = catalog[name]
        try:
            if not state.can_take_step():
                raise BudgetExhausted(f"{state.steps_taken}/{state.budget.max_steps} steps used")
            if spec.heavy:
                await _run_heavy_step(runner, state, job_store, run_id, t0, ceilings,
                                      i, name, args, spec)
            else:
                call_args, call_kwargs = spec.build_local(args)
                tc = await runner.call_tool(state, name, *call_args, **call_kwargs)
                tc.arguments = {"tool": name, "args": dict(args)}
        except BudgetExhausted as exc:
            state.status = RunStatus.BUDGET_EXHAUSTED
            logger.info("agent_run_budget_exhausted run_id=%s reason=%s", run_id, exc)
            break
        except _Cancelled:
            state.status = RunStatus.CANCELLED
            break

        await _write(job_store, run_id, t0, state, ceilings,
                     current_step=i + 1, total_steps=n)
    else:
        state.status = RunStatus.COMPLETED

    result = AgentResult(
        run_id=run_id, status=state.status,
        output={"tool_calls_made": len(state.tool_calls),
                "statuses": [tc.status.value for tc in state.tool_calls]},
        tool_calls=state.tool_calls,
    )
    result_doc = {
        "run_id": run_id,
        "status": state.status.value,
        "output": _safe_json(result.output),
        "error": result.error,
        "tool_calls": [_tc_to_dict(tc, i, with_result=True) for i, tc in enumerate(state.tool_calls)],
    }
    # BUDGET_EXHAUSTED is a clean stop at a ceiling, not an error -> the parent
    # Job is COMPLETED; the nuance is preserved in output["status"].
    final = {
        RunStatus.COMPLETED: JobStatus.COMPLETED,
        RunStatus.BUDGET_EXHAUSTED: JobStatus.COMPLETED,
        RunStatus.CANCELLED: JobStatus.CANCELLED,
        RunStatus.FAILED: JobStatus.FAILED,
        RunStatus.RUNNING: JobStatus.COMPLETED,
    }.get(state.status, JobStatus.COMPLETED)

    await _write(job_store, run_id, t0, state, ceilings,
                 current_step=len(state.tool_calls), total_steps=n,
                 result=result_doc, current_child=None)
    await job_store.update_job(run_id, status=final, completed_at=_utcnow())
    logger.info("agent_run_finished run_id=%s status=%s tool_calls=%d",
                run_id, state.status.value, len(state.tool_calls))
