"""
Thin helpers that run tools THROUGH the compute fabric — every call is
`tool_registry.get(name)` -> `compute_router.execute(tool, ...)`. Nothing here
touches ResourceManager, JobStore internals, LocalExecutor, or Vina directly,
and nothing here is a mock: a missing model or a broken Vina surfaces as an
error, never a synthetic value.

Used by both `funnel.baseline` and `funnel.funnel`.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

APP_DIR = Path(__file__).resolve().parents[1]     # backend/app

# The 9 ADMET/property prediction tools (registry names), in funnel-stage order.
ADMET_TOOLS = [
    "predict_solubility", "predict_bbb", "predict_cyp3a4", "predict_toxicity",
    "predict_cox2", "predict_hepg2", "predict_ace2", "predict_half_life",
]
BINDING_TOOL = "predict_binding"
# registry name -> PredictionResponse.model_name (what we key results by)
_TOOL_TO_MODEL = {
    "predict_solubility": "solubility", "predict_bbb": "bbbp", "predict_cyp3a4": "cyp3a4",
    "predict_toxicity": "toxicity", "predict_cox2": "cox2", "predict_hepg2": "hepg2",
    "predict_ace2": "ace2", "predict_half_life": "half_life", "predict_binding": "binding_score",
}

_STARTED = False


async def get_fabric_async():
    """Return (tool_registry, compute_router, job_store), running app startup once.

    COMPUTE_MODE must already be set in the environment before the first call
    (main builds its ComputePolicy at import time)."""
    global _STARTED
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))
    import main  # noqa: WPS433
    if not _STARTED:
        await main.startup_event()
        _STARTED = True
    return main.tool_registry, main.compute_router, main.job_store


# ---------------------------------------------------------------------------
# LOCAL tools
# ---------------------------------------------------------------------------
async def call_local(tool_name: str, *args):
    """tool_registry.get(name) -> compute_router.execute(tool, *args). LOCAL only."""
    reg, router, _ = await get_fabric_async()
    tool = reg.get(tool_name)
    if tool is None:
        raise KeyError(f"tool {tool_name!r} not registered")
    return await router.execute(tool, *args)


async def validate_smiles_fabric(smiles: str) -> bool:
    try:
        await call_local("parse_smiles", smiles)
        return True
    except Exception:
        return False


async def descriptors_fabric(smiles: str) -> dict[str, float]:
    from funnel.policy import DESCRIPTOR_NAMES
    arr = await call_local("calculate_descriptors", smiles)
    vals = list(map(float, list(arr)[0]))
    return dict(zip(DESCRIPTOR_NAMES, vals))


async def predict_all_fabric(smiles: str) -> dict[str, float]:
    """Run all 9 ADMET/property models + the binding model through the fabric."""
    out: dict[str, float] = {}
    from schemas.molecule import MoleculeInput
    payload = MoleculeInput(smiles=smiles)
    for tool_name in [*ADMET_TOOLS, BINDING_TOOL]:
        resp = await call_local(tool_name, payload)
        out[_TOOL_TO_MODEL[tool_name]] = float(resp.prediction)
    return out


# ---------------------------------------------------------------------------
# HEAVY_LOCAL docking (through the fabric + JobStore + LocalWorker)
# ---------------------------------------------------------------------------
@dataclass
class SeedDock:
    seed: int
    affinity: Optional[float]
    wall_s: float
    status: str
    error: Optional[str] = None


@dataclass
class DockResult:
    ligand_id: str
    smiles: str
    per_seed: list[SeedDock] = field(default_factory=list)
    jobs_submitted: int = 0
    wall_s_total: float = 0.0

    @property
    def affinities(self) -> list[float]:
        return [s.affinity for s in self.per_seed if s.affinity is not None]

    @property
    def mean_affinity(self) -> Optional[float]:
        a = self.affinities
        return sum(a) / len(a) if a else None

    @property
    def seed_stdev(self) -> Optional[float]:
        a = self.affinities
        if len(a) < 2:
            return 0.0 if a else None
        m = sum(a) / len(a)
        return (sum((x - m) ** 2 for x in a) / len(a)) ** 0.5

    @property
    def per_seed_map(self) -> dict[str, Optional[float]]:
        return {str(s.seed): s.affinity for s in self.per_seed}


async def _dock_one(smiles: str, target: str, exhaustiveness: int, seed: int,
                    conformer_seed: int, num_modes: int, poll_timeout: int) -> SeedDock:
    reg, router, job_store = await get_fabric_async()
    tool = reg.get("run_docking")
    job_id = f"funnel_{uuid.uuid4().hex[:12]}"
    t0 = time.perf_counter()

    # Retry only on ComputeRejected (concurrency race); real failures propagate.
    from compute.router import ComputeRejected
    for attempt in range(60):
        try:
            await router.execute(
                tool,
                _job_store=job_store,
                _job_type="docking",
                _job_id=job_id,
                _job_input={
                    "smiles": smiles, "target": target, "exhaustiveness": exhaustiveness,
                    "seed": seed, "conformer_seed": conformer_seed, "num_modes": num_modes,
                },
            )
            break
        except ComputeRejected:
            await asyncio.sleep(2)
    else:
        return SeedDock(seed, None, time.perf_counter() - t0, "rejected",
                        "ComputeRejected for 60 attempts")

    # Deadline on MONOTONIC time, not wall-clock: time.time() keeps advancing
    # while a laptop is asleep, so an overnight suspend used to blow the timeout
    # and mark a job "timeout" even though the worker had no real time to run it
    # (and in fact completed it fine on wake). perf_counter()/monotonic() pause
    # during sleep, which is the semantics we want — "how long has the worker
    # actually had?".
    deadline = time.monotonic() + poll_timeout
    while True:
        job = await job_store.get_job(job_id)
        if job and job.status.value in ("completed", "failed", "cancelled"):
            wall = time.perf_counter() - t0
            if job.status.value == "completed":
                aff = (job.output or {}).get("affinity_kcal_mol")
                return SeedDock(seed, float(aff) if aff is not None else None, wall, "completed")
            return SeedDock(seed, None, wall, job.status.value, job.error)
        if time.monotonic() > deadline:
            return SeedDock(seed, None, time.perf_counter() - t0, "timeout",
                            f"no terminal state in {poll_timeout}s of active runtime")
        await asyncio.sleep(2)


async def dock_candidate(
    ligand_id: str, smiles: str, seeds: list[int],
    *, target: str = "cox2", exhaustiveness: int = 8, conformer_seed: int = 42,
    num_modes: int = 5, poll_timeout: int = 1200,
) -> DockResult:
    """Dock one ligand once per seed, strictly serial (concurrency cap = 1)."""
    res = DockResult(ligand_id=ligand_id, smiles=smiles)
    for s in seeds:
        sd = await _dock_one(smiles, target, exhaustiveness, s, conformer_seed, num_modes, poll_timeout)
        res.per_seed.append(sd)
        res.jobs_submitted += 1
        res.wall_s_total += sd.wall_s
    return res


# ---------------------------------------------------------------------------
# LocalWorker lifecycle (a docking job only executes if this process is up)
# ---------------------------------------------------------------------------
@contextlib.contextmanager
def local_worker_process(env_overrides: Optional[dict] = None, log_path: Optional[str] = None):
    """
    Start `python -m jobs.workers.local_worker` for the duration of the block.

    Worker stdout+stderr go to a FILE, never an unread pipe — the worker is
    chatty (per-job logs, meeko/RDKit warnings) and an undrained OS pipe buffer
    (~64KB) will block its logging writes and deadlock the whole run.
    """
    env = os.environ.copy()
    env.setdefault("COMPUTE_MODE", "balanced")
    if env_overrides:
        env.update(env_overrides)

    log_path = log_path or f"/tmp/funnel_worker_{uuid.uuid4().hex[:8]}.log"
    log_fh = open(log_path, "w")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "jobs.workers.local_worker"],
        cwd=str(APP_DIR), env=env,
        stdout=log_fh, stderr=subprocess.STDOUT, text=True,
    )
    print(f"[funnel] LocalWorker pid={proc.pid} log={log_path}", flush=True)
    try:
        time.sleep(3)  # let it start polling
        if proc.poll() is not None:
            log_fh.close()
            raise RuntimeError(f"LocalWorker exited immediately; see {log_path}:\n"
                               + Path(log_path).read_text()[-2000:])
        yield proc
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=10)
        with contextlib.suppress(Exception):
            proc.kill()
        log_fh.close()
