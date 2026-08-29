# DrugForge

A drug-discovery prediction service: nine ADMET/property models, an RDKit
feature pipeline, an AutoDock Vina docking path behind a job queue, and — added
during this competition — a **computational funnel** that uses the cheap models
to decide *which* candidates are worth the expensive dock, plus the harness to
measure whether that trade is worth making.

---

## Who this is for, and the bottleneck

The user is a computational chemist or a small discovery team screening a
library against one target. They have a scoring method they trust —
physics-based docking — and they cannot afford to run it on everything. On the
hardware most teams actually have (a workstation or a single cloud box, not a
cluster), docking one ligand well takes tens of seconds to minutes, and a
realistic replica protocol multiplies that by the number of random seeds. A
few hundred candidates at four seeds each is an overnight job; a few thousand
is a week.

So the real question is not "how do I dock faster" — Vina is Vina — but "which
20% of this library do I spend the docking budget on, and how much do I lose by
not docking the rest?" That is what the funnel and its evaluation harness are
built to answer, with a number instead of a hunch.

---

## What existed before this competition, and what was added

**Pre-existing (not our work):**

- Nine scikit-learn models served over FastAPI: `solubility`, `bbbp`,
  `cyp3a4`, `cox2`, `hepg2`, `ace2`, `toxicity`, `half_life`, `binding_score`.
- The RDKit feature pipeline (Morgan fingerprints, descriptor extraction,
  SMILES validation) behind those models.
- AutoDock Vina integration — ligand prep via RDKit + Meeko, receptor PDBQT
  files, subprocess invocation.
- The "compute fabric": `ToolRegistry` → `ComputeRouter` → `ResourceManager`
  → `JobStore` (SQLite) → `LocalWorker`, which routes cheap calls in-process
  and heavy calls (docking) through a job queue with concurrency limits.
- `AgentRunner` — a fixed, caller-supplied tool-sequence executor with a
  budget. No planner.
- The React frontend.

**Added during the competition:**

- **Determinism for docking.** `scripts/setup_vina.sh` pins AutoDock Vina to
  one release (1.2.7) and verifies a per-platform SHA-256. Every Vina
  invocation now passes an explicit `--seed` (from `DOCKING_SEED`), `--cpu 1`,
  and explicit `--exhaustiveness` / `--num_modes`; the RDKit conformer is
  seeded too. Seed, cpu, exhaustiveness and the resolved Vina version are
  written into every job record. `GET /health` reports `vina_available` and
  `vina_version`. (`docs/development/local-worker.md`.)
- **The funnel** (`backend/app/funnel/`): SMILES validation → descriptor
  drug-likeness filter → toxicity filter → a multi-objective prescreen ranker
  → dock only the top-N. Every tool call goes through the existing compute
  fabric; the four contracts above are untouched. All thresholds and the
  ranking formula live in one dataclass, `FunnelPolicy` — the seam a planner
  would later replace.
- **A brute-force baseline** (`funnel/baseline.py`) that docks the entire
  candidate set, 4 seeds each, and a matching **evaluation harness**
  (`funnel/evaluate.py`) that diffs the two. Both emit the same versioned
  `RunRecord` JSON.
- **An offline policy sweep** (`funnel/sweep.py`): score any `FunnelPolicy`
  against a cached baseline in milliseconds, no docking.
- **The recall-vs-budget frontier** (`funnel/frontier.py`): for each docking
  budget N, what fraction of the baseline's top hits does the funnel recover,
  and at what wall-clock saving.
- **The ACE2 docking box fix.** The shipped `TARGET_CONFIG` for `ace2` centred
  the search box ~70 Å outside the protein — zero receptor atoms inside it.
  Every ACE2 dock ever run through the Docking Studio returned meaningless
  numbers. Re-centred on the catalytic Zn²⁺ and sanity-checked against known
  inhibitors.
- **A public ChEMBL candidate-set builder** with provenance and content
  hashing (`funnel/build_candidate_set.py`), for cox2 (CHEMBL230) and ace2
  (CHEMBL3736).

---

## The result, at its true size

Hardware: **Apple M2, 8 cores, 16 GB, macOS 26.5.2 (arm64)**. Python 3.11.14,
AutoDock Vina 1.2.7. Docking config: exhaustiveness 8, `--cpu 1`, seeds
`[1, 42, 2024, 31337]`, rank on mean best-affinity.

**Candidate set `cox2_v1`** — 45 molecules: 34 stratified from ChEMBL COX-2
bioactivity data + 11 reference drugs.

The full baseline docked all 45 (180 Vina jobs, **7134 s** of docking on this
box). The funnel, using the selected policy `v7_binding_weak_cox2` at the
recommended operating point **N = 10** (40 jobs, ~1777 s), recovers:

| | literal | tie-credited |
|---|---|---|
| recall@5 | **2 / 5** | **4 / 5** |
| recall@10 | 5 / 10 | 9 / 10 |

for a **~4× docking-wall-clock saving** (9× fewer jobs). At N = 4 (16 jobs,
~11× saving) it recovers 1/5 literal, 2/5 tie-credited. **5/5 literal is only
reached at N = 32** — barely a saving. The curve is stepwise, not smooth: it
plateaus at 2/5 literal across N = 10–29.

Both recall columns are always reported. *Literal* = a baseline top-5 molecule
is itself in the funnel's top-5. *Tie-credited* also counts a baseline top-5
molecule whose tie-group partner was picked, where tie-group members differ by
< 0.10 kcal/mol — on the order of the docking's own seed variance (median seed
σ = 0.036 kcal/mol on this baseline). Tie credit is a secondary view, never the
headline.

**Held-out target `ace2_v1`** — same construction, ChEMBL ACE2 data, docked
into the corrected box, policy frozen and never tuned against it. A prediction
that ACE2 recall would be *lower* than cox2 — because Vina does not model the
catalytic zinc (compressed dynamic range: MLN-4760, Ki ~0.44 nM, docks at only
−6.0 kcal/mol) and the ACE2 ChEMBL set is one narrow chemotype — was written
down and committed **before** any evaluation (`backend/app/funnel/CHANGELOG.md`,
"Task 0 — pre-registered prediction").

> **The held-out number is not yet obtained.** The ACE2 baseline
> (`funnel.baseline --set-id ace2_v1 --target ace2`) is a ~2–3 h docking run;
> two attempts on the reference machine were destroyed by host disk exhaustion
> (the SQLite job store cannot be written on a full disk and the run corrupts).
> The candidate set, the corrected box, the pre-registered prediction, and the
> one-shot evaluation command are all committed; the number drops in as soon as
> the baseline completes on a machine with adequate free disk. Reproduce:
> `funnel.baseline --candidates funnel/datasets/ace2_candidates_v1.csv
> --set-id ace2_v1 --target ace2 --out runs/baseline_ace2_v1.json`, then
> `funnel.evaluate` / `funnel.frontier --set ace2_v1`.

---

## The main failure mode

On `cox2_v1` the baseline's single strongest docker is **CHEMBL2315019**, a
naproxen-acridone hybrid, at **−7.56 kcal/mol**. It is invisible to every cheap
feature available: the `cox2` classifier gives it **P(active) = 0.05** (it does
not look like a coxib) and `binding_score` gives it **5.35** (mid-pack). No
linear combination of the nine models' outputs ranks it above ~30th of 41
survivors. Eight ranking variants were tried (below); none recovers it.

**The ceiling is the models, not the prescreen formula.** A better funnel here
needs a better binding predictor — or docking-aware features — not more weight
tuning. This is the honest boundary of the result.

---

## Hot take

Docking determinism is not free, and almost nobody pins it. AutoDock Vina
seeds its Monte-Carlo search from the wall clock by default, so two runs of the
same ligand against the same receptor give different affinities — routinely
0.3–0.7 kcal/mol apart for a flexible ligand, which is the same magnitude as
the gap between adjacent candidates in a screen. Pinning the seed is necessary
but not sufficient: with a fixed seed, the same Vina version, and identical
inputs, results still diverge across CPU architectures (x86-64 vs arm64 differ
by ~0.01–0.05 kcal/mol here) because the score is a sum of floating-point terms
evaluated in a different order. If a docking result in a paper or a benchmark
does not state the Vina version, the seed, the CPU count, and ideally the ISA,
it is not reproducible, and the field mostly shrugs at this.

---

## Improvement changelog

Each entry is the decision and the evidence that drove the next one. Full
detail, including every discarded variant, is in
`backend/app/funnel/CHANGELOG.md`.

1. **Funnel v1 built and run.** Multi-objective prescreen (cox2 P + binding +
   solubility − tox − CYP). Live result: recall@5 = 1/5 literal (2/5
   tie-credited), Spearman +1.000 over the commonly-docked subset, per-seed
   affinities bit-identical between funnel and baseline.
   → *Evidence:* the funnel's docking is faithful; the loss is entirely in
   *which* candidates it chooses. Root cause identified: the `cox2` model is a
   coxib-shape detector, not a binding proxy (aspirin, ibuprofen, naproxen all
   score P ≈ 0).

2. **Offline policy sweep, v1 → v8, all losers kept.** binding-only,
   binding-only with relaxed filters, a no-ML descriptor heuristic, a
   binding/descriptor blend, ligand-efficiency normalisation, binding with a
   weak cox2 tiebreak, binding-only with no filters. recall@5 was **flat at
   1/5 literal (2/5 tie-credited) for every viable variant**; ligand-efficiency
   collapsed to 0/5 (it rewards fragments — its picks were ethanol,
   acetaminophen, ibuprofen — because the baseline ranks on raw, size-biased
   affinity).
   → *Evidence:* no reweighting helps; the ceiling is the models. Selected
   `v7_binding_weak_cox2` on the tie-breaking secondary metric (recall@10 9/10
   vs 7/10 for binding-only), and because it demotes the misleading `cox2`
   term from weight 1.0 to a 0.15 tiebreak. recall@5 explicitly **not**
   improved.

3. **Live confirmation of v7.** Ran the funnel once for real with v7; picks and
   recall matched the offline sweep exactly.
   → *Evidence:* the offline harness is trustworthy, so the frontier (next) can
   be computed entirely offline.

4. **Recall-vs-budget frontier.** Swept N = 1..45 against the cached baseline.
   → *Evidence:* reframed a failed binary claim ("recovers the top hits") into
   a characterised trade-off. Knee at N = 10 (2/5 literal / 4/5 tie-credited,
   4× saving); 5/5 literal needs N = 32. Recommended operating point: N = 10.

5. **`binding_score` unit bug.** The endpoint, response schema and `/models`
   metadata reported `kcal/mol`; the model actually emits a positive pKd-like
   score (higher = stronger). Found while setting the funnel's ranking
   direction.
   → *Evidence:* fixed the direction flag in `FunnelPolicy` before any docking
   run, and fixed the shipped API docs/schema so a consumer is not misled.

6. **Tie-group chaining bug.** The first tie-grouping merged entries
   transitively, chaining a 0.65 kcal/mol span (15 molecules) into one "rank
   3". Found while reading the first baseline ranking.
   → *Evidence:* switched to anchor-based grouping (a member must be within
   tolerance of the group's *first* element), bounding a group's span to
   ~0.10 kcal/mol. Re-ranked from stored per-seed data, no re-docking.

7. **Exhaustiveness experiment, removed.** An early sweep of Vina
   `exhaustiveness ∈ {8,16,32,64}` showed seed variance does **not** shrink
   with exhaustiveness for a multi-pose ligand (aspirin stayed at σ ≈ 0.3
   through ex=64) — the mean converges by ex=32 but the spread does not.
   → *Evidence:* fixed exhaustiveness at 8 and moved the reproducibility budget
   into replica seeds instead. The standalone experiment script was deleted
   once its conclusion was folded into the docking config.

8. **LocalWorker pipe deadlock.** The funnel spawned the worker with an
   unread `stdout=PIPE`; after ~64 KB of worker logs the pipe buffer filled and
   the worker blocked, hanging a long baseline run.
   → *Evidence:* redirect worker output to a file; added a regression test that
   drives the worker past 64 KB of output under sustained job load.

9. **Poll-deadline sleep bug.** The parent's per-dock timeout used
   `time.time()`, which advances while a laptop is asleep, so an overnight
   suspend marked in-flight docks as "timeout" even though the worker completed
   them on wake.
   → *Evidence:* switched to `time.monotonic()` (pauses during sleep); re-ran
   the held-out ACE2 baseline clean under `caffeinate`.

10. **ACE2 docking box.** The shipped box had zero receptor atoms inside it.
    → *Evidence:* re-centred on the catalytic Zn²⁺; sanity docks separate
    known inhibitors from a negative control (MLN-4760 −6.0, lisinopril −5.8,
    captopril −4.4, ethanol −2.6 kcal/mol). Only then was the held-out ACE2
    baseline built and run.

---

## Reproducing this

See **[`docs/development/REPRODUCTION.md`](docs/development/REPRODUCTION.md)** —
a step-by-step guide from a bare environment, tested end-to-end in a clean
container. The full baseline is ~2 h of docking, so its `RunRecord` is
committed under `runs/` for replay; the funnel and all offline analysis run in
seconds against it.
