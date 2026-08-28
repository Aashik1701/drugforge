"""
Job — the generic unit of asynchronous work (docking today; any future
HEAVY_LOCAL/REMOTE_CAPABLE tool later).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    type: str
    input: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.QUEUED
    priority: int = 0
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    worker_id: Optional[str] = None
    execution_location: str = "local"
    retry_count: int = 0
    # Implementation detail beyond the spec's base field list: the OS PID of
    # a running subprocess (e.g. Vina), so a /cancel request arriving in a
    # different process than the one running the job can kill it directly.
    worker_pid: Optional[int] = None
