"""
LocalWorker — polls JobStore for queued docking jobs and executes them via
docking_worker. Runs as a separate OS process from uvicorn.

Run (from backend/app/, same convention as `cd app && uvicorn main:app` —
see backend/render.yaml and docs/development/local-worker.md):

    cd backend/app
    ../venv/bin/python -m jobs.workers.local_worker

Respects MAX_DOCKING_CONCURRENT via an asyncio.Semaphore — never spawns more
concurrent Vina subprocesses than configured (default 1).
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from jobs.models import JobStatus
from jobs.store import JobStore
from jobs.workers import docking_worker
from utils.vina_env import probe_vina

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("local_worker")

WORKER_ID = f"local-{uuid.uuid4().hex[:8]}"
POLL_INTERVAL_SECONDS = float(os.getenv("WORKER_POLL_INTERVAL_SECONDS", "2"))
DOCKING_TIMEOUT_SECONDS = int(os.getenv("DOCKING_TIMEOUT_SECONDS", "600"))
MAX_DOCKING_CONCURRENT = int(os.getenv("MAX_DOCKING_CONCURRENT", "1"))


async def _process_job(job, store: JobStore) -> None:
    logger.info("job_running job_id=%s type=%s worker_id=%s", job.id, job.type, WORKER_ID)
    t0 = time.perf_counter()
    try:
        result = await docking_worker.run_docking_job(
            job_id=job.id,
            smiles=job.input.get("smiles", ""),
            target=job.input.get("target", ""),
            exhaustiveness=job.input.get("exhaustiveness") or 8,
            store=store,
            seed=job.input.get("seed"),
            conformer_seed=job.input.get("conformer_seed"),
        )
        current = await store.get_job(job.id)
        if current and current.status == JobStatus.CANCELLED:
            logger.info("job_cancelled_during_run job_id=%s", job.id)
            return
        elapsed = round(time.perf_counter() - t0, 3)
        result["elapsed_seconds"] = elapsed
        await store.update_job(
            job.id, status=JobStatus.COMPLETED, output=result,
            completed_at=datetime.now(timezone.utc),
        )
        logger.info("job_completed job_id=%s elapsed_s=%s", job.id, elapsed)
    except Exception as exc:
        current = await store.get_job(job.id)
        if current and current.status == JobStatus.CANCELLED:
            logger.info("job_cancelled_during_run job_id=%s", job.id)
            return
        elapsed = round(time.perf_counter() - t0, 3)
        logger.exception("job_failed job_id=%s elapsed_s=%s", job.id, elapsed)
        await store.update_job(
            job.id, status=JobStatus.FAILED, error=str(exc),
            output={"elapsed_seconds": elapsed},
            completed_at=datetime.now(timezone.utc),
        )


async def main() -> None:
    store = JobStore()
    recovered = await store.recover_stale_running(timeout_seconds=DOCKING_TIMEOUT_SECONDS)
    logger.info(
        "worker_started worker_id=%s max_concurrent=%d poll_interval_s=%s recovered_stale=%d",
        WORKER_ID, MAX_DOCKING_CONCURRENT, POLL_INTERVAL_SECONDS, recovered,
    )

    # One-time Vina preflight. Informational only — the worker keeps polling
    # even if Vina is missing/broken; each docking job then fails fast with a
    # real error (docking_worker raises), never a fake success.
    probe = probe_vina()
    if probe.available:
        logger.info(
            "vina_preflight status=ok path=%s version=%s", probe.path, probe.version,
        )
    else:
        logger.warning(
            "vina_preflight status=unavailable path=%s error=%s", probe.path, probe.error,
        )
        logger.warning(
            "vina_preflight docking jobs WILL FAIL until this is fixed "
            "(worker still running; failure is per-job, not a crash)"
        )

    semaphore = asyncio.Semaphore(MAX_DOCKING_CONCURRENT)
    in_flight: set[asyncio.Task] = set()

    async def _run_with_semaphore(job) -> None:
        async with semaphore:
            await _process_job(job, store)

    while True:
        # Only claim a new job if we have concurrency budget available —
        # avoids claiming work we can't start yet.
        if semaphore.locked() and len(in_flight) >= MAX_DOCKING_CONCURRENT:
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
        else:
            job = await store.claim_next_queued("docking", WORKER_ID)
            if job is None:
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            else:
                task = asyncio.create_task(_run_with_semaphore(job))
                in_flight.add(task)
                task.add_done_callback(in_flight.discard)

        in_flight = {t for t in in_flight if not t.done()}


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_stopped worker_id=%s (KeyboardInterrupt)", WORKER_ID)
