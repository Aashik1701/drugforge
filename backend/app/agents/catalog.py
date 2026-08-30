"""
agents.catalog -- the adapter between an HTTP request ("call tool X with this
JSON") and what a registered Tool.fn actually accepts (a positional string, a
pydantic model, or -- for heavy tools -- a job_input dict for ComputeRouter).

This layer exists so `POST /api/agent/runs` can reject an unknown tool or a
malformed argument *at submission*, before the asyncio orchestrator burns real
compute reaching UNKNOWN_TOOL / FAILED at step 7. It introspects the tools the
registry already holds; it does not modify the tool-registry contract (no field
added to Tool, no change to ToolRegistry) and it contains no scientific logic.

Each ToolSpec knows how to:
  - describe its arguments as JSON Schema           -> GET /api/agent/tools
  - validate a raw args dict                        -> submission 400s
  - build the (args, kwargs) for AgentRunner.call_tool  (LOCAL tools)
  - build the (job_type, job_input) for a heavy child  (HEAVY_LOCAL tools)
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from compute.policy import ComputeClass
from tools.registry import ToolRegistry

# Tools whose fn is `fn(smiles: str)` -- a bare positional string, not a model.
_STR_ARG_TOOLS = {"parse_smiles", "calculate_descriptors"}

_STR_ARG_SCHEMA = {
    "type": "object",
    "properties": {"smiles": {"type": "string", "description": "SMILES string"}},
    "required": ["smiles"],
    "additionalProperties": False,
}


class SpecError(ValueError):
    """Raised by a ToolSpec when a raw args dict cannot be turned into a real
    call. `errors` is a list of human-readable strings for the 400 body."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def _fmt_validation_error(exc: ValidationError) -> list[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", ())) or "(body)"
        out.append(f"{loc}: {err.get('msg', 'invalid')}")
    return out


@dataclass
class ToolSpec:
    name: str
    category: str
    description: str
    compute_class: str
    heavy: bool
    is_async: bool
    version: str
    args_schema: dict
    # one of these is set depending on `heavy`
    _model: Optional[type[BaseModel]] = None
    _kind: str = "model"  # "model" | "str_arg" | "funnel"

    # ---- machine + human catalog entry -------------------------------------
    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "compute_class": self.compute_class,
            "heavy": self.heavy,
            "is_async": self.is_async,
            "version": self.version,
            "args_schema": self.args_schema,
        }

    # ---- validation (submission time) ------------------------------------
    def validate(self, args: Any) -> list[str]:
        """Return a list of error strings; empty means the args are usable."""
        if not isinstance(args, dict):
            return [f"args must be a JSON object, got {type(args).__name__}"]
        try:
            if self.heavy:
                self.heavy_job(args)
            else:
                self.build_local(args)
        except SpecError as exc:
            return exc.errors
        except ValidationError as exc:
            return _fmt_validation_error(exc)
        except Exception as exc:  # noqa: BLE001 -- surfaced verbatim to the client
            return [str(exc)]
        return []

    # ---- LOCAL tools: -> AgentRunner.call_tool(state, name, *args, **kwargs)
    def build_local(self, args: dict) -> tuple[tuple, dict]:
        if self._kind == "unsupported":
            raise SpecError([f"tool '{self.name}' has no argument adapter for /api/agent"])
        if self._kind == "str_arg":
            smi = args.get("smiles")
            if not isinstance(smi, str) or not smi.strip():
                raise SpecError(["'smiles' must be a non-empty string"])
            extra = set(args) - {"smiles"}
            if extra:
                raise SpecError([f"unexpected argument(s): {', '.join(sorted(extra))}"])
            return (smi,), {}
        # model-arg tool
        assert self._model is not None
        model = self._model(**args)  # raises ValidationError
        return (model,), {}

    # ---- HEAVY tools: -> (job_type, job_input) for ComputeRouter --------
    def heavy_job(self, args: dict) -> tuple[str, dict]:
        if self._kind == "funnel":
            return _build_funnel_job(args)
        # run_docking
        assert self._model is not None, f"{self.name}: no model adapter"
        from routers.dock import TARGET_CONFIG

        model = self._model(**args)  # DockStartRequest -- raises ValidationError
        target = getattr(model, "target", None)
        if target not in TARGET_CONFIG:
            raise SpecError(
                [f"unknown target '{target}'; supported: {', '.join(sorted(TARGET_CONFIG))}"]
            )
        import os

        exh = getattr(model, "exhaustiveness", None) or int(os.getenv("DOCKING_EXHAUSTIVENESS", "8"))
        return "docking", {"smiles": model.smiles, "target": target, "exhaustiveness": exh}


def _build_funnel_job(args: dict) -> tuple[str, dict]:
    """Validate an agent's run_funnel args with the funnel's own guards and
    return the exact job_input the funnel router builds."""
    from funnel import service as funnel_service
    from schemas.funnel import FunnelStartRequest

    try:
        req = FunnelStartRequest(**args)
    except ValidationError:
        raise
    try:
        set_id, sha, candidates, _ = funnel_service.resolve_candidates(
            req.candidate_set_id, req.smiles
        )
        eff_n = funnel_service.validate_start(req.policy_id, req.budget_n, len(candidates))
    except funnel_service.FunnelInputError as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            raise SpecError([str(detail)])
        raise SpecError([str(detail)])
    return "funnel", {
        "candidate_set_id": set_id,
        "content_sha256": sha,
        "target": req.target,
        "budget_n": eff_n,
        "policy_id": req.policy_id,
        "candidates": [
            {"ligand_id": c.ligand_id, "name": c.name, "smiles": c.smiles} for c in candidates
        ],
    }


def _model_param(fn: Callable) -> Optional[type[BaseModel]]:
    """If fn's single meaningful parameter is annotated as a pydantic model,
    return that model class, else None. `eval_str=True` resolves string
    annotations from routers that use `from __future__ import annotations`."""
    for kw in ({"eval_str": True}, {}):
        try:
            sig = inspect.signature(fn, **kw)
            break
        except (ValueError, TypeError, NameError):
            sig = None
    if sig is None:
        return None
    params = [
        p for p in sig.parameters.values()
        if p.name not in ("self", "cls") and p.kind
        in (p.POSITIONAL_OR_KEYWORD, p.POSITIONAL_ONLY, p.KEYWORD_ONLY)
    ]
    if len(params) != 1:
        return None
    ann = params[0].annotation
    if inspect.isclass(ann) and issubclass(ann, BaseModel):
        return ann
    return None


def build_catalog(registry: ToolRegistry) -> dict[str, ToolSpec]:
    """One ToolSpec per registered tool. Called once at router import."""
    catalog: dict[str, ToolSpec] = {}
    for tool in registry.list():
        heavy = tool.compute_class in (ComputeClass.HEAVY_LOCAL, ComputeClass.REMOTE_CAPABLE)
        model = _model_param(tool.fn)

        if tool.name in _STR_ARG_TOOLS:
            kind, schema = "str_arg", dict(_STR_ARG_SCHEMA)
        elif tool.name == "run_funnel":
            kind = "funnel"
            from schemas.funnel import FunnelStartRequest

            schema = FunnelStartRequest.model_json_schema()
        elif tool.name == "run_docking":
            from schemas.docking import DockStartRequest

            kind = "docking"
            model = DockStartRequest
            schema = DockStartRequest.model_json_schema()
        elif model is not None:
            kind = "model"
            schema = model.model_json_schema()
        else:
            # A tool we have no adapter for -- list it (so /tools is complete)
            # but every call attempt fails validation with a clear message.
            kind = "unsupported"
            schema = {"type": "object", "description": "no argument adapter; not callable via /api/agent"}

        catalog[tool.name] = ToolSpec(
            name=tool.name,
            category=tool.category,
            description=tool.description,
            compute_class=tool.compute_class.value,
            heavy=heavy,
            is_async=tool.is_async,
            version=tool.version,
            args_schema=schema,
            _model=model,
            _kind=kind,
        )
    return catalog
