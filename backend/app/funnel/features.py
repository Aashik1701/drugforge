"""
Precompute the LOCAL features for every candidate ONCE, so the offline policy
sweep can score dozens of FunnelPolicy variants in milliseconds without any
docking (or even any model inference) per variant.

Every value here comes through the compute fabric: tool_registry.get(name) ->
compute_router.execute(). No docking. Cache -> runs/features_<set_id>.json.

Run:  cd backend/app && COMPUTE_MODE=balanced ../venv/bin/python -m funnel.features
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

os.environ.setdefault("COMPUTE_MODE", "balanced")

from funnel.candidate_set import load_candidate_set
from funnel.fabric import call_local, descriptors_fabric, predict_all_fabric
from funnel.schema import RUNS_DIR


async def _one(smiles: str) -> dict:
    desc = await descriptors_fabric(smiles)
    preds = await predict_all_fabric(smiles)
    # heavy-atom count for ligand-efficiency style rankers (RDKit via the
    # parse_smiles tool -> Mol).
    mol = await call_local("parse_smiles", smiles)
    heavy = int(mol.GetNumHeavyAtoms())
    return {"descriptors": {k: round(v, 4) for k, v in desc.items()},
            "predictions": {k: round(v, 5) for k, v in preds.items()},
            "heavy_atoms": heavy}


async def _build(cs) -> dict:
    out = {}
    for i, c in enumerate(cs.candidates, 1):
        out[c.ligand_id] = await _one(c.smiles)
        print(f"  [{i:2}/{len(cs)}] {c.ligand_id}", flush=True)
    return out


def features_path(set_id: str) -> Path:
    return RUNS_DIR / f"features_{set_id}.json"


def load_features(set_id: str) -> dict:
    p = features_path(set_id)
    if not p.exists():
        raise FileNotFoundError(f"{p} missing — run `python -m funnel.features` first")
    return json.loads(p.read_text())


def main() -> int:
    cs = load_candidate_set()
    feats = asyncio.run(_build(cs))
    p = features_path(cs.set_id)
    p.write_text(json.dumps({
        "set_id": cs.set_id,
        "candidate_set_sha256": cs.content_sha256,
        "n": len(cs),
        "features": feats,
    }, indent=2))
    print(f"\nwrote {p}  ({len(feats)} candidates)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
