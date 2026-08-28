"""
Asynchronous molecular docking endpoints using AutoDock Vina CLI.

Endpoints (unchanged public contract):
- POST /api/dock/start
- POST /api/dock/cancel/{task_id}
- GET /api/dock/status/{task_id}
- GET /api/dock/history
- GET /api/dock/receptor/{target}

Design (post compute-fabric migration):
- Jobs persist in JobStore (SQLite-backed, survives API restarts) instead of
  an in-memory dict.
- Actual Vina execution happens in a separate LocalWorker process
  (jobs/workers/local_worker.py + docking_worker.py) — this router only
  creates/reads/cancels job records, it never runs Vina itself, not even via
  BackgroundTasks anymore.
- ResourceManager gates every /start request against the active ComputePolicy
  (e.g. docking is disabled by default in battery-saver mode).
- Cross-process cancellation: a running job's OS PID is written to the job
  record by the worker; /cancel kills it directly via os.kill().

No mock affinities — real kcal/mol from Vina, same as before.
"""

from __future__ import annotations

import logging
import os
import signal
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from compute.router import ComputeRejected
from jobs.models import JobStatus
from schemas.docking import (
    DockStartRequest,
    DockStartResponse,
    DockStatusResponse,
)
from utils.rdkit_helper import validate_smiles

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Paths (unchanged) ---
BACKEND_DIR = Path(__file__).resolve().parents[2]
TARGETS_DIR = Path(os.getenv("DOCKING_TARGETS_DIR", BACKEND_DIR / "targets"))

# --- Target definitions (unchanged) ---
TARGET_CONFIG: dict[str, dict[str, Any]] = {
    "cox2": {
        "receptor": "cox2_receptor.pdbqt",
        "center": [22.1, 10.5, -14.3],
        "box_size": [20.0, 20.0, 20.0],
    },
    "ace2": {
        "receptor": "ace2_receptor.pdbqt",
        "center": [15.1, 22.5, 9.0],
        "box_size": [20.0, 20.0, 20.0],
    },
}

# Internal-status -> external-status mapping. The public API has always used
# "processing" (see schemas.docking.DockTaskStatus); the internal Job model
# uses "running" (matches the generic job-status vocabulary shared with any
# future job type). This mapping is the only place that difference exists.
_STATUS_TO_API: dict[JobStatus, str] = {
    JobStatus.QUEUED: "queued",
    JobStatus.RUNNING: "processing",
    JobStatus.COMPLETED: "completed",
    JobStatus.FAILED: "failed",
    JobStatus.CANCELLED: "cancelled",
}


def _get_job_store():
    from main import job_store
    return job_store


def _get_tool_registry():
    from main import tool_registry
    return tool_registry


def _get_compute_router():
    from main import compute_router
    return compute_router


def _read_receptor_content(target: str) -> tuple[str, str, Optional[str]]:
    """Read receptor PDBQT content for a target. Unchanged."""
    target_cfg = TARGET_CONFIG[target]
    receptor_name = target_cfg["receptor"]
    receptor_path = TARGETS_DIR / receptor_name

    if receptor_path.exists():
        return receptor_path.read_text(), receptor_name, "file"

    raise FileNotFoundError(
        f"Receptor file not found: {receptor_path}. "
        f"Run `python download_targets.py` to fetch protein structures."
    )


def _job_to_status_response(job) -> DockStatusResponse:
    output = job.output or {}
    return DockStatusResponse(
        task_id=job.id,
        status=_STATUS_TO_API.get(job.status, "failed"),
        target=job.input.get("target", ""),
        smiles=job.input.get("smiles", ""),
        affinity_kcal_mol=output.get("affinity_kcal_mol"),
        docked_ligand_pdbqt=output.get("docked_ligand_pdbqt"),
        receptor_pdbqt=output.get("receptor_pdbqt"),
        mode=output.get("mode"),
        # NOTE: "started_at" has always meant "queued/created at" in this
        # API, not "processing began at" — preserving that exact meaning.
        started_at=job.created_at.isoformat() if job.created_at else None,
        finished_at=job.completed_at.isoformat() if job.completed_at else None,
        elapsed_seconds=output.get("elapsed_seconds"),
        error=job.error,
        # Determinism provenance. exhaustiveness falls back to the job input
        # for jobs that failed before the worker recorded it in output.
        exhaustiveness=output.get("exhaustiveness", job.input.get("exhaustiveness")),
        seed=output.get("seed"),
        cpu=output.get("cpu"),
        num_modes=output.get("num_modes"),
        vina_version=output.get("vina_version"),
    )


@router.post("/start", response_model=DockStartResponse)
async def start_docking(payload: DockStartRequest) -> DockStartResponse:
    """
    Queue a docking job and return immediately with a task ID.

    Vina never runs inside this request — a job row is created and the
    LocalWorker process picks it up. If no worker is running, the job will
    simply sit in "queued" until one does (see docs/development/local-worker.md).
    """
    if payload.target not in TARGET_CONFIG:
        supported = ", ".join(sorted(TARGET_CONFIG.keys()))
        raise HTTPException(status_code=400, detail=f"Unsupported target '{payload.target}'. Supported: {supported}")

    try:
        validate_smiles(payload.smiles)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    exhaustiveness = payload.exhaustiveness or int(os.getenv("DOCKING_EXHAUSTIVENESS", "8"))
    task_id = f"dock_{uuid.uuid4().hex[:12]}"

    tool_registry = _get_tool_registry()
    compute_router = _get_compute_router()
    tool = tool_registry.get("run_docking")

    try:
        job = await compute_router.execute(
            tool,
            _job_store=_get_job_store(),
            _job_type="docking",
            _job_input={"smiles": payload.smiles, "target": payload.target, "exhaustiveness": exhaustiveness},
            _job_id=task_id,
        )
    except ComputeRejected as exc:
        raise HTTPException(status_code=503, detail=exc.reason)

    logger.info("job_queued job_id=%s type=docking target=%s", job.id, payload.target)

    return DockStartResponse(
        task_id=job.id,
        status="queued",
        target=payload.target,
        smiles=payload.smiles,
        message=f"Docking task queued (exhaustiveness={exhaustiveness})",
    )


@router.get("/status/{task_id}", response_model=DockStatusResponse)
async def get_docking_status(task_id: str) -> DockStatusResponse:
    """Poll the status/result of a docking task."""
    job_store = _get_job_store()
    job = await job_store.get_job(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    return _job_to_status_response(job)


@router.post("/cancel/{task_id}")
async def cancel_docking(task_id: str) -> dict[str, Any]:
    """
    Cancel a running/queued docking task. Kills the Vina subprocess (running
    in the separate LocalWorker process) via its recorded OS PID.
    """
    job_store = _get_job_store()
    job = await job_store.get_job(task_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
        return {
            "task_id": task_id,
            "cancelled": False,
            "message": f"Task already {_STATUS_TO_API[job.status]}",
        }

    await job_store.cancel_job(task_id)

    if job.worker_pid:
        try:
            os.kill(job.worker_pid, signal.SIGKILL)
            logger.info("Killed Vina subprocess for task_id=%s (pid=%d)", task_id, job.worker_pid)
        except (ProcessLookupError, OSError):
            pass  # already exited

    logger.info("Cancelled docking task: %s", task_id)
    return {
        "task_id": task_id,
        "cancelled": True,
        "message": "Docking task cancelled",
    }


@router.get("/history")
async def get_docking_history() -> list[dict[str, Any]]:
    """Return all docking tasks (most recent first), excluding large PDBQT blobs."""
    job_store = _get_job_store()
    jobs = await job_store.list_jobs(job_type="docking", limit=200)

    history = []
    for job in jobs:  # already ordered most-recent-first by JobStore
        output = job.output or {}
        history.append({
            "task_id": job.id,
            "status": _STATUS_TO_API.get(job.status, "failed"),
            "target": job.input.get("target"),
            "smiles": job.input.get("smiles"),
            "affinity_kcal_mol": output.get("affinity_kcal_mol"),
            "mode": output.get("mode"),
            "exhaustiveness": output.get("exhaustiveness", job.input.get("exhaustiveness")),
            "seed": output.get("seed"),
            "cpu": output.get("cpu"),
            "num_modes": output.get("num_modes"),
            "vina_version": output.get("vina_version"),
            "started_at": job.created_at.isoformat() if job.created_at else None,
            "finished_at": job.completed_at.isoformat() if job.completed_at else None,
            "elapsed_seconds": output.get("elapsed_seconds"),
            "error": job.error,
        })

    return history


@router.get("/receptor/{target}")
async def get_receptor_for_target(target: str) -> dict[str, Any]:
    """Return receptor PDBQT content for frontend 3D overlay. Unchanged — no job involved."""
    target_key = target.strip().lower()
    if target_key not in TARGET_CONFIG:
        supported = ", ".join(sorted(TARGET_CONFIG.keys()))
        raise HTTPException(status_code=400, detail=f"Unsupported target '{target_key}'. Supported: {supported}")

    receptor_pdbqt, receptor_name, source = _read_receptor_content(target_key)
    return {
        "target": target_key,
        "receptor_name": receptor_name,
        "source": source,
        "receptor_pdbqt": receptor_pdbqt,
    }
