"""
FunnelPolicy — THE SEAM.

Every filter threshold and every term of the ranking function lives in this one
dataclass. The funnel path (`funnel.funnel`) contains NO magic numbers of its
own; it asks this object. An LLM planner replaces this object later and nothing
else in the funnel changes.

Nothing here is tuned to make the eval headline look good. Weights and cutoffs
are set from ADMET domain conventions (Lipinski / Veber, permissive tox gates).
The only data-derived quantity is min-max feature scaling of two continuous
predictors, computed from the candidate set at runtime — that is feature
normalisation, not threshold tuning, and it is logged in the run record.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# Order of the 10 descriptors returned by utils.rdkit_helper.extract_descriptors
DESCRIPTOR_NAMES = [
    "MolWt", "MolLogP", "NumHDonors", "NumHAcceptors", "TPSA",
    "NumRotatableBonds", "NumAromaticRings", "NumSaturatedRings",
    "RingCount", "FractionCSP3",
]


@dataclass(frozen=True)
class HardFilters:
    """A candidate failing ANY of these is dropped and never docked."""

    mw_max: float = 550.0
    logp_min: float = -1.0
    logp_max: float = 6.0
    hbd_max: int = 5
    hba_max: int = 10
    tpsa_max: float = 150.0
    rotatable_max: int = 12
    # Permissive toxicity gates: only drop the clearly-flagged.
    p_toxicity_max: float = 0.80   # hERG-based general toxicity model
    p_hepg2_max: float = 0.80      # hepatocyte toxicity model


@dataclass(frozen=True)
class RankWeights:
    """Linear weights for the rank score (higher score = better candidate)."""

    w_cox2_active: float = 1.00      # P(COX-2 active) — the on-target signal
    w_binding: float = 1.00         # normalised binding-model desirability
    w_solubility: float = 0.30      # mild preference for soluble molecules
    w_toxicity_penalty: float = 0.50
    w_cyp3a4_penalty: float = 0.20  # DDI liability, mild


@dataclass(frozen=True)
class FunnelPolicy:
    top_n: int = 5
    hard: HardFilters = field(default_factory=HardFilters)
    weights: RankWeights = field(default_factory=RankWeights)

    # binding_score model (RandomForestRegressor). Despite the "kcal/mol" label
    # on the endpoint, the model emits a POSITIVE pAffinity-style score
    # (observed range ~4.4-7.1 on this set; the simulated fallback in
    # routers/binding_score.py also uses uniform(5.0, 9.5)) where HIGHER =
    # stronger binder — e.g. celecoxib 6.18, rofecoxib 6.12 vs aspirin 4.41,
    # ethanol 4.88. So higher is better here. (This is the model's own scale,
    # not Vina's; Vina's convention "more negative = better" still governs the
    # docked affinities in funnel.ranking.) Set from the dry-run distribution
    # before any docking was run — see funnel/CHANGELOG.md.
    binding_lower_is_better: bool = False

    # Solubility desirability: logS >= this is "fine"; below it, decays.
    solubility_logs_ok: float = -5.0
    solubility_decay: float = 1.5

    # ------------------------------------------------------------------
    def descriptors_pass(self, desc: dict[str, float]) -> tuple[bool, str]:
        h = self.hard
        checks = [
            (desc["MolWt"] <= h.mw_max, f"MolWt {desc['MolWt']:.0f} > {h.mw_max:.0f}"),
            (h.logp_min <= desc["MolLogP"] <= h.logp_max,
             f"MolLogP {desc['MolLogP']:.2f} outside [{h.logp_min}, {h.logp_max}]"),
            (desc["NumHDonors"] <= h.hbd_max, f"HBD {desc['NumHDonors']:.0f} > {h.hbd_max}"),
            (desc["NumHAcceptors"] <= h.hba_max, f"HBA {desc['NumHAcceptors']:.0f} > {h.hba_max}"),
            (desc["TPSA"] <= h.tpsa_max, f"TPSA {desc['TPSA']:.0f} > {h.tpsa_max:.0f}"),
            (desc["NumRotatableBonds"] <= h.rotatable_max,
             f"RotB {desc['NumRotatableBonds']:.0f} > {h.rotatable_max}"),
        ]
        for ok, msg in checks:
            if not ok:
                return False, msg
        return True, ""

    def tox_pass(self, preds: dict[str, float]) -> tuple[bool, str]:
        h = self.hard
        if preds["toxicity"] > h.p_toxicity_max:
            return False, f"P(toxic) {preds['toxicity']:.2f} > {h.p_toxicity_max}"
        if preds["hepg2"] > h.p_hepg2_max:
            return False, f"P(hepG2-toxic) {preds['hepg2']:.2f} > {h.p_hepg2_max}"
        return True, ""

    # ------------------------------------------------------------------
    def _solubility_desirability(self, logs: float) -> float:
        if logs >= self.solubility_logs_ok:
            return 1.0
        return math.exp((logs - self.solubility_logs_ok) / self.solubility_decay)

    def rank_score(
        self,
        preds: dict[str, float],
        binding_norm: float,   # 0..1, already normalised + direction-corrected (1 = best)
    ) -> float:
        w = self.weights
        return (
            w.w_cox2_active * preds["cox2"]
            + w.w_binding * binding_norm
            + w.w_solubility * self._solubility_desirability(preds["solubility"])
            - w.w_toxicity_penalty * max(preds["toxicity"], preds["hepg2"])
            - w.w_cyp3a4_penalty * preds["cyp3a4"]
        )

    # ------------------------------------------------------------------
    def as_dict(self) -> dict[str, Any]:
        import dataclasses
        return dataclasses.asdict(self)


DEFAULT_POLICY = FunnelPolicy()
