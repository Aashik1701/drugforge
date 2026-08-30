"""
Pydantic schemas for the funnel service (POST /api/funnel/*).

The funnel's scientific output is the RunRecord v1.0.0 defined in
funnel/schema.py -- unchanged. These schemas only cover the HTTP request/response
envelope.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class FunnelStartRequest(BaseModel):
    """Start a funnel run. Provide exactly one of candidate_set_id or smiles."""

    candidate_set_id: Optional[str] = Field(
        None, description="A committed candidate set, e.g. 'cox2_v1' (see GET /api/funnel/sets)."
    )
    smiles: Optional[list[str]] = Field(
        None, description="An ad-hoc candidate list. RDKit-validated and size-capped before anything runs."
    )
    target: str = Field(..., description="Docking target: 'cox2' or 'ace2'.")
    budget_n: int = Field(
        10, ge=1,
        description="How many prescreen survivors to dock (x4 seeds). Bounded server-side; clamped to the set size.",
    )
    policy_id: str = Field(
        "v7_binding_weak_cox2",
        description="Frozen policy id. Only 'v7_binding_weak_cox2' is accepted.",
    )

    @field_validator("target")
    @classmethod
    def _norm_target(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("cox2", "ace2"):
            raise ValueError("target must be 'cox2' or 'ace2'")
        return v


class ParseFailure(BaseModel):
    index: int
    smiles: str
    error: str


class FunnelStartResponse(BaseModel):
    run_id: str
    status: str
    candidate_set_id: str
    target: str
    budget_n: int
    policy_id: str
    candidates_in: int
    message: str


class FunnelStatusResponse(BaseModel):
    run_id: str
    status: str                       # queued | running | completed | failed | cancelled
    stage: str                        # queued | screening | prescreen | docking | ranking | done | cancelled | failed
    candidate_set_id: str
    target: str
    budget_n: int
    policy_id: str
    candidates_in: int = 0
    stage_survivors: list[dict[str, Any]] = []
    prescreen_selected: list[str] = []
    docks_submitted: int = 0
    docks_total: int = 0
    docks_completed: int = 0
    docks_failed: int = 0
    current_dock_job_id: Optional[str] = None
    partial_results: list[dict[str, Any]] = []
    elapsed_s: Optional[float] = None
    error: Optional[str] = None


class CandidateSetInfo(BaseModel):
    set_id: str
    size: int
    n_reference: int
    content_sha256: str
    csv: str


class FrontierRow(BaseModel):
    N: int
    docked: int
    jobs: int
    recall5_literal: int
    recall5_tiecredit: int
    recall10_literal: int
    recall10_tiecredit: int
    est_dock_wall_s: float
    speedup_vs_full: Optional[float] = None
