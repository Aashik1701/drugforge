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

## Data-derived (not tuning)

`binding_norm` = min-max scaling of the `binding_score` predictions across the
funnel's filter survivors, computed at run time and recorded in the run
record's `notes` (`binding_min` / `binding_max`). This is feature
normalisation; it introduces no hand-set constant.
