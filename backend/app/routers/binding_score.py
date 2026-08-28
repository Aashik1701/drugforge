"""
Drug-Target Binding Score prediction router.

Endpoint: POST /predict/binding-score
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
    return model_loader.get("binding_score")


@router.post("/binding-score", response_model=PredictionResponse)
async def predict_binding_score(mol: MoleculeInput) -> PredictionResponse:
    """
    Predict a drug-target binding score.

    NOTE ON UNITS (this was previously mislabelled "kcal/mol"): the model emits
    a **pKd-like affinity score** — a positive number, roughly 4-9 in practice,
    where **higher means stronger predicted binding**. It is NOT a binding free
    energy in kcal/mol and is NOT comparable to the AutoDock Vina affinities
    from `/api/dock/*` (those are real kcal/mol, more-negative = stronger). The
    response carries `unit` and `direction` so a consumer never has to guess.

    Args:
        mol: Request body with a SMILES string.

    Returns:
        PredictionResponse; `prediction` is the pKd-like score,
        `direction` = "higher = stronger binding".

    Raises:
        HTTPException 400: Invalid SMILES.
        HTTPException 503: Model not loaded.
    """
    BINDING_UNIT = "pKd-like score"
    BINDING_DIRECTION = "higher = stronger binding"
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
            prediction = float(model.predict(features)[0])
            confidence = None
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(features)[0]
                confidence = round(float(max(proba)), 4)
        except Exception as e:
            logger.error(f"Binding score inference failed: {e}")
            raise HTTPException(status_code=500, detail="Prediction failed")
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        meta = {"unit": BINDING_UNIT, "direction": BINDING_DIRECTION, "molecular_weight": mol_weight, "execution_time_ms": elapsed_ms}
    else:
        # ── Simulated fallback (DeepPurpose not installed) ──────────
        # TODO: Integrate DeepPurpose for real binding predictions
        logger.warning("Binding score model unavailable — returning simulated result")
        seed = int(hashlib.md5(mol.smiles.encode()).hexdigest(), 16) % (10**8)
        rng = random.Random(seed)
        prediction = round(rng.uniform(5.0, 9.5), 4)
        confidence = 0.0  # 0.0 signals "simulated"
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        meta = {
            "unit": BINDING_UNIT,
            "direction": BINDING_DIRECTION,
            "molecular_weight": mol_weight,
            "execution_time_ms": elapsed_ms,
            "simulated": True,
            "note": "DeepPurpose model not available — result is a simulated pKd-like score, not kcal/mol",
        }

    result = PredictionResponse(
        smiles=mol.smiles,
        prediction=round(prediction, 4),
        confidence=confidence,
        unit=BINDING_UNIT,
        direction=BINDING_DIRECTION,
        interpretation=(
            "Simulated pKd-like score (model unavailable)"
            if model is None else
            f"pKd-like score {round(prediction, 2)} — higher = stronger predicted binding; not kcal/mol"
        ),
        model_name="binding_score",
        molecular_weight=mol_weight,
        execution_time_ms=elapsed_ms,
    )

    await save_prediction(PredictionCreate(
        smiles=mol.smiles,
        model_type="binding_score",
        result=round(prediction, 4),
        confidence=confidence,
        meta=meta,
    ))

    return result
