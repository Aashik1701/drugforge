"""
Pydantic schemas for molecule input and prediction responses.
"""

from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MoleculeInput(BaseModel):
    """
    Request body for all prediction endpoints.

    Attributes:
        smiles: SMILES string representation of a molecule.
    """

    smiles: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="SMILES string of the molecule (e.g. 'CCO' for ethanol)",
        json_schema_extra={"examples": ["CCO", "c1ccccc1", "CC(=O)Oc1ccccc1C(=O)O"]},
    )

    @field_validator("smiles")
    @classmethod
    def smiles_not_empty(cls, v: str) -> str:
        """Strip whitespace and reject empty strings."""
        v = v.strip()
        if not v:
            raise ValueError("SMILES string must not be empty")
        return v


class PredictionResponse(BaseModel):
    """
    Unified response for all prediction endpoints.

    Attributes:
        smiles: The input SMILES string (echoed back).
        prediction: Raw model output (float).
        confidence: Model confidence / probability (0-1 for classifiers).
        unit: Unit of measurement for the prediction. NOT an energy unless it
            literally says so — e.g. `binding_score` returns a pKd-like score,
            not kcal/mol (that is only the real docking endpoint,
            `/api/dock/*`, whose field is `affinity_kcal_mol`).
        direction: How to read `prediction` — e.g. "higher = stronger binding",
            "higher = more likely toxic". None when the raw value speaks for
            itself (probabilities, physical quantities).
        interpretation: Optional one-line human summary of this result.
        model_name: Name of the model used.
        model_version: Version tag of the model.
        molecular_weight: Calculated molecular weight (g/mol).
        execution_time_ms: Wall-clock inference time in milliseconds.
    """

    model_config = ConfigDict(protected_namespaces=())

    smiles: str
    prediction: float
    confidence: Optional[float] = None
    unit: str
    direction: Optional[str] = None
    interpretation: Optional[str] = None
    model_name: str
    model_version: str = "1.0"
    molecular_weight: Optional[float] = None
    execution_time_ms: Optional[float] = None
