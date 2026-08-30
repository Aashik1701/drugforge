# The LLM budget planner

Phase 4. Adds `POST /api/agent/plan`: an LLM substitutes for the human who,
until now, hand-wrote the tool sequence for `POST /api/agent/runs`. This pass
tests **one narrow, measurable claim** — *given a discovery goal and a candidate
set, can an LLM pick a docking budget `N` better than the fixed `N=10`
heuristic?* — measured offline against the same cached frontier every prior pass
used. It is not "we added an LLM."

## Scope boundary — what the planner does and does NOT do

### The planner does

1. **Reads three inputs, all already in the system:**
   - the goal (free text from the caller),
   - candidate-set metadata (`GET /api/funnel/sets` — size, reference count,
     content hash),
   - the cached recall-vs-budget frontier for that set
     (`GET /api/funnel/frontier/{set_id}` — the curve produced by eleven passes
     of offline research).
2. **Chooses one integer `N`** (the docking budget) and **writes a text
   rationale** for the choice.
3. **Emits a tool sequence** in the exact `POST /api/agent/runs` request format —
   in practice a single `run_funnel` step with `budget_n = N` and the frozen
   policy id.

### The planner does NOT

- **do chemistry** — no SMILES parsing, descriptor calculation, conformer
  generation. That stays in RDKit.
- **predict properties or score molecules** — no ADMET/binding inference. That
  stays in the trained models.
- **choose filter thresholds or ranking weights** — the v7 policy
  (`v7_binding_weak_cox2`) is frozen; the planner cannot name another policy id
  and the emitted step is rejected if it tries.
- **invent SMILES or candidate sets** — it may only reference a
  `candidate_set_id` that already exists; an unknown one is a 404 before the LLM
  is even called.
- **see or influence any docking result** — the planner runs once, before
  execution, with no docking output in scope. It cannot re-plan mid-run, cannot
  read partial results, cannot change `N` after docking starts.
- **execute anything** — `POST /api/agent/plan` returns a plan and stops. Compute
  is spent only when a human (or a follow-up call) posts the plan to
  `/api/agent/runs`.

This boundary is the difference between an orchestrator and a hallucination
surface. The LLM's entire influence on the system is **one integer**, and that
integer is clamped and its tool sequence re-validated in code (below) before it
can spend a single dock.

## Endpoints

```
POST /api/agent/plan
  body   { goal: str, candidate_set_id: str, target: "cox2" | "ace2" }
  200    { plan_id, chosen_n, rationale, tool_sequence,
           frontier_context: { recommended_n: 10, chosen_row, recommended_row,
                               knee_literal_r10, knee_tiecredit_r10, n_rows },
           clamp: { raw_n, chosen_n, ceiling, set_size, clamped: bool },
           llm: { provider, model, attempts, parse_ok } }
  400    the LLM's emitted tool sequence failed the Phase-3 submission
         validator (reason included) — a malformed plan is never runnable
  404    no cached frontier for candidate_set_id (the planner reads the curve;
         without it there is nothing to reason over)
  422    the LLM returned unparseable output after PLANNER_MAX_ATTEMPTS tries
         (declared constant, default 2 — no silent unbounded retry)
  503    GEMINI_API_KEY unset — same shape as POST /api/chat/ask

POST /api/agent/runs
  body   { plan_id }                       # execute a previously-inspected plan
    or   { requests: [...] , budget? }     # the Phase-3 caller-supplied form
  exactly one of plan_id / requests. With plan_id the stored tool_sequence
  becomes `requests` and the request proceeds down the unchanged Phase-3 path
  (clamp budgets, validate submission, create the `agent` Job, execute).
```

Plan and execute are **separable by construction**: `/plan` never creates an
`agent` Job and never calls the executor. A plan is a `job_type="agent_plan"`
record (status `completed`, the plan doc in `output`) that can be fetched,
diffed, or discarded without cost.

## Constraints enforced in code, not in the prompt

| requirement | where |
|---|---|
| `chosen_n` clamped to server ceilings | `planner.clamp_n()` → `max(1, min(raw_n, FUNNEL_MAX_BUDGET_N, set_size))`. Same `FUNNEL_MAX_BUDGET_N` (=50) the funnel's own `budget_n` is bound by, plus the candidate-set size. The LLM cannot raise it; a value above is clamped and flagged in `clamp.clamped`. |
| emitted sequence validated before it is runnable | `planner.make_plan()` runs the sequence through the **Phase-3** `clamp_budget()` + `validate_submission()` (unknown tool, bad args, heavy-count vs `max_docking_jobs`). Failure → `PlannerError` → HTTP 400 with the validator's reason. The same validator runs again at `/api/agent/runs` time. |
| unparseable LLM output fails cleanly, bounded retries | `PLANNER_MAX_ATTEMPTS` (module constant, default 2). Each attempt logged `planner_llm_attempt n=… parse_ok=…`. After the cap → `PlannerError("unparseable after N attempts")` → HTTP 422. No silent retry loop. |
| missing key → 503, chat shape | `services.llm.get_provider()` returns `None` → `PlannerUnavailable` → `HTTPException(503, "AI engine not configured. Set GEMINI_API_KEY in backend .env")`. |
| planner never touches scientific computation | the planner module imports `services.llm`, `funnel.service` (read-only `list_sets` / `load_frontier`), and the Phase-3 validator. It imports no RDKit, no model loader, no Vina, no docking params, no v7 policy internals. |

## The measurement (the actual deliverable)

`agents/plan_goals.py` holds **six goal prompts, pre-registered** before any
planner run, spanning implied budgets from "cost no object" to "cheap". For each
goal × {`cox2_v1`, `ace2_v1`} × 3 repeats, `agents/plan_eval.py`:

1. runs the planner, records `chosen_n` + rationale;
2. scores that `N` against the cached frontier row (`recall@10` literal and
   tie-credited, `recall@5` secondary, docks spent, est. wall-clock) — the
   frontier CSV *is* the cached baseline, no new docking;
3. compares to fixed `N=10` on the same goal;
4. reports the 3-run spread of `chosen_n` (determinism).

"Better" = reaches the goal's stated recall requirement at fewer docks, **or**
higher recall at the same docks. A planner that only helps on the target it was
demoed against is not a result — hence both sets.

The plausible outcome, stated up front: the frontier is a simple curve with an
obvious knee, and a fixed heuristic reading the same curve does fine. "An LLM
reading the frontier chooses sensibly but does not beat the fixed operating
point" is a real finding and closes the question. The prompt is **not** tuned
against the recall numbers; any prompt iteration is logged with its version and
result in the report.
