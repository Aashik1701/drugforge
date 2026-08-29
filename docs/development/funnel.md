# The computational funnel + baseline + eval

Code: `backend/app/funnel/`. No LLM, no planner, no candidate generation — a
deterministic, hardcoded policy that is designed to be swapped for a planner
later without touching anything else.

## What this proves (or disproves)

> "The advanced path docks **N** candidates and recovers the same (or better)
> top hits that the baseline found by docking all **M**."

The eval harness produces the headline: top-5 overlap, false-negative count,
wall-clock each path.

## The two paths

Both paths dock through the **exact same** compute fabric
(`tool_registry.get("run_docking")` → `compute_router.execute()` → `JobStore`
→ `LocalWorker` → Vina) with the **exact same** docking config. The *only*
difference is which candidates get docked.

| | baseline | funnel |
|---|---|---|
| candidates docked | all M | top N (`FunnelPolicy.top_n`, =5) |
| pre-dock filtering | none | SMILES validity → drug-likeness → toxicity |
| ranking of docked hits | `funnel.ranking.rank_docked` | same function |
| docking params | exhaustiveness 8, `--cpu 1`, seeds `[1, 42, 2024, 31337]`, conformer seed 42, num_modes 5 | identical |

Docking config rationale: `docs/development/local-worker.md` (§ "AutoDock Vina
— determinism"). Rank is on the **mean** best-affinity across the 4 seeds.
Near-ties (|Δmean| ≤ 0.10 kcal/mol or ≤ pooled seed stdev) share a rank and
carry a `tie_group` label — e.g. celecoxib/rofecoxib.

## The seam

`backend/app/funnel/policy.py` — `FunnelPolicy`. Every hard-filter threshold
and every ranking weight lives in this one dataclass. `funnel.funnel` contains
no magic numbers; it asks the policy. An LLM planner replaces this object and
nothing else changes. Any edit to it is logged in
`backend/app/funnel/CHANGELOG.md` (thresholds are never tuned to improve the
headline; only correctness fixes + data-derived feature scaling, both dated
relative to seeing results).

## Run record schema

`backend/app/funnel/schema.py` — `RunRecord`, schema `1.0.0`. Both paths emit
the identical shape to `runs/`. Funnel-only fields (`funnel_policy`,
`per_candidate`) are `null` in a baseline record; `filtered_out` is `[]` for
the baseline. Contains: run id / path / platform / vina version / docking
params / candidate-set id + size / per-stage survivor counts / total docking
jobs / total docking wall-clock / total run wall-clock / ranked results
`(ligand_id, smiles, mean_affinity, seed_stdev, per_seed_affinities)`.

## Candidate set

`backend/app/funnel/datasets/cox2_candidates_v1.csv` (`set_id = cox2_v1`),
provenance in the sibling `.provenance.md`. 45 molecules: 34 sampled
(stratified by pChEMBL, deterministic RNG) from
`ml/datasets/target_identification/COX-2.csv` — a **public ChEMBL bioactivity
export for CHEMBL230 (COX-2)** already vendored in this repo — plus the 11
reference ligands from `local-worker.md` so prior measurements stay
comparable. No molecules invented; no activity labels fabricated. Regenerate:

```bash
cd backend/app && ../venv/bin/python -m funnel.build_candidate_set
```

## Running it

```bash
scripts/setup_vina.sh                     # once, if backend/bin/vina is missing

# funnel + evaluate against the committed baseline reference artifact:
scripts/run_funnel_eval.sh

# also regenerate the (expensive) baseline from scratch first:
scripts/run_funnel_eval.sh --with-baseline

# funnel LOCAL stages only, no docking (inspect the prescreen):
scripts/run_funnel_eval.sh --dry-run
```

Or the modules directly (from `backend/app/`, `COMPUTE_MODE=balanced`):

```bash
../venv/bin/python -m funnel.baseline  --out ../../runs/baseline_cox2_v1.json
../venv/bin/python -m funnel.funnel    --out ../../runs/funnel_cox2_v1.json
../venv/bin/python -m funnel.evaluate  --baseline ../../runs/baseline_cox2_v1.json \
                                       --funnel   ../../runs/funnel_cox2_v1.json
```

Each `funnel.baseline` / `funnel.funnel` process starts its own `LocalWorker`
subprocess and its own private SQLite job store (`/tmp/funnel_*.db`), so it
never touches the dev `jobs.db`, and tears the worker down on exit.

## Baseline is cached

`runs/baseline_cox2_v1.json` is committed as a **reference artifact** so a
reviewer replays the comparison instead of re-docking ~M×4 jobs. It is
regenerated only with `--with-baseline` (or `python -m funnel.baseline`). It is
platform- and Vina-version-stamped; regenerate it if either changes (docked
affinities shift ~0.01 kcal/mol across ISAs, more across Vina versions).

## Pass 2 — offline policy sweep

`funnel/features.py` precomputes every candidate's LOCAL features once
(`runs/features_<set>.json`, no docking). `funnel/sweep.py` then scores any
number of `FunnelPolicy` variants against a cached baseline `RunRecord` in
milliseconds:

```bash
cd backend/app
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.features   # once per set
COMPUTE_MODE=balanced ../venv/bin/python -m funnel.sweep      # scores all declared variants
```

### recall@5 — reported two ways, LITERAL first

- **literal**: a baseline top-5 molecule is recovered only if it is *itself* in
  the policy's top-5.
- **tie-credited**: also counts a baseline top-5 molecule whose *tie-group
  partner* was picked.

Tie credit is defensible because tie-group members differ by **< TIE_EPSILON =
0.10 kcal/mol**, on the order of the docking method's own seed variance (median
seed σ = 0.036 kcal/mol on `baseline_cox2_v1`; celecoxib/rofecoxib differ by
0.045, ibuprofen/acetaminophen by 0.064). A pick within a tie group is a
coin-flip the docking cannot resolve. **Both numbers are always shown** —
`evaluate.py`, `sweep.py`, `frontier.py` (table, CSV, plot).

**Result on cox2_v1:** 8 variants. recall@5 flat at **1/5 literal, 2/5
tie-credited** for every viable ranker (ligand-efficiency collapsed to 0/5).
The baseline's top 3 docked hits carry no cheap signal — no reweighting
recovers them. Adopted `v7` (`binding_weak_cox2`: binding score primary,
P(cox2) demoted to a 0.15 tiebreak) on secondary metrics only (recall@10 9/10);
recall@5 is **not** improved. Full table: `backend/app/funnel/CHANGELOG.md`.

## Frontier (recall vs docking budget)

`funnel/frontier.py --set <id>` — offline, zero docking. For each budget N it
takes the policy's top-N prescreen picks, scores them against the cached
baseline, and estimates wall-clock from the baseline's per-candidate
`dock_wall_s`. Writes `runs/frontier_<set>.csv` and a two-curve
`runs/frontier_<set>.svg` (literal + tie-credited).

cox2_v1 shape: literal recall@5 hits **2/5 at N=10** (4× docking saving), 5/5
only at N=32; tie-credited hits **4/5 at N=10**. The funnel filters 4/45, so it
can never dock more than 41. **Recommended operating point: N=10.**

## Held-out second target — ACE2

The shipped `TARGET_CONFIG["ace2"]` box (`center [15.1, 22.5, 9.0]`) contained
**0 receptor atoms** — it sat ~70 Å off the active site. **Fixed** (pass 3):
re-centred on the catalytic Zn²⁺ (PDB 1R42, `[53.1, 68.6, 31.2]`), sanity-
checked (MLN-4760 −6.0, lisinopril −5.8, captopril −4.4, ethanol −2.6 kcal/mol
— monotone, discriminating). Candidate set `ace2_v1` built the same way as
`cox2_v1` (ChEMBL CHEMBL3736, 45 molecules). Held-out baseline
`runs/baseline_ace2_v1.json` + evaluation: see `CHANGELOG.md` pass 4.
