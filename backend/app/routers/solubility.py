"""
Solubility prediction router.

Endpoint: POST /predict/solubility
"""

import time
import logging

from fastapi import APIRouter, HTTPException

from schemas.molecule import MoleculeInput, PredictionResponse
from schemas.prediction import PredictionCreate
from utils.rdkit_helper import extract_features, get_molecular_weight
from utils.model_loader import ModelLoader
from services.db_service import save_prediction

logger = logging.getLogger(__name__)
router = APIRouter()

# Reference to the global model loader (injected from main.py via app state)
_loader: ModelLoader | None = None


def _get_loader() -> ModelLoader:
    """Lazy import of the global model_loader from main."""
    global _loader
    if _loader is None:
        from main import model_loader
        _loader = model_loader
    return _loader


@router.post("/solubility", response_model=PredictionResponse)
async def predict_solubility(mol: MoleculeInput) -> PredictionResponse:
    """
    Predict aqueous solubility (logS) for a molecule.

    Args:
        mol: Request body with a SMILES string.

    Returns:
        PredictionResponse with logS value.

    Raises:
        HTTPException 400: Invalid SMILES.
        HTTPException 503: Model not loaded.
    """
    loader = _get_loader()
    model = loader.get("solubility")
    if model is None:
        raise HTTPException(status_code=503, detail="Solubility model is not available")

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
        logger.error(f"Solubility inference failed: {e}")
        raise HTTPException(status_code=500, detail="Prediction failed")
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)

    result = PredictionResponse(
        smiles=mol.smiles,
        prediction=round(prediction, 4),
        confidence=confidence,
        unit="log(mol/L)",
        model_name="solubility",
        molecular_weight=mol_weight,
        execution_time_ms=elapsed_ms,
    )

    # Persist to Supabase (non-blocking, errors are logged not raised)
    await save_prediction(PredictionCreate(
        smiles=mol.smiles,
        model_type="solubility",
        result=round(prediction, 4),
        confidence=confidence,
        meta={"unit": "log(mol/L)", "molecular_weight": mol_weight, "execution_time_ms": elapsed_ms},
    ))

    return result
