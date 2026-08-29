# Performance Baseline — Pre Compute-Fabric Migration

Measured 2026-08-28 on the actual dev machine (MacBook Air M2, 16GB), before
any Phase 2+ changes. Methodology and honest limitations noted per measurement
— this is not a lab-grade benchmark, it's representative sampling on real
hardware with a real (not synthetic) codebase.

## Backend (FastAPI, `uvicorn main:app`, no `--reload`, 9 models loaded)

**Method:** `ps -o %cpu,%mem -p <pid>`, sampled 5× at 2s intervals while idle;
`curl -w "%{time_total}"` for latency, 5 runs per endpoint unless noted.

| Measurement | Result |
|---|---|
| Idle CPU (backend process, no requests) | **~0.1%** — negligible |
| Idle memory | ~0.3–1.2% of 16GB (models resident, nothing else) |
| `GET /health` | 37.6ms |
| `POST /predict/solubility` (single molecule) | 17–83ms (5-run range, median ~18ms) |
| `POST /utils/generate-3d` | 17–52ms |
| `POST /predict/batch`, 5 molecules × 9 models | **5.38s** |
| `POST /predict/batch`, 20 molecules × 9 models | **9.3–17.6s** (two runs, see note) |
| `POST /api/dock/start` (submission only) | 4.6–14.7ms — already fast; BackgroundTasks scheduling is cheap, this number won't change structurally once moved behind a job queue |

**Note on batch:** the two 20-molecule runs (9.3s and 17.6s) differ because the
second immediately followed the first with no cooldown — some resource
contention on this 8-core M2 Air. Either number alone justifies §15's
`MAX_LOCAL_BATCH_SIZE` — at this rate, a 100-molecule batch (the schema
currently allows up to **1000**) would plausibly take 45–90+ seconds
synchronously blocking a FastAPI worker thread. This is the single most
concrete piece of evidence for why batch needs a hard limit, independent of
docking.

**Docking execution:** cannot be measured — `backend/bin/vina` is absent.
`POST /api/dock/start` already degrades gracefully today: the job is marked
`failed` within ~1ms of actual Vina invocation with a clear error
(`"Vina binary not found at .../bin/vina. Download it from
https://github.com/ccsb-scripps/AutoDock-Vina/releases"`) rather than hanging
or crashing the API. Real docking latency/CPU baseline is deferred until the
binary is restored.

## Frontend (Vite dev server + Chrome)

**Method:** `ps -o %cpu,%mem -p <vite-pid>` for the dev server process;
`ps aux | grep "Google Chrome Helper (Renderer)"` summed across all renderer
processes for browser-side load, sampled 6× at 2s intervals.

| Measurement | Result |
|---|---|
| Vite dev server process, idle after initial compile | 0.3–18% (settles down; the higher numbers are startup/first-compile, not steady-state) |
| Chrome renderer total CPU%, DrugForge landing page open (aurora/meteor/shimmer/glow animations running) | **16.4% – 44.4%** across 6 samples, avg ≈ 29% |
| Chrome renderer total CPU%, static comparison page (example.com) open in the same profile | **13.7% – 26%** across 6 samples, avg ≈ 19% |

**Important limitation:** these renderer numbers are **not isolated to a
single tab** — `ps` sums every Chrome renderer process in the profile, which
may include other tabs open in the same browser session, not just the one
under test. I don't have a reliable way to attribute CPU to one specific tab
from outside the browser. The comparison above (DrugForge landing vs. a
static page, same session, same other-tab noise) is the most honest signal I
can extract: roughly a **10-percentage-point-average delta**, with DrugForge's
peak sample (44.4%) meaningfully higher than any static-page sample (max
26%). That delta is consistent with continuously-running CSS animations
being real, non-trivial GPU/CPU load — but I'm not claiming a precise
percentage reduction target from this number alone.

## What this baseline will be compared against

After Phase 17 (lazy-load + performance mode), re-run the same landing-page
vs. static-page comparison with `VITE_PERFORMANCE_MODE=true` and report the
new delta next to this one — same method, so the comparison is apples-to-apples
even though neither number is lab-precise.
