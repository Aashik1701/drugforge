"""
JobStore — persists Job records.

Backed by a local SQLite file (stdlib `sqlite3`, zero new dependency) rather
than Supabase. This is a deliberate deviation from "use the existing
Supabase integration" (see docs/architecture/compute-fabric.md for the full
reasoning): Supabase is optional and already degrades gracefully everywhere
else in this app (predictions still work with it unset). Job state is
explicitly required to "survive API restarts" (spec §13/§48) — making that
depend on an external service the app is designed to run without would
contradict the "$0 infrastructure, fully local" mandate. SQLite gives real
restart-survival with zero configuration. Supabase's `predictions` table is
untouched; this does not replace or migrate anything.

Async methods wrap synchronous sqlite3 calls via asyncio.to_thread so the
event loop is never blocked, even though each call is fast (local file).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .models import Job, JobStatus

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "jobs.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    input TEXT NOT NULL,
    output TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    worker_id TEXT,
    execution_location TEXT NOT NULL DEFAULT 'local',
    retry_count INTEGER NOT NULL DEFAULT 0,
    worker_pid INTEGER
);
"""


def _row_to_job(row: sqlite3.Row) -> Job:
    return Job(
        id=row["id"],
        type=row["type"],
        status=JobStatus(row["status"]),
        priority=row["priority"],
        input=json.loads(row["input"]) if row["input"] else {},
        output=json.loads(row["output"]) if row["output"] else None,
        error=row["error"],
        created_at=datetime.fromisoformat(row["created_at"]),
        started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
        completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        worker_id=row["worker_id"],
        execution_location=row["execution_location"],
        retry_count=row["retry_count"],
        worker_pid=row["worker_pid"],
    )


class JobStore:
    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or Path(os.getenv("JOB_STORE_PATH", str(DEFAULT_DB_PATH)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    # ------------------------------------------------------------------
    # Sync implementations (run off the event loop via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _create_job_sync(self, job: Job) -> Job:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO jobs
                   (id, type, status, priority, input, output, error,
                    created_at, started_at, completed_at, worker_id,
                    execution_location, retry_count, worker_pid)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job.id, job.type, job.status.value, job.priority,
                    json.dumps(job.input), None, None,
                    job.created_at.isoformat(), None, None, None,
                    job.execution_location, job.retry_count, None,
                ),
            )
        return job

    def _get_job_sync(self, job_id: str) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None

    def _update_job_sync(self, job_id: str, **fields) -> Optional[Job]:
        if not fields:
            return self._get_job_sync(job_id)
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = []
        for k, v in fields.items():
            if k == "status" and isinstance(v, JobStatus):
                v = v.value
            elif k in ("output",) and v is not None:
                v = json.dumps(v)
            elif k in ("started_at", "completed_at") and isinstance(v, datetime):
                v = v.isoformat()
            values.append(v)
        values.append(job_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", values)
        return self._get_job_sync(job_id)

    def _list_jobs_sync(self, job_type: Optional[str] = None, limit: int = 100) -> List[Job]:
        query = "SELECT * FROM jobs"
        params: tuple = ()
        if job_type:
            query += " WHERE type = ?"
            params = (job_type,)
        query += " ORDER BY created_at DESC LIMIT ?"
        params = params + (limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_job(r) for r in rows]

    def _count_active_sync(self, job_type: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as c FROM jobs WHERE type = ? AND status IN ('queued', 'running')",
                (job_type,),
            ).fetchone()
        return row["c"] if row else 0

    def _claim_job_sync(self, job_id: str, worker_id: str) -> Optional[Job]:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ?, worker_id = ?, started_at = ? "
                "WHERE id = ? AND status = ?",
                (JobStatus.RUNNING.value, worker_id, datetime.now(timezone.utc).isoformat(),
                 job_id, JobStatus.QUEUED.value),
            )
            if cur.rowcount == 0:
                return None
        return self._get_job_sync(job_id)

    def _claim_next_queued_sync(self, job_type: str, worker_id: str) -> Optional[Job]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE type = ? AND status = ? "
                "ORDER BY priority DESC, created_at ASC LIMIT 1",
                (job_type, JobStatus.QUEUED.value),
            ).fetchone()
        if not row:
            return None
        return self._claim_job_sync(row["id"], worker_id)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def create_job(self, job_type: str, job_input: dict, priority: int = 0, job_id: Optional[str] = None) -> Job:
        job = Job(type=job_type, input=job_input, priority=priority)
        if job_id:
            job.id = job_id
        return await asyncio.to_thread(self._create_job_sync, job)

    async def get_job(self, job_id: str) -> Optional[Job]:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    async def update_job(self, job_id: str, **fields) -> Optional[Job]:
        return await asyncio.to_thread(self._update_job_sync, job_id, **fields)

    async def list_jobs(self, job_type: Optional[str] = None, limit: int = 100) -> List[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, job_type, limit)

    async def count_active(self, job_type: str) -> int:
        return await asyncio.to_thread(self._count_active_sync, job_type)

    async def claim_next_queued(self, job_type: str, worker_id: str) -> Optional[Job]:
        return await asyncio.to_thread(self._claim_next_queued_sync, job_type, worker_id)

    async def cancel_job(self, job_id: str, reason: str = "Cancelled by user") -> Optional[Job]:
        job = await self.get_job(job_id)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return job
        return await self.update_job(
            job_id, status=JobStatus.CANCELLED, error=reason, completed_at=datetime.now(timezone.utc)
        )

    async def recover_stale_running(self, timeout_seconds: int) -> int:
        """
        Practical restart recovery (spec §14/§48): any job still 'running'
        older than timeout_seconds when a worker starts is presumed dead
        (the process that owned it is gone) and marked failed. Not
        distributed fault tolerance — just "don't leave zombie rows."
        """
        cutoff = datetime.now(timezone.utc).timestamp() - timeout_seconds
        jobs = await self.list_jobs(limit=1000)
        recovered = 0
        for job in jobs:
            if job.status == JobStatus.RUNNING and job.started_at:
                if job.started_at.timestamp() < cutoff:
                    await self.update_job(
                        job.id, status=JobStatus.FAILED,
                        error="Recovered as failed on worker restart (was still 'running' past timeout)",
                        completed_at=datetime.now(timezone.utc),
                    )
                    recovered += 1
        if recovered:
            logger.warning("job_recovery recovered_count=%d", recovered)
        return recovered
