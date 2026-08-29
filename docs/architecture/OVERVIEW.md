# Architecture Overview

This is a map of the repository after the 2026-08 cleanup — what lives where,
and why. It's organizational, not a spec for new features.

## Top-level layout

```
frontend/    React + Vite UI. Deployed to Vercel (frontend/vercel.json).
backend/     FastAPI prediction + docking API. Deployed to Render (backend/render.yaml).
ml/          Training scripts, notebooks, and datasets that produce backend/models/*.pkl.
research/    Papers, standalone docking experiments, and archived legacy code.
docs/        This directory.
```

`frontend/` and `backend/` are independently deployable — the frontend talks
to the backend purely over HTTP (`frontend/src/services/api.js` → the URL in
`VITE_API_URL`). Nothing in `ml/` or `research/` is imported by either at
runtime; they're offline.

## Backend internals

```
backend/
├── app/            The FastAPI application (main.py, routers/, schemas/, services/, utils/, database/)
├── models/          Runtime .pkl models — the ONE authoritative copy of each
├── targets/          Docking receptor structures (.pdb/.pdbqt)
├── bin/vina          AutoDock Vina CLI binary, called via subprocess by routers/dock.py
├── tests/             pytest suite
├── conftest.py        Makes app/ importable so tests can `from main import app`
└── render.yaml        Deploy config — runs `cd app && uvicorn main:app`
```

The app is split into `app/` (versioned application code) and the sibling
`models/`, `targets/`, `bin/` (larger, more static runtime assets) so that
code and data artifacts are easy to reason about separately. See `ml/README.md`
for which models are reproducible from what's in this repo, and which aren't.

## Where things came from

- `backend/` used to run a Flask app directly out of `backendML/`. That's
  been retired; see `research/archive/legacy-flask-backend/README.md` for
  the full history.
- `ml/` and `research/docking_experiments/` used to be one big `backendML/`
  directory mixing production models, training notebooks, datasets, and
  one-off docking experiments together. They're now split by purpose.

## Frontend state — what goes where

- **React Context** (`AuthContext`, `DrugForgeContext`) — cross-cutting,
  stable app state. Unchanged by this modernization.
- **TanStack Query** (`@tanstack/react-query`, wired in `src/index.jsx`) —
  server state. `src/hooks/useModelHealth.js` is the reference pattern:
  fetch + cache + loading/error state for a GET endpoint. Existing hooks
  with their own working polling/mutation logic (`useDocking`) were left
  alone — this is additive, not a wholesale Axios migration.
- **Zustand — not added yet.** Nothing in the current UI has state complex
  enough to need it; the two Context providers above cover it. Reach for it
  when an agent workspace UI (multi-step run builder, live trajectory view)
  needs client state that Context/prop-drilling makes awkward — not before.

## Preparing for agentic expansion

The next phase of this project introduces agent-driven workflows on top of
this foundation — roughly:

```
Research/Discovery → Target Analysis → Candidate Generation → Molecular Evaluation
  (ADMET, QSAR, Binding, Docking, properties) → Critique/Verification →
  Experiment/Evaluation → Evidence/Reporting
```

None of that is implemented yet. The point of this cleanup is that each of
those stages has an obvious home to grow into without another repo-wide
restructuring:

- **Molecular Evaluation** (ADMET/QSAR/Binding/Docking) maps directly onto
  `backend/app/routers/` and `ml/training/` — new prediction types are new
  routers + new training scripts, following the existing pattern.
- **Target Analysis** and **Candidate Generation** would be new backend
  services/routers, using `backend/targets/` and `ml/datasets/` as inputs.
- **Critique/Verification** and **Evidence/Reporting** are new service-layer
  concerns — natural fits under `backend/app/services/`.
- Anything genuinely agent-orchestration-specific (planning, tool routing
  between the above) should get its own top-level package once it exists —
  premature to create an empty one now.
