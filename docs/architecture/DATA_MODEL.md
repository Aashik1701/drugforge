# Data Model — Current State & Future Provenance

## What exists today

One table, accessed via raw Supabase REST calls (`backend/app/services/db_service.py`,
using `httpx` — not an ORM; `backend/app/database/connection.py` is an
unimplemented placeholder for a future SQLAlchemy engine):

- **`predictions`** — one row per prediction request: SMILES, model type,
  result, confidence, metadata (unit, molecular weight, execution time).
  Written after every successful `/predict/*` call; failures to write are
  logged, not raised (`services/db_service.py:save_prediction`) — DB
  unavailability never breaks a prediction response.

Nothing else is persisted. There is no `users`, `projects`, or `agent_runs`
table yet.

## Future entities (conceptual only — not implemented)

As agentic workflows get built, the following entities will likely be
needed, in roughly this dependency order:

| Entity | Purpose | Depends on |
|---|---|---|
| `projects` | Group work into a named research effort | — |
| `targets` | A protein/receptor being investigated (links to `backend/targets/*.pdb`) | `projects` |
| `molecules` | Canonical SMILES + computed descriptors, deduplicated | `projects` |
| `candidates` | A molecule proposed for a specific target | `molecules`, `targets` |
| `experiments` | A batch of evaluation runs against one or more candidates | `projects` |
| `predictions` | *(exists today)* — extend with `experiment_id` FK when experiments exist | `experiments`, `molecules` |
| `docking_runs` | AutoDock Vina results — currently return-only, never persisted | `candidates`, `targets` |
| `agent_runs` | One execution of an agent — maps to `AgentRun` in `backend/app/agents/types.py` | `experiments` |
| `tool_calls` | Audit trail of tool invocations within a run — maps to `ToolCall` in `agents/types.py` | `agent_runs` |
| `evidence` | Citations/sources an agent used to justify a conclusion | `agent_runs` |

## Why this isn't built yet

Building this schema now, before any agent exists to populate or query it,
would be speculative — exactly the "huge schema for features that don't
exist" this modernization pass was told to avoid. `AgentState`, `AgentRun`,
`AgentResult`, and `ToolCall` already exist as in-memory dataclasses
(`backend/app/agents/types.py`) with field names chosen to match this table
list, so wiring persistence later is a matter of writing repository
functions against these existing shapes — not redesigning them.

`docking_runs` is worth calling out: docking results are currently
ephemeral (in-memory task registry in `routers/dock.py`, lost on restart).
Persisting them is the most immediately useful addition from this list, once
Supabase migrations are actually being made.
