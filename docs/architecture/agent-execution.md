# Agent Execution (minimal loop — no autonomy yet)

`backend/app/agents/runner.py`. This is orchestration, not intelligence:
`AgentRunner.run()` executes a fixed, caller-supplied sequence of tool
requests, one at a time. There is no planner, no LLM, no decision-making
about *which* tool to call next — that's explicitly future work. What this
proves is that the plumbing between an agent-shaped caller and the already-
verified compute fabric (`docs/architecture/compute-fabric.md`) actually
works, end to end, for both cheap and heavy tools.

## The path — no exceptions

```
AgentRunner.call_tool(state, tool_name, *args, **kwargs)
        │
        ▼
state.can_call_tool()  ── False ──▶ raise BudgetExhausted (no ToolCall recorded)
        │ True
        ▼
tool_registry.get(tool_name)  ── None ──▶ ToolCall(status=UNKNOWN_TOOL)
        │ found
        ▼
compute_router.execute(tool, *args, **kwargs)
        │
   ┌────┴─────────────────────────┐
   ▼                               ▼
ComputeRejected                 success / tool's own exception
(ResourceManager said no)              │
   │                                   ▼
   ▼                          ToolCall(status=SUCCESS, result=...)
ToolCall(status=REJECTED)     or ToolCall(status=FAILED, error=...)
```

`AgentRunner` imports `ToolRegistry` and `ComputeRouter` only. It never
imports `ResourceManager`, `LocalExecutor`, `JobStore`, or anything
Vina-related — verified by grep, not just by intent:

```bash
grep -n "^from\|^import" backend/app/agents/runner.py
# compute.router (ComputeRejected, ComputeRouter), tools.registry (ToolRegistry) — nothing else
```

## Lightweight vs. heavy tools — identical call shape

```python
# LOCAL tool — runs immediately, result is the real return value
await runner.call_tool(state, "parse_smiles", "CCO")

# HEAVY_LOCAL tool (docking) — same call shape, extra kwargs the caller
# already needs to know about (same ones routers/dock.py passes) — the
# agent doesn't need special-case logic, it just forwards what it's given
await runner.call_tool(
    state, "run_docking", None, None,
    _job_store=job_store, _job_type="docking",
    _job_input={"smiles": "CCO", "target": "cox2"},
)
```

Both return a `ToolCall`. For the heavy case, `ToolCall.result` is a `Job`
dataclass (`status="queued"`) — never a docking score. Verified live: an
agent's `run_docking` call in battery-saver mode gets `status=REJECTED`
straight from the real `ResourceManager` (not mocked — the rejection log
line comes from `compute.router`'s own logger); the same call in balanced
mode gets `status=SUCCESS` with a real queued `Job`, and the call itself
takes under 2ms — the agent process is never blocked waiting on Vina or a
worker, by construction (same architectural guarantee proven in the
compute-fabric hardening pass, now proven again from the agent's calling
convention specifically).

## Budget

`AgentState.can_call_tool()` (unchanged, from `agents/types.py`) is
checked *before* every attempted call. If it returns `False`,
`call_tool()` raises `BudgetExhausted` and — this is the important part —
**no `ToolCall` is appended**. A blocked attempt isn't an invocation; the
audit trail only records things that actually happened (executed,
rejected, failed, or unknown-tool — all real outcomes). `AgentRunner.run()`
catches `BudgetExhausted` and sets `state.status = RunStatus.BUDGET_EXHAUSTED`
(new enum value — didn't exist before this phase; extending `RunStatus`
was the minimal necessary change, not a redesign).

Verified: `AgentBudget(max_tool_calls=2)` with 3 requested calls executes
exactly 2, the 3rd never touches `ToolRegistry` or `ComputeRouter` at all,
and `len(result.tool_calls) == 2` — not 3 with an error, exactly 2.

## Failure taxonomy

New `ToolCallStatus` enum (`agents/types.py`) — the other minimal, spec-
justified extension this phase made:

| Status | Meaning | Who decides |
|---|---|---|
| `SUCCESS` | Tool ran, returned normally | — |
| `FAILED` | Tool's own code raised | the tool |
| `REJECTED` | `ComputeRejected` from ComputeRouter | ResourceManager, via ComputeRouter |
| `UNKNOWN_TOOL` | No such tool in ToolRegistry | AgentRunner, before ComputeRouter is even reached |

`AgentRunner.run()` does **not** stop on `FAILED`/`REJECTED`/`UNKNOWN_TOOL`
— only on `BUDGET_EXHAUSTED`. Each requested call is independent; there's
no planner yet to decide "should I stop because step 2 failed," so the
loop keeps going and lets the caller inspect `AgentResult.tool_calls`
afterward. This is a deliberate, documented choice, not an oversight —
revisit when an actual planner exists and has an opinion about it.

## What was added vs. reused

**Reused as-is, no changes:** `AgentState`, `AgentBudget`, `AgentRun`,
`AgentResult`, `ToolRegistry`, `ComputeRouter`, `ComputePolicy`,
`ResourceManager`, `JobStore`.

**Extended (justified, minimal):**
- `RunStatus` gained `BUDGET_EXHAUSTED` — no existing value could represent "stopped cleanly at a safety ceiling, not an error."
- `ToolCall` gained `status: ToolCallStatus` and a computed `duration_ms` property — the spec explicitly asked for these two fields; previously the only signal was `error is None`, which couldn't distinguish rejected/unknown-tool/failed from each other.

**New:** `agents/runner.py` (`AgentRunner`, `BudgetExhausted`) — the only new module this phase added.

## A real bug this phase's testing caught (not agent-specific, but found here)

`JobStore`'s SQLite file (`backend/app/jobs/jobs.db`) is shared across the
dev server, manual `curl` testing, and every pytest invocation. A queued
job left over from any of those silently occupied the one
`MAX_DOCKING_CONCURRENT` slot and broke unrelated docking tests — but only
on a *second* pytest run, since the first run always started from an empty
file. Running the suite 3× in a row without cleanup between runs is what
surfaced it. Fixed in `conftest.py`: the DB is wiped at the start of every
test session now. This benefits the whole suite, not just the new agent
tests — flagging it here because it was found while building this phase,
not because it's conceptually agent-related.

## What's explicitly NOT here

No `/api/agent/runs` endpoint — nothing calls `AgentRunner` outside tests
yet, and the spec was explicit: don't build the endpoint for architectural
aesthetics before something needs it. No planner, no LLM, no tool
selection logic, no candidate generation, no funnel implementation (the
funnel is still just documentation in `compute-fabric.md` — this phase
proved the loop that a funnel-following planner would eventually drive).
