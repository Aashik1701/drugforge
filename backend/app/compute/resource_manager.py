"""
ResourceManager — decides whether a requested computation may run right now.

Does not execute anything itself. ComputeRouter asks can_run() first;
LocalExecutor/JobStore only get called if the answer is (True, "").
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from .policy import ComputeClass, ComputePolicy

logger = logging.getLogger(__name__)


@dataclass
class ResourceDecision:
    allowed: bool
    reason: str = ""


class ResourceManager:
    """
    Stateless with one exception: it needs to know how many docking jobs are
    currently active. That count is supplied by an injected callable rather
    than a hard dependency on JobStore, so this module doesn't need to import
    jobs/ — jobs/ (built in Phase 8-9) wires the real callback in at startup.
    """

    def __init__(
        self,
        policy: ComputePolicy,
        active_docking_count_fn: Optional[Callable[[], Union[int, Awaitable[int]]]] = None,
        max_local_batch_size: int = 100,
    ) -> None:
        self.policy = policy
        self._active_docking_count_fn = active_docking_count_fn or (lambda: 0)
        self.max_local_batch_size = max_local_batch_size

    async def can_run(self, tool_name: str, compute_class: ComputeClass, batch_size: int = 1) -> ResourceDecision:
        """Async because checking active docking-job count reads JobStore."""
        if compute_class in (ComputeClass.LOCAL, ComputeClass.LOCAL_SMALL):
            return self._check_local(tool_name, batch_size)
        if compute_class in (ComputeClass.HEAVY_LOCAL, ComputeClass.REMOTE_CAPABLE):
            return await self._check_heavy(tool_name)
        return ResourceDecision(False, f"Unknown compute class for '{tool_name}': {compute_class}")

    def _check_local(self, tool_name: str, batch_size: int) -> ResourceDecision:
        if batch_size > 1:
            limit = self.max_local_batch_size if not self.policy.allow_large_batches else float("inf")
            if batch_size > limit:
                return ResourceDecision(
                    False,
                    f"Batch size {batch_size} exceeds the local limit of {self.max_local_batch_size} "
                    f"(mode={self.policy.mode.value}); split the request or use a smaller batch.",
                )
        return ResourceDecision(True)

    async def _check_heavy(self, tool_name: str) -> ResourceDecision:
        if not self.policy.allow_docking:
            return ResourceDecision(False, f"Docking is disabled in {self.policy.mode.value} mode")
        active = self._active_docking_count_fn()
        if inspect.isawaitable(active):
            active = await active
        if active >= self.policy.max_docking_jobs:
            return ResourceDecision(
                False,
                f"Docking concurrency limit reached ({active}/{self.policy.max_docking_jobs} active). Try again shortly.",
            )
        return ResourceDecision(True)
