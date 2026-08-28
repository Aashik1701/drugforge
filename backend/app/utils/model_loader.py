"""
ML Model Loader.

Loads serialised scikit-learn models from disk once on startup and
keeps them cached in memory for fast inference.
"""

import os
import logging
import pickle
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Canonical mapping: model key → expected file name.
#
# `version` + `algorithm` make each entry addressable as e.g. "solubility:v1",
# so a future model registry can host multiple algorithms/versions per task
# (e.g. an XGBoost or ensemble "solubility:v2") without changing callers —
# they remain RandomForest baselines for now, no retraining involved.
MODEL_REGISTRY: Dict[str, Dict[str, str]] = {
    "solubility": {
        "file": "solubility_model.pkl",
        "description": "Aqueous solubility prediction (logS)",
        "unit": "log(mol/L)",
        "version": "v1",
        "algorithm": "RandomForestRegressor",
    },
    "binding_score": {
        "file": "binding_model.pkl",
        "description": "Drug-target binding affinity (pKd-like score)",
        # NOT kcal/mol — the model emits a positive pKd-like score (~4-9),
        # higher = stronger. kcal/mol is only the real Vina docking endpoint
        # (/api/dock/*, field affinity_kcal_mol). See routers/binding_score.py.
        "unit": "pKd-like score",
        "direction": "higher = stronger binding",
        "version": "v1",
        "algorithm": "RandomForestRegressor",
    },
    "bbbp": {
        "file": "bbbp_model.pkl",
        "description": "Blood-brain barrier permeability",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "cyp3a4": {
        "file": "cyp3a4_model.pkl",
        "description": "CYP3A4 enzyme inhibition",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "cox2": {
        "file": "cox2_model.pkl",
        "description": "COX2 enzyme inhibition",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "hepg2": {
        "file": "hepg2_model.pkl",
        "description": "HepG2 cell toxicity",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "ace2": {
        "file": "ace2_model.pkl",
        "description": "ACE2 receptor binding",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "toxicity": {
        "file": "toxicity_model.pkl",
        "description": "General toxicity prediction",
        "unit": "probability",
        "version": "v1",
        "algorithm": "RandomForestClassifier",
    },
    "half_life": {
        "file": "half_life_model.pkl",
        "description": "Plasma half-life prediction",
        "unit": "hours",
        "version": "v1",
        "algorithm": "RandomForestRegressor",
    },
}


def versioned_name(key: str) -> str:
    """e.g. "solubility" -> "solubility:v1" — a stable id for registries/logs."""
    meta = MODEL_REGISTRY.get(key, {})
    return f"{key}:{meta.get('version', 'v1')}"


class ModelLoader:
    """
    Singleton-style model cache.

    Usage::

        loader = ModelLoader()
        loader.load_all("./models")
        model = loader.get("solubility")  # returns sklearn model or None
    """

    def __init__(self) -> None:
        self._models: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load_all(self, models_dir: str) -> int:
        """
        Scan *models_dir* for every file listed in MODEL_REGISTRY and
        load whatever is found.

        Args:
            models_dir: Absolute or relative path to the models folder.

        Returns:
            Number of models successfully loaded.
        """
        loaded = 0
        for key, meta in MODEL_REGISTRY.items():
            path = os.path.join(models_dir, meta["file"])
            if os.path.isfile(path):
                try:
                    with open(path, "rb") as fh:
                        self._models[key] = pickle.load(fh)
                    logger.info(f"  ✅ {key} loaded from {meta['file']}")
                    loaded += 1
                except Exception as exc:
                    logger.error(f"  ❌ {key} failed to load: {exc}")
            else:
                logger.warning(f"  ⚠️  {key} model not found ({meta['file']})")
        return loaded

    # ------------------------------------------------------------------
    # Access
    # ------------------------------------------------------------------

    def get(self, name: str) -> Optional[Any]:
        """
        Retrieve a loaded model by name.

        Args:
            name: Model key (e.g. ``"solubility"``).

        Returns:
            The sklearn model object, or ``None`` if not loaded.
        """
        return self._models.get(name)

    def is_loaded(self, name: str) -> bool:
        """Check whether a model is available."""
        return name in self._models

    def list_loaded(self) -> List[str]:
        """Return the keys of all loaded models."""
        return list(self._models.keys())

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_metadata(self) -> Dict[str, Dict[str, str]]:
        """
        Return metadata for every registered model, including
        whether it is currently loaded.
        """
        out: Dict[str, Dict[str, str]] = {}
        for key, meta in MODEL_REGISTRY.items():
            out[key] = {
                "description": meta["description"],
                "unit": meta["unit"],
                # Explicit for consumers: how to read the raw `prediction`.
                # Classifiers return P(positive class); `binding_score` is a
                # pKd-like score (higher = stronger) — NOT kcal/mol.
                "direction": meta.get(
                    "direction",
                    "P(positive class), 0-1"
                    if meta.get("algorithm", "").endswith("Classifier")
                    else "raw model output",
                ),
                "version": meta.get("version", "v1"),
                "algorithm": meta.get("algorithm", "unknown"),
                "status": "ready" if key in self._models else "not_available",
            }
        return out

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def unload_all(self) -> None:
        """Release all loaded models from memory."""
        self._models.clear()
        logger.info("All models unloaded")
