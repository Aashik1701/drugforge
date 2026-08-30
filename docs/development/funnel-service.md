# Funnel as a backend service

Moves the computational funnel (eleven passes of research, previously
CLI-only) behind HTTP. **This pass moves existing behaviour, it does not change
the funnel's scientific logic, the frozen v7 policy, or the docking params.**

## Job shape

**Decision: one parent `Job` of type `funnel` in the JobStore, orchestrated by
an `asyncio` task inside the API process; every dock it needs is a separate
child `Job` of type `docking` created through `ComputeRouter` exactly as
`/api/dock/start` does.**

Rejected alternatives:

- *One monolithic Job that runs in the LocalWorker.* The LocalWorker's claim
  loop only pulls `docking` jobs and each dock holds a `MAX_DOCKING_CONCURRENT`
  semaphore slot. A funnel job that itself submits child docks and waits on
  them, while occupying the single worker, deadlocks: nothing is left to run the
  children.
- *Private `/tmp` job store + private LocalWorker per run* (what the CLI does).
  This is exactly the bypass the task forbids: a private worker enforces its own
  `MAX_DOCKING_CONCURRENT` against its own store, so two runs (or a run plus a
  manual dock) can exceed the global limit.

The parent `funnel` Job is a **record**, not a unit of worker execution. Its
`output` column (free-form JSON, no schema change) accumulates stage progress
and, on completion, the full `RunRecord`. The `asyncio` task in the API process
does the work: it is almost entirely `await` (polling child docking jobs,
`asyncio.sleep` between polls), so it never blocks the event loop and the API
stays responsive.

### Why no JobStore / ResourceManager / ComputeRouter / tool-registry change is needed

- `job_store.create_job(job_type="funnel", job_input=..., job_id=run_id)` --
  `type` is an arbitrary string column.
- Progress lives in `output` (TEXT / JSON). No new column.
- `job_store.count_active("funnel")` -- `count_active` is type-generic
  (`WHERE type = ? AND status IN ('queued','running')`).
- Child docks link to the parent by `job_input["funnel_run_id"]` (free JSON) and
  a deterministic id (`<run_id>__c<idx>s<seed>`).
- Cross-process cancel of an in-flight Vina subprocess reuses the existing
  `worker_pid` column and the exact kill path from `routers/dock.py`.
- `JobStore.recover_stale_running` already marks any `running` job past the
  timeout as `failed`, type-agnostically -- it cleans up an orphaned `funnel`
  parent after an API restart with no change.
- The funnel is registered in `build_default_registry()` as one more `Tool`
  (same as `run_docking` was added) -- that follows the tool-registry contract,
  it does not modify it.

## Concurrency safety -- how a funnel run respects `MAX_DOCKING_CONCURRENT`

1. **`POST /api/funnel/start` goes through `ComputeRouter.execute` with a
   `HEAVY_LOCAL` tool.** `ResourceManager._check_heavy` runs the *same* gate as
   `/api/dock/start`: docking must be enabled in the active `ComputePolicy`
   (rejected in `battery-saver`), and `count_active("docking")` must be below
   `MAX_DOCKING_CONCURRENT`. A start during an active dock returns `503` -- no
   separate gating path.
2. **The funnel executor docks strictly serially.** It submits child seed docks
   one at a time (`N` candidates x 4 seeds, inner loop over seeds, outer over
   candidates) and waits for each child to reach a terminal state before
   submitting the next. It never holds more than one `docking` job
   `queued`+`running` at once.
3. **Every child dock is created through `ComputeRouter.execute` as
   `HEAVY_LOCAL` `docking`.** If something else (a manual `/api/dock/start`, a
   second funnel that slipped in during this one's screening phase) has taken
   the slot, the child submission gets `ComputeRejected`; the executor backs off
   (`asyncio.sleep`, up to a bounded number of retries) and re-submits. It
   cannot force a dock past the limit -- there is no code path that reaches Vina
   except `create_job("docking")` -> the shared LocalWorker, and the worker's
   own `asyncio.Semaphore(MAX_DOCKING_CONCURRENT)` is the final backstop.
4. **Only one funnel run at a time.** `POST /api/funnel/start` also rejects
   (`503`) if `count_active("funnel") > 0`. Two interleaving funnels would still
   be *safe* (every child dock is gated as above) but slow and confusing;
   forbidding a second run is simpler and enforced in the funnel service, not in
   ResourceManager.

Net: the only way to run Vina is a `docking` Job through the shared worker, and
that path is gated identically whoever creates the job. The funnel adds a
serial submitter in front of it, never a parallel one.

## Stage progress (the parent Job's `output`)

```json
{
  "stage": "queued|screening|prescreen|docking|ranking|done|cancelled|failed",
  "candidate_set_id": "cox2_v1", "target": "cox2",
  "budget_n": 3, "policy_id": "v7_binding_weak_cox2",
  "candidates_in": 45,
  "stage_survivors": [
    {"stage": "smiles_validation", "in": 45, "out": 45},
    {"stage": "druglikeness_filter", "in": 45, "out": 41},
    {"stage": "toxicity_filter", "in": 41, "out": 41}
  ],
  "prescreen_selected": ["CHEMBL411894", "CHEMBL408215", "CHEMBL111518"],
  "docks_submitted": 8, "docks_completed": 6, "docks_failed": 0,
  "current_dock_job_id": "<run_id>__c1s2024",
  "partial_results": [
    {"ligand_id": "CHEMBL411894", "seeds_done": 4, "mean_affinity": -5.73}
  ],
  "started_at": "2026-08-30T...Z", "elapsed_s": 214.7,
  "run_record": null
}
```

`run_record` is `null` until `stage == "done"`, then it is the full
`RunRecord` v1.0.0 dict (schema unchanged).

## Cancellation

`POST /api/funnel/cancel/{run_id}`:

1. `job_store.cancel_job(run_id)` -- parent `funnel` Job -> `cancelled`.
2. Read `output.current_dock_job_id`; if a child dock is in flight,
   `job_store.cancel_job(child_id)` and, if the child has a `worker_pid`,
   `os.kill(worker_pid, SIGKILL)` -- the identical path `routers/dock.py`
   `cancel_docking` uses to kill a running Vina subprocess from a different
   process than the worker.
3. The executor's poll loop checks the parent Job status between stages and on
   every poll tick; on seeing `cancelled` it stops, sets `stage="cancelled"`,
   and returns without writing a `RunRecord`.

## Guards (Task 4)

| failure mode | guard |
|---|---|
| oversized upload | `len(smiles) <= FUNNEL_MAX_UPLOAD` (default 100), else `413` |
| invalid SMILES in upload | every SMILES RDKit-parsed before anything expensive; if any fail, `400` with `{parse_failures: [{index, smiles, error}], n_valid}` -- nothing is silently dropped and no run starts |
| `budget_n` unbounded | `1 <= budget_n <= FUNNEL_MAX_BUDGET_N` (default 50) server-side, else `413`; then clamped to the set size |
| a single dock hangs | executor poll deadline (`monotonic`, `FUNNEL_DOCK_POLL_TIMEOUT`, default = `DOCKING_TIMEOUT_SECONDS`) marks that seed `failed` and the run continues; the LocalWorker independently kills the Vina subprocess at `DOCKING_TIMEOUT_SECONDS` |
| two funnel runs | `count_active("funnel") > 0` -> `503` |
| docking disabled / slot full | `ComputeRouter` -> `ComputeRejected` -> `503`, same as `/api/dock/start` |

## Endpoints

| method + path | purpose |
|---|---|
| `POST /api/funnel/start` | `{candidate_set_id \| smiles[], target, budget_n, policy_id}` -> `{run_id, status}`; rejects `503`/`413`/`400` before any expensive work |
| `GET /api/funnel/status/{run_id}` | the `output` block above |
| `GET /api/funnel/result/{run_id}` | the full `RunRecord` v1.0.0 (`409` if not `done`) |
| `POST /api/funnel/cancel/{run_id}` | cancel run + in-flight dock |
| `GET /api/funnel/sets` | committed candidate sets: `set_id`, size, `content_sha256`, `n_reference` |
| `GET /api/funnel/frontier/{set_id}` | the cached `runs/frontier_<set_id>.csv` rows, for showing the budget tradeoff before picking `N` |

Route handlers stay thin: validate cheaply, `tool_registry.get("run_funnel")`,
`compute_router.execute(...)`, spawn the executor task, return. The resource
decision stays in `ComputeRouter` / `ResourceManager`.

## Compute class for `run_funnel`

**`HEAVY_LOCAL`.** A funnel run is non-inline (minutes to an hour), requires the
docking-enabled policy, and must serialize against other heavy docking work.
`HEAVY_LOCAL` is exactly "gated by `_check_heavy` (docking enabled + concurrency
slot), created as a Job, never run inline." `REMOTE_CAPABLE` would imply a
future `RemoteWorker` could execute it, which is not true (the executor is an
in-process `asyncio` task). `LOCAL`/`LOCAL_SMALL` would run it inline on the
request and skip the docking gate entirely -- wrong on both counts.

The one semantic imperfection: `_check_heavy` counts active `docking` jobs, not
`funnel` jobs, so "start a funnel" is blocked whenever a manual dock is
running. This is acceptable and in fact desirable -- it serializes heavy work
without a ResourceManager change.
