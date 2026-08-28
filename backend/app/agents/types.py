"""
Minimal data shapes for the future agent system. No orchestration logic
lives here — this is just the vocabulary that logging, the DB, and an
eventual orchestrator (see docs/architecture/OVERVIEW.md) will share.

Deliberately NOT included yet: a graph/workflow engine, a planner, retry
logic, or any concrete agent. Add those when an actual agent needs them.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AgentBudget:
    """
    Hard safety ceilings for one agent run (spec §18/§22) — never bypassed,
    never inferred from mode presets. Distinct from ComputePolicy: that
    governs *how* a single tool call executes (local vs. job); this governs
    how much an entire multi-step agent run is allowed to do in total.
    """

    max_candidates: int = 50
    max_docking_jobs: int = 5
    max_steps: int = 30
    max_tool_calls: int = 50
    max_retries: int = 2
    max_concurrent_runs_local: int = 1

    @staticmethod
    def from_env() -> "AgentBudget":
        def _int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default

        return AgentBudget(
            max_candidates=_int("MAX_AGENT_CANDIDATES", 50),
            max_docking_jobs=_int("MAX_AGENT_DOCKING_JOBS", 5),
            max_steps=_int("MAX_AGENT_STEPS", 30),
            max_tool_calls=_int("MAX_AGENT_TOOL_CALLS", 50),
            max_retries=_int("MAX_AGENT_RETRIES", 2),
            max_concurrent_runs_local=_int("MAX_AGENT_RUNS_LOCAL", 1),
        )


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget_exhausted"  # added for AgentRunner (agents/runner.py) —
    # distinct from FAILED: the run stopped cleanly at a safety ceiling, not an error.


class ToolCallStatus(str, Enum):
    """Added for AgentRunner — lets a ToolCall distinguish *why* it didn't
    succeed, per the explicit requirement to tell these apart (tool failed
    vs. tool rejected vs. unknown tool), not just "error is set/unset"."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"        # ComputeRejected from ComputeRouter/ResourceManager
    UNKNOWN_TOOL = "unknown_tool"


@dataclass
class ToolCall:
    """One invocation of a tool from the ToolRegistry, for the audit trail."""

    tool_name: str
    arguments: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    status: ToolCallStatus = ToolCallStatus.SUCCESS
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds() * 1000


@dataclass
class AgentState:
    """
    Mutable state carried through a single agent run.

    budget is checked by the (future) agent loop before every tool call and
    every new candidate/step — see docs/architecture/compute-fabric.md for
    the intended "cheap first, expensive last" funnel this exists to bound.
    """

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: str = ""
    context: Dict[str, Any] = field(default_factory=dict)
    tool_calls: List[ToolCall] = field(default_factory=list)
    status: RunStatus = RunStatus.PENDING
    budget: AgentBudget = field(default_factory=AgentBudget.from_env)
    candidates_generated: int = 0
    docking_jobs_submitted: int = 0
    steps_taken: int = 0
    retries_used: int = 0

    def can_take_step(self) -> bool:
        return self.steps_taken < self.budget.max_steps

    def can_call_tool(self) -> bool:
        return len(self.tool_calls) < self.budget.max_tool_calls

    def can_submit_docking_job(self) -> bool:
        return self.docking_jobs_submitted < self.budget.max_docking_jobs

    def can_generate_candidate(self) -> bool:
        return self.candidates_generated < self.budget.max_candidates

    def can_retry(self) -> bool:
        return self.retries_used < self.budget.max_retries


@dataclass
class AgentRun:
    """A started agent execution — what gets persisted/logged."""

    run_id: str
    agent_name: str
    goal: str
    status: RunStatus
    started_at: datetime
    finished_at: Optional[datetime] = None


@dataclass
class AgentResult:
    """The outcome of a finished agent run."""

    run_id: str
    status: RunStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
