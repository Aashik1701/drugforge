# AgentRunner as a backend service

Wires `backend/app/agents/runner.py` (present since Pass 3, called only by
tests) to HTTP. **This pass exposes `AgentRunner` / `AgentState` / `AgentBudget`
/ `ToolCall`; it does not change their semantics. No LLM, no planner — the tool
sequence is supplied by the caller.** Phase 4 replaces the caller with a
planner; the seam it plugs into is the request body of `POST /api/agent/runs`.

## TASK 1 — execution shape

### Decision: one parent `Job` of type `agent`, orchestrated by an `asyncio` task in the API process — the funnel pattern, with one deliberate change to how the parent row is created.

An agent run is a record, exactly like a `funnel` parent Job: its `output`
column (free-form JSON, no schema change) accumulates the live `ToolCall` audit
trail and per-step budget counters; on completion it also holds the full
`AgentResult`. The `asyncio` task is almost entirely `await` (one tool call at a
time; `asyncio.sleep` between polls of a heavy child job), so it never blocks the
event loop and `/health` + every `GET` stays responsive for the hours a run
containing a funnel can take.

**The one difference from the funnel service:** the funnel router creates its
parent row *through* `ComputeRouter.execute(run_funnel_tool, …)`. An agent run
cannot. `ComputeRouter` has exactly two paths: `LOCAL`/`LOCAL_SMALL` execute the
tool **inline and return the value** (wrong — the POST must return a `run_id` in
milliseconds for a multi-hour run), and `HEAVY_LOCAL`/`REMOTE_CAPABLE` create a
Job but only after `ResourceManager._check_heavy`, which requires
`allow_docking=True` and a free docking slot (wrong — a three-`predict_*` agent
run must succeed in `battery-saver`, and Task 4's cheap sequence must finish in
under a second). The agent coordinator is neither cheap-inline nor
docking-gated; it is a long-lived orchestrator whose **individual steps** are
what need routing. So:

- the parent `agent` row is created with `job_store.create_job(job_type="agent",
  job_id=run_id, job_input=…)` directly;
- **every step** still goes through the unmodified
  `AgentRunner.call_tool → ComputeRouter.execute → ResourceManager.can_run`
  path. A `run_docking` step in `battery-saver` comes back `ComputeRejected` and
  is recorded as a `REJECTED` `ToolCall` — the rejection travels through the
  real `ResourceManager`, exactly as in `test_resource_rejection_travels_through_real_compute_router`.

"Rejects through ComputeRouter as everything else does" therefore holds at the
granularity that consumes real compute — the tool call. At submission the run is
rejected only for the agent concurrency ceiling (`503`, mirroring the funnel's
one-at-a-time rule) and for the up-front validation in Task 3.

Rejected alternatives:

- *Register a `run_agent` HEAVY_LOCAL tool and submit through `ComputeRouter`
  like the funnel.* Couples starting any agent run to `allow_docking`; breaks
  the cheap sequence. Also invites a planner to nest agent runs. Not registered:
  the registry stays a catalog of leaf operations, which is also what
  `GET /api/agent/tools` should hand a planner.
- *Run the whole sequence inside `AgentRunner.run()` and expose the trail only
  at the end.* The audit trail is the point of this layer and the task is
  explicit that it must be visible live. `AgentRunner.run()` returns only when
  the sequence is done, so the service owns the per-step loop and calls
  `AgentRunner.call_tool()` (its public one-call primitive) once per step,
  writing `job.output` after each. The loop replicates `run()`'s stop semantics
  exactly: `BudgetExhausted` → `RunStatus.BUDGET_EXHAUSTED` and stop; an
  individual `FAILED`/`REJECTED`/`UNKNOWN_TOOL` call does not stop the run;
  otherwise `RunStatus.COMPLETED`.
- *A monolithic `agent` job in the LocalWorker.* Same deadlock the funnel doc
  describes — the worker only claims `docking` jobs and each holds the
  concurrency slot; an agent job that submits child docks and waits on them
  while occupying the worker has nothing left to run the children.

### How the audit trail is exposed while the run is in flight

The orchestration task appends to `job.output["tool_calls"]` **immediately after
each `ToolCall` returns**, and rewrites `job.output["current_step"]` /
`job.output["budget"]` before and after every step. For a heavy step it also
writes `job.output["current_child"]` (the child `docking`/`funnel` job's id and,
for a funnel, its live `stage` / `docks_completed` / `docks_total`) on every
poll iteration. `GET /api/agent/runs/{run_id}` just reads `job.output`, so the
trail grows call-by-call and the funnel child's progress is visible while it is
still docking. This mirrors how the funnel service writes `partial_results` and
`docks_completed` incrementally.

Each serialised `ToolCall` carries: `step`, `tool_name`, `arguments`, `status`
(`success` | `failed` | `rejected` | `unknown_tool`), `duration_ms`, `error`,
`started_at`, `finished_at`. `/status` carries a compact result summary; the
full `tc.result` is in `/result` only.

### Budget: what a client may set, what stays a server ceiling

`AgentBudget` (env-configured via `AgentBudget.from_env()`) **is the ceiling**.
`MAX_AGENT_TOOL_CALLS`, `MAX_AGENT_DOCKING_JOBS`, `MAX_AGENT_STEPS`,
`MAX_AGENT_CANDIDATES`, `MAX_AGENT_RETRIES`, `MAX_AGENT_RUNS_LOCAL` set it.

| field | per-request? | rule |
|---|---|---|
| `max_tool_calls` | yes, **lower only** | effective = `min(requested, ceiling)` |
| `max_docking_jobs` | yes, **lower only** | effective = `min(requested, ceiling)` |
| `max_steps` | yes, **lower only** | effective = `min(requested, ceiling)` |
| `max_candidates` | yes, **lower only** | effective = `min(requested, ceiling)` |
| `max_retries` | yes, **lower only** | effective = `min(requested, ceiling)` |
| `max_concurrent_runs_local` | **no** | global, not a per-run property; server-only |

The clamp is `min()` applied field by field in `clamp_budget()`. There is no
code path that assigns a request value to an `AgentBudget` field without the
`min()` against the env ceiling. When a request asks for more than the ceiling
the response reports it under `budget.clamped` and proceeds with the ceiling —
the request is never rejected for asking too high, and never granted it.

### JobStore schema

**No change needed.** `type` is an arbitrary string column; the trail and
budget counters live in `output` (TEXT/JSON); `count_active("agent")` is
type-generic; `recover_stale_running` already fails an orphaned `agent` parent
after a restart, type-agnostically. Nothing here touches `ComputeRouter`,
`ResourceManager`, `JobStore`, or the tool-registry contract.

## TASK 2 — endpoints

```
POST /api/agent/runs
  body {
    goal?: str,
    requests: [ { name: str, args: object }, … ],      # ordered
    budget?: { max_tool_calls?, max_docking_jobs?, max_steps?,
               max_candidates?, max_retries? }          # clamped, never raised
  }
  201-style 200 → { run_id, status:"queued", accepted_steps, heavy_steps,
                    budget:{ effective, ceilings, clamped }, message }
  400  unknown tool name(s)         → lists every registered name
  400  invalid args for a step      → per-step {index, name, errors[]}
  400  heavy steps > max_docking_jobs → arithmetic shown, nothing started
  503  an agent run is already active (count_active("agent") ≥ ceiling)
  503  ComputeRejected surfaced at submission (kept for parity; today only
       the concurrency guard fires here)

GET  /api/agent/runs/{run_id}
  → { run_id, status, current_step, total_steps,
      tool_calls: [ {step, tool_name, arguments, status, duration_ms,
                     error, started_at, finished_at, result_summary} ],
      budget: { consumed:{tool_calls,steps,docking_jobs},
                remaining:{…}, ceilings:{…} },
      current_child?: {job_id, type, stage?, docks_completed?, docks_total?},
      error? }
  404  no such agent run

GET  /api/agent/runs/{run_id}/result
  → full AgentResult { run_id, status, output, error,
                       tool_calls:[ …full, incl. result ] }
  409  until the run is terminal

POST /api/agent/runs/{run_id}/cancel
  → { run_id, cancelled: bool, in_flight_child_cancelled: bool,
      vina_subprocess_killed: bool, message }

GET  /api/agent/tools
  → [ { name, category, description, compute_class, heavy, is_async, version,
        args_schema } ]                # args_schema is JSON Schema (pydantic
                                       # model_json_schema() or a hand shape for
                                       # the str-arg tools) — machine-readable
                                       # for a Phase-4 planner and a human.
```

Handlers stay thin: parse, validate via `agents/catalog.py` + `agents/service.py`,
create the row, spawn the task, return. No scientific logic in the router.

## TASK 3 — validation before the run starts

`agents/catalog.py` builds a `ToolSpec` per registered tool by introspecting
`tool.fn`:

- single parameter annotated as a `pydantic.BaseModel` subclass (`predict_*` →
  `MoleculeInput`, `generate_3d` → `MoleculeRequest`, `predict_batch` →
  `BatchRequest`, `run_docking` → `DockStartRequest`): `args_schema` is the
  model's `model_json_schema()`; validation constructs the model and reports
  `ValidationError` line by line;
- `parse_smiles` / `calculate_descriptors` (`fn(smiles: str)`): hand `args_schema`
  `{smiles: string, required}`; validation checks presence + non-empty str;
- `run_funnel`: validated by the funnel's own `FunnelStartRequest` +
  `service.resolve_candidates` + `service.validate_start` — the real guards,
  reused, so a bad `candidate_set_id` or an over-cap SMILES list is caught here
  and not 40 minutes in.

Submission runs, in order and all before any `Job` row:

1. **unknown tool** → `400` with the full registered-name list;
2. **bad args for any step** → `400`, every offending step reported with its
   index and the validation errors;
3. **heavy arithmetic** → `heavy_steps` (`run_docking` + `run_funnel` count) vs
   effective `max_docking_jobs`; if greater, `400` with
   `"sequence has H heavy tool(s) but max_docking_jobs=M (requested R, server
   ceiling C); nothing was started"`.

`max_tool_calls` / `max_steps` overshoot is **not** rejected up front — a
sequence longer than `max_tool_calls` is allowed to run and stop at
`BUDGET_EXHAUSTED`, which is `AgentRunner`'s existing contract
(`test_budget_exhaustion_blocks_excess_calls`) and Task 4's budget case. Only
the heavy-tool ceiling, which would otherwise burn real Vina time before
truncating, is pre-checked.

## Concurrency

- **One agent run at a time** — `POST` returns `503` if
  `count_active("agent") ≥ max_concurrent_runs_local` (default 1).
- **A `run_funnel` step respects the funnel's one-at-a-time rule** — the step
  checks `count_active("funnel")` and records a `FAILED` `ToolCall`
  (`"a funnel run is already active"`) rather than starting a second funnel; at
  submission the same check yields a `400` if a funnel is already running.
- **Heavy child docks are gated identically to everywhere else** — each is a
  `docking` Job via `ComputeRouter.execute`; if the slot is taken (a manual
  dock, the funnel) the submission is `ComputeRejected`, recorded `REJECTED`.
  The agent submits serially and never holds more than one child job.
- **Cancel** marks the parent `agent` Job `CANCELLED`; the task notices between
  steps (and inside a heavy poll loop), cancels the in-flight child and kills
  its `worker_pid` via the exact path `routers/dock.py` / `funnel/service.py`
  use.
