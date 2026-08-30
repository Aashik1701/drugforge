"""
Pydantic envelopes for the agent service (POST/GET /api/agent/*).

The agent's semantics live in agents/types.py (AgentState/AgentBudget/ToolCall);
these schemas only cover the HTTP request/response shell.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AgentToolRequest(BaseModel):
    """One entry in the ordered sequence the caller supplies."""

    name: str = Field(..., min_length=1, description="A registered tool name (see GET /api/agent/tools).")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments for the tool, as JSON.")


class AgentBudgetRequest(BaseModel):
    """Optional per-request budget. Every value is CLAMPED to the server
    ceiling (min()); a value above the ceiling is reported back, not honoured,
    and never rejected. Omitted fields use the ceiling."""

    # extra="forbid": a request that tries to set max_concurrent_runs_local (or
    # any non-clampable knob) gets a clear 422, never a silently ignored raise.
    model_config = ConfigDict(extra="forbid")

    max_tool_calls: Optional[int] = Field(None, ge=1)
    max_docking_jobs: Optional[int] = Field(None, ge=1)
    max_steps: Optional[int] = Field(None, ge=1)
    max_candidates: Optional[int] = Field(None, ge=1)
    max_retries: Optional[int] = Field(None, ge=1)


class AgentRunRequest(BaseModel):
    goal: str = Field("", description="Free-text label for the run (not interpreted).")
    requests: list[AgentToolRequest] = Field(
        ..., min_length=1, description="Ordered tool sequence. No planner -- executed as given."
    )
    budget: Optional[AgentBudgetRequest] = None


class AgentRunAccepted(BaseModel):
    run_id: str
    status: str
    accepted_steps: int
    heavy_steps: int
    budget: dict[str, Any]
    message: str
