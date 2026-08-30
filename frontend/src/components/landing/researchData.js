/**
 * Single source of truth for every real number/claim used across the
 * landing page. Every value here is traceable to `docs/FINDINGS.md` (which
 * itself cites `backend/app/funnel/CHANGELOG.md` and committed `runs/`
 * artifacts). Nothing in this file is invented — if a section needs a number
 * that isn't here, it must be added here first, with its source, not typed
 * inline in a component.
 *
 * Do not edit docs/FINDINGS.md or CHANGELOG.md from this file or its
 * consumers — this is a read-only summary for display purposes.
 */

export const CHEMBL_OUTLIER = {
  id: 'CHEMBL2315019',
  description: 'a naproxen-acridone hybrid with no close structural analogue in the 45-molecule cox2 set',
  bindingAffinity: -7.56, // kcal/mol, real Vina result, CHANGELOG Pass 5 / FINDINGS Stage 2
  affinityMargin: 0.75, // kcal/mol above the #2 hit
  baselineRank: 1, // true docking baseline rank
  f1Rank: 20, // ligand-only ECFP4 + descriptors, FINDINGS Stage 7 / CHANGELOG Pass 10
  f3Rank: 3, // pharmacophore complementarity, same source
  totalCandidates: 45,
};

export const MODEL_FAMILIES = {
  f1: {
    name: 'F1 — Ligand-only',
    description: 'ECFP4 fingerprints (radius 2, 1024 bits) + 10 RDKit descriptors',
    looSpearman: { cox2: 0.687, ace2: 0.637 },
  },
  f3: {
    name: 'F3 — Pharmacophore complementarity',
    description: 'ligand pharmacophore counts × complementary pocket counts',
    looSpearman: { cox2: 0.734, ace2: 0.637 },
  },
};

export const FUNNEL_SUMMARY = {
  passCount: 11,
  primaryMetric: 'Recall@10 (literal)',
  frozenPolicy: 'v7_binding_weak_cox2',
  budgetForPartialRecovery: { n: 10, of: 45, literalRecall5: '2/5', tieCreditedRecall5: '4/5', falseNegatives: 0, wallClockSaving: '~4x' },
  budgetForFullRecovery: { n: 32, of: 45 },
  combinationVerdict:
    'F1 and F3 are not complementary in the pre-registered sense — no combination cleared the declared margin on both targets (CHANGELOG Pass 11).',
};

export const HELD_OUT_TARGET = {
  name: 'ACE2',
  candidateCount: 45,
  completed: 39,
  excludedReason: '6 boronic-acid candidates fail deterministically at the Vina PDBQT-parse step (no AutoDock atom type for boron)',
  chemotype: 'Phe-Pro dipeptide mimics with thiol / phosphinic / boronic warheads',
};

export const RESEARCH_CARDS = [
  {
    title: 'Model ceiling',
    body: 'Existing cheap predictors do not reliably recover every strong docking candidate — one out-of-distribution outlier was never in a ligand-only surrogate’s top-5 across eleven passes.',
  },
  {
    title: 'Chemical blind spots',
    body: 'A molecule can be underestimated when its chemistry lies outside what a predictor has seen. CHEMBL2315019 has no close structural neighbour in the training set, so ligand-only models shrink it toward the mean.',
  },
  {
    title: 'Evidence disagreement',
    body: 'A pharmacophore-complementarity feature family recovers that same outlier at rank 3 (versus rank 20) — but does so by trading away accuracy on the rest of the ranking. It localises the miss; it doesn’t fix it.',
  },
  {
    title: 'Compute matters',
    body: 'At a budget of roughly 10 of 45 candidates, selective docking already recovers most of the ranking’s value at a ~4x wall-clock saving. Full recovery still costs a much larger budget.',
  },
];

export const COMPUTE_TIERS = [
  { name: 'RDKit', cost: 'Low', role: 'Cheminformatics — parsing, descriptors, ligand prep' },
  { name: 'ML models', cost: 'Low', role: 'ADMET + binding prescreen across 9 trained models' },
  { name: 'Vina docking', cost: 'High', role: 'Physics-based structural evidence, allocated selectively' },
];

export const DOCKING_PIPELINE = ['SMILES', 'RDKit', 'Ligand preparation', 'Receptor', 'AutoDock Vina', 'Docking poses', 'Binding affinity'];

export const HERO_METRICS = [
  { value: '9', label: 'Scientific Models' },
  { value: 'ADMET + Binding', label: 'Multi-Lens Evidence' },
  { value: 'Physics-Based', label: 'Real Vina Docking' },
  { value: 'Adaptive', label: 'Compute Control' },
];
