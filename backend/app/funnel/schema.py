"""
Run-record schema — defined FIRST, before either execution path.

ONE record shape, emitted by both `funnel.baseline` and `funnel.funnel`. If the
funnel needs a field the baseline doesn't (funnel_policy, per_candidate, the
reason a candidate was dropped), the baseline emits null / an empty list — it
never emits a different shape.

Persisted as JSON under `runs/`. `SCHEMA_VERSION` is bumped on any breaking
field change so the evaluator can refuse mismatched records.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "1.0.0"

# Repo root: backend/app/funnel/schema.py -> parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
RUNS_DIR = REPO_ROOT / "runs"


@dataclass
class DockingParams:
    """The SETTLED docking config. Identical for both paths — never varied."""

    exhaustiveness: int = 8
    seeds: list[int] = field(default_factory=lambda: [1, 42, 2024, 31337])
    cpu: int = 1
    target: str = "cox2"
    num_modes: int = 5
    conformer_seed: int = 42


@dataclass
class StageCount:
    """One row of the per-stage survivor ledger."""

    stage: str
    survivors_in: int
    survivors_out: int
    note: str = ""

    @property
    def dropped(self) -> int:
        return self.survivors_in - self.survivors_out


@dataclass
class RankedEntry:
    """One docked ligand in the ranked result list."""

    rank: int
    ligand_id: str
    smiles: str
    mean_affinity: Optional[float]          # mean best-affinity across seeds (kcal/mol)
    seed_stdev: Optional[float]             # population stdev across seeds
    per_seed_affinities: dict[str, Optional[float]]  # {"1": -6.1, "42": -6.0, ...}
    dock_wall_s: Optional[float] = None     # summed wall-clock for this ligand's seed docks
    tie_group: Optional[str] = None         # non-null => this rank is tied with others in the group


@dataclass
class FilteredOut:
    """A candidate the funnel dropped before docking (baseline: always empty)."""

    ligand_id: str
    smiles: str
    stage: str
    reason: str


@dataclass
class RunRecord:
    run_id: str
    path_name: str                         # "baseline" | "funnel"
    schema_version: str
    timestamp: str                         # ISO-8601 UTC
    platform: str
    vina_version: Optional[str]
    docking_params: DockingParams
    candidate_set_id: str
    candidate_set_size: int

    stage_survivors: list[StageCount]
    total_docking_jobs_submitted: int
    total_docking_wall_s: float
    total_run_wall_s: float

    results: list[RankedEntry]             # ranked, best (most negative mean) first
    filtered_out: list[FilteredOut]        # funnel only; [] for baseline

    # Funnel-only extras. Baseline emits null.
    funnel_policy: Optional[dict[str, Any]] = None
    per_candidate: Optional[dict[str, dict[str, Any]]] = None  # ligand_id -> ADMET/binding preds
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def save(self, out_dir: Optional[Path] = None, filename: Optional[str] = None) -> Path:
        out_dir = out_dir or RUNS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        name = filename or f"{self.path_name}_{self.candidate_set_id}_{self.run_id}.json"
        path = out_dir / name
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=False))
        return path

    # ------------------------------------------------------------------
    @staticmethod
    def load(path: Path) -> "RunRecord":
        raw = json.loads(Path(path).read_text())
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"{path}: schema_version {raw.get('schema_version')!r} != {SCHEMA_VERSION!r}"
            )
        raw["docking_params"] = DockingParams(**raw["docking_params"])
        raw["stage_survivors"] = [StageCount(**s) for s in raw["stage_survivors"]]
        raw["results"] = [RankedEntry(**r) for r in raw["results"]]
        raw["filtered_out"] = [FilteredOut(**f) for f in raw.get("filtered_out", [])]
        return RunRecord(**raw)
