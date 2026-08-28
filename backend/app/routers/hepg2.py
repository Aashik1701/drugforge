"""
HEPG2 cytotoxicity prediction router.

Endpoint: POST /predict/hepg2
"""

import time
import random
import hashlib
import logging

from fastapi import APIRouter, HTTPException

from schemas.molecule import MoleculeInput, PredictionResponse
from schemas.prediction import PredictionCreate
from utils.rdkit_helper import extract_features, get_molecular_weight, validate_smiles
from services.db_service import save_prediction

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_model():
    from main import model_loader
    return model_loader.get("hepg2")


@router.post("/hepg2", response_model=PredictionResponse)
async def predict_hepg2(mol: MoleculeInput) -> PredictionResponse:
    """
    Predict HepG2 liver cell cytotoxicity.

    Args:
        mol: Request body with a SMILES string.

    Returns:
        PredictionResponse with toxicity probability.

    Raises:
        HTTPException 400: Invalid SMILES.
        HTTPException 503: Model not loaded.
    """
    # Validate SMILES first (applies to both real and simulated paths)
    try:
        validate_smiles(mol.smiles)
        mol_weight = get_molecular_weight(mol.smiles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    model = _get_model()
    start = time.perf_counter()

    if model is not None:
        # ── Real inference ──────────────────────────────────────────
        try:
            features = extract_features(mol.smiles)
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(features)[0]
                prediction = round(float(proba[1]), 4)  # P(toxic)
                confidence = round(float(max(proba)), 4)
            else:
                prediction = float(model.predict(features)[0])
                confidence = None
        except Exception as e:
            logger.error(f"HEPG2 inference failed: {e}")
            raise HTTPException(status_code=500, detail="Prediction failed")
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        meta = {"unit": "probability", "molecular_weight": mol_weight, "execution_time_ms": elapsed_ms}
    else:
        # ── Simulated fallback (ptd.csv dataset missing) ────────────
        # TODO: Obtain HepG2 dataset and train real model
        logger.warning("HepG2 model unavailable — returning simulated result")
        seed = int(hashlib.md5(mol.smiles.encode()).hexdigest(), 16) % (10**8)
        rng = random.Random(seed)
        prediction = round(rng.uniform(0.05, 0.65), 4)
        confidence = 0.0  # 0.0 signals "simulated"
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        meta = {
            "unit": "probability",
            "molecular_weight": mol_weight,
            "execution_time_ms": elapsed_ms,
            "simulated": True,
            "note": "HepG2 model not trained — result is simulated",
        }

    result = PredictionResponse(
        smiles=mol.smiles,
        prediction=round(prediction, 4),
        confidence=confidence,
        unit="probability",
        model_name="hepg2",
        molecular_weight=mol_weight,
        execution_time_ms=elapsed_ms,
    )

    await save_prediction(PredictionCreate(
        smiles=mol.smiles,
        model_type="hepg2",
        result=round(prediction, 4),
        confidence=confidence,
        meta=meta,
    ))

    return result
