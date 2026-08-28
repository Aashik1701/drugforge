"""
Pydantic schemas for asynchronous molecular docking API.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


DockTaskStatus = Literal["queued", "processing", "completed", "failed", "cancelled"]


class DockStartRequest(BaseModel):
    """Request payload for starting a docking job."""

    smiles: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="SMILES string for the ligand molecule",
        json_schema_extra={"examples": ["CC(=O)Oc1ccccc1C(=O)O"]},
    )
    target: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Target identifier (e.g. 'cox2', 'ace2')",
        json_schema_extra={"examples": ["cox2"]},
    )
    exhaustiveness: Optional[int] = Field(
        None,
        ge=1,
        le=64,
        description="Vina exhaustiveness parameter (1-64). Higher = more thorough but slower.",
    )

    @field_validator("smiles")
    @classmethod
    def smiles_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("SMILES string must not be empty")
        return value

    @field_validator("target")
    @classmethod
    def target_normalized(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("Target must not be empty")
        return value


class DockStartResponse(BaseModel):
    """Immediate response after queuing a docking job."""

    task_id: str
    status: DockTaskStatus
    target: str
    smiles: str
    message: str


class DockStatusResponse(BaseModel):
    """Polling response for a docking job."""

    task_id: str
    status: DockTaskStatus
    target: str
    smiles: str
    affinity_kcal_mol: Optional[float] = None
    docked_ligand_pdbqt: Optional[str] = None
    receptor_pdbqt: Optional[str] = None
    mode: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None
