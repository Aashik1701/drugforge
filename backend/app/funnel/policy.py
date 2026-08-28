"""
FunnelPolicy — THE SEAM.

Every filter threshold and every term of the ranking function lives in this one
dataclass. The funnel path (`funnel.funnel`) contains NO magic numbers of its
own; it asks this object. An LLM planner replaces this object later and nothing
else in the funnel changes.

`ranker` selects the ranking formula and `filter_mode` selects which hard
filters apply — so the offline sweep (funnel/sweep.py) can score many candidate
policies by constructing FunnelPolicy variants, without touching funnel.funnel.

Nothing here is tuned to make an eval headline look good. Thresholds come from
ADMET domain conventions (Lipinski / Veber, permissive tox gates). Two
continuous predictors get min-max feature scaling from the candidate set at
runtime — feature normalisation, not threshold tuning, logged in the run record.
Every change is recorded in funnel/CHANGELOG.md.
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

RANKERS = {
    "v1_multiobjective",   # w_cox2*P(cox2) + w_bind*binding_norm + w_sol*sol - w_tox*tox - w_cyp*cyp
    "binding_only",        # rank on binding_norm alone
    "descriptor_heuristic",  # rank on a drug-likeness descriptor-profile score (no ML)
    "binding_desc_blend",  # 0.7*binding_norm + 0.3*descriptor score
    "ligand_efficiency",   # binding_score per heavy atom
    "binding_weak_cox2",   # binding_norm primary, P(cox2) as a light tiebreak
}
FILTER_MODES = {"druglike_and_tox", "tox_only", "none"}


@dataclass(frozen=True)
class HardFilters:
    """A candidate failing ANY active filter is dropped and never docked."""

    mw_max: float = 550.0
    logp_min: float = -1.0
    logp_max: float = 6.0
    hbd_max: int = 5
    hba_max: int = 10
    tpsa_max: float = 150.0
    rotatable_max: int = 12
    p_toxicity_max: float = 0.80   # hERG-based general toxicity model
    p_hepg2_max: float = 0.80      # hepatocyte toxicity model


@dataclass(frozen=True)
class RankWeights:
    w_cox2_active: float = 1.00
    w_binding: float = 1.00
    w_solubility: float = 0.30
    w_toxicity_penalty: float = 0.50
    w_cyp3a4_penalty: float = 0.20


@dataclass(frozen=True)
class FunnelPolicy:
    top_n: int = 5
    # v7 (pass 2): binding_norm primary + a light P(cox2) tiebreak. Adopted on
    # secondary metrics only — recall@5 on cox2_v1 is UNCHANGED at 2/5 vs the
    # original v1_multiobjective. See funnel/CHANGELOG.md "Sweep results".
    ranker: str = "binding_weak_cox2"
    filter_mode: str = "druglike_and_tox"
    hard: HardFilters = field(default_factory=HardFilters)
    weights: RankWeights = field(default_factory=RankWeights)

    # binding_score model (RandomForestRegressor). Despite the "kcal/mol" label
    # on the endpoint it emits a POSITIVE pAffinity-style score (observed
    # ~4.4-7.1 on cox2_v1; the simulated fallback in routers/binding_score.py
    # uses uniform(5.0, 9.5)) where HIGHER = stronger binder. So higher is
    # better. (Model's own scale, not Vina's.) See funnel/CHANGELOG.md.
    binding_lower_is_better: bool = False

    solubility_logs_ok: float = -5.0
    solubility_decay: float = 1.5

    # blend / tiebreak coefficients (used only by the rankers that name them)
    blend_binding: float = 0.70
    blend_descriptor: float = 0.30
    weak_cox2_coeff: float = 0.15

    # ------------------------------------------------------------------
    # Hard filters
    # ------------------------------------------------------------------
    def _druglike_ok(self, desc: dict[str, float]) -> tuple[bool, str]:
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

    def descriptors_pass(self, desc: dict[str, float]) -> tuple[bool, str]:
        if self.filter_mode in ("tox_only", "none"):
            return True, ""
        return self._druglike_ok(desc)

    def tox_pass(self, preds: dict[str, float]) -> tuple[bool, str]:
        if self.filter_mode == "none":
            return True, ""
        h = self.hard
        if preds["toxicity"] > h.p_toxicity_max:
            return False, f"P(toxic) {preds['toxicity']:.2f} > {h.p_toxicity_max}"
        if preds["hepg2"] > h.p_hepg2_max:
            return False, f"P(hepG2-toxic) {preds['hepg2']:.2f} > {h.p_hepg2_max}"
        return True, ""

    # ------------------------------------------------------------------
    # Sub-scores
    # ------------------------------------------------------------------
    def _solubility_desirability(self, logs: float) -> float:
        if logs >= self.solubility_logs_ok:
            return 1.0
        return math.exp((logs - self.solubility_logs_ok) / self.solubility_decay)

    @staticmethod
    def _gauss(x: float, mu: float, sigma: float) -> float:
        return math.exp(-0.5 * ((x - mu) / sigma) ** 2)

    def descriptor_desirability(self, desc: dict[str, float]) -> float:
        """
        0..1 "looks like a small-molecule enzyme inhibitor" score from cheap
        physicochemistry only — no ML. Peaks at MW~370, LogP~3, low TPSA, few
        rotatable bonds, 2-3 aromatic rings. Used by descriptor_heuristic /
        binding_desc_blend.
        """
        mw = self._gauss(desc["MolWt"], 370.0, 90.0)
        logp = self._gauss(desc["MolLogP"], 3.0, 1.8)
        tpsa = 1.0 if desc["TPSA"] <= 90 else math.exp((90 - desc["TPSA"]) / 50.0)
        rotb = 1.0 if desc["NumRotatableBonds"] <= 5 else math.exp((5 - desc["NumRotatableBonds"]) / 4.0)
        arom = self._gauss(desc["NumAromaticRings"], 2.5, 1.0)
        return (mw * logp * tpsa * rotb * arom) ** 0.2  # geometric mean of 5 terms

    # ------------------------------------------------------------------
    # The ranking function (dispatches on self.ranker). Higher = better.
    # `feat` = {"predictions": {...}, "descriptors": {...}, "heavy_atoms": int}
    # `binding_norm` = 0..1, direction-corrected (1 = strongest predicted binder)
    # ------------------------------------------------------------------
    def rank_score(self, feat: dict[str, Any], binding_norm: float) -> float:
        preds = feat["predictions"]
        desc = feat["descriptors"]
        r = self.ranker

        if r == "binding_only":
            return binding_norm

        if r == "descriptor_heuristic":
            return self.descriptor_desirability(desc)

        if r == "binding_desc_blend":
            return (self.blend_binding * binding_norm
                    + self.blend_descriptor * self.descriptor_desirability(desc))

        if r == "ligand_efficiency":
            ha = max(1, int(feat.get("heavy_atoms", 1)))
            return preds["binding_score"] / ha

        if r == "binding_weak_cox2":
            return binding_norm + self.weak_cox2_coeff * preds["cox2"]

        # default: v1_multiobjective
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
