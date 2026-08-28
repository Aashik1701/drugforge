"""
ComputeRouter — the single place that decides where a tool call executes.

Route handlers call `compute_router.execute(tool_name, *args, **kwargs)`
instead of branching on tool type themselves. This is the centralization
point called for in the spec ("do not scatter `if docking: ...` throughout
the codebase").
"""

from __future__ import annotations

import logging
from typing import Any

from .local_executor import LocalExecutor
from .policy import ComputeClass, ComputePolicy
from .resource_manager import ResourceManager, ResourceDecision

logger = logging.getLogger(__name__)


class ComputeRejected(Exception):
    """Raised when ResourceManager denies execution. Callers map this to a 4xx."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class ComputeRouter:
    def __init__(self, policy: ComputePolicy, resource_manager: ResourceManager) -> None:
        self.policy = policy
        self.resource_manager = resource_manager
        self.local_executor = LocalExecutor(max_concurrent=resource_manager.policy.max_local_jobs)

    async def execute(self, tool, *args: Any, batch_size: int = 1, **kwargs: Any) -> Any:
        """
        tool: a tools.registry.Tool instance (already looked up by the caller
        via ToolRegistry.get()).

        LOCAL/LOCAL_SMALL -> runs immediately in-process, returns the result.
        HEAVY_LOCAL/REMOTE_CAPABLE -> enqueues a Job and returns the Job
        record (queued) — the caller (a route handler) turns that into the
        existing {"task_id", "status"} response shape.
        """
        decision: ResourceDecision = await self.resource_manager.can_run(tool.name, tool.compute_class, batch_size)
        if not decision.allowed:
            logger.warning("compute_rejected tool=%s reason=%s", tool.name, decision.reason)
            raise ComputeRejected(decision.reason)

        if tool.compute_class in (ComputeClass.LOCAL, ComputeClass.LOCAL_SMALL):
            return await self.local_executor.run(tool, *args, **kwargs)

        # HEAVY_LOCAL / REMOTE_CAPABLE -> job queue. Lazy import: jobs/ is a
        # separate package built alongside compute/ — this keeps compute/
        # importable on its own without a hard circular dependency.
        from jobs.store import JobStore

        job_store: JobStore = kwargs.pop("_job_store")
        job_type = kwargs.pop("_job_type", tool.name)
        job_input = kwargs.pop("_job_input", {})
        job_id = kwargs.pop("_job_id", None)
        job = await job_store.create_job(job_type=job_type, job_input=job_input, job_id=job_id)
        logger.info("job_queued job_id=%s tool=%s", job.id, tool.name)
        return job
