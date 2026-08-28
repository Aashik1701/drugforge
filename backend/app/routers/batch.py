"""
High-Throughput Batch Prediction Router.

Endpoint: POST /predict/batch
Accepts a list of SMILES and runs every loaded ML model on each molecule.
Returns a flat array of per-molecule result dicts.
"""

import time
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from utils.rdkit_helper import extract_features, get_molecular_weight, validate_smiles
from utils.model_loader import ModelLoader, MODEL_REGISTRY
from compute.router import ComputeRejected

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Lazy reference to global model_loader ──────────────────────
_loader: Optional[ModelLoader] = None


def _get_loader() -> ModelLoader:
    """Import the singleton model loader from main."""
    global _loader
    if _loader is None:
        from main import model_loader
        _loader = model_loader
    return _loader


def _get_tool_registry():
    from main import tool_registry
    return tool_registry


def _get_compute_router():
    from main import compute_router
    return compute_router


# ── Request / Response Schemas ─────────────────────────────────

class BatchRequest(BaseModel):
    """Request body for batch prediction."""

    smiles_list: List[str] = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="List of SMILES strings to process (max 1 000)",
    )
    models: Optional[List[str]] = Field(
        default=None,
        description="Model keys to run. Omit or pass null to run all loaded models.",
    )


class MoleculeResult(BaseModel):
    """Prediction results for a single molecule."""
    smiles: str
    molecular_weight: Optional[float] = None
    predictions: Dict[str, Any] = {}
    status: str = "success"
    error: Optional[str] = None


class BatchResponse(BaseModel):
    """Full batch response."""
    total: int
    succeeded: int
    failed: int
    results: List[MoleculeResult]
    execution_time_ms: float


# ── Endpoint ───────────────────────────────────────────────────

async def _execute_batch(request: BatchRequest) -> BatchResponse:
    """
    The actual batch-prediction logic — registered in ToolRegistry as
    'predict_batch' and only ever invoked via ComputeRouter.execute(), which
    performs the resource check *before* this runs. This function does not
    check resource limits itself — that would duplicate the check ComputeRouter
    already made (see routers/dock.py's compute-fabric.md for why there must
    be exactly one compute decision path).

    For each SMILES string:
      1. Validate with RDKit and extract Morgan fingerprint.
      2. Run every requested (or all loaded) model.
      3. Collect prediction + confidence.
    """
    t0 = time.perf_counter()
    loader = _get_loader()
    loaded_models = loader.list_loaded()

    if not loaded_models:
        raise HTTPException(status_code=503, detail="No ML models are loaded")

    # Determine which models to run.
    # Use MODEL_REGISTRY (not loaded_models) so that models which failed
    # to load still appear in the response with an error instead of
    # being silently dropped.
    if request.models:
        target_models = [m for m in request.models if m in MODEL_REGISTRY]
        if not target_models:
            raise HTTPException(
                status_code=400,
                detail=f"None of the requested models exist. Available: {list(MODEL_REGISTRY.keys())}",
            )
    else:
        target_models = list(MODEL_REGISTRY.keys())

    results: List[MoleculeResult] = []
    succeeded = 0
    failed = 0

    for smiles in request.smiles_list:
        smiles = smiles.strip()
        if not smiles:
            results.append(MoleculeResult(
                smiles=smiles, status="failed", error="Empty SMILES string",
            ))
            failed += 1
            continue

        # Validate molecule once
        try:
            validate_smiles(smiles)
            features = extract_features(smiles)
            mol_weight = get_molecular_weight(smiles)
        except ValueError as e:
            results.append(MoleculeResult(
                smiles=smiles, status="failed", error=str(e),
            ))
            failed += 1
            continue

        # Run each model
        predictions: Dict[str, Any] = {}
        mol_failed = False

        for model_key in target_models:
            model = loader.get(model_key)
            if model is None:
                predictions[model_key] = {"value": None, "error": "Model not loaded"}
                continue

            try:
                pred_val = float(model.predict(features)[0])

                confidence = None
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(features)[0]
                    confidence = round(float(max(proba)), 4)

                unit = MODEL_REGISTRY.get(model_key, {}).get("unit", "")

                predictions[model_key] = {
                    "value": round(pred_val, 4),
                    "confidence": confidence,
                    "unit": unit,
                }
            except Exception as e:
                predictions[model_key] = {"value": None, "error": str(e)}
                logger.warning(f"Model {model_key} failed for {smiles}: {e}")

        results.append(MoleculeResult(
            smiles=smiles,
            molecular_weight=mol_weight,
            predictions=predictions,
            status="success",
        ))
        succeeded += 1

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    logger.info(
        f"✅ Batch complete: {succeeded}/{len(request.smiles_list)} succeeded "
        f"in {elapsed_ms}ms ({len(target_models)} models)"
    )

    return BatchResponse(
        total=len(request.smiles_list),
        succeeded=succeeded,
        failed=failed,
        results=results,
        execution_time_ms=elapsed_ms,
    )


# ── Endpoint (thin wrapper: ToolRegistry -> ComputeRouter -> ResourceManager) ──

@router.post("/batch", response_model=BatchResponse)
async def run_batch(request: BatchRequest) -> BatchResponse:
    """
    HTTP entry point. Routes through the same compute decision path as every
    other tool — ToolRegistry.get() -> ComputeRouter.execute() -> ResourceManager
    — rather than checking limits itself.
    """
    tool_registry = _get_tool_registry()
    compute_router = _get_compute_router()
    tool = tool_registry.get("predict_batch")

    try:
        return await compute_router.execute(tool, request, batch_size=len(request.smiles_list))
    except ComputeRejected as exc:
        raise HTTPException(status_code=413, detail=exc.reason)
