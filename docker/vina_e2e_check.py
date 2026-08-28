"""
Submit real docking job(s) to the running API, poll to completion, and assert
the result is genuine: negative affinity in kcal/mol, non-null PDBQT text,
elapsed_seconds > 0. With E2E_RUNS > 1, also assert every run's affinity is
identical (determinism under the fixed DOCKING_SEED).

Exits 0 only if every assertion passes.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx

API = "http://127.0.0.1:5001"
SMILES = "CC(=O)Oc1ccccc1C(=O)O"  # aspirin
TARGET = "cox2"
RUNS = int(os.getenv("E2E_RUNS", "3"))
EXHAUSTIVENESS = int(os.getenv("E2E_EXHAUSTIVENESS", "8"))
POLL_TIMEOUT = int(os.getenv("E2E_POLL_TIMEOUT", "1800"))


def submit_and_wait(client: httpx.Client, run_no: int) -> dict:
    r = client.post(
        f"{API}/api/dock/start",
        json={"smiles": SMILES, "target": TARGET, "exhaustiveness": EXHAUSTIVENESS},
    )
    r.raise_for_status()
    task_id = r.json()["task_id"]
    print(f"[run {run_no}] queued task_id={task_id}", flush=True)

    t0 = time.time()
    while True:
        s = client.get(f"{API}/api/dock/status/{task_id}").json()
        status = s["status"]
        if status in ("completed", "failed", "cancelled"):
            print(f"[run {run_no}] {status} after {time.time() - t0:.0f}s", flush=True)
            return s
        if time.time() - t0 > POLL_TIMEOUT:
            raise TimeoutError(f"run {run_no} still {status} after {POLL_TIMEOUT}s")
        time.sleep(3)


def main() -> int:
    failures: list[str] = []
    results: list[dict] = []

    with httpx.Client(timeout=30) as client:
        for i in range(1, RUNS + 1):
            res = submit_and_wait(client, i)
            results.append(res)

    first = results[0]
    print("\n================ run 1 full status ================")
    print(json.dumps(first, indent=2)[:4000])
    print("==================================================\n")

    # --- assertions on the primary run ---
    if first["status"] != "completed":
        failures.append(f"run 1 status is {first['status']!r}, expected 'completed' "
                        f"(error={first.get('error')!r})")
    else:
        aff = first.get("affinity_kcal_mol")
        if not isinstance(aff, (int, float)) or aff >= 0:
            failures.append(f"affinity_kcal_mol={aff!r} — expected a real negative kcal/mol")

        pdbqt = first.get("docked_ligand_pdbqt")
        if not pdbqt or ("ATOM" not in pdbqt and "HETATM" not in pdbqt):
            failures.append("docked_ligand_pdbqt is null / not PDBQT atom records")

        elapsed = first.get("elapsed_seconds")
        if not isinstance(elapsed, (int, float)) or elapsed <= 0:
            failures.append(f"elapsed_seconds={elapsed!r} — expected > 0")

        for field in ("seed", "cpu", "num_modes", "vina_version", "exhaustiveness"):
            if first.get(field) in (None, ""):
                failures.append(f"provenance field {field!r} missing from job record")

    # --- determinism across runs ---
    if RUNS > 1:
        completed = [r for r in results if r["status"] == "completed"]
        affs = {r["affinity_kcal_mol"] for r in completed}
        print(f"affinities across {len(completed)} completed runs: "
              f"{sorted(a for a in affs)}")
        if len(completed) != RUNS:
            failures.append(f"only {len(completed)}/{RUNS} runs completed")
        elif len(affs) != 1:
            failures.append(f"NON-DETERMINISTIC: distinct affinities {sorted(affs)}")
        else:
            print(f"determinism: all {RUNS} runs -> {affs.pop():+.4f} kcal/mol  ✓")

    print()
    if failures:
        print("E2E RESULT: FAIL")
        for f in failures:
            print("  ✗", f)
        return 1

    print("E2E RESULT: PASS ✓")
    print(f"  affinity_kcal_mol = {first['affinity_kcal_mol']:+.4f} kcal/mol")
    print(f"  elapsed_seconds   = {first['elapsed_seconds']}")
    print(f"  docked_ligand_pdbqt = {len(first['docked_ligand_pdbqt'])} chars of PDBQT")
    print(f"  vina_version = {first['vina_version']}  seed = {first['seed']}  "
          f"cpu = {first['cpu']}  exhaustiveness = {first['exhaustiveness']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
