"""
Worker interface — what ComputeRouter/JobStore depend on, never a concrete
implementation. LocalWorker (Phase 11) is the only implementation today.
RemoteWorker/GPUWorker are future implementations of this same interface;
nothing outside a worker module needs to change when one is added.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from jobs.models import Job


class Worker(ABC):
    @abstractmethod
    async def submit(self, job: Job) -> None:
        """Hand a job to this worker. LocalWorker: no-op, it polls the store itself."""
        raise NotImplementedError

    @abstractmethod
    async def status(self, job_id: str) -> Job:
        raise NotImplementedError

    @abstractmethod
    async def cancel(self, job_id: str) -> None:
        raise NotImplementedError
