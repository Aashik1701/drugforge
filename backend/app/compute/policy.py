"""
Compute classification and policy.

ComputeClass labels what a Tool costs to run — it's tool metadata, read by
ComputeRouter/ResourceManager to decide execution path. ComputePolicy is the
per-request/per-session set of limits that decision is checked against.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict


class ComputeClass(str, Enum):
    """How expensive a tool is to run — set once per Tool at registration."""

    LOCAL = "LOCAL"                     # SMILES validation, descriptors, RandomForest inference
    LOCAL_SMALL = "LOCAL_SMALL"         # 3D generation, small batches
    HEAVY_LOCAL = "HEAVY_LOCAL"         # AutoDock Vina — runs locally today, via a job/worker
    REMOTE_CAPABLE = "REMOTE_CAPABLE"   # could run on a future RemoteWorker; not required to


class ComputeMode(str, Enum):
    BATTERY_SAVER = "battery-saver"
    BALANCED = "balanced"
    PERFORMANCE = "performance"


@dataclass(frozen=True)
class ComputePolicy:
    """
    Backend-authoritative limits (§38 of the spec: frontend settings are
    preferences, this is enforcement). One instance per running process,
    built from env vars via from_env(); presets below are the three modes.
    """

    mode: ComputeMode = ComputeMode.BATTERY_SAVER
    allow_docking: bool = False
    allow_large_batches: bool = False
    allow_parallel_jobs: bool = False
    max_local_jobs: int = 1
    max_docking_jobs: int = 1
    max_agent_steps: int = 30
    max_agent_tool_calls: int = 50
    max_runtime: int = 600  # seconds

    @staticmethod
    def preset(mode: ComputeMode) -> "ComputePolicy":
        if mode == ComputeMode.BATTERY_SAVER:
            return ComputePolicy(
                mode=mode, allow_docking=False, allow_large_batches=False,
                allow_parallel_jobs=False, max_local_jobs=1, max_docking_jobs=0,
            )
        if mode == ComputeMode.BALANCED:
            return ComputePolicy(
                mode=mode, allow_docking=True, allow_large_batches=False,
                allow_parallel_jobs=False, max_local_jobs=2, max_docking_jobs=1,
            )
        if mode == ComputeMode.PERFORMANCE:
            # "Performance" still enforces hard ceilings — never unlimited (§10).
            return ComputePolicy(
                mode=mode, allow_docking=True, allow_large_batches=True,
                allow_parallel_jobs=True, max_local_jobs=4, max_docking_jobs=2,
            )
        raise ValueError(f"Unknown compute mode: {mode}")

    @staticmethod
    def from_env() -> "ComputePolicy":
        """
        Build the active policy from COMPUTE_MODE plus any explicit
        MAX_*/ALLOW_* overrides in the environment. Env overrides win over
        the mode preset — lets a deployment pin exact numbers without
        inventing a fourth mode.
        """
        mode_name = os.getenv("COMPUTE_MODE", ComputeMode.BATTERY_SAVER.value)
        try:
            mode = ComputeMode(mode_name)
        except ValueError:
            mode = ComputeMode.BATTERY_SAVER
        base = ComputePolicy.preset(mode)

        def _int(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                return default

        def _bool(key: str, default: bool) -> bool:
            val = os.getenv(key)
            if val is None:
                return default
            return val.strip().lower() in ("1", "true", "yes", "on")

        return ComputePolicy(
            mode=base.mode,
            allow_docking=_bool("DOCKING_ENABLED", base.allow_docking),
            allow_large_batches=base.allow_large_batches,
            allow_parallel_jobs=base.allow_parallel_jobs,
            max_local_jobs=_int("MAX_LOCAL_CONCURRENT_TOOLS", base.max_local_jobs),
            max_docking_jobs=_int("MAX_DOCKING_CONCURRENT", base.max_docking_jobs),
            max_agent_steps=_int("MAX_AGENT_STEPS", base.max_agent_steps),
            max_agent_tool_calls=_int("MAX_AGENT_TOOL_CALLS", base.max_agent_tool_calls),
            max_runtime=_int("DOCKING_TIMEOUT_SECONDS", base.max_runtime),
        )


# Process-wide active policy — read once at import time, matches the pattern
# already used by MODEL_REGISTRY (module-level constant, not a DI container).
ACTIVE_POLICY: ComputePolicy = ComputePolicy.from_env()
