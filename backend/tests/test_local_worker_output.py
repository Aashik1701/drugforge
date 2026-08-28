"""
Regression tests for the LocalWorker pipe-deadlock.

The bug: `funnel.fabric.local_worker_process` used to spawn the LocalWorker with
`stdout=subprocess.PIPE` and never drain it. The worker is chatty (per-job logs
+ meeko/RDKit warnings + tracebacks on failed jobs); once cumulative output
exceeded the ~64 KB OS pipe buffer the worker's next `write()` blocked forever,
freezing the whole run. It surfaced only under sustained multi-job load — a
short run finished before the buffer filled.

Two guards:
  1. static  — `local_worker_process` must not pipe worker stdout into an
     unread PIPE (catches a straight file -> PIPE reversion).
  2. behavioural — hammer a real LocalWorker with enough failing jobs to emit
     well past 64 KB and assert it keeps draining the queue and stays alive.
"""

from __future__ import annotations

import asyncio
import inspect
import subprocess
import sys
import time
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

VINA_BIN = APP_DIR.parent / "bin" / "vina"


# ---------------------------------------------------------------------------
# 1. static guard
# ---------------------------------------------------------------------------
def test_local_worker_process_does_not_pipe_worker_output():
    from funnel import fabric

    src = inspect.getsource(fabric.local_worker_process)
    assert "subprocess.PIPE" not in src, (
        "local_worker_process must send the worker's stdout to a FILE, not an "
        "unread subprocess.PIPE — an undrained pipe buffer deadlocks the worker "
        "under sustained load."
    )
    assert "stdout=log_fh" in src and "open(" in src, (
        "expected the worker subprocess stdout to be redirected to an open file"
    )


# ---------------------------------------------------------------------------
# helper: a subprocess emitting > buffer_size to a redirected file must not block
# ---------------------------------------------------------------------------
def test_high_volume_child_stdout_to_file_does_not_block(tmp_path):
    """The generic condition behind the deadlock, isolated: a child that writes
    far more than the pipe buffer completes fine when stdout is a file."""
    log = tmp_path / "child.log"
    payload_lines = 40_000  # ~1.6 MB, ~25x the pipe buffer
    code = f"import sys\nfor _ in range({payload_lines}): sys.stdout.write('x' * 40 + chr(10))\n"
    with open(log, "w") as fh:
        proc = subprocess.Popen([sys.executable, "-c", code], stdout=fh,
                                stderr=subprocess.STDOUT, text=True)
        rc = proc.wait(timeout=30)
    assert rc == 0
    assert log.stat().st_size > 1_000_000


# ---------------------------------------------------------------------------
# 2. behavioural: real LocalWorker under sustained load
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not VINA_BIN.exists(),
                    reason="needs backend/bin/vina (scripts/setup_vina.sh)")
def test_local_worker_survives_sustained_job_load(tmp_path, monkeypatch):
    """
    Queue enough docking jobs to push worker output well past the 64 KB pipe
    buffer, and confirm the worker drains every one and is still responsive.
    Uses invalid SMILES so each job fails fast (no real Vina search) but still
    logs a full traceback from local_worker._process_job — that is the output
    volume that used to deadlock the pipe.
    """
    monkeypatch.setenv("COMPUTE_MODE", "balanced")
    monkeypatch.setenv("WORKER_POLL_INTERVAL_SECONDS", "0.1")  # keep the test quick
    job_db = tmp_path / "jobs.db"
    monkeypatch.setenv("JOB_STORE_PATH", str(job_db))

    from jobs.store import JobStore
    from jobs.models import JobStatus
    from funnel.fabric import local_worker_process

    store = JobStore(db_path=job_db)

    N = 45  # each failed job logs a full traceback (~3 KB); 45 => well past 64 KB
    worker_log = tmp_path / "worker.log"

    async def _drive():
        ids = []
        for i in range(N):
            job = await store.create_job(
                "docking",
                {"smiles": f"not-a-real-smiles-{i}", "target": "cox2",
                 "exhaustiveness": 8, "seed": 1, "conformer_seed": 42},
            )
            ids.append(job.id)

        deadline = time.time() + 90
        pending = set(ids)
        while pending and time.time() < deadline:
            await asyncio.sleep(1.0)
            done = set()
            for jid in pending:
                j = await store.get_job(jid)
                if j and j.status in (JobStatus.FAILED, JobStatus.COMPLETED,
                                      JobStatus.CANCELLED):
                    done.add(jid)
            pending -= done
        return pending

    with local_worker_process({"JOB_STORE_PATH": str(job_db),
                               "COMPUTE_MODE": "balanced"},
                              log_path=str(worker_log)) as proc:
        still_pending = asyncio.new_event_loop().run_until_complete(_drive())
        worker_alive = proc.poll() is None

    assert not still_pending, (
        f"{len(still_pending)}/{N} jobs never reached a terminal state — the "
        f"worker likely deadlocked on its output stream"
    )
    assert worker_alive, "worker process died during the run"
    # And it really did produce output past the danger threshold:
    assert worker_log.stat().st_size > 64 * 1024, (
        f"worker only emitted {worker_log.stat().st_size} B — test did not "
        f"actually exercise the >64 KB condition"
    )
