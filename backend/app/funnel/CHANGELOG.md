# Funnel policy — change log

Every change to `funnel/policy.py` (`FunnelPolicy`: thresholds, weights, or
feature handling) is logged here. Per the build spec: thresholds are NOT tuned
to make the funnel-vs-baseline headline look better; only correctness fixes and
data-derived feature *scaling* are allowed, and both must be recorded with what
changed and when relative to seeing results.

## v1 — initial policy

Set from ADMET domain conventions (Lipinski / Veber) and permissive tox gates,
before any predictor output was inspected:

- Hard filters: MW ≤ 550, LogP ∈ [-1.0, 6.0], HBD ≤ 5, HBA ≤ 10, TPSA ≤ 150,
  RotB ≤ 12, P(toxicity) ≤ 0.80, P(hepG2-toxic) ≤ 0.80.
- Rank weights: cox2_active 1.00, binding 1.00, solubility 0.30,
  toxicity_penalty 0.50, cyp3a4_penalty 0.20.
- top_n = 5.

## v1.1 — binding-score direction fix (before any docking run)

**What:** `binding_lower_is_better` flipped `True → False`.

**Why:** the `--dry-run` (LOCAL stages only, no docking) showed the
`binding_score` model emits a **positive pAffinity-style score**, observed range
≈ 4.41–7.07 on `cox2_v1`, where higher = stronger binder (celecoxib 6.18,
rofecoxib 6.12, CHEMBL411894 7.07 vs aspirin 4.41, acetaminophen 4.68, ethanol
4.88). The initial `True` assumed Vina's "more negative = better" convention,
which does not apply to this ML model's own scale.

**When:** during the dry-run, before a single docking job was submitted for
either path. No funnel/baseline *results* had been produced, so this was not
results-driven tuning — it is a feature-direction correctness fix.

**Not changed:** every threshold and weight above is unchanged.

## Infra fixes during the first run (not policy, not tuning)

Bugs in the new harness code, found and fixed mid-build. None touch
`ComputeRouter` / `ResourceManager` / `JobStore` / the tool-registry contract,
and none change what gets docked or how it is scored.

1. **LocalWorker pipe deadlock.** `fabric.local_worker_process` piped the
   worker's stdout to an unread `subprocess.PIPE`; the worker is chatty
   (per-job logs + meeko/RDKit warnings) and the ~64KB OS pipe buffer filled,
   blocking its logging writes and hanging the baseline at candidate 14/45.
   Fix: worker stdout/stderr → a file (`/tmp/funnel_worker_*.log`).

2. **Job-store path race (funnel path only).** `funnel.funnel` ran the LOCAL
   screening phase — which triggers app startup and binds `main.job_store` to
   `JOB_STORE_PATH` — *before* setting that env var, so the parent used the
   default `jobs.db` while the LocalWorker used `/tmp/funnel_<run>.db`. Result:
   all 5 funnel docks reported FAILED (jobs written to a DB no worker polled).
   Fix: set `JOB_STORE_PATH` before the first `get_fabric_async()` in both
   `funnel.py` and `baseline.py`. (The baseline path happened to set it in the
   right order already; made explicit.)

3. **Tie-group chaining in `funnel.ranking`.** The first version grew a tie
   cluster while each entry was within `TIE_EPSILON` of the *previous* one,
   which transitively chained a 0.65 kcal/mol span (15 molecules) into one
   "rank 3". Fixed to anchor-based grouping: an entry joins only while within
   tolerance of the group's *first* member, bounding a group's span to
   ~`TIE_EPSILON`. Ranks are now always sequential (never collapsed). Applies
   identically to both paths; the baseline record was re-ranked from its
   stored per-seed affinities (no re-docking).

## Data-derived (not tuning)

`binding_norm` = min-max scaling of the `binding_score` predictions across the
funnel's filter survivors, computed at run time and recorded in the run
record's `notes` (`binding_min` / `binding_max`). This is feature
normalisation; it introduces no hand-set constant.

---

# Pass 2 — offline policy sweep on cox2_v1

## Held-out target — BLOCKED (reported, not improvised)

The plan was to validate the selected policy on a second target docked with a
held-out baseline. `backend/targets/` has exactly one other receptor, **ace2**
(`ace2_receptor.pdbqt`, from PDB 1R42). Its box in the shipped `TARGET_CONFIG`
is **`center=[15.1, 22.5, 9.0]`, `size=[20,20,20]`** — and **0 of the 6265
receptor atoms fall inside that box** (receptor spans X[19,97] Y[16,94]
Z[-8,60]; the catalytic Zn²⁺ that marks the ACE2 active site is at
(53.1, 68.6, 31.2), ~70 Å from the box centre). The same is true against the
raw 1R42 PDB, so it is not a coordinate-frame artefact — the shipped ACE2
docking box is simply wrong and would dock ligands into vacuum.

Per the task's explicit instruction ("if no second receptor has a usable box
definition, STOP and tell me before improvising one"), the held-out baseline
was **not launched** and no ACE2 box was invented. Task 4 is deferred pending a
decision on the box. (This is also a shipped-product bug — see Task 5 notes.)

## Variants — hypotheses declared BEFORE scoring (2026-08-28)

Ranking formulas live in `funnel/policy.py` (`FunnelPolicy.ranker` +
`filter_mode`). Cap: 8. Scored offline against `runs/baseline_cox2_v1.json`
using pre-cached LOCAL features (`runs/features_cox2_v1.json`) — no docking.

| id | ranker / filter | hypothesis |
|----|-----------------|------------|
| v1_current | v1_multiobjective, druglike+tox | known: recall 1/5. The `cox2` "shape detector" dominates the weighted sum. |
| v2_binding_only | binding_only, druglike+tox | If `binding_score` carries real binding signal, ranking on it alone (cox2 dropped) beats "looks like celecoxib". |
| v3_binding_only_tox_filter | binding_only, tox_only | Same ranker as v2 but the drug-likeness gate is dropped (safety filter only). Tests whether the MW/LogP gate is itself removing a real top binder (it cost us CHEMBL67659, baseline #14). |
| v4_descriptor_heuristic | descriptor_heuristic, druglike+tox | Pure physicochemistry (MW/LogP/TPSA/RotB/arom-rings profile), no ML at all. Sanity floor: does a drug-likeness prior alone match docking rank as well as the broken model? |
| v5_binding_desc_blend | binding_desc_blend (0.7/0.3), druglike+tox | Binding signal plus a mild drug-like prior — expected to beat either alone if binding_score is noisy. |
| v6_ligand_efficiency | ligand_efficiency (binding_score / heavy atoms), druglike+tox | Vina mean-affinity is size-biased; LE-normalising is the "correct" cheminformatics move but may *hurt* recall against a size-biased baseline. Testing the trade-off explicitly. |
| v7_binding_weak_cox2 | binding_weak_cox2 (binding_norm + 0.15·P(cox2)), druglike+tox | `cox2` is not anti-correlated with binding, just massively over-weighted in v1. A light tiebreak (0.15 vs 1.0) may edge out pure binding_only. |
| v8_binding_only_no_filter | binding_only, none | Upper bound for `binding_score` alone: dock the 5 highest predicted binders, no filters. Tells us if the filters help or hurt recall. |

Results (every variant, losers kept) are appended below after the sweep runs.

## Sweep results — cox2_v1 (offline, no docking; all 8 variants, losers kept)

recall@5 is TIE-CREDITED (a baseline top-5 molecule counts as recovered if it
OR a tie-group partner is selected — as the task specifies). Under this metric
v1 itself scores 2/5, not 1/5: it picks CHEMBL34913 (baseline #4, tie2) which
credits its tie-partner CHEMBL76692 (baseline #5).

| variant | ranker / filter | survivors | recall@5 | recall@10 | false-neg | mean baseline rank of 5 picked |
|---|---|---:|---:|---:|---:|---:|
| v1_current | v1_multiobjective / druglike+tox | 41 | **2/5** | 9/10 | 0 | 12.8 |
| v2_binding_only | binding_only / druglike+tox | 41 | **2/5** | 7/10 | 0 | 11.8 |
| v3_binding_only_tox_filter | binding_only / tox_only | 45 | **2/5** | 7/10 | 0 | 11.8 |
| v4_descriptor_heuristic | descriptor_heuristic / druglike+tox | 41 | **2/5** | 7/10 | 0 | 20.4 |
| v5_binding_desc_blend | binding_desc_blend / druglike+tox | 41 | **2/5** | 7/10 | 0 | 11.8 |
| v6_ligand_efficiency | ligand_efficiency / druglike+tox | 41 | **0/5** | 3/10 | 0 | 40.8 |
| v7_binding_weak_cox2 | binding_norm + 0.15·P(cox2) / druglike+tox | 41 | **2/5** | 9/10 | 0 | 12.6 |
| v8_binding_only_no_filter | binding_only / none | 45 | **2/5** | 7/10 | 0 | 11.8 |

**No variant clears a meaningful improvement on recall@5** — it is flat at 2/5
for every viable ranker. Reason (from the sweep detail): the baseline's top 3
docked hits carry no cheap signal —

| ligand | baseline rank / affinity | cox2 P(act) | binding_score | best policy rank (of ~41) |
|---|---|---:|---:|---:|
| CHEMBL2315019 | #1 / -7.56 | 0.05 | 5.35 | p#29 (v2) |
| CHEMBL184613 | #2 / -6.81 | 0.69 | 5.17 | p#24 (v1) |
| CHEMBL111786 | #3 / -6.76 | 0.99 | 6.26 | p#7 (v1), p#10 (v7) |

Only CHEMBL111786 is anywhere near reachable, and only recall@10 catches it
(v1, v7). CHEMBL34913 (#4, a real coxib: cox2 0.74, binding 6.79) is the one
top-5 molecule every viable policy finds; CHEMBL76692 (#5) comes via tie credit.

v6 (ligand efficiency) is a genuine loser: dividing binding_score by heavy-atom
count rewards tiny fragments (its picks: ethanol, acetaminophen, ibuprofen,
ferulate, esketamine — baseline ranks 45/40/39/37/43), because the baseline
ranks on raw (size-biased) mean affinity. Confirmed the hypothesis that LE
fights a size-biased baseline.

v4 (pure physicochemistry, no ML) matches the ML variants on recall@5 (2/5) but
picks worse-docking molecules overall (mean rank 20.4) — a drug-likeness prior
alone is not worse than the broken `cox2` model at finding the tie2 cluster,
but it is worse at everything else.

## v7 adopted (recall@5 NOT improved; adopted on secondary grounds)

`DEFAULT_POLICY` ranker `v1_multiobjective` -> `binding_weak_cox2`
(`binding_norm + 0.15 * P(cox2)`), filters unchanged.

- recall@5: 2/5 -> 2/5 (**no change** — stated plainly).
- recall@10: 9/10 (tied best), mean baseline rank of picks 12.8 -> 12.6.
- Rationale: removes the `cox2` shape-detector's *dominance* (weight 1.0 -> 0.15
  as a tiebreak only) while — per the sweep data, not tuning — keeping the one
  near-miss (CHEMBL111786, cox2 P=0.99) in top-10 reach, which pure
  binding_only loses (7/10). No weights were searched; 0.15 is the single
  declared `weak_cox2_coeff`.
- This is not a "fix" for recall@5. The honest finding is that cheap
  prescreening cannot recover this baseline's top hits; see the table above.

## v7 live confirmation on cox2_v1 (Task 3) — offline harness VALIDATED

Ran `funnel.funnel` once for real with v7 (20 docks, 376 s). Offline sweep
predicted v7's picks and recall; the live run reproduces them exactly:

| | offline sweep (from cached baseline) | live run (fresh docks) |
|---|---|---|
| picks (baseline rank) | 411894#22, 408215#19, 111518#8, 34913#4, 327900#10 | **same five** |
| recall@5 (tie-credited) | 2/5 (CHEMBL34913, CHEMBL76692) | **2/5 (CHEMBL34913, CHEMBL76692)** |
| literal top-5 overlap | 1/5 | 1/5 |

Per-seed docked affinities for all 5 are bit-identical to `baseline_cox2_v1.json`
(the funnel and baseline still differ ONLY in which molecules are docked).
Spearman rho over the 5 commonly-docked = +1.000. 0 false negatives.
`runs/funnel_cox2_v1.json` now holds the v7 run.

**Bottom line for Task 3:** offline prediction == live result (no harness bug);
recall@5 unchanged at 2/5; the prescreen is not "fixed" — the baseline's top 3
docked hits carry no cheap signal that any of the 8 tested policies can exploit.
