# Computational funnel, findings

Nine passes of offline evaluation on the DrugForge computational funnel. This
document reads the evidence already in `backend/app/funnel/CHANGELOG.md` and the
`runs/` artifacts; it adds no experiments and no numbers. Every figure below is
traceable to a committed artifact, cited inline.

**One-line result:** cheap ligand-only prescreening cannot recover a docking
baseline's top hits at a meaningful compute saving on a 45-molecule set. The
shortfall has two separable causes: a data-coverage problem for
out-of-distribution top dockers, and a ranking-formula problem for the
mid-pack. One of the two is partly fixable with real docking labels. This
is a characterised trade-off with a named failure mode, not a solved problem.

The frozen policy `v7_binding_weak_cox2` and the docking configuration
(exhaustiveness 8, `--cpu 1`, seeds `[1, 42, 2024, 31337]`, conformer seed 42)
have not changed since they were selected on `cox2_v1`. Nothing below tunes,
edits, or retracts any published number; corrections are additive.

> **Pass-number note.** The brief for this synthesis labels the six
> investigations P4-P9. They map to `CHANGELOG.md` as: the 8-variant sweep is
> **Pass 2**; the surrogate, two-phase, seed-diversity, metric, and held-out
> passes are **Pass 5-9**. This document uses descriptive stage names and cites
> the CHANGELOG pass where each result lives.

---

## The narrative arc

### Stage 1, reweight the nine existing models (CHANGELOG Pass 2; recall@10 re-read in Pass 8 Task 2)

**Believed:** the multi-objective prescreen ranks candidates badly because the
weights are wrong. A better linear combination of the nine existing model
outputs should recover more of the baseline's top hits.

**Measured:** eight `FunnelPolicy` variants scored offline against
`runs/baseline_cox2_v1.json`, the original multi-objective ranker, binding-only
(three filter settings), a no-ML descriptor heuristic, a binding/descriptor
blend, ligand-efficiency normalisation, and binding-with-a-weak-cox2-tiebreak.
Literal recall@5 was **1/5 for seven of the eight** (`v6_ligand_efficiency`
alone at 0/5, it rewards fragments). Under recall@10 (re-read in Pass 8) the
same eight span **1/10 to 5/10**, which does separate the genuine loser (v6)
and the physicochemistry-only heuristic (v4, 3/10) from the binding-driven
rankers (v1/v7, 5/10), a distinction recall@5 could not make.
`v7_binding_weak_cox2` was adopted on those secondary grounds (recall@10, and
demoting the misleading `cox2` term to a 0.15 tiebreak); recall@5 was
explicitly not improved.

**Changed:** the working conclusion became *"the ceiling is the models, not the
ranking formula."* Stage 2 shows that statement is too strong.

Artifacts: `runs/frontier_cox2_v1.csv`, CHANGELOG Pass 2.

### Stage 2, a surrogate trained on real docking labels (CHANGELOG Pass 5)

**Believed:** if reweighting nine imperfect models cannot help, a regressor
fitted directly on real Vina affinities might, it is predicting the exact
quantity the prescreen fails at.

**Measured:** `ECFP4 (radius 2, 1024 bits) + 10 RDKit descriptors -> mean Vina
affinity`, n = 45, leave-one-out. Three fixed-hyperparameter models. LOO
affinity fit: ridge R2 0.337 / rho 0.607; **rf** R2 0.401 / rho 0.679 (primary,
chosen by rho before any recall number); `krr_tanimoto` R2 -2.738 / rho 0.482
(logged loser). Modest but real signal for docking score.

As a ranker over the 41 hard-filter survivors: full literal recall@5 recovery
at **N = 21 (rf) / N = 20 (ridge)** versus frozen v7's **N = 32**; full
recall@10 at **N = 21** versus v7's **N = 36**. Below N ~ 13 the surrogate is
level with or behind v7, at the strict N = 5 cut, rf scores **0/5** (worse
than v7's 1/5); ridge scores 1/5.

`CHEMBL2315019` (baseline #1, true -7.56 kcal/mol, a 0.75 kcal/mol outlier
above #2): LOO prediction -5.89 (rf) / -5.96 (ridge), ranked 18th / 15th of 41.
**Never in a surrogate top-5.** It has no close structural analogue in the set
(a naproxen-acridone hybrid), so a LOO model has nothing to interpolate from
and shrinks it toward the set mean.

**Changed:** the Stage 1 conclusion splits in two.
- The **outlier is a data-coverage problem**, no regression on ligand-only
  features recovers a point with no neighbours, just as no reweighting did.
- The **mid-pack (baseline ranks ~6-20) was a ranking-formula problem after
  all**, the same features the prescreen already had, fitted on real labels,
  cut the budget for full top-5 recovery from N ~ 32 to N ~ 20-21 (a further
  ~1.4-1.5x docking saving), holding for two independent models.

The surrogate is target-specific: it needs ~44 real docking labels per fold.
It is not a cold-start prescreen.

Artifacts: `runs/surrogate_cox2_v1.json`,
`runs/frontier_surrogate_cox2_v1.{csv,svg}`, CHANGELOG Pass 5.

### Stage 3, two-phase: a small v7-selected seed batch (CHANGELOG Pass 6)

**Believed:** the Stage 2 surrogate is impractical (you would have had to dock
almost everything). The realistic version: dock a small seed batch chosen by v7
alone, fit the rf surrogate on just those labels, spend the rest of the budget
on what it then says. Some of Stage 2's advantage should survive at a
committable up-front budget.

**Measured:** seed size S in {5, 8, 10, 13, 16, 20} (declared before running),
N swept S->41, 180 cells. Phase-2 held-out Spearman: **-0.334 at S=5**, -0.412
at S=8, +0.198 at S=10, then +0.411 / +0.733 / +0.701 at S=13/16/20. Full
literal recall@5 recovery: best two-phase cell **S=16 at N=26** (S=13->28,
S=20->30, a 26-30 plateau once S>=13), all ahead of v7's N=32, all **behind
the Stage-2 surrogate's N=21** at every S.

**Diagnosed cause:** v7's own top-S is a **narrow affinity band**. The S=5
seed batch spans 0.9 kcal/mol of the set's 5.0 kcal/mol range; a regressor
with no label gradient produces a ranking closer to random than informative,
hence the negative Spearman. The band widens only slowly with S (1.6 kcal/mol
at S=13, 2.0 at S=20).

**Changed:** two-phase beats cold-start v7 (S>=13) but loses to the full-label
surrogate by ~1.2x at its best S. The bottleneck is not sample count alone;
it is **label diversity**.

Artifacts: `runs/two_phase_cox2_v1.{csv,json,svg}`, CHANGELOG Pass 6.

### Stage 4, diversity seed selection (CHANGELOG Pass 7, pre-registered)

**Believed (pre-registered before the code existed):** if v7-top-S is a narrow
band, picking the seed batch for feature-space spread should widen the label
range, clear the Spearman noise floor at a smaller S, and close the gap to the
Stage-2 reference.

**Measured:** four selection strategies, `control_v7_topS`,
`maxmin_diversity` (greedy farthest-point in the 1034-dim feature space),
`stratified_v7_score` (evenly spaced across the v7 rank order), `random_seed0`
(uniform random). 24 (strategy, S) fits, 720 grid cells; both leakage guards
asserted per cell, zero fires. Held-out Spearman at S=5: control **-0.334**,
maxmin +0.431, stratified +0.518, **random +0.525**. First S to clear rho >= 0.4:
control S=13; all three alternatives **S=5**, four declared-S steps earlier.
range-vs-quality correlation across 24 cells: Pearson **+0.505** (real, moderate, 
not the whole story).

Full literal recall@5 recovery: nothing reliably beats the Stage-2 reference
N=21. One cell, `maxmin_diversity` S=5, N=20, nominally does, and is reported
as **noise**: a single cell in a 24-cell grid, a non-monotonic neighbourhood
(20, 28, 35, 36, 25, 27 across S), a ~2% margin.

**Unanticipated:** `maxmin_diversity` docks `CHEMBL2315019` early in every S
(N = 18, 10, 17, 13, 16, 20, often earlier than any other strategy) yet its
"first N to 5/5" is frequently among the *worst* in the grid (S=10 -> 35,
S=13 -> 36). Farthest-point search surfaces a structural outlier fast, but the
same property strands an easy, representative true-positive that a
score-based or random ordering reaches sooner. Diversity trades one kind of
miss for another; it does not dominate.

**Changed:** seed selection was a real, easily-fixed problem, but **not the
binding constraint**. Uniform random beating v7-top-S means v7-top-S was a
*specifically* bad selector, not that selection is decisive. The remaining gap
to N=21 is the **label budget** (S<=20 vs the reference's ~44), not the
selection rule.

Artifacts: `runs/seed_diversity_cox2_v1.{csv,json,svg}`, CHANGELOG Pass 7.

### Stage 5, the metric itself (CHANGELOG Pass 7 Task 5, Pass 8)

**Believed:** the recall@5 milestone is a smooth function of prescreen quality,
so it can discriminate between policies.

**Measured:** `funnel/concentration_check.py` re-read all 34 policy curves
computed across Passes 2-7 (v7 + 3 surrogate + 6 two-phase + 24
seed-diversity). **18 of 34 (53%)** reach literal recall@5 = 5/5 at the *exact*
N at which `CHEMBL2315019` first enters the docked set. `funnel/measurement_recall10.py`
(Pass 8) recomputed every recall@5 and recall@10 value from the same frozen
functions and asserted equality with each committed artifact, **34/34 passed**, 
then measured the same coincidence for recall@10: **10 of 34 (29%)**, with the
"last hit recovered" spread across **9 of the 10** true-top-10 members
(`CHEMBL2315019` x10, `CHEMBL6` x7, `CHEMBL149781` x4, and six others). Gap
between 9/10 and 10/10: median 3 extra docks, max 16. Completion-N spread is
comparable under both metrics (std 5.27 vs 4.95), so recall@10 does not lose
discriminative power.

**The one flip:** Pass 7's only nominal win (`maxmin_diversity` S=5, N=20 vs
reference N=21) needs **N=29 under recall@10** against the reference's N=21, a
clear loss. Confirms the Pass-7 noise call rather than reversing it. No other
prior conclusion changes direction.

**Changed:** **recall@10 literal is adopted as the primary metric; recall@5
literal is retained as a published secondary.** No recall@5 number is
retracted. Stated caveat (Pass 8's own): recall@10 is *less* degenerate, not
*non*-degenerate, `CHEMBL2315019` is still the single most common straggler at
29%, versus the 10% a uniform draw over ten targets would give.

Artifacts: `runs/concentration_cox2_v1.json`,
`runs/measurement_recall10_cox2_v1.{csv,json}`, CHANGELOG Pass 7 Task 5, Pass 8.

### Stage 6, the held-out ACE2 target (CHANGELOG Pass 9)

**Believed (pre-registered in CHANGELOG Pass 4, before any ACE2 result):**
held-out recall on `ace2_v1` will be **lower** than on `cox2_v1`, for
target-intrinsic reasons, Vina does not model ACE2's catalytic zinc (MLN-4760,
Ki ~0.44 nM, docks at only -6.0), and `ace2_v1` is one narrow chemotype
(Phe-Pro dipeptide mimics with thiol / phosphinic / boronic warheads). Not a
policy defect. Falsifiable: literal recall@5 ace2 <= cox2; tie-credited
recall@5 ace2 < 4/5 at N=10; 0 hard false negatives.

**Measured:** `runs/baseline_ace2_v1.json`, 45 candidates, corrected
Zn-centred box, docking config identical to cox2, 180 jobs, 9322 s (2.6 h).

- **Completion: 39/45.** Six failures, all boronic acids, all deterministic:
  `PDBQT parsing error: Atom type B is not a valid AutoDock type`, every seed,
  ~0.05 s at the Vina parse step. **Reported as 45 with 6 explicitly
  excluded**, never as a bare 39, the denominator change was outside the
  pre-registration and is kept visible.
- **Run is sound.** The four reference ligands reproduce the Pass-3 box-fix
  sanity docks: MLN-4760 -6.32 (box-fix -6.00, within ~1sigma; it was the noisiest
  of the four then, sd 0.36), lisinopril -5.80 (-5.80), captopril -4.39
  (-4.39), ethanol -2.65 (-2.65); potency order preserved exactly.
- **Frozen v7 held-out: 0 false negatives.** recall@10 literal 10/10 at
  **N=35** (cox2 N=36); recall@10 tie-credited 10/10 at **N=24** (cox2 N=32);
  recall@5 literal 5/5 at N=30 (cox2 N=32); recall@5 literal at N=10 is **1/5**
  (cox2 2/5). Mean baseline rank of v7's top-10 picks **20.4** (cox2 ~12.6).
- **Pre-registration verdict:** holds for recall@5 and the early/mid curve
  (ACE2 is lower everywhere through N ~ 24); a **wash at full recovery on the
  current primary metric** (recall@10 N=35 vs 36); ACE2 *beats* cox2 on
  tie-credited recall@10 (N=24 vs 32). The prediction was framed in the
  recall@5 era; on the metric adopted in Stage 5 it does not hold as "lower."
- **No dominant straggler on ACE2.** The baseline top-10 sit at v7 prescreen
  ranks `[1, 7, 12, 13, 15, 22, 24, 25, 30, 35]`, median 18 of 38 survivors.
  There are **three** analogues of `CHEMBL2315019` (baseline #2/#3/#5, all
  mid-pack `binding_score` ~5.4-5.7, all buried at prescreen 22-30), not one.
  `P(ace2)` is anti-informative for docking rank on its own target's set (0.93
  for baseline #4/#5, 0.08-0.39 for #1/#2/#3).

**Changed:** Pass 8's "recall@10 is less degenerate" is a **cox2-specific**
property, it dilutes cox2's lone outlier. On ACE2 both metrics are diffusely
hard because there is no outlier to dilute; the cheap `binding_score` model has
near-zero rank signal across the whole peptidomimetic top-k.

Artifacts: `runs/baseline_ace2_v1.json`, `runs/heldout_ace2_v1.json`,
`runs/frontier_ace2_v1.{csv,svg}`, `runs/frontier_ace2_vs_cox2_pass9.svg`,
CHANGELOG Pass 9.

---

## Results that are not about DrugForge

These would apply to anyone building a molecular-docking evaluation.

### 1. Benchmark degeneracy in small screening sets is general but composition-dependent

A 45-molecule benchmark's recall milestone can be dominated by the behaviour on
a handful of molecules, but *which* molecules, and how concentrated, depends
on how the set was sampled.

- **Diverse source (cox2_v1: 8105 unique molecules in the ChEMBL export):**
  hardness concentrates in one out-of-distribution outlier. 53% of literal
  recall@5 completion events across 34 policies land on the exact dock of one
  molecule (`concentration_cox2_v1.json`). The metric is largely a
  single-molecule detection test.
- **Narrow source (ace2_v1: 122 unique, one scaffold family):** near-zero
  cheap-model rank signal spread across the *whole* top-k (baseline top-10 at
  prescreen ranks median 18 of 38), plus 13% of the set un-dockable by the
  method at all. No single molecule dominates; every top docker is roughly
  equally invisible.

A single-target benchmark cannot tell you which regime you are in. You need at
least two targets of deliberately different chemical diversity to distinguish
"my prescreen fails on outliers" from "my prescreen has no signal here."

### 2. A tie threshold calibrated on one target does not transfer

`TIE_EPSILON = 0.10 kcal/mol` was pre-registered and calibrated on `cox2_v1`,
whose per-candidate seed standard deviation has median **0.036**, so the
window sits ~3x above the docking's own noise floor and groups only pairs the
search genuinely cannot resolve.

`ace2_v1` docking is **~3x noisier**: median seed sigma **0.110**, with 22 of 39
candidates exceeding TIE_EPSILON versus 11 of 45 on cox2. The same fixed 0.10
window now sits **below** the ACE2 noise floor, it calls pairs 0.10-0.22
kcal/mol apart "distinct ranks" when four random seeds cannot tell them apart.
On ACE2, literal recall understates and tie-credited recall is the more honest
read.

**This is a method finding, not a correction to a number.** TIE_EPSILON stays
at 0.10; the frozen constant's figures are the held-out result of record. The
correct design going forward is a **per-set epsilon scaled to that set's own
median seed sigma** (or a fixed small multiple of it), computed at evaluation time,
not a single hardcoded window.

### 3. Vina has hard chemistry boundaries

Boron has no AutoDock atom type. Six of the 45 `ace2_v1` candidates (13%) are
boronic acids; all six fail **deterministically** at the PDBQT parse step in
~0.05 s, identically across all four seeds:
`PDBQT parsing error: Atom type B is not a valid AutoDock type`. Meeko writes a
syntactically valid PDBQT containing a `B` atom; Vina rejects it. No seed,
exhaustiveness, or box change helps, the molecule simply cannot be scored by
this function.

Any docking evaluation over real medicinal-chemistry sets, which routinely
contain boronic-acid warheads, organometallics, and other non-standard
elements, will silently lose those molecules unless the pipeline checks for
un-scorable atoms up front and reports the exclusion.

---

## What would be needed to break the ceiling

Open problems, stated as such, not a committed roadmap.

- **Docking-aware cheap features.** The current features are ligand-only
  (ECFP4 + physicochemical descriptors). They carry a real but limited signal
  for docking score (LOO rho about 0.6-0.7) and miss out-of-distribution top dockers
  entirely. Features that encode the ligand *against the pocket* (interaction
  fingerprints, pharmacophore-to-pocket distances, shape complementarity)
  would be a different input class, not a reweighting of this one.

- **A larger, deliberately diversity-stratified candidate set.** Pass 8 Task 4
  scoped a ~100-molecule cox2 rebuild at ~4.4 h of docking and near-zero
  tooling change. It would dilute cox2's one-outlier concentration (5-10 hard
  molecules instead of 1, and the outlier gains neighbours). It would **not**
  address ACE2's problem, which is weak feature signal, not sample size.

- **A fundamentally better cheap binding predictor.** The `binding_score` model
  was trained on broad, mostly non-peptidic data; on the narrow ACE2
  peptidomimetic set it has almost no rank signal, and `P(ace2)` is
  anti-informative. A predictor trained on docking scores directly, or on
  binding data broad enough to cover warhead chemistry, is a separate modelling
  effort.

- **Explicit handling of non-Vina-tractable chemistry.** Either a scoring
  function that parameterises boron and metals, or a pre-filter that excludes
  and reports un-scorable molecules rather than letting them fail silently
  mid-run.

None of these is small. The honest current state is a characterised trade-off:
at a docking budget of N ~ 10 of 45, the frozen funnel recovers 2/5 of the
cox2 baseline's top-5 (4/5 tie-credited) with 0 false negatives at a ~4x
wall-clock saving; full recovery needs N ~ 32 (~1.7x saving); and the single
hardest molecule is unreachable by any cheap ranker tested.

---

## Methodology notes (what makes this checkable)

- **Pre-registration before each pass.** The ACE2 prediction and its
  falsifiable expectations (CHANGELOG Pass 4). The two-phase S range
  `{5, 8, 10, 13, 16, 20}` (Pass 6, "not extended after seeing results"). The
  four seed-diversity strategies and their one-line hypotheses, written before
  `seed_diversity.py` existed (Pass 7). The metric-selection *rule* stated
  before the recall@10 concentration numbers (Pass 8 Task 3).

- **Losers kept.** `v6_ligand_efficiency` (0/5, rewards fragments).
  `krr_tanimoto` (LOO R2 -2.74, Tanimoto neighbourhood too sparse at n=45).
  Two-phase S = 5 / 8 / 10 (worse than v7, non-monotonic in S). All 24
  seed-diversity cells including the failures. Every discarded ranker variant
  is in `CHANGELOG.md` with the reason.

- **Leakage guards asserted per cell, not merely intended.** Pass 6/7 **G1**:
  each strategy function receives only the v7 prescreen order plus the feature
  matrix, never the baseline, an affinity, or a Pass-5 out-of-fold prediction
  (there is no argument for it to consult by accident). **G2**: `fit_phase2()`
  asserts exactly S training rows and train/held-out id disjointness
  immediately before every `model.fit()`. Zero assertion fires across 180
  (Pass 6) + 720 (Pass 7) grid cells. Pass 5: leave-one-out with the scaler
  and kernel refit inside each fold; the fit-on-everything number (ridge
  in-sample R2 0.999, recall@5 5/5) is labelled a leaked upper bound and never
  reported as a result.

- **Recomputation integrity.** Pass 8 re-derived every recall@5 and recall@10
  value for all 34 policies from the same frozen deterministic functions and
  asserted equality with the committed artifacts, 34/34 passed. Pass 9's
  `heldout_ace2.py` cross-checks zero-mismatch against `funnel.frontier --set
  ace2_v1`.

- **Following the declared protocol cost the headline at least twice.**
  1. Pass 5's primary model was chosen by leave-one-out affinity Spearman
     *before* any recall number was looked at. That selected `rf`, which is
     **worse** at the strict recall@5 cut (0/5) than `ridge` (1/5) or frozen v7
     (1/5). The disciplined choice lost the cleaner headline; the mixed result
     is what is reported.
  2. Pass 7's only cell that nominally beat the Pass-5 reference
     (`maxmin_diversity` S=5, N=20 vs N=21) was called **noise** on the
     pre-declared multiple-comparisons grounds and not promoted. Pass 8
     confirmed it (N=29 under recall@10).

---

## Contradictions between passes

Two places where a pass's conclusion is inconsistent with another pass or with
its own artifact. Both are recorded here as additive corrections; no published
number is edited.

1. **Cox2 recall@5 at N=10: "1/5" (Pass 4) vs "2/5" (Pass 3 and the committed
   frontier).** The Pass-4 pre-registration anchors its comparison on
   *"literal recall@5 on cox2 ... is 1/5 at N=10."* Pass 3's frontier, the
   immediately preceding pass, and `runs/frontier_cox2_v1.csv` both give
   **2/5 at N=10** (1/5 is the N = 4-9 plateau, and also the value of the live
   20-dock funnel run). The pre-registration's *direction* is unaffected (ACE2
   is 1/5 at N=10, which is <= 2/5), but the anchor figure is wrong. Flagged in
   Pass 9; recorded here.

2. **Distinct recall@5 stragglers: "1" (Pass 8 Task 1 table) vs "4" (Pass 8's
   own artifact, and Pass 7).** The Pass-8 Task-1 table cell reads *"distinct
   molecules that are ever the [recall@5] straggler: 1 (by construction, only
   one target)."* The pass's own committed `runs/measurement_recall10_cox2_v1.json`
   (`rows`) shows **four**: `CHEMBL2315019` x18, `CHEMBL34913` x6,
   `CHEMBL184613` x5, `CHEMBL111786` x5. Pass 7 Task 5 independently states
   `maxmin_diversity` "stalls on a *different* top-5 member" (never
   `CHEMBL2315019`). The **53% coincidence rate is correct and unaffected**:
   it counts only exact-N coincidence with `CHEMBL2315019`, and 18/34 is right.
   But "recall@5 is a one-molecule detection test" is slightly overstated: it
   is a `CHEMBL2315019` detection test in 53% of the 34 policies and a
   *different* top-5 molecule's detection test in the other 47%. This one does
   not appear to have been noticed before now.
