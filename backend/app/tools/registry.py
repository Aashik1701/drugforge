"""
Tool registry — a name-addressable catalog of the existing scientific
operations (chemistry, prediction, docking), for a future agent orchestrator
to look up and call.

This module wraps existing functions; it does not duplicate any prediction,
chemistry, or docking logic. Each Tool.fn is the same function the FastAPI
routes already call.
"""

from __future__ import annotations

import inspect
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from compute.policy import ComputeClass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    name: str
    category: str
    description: str
    fn: Callable[..., Any]
    compute_class: ComputeClass = ComputeClass.LOCAL
    supports_remote: bool = False
    version: str = "v1"

    @property
    def is_async(self) -> bool:
        return inspect.iscoroutinefunction(self.fn)


class ToolRegistry:
    """In-memory catalog. No execution/orchestration logic lives here."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self, category: Optional[str] = None) -> List[Tool]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    async def invoke(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """
        Call a registered tool by name, logging start/end/errors tagged
        "tool_call" — the audit trail a future agent orchestrator needs.
        Prefer this over calling Tool.fn directly once an actual caller exists.
        """
        tool = self.get(name)
        if tool is None:
            raise KeyError(f"No tool registered as '{name}'")

        t0 = time.perf_counter()
        logger.info("tool_call start name=%s", name)
        try:
            result = await tool.fn(*args, **kwargs) if tool.is_async else tool.fn(*args, **kwargs)
        except Exception:
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            logger.exception("tool_call failed name=%s elapsed_ms=%s", name, elapsed_ms)
            raise
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.info("tool_call done name=%s elapsed_ms=%s", name, elapsed_ms)
        return result


def build_default_registry() -> ToolRegistry:
    """
    Wire the existing routers/utils in as named tools.

    Local imports mirror the pattern already used throughout app/ (routers
    are only meant to be imported once main.py has set up the package path).
    """
    from utils.rdkit_helper import extract_descriptors, validate_smiles
    from routers import ace2, bbbp, binding_score, cox2, cyp3a4, dock, half_life, hepg2, solubility, toxicity
    from routers import utils as utils_router
    from routers import batch as batch_router

    registry = ToolRegistry()

    # --- Chemistry tools -------------------------------------------------
    registry.register(Tool(
        "parse_smiles", "chemistry",
        "Parse and validate a SMILES string into an RDKit molecule (raises ValueError if invalid).",
        validate_smiles,
        compute_class=ComputeClass.LOCAL,
    ))
    registry.register(Tool(
        "calculate_descriptors", "chemistry",
        "Compute 10 physicochemical descriptors (MW, LogP, TPSA, H-bond donors/acceptors, ...) for a SMILES string.",
        extract_descriptors,
        compute_class=ComputeClass.LOCAL,
    ))
    registry.register(Tool(
        "generate_3d", "chemistry",
        "Generate 3D atomic coordinates for a molecule.",
        utils_router.generate_3d_coordinates,
        compute_class=ComputeClass.LOCAL_SMALL,
    ))

    # --- Prediction tools (one per trained ADMET/binding model) ----------
    # All LOCAL: RandomForest inference on an already-loaded model, cheap.
    prediction_tools = [
        ("predict_solubility", solubility.predict_solubility, "Predict aqueous solubility (logS)."),
        ("predict_bbb", bbbp.predict_bbbp, "Predict blood-brain barrier permeability."),
        ("predict_cyp3a4", cyp3a4.predict_cyp3a4, "Predict CYP3A4 enzyme inhibition."),
        ("predict_toxicity", toxicity.predict_toxicity, "Predict general toxicity."),
        ("predict_binding", binding_score.predict_binding_score, "Predict drug-target binding affinity."),
        ("predict_cox2", cox2.predict_cox2, "Predict COX2 enzyme inhibition."),
        ("predict_hepg2", hepg2.predict_hepg2, "Predict HepG2 cell toxicity."),
        ("predict_ace2", ace2.predict_ace2, "Predict ACE2 receptor binding."),
        ("predict_half_life", half_life.predict_half_life, "Predict plasma half-life."),
    ]
    for name, fn, desc in prediction_tools:
        registry.register(Tool(name, "prediction", desc, fn, compute_class=ComputeClass.LOCAL))

    # LOCAL_SMALL: same per-molecule work as the single predictors above,
    # just looped — batch_size is what makes it worth a distinct class
    # (ResourceManager checks it against MAX_LOCAL_BATCH_SIZE).
    registry.register(Tool(
        "predict_batch", "prediction",
        "Run every requested model across a list of SMILES strings.",
        batch_router._execute_batch,
        compute_class=ComputeClass.LOCAL_SMALL,
    ))

    # --- Docking -----------------------------------------------------------
    # start_docking(payload: DockStartRequest) enqueues a Job via JobStore
    # and returns immediately — actual execution happens in the separate
    # LocalWorker process (jobs/workers/docking_worker.py), never inline.
    # HEAVY_LOCAL: runs via LocalWorker/job queue, not inline. supports_remote
    # is True as an interface capability only — no RemoteWorker exists yet.
    registry.register(Tool(
        "run_docking", "docking",
        "Start an AutoDock Vina docking job for a ligand SMILES against a target receptor.",
        dock.start_docking,
        compute_class=ComputeClass.HEAVY_LOCAL,
        supports_remote=True,
    ))

    # --- Funnel ----------------------------------------------------------
    # A multi-stage run: cheap LOCAL screening, then a serial dock of the top-N
    # survivors. HEAVY_LOCAL for the same reason docking is — it is gated by
    # ResourceManager._check_heavy (docking must be enabled, a concurrency slot
    # must be free) and created as a Job, never run inline. Unlike run_docking
    # it is executed by an in-process asyncio task, not the LocalWorker, so
    # supports_remote stays False. Its child docks are individual run_docking
    # Jobs through the same path, so MAX_DOCKING_CONCURRENT is respected.
    # See docs/development/funnel-service.md.
    from funnel.service import execute_run as _funnel_execute
    registry.register(Tool(
        "run_funnel", "funnel",
        "Run the computational funnel (frozen v7 policy): screen a candidate set, "
        "then dock the top-N survivors. Returns a run_id; poll /api/funnel/status.",
        _funnel_execute,
        compute_class=ComputeClass.HEAVY_LOCAL,
    ))

    return registry
