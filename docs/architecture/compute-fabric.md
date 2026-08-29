# Compute Fabric

How DrugForge decides where computation runs, and what stops it from
overwhelming a fanless MacBook Air. Implemented incrementally in
`backend/app/compute/` and `backend/app/jobs/` — see
`docs/development/local-worker.md` for how to actually run it.

## Architecture

```
Route handler (e.g. routers/dock.py)
        │
        ▼
ResourceManager.can_run(tool_name, compute_class, batch_size)
        │  reads the active ComputePolicy (battery-saver/balanced/performance)
        ▼
   allowed?  ──No──▶  raise (503/413) with a human-readable reason
        │
       Yes
        │
   ┌────┴────────────────────────┐
   ▼                              ▼
LOCAL / LOCAL_SMALL          HEAVY_LOCAL / REMOTE_CAPABLE
   │                              │
LocalExecutor                 JobStore.create_job(...)
(in-process, same as           → row in jobs.db, status=queued
 it always ran)                → route handler returns immediately
                                       │
                                       ▼
                               LocalWorker (separate OS process)
                               polls JobStore, claims the job,
                               runs docking_worker.run_docking_job()
                               (the actual Vina subprocess)
```

**Update:** `routers/dock.py` and `routers/batch.py` now both route through
`ComputeRouter.execute()` — there is exactly one compute decision path, as
required before the agent layer is built. Neither router calls
`ResourceManager` directly anymore. `main.py` wires two singletons that make
this possible: `tool_registry = build_default_registry()` and
`compute_router = ComputeRouter(compute_policy, resource_manager)` — until
this pass, neither was actually instantiated anywhere in the running app,
so `ToolRegistry`/`ComputeRouter` existed as *unused* modules even though
`ResourceManager` alone was already being called correctly. That gap is
closed now:

```
dock.py::start_docking
    tool = tool_registry.get("run_docking")
    job = await compute_router.execute(tool, _job_store=..., _job_id=task_id, ...)
    # ComputeRejected -> 503

batch.py::run_batch
    tool = tool_registry.get("predict_batch")
    result = await compute_router.execute(tool, request, batch_size=len(...))
    # ComputeRejected -> 413
```

`batch.py`'s prediction loop itself was extracted into a standalone
`_execute_batch()` function (same logic, unchanged) so it could be
registered as a `Tool` and called via `LocalExecutor` like every other
LOCAL/LOCAL_SMALL tool — the HTTP handler is now a thin wrapper, not where
the resource check happens.

A future agent's tool calls go through the exact same
`tool_registry.get(name)` → `compute_router.execute(tool, ...)` shape —
nothing agent-specific needs to be built into the compute layer itself.

## Compute classes

Set once per tool at registration (`tools/registry.py`):

| Class | Meaning | Current tools |
|---|---|---|
| `LOCAL` | Cheap, synchronous, in-process | `parse_smiles`, `calculate_descriptors`, all 9 `predict_*` |
| `LOCAL_SMALL` | Slightly heavier but still synchronous | `generate_3d` |
| `HEAVY_LOCAL` | Runs via LocalWorker + JobStore, never inline | `run_docking` |
| `REMOTE_CAPABLE` | Interface-level flag only — no RemoteWorker exists | `run_docking` also sets `supports_remote=True` |

## Compute modes

Three fixed presets (`compute/policy.py::ComputePolicy.preset`) — never an
arbitrary client-supplied limit, per spec §10/§38:

| Mode | Docking | Large batches | Max local jobs | Max docking jobs |
|---|---|---|---|---|
| `battery-saver` (default) | disabled | disabled | 1 | 0 |
| `balanced` | enabled | disabled | 2 | 1 |
| `performance` | enabled | enabled | 4 | 2 — still bounded, never unlimited |

Change at runtime: `POST /api/compute/mode {"mode": "balanced"}`, or pin at
startup via `COMPUTE_MODE` env var. `GET /api/compute/policy` / `GET
/health`'s `compute_mode`/`queue` fields show current state. Individual
overrides (`DOCKING_ENABLED`, `MAX_LOCAL_CONCURRENT_TOOLS`, etc.) win over
the preset — see `.env.example`.

## Jobs

`jobs/models.py::Job` — `id, type, status, priority, input, output, error,
created_at, started_at, completed_at, worker_id, execution_location,
retry_count`, plus one addition beyond the spec's base list: `worker_pid`,
so a `/cancel` request arriving in the API process can kill a subprocess
owned by the separate LocalWorker process via `os.kill()`.

**Why SQLite, not Supabase, for the job store:** the spec says "use the
existing Supabase integration," but Supabase is optional everywhere else in
this app (predictions already work without it configured) and jobs are
explicitly required to survive API restarts. Making that depend on an
external service this app is designed to run without would contradict the
"$0 infrastructure, fully local" mandate. `jobs/store.py` uses Python's
stdlib `sqlite3` (`backend/app/jobs/jobs.db`, gitignored) — zero new
dependency, real restart survival, works completely offline. Supabase's
`predictions` table is untouched.

**Restart recovery** (`JobStore.recover_stale_running`): on `LocalWorker`
startup, any job still `status='running'` older than
`DOCKING_TIMEOUT_SECONDS` is presumed dead (its owning process is gone) and
marked `failed`. This is practical zombie-row cleanup, not distributed fault
tolerance — a genuinely in-flight job that's merely slow will look
identical to a crashed one until the timeout, which is the same tradeoff
the original in-memory design had.

## The computational funnel (future agent — not built yet)

The infrastructure above exists so a future agent never does this:

```
generate 1000 candidates → run 1000 Vina jobs   ✗ never
```

and instead does this:

```
candidates → SMILES validation (LOCAL) → descriptors (LOCAL)
  → cheap ADMET prediction (LOCAL, 9 existing models)
  → binding prediction (LOCAL) → filter
  → selective docking on the survivors only (HEAVY_LOCAL, queued, bounded
    by AgentBudget.max_docking_jobs)
  → ranking → critique → optional iteration
```

`AgentState` (`agents/types.py`) carries an `AgentBudget` and exposes
`can_take_step()`, `can_call_tool()`, `can_submit_docking_job()`,
`can_generate_candidate()`, `can_retry()` — a future agent loop checks these
before every action; none of them are currently called by anything, because
no agent loop exists yet. That loop is the next phase, not this one.

## A subtlety worth knowing: MAX_DOCKING_CONCURRENT also caps queue depth

`ResourceManager._check_heavy()` counts jobs with `status IN ('queued',
'running')` as "active." That means with `MAX_DOCKING_CONCURRENT=1`, a
*second* submission is rejected the moment the first is queued — even
before any worker has claimed it, even if no worker is running at all.
Verified: submitting 3 jobs back-to-back with no worker running rejects
jobs 2 and 3 immediately (503), not just once a job starts executing. This
is a reasonable, conservative reading of the limit — it also prevents
unbounded queue buildup, not just unbounded concurrent execution — but
it's worth knowing explicitly rather than assuming "concurrent" means only
"simultaneously running."

## Local development vs. future hosted deployment

Everything above already runs config-driven, not localhost-assumed —
verified by grep: no hardcoded `127.0.0.1`/`localhost` in application logic
(the one hit is a dev-only startup log line), no hardcoded absolute
filesystem paths anywhere in `backend/app/`. What's still local-development-shaped
by explicit design choice, not oversight:

| Concern | Local dev today | What hosting would need |
|---|---|---|
| Job persistence | SQLite file (`jobs.db`) | Render's filesystem is ephemeral — job history is lost on every redeploy. Acceptable for now (jobs are transient work items, not permanent records); a `PostgresJobStore` implementing the same `JobStore` interface (Phase 10 confirmed: zero SQLite leakage outside `store.py`) is the natural fix *when* that becomes a real requirement, not before. |
| LocalWorker process | Manually started second terminal | Render's free/starter tiers run one process per service; running a second always-on worker process needs a second Render service (or a background worker dyno-equivalent) — a deployment config change, not a code change. |
| Vina binary | Missing locally; architecture-gated when present | Needs an `linux-x86_64` (or whatever Render's runtime is) build, not the macOS one referenced in earlier sessions — cross-platform binary management is a real open item, unrelated to anything built in this pass. |
| Rate limiting / auth on compute-heavy routes | None | Not built in this pass (§12 says "prepare," not "build a security platform") — `ResourceManager` is the natural place to add a per-IP or per-user check later without touching route handlers again. |

None of this requires new infrastructure to keep working exactly as it does
today, fully local, $0 cost — it's a list of what a *public* deployment
would additionally need, kept separate from what exists now.

## What's NOT built yet (by design)

- The actual agent orchestration loop / LangGraph graph — `AgentState`
  exists, nothing drives it.
- `RemoteWorker` / `GPUWorker` — `jobs/workers/base.py`'s `Worker` interface
  supports them; only `LocalWorker` is implemented.
- Independent per-field policy overrides from the frontend (the spec's UI
  mockup showed independent checkboxes; this implementation uses 3 fixed
  presets instead — see `docs/development/local-worker.md` if that tradeoff
  needs revisiting).
