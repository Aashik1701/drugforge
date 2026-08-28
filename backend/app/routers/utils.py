"""
Utility endpoints for molecular operations.

Endpoint: POST /utils/generate-3d
Returns 3D MOL block, Gasteiger partial charges, and pharmacophore features.
"""

import os
import math
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from rdkit import Chem, RDConfig
from rdkit.Chem import AllChem, ChemicalFeatures

logger = logging.getLogger(__name__)
router = APIRouter()

# Load pharmacophore feature factory once (singleton)
_fdef_path = os.path.join(RDConfig.RDDataDir, 'BaseFeatures.fdef')
_feature_factory = ChemicalFeatures.BuildFeatureFactory(_fdef_path)


class MoleculeRequest(BaseModel):
    """Request body for 3D coordinate generation."""
    smiles: str


@router.post("/generate-3d")
async def generate_3d_coordinates(data: MoleculeRequest) -> dict:
    """
    Convert a SMILES string into a 3D MOL block with optimised geometry,
    Gasteiger partial charges, and pharmacophore feature locations.

    Args:
        data: Request body containing a SMILES string.

    Returns:
        Dictionary with:
        - ``mol_block``: V2000 MOL block text
        - ``charges``: list of Gasteiger partial charges per atom
        - ``features``: list of pharmacophore features with 3D positions

    Raises:
        HTTPException 400: If SMILES is invalid or embedding fails.
    """
    smiles = data.smiles.strip()
    if not smiles:
        raise HTTPException(status_code=400, detail="SMILES string is required")

    try:
        # 1. Parse SMILES
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES: {smiles}")

        # 2. Add hydrogens (critical for realistic 3D geometry)
        mol = Chem.AddHs(mol)

        # 3. Generate 3D coordinates via ETKDGv3
        params = AllChem.ETKDGv3()
        params.randomSeed = 42  # Reproducible results
        res = AllChem.EmbedMolecule(mol, params)

        if res == -1:
            # Fallback: random coordinates for difficult molecules
            logger.warning(f"ETKDGv3 failed for {smiles}, falling back to random coords")
            res = AllChem.EmbedMolecule(mol, useRandomCoords=True)
            if res == -1:
                raise ValueError("Could not generate 3D coordinates for this molecule")

        # 4. Optimise geometry with MMFF force field
        try:
            AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
        except Exception:
            # Skip optimisation if force field fails — raw embedding is okay
            logger.warning(f"MMFF optimisation skipped for {smiles}")

        # 5. Compute Gasteiger partial charges
        AllChem.ComputeGasteigerCharges(mol)
        charges: list[float] = []
        for atom in mol.GetAtoms():
            try:
                q = float(atom.GetProp('_GasteigerCharge'))
                # Replace NaN/Inf with 0.0
                if math.isnan(q) or math.isinf(q):
                    q = 0.0
                charges.append(round(q, 4))
            except Exception:
                charges.append(0.0)

        # 6. Detect pharmacophore features
        features_data: list[dict] = []
        try:
            feats = _feature_factory.GetFeaturesForMol(mol)
            for f in feats:
                family = f.GetFamily()
                # Only include the three key types
                if family not in ('Donor', 'Acceptor', 'Aromatic'):
                    continue
                pos = f.GetPos()
                features_data.append({
                    "family": family,
                    "type": f.GetType(),
                    "x": round(pos.x, 3),
                    "y": round(pos.y, 3),
                    "z": round(pos.z, 3),
                })
        except Exception as e:
            logger.warning(f"Pharmacophore detection skipped: {e}")

        # 7. Return everything
        mol_block = Chem.MolToMolBlock(mol)
        logger.info(f"✅ Generated 3D + charges + features for: {smiles}")
        return {
            "mol_block": mol_block,
            "charges": charges,
            "features": features_data,
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"3D generation failed: {e}")
        raise HTTPException(status_code=400, detail=f"3D generation failed: {str(e)}")
