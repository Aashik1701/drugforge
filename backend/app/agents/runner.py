"""
AgentRunner — the minimal orchestration loop described in the spec:

    state -> budget check -> tool request -> ToolRegistry -> ComputeRouter
    -> result -> ToolCall -> state update -> repeat

This is deliberately NOT a planner and NOT autonomous. It executes a fixed,
caller-supplied sequence of tool requests, one at a time, checking the
budget before each and recording exactly what happened. No scientific
logic lives here — every tool call goes through ToolRegistry.get() then
ComputeRouter.execute(), the same path routers/dock.py and routers/batch.py
use. AgentRunner never imports or calls ResourceManager, LocalExecutor, or
Vina directly.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Tuple

from compute.router import ComputeRejected, ComputeRouter
from tools.registry import ToolRegistry

from .types import AgentResult, AgentState, RunStatus, ToolCall, ToolCallStatus

logger = logging.getLogger(__name__)

# A single requested call: (tool_name, positional_args, keyword_args)
ToolRequest = Tuple[str, tuple, dict]


class BudgetExhausted(Exception):
    """Raised by call_tool() when state.can_call_tool() is False. No ToolCall
    is recorded for the attempt — per spec: 'no resource is consumed for
    blocked execution.'"""


class AgentRunner:
    def __init__(self, tool_registry: ToolRegistry, compute_router: ComputeRouter) -> None:
        self._tool_registry = tool_registry
        self._compute_router = compute_router

    async def call_tool(self, state: AgentState, tool_name: str, *args: Any, **kwargs: Any) -> ToolCall:
        """
        Attempt exactly one tool call against the shared compute fabric.

        Raises BudgetExhausted (no ToolCall recorded, no tool executed) if
        the run is already at its tool-call ceiling. Otherwise always
        returns a ToolCall, appended to state.tool_calls, whose `status`
        distinguishes success / failed / rejected / unknown_tool — never
        silently converts a failure into a success.
        """
        if not state.can_call_tool():
            raise BudgetExhausted(
                f"run {state.run_id}: {len(state.tool_calls)}/{state.budget.max_tool_calls} tool calls already used"
            )

        # arguments recorded for the audit trail — kept JSON-friendly-ish;
        # objects that don't repr cleanly still show up as *something*.
        call = ToolCall(tool_name=tool_name, arguments={"args": [repr(a) for a in args], "kwargs": dict(kwargs)})

        tool = self._tool_registry.get(tool_name)
        if tool is None:
            call.status = ToolCallStatus.UNKNOWN_TOOL
            call.error = f"No tool registered as '{tool_name}'"
            call.finished_at = call.started_at
            state.tool_calls.append(call)
            state.steps_taken += 1
            logger.warning("agent_tool_call run_id=%s tool=%s status=unknown_tool", state.run_id, tool_name)
            return call

        try:
            result = await self._compute_router.execute(tool, *args, **kwargs)
            call.result = result
            call.status = ToolCallStatus.SUCCESS
        except ComputeRejected as exc:
            call.status = ToolCallStatus.REJECTED
            call.error = exc.reason
        except Exception as exc:  # tool itself raised — never swallow, always record
            call.status = ToolCallStatus.FAILED
            call.error = str(exc)
        finally:
            from datetime import datetime, timezone
            call.finished_at = datetime.now(timezone.utc)
            state.tool_calls.append(call)
            state.steps_taken += 1

        logger.info(
            "agent_tool_call run_id=%s tool=%s status=%s duration_ms=%s",
            state.run_id, tool_name, call.status.value, call.duration_ms,
        )
        return call

    async def run(self, state: AgentState, tool_requests: Iterable[ToolRequest]) -> AgentResult:
        """
        Execute a fixed, deterministic sequence of tool requests in order.

        Stops early (status=BUDGET_EXHAUSTED) the moment the budget is hit —
        does not attempt remaining requests. An individual tool failure or
        rejection does NOT stop the run; it's recorded on that ToolCall and
        the next requested call still proceeds, since each is independent
        and the point of this phase is proving the plumbing works across
        several distinct outcomes in one run, not fail-fast semantics (no
        planner exists yet to decide what "fail fast" should even mean).
        """
        state.status = RunStatus.RUNNING
        logger.info("agent_run_started run_id=%s goal=%r", state.run_id, state.goal)

        for tool_name, args, kwargs in tool_requests:
            try:
                await self.call_tool(state, tool_name, *args, **kwargs)
            except BudgetExhausted:
                state.status = RunStatus.BUDGET_EXHAUSTED
                logger.warning("agent_run_budget_exhausted run_id=%s", state.run_id)
                break
        else:
            state.status = RunStatus.COMPLETED

        logger.info("agent_run_finished run_id=%s status=%s tool_calls=%d",
                     state.run_id, state.status.value, len(state.tool_calls))

        return AgentResult(
            run_id=state.run_id,
            status=state.status,
            output={"tool_calls_made": len(state.tool_calls)},
            tool_calls=state.tool_calls,
        )
