"""
Half-life prediction router.

Endpoint: POST /predict/half-life
"""

import time
import logging

from fastapi import APIRouter, HTTPException

from schemas.molecule import MoleculeInput, PredictionResponse
from schemas.prediction import PredictionCreate
from utils.rdkit_helper import extract_features, get_molecular_weight
from services.db_service import save_prediction

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_model():
    from main import model_loader
    return model_loader.get("half_life")


@router.post("/half-life", response_model=PredictionResponse)
async def predict_half_life(mol: MoleculeInput) -> PredictionResponse:
    """
    Predict plasma half-life in hours.

    Args:
        mol: Request body with a SMILES string.

    Returns:
        PredictionResponse with predicted half-life.

    Raises:
        HTTPException 400: Invalid SMILES.
        HTTPException 503: Model not loaded.
    """
    model = _get_model()
    if model is None:
        raise HTTPException(status_code=503, detail="Half-life model is not available")

    try:
        features = extract_features(mol.smiles)
        mol_weight = get_molecular_weight(mol.smiles)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    start = time.perf_counter()
    try:
        prediction = float(model.predict(features)[0])
        confidence = None
        if hasattr(model, "predict_proba"):
            proba = model.predict_proba(features)[0]
            confidence = round(float(max(proba)), 4)
    except Exception as e:
        logger.error(f"Half-life inference failed: {e}")
        raise HTTPException(status_code=500, detail="Prediction failed")
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    result = PredictionResponse(
        smiles=mol.smiles,
        prediction=round(prediction, 4),
        confidence=confidence,
        unit="hours",
        model_name="half_life",
        molecular_weight=mol_weight,
        execution_time_ms=elapsed_ms,
    )

    await save_prediction(PredictionCreate(
        smiles=mol.smiles,
        model_type="half_life",
        result=round(prediction, 4),
        confidence=confidence,
        meta={"unit": "hours", "molecular_weight": mol_weight, "execution_time_ms": elapsed_ms},
    ))

    return result
