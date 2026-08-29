# Running DrugForge locally (post compute-fabric migration)

There are now **two backend processes**, not one. Docking silently does
nothing if you forget the second one — the job just sits `queued` forever.

## The two processes

**1. FastAPI (the API gateway)** — same as before:

```bash
cd backend
python3.11 -m venv venv   # first time only
source venv/bin/activate
pip install -r requirements.txt

cd app
uvicorn main:app --reload --port 5001
```

**2. LocalWorker (executes docking)** — new. In a second terminal, same venv:

```bash
cd backend/app
../venv/bin/python -m jobs.workers.local_worker
```

You'll see `worker_started worker_id=local-xxxxxxxx ...` when it's up. Every
docking job goes through this process now — `POST /api/dock/start` only
ever creates a job row and returns; it never runs Vina itself, not even via
a background task.

**3. Frontend** — unchanged:

```bash
cd frontend
npm run dev
```

## Compute mode

Docking is **disabled by default** (`COMPUTE_MODE=battery-saver`). If
`/api/dock/start` returns `503 "Docking is disabled in battery-saver mode"`,
either:

```bash
# one-off, for the current process:
COMPUTE_MODE=balanced uvicorn main:app --port 5001

# or at runtime, no restart needed:
curl -X POST http://localhost:5001/api/compute/mode -d '{"mode":"balanced"}' \
  -H "Content-Type: application/json"
```

The frontend's Compute Control panel (Dashboard → System) does the same
thing via a button.

## If nothing happens after `/start`

1. Is `local_worker` actually running? Check its terminal for `job_running`
   log lines — if it's silent, it's not polling.
2. `GET /api/dock/history` or `/api/dock/status/{task_id}` — a job stuck at
   `queued` means no worker claimed it. `completed`/`failed` means it did.
3. Vina binary present and runnable? `scripts/verify_vina.sh` (or
   `GET /health` → `vina_available` / `vina_version`). If it's missing, jobs
   fail fast with a clear error pointing at `scripts/setup_vina.sh` — that's
   expected, not a bug in the job system itself. Fix with
   `scripts/setup_vina.sh`.

## Environment variables (compute-fabric additions)

See `.env.example` for the full list — `COMPUTE_MODE`,
`MAX_LOCAL_BATCH_SIZE`, `MAX_LOCAL_CONCURRENT_TOOLS`, `DOCKING_ENABLED`,
`MAX_DOCKING_CONCURRENT`, `DOCKING_TIMEOUT_SECONDS`, `DOCKING_EXHAUSTIVENESS`,
`DOCKING_SEED`, `DOCKING_CPU`, `DOCKING_N_POSES`, `MAX_AGENT_*` (unused until
an agent loop exists, but already enforced-ready via `AgentState`/`AgentBudget`).

## AutoDock Vina — install, verify, determinism

### Install (pinned + checksum-verified)

The Vina binary is **not** in git. Acquire it on every fresh checkout with:

```bash
scripts/setup_vina.sh
```

This downloads **one pinned release** (AutoDock Vina 1.2.7 — the version is
hardcoded, never resolved to "latest"), checks its SHA256 against a
hardcoded per-platform digest, aborts loudly on any mismatch, installs it at
`backend/bin/vina`, and `chmod +x`'s it. It is idempotent — a second run with
a correct binary already present exits 0 without re-downloading. Supported
platforms: `linux-x86_64`, `macos-x86_64`, `macos-arm64`. Anything else
(e.g. `linux-aarch64`) fails with an actionable message rather than fetching
the wrong asset. Full checksum table: `scripts/README-vina.md`.

Check an existing install at any time:

```bash
scripts/verify_vina.sh          # exit 0 iff present, checksum-verified, and runnable here
scripts/setup_vina.sh --verify  # same thing
scripts/setup_vina.sh --force   # re-download even if a valid binary exists
```

`GET /health` also reports `vina_available` (bool) and `vina_version`
(the version the binary actually reports). The LocalWorker logs a one-line
`vina_preflight` on startup — it does **not** crash if Vina is absent; each
docking job then fails fast with a real error (there is no mock/fallback path
anywhere).

### Run a real docking job

```bash
# both processes, second terminal for the worker (see "The two processes" above)
cd backend/app && COMPUTE_MODE=balanced ../venv/bin/python -m uvicorn main:app --port 5001
cd backend/app && ../venv/bin/python -m jobs.workers.local_worker

curl -s http://localhost:5001/health | python -m json.tool        # vina_available: true

curl -X POST http://localhost:5001/api/dock/start \
  -H "Content-Type: application/json" \
  -d '{"smiles": "CC(=O)Oc1ccccc1C(=O)O", "target": "cox2", "exhaustiveness": 8}'
# -> {"task_id": "dock_...", ...}

curl -s http://localhost:5001/api/dock/status/<task_id> | python -m json.tool
# status="completed", real negative affinity_kcal_mol, non-null docked_ligand_pdbqt,
# elapsed_seconds > 0, plus provenance: seed, cpu, num_modes, exhaustiveness, vina_version
```

The worker log line for a completed job now records the full invocation:
`Docking complete: affinity=... exhaustiveness=8 seed=42 cpu=1 vina_version=1.2.7`.

### Determinism guarantee

Vina's Monte Carlo search is stochastic. Every invocation now passes an
explicit `--seed` (from `DOCKING_SEED`, default **42** — a fixed integer,
never time/PID-derived), an explicit `--cpu` (from `DOCKING_CPU`, default
**1** — a fixed thread count is required for bit-identical results across
machines with different core counts), and explicit `--exhaustiveness` /
`--num_modes`. The ETKDG conformer handed to Vina is seeded with the same
value. All of `seed`, `cpu`, `num_modes`, `exhaustiveness`, `vina_version`,
and `target` are stored in every job's `output`, so any stored affinity
traces back to the exact command that produced it.

**Verified** (macos-arm64, Vina 1.2.7, aspirin → cox2, exhaustiveness 8,
seed 42): three consecutive runs → identical best affinity `-4.4700 kcal/mol`,
identical all-five poses, identical docked-PDBQT hash. Changing only the seed
(1 / 12345 / 99999) gives `-4.502 / -4.548 / -5.209` — confirming the search
is genuinely stochastic and the seed is the control. Re-verified on
`linux-x86_64` via the clean-container test below.

Affinities **will** differ between Vina versions and between
exhaustiveness/box settings — that is expected, and is why the version and
every parameter are recorded per job.

### Clean-container reproduction (zero prior setup)

`docker/` proves the whole path from a bare `python:3.11-slim`: install
backend requirements → `scripts/setup_vina.sh` → boot API + LocalWorker →
run real docking job(s) → assert a real negative affinity, non-null PDBQT,
`elapsed_seconds > 0`, and (with `E2E_RUNS>1`) identical affinity across runs.

```bash
# from the repo root
docker compose -f docker/docker-compose.vina-e2e.yml up --build

# or without compose:
docker build  --platform=linux/amd64 -f docker/Dockerfile.vina-e2e -t drugforge-vina-e2e .
docker run --rm --platform=linux/amd64 drugforge-vina-e2e
```

`--platform=linux/amd64` is required — `setup_vina.sh` supports `linux-x86_64`
(the canonical CI/benchmark target), not `linux-aarch64`. On an Apple-Silicon
host it runs under QEMU emulation: correct, but several minutes per dock. The
container exits 0 only if every assertion passes, so it doubles as a CI gate.

## Design tradeoffs worth knowing about

- **Job persistence is SQLite, not Supabase** (`backend/app/jobs/jobs.db`,
  gitignored) — a deliberate choice so job state survives restarts without
  requiring Supabase to be configured. See
  `docs/architecture/compute-fabric.md` for the reasoning.
- **ComputeControl's mode buttons are the only independently-settable
  control** — the "Allow Docking / Allow Large Batches / Allow Parallel
  Jobs / Max Concurrent" readout underneath is informational (derived from
  whichever mode is active), not four separate settable fields. If you need
  finer-grained control than the 3 presets, that's a real but bigger change
  to `ComputePolicy` — flag it before assuming it's a quick add.
