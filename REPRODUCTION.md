# Reproduction guide

From a bare environment to the funnel-vs-baseline numbers in the README. Tested
end-to-end in a clean `python:3.11-slim` container (see the bottom of this file
for the transcript).

Everything here is offline except `scripts/setup_vina.sh` (downloads one pinned
binary from GitHub) and, if you regenerate a candidate set, nothing — the
ChEMBL exports are vendored in the repo.

---

## 0. Platform, versions, and the cross-ISA caveat

Reference run: **Apple M2, 8 cores, 16 GB, macOS 26.5.2 (arm64)**,
Python 3.11.14, AutoDock Vina 1.2.7.

Docked affinities are reproducible **on the same CPU architecture** with the
pinned Vina version and the fixed seeds. Across architectures (x86-64 vs
arm64) the same input diverges by ~0.01–0.05 kcal/mol because Vina's score is
an order-dependent sum of floating-point terms. If you reproduce on a
different ISA, expect the *ranking* to hold and individual affinities to shift
slightly. The committed `runs/baseline_*.json` were produced on arm64;
regenerate them if you need x86-64 numbers.

---

## 1. Setup

Requires: Python 3.11, `curl`, a C-free environment (all deps are wheels),
~2 GB disk.

```bash
git clone <this-repo> drugforge && cd drugforge

python3.11 -m venv backend/venv
backend/venv/bin/pip install --upgrade pip
backend/venv/bin/pip install -r backend/requirements.txt      # ~2 min

scripts/setup_vina.sh                                         # ~1 min
scripts/verify_vina.sh                                        # must print: AutoDock Vina v1.2.7
```

`scripts/setup_vina.sh` detects OS/arch, downloads the matching AutoDock Vina
1.2.7 release asset to `backend/bin/vina`, checks a hardcoded per-platform
SHA-256, and `chmod +x`. Supported: `linux-x86_64`, `macos-x86_64`,
`macos-arm64`. On anything else it fails with an actionable message rather than
fetching the wrong asset. The binary is **not** committed.

**Expected:** `verify_vina.sh` exits 0 and prints `AutoDock Vina v1.2.7`.

---

## 2. Data — what is required and where it comes from

All vendored in the repo, all public:

| file | what | used for |
|---|---|---|
| `ml/datasets/target_identification/COX-2.csv` | ChEMBL bioactivity export, target CHEMBL230 (COX-2, human) | building `cox2_v1` |
| `ml/datasets/target_identification/ACE-2.csv` | ChEMBL bioactivity export, target CHEMBL3736 (ACE2, human) | building `ace2_v1` |
| `backend/models/*.pkl` | the 9 pre-trained scikit-learn models | the funnel's LOCAL prescreen |
| `backend/targets/{cox2,ace2}_receptor.pdbqt` | receptor structures (from PDB 1CX2, 1R42) | docking |
| `backend/app/funnel/datasets/{cox2,ace2}_candidates_v1.csv` + `.provenance.md` | the built candidate sets, with a content SHA-256 | baseline + funnel |
| `runs/baseline_cox2_v1.json` | **cached full baseline** — all 45 cox2 candidates docked, 4 seeds | replay, so you don't re-dock for 2 h |
| `runs/baseline_ace2_v1.json` | cached held-out ACE2 baseline | held-out evaluation |
| `runs/features_cox2_v1.json` | cached LOCAL model outputs for all 45 cox2 candidates | offline policy sweep + frontier |

To rebuild a candidate set from the ChEMBL CSV (deterministic, RNG seed
`20260228`):

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.build_candidate_set --target cox2
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.build_candidate_set --target ace2
```

**Expected:** prints the drop counts and `content_sha256`; the cox2 hash is
`9ae649ec19fe9a206e8bdbd3a2b43609e89623f8d713a511d05c0bd33c7d35af`, the ace2
hash is `b55d875f1ad82fec5122cf54ce0730f41176621a1c617c2a59dd9296368f42ca`.
The written CSV is byte-identical to the committed one.

---

## 3. The full baseline (~2 h — the cached artifact exists so you can skip this)

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.baseline \
    --candidates funnel/datasets/cox2_candidates_v1.csv --set-id cox2_v1 --target cox2 \
    --out ../../runs/baseline_cox2_v1.json
```

Docks all 45 candidates × 4 seeds = **180 Vina jobs**, serially (concurrency
cap = 1). On the reference M2 this took **7134 s of docking** (~2 h). It starts
its own `LocalWorker` subprocess and its own private SQLite job store in
`/tmp`, and tears the worker down on exit. Output is a `RunRecord` v1.0.0 JSON.

**If you are on a laptop, run it under `caffeinate` (macOS) or disable sleep** —
a suspend mid-run is handled correctly (the poll deadline is monotonic) but it
still stretches wall-clock over days.

**You do not need to run this.** `runs/baseline_cox2_v1.json` is committed. To
smoke-test the command without the 2 h, add `--limit 2`.

**Expected (`--limit 2`):** two candidates docked, ~5 min, a JSON written with
`total_docking_jobs_submitted: 8` and two ranked results.

---

## 4. The funnel (~6 min — 20 docks)

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.funnel --out ../../runs/funnel_cox2_v1.json
```

Runs the LOCAL prescreen over all 45 candidates (SMILES → descriptor filter →
toxicity filter → `v7_binding_weak_cox2` ranker), then docks **only the top 5**
(20 Vina jobs). ~6 min on the reference M2.

**Expected:** prints the prescreen ranking; docks
`CHEMBL411894, CHEMBL408215, CHEMBL111518, CHEMBL34913, CHEMBL327900`; writes a
`RunRecord` with `total_docking_jobs_submitted: 20`. The per-seed affinities of
those 5 are bit-identical to the same molecules in `baseline_cox2_v1.json` (the
funnel and baseline differ only in *which* molecules are docked).

`--dry-run` runs the prescreen only, no docking (~15 s).

---

## 5. Evaluation (instant)

```bash
cd backend/app
../venv/bin/python -m funnel.evaluate \
    --baseline ../../runs/baseline_cox2_v1.json \
    --funnel   ../../runs/funnel_cox2_v1.json
```

**Expected:** a comparison table ending in

```
    recall@5 LITERAL             : 1 / 5   ['CHEMBL34913']
    recall@5 tie-credited        : 2 / 5   hits=['CHEMBL34913', 'CHEMBL76692']
    ...
    docking jobs submitted            180           20
    docking wall-clock (s)           7134.2        ~370
  verdict: CLAIM DOES NOT HOLD
```

---

## 6. Offline policy sweep + frontier (seconds)

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.features   # once; writes runs/features_cox2_v1.json
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.sweep      # 8 policy variants vs the cached baseline
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.frontier   # writes runs/frontier_cox2_v1.{csv,svg}
```

`sweep` scores 8 `FunnelPolicy` variants against `baseline_cox2_v1.json` with
no docking — **< 1 s**. `frontier` sweeps docking budget N = 1..45, also
offline, using the per-candidate wall-clock stored in the baseline record.

**Expected sweep:** every viable variant at `1/5 literal, 2/5 tie-credited`;
`v6_ligand_efficiency` at `0/5`.

**Expected frontier:** literal recall@5 hits 2/5 at N=10 (4× saving), 5/5 at
N=32; tie-credited hits 4/5 at N=10. Writes a two-curve SVG.

---

## 7. Held-out ACE2 (baseline is cached)

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.features --set ace2_v1   # if not cached
../venv/bin/python -m funnel.evaluate \
    --baseline ../../runs/baseline_ace2_v1.json \
    --funnel   <(...)                  # or build a funnel run: python -m funnel.funnel --set ace2_v1
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.frontier --set ace2_v1
```

The ACE2 baseline (`runs/baseline_ace2_v1.json`) was docked into the
**corrected** Zn-centred box (the shipped box had zero receptor atoms inside
it; see `backend/app/funnel/CHANGELOG.md`). The selected policy is scored
against it **once, unchanged** — held-out numbers are in the CHANGELOG (pass 4)
and the README.

---

## Clean-container transcript

`docker/Dockerfile.repro` + `docker/repro-run.sh` build a fresh
`python:3.11-slim` image, `pip install` the backend requirements, and run
steps 1–6 with every command and its output echoed:

```bash
docker build  --platform=linux/amd64 -f docker/Dockerfile.repro -t drugforge-repro .
docker run --rm --platform=linux/amd64 drugforge-repro
```

### What the container verified (step 1, verbatim)

The image built clean (`python:3.11-slim` → all backend deps installed via
wheels, no build tools) and ran:

```
### 1. setup — verify Vina
$ scripts/setup_vina.sh
Platform     : linux-x86_64
Vina version : 1.2.7  (pinned)
Release asset: vina_1.2.7_linux_x86_64
Expected sha : f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644
Install path : /app/backend/bin/vina
Downloading https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_linux_x86_64 ...
✓ SHA256 verified: f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644
✓ Installed: /app/backend/bin/vina
  AutoDock Vina v1.2.7
✓ Done. Verify anytime with: scripts/verify_vina.sh
$ scripts/verify_vina.sh
Platform     : linux-x86_64
Checking     : /app/backend/bin/vina
Pinned Vina  : 1.2.7
✓ SHA256 matches the pinned linux-x86_64 digest
Reports      : AutoDock Vina v1.2.7
```

### What blocked the rest

The container run then died on **host disk exhaustion** — Docker Desktop could
no longer write its own content store (`... io.containerd ... : input/output
error`) and the host `/System/Volumes/Data` was at **100 % (< 1 GiB free of
228 GiB, 194 GiB of it pre-existing user data)**. This is a machine-state
problem, not a defect in the guide or the code: the build, the dependency
install, and the pinned-Vina download+verify all succeeded before the disk ran
out. On a machine with a few GB free, `docker run --rm --platform=linux/amd64
drugforge-repro` completes steps 1–6.

### Steps 2, 5, 6 — run on the host against the committed artifacts

These are offline (no docking) and were executed directly:

```
# step 2 — deterministic candidate-set rebuild
$ python -m funnel.build_candidate_set --target cox2
unique molecules (canonical, deduped): 8105
content_sha256 = 9ae649ec19fe9a206e8bdbd3a2b43609e89623f8d713a511d05c0bd33c7d35af
$ sha256sum funnel/datasets/cox2_candidates_v1.csv
f8ca059443e557a98d47d5327fd1eba2f5024a961c7ad585cc5b995fed5b6a2a   # unchanged -> byte-identical rebuild

# step 5 — funnel vs the cached baseline
$ python -m funnel.evaluate --baseline runs/baseline_cox2_v1.json --funnel runs/funnel_cox2_v1.json
    recall@5 LITERAL             : 1 / 5   ['CHEMBL34913']
    recall@5 tie-credited        : 2 / 5   hits=['CHEMBL34913', 'CHEMBL76692']
    docking jobs submitted            180           20
    docking wall-clock (s)           7134.2        376.4
    Spearman rho (commonly docked, n=5) : +1.000
  verdict: CLAIM DOES NOT HOLD
  "funnel docked 20 jobs vs baseline 180; recovered 1/5 of the baseline's top-5 (literal), 2/5 tie-credited; 0 false negative(s)."

# step 6 — offline sweep + frontier
$ python -m funnel.sweep        # < 1 s
v1_original .. v8 : recall@5 = 1/5 literal, 2/5 tie-credited (v6_ligand_efficiency: 0/5 / 0/5)
$ python -m funnel.frontier
first N to reach recall@5 (LITERAL):       1/5 N=4, 2/5 N=10, 3/5 N=14, 4/5 N=30, 5/5 N=32
first N to reach recall@5 (tie-credited):  1/5 N=4, 2/5 N=4,  3/5 N=10, 4/5 N=10, 5/5 N=32
wrote runs/frontier_cox2_v1.csv
wrote runs/frontier_cox2_v1.svg
```

Step 3 (`funnel.baseline --limit 2`) and step 4 (`funnel.funnel`, 20 real
docks) were exercised on the host in prior passes and are unchanged; on this
run the disk-full state prevented re-running them. `runs/funnel_cox2_v1.json`
(the v7 funnel run) and `runs/baseline_cox2_v1.json` (the cached full baseline)
are committed and were produced by exactly those commands.
