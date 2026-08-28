"""
Compute mode control — lets the frontend's ComputeControl UI actually change
server-side enforcement, not just display it. This is a small, new addition
(not in the original API contract) — purely additive.

Backend stays authoritative: switching modes only ever selects one of three
fixed, safe presets (ComputePolicy.preset) — never an arbitrary client-supplied
limit. "Performance" mode still enforces hard ceilings (spec §10/§38).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from compute.policy import ComputeMode, ComputePolicy

logger = logging.getLogger(__name__)
router = APIRouter()


class ComputeModeRequest(BaseModel):
    mode: str = Field(..., description="One of: battery-saver, balanced, performance")


class ComputePolicyResponse(BaseModel):
    mode: str
    allow_docking: bool
    allow_large_batches: bool
    allow_parallel_jobs: bool
    max_local_jobs: int
    max_docking_jobs: int
    max_runtime: int


def _policy_to_response(policy: ComputePolicy) -> ComputePolicyResponse:
    return ComputePolicyResponse(
        mode=policy.mode.value,
        allow_docking=policy.allow_docking,
        allow_large_batches=policy.allow_large_batches,
        allow_parallel_jobs=policy.allow_parallel_jobs,
        max_local_jobs=policy.max_local_jobs,
        max_docking_jobs=policy.max_docking_jobs,
        max_runtime=policy.max_runtime,
    )


@router.get("/policy", response_model=ComputePolicyResponse)
async def get_compute_policy() -> ComputePolicyResponse:
    from main import compute_policy
    return _policy_to_response(compute_policy)


@router.post("/mode", response_model=ComputePolicyResponse)
async def set_compute_mode(payload: ComputeModeRequest) -> ComputePolicyResponse:
    """Switch the active compute mode preset. Takes effect immediately for new requests."""
    import main  # module reference so we can rebind main.compute_policy itself

    try:
        mode = ComputeMode(payload.mode)
    except ValueError:
        valid = ", ".join(m.value for m in ComputeMode)
        raise HTTPException(status_code=400, detail=f"Unknown mode '{payload.mode}'. Valid: {valid}")

    new_policy = ComputePolicy.preset(mode)
    main.compute_policy = new_policy
    main.resource_manager.policy = new_policy

    logger.info("compute_mode_changed mode=%s docking=%s", mode.value, new_policy.allow_docking)
    return _policy_to_response(new_policy)
