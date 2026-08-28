"""
AgentRunner tests — the minimal execution loop (agents/runner.py) on top of
the already-verified compute fabric (ToolRegistry -> ComputeRouter ->
ResourceManager). No LLM, no planner: every test drives a fixed, explicit
sequence of tool requests and checks what AgentRunner actually did.

Run with: cd backend && python -m pytest tests/ -v
"""

import pytest
import pytest_asyncio

from agents import AgentBudget, AgentRunner, AgentState, BudgetExhausted, RunStatus, ToolCallStatus
from compute.policy import ComputeMode, ComputePolicy
from schemas.molecule import MoleculeInput


@pytest_asyncio.fixture
async def runner():
    """
    Uses the app's real singletons (main.tool_registry / main.compute_router),
    already populated by the session-scoped lifespan fixture in conftest.py —
    same models, same registry, same router every other test suite uses.
    """
    import main
    yield AgentRunner(main.tool_registry, main.compute_router)


@pytest_asyncio.fixture(autouse=True)
async def _reset_compute_mode():
    """Every test starts from a known mode and restores it after."""
    import main
    yield
    main.compute_policy = ComputePolicy.preset(ComputeMode.BATTERY_SAVER)
    main.resource_manager.policy = main.compute_policy


# ── One / sequential tool calls ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_tool_call(runner: AgentRunner):
    state = AgentState(goal="single call")
    result = await runner.run(state, [("parse_smiles", ("CCO",), {})])
    assert result.status == RunStatus.COMPLETED
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].status == ToolCallStatus.SUCCESS


@pytest.mark.asyncio
async def test_two_sequential_tool_calls(runner: AgentRunner):
    state = AgentState(goal="two calls")
    result = await runner.run(state, [
        ("parse_smiles", ("CCO",), {}),
        ("calculate_descriptors", ("CCO",), {}),
    ])
    assert result.status == RunStatus.COMPLETED
    assert len(result.tool_calls) == 2
    assert all(tc.status == ToolCallStatus.SUCCESS for tc in result.tool_calls)


@pytest.mark.asyncio
async def test_three_sequential_calls_including_a_prediction(runner: AgentRunner):
    """The deterministic scenario from the spec: parse -> descriptors -> ADMET prediction."""
    state = AgentState(goal="characterize ethanol")
    result = await runner.run(state, [
        ("parse_smiles", ("CCO",), {}),
        ("calculate_descriptors", ("CCO",), {}),
        ("predict_solubility", (MoleculeInput(smiles="CCO"),), {}),
    ])
    assert result.status == RunStatus.COMPLETED
    assert len(result.tool_calls) == 3
    assert all(tc.status == ToolCallStatus.SUCCESS for tc in result.tool_calls)
    assert result.tool_calls[2].result.prediction is not None  # a real predicted value, not None/mocked


# ── Budget ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_budget_exhaustion_blocks_excess_calls(runner: AgentRunner):
    state = AgentState(goal="budget test", budget=AgentBudget(max_tool_calls=2))
    result = await runner.run(state, [
        ("parse_smiles", ("CCO",), {}),
        ("parse_smiles", ("c1ccccc1",), {}),
        ("parse_smiles", ("CC(=O)O",), {}),  # must never execute
    ])
    assert result.status == RunStatus.BUDGET_EXHAUSTED
    assert len(result.tool_calls) == 2  # the 3rd was blocked, not recorded as a failure


@pytest.mark.asyncio
async def test_call_tool_raises_when_budget_already_exhausted(runner: AgentRunner):
    state = AgentState(goal="already at limit", budget=AgentBudget(max_tool_calls=0))
    with pytest.raises(BudgetExhausted):
        await runner.call_tool(state, "parse_smiles", "CCO")
    assert len(state.tool_calls) == 0  # no resource consumed, no record created


# ── Failure handling ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_tool(runner: AgentRunner):
    state = AgentState(goal="unknown tool")
    result = await runner.run(state, [("this_tool_does_not_exist", (), {})])
    assert result.tool_calls[0].status == ToolCallStatus.UNKNOWN_TOOL
    assert "not registered" in "" or "No tool registered" in result.tool_calls[0].error


@pytest.mark.asyncio
async def test_tool_execution_failure_is_recorded_not_swallowed(runner: AgentRunner):
    state = AgentState(goal="invalid input")
    result = await runner.run(state, [("parse_smiles", ("NOT_A_VALID_SMILES!!!",), {})])
    tc = result.tool_calls[0]
    assert tc.status == ToolCallStatus.FAILED
    assert tc.error is not None
    assert tc.result is None  # never converted into a fake success


@pytest.mark.asyncio
async def test_run_continues_past_individual_failures(runner: AgentRunner):
    """One failed/unknown call doesn't abort the whole run — only budget does."""
    state = AgentState(goal="mixed outcomes")
    result = await runner.run(state, [
        ("parse_smiles", ("garbage!!!",), {}),
        ("no_such_tool", (), {}),
        ("parse_smiles", ("CCO",), {}),
    ])
    assert result.status == RunStatus.COMPLETED
    assert [tc.status for tc in result.tool_calls] == [
        ToolCallStatus.FAILED, ToolCallStatus.UNKNOWN_TOOL, ToolCallStatus.SUCCESS,
    ]


# ── Resource rejection (proves real ComputeRouter/ResourceManager routing) ──

@pytest.mark.asyncio
async def test_resource_rejection_travels_through_real_compute_router(runner: AgentRunner):
    """
    Docking is disabled by default (battery-saver). This is NOT mocked at
    the AgentRunner level — the rejection comes from the actual
    ResourceManager.can_run() call inside ComputeRouter.execute().
    """
    state = AgentState(goal="docking while disabled")
    result = await runner.run(state, [("run_docking", (None, None), {})])
    tc = result.tool_calls[0]
    assert tc.status == ToolCallStatus.REJECTED
    assert "battery-saver" in tc.error


# ── Heavy tool / job submission path (no Vina required) ─────────────────

@pytest.mark.asyncio
async def test_heavy_tool_returns_queued_job_without_blocking(runner: AgentRunner):
    """
    With docking enabled, the agent's run_docking call must return a real
    Job record (status=queued) — not a docking score, not a mock, and the
    call itself must be fast (proves the agent process never waits on Vina).
    """
    import main
    import time
    main.compute_policy = ComputePolicy.preset(ComputeMode.BALANCED)
    main.resource_manager.policy = main.compute_policy

    state = AgentState(goal="submit docking job")
    t0 = time.perf_counter()
    result = await runner.run(state, [
        ("run_docking", (None, None), {
            "_job_store": main.job_store,
            "_job_type": "docking",
            "_job_input": {"smiles": "CCO", "target": "cox2", "exhaustiveness": 8},
        }),
    ])
    elapsed = time.perf_counter() - t0

    tc = result.tool_calls[0]
    assert tc.status == ToolCallStatus.SUCCESS
    assert tc.result.status.value == "queued"
    assert tc.result.id is not None
    assert elapsed < 1.0  # did not block waiting on Vina/a worker

    # JobStore is a real shared SQLite file across the whole test session —
    # an uncancelled queued job here would occupy the one concurrency slot
    # and break every docking test that runs after this one.
    await main.job_store.cancel_job(tc.result.id)
