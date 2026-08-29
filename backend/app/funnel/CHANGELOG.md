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

| variant | ranker / filter | survivors | recall@5 literal | recall@5 tie-cred | recall@10 lit / tie | false-neg | mean baseline rank |
|---|---|---:|---:|---:|---:|---:|---:|
| v1_original | v1_multiobjective / druglike+tox | 41 | **1/5** | **2/5** | 5/10 / 9/10 | 0 | 12.8 |
| v2_binding_only | binding_only / druglike+tox | 41 | **1/5** | **2/5** | 4/10 / 7/10 | 0 | 11.8 |
| v3_binding_only_tox_filter | binding_only / tox_only | 45 | **1/5** | **2/5** | 4/10 / 7/10 | 0 | 11.8 |
| v4_descriptor_heuristic | descriptor_heuristic / druglike+tox | 41 | **1/5** | **2/5** | 3/10 / 7/10 | 0 | 20.4 |
| v5_binding_desc_blend | binding_desc_blend / druglike+tox | 41 | **1/5** | **2/5** | 4/10 / 7/10 | 0 | 11.8 |
| v6_ligand_efficiency | ligand_efficiency / druglike+tox | 41 | **0/5** | **0/5** | 1/10 / 3/10 | 0 | 40.8 |
| v7_binding_weak_cox2 | binding_norm + 0.15·P(cox2) / druglike+tox | 41 | **1/5** | **2/5** | 5/10 / 9/10 | 0 | 12.6 |
| v8_binding_only_no_filter | binding_only / none | 45 | **1/5** | **2/5** | 4/10 / 7/10 | 0 | 11.8 |

**No variant clears a meaningful improvement on recall@5** — flat at 1/5 literal, 2/5 tie-credited
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

v4 (pure physicochemistry, no ML) matches the ML variants on recall@5 (1/5 lit, 2/5 tie) but
picks worse-docking molecules overall (mean rank 20.4) — a drug-likeness prior
alone is not worse than the broken `cox2` model at finding the tie2 cluster,
but it is worse at everything else.

## v7 adopted (recall@5 NOT improved; adopted on secondary grounds)

`DEFAULT_POLICY` ranker `v1_multiobjective` -> `binding_weak_cox2`
(`binding_norm + 0.15 * P(cox2)`), filters unchanged.

- recall@5: 1/5 literal / 2/5 tie-credited -> unchanged (**no change** — stated plainly).
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
| recall@5 literal / tie-cred | 1/5 / 2/5 (CHEMBL34913, CHEMBL76692) | **1/5 / 2/5 (same)** |
| literal top-5 overlap | 1/5 | 1/5 |

Per-seed docked affinities for all 5 are bit-identical to `baseline_cox2_v1.json`
(the funnel and baseline still differ ONLY in which molecules are docked).
Spearman rho over the 5 commonly-docked = +1.000. 0 false negatives.
`runs/funnel_cox2_v1.json` now holds the v7 run.

**Bottom line for Task 3:** offline prediction == live result (no harness bug);
recall@5 unchanged (1/5 literal, 2/5 tie-credited); the prescreen is not "fixed" — the baseline's top 3
docked hits carry no cheap signal that any of the 8 tested policies can exploit.

---

# Pass 3

## Task 1 — recall vs docking-budget frontier (offline, cox2_v1, policy v7)

`funnel/frontier.py` sweeps N = 1..45 against `runs/baseline_cox2_v1.json` with
zero docking. Estimated wall-clock is summed from the per-candidate `dock_wall_s`
already in the baseline record. Artifacts: `runs/frontier_cox2_v1.csv`,
`runs/frontier_cox2_v1.svg`.

The funnel filters 4 of 45 candidates (drug-likeness), so its docking pool is
**41** — it can never reach N > 41, and the last 4 recall points beyond N≈32
come from candidates the *baseline* docked that the funnel's prescreen buries.

| recall@5 first reached at N (jobs=4N) | LITERAL | tie-credited | est. dock wall / saving vs full 180-job baseline |
|---|---|---|---|
| 1/5 | N=4 (16) | N=4 (16) | ~644 s / **11.1×** |
| 2/5 | N=10 (40) | N=4 (16) | lit ~1777 s / **4.0×**;  tie ~644 s / **11.1×** |
| 3/5 | N=14 (56) | N=10 (40) | lit ~2172 s / 3.3×;  tie ~1777 s / 4.0× |
| 4/5 | N=30 (120) | N=10 (40) | lit ~4016 s / 1.8×;  tie ~1777 s / 4.0× |
| 5/5 | N=32 (128) | N=32 (128) | ~4321 s / 1.7× |

recall@10 (literal / tie-credited): 2 / 6 at N=4, 5 / 9 at N=10, 9 / 10 at N=32.

Marginal efficiency of recall@5(tie): 0→2 costs 4 candidates (0.50/cand);
2→4 costs 6 (0.33/cand); 4→5 costs **22** (0.045/cand) — a 7× efficiency drop.

**Recommended operating point: N = 10.** recall@5 = **2/5 literal, 4/5
tie-credited**, recall@10 = 5/10 literal, 9/10 tie-credited, ~4× docking saving (40 jobs vs 180, ~1.8 ks vs
7.1 ks). It is the knee: below it you sit at 2/5; above it, 22 more candidates
(88 jobs) buy exactly one more recall point, because CHEMBL2315019 — the single
strongest docker (−7.56) — has cox2 P=0.05 and binding_score 5.35 and the
prescreen ranks it 32nd of 41. A cheaper option is **N = 4** (2/5 tie, 11×
saving) if only the easy hits matter.

Framed as asked: *to recover 4 of the baseline's top 5 (tie-credited) the funnel
docks 10 candidates instead of 45 — a 4.5× candidate / ~4× wall-clock saving. It
does not reach 5/5 below N=32 (≈1.7× saving); the curve plateaus at 2/5 across
N=4–9 and at 4/5 across N=10–31.*

## Task 2 — ACE2 docking box fixed (was a shipped bug)

**The shipped `TARGET_CONFIG["ace2"]` box was wrong.** `center=[15.1, 22.5, 9.0]`,
20 A cube — **0 of the 6265 receptor atoms fall inside it** (the box sits ~70 A
outside the ACE2 structure). Every docking job submitted with `target=ace2`
(offered in the frontend Docking Studio and `/api/dock/*`) has been docking
ligands into empty space and returning meaningless affinities.

**New box:** centred on the **catalytic Zn2+** of ACE2 (PDB 1R42:
53.141, 68.638, 31.204 → recorded as `[53.1, 68.6, 31.2]`), 20 A cube (matches
the cox2 box size). Centring on the catalytic metal is standard practice for a
metalloprotease; 1R42 is the apo structure so there is no co-crystal ligand to
centre on. The new box contains **361 receptor atoms (5.8%)** — comparable to
the working cox2 box (270 atoms, 1.2%).

**Sanity docks** (ex=8, --cpu 1, seeds [1,42,2024,31337], conformer seed 42;
mean best affinity, kcal/mol):

| ligand | mean | sd | note |
|---|---:|---:|---|
| MLN-4760 | **-6.00** | 0.36 | canonical ACE2 inhibitor, Ki ~0.44 nM |
| lisinopril | **-5.80** | 0.25 | ACE inhibitor, weak ACE2 binder |
| captopril | **-4.39** | 0.02 | ACE inhibitor, weak ACE2 binder |
| ethanol | **-2.65** | 0.00 | negative control |

**PASS** — monotone MLN-4760 > lisinopril > captopril > ethanol (matches known
potency order); every known binder is ≥1.5 kcal/mol stronger than the control
(weakest gap 1.75); MLN-4760 at -6.0 is a plausible inhibitor range for a blind
20 A dock. The box discriminates.

Fixed in three places (kept in sync): `app/routers/dock.py`,
`app/jobs/workers/docking_worker.py`, `download_targets.py`. No docking
parameters changed — only the ace2 box centre.

## Task 3 — held-out ACE2 baseline: candidate set built, baseline LAUNCHED

Task 2 passed, so the held-out baseline proceeds.

**Candidate set `ace2_v1`** — same builder, same pipeline as `cox2_v1`
(`build_candidate_set.py` refactored to `--target {cox2,ace2}`; cox2 output
re-verified byte-identical, sha `9ae649ec…`).
- source: `ml/datasets/target_identification/ACE-2.csv` (ChEMBL **CHEMBL3736**,
  Angiotensin-converting enzyme 2, Homo sapiens).
- 190 rows → 0 no-SMILES, 0 parse fail, 54 set-filtered, **122 unique**.
- stratified sample {potent 14, moderate 13, weak 14} + 4 references
  (MLN-4760, lisinopril, captopril, ethanol — the Task-2 sanity ligands).
- **45 molecules**, content_sha256 `b55d875f1ad82fec5122cf54ce0730f41176621a1c617c2a59dd9296368f42ca`.
- `funnel/datasets/ace2_candidates_v1.csv` + `.provenance.md`.

**Baseline run** (background, output to a FILE): `funnel.baseline
--candidates … --set-id ace2_v1 --target ace2`, docking into the NEW Zn-centred
box, ex=8, --cpu 1, seeds [1,42,2024,31337], RunRecord v1.0.0 →
`runs/baseline_ace2_v1.json`. Smoke (2 candidates) reproduced the Task-2 sanity
affinities bit-identically (captopril −4.393, identical per-seed).

NOT evaluated against the selected policy this pass — held out.

---

# Pass 4

## Task 0 — PRE-REGISTERED prediction for the held-out ACE2 evaluation (2026-08-29)

Written and committed BEFORE scoring the selected policy against
`runs/baseline_ace2_v1.json`. The selected policy (`v7_binding_weak_cox2`) is
frozen; it was chosen only on `cox2_v1`; `baseline_ace2_v1.json` has not been
used for any selection or tuning and will not be.

**Prediction: held-out recall on ace2_v1 will likely be LOWER than on cox2_v1,
for reasons intrinsic to the target and the candidate set — not the policy.**

1. **Vina does not model Zn²⁺ coordination.** ACE2 is a zinc metalloprotease;
   its inhibitors chelate the catalytic Zn. Vina scores this pocket with a
   generic force field, so the dynamic range is compressed — the Task-2 sanity
   check put MLN-4760 (Ki ~0.44 nM) at only −6.0 kcal/mol, ~2 kcal/mol from a
   non-binder. A compressed baseline spread means small prescreen errors flip
   more rank positions, so recall@k is mechanically harder to hit.
2. **`ace2_v1` is chemotype-narrow.** 122 unique molecules from ChEMBL, heavily
   one scaffold family (Phe-Pro dipeptide mimics with thiol / phosphinic /
   boronic warheads). The `binding_score` and `cox2` models were trained on
   broad, mostly non-peptidic data; on a narrow peptidomimetic set their
   ranking signal is expected to be weaker and less differentiated than on the
   diverse `cox2_v1` (8105 unique).
3. Corollary: a drop is expected to reflect (1)+(2), NOT a defect in the funnel
   mechanics, the ranking function, or the v7 policy. The cox2 finding —
   "recall@5 ceiling is the models, not the prescreen formula" — is expected to
   hold or strengthen on ace2.

**Falsifiable expectations, in order of confidence:**
- literal recall@5 on ace2 ≤ literal recall@5 on cox2 (which is 1/5 at N=10).
- tie-credited recall@5 on ace2 < 4/5 at N=10 (the cox2 value).
- 0 hard false negatives (the drug-likeness/tox filter should not be the cause
  of any miss — as on cox2).
- If recall is *higher* on ace2, that would be a surprise and I would want to
  understand why before trusting it.

**Disclosure:** while diagnosing an infrastructure failure in the first ACE2
baseline run (a `time.time()`-based poll deadline that a laptop sleep blew,
producing spurious FAILED docks — now fixed to `time.monotonic()`), roughly ten
individual raw ACE2 affinity values were visible in a log tail. No ranking,
recall, or policy comparison was computed from them; that first run is being
discarded and re-docked clean. This pre-registration and its commit precede any
evaluation of the clean artifact.

## Task 2 (pass 4) — recall reporting: LITERAL + tie-credited everywhere, literal first

The tie-credited number does not stand alone. Every place a recall figure
appears now shows **literal first, then tie-credited**:
`funnel/evaluate.py` output, `funnel/sweep.py` table + per-variant detail,
`funnel/frontier.py` table + `runs/frontier_*.csv` (columns `recall5_literal`,
`recall5_tiecredit`, `recall10_literal`, `recall10_tiecredit`) +
`runs/frontier_*.svg` (four curves, literal-first legend),
`docs/development/funnel.md`, and the tables above in this file.

**Why tie credit is defensible (one line):** tie-group members are separated by
less than `TIE_EPSILON = 0.10 kcal/mol` — on the order of the docking method's
own measured seed variance (median seed σ = **0.036 kcal/mol** across the 45
`baseline_cox2_v1` candidates; celecoxib/rofecoxib differ by 0.045,
ibuprofen/acetaminophen by 0.064). Picking one member of a tie group over
another is a coin-flip the docking cannot resolve, so it is not scored as a
miss. It is a *secondary* view, never the headline.

cox2_v1 corrected headline: **recall@5 = 1/5 literal, 2/5 tie-credited** for
every viable policy (v6 = 0/5 both). Frontier knee at N=10: **2/5 literal, 4/5
tie-credited**, 4× docking saving.

## Task 1 & 4 (pass 4) — BLOCKED by host disk exhaustion

The reference machine (Apple M2, 228 GiB disk) filled during this pass:
`/System/Volumes/Data` reached 100 % with **< 1 GiB free** (194 GiB pre-existing
user data, not touchable). Two things could not complete:

1. **Held-out ACE2 evaluation (Task 1).** The ACE2 baseline docking run
   (`funnel.baseline --set-id ace2_v1 --target ace2`, ~2–3 h, 180 Vina jobs)
   was launched twice:
   - Run 1 (`baseline_ace2` PID 27106): laptop slept overnight; the poll
     deadline used `time.time()` (advances during sleep) and marked in-flight
     docks "timeout" though the worker completed them on wake. Discarded.
     **Fix committed (`3297f70`): `_dock_one` now uses `time.monotonic()`.**
   - Run 2 (clean, under `caffeinate`, monotonic deadline): got to ~4/45 then
     the disk filled; SQLite (`/tmp/funnel_baseline_*.db`) could no longer be
     written and the job store corrupted (`OperationalError: no such table:
     jobs`), killing the worker. Unrecoverable.

   The held-out number is therefore **not obtained this pass**. Everything
   needed to get it is in place and untouched: the frozen policy
   (`v7_binding_weak_cox2`), the `ace2_v1` candidate set (sha
   `b55d875f…`), the corrected Zn-centred box, the pre-registered prediction,
   and the one-shot commands. It runs on any machine with a few GB free.

2. **Clean-container reproduction (Task 4).** `docker/Dockerfile.repro` +
   `docker/repro-run.sh` build from `python:3.11-slim` and execute
   REPRODUCTION.md steps 1–6. The container **built clean, installed every
   backend dependency, and ran `scripts/setup_vina.sh` + `scripts/verify_vina.sh`
   successfully** (verbatim transcript in `REPRODUCTION.md`). It then died when
   Docker Desktop could not write its own content store (`io.containerd …:
   input/output error`) — the same disk-full condition. Steps 2, 5, 6 were run
   on the host against the committed artifacts and match the guide; steps 3–4
   (docking) are unchanged from prior passes and their outputs
   (`runs/funnel_cox2_v1.json`, `runs/baseline_cox2_v1.json`) are committed.

Not a code or guide defect — a machine-state blocker. Stated plainly rather
than worked around by deleting the user's data.
