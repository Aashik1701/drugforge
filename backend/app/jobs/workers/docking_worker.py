"""
DockingWorker — the actual AutoDock Vina execution, moved out of
routers/dock.py's BackgroundTasks handler. Runs inside the LocalWorker
process, never inside FastAPI's own process.

Every function below (_prepare_ligand_pdbqt_from_smiles, _parse_vina_stdout,
_run_real_docking) is the SAME code that used to live in routers/dock.py —
moved, not rewritten. The one real change: cancellation and subprocess PID
tracking now go through JobStore (cross-process, via SQLite) instead of an
in-memory dict, because the worker is a separate OS process from the API
that receives the /cancel request.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from jobs.models import JobStatus
from jobs.store import JobStore
from utils.vina_env import EXPECTED_VINA_VERSION, resolved_vina_version, vina_bin_path

logger = logging.getLogger(__name__)

# --- Paths --- (identical to the old routers/dock.py constants)
BACKEND_DIR = Path(__file__).resolve().parents[3]
TARGETS_DIR = Path(os.getenv("DOCKING_TARGETS_DIR", BACKEND_DIR / "targets"))
VINA_BIN = vina_bin_path()  # backend/bin/vina, or $VINA_BIN — see utils/vina_env.py


def _docking_seed() -> int:
    """Fixed by default — never time- or PID-derived. Overridable via DOCKING_SEED."""
    try:
        return int(os.getenv("DOCKING_SEED", "42"))
    except ValueError:
        return 42


def _docking_cpu() -> int:
    """
    Vina threads. Pinned to 1 by default: with a fixed --seed, Vina's Monte
    Carlo search is only bit-for-bit reproducible for a *fixed* CPU count, so
    a single fixed value is what makes stored affinities comparable across
    machines with different core counts. Overridable via DOCKING_CPU.
    """
    try:
        return max(1, int(os.getenv("DOCKING_CPU", "1")))
    except ValueError:
        return 1


def _docking_num_modes() -> int:
    try:
        return int(os.getenv("DOCKING_N_POSES", "5"))
    except ValueError:
        return 5

TARGET_CONFIG: dict[str, dict[str, Any]] = {
    "cox2": {
        "receptor": "cox2_receptor.pdbqt",
        "center": [22.1, 10.5, -14.3],
        "box_size": [20.0, 20.0, 20.0],
    },
    "ace2": {
        "receptor": "ace2_receptor.pdbqt",
        "center": [15.1, 22.5, 9.0],
        "box_size": [20.0, 20.0, 20.0],
    },
}


def _prepare_ligand_pdbqt_from_smiles(smiles: str, seed: Optional[int] = None) -> str:
    """
    Convert SMILES → 3D conformer → PDBQT using RDKit + Meeko.

    The ETKDG embedding is seeded (default DOCKING_SEED) on BOTH the normal
    and the random-coords fallback path, so the conformer handed to Vina is
    itself reproducible — otherwise a fixed --seed on a non-deterministic
    starting geometry would still drift.
    """
    from rdkit import Chem
    from rdkit.Chem import AllChem

    if seed is None:
        seed = _docking_seed()

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError("Invalid SMILES string")

    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = seed
    embed_res = AllChem.EmbedMolecule(mol, params)
    if embed_res == -1:
        embed_res = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=seed)
        if embed_res == -1:
            raise ValueError("Failed to embed ligand in 3D")

    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
    except Exception:
        logger.warning("MMFF optimization skipped for docking ligand")

    from meeko import MoleculePreparation

    preparator = MoleculePreparation()
    setups = preparator.prepare(mol)
    if not setups:
        raise ValueError("Meeko failed to prepare ligand")

    pdbqt_str: Optional[str] = None

    try:
        from meeko import PDBQTWriterLegacy

        pdbqt_str, is_ok, error_msg = PDBQTWriterLegacy.write_string(setups[0])
        if not is_ok:
            raise ValueError(error_msg or "Unable to generate ligand PDBQT")
    except ImportError:
        for setup in setups:
            if hasattr(setup, "write_pdbqt_string"):
                pdbqt_str = setup.write_pdbqt_string()
                break

    if not pdbqt_str:
        raise ValueError("Unable to generate ligand PDBQT from Meeko setup")

    return pdbqt_str


def _parse_vina_stdout(stdout: str) -> list[dict[str, float]]:
    """Unchanged from the original routers/dock.py."""
    results: list[dict[str, float]] = []
    pattern = re.compile(r"^\s*(\d+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)", re.MULTILINE)
    for match in pattern.finditer(stdout):
        results.append({
            "mode": int(match.group(1)),
            "affinity": float(match.group(2)),
            "rmsd_lb": float(match.group(3)),
            "rmsd_ub": float(match.group(4)),
        })
    return results


async def _is_cancelled(job_id: str, store: JobStore) -> bool:
    job = await store.get_job(job_id)
    return job is not None and job.status == JobStatus.CANCELLED


async def run_docking_job(
    job_id: str,
    smiles: str,
    target: str,
    exhaustiveness: int,
    store: JobStore,
    seed: Optional[int] = None,
    conformer_seed: Optional[int] = None,
) -> dict[str, Any]:
    """
    Execute real AutoDock Vina docking via CLI subprocess for job `job_id`.
    Same 3-step pipeline as the original _run_real_docking: prepare ligand,
    call vina, parse results. Raises on any failure — the caller (local_worker)
    is responsible for catching and marking the job failed.

    `seed` overrides ONLY Vina's `--seed` (the Monte-Carlo search seed); when
    None it falls back to DOCKING_SEED. `conformer_seed` overrides ONLY the
    RDKit ETKDG embedding seed; when None it also falls back to DOCKING_SEED.
    Splitting them lets a caller run several search replicas (varying `seed`)
    against one fixed conformer — the design the funnel/baseline eval relies on
    (see docs/development/local-worker.md). Both are recorded in the output.
    """
    if not VINA_BIN.exists():
        raise FileNotFoundError(
            f"Vina binary not found at {VINA_BIN}. Run scripts/setup_vina.sh to "
            f"download and checksum-verify a pinned AutoDock Vina "
            f"{EXPECTED_VINA_VERSION} build for this platform "
            f"(see docs/development/local-worker.md)."
        )

    target_cfg = TARGET_CONFIG[target]
    receptor_path = TARGETS_DIR / target_cfg["receptor"]
    if not receptor_path.exists():
        raise FileNotFoundError(
            f"Missing receptor file: {receptor_path}. "
            f"Run `python download_targets.py` to fetch protein structures."
        )

    # --- Resolve EVERY search parameter explicitly. Nothing is left to Vina's
    #     built-in defaults: seed, exhaustiveness, cpu, and num_modes are all
    #     passed on the command line and recorded in the job output below, so a
    #     stored affinity can be reproduced from the job record alone. ---
    seed = _docking_seed() if seed is None else int(seed)
    conformer_seed = seed if conformer_seed is None else int(conformer_seed)
    cpu = _docking_cpu()
    num_modes = _docking_num_modes()
    vina_version = resolved_vina_version()

    logger.info(
        "Preparing ligand PDBQT for SMILES: %s (conformer_seed=%d, vina_seed=%d)",
        smiles[:50], conformer_seed, seed,
    )
    ligand_pdbqt = _prepare_ligand_pdbqt_from_smiles(smiles, seed=conformer_seed)

    if await _is_cancelled(job_id, store):
        raise RuntimeError("Task cancelled by user")

    with tempfile.TemporaryDirectory(prefix="drugforge_dock_") as temp_dir:
        temp_path = Path(temp_dir)
        ligand_file = temp_path / "ligand.pdbqt"
        out_file = temp_path / "out.pdbqt"
        ligand_file.write_text(ligand_pdbqt)

        center = target_cfg["center"]
        box = target_cfg["box_size"]

        cmd = [
            str(VINA_BIN),
            "--receptor", str(receptor_path),
            "--ligand", str(ligand_file),
            "--out", str(out_file),
            "--center_x", str(center[0]),
            "--center_y", str(center[1]),
            "--center_z", str(center[2]),
            "--size_x", str(box[0]),
            "--size_y", str(box[1]),
            "--size_z", str(box[2]),
            "--exhaustiveness", str(exhaustiveness),
            "--num_modes", str(num_modes),
            "--seed", str(seed),
            "--cpu", str(cpu),
        ]

        logger.info(
            "Running Vina (version=%s exhaustiveness=%d seed=%d cpu=%d num_modes=%d): %s",
            vina_version, exhaustiveness, seed, cpu, num_modes, " ".join(cmd),
        )

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        # Persist the OS PID so a /cancel request from the (separate) API
        # process can kill this subprocess directly via os.kill(pid, SIGKILL)
        # — the two processes don't share memory, so this replaces the old
        # in-memory _RUNNING_PROCS dict as the cross-process handle.
        await store.update_job(job_id, worker_pid=proc.pid)

        timeout = int(os.getenv("DOCKING_TIMEOUT_SECONDS", "600"))
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout, stderr = proc.communicate()
            raise RuntimeError(f"Vina docking timed out after {timeout} seconds")
        finally:
            await store.update_job(job_id, worker_pid=None)

        if await _is_cancelled(job_id, store):
            raise RuntimeError("Task cancelled by user")

        if proc.returncode != 0:
            if proc.returncode in (-9, -15):
                raise RuntimeError("Task cancelled by user")
            error_detail = stderr or stdout or "Unknown error"
            logger.error("Vina failed (code %d): %s", proc.returncode, error_detail)
            raise RuntimeError(f"Vina docking failed: {error_detail[:500]}")

        vina_results = _parse_vina_stdout(stdout)
        if not vina_results:
            vina_results = _parse_vina_stdout(stderr)
        if not vina_results:
            logger.warning("Could not parse Vina output. stdout: %s", stdout[:500])
            raise RuntimeError("Vina completed but no binding affinities were parsed from output")

        best = vina_results[0]
        best_affinity = best["affinity"]

        if out_file.exists():
            docked_pdbqt = out_file.read_text()
        else:
            raise RuntimeError("Vina did not produce output file")

        logger.info(
            "Docking complete: affinity=%.2f kcal/mol, %d poses, "
            "exhaustiveness=%d seed=%d cpu=%d vina_version=%s",
            best_affinity, len(vina_results), exhaustiveness, seed, cpu, vina_version,
        )

        return {
            "affinity_kcal_mol": best_affinity,
            "docked_ligand_pdbqt": docked_pdbqt,
            "mode": "vina",
            "receptor_pdbqt": str(receptor_path.name),
            "all_poses": vina_results,
            # --- Full provenance: everything needed to re-run this exact dock.
            "exhaustiveness": exhaustiveness,
            "seed": seed,
            "conformer_seed": conformer_seed,
            "cpu": cpu,
            "num_modes": num_modes,
            "vina_version": vina_version,
            "target": target,
            "search_center": list(center),
            "search_box_size": list(box),
        }
