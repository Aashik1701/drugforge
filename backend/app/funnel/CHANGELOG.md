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

---

# Pass 5 — surrogate ranker trained on real docking scores (2026-08-29)

## Question

Does a regressor trained on this target's own real Vina mean-affinities beat the
frozen v7 prescreen? Offline, against `runs/baseline_cox2_v1.json`, no new
docking. Established prior: recall@5 is flat at 1/5 literal across all 8 policy
variants; the stated read was "the ceiling is the models, not the ranking
formula."

## Setup (`funnel/surrogate.py`, additive + offline)

- **Label:** mean best-affinity over 4 seeds, from `baseline_cox2_v1.json`
  (45 molecules, no failed docks).
- **Features:** ECFP4 Morgan fingerprint (radius 2, 1024 bits — identical to
  `utils/rdkit_helper.extract_features` and
  `ml/training/train_all_models.smiles_to_fingerprint`) concatenated with the 10
  RDKit descriptors already cached in `runs/features_cox2_v1.json`. 1034
  features, n = 45. No new featurisation.
- **CV:** leave-one-out, 45 folds. Every molecule's predicted affinity comes
  from a model refit on the other 44; scaler / kernel refit inside each fold.
  The fit-on-everything number is reported only as a leaked upper bound.
- **3 variants, fixed hyper-parameters, no grid search:** `ridge`
  (StandardScaler + Ridge alpha=10), `rf` (RandomForestRegressor, 300 trees,
  seed 0), `krr_tanimoto` (KernelRidge alpha=1 on a Tanimoto Gram matrix of the
  fingerprint bits).
- **Primary chosen by LOO affinity Spearman, before any recall number was
  looked at.** Ranker = sort ascending on predicted affinity. Scored with the
  existing recall@5 / recall@10 / frontier logic, over the same 41 v7
  hard-filter survivors as `runs/frontier_cox2_v1.csv`.

## Affinity regression (leave-one-out)

| variant | R2 | MAE | RMSE | Spearman rho | Pearson r |
|---|---:|---:|---:|---:|---:|
| ridge | 0.337 | 0.456 | 0.649 | 0.607 | 0.584 |
| **rf** (primary) | **0.401** | **0.440** | **0.617** | **0.679** | 0.665 |
| krr_tanimoto | -2.738 | 1.329 | 1.541 | 0.482 | 0.581 |

Small-n caveat: 45 points, 1034 features, LOO — intervals are wide. Read
R2 ~ 0.34-0.40, rho ~ 0.6-0.68 as "modest but real signal for docking score"
(the prescreen models were not even trying to predict this quantity), not a
calibrated model. `krr_tanimoto` is a genuine loser: the Tanimoto neighbourhood
over 44 points is too sparse and alpha=1 too weak; kept as a logged negative.

Leaked upper bound (fit on all 45, predict all 45): ridge in-sample R2 = 0.999,
recall@5 = 5/5 — pure memorisation of 1034 features over 45 rows. This is why
LOO is mandatory; it is not a result.

## CHEMBL2315019 — the named failure mode (headline)

Baseline #1, true -7.56 kcal/mol (a 0.75 kcal/mol outlier above #2).

| variant | LOO predicted affinity | rank / 41 survivors | first docked at N |
|---|---:|---:|---:|
| ridge | -5.96 | 15 | 15 |
| rf | -5.89 | 18 | 18 |
| krr_tanimoto | -4.29 | 26 | 26 |

**The surrogate does not surface it.** Every variant under-predicts it by
1.6-3.3 kcal/mol and ranks it 15th-26th; it is never in a surrogate top-5. It is
the one molecule in the set with no close structural analogue (a
naproxen-acridone hybrid) and an outlier label, so a LOO model has nothing to
interpolate from and shrinks it toward the set mean.

## Frontier: frozen v7 vs surrogate (rf primary), recall literal, over the 41 survivors

| milestone | v7: first N | surrogate: first N |
|---|---:|---:|
| recall@5 = 1/5 | 4 | 6 |
| recall@5 = 2/5 | 10 | 12 |
| recall@5 = 3/5 | 14 | 13 |
| recall@5 = 4/5 | 30 | 18 |
| **recall@5 = 5/5** | **32** | **21** |
| recall@10 = 8/10 | 30 | 18 |
| **recall@10 = 10/10** | **36** | **21** |

Strict cut (N=5): v7 = 1/5 literal (2/5 tie-credited); surrogate-rf = **0/5**
literal (0/5 tie); surrogate-ridge = 1/5 literal (2/5 tie), matching v7. Below
N ~ 13 the surrogate is level with or behind v7. From N ~ 13 up it pulls clearly
ahead: full top-5 recovery at N=21 (2.3x saving) vs v7's N=32 (1.6x), and full
top-10 recovery at N=21 vs v7's N=36. Ridge gives the same shape (5/5 at N=20) —
not a one-model artefact.

Artifacts: `runs/surrogate_cox2_v1.json`, `runs/frontier_surrogate_cox2_v1.csv`,
`runs/frontier_surrogate_cox2_v1.svg`.

## Conclusion

**The surrogate does NOT beat v7 where it matters most, and DOES beat it on the
rest of the curve — the split is the finding.**

1. **The named failure mode is a data-coverage problem, not a feature or formula
   problem.** CHEMBL2315019 is an out-of-distribution singleton in a 45-molecule
   set. No LOO regression on these features recovers it, just as no reweighting
   of the 8 prescreen variants did. Fixing it needs more candidates (so it has
   neighbours) or docking-aware features / actually docking it — not a better
   cheap ranker.
2. **The mid-pack was partly a ranking-formula problem after all.** A surrogate
   on the *same* fp + descriptors the prescreen already had, but fit on real
   docking labels, cuts the budget for full top-5 recovery from N ~ 32 to
   N ~ 20-21 and for full top-10 from N ~ 36 to N ~ 21 — a real ~1.4-1.5x
   further docking saving on top of v7's, holding for both ridge and rf. So the
   earlier "the ceiling is the models, not the formula" is too strong: it holds
   for the #1 outlier, not for baseline ranks ~ 6-20.
3. **This surrogate is target-specific.** It was trained on cox2's own docking
   results. It is not a general-purpose prescreen: any new target would need a
   seed batch of ~40 docks before the surrogate could rank anything, where the
   frozen v7 policy needs zero.
4. **Anti-leakage discipline cost the headline.** The affinity-best model (rf,
   LOO rho = 0.679) is *worse* at strict recall@5 (0/5) than ridge (1/5) or v7
   (1/5). Choosing the primary by affinity and reporting recall once — not
   picking the model that happened to hit the top-5 — is what makes the mixed
   result trustworthy.

Frozen contracts untouched: v7 policy, docking params, ComputeRouter /
ResourceManager / JobStore / tool-registry unchanged. `funnel/surrogate.py` is
additive and offline. ace2 data not read.

---

# Pass 6 — two-phase adaptive funnel: does a small real-label seed batch beat a cold-start ranker? (2026-08-29)

## Question

Pass 5's surrogate needs ~44 real docking labels (leave-one-out over all 45) to
beat v7 from N ~ 13 up. That is not a policy anyone could run cold — you would
have needed to dock nearly everything already. The realistic version: **spend
a small seed batch of real docks chosen by v7 alone, fit a target-specific
surrogate on just that seed batch, then spend the rest of the budget on what
the surrogate now says.** Does that two-phase policy earn back any of Pass 5's
advantage at a budget an actual campaign could commit to up front? Offline,
against the cached `baseline_cox2_v1.json`, no new docking.

## Policy (`funnel/two_phase.py`)

- **Phase 1:** rank the 41 v7-hard-filter survivors with the frozen v7 formula
  alone. Dock the top-S ("seed batch").
- **Phase 2:** fit a RandomForestRegressor (`n_estimators=300, random_state=0`
  — Pass 5's `rf` variant, unchanged, no hyperparameter search) on ONLY the
  seed batch's S real mean-affinities. Rank the remaining 41-S survivors with
  it. Dock the next (N-S).
- Union ranked on mean affinity (`funnel.ranking`, the one ranking function
  everywhere else uses) to produce the funnel's final shortlist.

**Declared S range, frozen before running:** `{5, 8, 10, 13, 16, 20}`. N swept
from S to 41 for each S — 180 (S, N) cells total. Not extended after seeing
results.

## Leakage guards (asserted in code, not just intent)

- **G1** — `seed_batch_for_S(v7_order, S)` takes only the pre-computed v7
  prescreen order as its argument. That order comes from
  `funnel.frontier.prescreen_order(DEFAULT_POLICY, features, candidate_ids)`,
  which reads only the frozen policy and cached features — never the
  baseline, never Pass 5's OOF predictions. There is no such argument for the
  function to consult even by accident.
- **G2** — `fit_phase2()` asserts `x_tr.shape[0] == S` and `y_tr.shape[0] ==
  S` immediately before every `model.fit()` call, and asserts the training ids
  and the held-out remainder ids are disjoint. `y_tr` is built by dict lookup
  keyed only on the seed ids, so no label outside the seed batch can enter
  training. Every Phase-2 prediction comes from a model that has seen exactly
  S real affinities.

Both guards ran clean on all 180 cells — no assertion fired.

## Phase-2 fit quality vs. S (Spearman, predicted vs. true, on the held-out remainder)

| S | held-out n | Spearman rho | MAE | seed-batch affinity range (kcal/mol) |
|---:|---:|---:|---:|---|
| 5  | 36 | **-0.334** | 0.748 | [-6.61, -5.73] (0.9 kcal/mol wide) |
| 8  | 33 | **-0.412** | 0.725 | [-6.61, -5.73] (0.9 kcal/mol wide) |
| 10 | 31 | +0.198 | 0.730 | [-6.76, -5.71] (1.1 kcal/mol wide) |
| 13 | 28 | +0.411 | 0.627 | [-6.76, -5.12] (1.6 kcal/mol wide) |
| 16 | 25 | +0.733 | 0.602 | [-6.76, -5.12] (1.6 kcal/mol wide) |
| 20 | 21 | +0.701 | 0.524 | [-6.76, -4.75] (2.0 kcal/mol wide) |

Full 45-molecule affinity range for reference: [-7.56, -2.52], 5.0 kcal/mol
wide. **Below S=13 the fit is noise or worse than noise** (negative rho at
S=5, S=8 — a RandomForest with 300 trees given 5-8 points cannot do anything
but overfit). Real signal starts at S=13 and is not obviously still improving
by S=20 (0.733 -> 0.701, inside noise for these sample sizes).

## The (S, N) grid — recall@5 literal milestones

First N at which each S reaches literal recall@5 = 5/5, against the two
references at the same metric:

| policy | first N at literal 5/5 | jobs |
|---|---:|---:|
| frozen v7 (reference) | 32 | 128 |
| Pass-5 LOO surrogate, rf (reference) | 21 | 84 |
| two-phase S=5 | 33 | 132 |
| two-phase S=8 | 39 | 156 |
| two-phase S=10 | 40 | 160 |
| two-phase S=13 | 28 | 112 |
| **two-phase S=16 (best)** | **26** | **104** |
| two-phase S=20 | 30 | 120 |

Full grid: `runs/two_phase_cox2_v1.csv` / `.json`. Plot (three curves — v7,
Pass-5 rf surrogate, two-phase S=16 — recall@5 literal vs N):
`runs/two_phase_cox2_v1.svg`.

## Task 3 — is S=16 a real optimum, or a grid artifact?

**It is not a lucky single cell, but it is not a sharp optimum either.** Every
S at or above the S=13 quality threshold (13, 16, 20) lands full recall@5 in a
narrow N=26-30 band, all three clearly ahead of v7's N=32. The S=16 vs S=13
(26 vs 28) and S=16 vs S=20 (26 vs 30) gaps are 2-4 N wide — inside the
resolution this grid can resolve with one candidate set and no resampling.
**Read it as: a plateau opens up once S >= 13, not a peak at S=16
specifically.** Below that threshold (S=5, 8, 10) the policy is worse than v7
and *non-monotonic in S* (S=5 beats S=8 and S=10) — exactly what negative/
near-zero held-out Spearman predicts: the ranking each of those fits produces
is closer to random than to informative, so which N first stumbles onto the
right molecules is luck, not signal.

## Why the small-S fits are bad: v7's own seed batch is a narrow affinity band, not a diverse one

The unanticipated finding. v7 doesn't sample the affinity range when it picks
a seed batch — it picks the S molecules **it already likes**, which cluster
tightly: the S=5 seed batch spans only 0.9 kcal/mol (-6.61 to -5.73) out of
the full set's 5.0 kcal/mol range. A regressor trained on a 0.9 kcal/mol-wide
label range has no gradient to learn and cannot extrapolate to the 5.0
kcal/mol range it is then asked to rank — hence negative Spearman, not just
weak Spearman. The seed-batch range widens only slowly as S grows (1.6 kcal/mol
at S=13, still only 2.0 at S=20, vs 5.0 for the full set), which is the real
reason quality turns positive only once S >= 13, not simply "more points is
better." **A seed batch chosen by v7 is a biased sample for this purpose** —
picking-the-best-looking-S is in tension with picking-a-labelled-set-that-
spans-the-space. A policy that wanted the surrogate to work sooner would need
to seed-sample for label diversity (e.g. a stratified or max-min-distance pick
over v7 score, or over descriptor space), not simply take v7's own top-S. That
redesign is out of scope for this pass — noted, not built.

## The honest answer to "does two-phase beat both references?"

**It beats frozen v7 (once S >= 13) and does NOT beat the Pass-5 LOO
surrogate, at every S in the declared range.** That second result is not a
failure of the two-phase idea — it is the answer to the question Pass 5 left
open. The Pass-5 reference is fit on 44 real labels per fold (via leave-one-
out); the best two-phase seed batch tested here uses at most 20. The gap
(N=21 vs N=26, ~1.2x more docking for the two-phase policy at its best S) is
the price of using less than half the labels the reference had. This pass
does not establish where between S=20 and S=44 the crossover to beating the
LOO reference sits — that would need S values above 20, outside the declared
range, and is deliberately not tested here (see Constraints).

CHEMBL2315019 (baseline #1, the named out-of-distribution singleton) is
recovered by every S in {13, 16, 20} — first entering the docked set at
N=28, 26, 30 respectively, always simultaneously with the last remaining
true-top-5 slot (in this candidate set, "full recall@5" and "has
CHEMBL2315019 been docked yet" are the same event past S=13, since the other
four true-top-5 molecules are all recovered by low N in every variant). It is
**not** recovered at all under S in {5, 8, 10} within their own budgets short
of N=29-40 — consistent with the CONTEXT prediction that the singleton would
likely still be missed, and consistent with Pass 5's finding that it is an
out-of-distribution point no LOO variant predicted well either (rank
15th-26th there). The two-phase S=13-20 fits do surface it earlier than v7
(N=32) despite training on far fewer labels than Pass 5's LOO fits — the
seed-batch range effect above is the reason once S clears the S=13 threshold.

## Declared S range and conclusion, for the record

Declared before running: S in {5, 8, 10, 13, 16, 20}. Not extended after
seeing results — the observed non-monotonicity below S=13 and the shallow
plateau at S=13-20 are reported as found, not smoothed over by adding more S
values to chase a cleaner curve.

**Conclusion:** a v7-selected seed batch needs S >= 13 (of 41 survivors) before
its surrogate fit clears noise (Spearman rho turns from negative to +0.4-0.7);
below that, the two-phase policy is worse than v7 and non-monotonic in S. Once
past that threshold, two-phase beats v7 by a real but modest margin (~1.1-1.2x
fewer docks for full recall@5, S=13-20 all landing in a 26-30 N band) and
still trails the Pass-5 full-information surrogate by a similar margin
(~1.2-1.4x). The bottleneck is not sample count alone but **label diversity**:
v7's own top-S seed batch is a narrow affinity band by construction, which is
why quality rises with S more slowly than "more data helps" alone would
predict. No hyperparameters were tuned against recall; the rf model is Pass
5's, unchanged. Frozen contracts untouched: v7 policy, docking params,
ComputeRouter / ResourceManager / JobStore / tool-registry unchanged.
`funnel/two_phase.py` is additive and offline. ace2 data not read.

---

# Pass 7 — pre-registration: does a diversity-selected seed batch fix Pass 6? (2026-08-29)

Written before `funnel/seed_diversity.py` exists or runs. Four strategies,
capped at three plus the Pass-6 control. Same S range as Pass 6 — `{5, 8, 10,
13, 16, 20}` — and the same N range (S to 41). Neither range is extended after
seeing results.

| strategy | selection rule | one-line hypothesis |
|---|---|---|
| `control_v7_topS` | Pass 6, unchanged: top-S of the v7 prescreen order | reproduces Pass 6 exactly — the baseline this pass tries to beat |
| `maxmin_diversity` | greedy farthest-point over the 1034-dim (ECFP4 1024 bits + 10 descriptors) feature space, standardized (z-score) over the 41 survivors; start from the point closest to the feature-space centroid | maximizing feature-space spread should also widen the label range, clearing the Spearman noise floor at a smaller S than v7-top-S |
| `stratified_v7_score` | S positions evenly spaced across the v7 rank-score ordering (index `round(i*(n-1)/(S-1))` for `i in 0..S-1`, `n=41`) — spread across the ranking, not concentrated at the top | v7's score already weakly tracks affinity, so spreading picks across its full range should capture more of the affinity spread than pure diversity, at lower implementation risk |
| `random_seed0` | uniform random sample of S survivors, `numpy.random.default_rng(seed=0)`, single draw, no resampling | a real control — v7-top-S is a specifically bad (narrow-band) sample by construction, so even uniform random should do no worse; if random alone beats v7-top-S, seed *selection* was the fixable part of Pass 6 and the specific diversity criterion doesn't matter much |

**Leakage guard G1 (unchanged from Pass 6):** every strategy function receives
only a `ctx` containing the v7 prescreen order, the v7 rank-scores, and the
feature matrix — never the baseline, an affinity, or a Pass-5 OOF prediction.
`maxmin_diversity`'s starting point is the feature-space centroid, not v7's
#1 pick, specifically so v7's ranking preference cannot leak into which point
anchors the greedy search. Tie-breaks in `maxmin_diversity` and the sampling
order in `random_seed0` use a v7-independent canonical order (sorted ligand
id), so v7's ranking cannot bias tie-breaking either.

**Leakage guard G2 (unchanged from Pass 6):** `fit_phase2()` is reused
unmodified from `funnel.two_phase` — same assertion that training sees
exactly S rows, same disjointness check between training and held-out ids.

**Surrogate model:** Pass 5's `rf` (`RandomForestRegressor(n_estimators=300,
random_state=0)`), unchanged. Not tuned against recall in this pass either.

**Bar to clear:** beating frozen v7 (N=32) is necessary but not sufficient —
Pass 6 already showed that's possible. The real question is whether any
strategy beats the Pass-5 LOO surrogate (N=21). If none do, seed selection is
not the binding constraint and this line of investigation closes.

## Results (`funnel/seed_diversity.py`)

Both leakage guards fired zero assertions across all 24 (strategy, S) fits and
720 (strategy, S, N) grid cells. `runs/seed_diversity_cox2_v1.{csv,json,svg}`.

### Seed-batch affinity range and held-out Spearman, all 24 cells

| S | control (v7-top-S) | maxmin diversity | stratified v7-score | random (seed 0) |
|---:|---|---|---|---|
| 5  | range 0.88, rho **-0.334** | range 0.96, rho **+0.431** | range 0.95, rho **+0.518** | range 1.72, rho **+0.525** |
| 8  | range 0.88, rho -0.412 | range 1.19, rho +0.341 | range 2.03, rho +0.594 | range 1.97, rho +0.371 |
| 10 | range 1.05, rho +0.198 | range 1.19, rho +0.581 | range 2.78, rho +0.620 | range 1.74, rho +0.421 |
| 13 | range 1.64, rho +0.411 | range 2.47, rho +0.501 | range 1.83, rho +0.632 | range 1.74, rho +0.450 |
| 16 | range 1.64, rho +0.733 | range 2.47, rho +0.432 | range 2.06, rho +0.628 | range 1.74, rho +0.582 |
| 20 | range 2.01, rho +0.701 | range 2.81, rho +0.488 | range 4.29, rho +0.582 | range 4.29, rho +0.758 |

**First S at which held-out Spearman clears a "usable" bar (rho >= 0.4):**
control = S=13; maxmin = S=5; stratified = S=5; random = S=5. All three
alternative strategies clear it at the *smallest* S tested — four whole
declared-S steps earlier than v7-top-S needs.

**Range vs. quality, Pearson r across all 24 cells: +0.505.** Real and
positive, confirming the Pass-6 mechanism in direction — but moderate, not
strong: e.g. control's own best fit (S=16, rho=0.733) has a narrower range
(1.64) than several worse-performing cells (stratified S=20: range 4.29, rho
only 0.582). Range is *part* of the story, not the whole of it — which
specific points end up in the batch matters too, not just how spread out they
are. Plot: `runs/seed_diversity_cox2_v1.svg`.

### First N reaching literal recall@5 = 5/5

| S | control | maxmin | stratified | random |
|---:|---:|---:|---:|---:|
| 5  | 33 | **20** | 26 | 25 |
| 8  | 39 | 28 | 28 | 31 |
| 10 | 40 | 35 | 24 | 28 |
| 13 | 28 | 36 | 25 | 32 |
| 16 | 26 | 25 | 25 | 30 |
| 20 | 30 | 27 | 30 | 30 |

References at the same metric: **frozen v7 = N=32. Pass-5 LOO surrogate (rf,
44 labels/fold) = N=21.**

## Task 4 — the mechanism question, answered directly

**Does a wider seed range produce a better fit?** Yes, moderately (Pearson
r=+0.505 across 24 cells) — direction confirmed, strength partial.

**Does any strategy push the Spearman crossover below S=13?** Yes, decisively.
`maxmin_diversity`, `stratified_v7_score`, and `random_seed0` all clear
rho >= 0.4 already at S=5, the smallest value tested — where the control needs
S=13. Fixing *what a seed batch of a given size can learn* is real and easy:
v7-top-S was a specifically bad way to pick a seed batch, and almost anything
else (including plain uniform random) does better.

**Does any strategy beat N=21?** One cell does, barely:
`maxmin_diversity` at S=5 reaches N=20 — one job-count better than the Pass-5
reference. **Read this as noise, not a finding.** Three things argue against
it: (1) it is a single cell in a 24-cell grid, exactly the multiple-comparisons
risk named going in; (2) `maxmin_diversity`'s own curve is wildly
non-monotonic in S (20, 28, 35, 36, 25, 27) with no stable neighbourhood around
S=5 — S=8 for the same strategy is 8 N worse; (3) the margin itself is one N
out of a 41-wide sweep (~2%), well inside the resolution this grid can
resolve with one candidate set and no resampling. No other cell, across 24
(strategy, S) combinations and 4 candidate mechanisms, gets within 4 N of the
reference from below.

**Seed selection was not the binding constraint.** It looked like one after
Pass 6 — negative Spearman is a loud, specific symptom, and it has a specific,
now-confirmed cause (v7's seed batch is a narrow affinity band) and a specific,
now-confirmed fix (pick for range instead: any of the three alternatives
clears the noise floor four S-steps earlier). But fixing that symptom did not
close the gap to the Pass-5 reference. Two things stand between "fit quality
is fine now" and "beats N=21":

1. **The recall milestone is a discrete, single-molecule event, not a smooth
   function of fit quality** (this is Task 5's concentration finding, below).
   A Spearman rho of 0.5 on 30+ held-out points says almost nothing about
   whether one specific rank-1 outlier lands inside the next 10-15 picks —
   that is a tail event the aggregate correlation does not control. Compare
   `maxmin_diversity` S=8 (rho=+0.341, one of its weaker fits) landing
   `CHEMBL2315019` at N=10 — earlier than S=5's own N=18 (rho=+0.431, its
   *best* fit) — direct evidence that fit quality and outlier-detection timing
   are only loosely coupled here.
2. **The Pass-5 reference is not a fair like-for-like target.** It is fit on
   44 real labels per leave-one-out fold — more than double the largest S
   declared here (20). Closing the gap on genuinely equal footing would need
   testing S values above 20, which is outside the declared range and
   deliberately not done in this pass (see Constraints). This pass answers
   "can smarter seed selection alone, at S<=20, match a model that effectively
   saw ~44 labels" — and the answer is no, not reliably.

## Unanticipated: `maxmin_diversity` is good at finding the outlier and bad at something else

Cross-referencing against `funnel/concentration_check.py` (Task 5, below):
`maxmin_diversity` docks `CHEMBL2315019` early in every S (N=18, 10, 17, 13,
16, 20 — often *earlier* than any other strategy, including the control at
comparable S), yet its "first N to literal 5/5" is frequently among the
*worst* in the grid (S=10 -> 35, S=13 -> 36). The gap between "named molecule
found" and "all five found" is 7-23 N for `maxmin_diversity` — far wider than
any other strategy (control/random/stratified gaps are mostly 0-14 N, usually
under 5 once S>=13). A plausible mechanism: greedy farthest-point search
explicitly spends its early picks on points *unlike* what it already has,
which is exactly what surfaces a structural outlier fast — but the same
property can strand an "easy," representative true-positive that a
score-based or even random ordering would reach sooner, because diversity
selection has no reason to prefer typical, high-probability molecules over
atypical ones. Diversity trades one kind of miss for another; it does not
strictly dominate.

## Task 5 — benchmark limitation: how concentrated is cox2_v1's recall@5 in one molecule?

`funnel/concentration_check.py` re-reads every already-computed policy curve
from Passes 4-7 (v7; the 3 Pass-5 surrogate variants; the 6 Pass-6 two-phase
S values; the 24 Pass-7 strategy x S combinations — 34 policies total) and
checks whether the N at which literal recall@5 first reaches 5/5 is *exactly*
the N at which `CHEMBL2315019` first enters the docked set.

**18 of 34 policies (53%) have their literal recall@5 = 5/5 milestone land on
the exact same N as `CHEMBL2315019` being docked.** Full breakdown in
`runs/concentration_cox2_v1.json`.

This is lower than Pass 6's own framing suggested ("past S=13... the same
event in every curve") — that held for the control/v7-derived family
specifically, not universally. `maxmin_diversity` never coincides (0/6) for
exactly the reason above: it finds the outlier fast but stalls on a different
top-5 member. Even where the *exact* N doesn't match, the named molecule is
usually close to the last one found (median gap a few N) for every strategy
except `maxmin_diversity`, where the gap runs as high as 23 N.

**Stated plainly as a benchmark limitation:** whether or not
`CHEMBL2315019` specifically has been docked explains roughly half of every
"did this policy reach full recall@5" outcome tested across four passes of
this evaluation. cox2_v1's literal-recall@5 headline is, to a first
approximation, a one-molecule detection test wearing a five-molecule metric's
clothes. That does not invalidate the earlier recall numbers, but it does
mean this benchmark's power to discriminate between policies that all handle
the other four true-top-5 molecules easily (nearly all of them, at low N) is
limited to how each policy handles exactly one hard, out-of-distribution
point. A benchmark that could actually separate these policies on their
general prescreen quality — rather than on one coin-flip-adjacent event —
would need either a larger candidate set (so the difficulty isn't
concentrated in a single point) or a recall target less dominated by one
outlier (e.g. recall@10, where the milestone is less singular — worth a
future pass, not run here).

## Summary

Diversity-based (and even plain random) seed selection **does** fix the
diagnosed Pass-6 mechanism — fit quality clears the noise floor four S-steps
earlier than v7-top-S. It does **not** reliably close the gap to the Pass-5
LOO reference; the one cell that nominally does (`maxmin_diversity` S=5,
N=20) is a single-cell, non-monotonic-neighbourhood result inside a
one-molecule-dominated metric, and is reported here as noise, not a win.
Seed selection was a real, fixable problem; it was not *the* binding
constraint on beating a reference fit on more than double the labels any
declared S provides. Declared S range `{5, 8, 10, 13, 16, 20}` not extended
after seeing results. No surrogate hyperparameters tuned against recall (Pass
5's rf, unchanged). Frozen contracts untouched: v7 policy, docking params,
ComputeRouter / ResourceManager / JobStore / tool-registry unchanged.
`funnel/seed_diversity.py` and `funnel/concentration_check.py` are additive
and offline. ace2 data not read.

---

# Pass 8 — fix the measurement, not the policy: is recall@10 less degenerate? (2026-08-29)

Four passes of policy work are closed (P4-P7 below use this pass's own
shorthand: the 8-variant ranker sweep, the Pass-5 surrogate, the Pass-6
two-phase policy, the Pass-7 seed-diversity strategies). This pass adds no
policy, no surrogate, no seed strategy. It re-reads what already exists under
a second metric and asks whether recall@5 was the wrong ruler.

**Method:** `funnel/measurement_recall10.py` recomputes the full per-molecule
docking ORDER for all 34 Pass 4-7 policies from the exact same frozen,
deterministic functions already executed (`prescreen_order`, Pass-5's `rf`
surrogate via `fit_phase2`/`phase2_order`, the Pass-6 control seed strategy,
the four Pass-7 strategies) — needed only to recover *which* target molecule
arrives last, a detail the committed aggregate CSVs don't carry per-molecule.
**Every recomputed recall@5 and recall@10 value was asserted equal to the
already-published figure in its corresponding committed artifact — all 34
checks passed.** This is a re-read of existing results, not a re-run of new
ones; nothing here changes any number already published.

## The one flip, stated first

**Pass 7's single nominal "win" over the Pass-5 reference does not survive
under recall@10, confirming it was noise, not a finding.**
`maxmin_diversity` at S=5 reached the Pass-5 LOO surrogate's recall@5
milestone one N early (N=20 vs N=21) — flagged in Pass 7 as "read this as
noise, not a finding" on multiple-comparisons grounds. Under recall@10 that
same cell needs **N=29** against the reference's **N=21** — a clear loss, not
a marginal win. No cell across all 24 Pass-7 (strategy, S) combinations comes
within 5 of the recall@10 reference (closest: `control_v7_topS` S=16 and
`stratified_v7_score` S=10, both N=26-27). The recall@5 "win" was exactly the
kind of artifact it was called out as; recall@10 removes the ambiguity rather
than reversing the verdict.

None of P4, P5, or P6's headline conclusions flip (all detailed below).

## Task 1 — concentration under recall@10

| | recall@5 | recall@10 |
|---|---|---|
| dominant straggler | CHEMBL2315019 | CHEMBL2315019 |
| policies (of 34) determined by it | **18 (53%)** | **10 (29%)** |
| distinct molecules that are ever the straggler | 1 (by construction — only one target) | **9 of 10** true-top-10 members |
| 2nd-most-common straggler | n/a | CHEMBL6 (baseline #9, weakest of the ten) in 7/34 (21%) |

Full distribution (`runs/measurement_recall10_cox2_v1.json`): CHEMBL2315019
10, CHEMBL6 7, CHEMBL149781 4, CHEMBL327900 3, CHEMBL34913 3, CHEMBL1956384 3,
CHEMBL111786 2, CHEMBL111518 1, CHEMBL184613 1. (CHEMBL76692, baseline #5 of
the top-10 set, is never the final straggler across all 34 policies — it is
always found before nine other members, in every policy tested.)

**recall@10 is less concentrated, clearly — nearly half the coincidence rate
(29% vs 53%), and the failure is spread across 9 different molecules instead
of being almost entirely one.** It is not *non*-degenerate: CHEMBL2315019 is
still the single most common straggler, at a rate (29%) well above the 10%
a uniform draw over ten target molecules would predict — it is still the
hardest of the ten to rank, just not the *only* thing the metric measures
anymore.

**Gap distribution** (N at 10/10 minus N at 9/10 — how many extra docks the
last mile costs), n=34: min=1, p25=1, median=**3**, p75=4, max=16. Tight and
right-skewed with a short tail — most policies close the last slot within a
few docks of the ninth, unlike recall@5's single-molecule cliff-edge behaviour
documented in Pass 7 (`maxmin_diversity` gaps up to 23).

**Does recall@10 still discriminate between policies?** Yes — checked
separately, since a metric identical for every policy would be as useless as
a degenerate one. Completion-N spread: recall@5 min=20 max=40 (std 5.3);
recall@10 min=21 max=40 (std 5.0). Essentially the same spread. Fixing the
concentration problem did not flatten the metric.

## Task 2 — re-read of all four conclusions

**P4 (8-variant ranker sweep, Pass 2, N=5 fixed budget — the only recall@10
figures that pass produced; no full frontier exists per non-v7 variant, so
this is the already-published snapshot, not a re-derived milestone):**

| variant | recall@5 lit | recall@10 lit |
|---|---:|---:|
| v1_original | 1/5 | 5/10 |
| v2_binding_only | 1/5 | 4/10 |
| v3_binding_only_tox_filter | 1/5 | 4/10 |
| v4_descriptor_heuristic | 1/5 | 3/10 |
| v5_binding_desc_blend | 1/5 | 4/10 |
| v6_ligand_efficiency | 0/5 | **1/10** |
| v7_binding_weak_cox2 | 1/5 | 5/10 |
| v8_binding_only_no_filter | 1/5 | 4/10 |

**Not flat.** recall@5 was flat at 1/5 for 7 of 8 variants (only v6 stood
out); recall@10 ranges 1/10 to 5/10 and clearly separates v6 (a genuine loser,
already known) from the rest, *and* separates v4 (physicochemistry-only, 3/10)
from v1/v7 (5/10) — a distinction recall@5 could not make. Pass 2's own text
already flagged this ("only recall@10 catches [CHEMBL111786]") without
naming it as a metric property; this pass makes it explicit. Not a flip of
Pass 2's conclusion (which was specifically about recall@5), but the clearest
evidence in this whole investigation that recall@10 was already the more
informative number, sitting unused in a table three passes ago.

**P5 (surrogate vs. frozen v7):** holds, margin unchanged in direction.
v7 N=36 at recall@10 (vs N=32 at recall@5). Surrogates: ridge N=25 (1.44x),
rf N=21 (1.71x), krr N=26 (1.38x). All three still clearly beat v7, by a
similar or slightly larger multiple than under recall@5 (ridge/rf/krr were
1.6x/1.5x/1.2x at recall@5). **No flip.**

**P6 (two-phase vs. Pass-5 LOO surrogate):** holds. Best two-phase cell under
recall@10 is control S=16 at N=26 — same S as the recall@5 best cell, same
N — against the surrogate reference's N=21. Two-phase still loses by the same
~1.2x margin. **No flip.**

| S | two-phase N@5/5 | two-phase N@10/10 |
|---:|---:|---:|
| 5  | 33 | 39 |
| 8  | 39 | 39 |
| 10 | 40 | 40 |
| 13 | 28 | 33 |
| 16 | 26 | 26 |
| 20 | 30 | 30 |

**P7 (does any seed strategy beat the reference, stably across S):** does
**not** hold — see "the one flip" above. Under recall@10, nothing beats N=21;
the nearest approach is 5 N away (control S=16, stratified S=10, both 26-27),
and neither is part of a monotonic or stable trend across neighbouring S
(control: 39,39,40,33,**26**,30; stratified: 28,28,**27**,30,34,33 — both
noisy, not smoothly improving toward their best S). **The recall@5 "win" is
gone; the recall@10 read is unambiguous: seed selection does not close the
gap to the reference at S<=20, under either metric.**

## Task 3 — primary metric, and the rule

**Rule:** prefer the recall level whose completion event is attributable to a
single molecule in the smallest fraction of policies — *provided* its
completion-N still varies meaningfully across policies. A metric that is
non-degenerate in the concentration sense but identical for every policy
(no spread) would be equally useless for telling policies apart; both
properties are checked, not just the one Pass 7 flagged.

**recall@10 (literal) passes both checks better than recall@5:** less
concentrated (29% vs 53% coincidence with one molecule, failure spread across
9 distinct molecules instead of 1) and equally discriminating (completion-N
std 5.0 vs 5.3, same order of magnitude, not flattened).

**Recommendation: recall@10 literal becomes the primary metric for future
policy comparisons in this project.** recall@5 remains reported alongside it
— it is the more intuitive, more commonly cited number, and every conclusion
re-checked in this pass held its direction under both metrics anyway (only
the one already-flagged-as-noise cell changed). **No published recall@5
number is retracted or edited by this pass.** The data does not change; which
number gets called "the headline" does.

Caveat, stated plainly: recall@10 is *less* degenerate, not *non*-degenerate.
CHEMBL2315019 is still the single most common straggler (29%, versus the 10%
a uniform draw over ten targets would give), and Task 5 of the previous pass
already showed docking-hard outliers are a real, unresolved cox2_v1 property.
Switching the primary metric mitigates the measurement problem; it does not
fix the underlying one, which is what Task 4 (below) scopes a fix for.

## Task 4 — scoping a bigger candidate set (not built this pass)

**Cost, projected from `runs/baseline_cox2_v1.json`'s own per-candidate
wall-clock** (45 candidates, 4 seeds each, identical exhaustiveness/seed/cpu
config the whole project has used): mean 158.54s per candidate (4 docks),
39.63s per single Vina job. `total_run_wall_s` (7141.07s) is within 7s of
`total_docking_wall_s` (7134.23s) — the reference run was effectively serial,
so linear scaling from the observed mean is realistic, not optimistic.

| candidate-set size | Vina jobs (x4 seeds) | projected dock wall-clock |
|---:|---:|---:|
| 45 (current) | 180 | 7134s (~2.0 h) — actual |
| 100 | 400 | ~15,854s (**~4.4 h**) |
| 150 | 600 | ~23,781s (**~6.6 h**) |

**Tooling change required: close to zero, confirmed.** Grepped
`baseline.py`, `funnel.py`, `evaluate.py`, `sweep.py`, `frontier.py` for a
hardcoded candidate count — none exists; every one of them derives its loop
bound from the loaded candidate set. The only production-code change needed
is bumping the `per_bin` counts in `build_candidate_set.CONFIGS["cox2"]`
(currently 12/11/11 = 34 stratified + 11 fixed references = 45; e.g.
~30/30/29 + 11 = 100, ~47/46/46 + 11 = 150). The raw ChEMBL source
(`ml/datasets/target_identification/COX-2.csv`) has ~14,000 rows — no
data-availability ceiling anywhere near 100-150 after the existing
MW/heavy-atom set-construction filter. **Caveat, self-inflicted, not part of
"the harness":** this pass's own analysis scripts (`surrogate.py`,
`two_phase.py`, `seed_diversity.py`, `concentration_check.py`,
`measurement_recall10.py`) hardcode `== 45` / `SURVIVOR_CAP = 41` as
integrity-check constants for cox2_v1 specifically; a bigger set would need
those bumped (one line each) or re-derived from the loaded candidate set. Not
a harness limitation — a byproduct of writing tight assertions against a
known-size set in Passes 5-8.

**Recommendation: not yet — finish ACE2 first.** The held-out ACE2 baseline
(pre-registered, `funnel/CHANGELOG.md` Pass 4) is still unrun, blocked twice
by host disk exhaustion (STATUS.md, Pass 4 disclosure), and is a standing,
already-committed obligation with a written prediction on record — smaller in
scope (~2-3h, 180 jobs) than either candidate-set expansion considered here.
A 150-candidate cox2 rebuild is 600 jobs, more than 3x the job count of the
ACE2 run that has already failed twice on disk space, on the same single
machine. Both compete for the same docking hours; running the larger,
riskier, purely-exploratory job first while a smaller, already-promised one
sits blocked is the wrong order. Recommend: verify free disk headroom
explicitly, finish ACE2, *then* revisit whether a bigger cox2_v1 candidate set
is worth ~4.4-6.6 h against whatever ACE2 turns up — the ACE2 result may
itself change how urgent the concentration problem looks (Pass 4's own
falsifiable prediction was that ACE2 recall would be *lower* than cox2's,
which would mean ACE2 has the same concentration problem or worse, in which
case a single bigger cox2 set fixes only one of the two evaluations).

## Summary

recall@10 literal is confirmed less degenerate than recall@5 (29% vs 53%
one-molecule concentration, failure spread across 9 of 10 target molecules
instead of 1) without losing discriminative power (comparable completion-N
spread), and is adopted as the primary metric going forward — recall@5 stays
published, unedited, as a secondary number. Re-checking all four prior policy
conclusions under recall@10 confirms three exactly and reverses the fourth's
only nominal exception (Pass 7's single-cell "win," already flagged as likely
noise, is a clear loss under recall@10) — no conclusion about frozen v7,
the Pass-5 surrogate, or the two-phase policy's shortfall changes. A bigger
candidate set is scoped (~4.4h at 100, ~6.6h at 150 candidates; near-zero
harness changes) but not built, and is recommended to wait behind finishing
the already-committed, smaller, twice-failed ACE2 baseline. No new docking,
no new policy, surrogate, or seed strategy this pass. Frozen contracts
untouched: v7 policy, docking params, ComputeRouter / ResourceManager /
JobStore / tool-registry unchanged. `funnel/measurement_recall10.py` is
additive, offline, and re-derives nothing that changes a previously published
number. ace2 data not read.

---

# Pass 9 -- held-out ACE2 baseline: run it, score the frozen policy, test the prediction (2026-08-30)

The `ace2_v1` baseline (pre-registered Pass 4, blocked twice by disk exhaustion)
finally ran clean: 43 GB free, `caffeinate -i`, output to a file, corrected
Zn-centred box, docking config identical to cox2 (ex=8, --cpu 1,
seeds [1,42,2024,31337], conformer seed 42). `runs/baseline_ace2_v1.json`,
180 jobs, 9322 s (2.6 h). Scored ONCE against the UNCHANGED frozen v7 policy.
No tuning, no new policy/surrogate/seed strategy. `funnel/heldout_ace2.py`
(additive, offline) and its numbers cross-check zero-mismatch against
`funnel.frontier --set ace2_v1`.

## Task 3 -- run sanity

**39/45 completed. 6 failed, all boronic acids** (`...B(O)O` warhead:
CHEMBL4438924, 4444926, 4450628, 4451026, 4455145, 4469059). Deterministic:
`PDBQT parsing error: Atom type B is not a valid AutoDock type` -- Vina has no
boron parameters; every seed fails identically in ~0.05 s at the Vina parse
step. Not a run defect, a method boundary. Re-docking is futile and was not
done. **The held-out set is effectively 39, not 45**, and the excluded 6 are
one chemotype.

**Reference ligands reproduce the Pass-3 box-fix sanity docks:**

| ligand | this run | box-fix | delta | sd(now) |
|---|---:|---:|---:|---:|
| MLN-4760 / ORE-1001 (CHEMBL429844) | -6.321 | -6.00 | -0.32 | 0.081 |
| lisinopril | -5.796 | -5.80 | +0.00 | 0.253 |
| captopril | -4.393 | -4.39 | -0.00 | 0.020 |
| ethanol | -2.647 | -2.65 | +0.00 | 0.002 |

Potency order preserved exactly (MLN-4760 > lisinopril > captopril > ethanol);
3 of 4 affinities bit-close; MLN-4760 off by 0.32 (largest, most flexible of the
four; box-fix reported it at sd 0.36, so within ~1 sigma). The box discriminates.
Run is sound.

**Seed noise -- ACE2 is ~3x noisier than cox2:**

| set | n | median seed sd | mean | p90 | max | frac > TIE_EPSILON(0.10) |
|---|---:|---:|---:|---:|---:|---:|
| cox2_v1 | 45 | 0.036 | 0.072 | 0.142 | 0.440 | 11/45 |
| ace2_v1 | 39 | **0.110** | 0.151 | 0.306 | 0.681 | **22/39** |

**TIE_EPSILON = 0.10 sits BELOW the ACE2 median seed-noise floor** (on cox2 it
was ~3x above). The frozen tie-grouping is therefore too tight for ACE2: pairs
0.10-0.22 kcal/mol apart get distinct ranks when the docking cannot actually
resolve them. Literal recall understates on ACE2; tie-credited is the more
honest read here. The constant was calibrated on cox2 and does not transfer.
**Not fixed this pass** -- flagged for a decision, since changing it is a
measurement change to a held-out result.

## Task 1 -- held-out evaluation, frozen v7, one pass

- Hard filter: 38/45 survive, **0 false negatives** (no baseline top-5 or
  top-10 molecule dropped by the filter -- prediction held).
- 5 of the 6 boronic acids pass the filter and occupy prescreen ranks 28-33:
  in a real funnel run those docking slots are wasted (the jobs error out).

**First N to reach each recall level -- ACE2 held-out vs cox2 reference:**

| metric | ACE2 | cox2 |
|---|---:|---:|
| recall@10 literal = 10/10 (PRIMARY) | N=35 | N=36 |
| recall@10 literal = 8/10 | N=25 | N=30 |
| recall@10 literal = 5/10 | N=15 | N=10 |
| recall@10 tie-credited = 10/10 | **N=24** | N=32 |
| recall@5 literal = 5/5 (secondary) | N=30 | N=32 |
| recall@5 literal = 2/5 | N=13 | N=10 |
| recall@5 literal = 1/5 | N=1 | N=4 |
| recall@5 tie-credited = 5/5 | N=24 | N=32 |

Mean baseline rank of v7's top-10 prescreen picks: ACE2 **20.4** vs cox2 ~12.6.
Speedup at recall@10 10/10: ACE2 1.3x (N=35 of 38 survivors), cox2 1.3x (N=36).

## Did the pre-registered prediction hold?

Pass 4 predicted: **held-out recall on ace2_v1 LOWER than cox2, for
target-intrinsic reasons (Vina ignores the catalytic Zn; narrow chemotype),
not a policy defect.** Falsifiable expectations:

1. `literal recall@5 ace2 <= literal recall@5 cox2` -- **HELD.** At N=10, ACE2
   1/5 vs cox2 2/5 (Pass 4's "1/5 at N=10" for cox2 is stale; the committed
   frontier is 2/5). ACE2 is lower everywhere on recall@5 through N=24.
2. `tie-credited recall@5 ace2 < 4/5 at N=10` -- **HELD** (ACE2 is 1/5 at N=10).
3. `0 hard false negatives` -- **HELD exactly** (top-5 and top-10).
4. `the cox2 "ceiling is the models, not the formula" holds or strengthens` --
   **HELD and strengthened** (Task 2).

**But the framing was recall@5-era. Under Pass 8's primary metric (recall@10
literal, full recovery) the prediction is roughly a WASH:** ACE2 N=35 vs
cox2 N=36, and ACE2 *beats* cox2 on tie-credited recall@10 (N=24 vs N=32). And
ACE2's curve shape is the opposite of "uniformly lower": it hits 1/5 and 1/10
at **N=1** (cox2 needs N=3-4) because CHEMBL4080520, ACE2 baseline #1, is
prescreen rank #1 -- the single best cheap-model call in either evaluation.
**Fast start, weak middle, converges at the tail.** Verdict: prediction correct
on the metric it was written for and on the early/middle curve; not lower on the
current primary metric at full recovery.

## Task 2 -- is ace2_v1 degenerate the same way cox2_v1 is?

(Single frozen policy only -- ACE2 has no 34-policy grid; forbidden from making
non-frozen policies for the hold-out.)

**Prescreen ranks of the baseline top-10 under frozen v7:** `[1, 7, 12, 13, 15,
22, 24, 25, 30, 35]` of 38 survivors, **median 18**. The whole top-10 is
scattered through the back half of the prescreen order.

- **cox2_v1**: tractable set + ONE out-of-distribution outlier (CHEMBL2315019)
  that drives 53% of recall@5 across 34 policies; the other four top-5 are easy.
- **ace2_v1**: **NO single dominant straggler.** Worst is CHEMBL163454
  (baseline #7) at prescreen #35, but the gap to 2nd-worst is only 5, and FOUR
  baseline-top-10 members sit at prescreen rank >= 24. Last two top-10 members
  recovered at N=30 and N=35 (5-dock final gap, like cox2's recall@10 gap
  median of 3). The problem is not "detect one molecule" -- it is "the cheap
  `binding_score` model has almost no rank signal on this Phe-Pro/thiol/
  phosphinic/boronic chemotype."

**recall@10 vs recall@5 concentration on ACE2:** both are diffusely hard.
recall@5 5/5 at N=30, recall@10 10/10 at N=35 -- 5 extra docks for double the
targets. recall@10 is NOT meaningfully less concentrated here, because there is
no outlier to dilute. **Pass 8's "recall@10 is less degenerate" is a
cox2-specific property** (it dilutes cox2's lone outlier); it does not
generalise to a set whose difficulty is already spread out.

**ACE2 analogue of CHEMBL2315019 -- there are THREE, not one:**

| baseline # | ligand | aff | prescreen # | binding_score | P(ace2) | P(cox2) |
|---:|---|---:|---:|---:|---:|---:|
| 1 | CHEMBL4080520 | -7.79 | 1 | 7.12 | 0.13 | 0.42 |
| 2 | CHEMBL402987 | -7.40 | 30 | 5.36 | 0.39 | 0.32 |
| 3 | CHEMBL252417 | -7.13 | 24 | 5.52 | 0.08 | 0.45 |
| 5 | CHEMBL400527 | -6.96 | 22 | 5.65 | 0.93 | 0.23 |

Baseline #2, #3, #5 all dock -6.96 to -7.40 but carry mid-pack `binding_score`
(~5.4-5.7) and sit at prescreen 22-30. The one visible top docker (#1) has the
highest `binding_score` in the set (7.12) and is the only reason ACE2's early
curve looks good. `P(ace2)` is anti-informative: 0.93 for baseline #4/#5, but
0.08-0.39 for #1/#2/#3 -- the ACE2 activity model and the docking disagree
completely on this set.

## General read: set-specific or general?

**Benchmark degeneracy is a general property of 45-molecule screening sets, not
a cox2 artifact -- but it manifests differently by set composition.** A diverse
set (cox2, 8105 unique in the source) concentrates its hardness in a few
out-of-distribution outliers; a narrow set (ace2, 122 unique, one scaffold
family) spreads thin, near-zero cheap-model signal across the whole top-k, and
additionally loses 13% of itself to un-dockable chemistry.

**A 100-molecule cox2 expansion fixes cox2's version** (the outlier gains
neighbours; 5-10 hard molecules instead of 1 dilutes the coincidence rate;
Pass 8 scoped it at ~4.4 h and near-zero tooling change). **It would not fix
ace2's version**, which is a feature-signal problem, not a sample-size problem.
Recommendation stands: the cox2 expansion is worth doing, understood as
metric-hygiene for cox2 policy comparisons -- not a general fix, and ACE2 just
demonstrated why.

## Unanticipated

1. 6/45 un-dockable (boronic acids); effective held-out set is 39. Not in the
   pre-registration; changes the denominator.
2. ACE2 docking 3x noisier; TIE_EPSILON (0.10) no longer clears the seed-noise
   floor. Calibrated on one target, does not transfer.
3. Under the current primary metric the "lower recall" prediction is a wash at
   full recovery, and ACE2 *wins* on tie-credited recall@10.
4. ACE2's curve is fast-start / slow-middle / converging, driven entirely by
   CHEMBL4080520 being prescreen #1 -- not "uniformly lower."
5. `P(ace2)` is anti-informative for docking rank on its own target's set.

**No policy change made or recommended** -- v7 behaved as predicted. Two
MEASUREMENT issues (TIE_EPSILON transfer; handling of the 6 un-dockable
molecules) are flagged for a decision before this becomes a published held-out
number; neither was acted on. Frozen contracts untouched: v7 policy, docking
params, ComputeRouter / ResourceManager / JobStore / tool-registry unchanged.
ace2 baseline used once, as intended. `funnel/heldout_ace2.py` is additive and
offline. Artifacts: `runs/baseline_ace2_v1.json`, `runs/features_ace2_v1.json`,
`runs/frontier_ace2_v1.{csv,svg}`, `runs/frontier_ace2_v1_heldout.csv`,
`runs/heldout_ace2_v1.json`, `runs/frontier_ace2_vs_cox2_pass9.svg`.

> **Correction note appended 2026-08-30 (from Pass 10, not an edit to the
> above).** This entry says several times that "the cheap models have near-zero
> rank signal across the ACE2 top-k." That is correct **for the shipped
> pre-trained models** (`binding_score`, `P(ace2)`) used by the frozen v7
> prescreen. It does **not** extend to a fresh surrogate: Pass 10 found that a
> RandomForest fitted by leave-one-out on ACE2's own docking labels (ECFP4 + 10
> descriptors, Pass-5's F1 feature set) ranks ACE2 affinity at LOO Spearman
> 0.637, R^2 0.548 -- comparable to cox2 (0.687). The narrow chemotype that
> defeats the shipped models makes leave-one-out *easy* (every held-out molecule
> has near-identical neighbours to interpolate from). Read the Pass 9 statements
> as "the shipped models have no signal on ACE2," not "no signal is available
> there." No number in this Pass 9 entry changes.

---

# Pass 10 -- PRE-REGISTRATION: do receptor-aware features predict Vina affinity where fingerprints cannot? (2026-08-30)

Committed BEFORE `funnel/receptor_features.py` or `funnel/pass10_eval.py` exist
or run. Nine passes established that ligand-only features (ECFP4 + 10 RDKit
descriptors) carry modest signal for docking score on cox2 (LOO Spearman ~0.68,
Pass 5 rf) and near-zero rank signal across the ACE2 top-10 (Pass 9). The
diagnosis those passes converged on: docking score is a property of the
ligand-RECEPTOR pair; the cheap features describe the ligand alone. This pass
tests the direct consequence -- do features that encode the ligand's fit to a
specific pocket beat ligand-only features? It may fail; a clean negative closes
the question.

No new docking. Frozen v7 policy, docking params, and the four frozen contracts
(ComputeRouter / ResourceManager / JobStore / tool-registry) untouched. Additive,
offline. Published numbers are not edited or retracted.

## Data actually available (checked before pre-registering)

- `runs/baseline_cox2_v1.json` -- 45 molecules, real mean Vina affinities (4 seeds). No poses stored.
- `runs/baseline_ace2_v1.json` -- 45 molecules; 39 usable (6 boronic acids un-dockable). No poses stored.
- `backend/targets/{cox2,ace2}_receptor.pdbqt` + raw `1CX2.pdb` / `1R42.pdb`. Frozen boxes: cox2 centre [22.1, 10.5, -14.3], ace2 centre [53.1, 68.6, 31.2], both 20 A cubes.
- `/tmp/funnel_baseline_110aff1e6d6c.db` -- the ACE2 baseline's private (ephemeral) job store, still on disk: 156 completed jobs each with the full docked-pose PDBQT. **The cox2 baseline's job store (Aug 28) is gone.** So pose-derived features can be computed for **ACE2 only**. The ACE2 MODEL-1 pose coordinates will be extracted once into a committed artifact so the result survives `/tmp` being cleared.

## Feature families (four, capped, no post-hoc additions)

| # | family | prescreen-usable? | one-line hypothesis |
|---|---|---|---|
| **F1** | **control** -- ECFP4 radius 2 / 1024 bits + the 10 RDKit descriptors (Pass 5's exact set, from `runs/features_{set}.json`) | **YES** | reproduces the Pass-5 baseline (cox2 rf LOO Spearman ~0.68); the number every other family is measured against |
| **F2** | **ligand-vs-pocket shape/geometry** -- ligand 3D shape from one ETKDGv3 conformer (seed 42, MMFF -- the pre-docking conformer the pipeline builds): radius of gyration, asphericity, eccentricity, spherocity, NPR1/2, PMI1/2/3, inertial shape factor, molecular volume, heavy-atom count, longest interatomic distance. Pocket geometry from receptor atoms inside the frozen box: pocket heavy-atom count, pocket radius of gyration, pocket bounding-box spans, a grid-estimated pocket cavity volume. Complementarity ratios: ligand_volume / pocket_volume, ligand_Rg / pocket_Rg, ligand_length / pocket_span, ligand_volume / box_volume. | **YES** | a ligand that fills the pocket without exceeding it docks better; size/volume ratios in a mid range should score, tiny fragments and oversized ligands should score badly -- the "does it fit" signal fingerprints cannot express |
| **F3** | **pharmacophore complementarity** -- ligand H-bond donor / acceptor / aromatic / hydrophobe / +ionisable / -ionisable counts (RDKit BaseFeatures factory + descriptor counts). Pocket counts from box residues by type: donor atoms, acceptor atoms, aromatic residues, hydrophobic residues, +/- charged residues. Features: the raw ligand counts, the (constant-per-target) pocket counts, and the products ligand_HBD x pocket_acc, ligand_HBA x pocket_don, ligand_arom x pocket_arom, ligand_hydrophobe x pocket_hydrophobe, ligand_+ x pocket_-, ligand_- x pocket_+. | **YES** | ligands whose donors / acceptors / aromatics match what the pocket presents dock better; the pocket-count columns are what could let a model trained on one target transfer to the other |
| **F4** | **pose-derived interaction** -- from the best pose (MODEL 1) of each completed ACE2 dock, averaged over the 4 seeds: ligand-receptor heavy-atom contacts < 4.0 A, close contacts < 3.5 A, buried ligand SASA fraction, min distance to the catalytic Zn and to the HEXXH residues (His374/His378/Glu402 of 1R42), pose radius of gyration, pose-centroid distance from box centre, count of ligand atoms outside the box. **ACE2 only** (cox2 poses not retained). | **NO -- CEILING ESTIMATE ONLY** | measures how much signal the real pose carries for affinity at all; it is computed FROM the docking result, cannot be had for an un-docked molecule, and is **never** a prescreen candidate. If its own LOO R^2 is low, the surrogate direction is bounded regardless of features. |

## Protocol

- **LOO, Pass-5 exact.** `RandomForestRegressor(n_estimators=300, random_state=0)`, raw features (no scaling for rf), refit inside every fold. cox2 n=45; ACE2 n=39 usable. Reuse Pass 5's rf hyperparameters unchanged; no tuning against recall.
- **Per family per target:** LOO Spearman, R^2, MAE vs mean affinity.
- **Ranker evaluation:** each family's LOO out-of-fold predictions -> sort ascending -> the existing frontier logic. recall@10 literal + tie-credited (primary, per Pass 8), recall@5 literal + tie-credited (secondary), first N to full recovery, against the frozen v7 policy and the Pass-5 surrogate as references (cox2: `runs/frontier_cox2_v1.csv` + `runs/surrogate_cox2_v1.json`; ACE2: `runs/frontier_ace2_v1.csv`).
- **Known-hard molecules:** rank under each family -- `CHEMBL2315019` on cox2; `CHEMBL402987` (#2), `CHEMBL252417` (#3), `CHEMBL400527` (#5) on ACE2.
- **Cross-target transfer (Task 3):** fit each family on ALL of set A, predict ALL of set B (single fit, no LOO), Spearman(pred, true). Both directions. F1 should give ~0 by construction (no receptor information). Chemotype distributions differ, so a negative result is ambiguous; a positive result is not.
- **Feature caches** committed with a content SHA-256 over the sorted feature rows, same discipline as the candidate sets.
- Dependencies: RDKit (`Descriptors3D`, `rdFreeSASA`, `ComputeMolVolume`, ETKDGv3, BaseFeatures factory), a hand-rolled PDB/PDBQT ATOM-record parser, numpy, scikit-learn. **No new heavyweight dependency.**

## Bar to clear (declared)

- **Prescreen-usable (F2, F3):** clears the bar only if BOTH -- (a) LOO Spearman on cox2 exceeds F1-control's cox2 LOO Spearman (recomputed fresh for exact comparability), AND (b) LOO Spearman on ACE2 is materially above F1-control's ACE2 value and above ~0.2 (a floor for "any signal at all" at n=39). Single-target improvements are explicitly weak and will be reported as such.
- **Cross-target transfer:** a prescreen-usable receptor-aware family shows positive Spearman(pred, true) in at least one train->test direction, where F1 gives ~0. Positive transfer is the strongest possible evidence in this pass that the features encode fit rather than this specific set.
- **F4 ceiling:** no bar -- diagnostic. If ACE2 LOO R^2 < ~0.3 with the real pose, that is a reportable ceiling: even perfect pose knowledge does not linearly predict affinity, and the surrogate direction is bounded.

Expected outcome, stated so it is falsifiable: **F2/F3 probably do NOT clear the
prescreen bar** -- comparing bulk ligand shape/pharmacophore to a static pocket,
without placing the ligand, is a crude proxy for fit, and Vina's own score is
dominated by terms (per-atom vdW/electrostatics over the actual pose, and for
ACE2 a Zn interaction it does not model at all) that these features cannot see.
The most likely substantive result is the F4 ceiling: whether the real pose even
linearly predicts affinity on ACE2. A surprise in either direction would be
worth understanding before trusting it.

## Results (`funnel/receptor_features.py`, `funnel/pass10_eval.py`)

Feature caches: `runs/features_receptor_cox2_v1.json` (sha `fb27135c664a5d4e...`),
`runs/features_receptor_ace2_v1.json` (sha `bf7b5914cafca719...`), ACE2 poses
extracted from the ephemeral job store to `runs/poses_ace2_v1.json`. Eval:
`runs/pass10_eval.json`.

**Computability.** F1/F2/F3 computed for all 45 molecules of each set (0
conformer-embedding failures). F4 computed for 39/45 ACE2 (the 6 boronic acids
were never docked, so no pose exists); F4 not computable for cox2 at all (that
baseline's job store was not retained). cox2 pocket: 465 atoms / 79 residues
inside box+4 A; ACE2 pocket: 823 atoms / 142 residues (the Zn site is more
buried, more protein around the box).

### LOO (rf, Pass-5 protocol) -- affinity fit

| target | family | prescreen? | n | LOO Spearman | R^2 | MAE | CHEMBL2315019 rank | ACE2 #2/#3/#5 rank |
|---|---|---|---:|---:|---:|---:|---:|---:|
| cox2_v1 | F1 control | yes | 45 | **0.687** | 0.407 | 0.434 | 20 | -- |
| cox2_v1 | F2 shape | yes | 45 | 0.466 | 0.251 | 0.464 | 35 | -- |
| cox2_v1 | F3 pharmacophore | yes | 45 | **0.734** | 0.483 | 0.429 | **3** | -- |
| ace2_v1 | F1 control | yes | 39 | **0.637** | 0.548 | 0.389 | -- | 11 / 14 / 12 |
| ace2_v1 | F2 shape | yes | 39 | 0.093 | 0.297 | 0.587 | -- | 16 / 12 / 21 |
| ace2_v1 | F3 pharmacophore | yes | 39 | 0.637 | 0.529 | 0.415 | -- | **6 / 4** / 12 |
| ace2_v1 | F4 pose (CEILING) | **NO** | 39 | 0.529 | 0.448 | 0.481 | -- | 6 / 23 / 8 |

F1-here (0.687 on cox2) matches Pass 5's published 0.679 to within LOO noise;
it is the control for this pass.

### Ranker (LOO out-of-fold order -> frontier; full usable set, not v7-survivors, so indicative only)

| target | family | first N r@10 10/10 | first N r@5 5/5 |
|---|---|---:|---:|
| cox2_v1 | F1 | 22 | 22 |
| cox2_v1 | F2 | 35 | 35 |
| cox2_v1 | F3 | 26 | 23 |
| ace2_v1 | F1 | 21 | 14 |
| ace2_v1 | F2 | 34 | 21 |
| ace2_v1 | F3 | 34 | 16 |
| ace2_v1 | F4 (ceiling) | 36 | 23 |

Reference (full recovery): frozen v7 -- cox2 r@10 N=36 / r@5 N=32; ace2 r@10
N=35 / r@5 N=30. Pass-5 surrogate (cox2) r@10 N=21 / r@5 N=21.

### Cross-target transfer (fit all of A, predict all of B)

| family | cox2 -> ace2 Spearman (R^2) | ace2 -> cox2 Spearman (R^2) |
|---|---:|---:|
| F1 ligand-only | +0.622 (-0.103) | +0.653 (+0.190) |
| F2 shape | +0.320 (+0.216) | +0.576 (+0.227) |
| F3 pharmacophore | +0.604 (+0.394) | +0.657 (+0.543) |

## Task 4 -- the shape of the result

**Prescreen-usable vs ceiling-only, stated plainly:** F1, F2, F3 are
prescreen-usable (computable before docking from SMILES + the receptor
structure + the box). **F4 is not** -- it is computed from the docked pose,
cannot exist for an un-docked molecule, and is reported only as a ceiling
estimate.

**1. Nothing prescreen-usable beats the control. The bar is not cleared.**
F2 (bulk shape vs a static pocket, fit ratios) is a clear loser: LOO Spearman
0.466 on cox2 (vs F1's 0.687) and 0.093 on ACE2 (essentially zero). F3
(pharmacophore complementarity) matches F1 exactly on ACE2 (0.637 = 0.637) and
is +0.047 Spearman above F1 on cox2 (0.734 vs 0.687) -- inside the LOO noise
band for n=45, and F3 is a *worse* ranker than F1 on both targets (first N to
full recovery 23/26 vs 22 on cox2; 34 vs 21 for r@10 on ACE2). **"Receptor-aware
features computable without docking do not beat ligand-only features on these
sets."** The open question this pass set out to answer is closed, negative.

**2. The cross-target transfer test is invalidated by F1 also transferring.**
The pre-registration predicted ligand-only F1 would fail transfer "by
construction -- it contains no receptor information." It did not fail: F1
transfers at Spearman +0.62 / +0.65 both directions. Docking *rank* has a large
receptor-independent component (bigger, more lipophilic, more rigid ligands
dock more negatively against any pocket -- Vina's score is dominated by a count
of favourable vdW contacts that scales with ligand size). So a receptor-aware
family also transferring is **not** evidence it "encodes fit," and in fact F2
transfers *worse* than F1 and F3 the same on Spearman. F3 does transfer with
positive R^2 both directions where F1 goes negative (+0.39/+0.54 vs -0.10/+0.19)
-- the pocket columns help *calibration* (absolute scale), not *ranking*. A
prescreen needs ranking. No net gain.

**3. The F4 pose ceiling is real but modest, and below the ligand-only fit.**
Interaction features from the true docked pose (contacts, buried SASA,
catalytic-Zn / HEXXH distances, pose Rg) give LOO R^2 0.448 on ACE2 -- above the
pre-declared 0.3 "bounded" threshold, so pose knowledge does linearly carry
affinity signal. But F1 fingerprints do **better** (R^2 0.548, Spearman 0.637 vs
F4's 0.448 / 0.529). Even computing features *from the docking result*, a crude
hand-rolled interaction-feature set does not extract the affinity signal better
than a fresh ECFP4 rf. A naive interaction-feature approach will not advance the
surrogate direction; a proper per-residue interaction fingerprint or an
energy-term decomposition might, and is untested here.

**4. The one substantive positive is a mechanism, not a win: F3 ranks the
known-hard molecules far better than F1.** CHEMBL2315019 -- the cox2 baseline #1
out-of-distribution outlier that no cheap signal surfaced across nine passes --
is **rank 3 of 45** under F3 (rank 20 under F1, rank 35 under F2). On ACE2, F3
ranks the three buried top-5 dockers 6 / 4 / 12 (F1: 11 / 14 / 12). The
pharmacophore-product features (ligand aromatic count x pocket aromatic
residues; ligand HBA x pocket donor atoms) capture something about these
polyaromatic, H-bond-rich molecules that 1024 sparse ECFP4 bits do not. But F3
trades this for worse mid-pack ranking (its overall first-N is worse than F1),
so it yields no better funnel -- the same "finds the outlier, strands the easy
ones" trade seen with Pass 7's `maxmin_diversity`.

## Unanticipated

- **F1 (ligand-only ECFP4) has strong LOO signal on ACE2** (Spearman 0.637,
  R^2 0.548 -- higher R^2 than on cox2). Pass 9's "near-zero cheap-model rank
  signal across the ACE2 top-10" was about the *frozen pre-trained models*
  (`binding_score`, `P(ace2)`), and it does **not** extend to a fresh surrogate:
  a rf fitted by leave-one-out on ACE2's own docking labels ranks them fine.
  The narrow chemotype that makes ACE2 hard for the frozen models makes it
  *easier* for LOO (every held-out molecule has near-identical neighbours to
  interpolate from). This corrects the Pass-9 framing: ACE2 is not "no signal
  available," it is "the shipped models have no signal there."
- Cross-target transfer works for ligand-only features because docking rank is
  substantially receptor-independent -- an unanticipated property of the metric,
  and the reason the transfer test cannot answer the question it was designed
  for.
- F3 surfacing CHEMBL2315019 at rank 3 is the first time in ten passes anything
  prescreen-usable has ranked that molecule near the top. It does not survive
  into a better ranker, but it localises what ECFP4 misses about it:
  aromatic-count and H-bond-acceptor complementarity, not substructure identity.
- The F4 pose features underperforming fingerprints was not expected -- it
  suggests either the interaction featurisation is too crude or the ACE2 LOO
  fit is simply very strong on a narrow set (probably both).

## Conclusion for the record

Receptor-aware features computable without docking (F2 shape, F3 pharmacophore
complementarity) **do not beat ligand-only fingerprints + descriptors** on cox2
or ACE2, under LOO affinity Spearman or as rankers. The cross-target transfer
test intended to distinguish "encodes fit" from "encodes this set" is
inconclusive: ligand-only features transfer too (docking rank is largely
receptor-independent), so a receptor-aware family transferring is not
diagnostic, and none transfers better on ranking anyway. The pose-derived
ceiling (F4, ACE2, not a prescreen) is R^2 ~0.45 -- signal exists in the pose
but a crude interaction-feature set extracts it *worse* than fingerprints. Net:
the surrogate direction is not advanced by cheap receptor-aware features as
built here; the remaining paths (proper interaction fingerprints, a better cheap
binding model, a larger diverse candidate set) are unchanged from the Pass-8/9
open-problems list. F3's rank-3 placement of the long-standing cox2 outlier is a
mechanism worth remembering but is not, on its own, a better prescreen.

No policy change made or recommended. Frozen v7 policy, docking params, and the
four frozen contracts untouched. `funnel/receptor_features.py` and
`funnel/pass10_eval.py` are additive and offline. No published number edited or
retracted.

---

# Pass 11 -- PRE-REGISTRATION: are F1 and F3 complementary, or is the investigation closed? (2026-08-30)

Committed BEFORE `funnel/pass11_eval.py` exists or runs. **This is the final
pass of the funnel prescreen investigation, regardless of outcome.**

Pass 10 closed the receptor-aware question negative. One live thread: on cox2,
F3 (pharmacophore x pocket) ranks `CHEMBL2315019` -- the out-of-distribution
outlier nothing surfaced in ten passes -- at rank 3 of 45, while ranking the
mid-pack worse; F1 (ligand-only ECFP4) is the reverse. This pass asks whether
combining them nets a gain, or whether it is the same "finds the outlier,
strands the easy ones" trade with no net improvement (Pass 7 `maxmin_diversity`).

No new docking. No new feature families. No new targets. Frozen v7 policy,
docking params, and the four frozen contracts (ComputeRouter / ResourceManager /
JobStore / tool-registry) untouched. Additive, offline. Published numbers are
appended to, never edited or retracted.

## Primary metric

**recall@10 literal** (first N to full 10/10 recovery), per Pass 8. recall@10
tie-credited and recall@5 literal/tie-credited reported as secondary.

## Combination methods (three, capped, no post-hoc additions)

| # | method | rule |
|---|---|---|
| **C1** | rank-average | for each molecule, average its position in F1's LOO-OOF ascending order and F3's; re-sort ascending. No new model fit. |
| **C2** | concat + single rf | horizontally stack F1's 1034 features and F3's 23 features (1057 total); one `RandomForestRegressor(n_estimators=300, random_state=0)`, LOO, refit per fold. |
| **C3** | F1 primary, F3 re-ranks F1's shortlist | take F1's LOO-OOF order; re-sort its top-K by F3's LOO-OOF predicted affinity (ascending); tail unchanged. K = F1's own first-N-to-recall@10-10/10 (22 on cox2, 21 on ACE2 -- F1's operating point, fixed before this pass, not chosen to reach any specific molecule). |

## Declared margin (before computing anything)

F1 and F3 differ by 0.047 LOO Spearman on cox2 (inside n=45 noise) and are
identical on ACE2 (0.637 = 0.637). To call F1+F3 **complementary** (a real
result), a combination method must, **on BOTH targets simultaneously**:

- **(a)** beat the better single family's LOO Spearman by **>= 0.05** (just
  above the 0.047 cox2 F1<->F3 gap), AND
- **(b)** reach full recall@10 literal (10/10) at **>= 3 N fewer** than the
  better single family (3 N being the minimum this grid can resolve on one
  candidate set with no resampling -- the same resolution floor Passes 6-7
  used).

An improvement on one target only is **not** an improvement and will be stated
as such. Anything below this margin closes the investigation with no further
recommendation and no follow-up pass.

## Protocol

- LOO, Pass-5 rf hyperparameters unchanged (`n_estimators=300, random_state=0`),
  no scaling for rf, refit inside every fold. cox2 n=45; ACE2 n=39 usable.
- Per method per target: LOO Spearman, R^2, MAE vs mean affinity, next to F1 and
  F3 alone (recomputed fresh, deterministic).
- Each method as a ranker through the existing frontier logic: recall@10
  literal + tie-credited (primary), recall@5 literal + tie-credited (secondary),
  first N to full recovery, vs frozen v7 and (cox2 only) the Pass-5 surrogate as
  references.
- Ranks of the known-hard molecules: `CHEMBL2315019` on cox2; `CHEMBL402987`
  (#2), `CHEMBL252417` (#3), `CHEMBL400527` (#5) on ACE2.
- No tuning against recall. K in C3 is fixed above before any result is seen.

Expected outcome, stated so it is falsifiable: **no method clears the margin on
both targets.** C2 (concat) is expected to be ~= F1 alone, because rf feature
subsampling (`max_features='sqrt'` ~ 32 of 1057) will pick an F3 column only ~2%
of the time and the 1024 ECFP bits dominate. C1 (rank-average) and C3 (re-rank)
may edge one target and lose the other -- the "finds the outlier, strands the
easy ones" trade averaging out, not cancelling. A both-target clearance of the
declared margin would be the only real result and would be a surprise.

## Results (`funnel/pass11_eval.py`, `runs/pass11_eval.json`)

LOO (rf, Pass-5 protocol) and each method as a ranker through the frontier
logic. C3's K = F1's own first-N-to-recall@10-10/10 (22 cox2, 21 ACE2), fixed
before running.

### cox2_v1 (n=45)

| method | LOO Spearman | R^2 | MAE | first N r@10 10/10 | first N r@10t 10/10 | first N r@5 5/5 | CHEMBL2315019 rank |
|---|---:|---:|---:|---:|---:|---:|---:|
| F1 | 0.687 | 0.407 | 0.434 | 22 | 20 | 22 | 20 |
| F3 | 0.734 | 0.483 | 0.429 | 26 | 13 | 23 | **3** |
| C1 rank-average | 0.753 | n/a | n/a | 25 | 10 | 25 | 9 |
| C2 concat + rf | 0.707 | 0.418 | 0.440 | 20 | 20 | 20 | 20 |
| C3 F1 then F3-rerank top-22 | **0.780** | n/a | n/a | **19** | 10 | **18** | **3** |

### ace2_v1 (n=39 usable)

| method | LOO Spearman | R^2 | MAE | first N r@10 10/10 | first N r@10t 10/10 | first N r@5 5/5 | #2 / #3 / #5 rank |
|---|---:|---:|---:|---:|---:|---:|---|
| F1 | 0.637 | 0.548 | 0.389 | 21 | 11 | 14 | 11 / 14 / 12 |
| F3 | 0.637 | 0.529 | 0.415 | 34 | 7 | 16 | 6 / 4 / 12 |
| C1 rank-average | 0.639 | n/a | n/a | 27 | 8 | 16 | 8 / 9 / 14 |
| C2 concat + rf | 0.625 | 0.540 | 0.400 | 26 | 12 | 15 | 12 / 15 / 11 |
| C3 F1 then F3-rerank top-21 | **0.696** | n/a | n/a | **20** | 7 | 15 | 6 / 4 / 12 |

### Declared-margin check (pre-registered: both targets, LOO Spearman > better-single by >= 0.05 AND recall@10 literal 10/10 reached >= 3 N earlier)

| method | cox2: d(Spearman), d(N) | ACE2: d(Spearman), d(N) | clears both? |
|---|---|---|---|
| C1 rank-average | +0.019, -3 | +0.001, -6 | **no** |
| C2 concat + rf | -0.028, +2 | -0.012, -5 | **no** |
| C3 F1 then F3-rerank | +0.045, +3 | +0.059, +1 | **no** |

*(d(Spearman) = method minus the better of F1/F3; d(N) = better-of-F1/F3's N to
recall@10 10/10 minus the method's, positive = method is earlier.)*

**No method clears the declared margin on both targets.**

## Task 2 -- the closing

**F1 and F3 are not complementary in the pre-registered sense. The funnel
prescreen investigation is closed.**

- **C2 (concat + rf) is F1 with noise.** LOO Spearman 0.707 / 0.625 (below F3 on
  cox2, below F1 on ACE2), and it ranks `CHEMBL2315019` at exactly F1's rank
  (20), confirming what the pre-registration predicted: rf feature subsampling
  drowns the 23 F3 columns under 1024 ECFP bits. Adding F3 to the matrix does
  nothing.
- **C1 (rank-average) dilutes both.** It splits the difference on the outlier
  (`CHEMBL2315019` rank 9, between F1's 20 and F3's 3) and is a worse full-r@10
  ranker than F1 on both targets (N=25 / N=27 vs F1's 22 / 21). Averaging two
  orderings that disagree about which molecules are hard produces an ordering
  worse than either at what each is good at.
- **C3 (F1 primary, top-K re-ranked by F3) comes closest and still does not
  clear.** It is directionally consistent -- LOO Spearman up on both targets
  (0.780 cox2, 0.696 ACE2, both above either single family), full recall@10
  reached slightly earlier on both (N=19, N=20) -- and it keeps F3's rank-3
  placement of `CHEMBL2315019` while not wrecking the mid-pack the way F3 alone
  does (cox2 r@5 5/5 at N=18 vs F1's 22 and F3's 23). But every individual
  gain is at or inside the resolution floor declared before running: cox2
  d(Spearman) = +0.045 (below the +0.05 threshold by 0.005) with d(N) = +3;
  ACE2 d(Spearman) = +0.059 (clears) with d(N) = +1 (below +3). Each target
  clears one of the two conditions and misses the other, and never the same
  one. That is the "finds the outlier, strands the easy ones" trade partly
  averaging out, not a net gain above noise -- exactly what the pre-stated
  honesty constraint said would not count.
- **C3 is also fragile by construction:** it can only re-order what F1 already
  puts in its top-K. `CHEMBL2315019` is at F1 rank 20 <= K=22 on cox2, so C3
  can pull it forward; had F1 ranked it 23rd, C3 could not. The one visible
  positive depends on F1 nearly getting it right already.

The durable takeaway from Passes 10-11 is a **mechanism, not a method**: F3's
pharmacophore-product features (ligand aromatic count x pocket aromatic
residues; ligand H-bond-acceptor count x pocket donor atoms) localise what
ECFP4 misses about `CHEMBL2315019` -- aromatic and H-bond-acceptor
complementarity, not substructure identity. Whether that mechanism can be
turned into a prescreen that beats F1 on a metric that a single 45-molecule set
can resolve is not answered here and is not pursued further.

No policy change made or recommended. No follow-up experiment. Frozen v7 policy,
docking params, and the four frozen contracts untouched. `funnel/pass11_eval.py`
is additive and offline. No published number edited or retracted; the Pass 9
correction note above is appended, not an edit.

## Task 3 -- Pass 9 correction propagation (verified / fixed this pass)

The Pass-10 finding that ACE2's "no signal" is about the *shipped* models, not a
fresh surrogate, now appears in all three places:
- `docs/FINDINGS.md` -- Stage 7 ("Correction to Stage 6"), plus a forward
  pointer added at the end of Stage 6 this pass.
- `README.md` -- the ACE2 held-out section, correction bullet added this pass.
- this file -- the appended correction note at the end of the Pass 9 entry
  above, added this pass (not an edit to Pass 9's text).
