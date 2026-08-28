#!/usr/bin/env python3
"""
Download and prepare protein receptor files for AutoDock Vina docking.

Downloads PDB structures from RCSB, removes waters/ligands, and converts
to PDBQT format using Open Babel.

Usage:
    python download_targets.py

Requirements:
    - Open Babel CLI (obabel) installed: brew install open-babel
    - Internet connection for RCSB PDB downloads
"""

import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

TARGETS_DIR = Path(__file__).resolve().parent / "targets"

# Target definitions: PDB ID → output name and active-site center for docking
TARGETS = {
    "cox2": {
        "pdb_id": "1CX2",
        "output": "cox2_receptor.pdbqt",
        "description": "Cyclooxygenase-2 (COX-2)",
        "center": [22.1, 10.5, -14.3],
        "box_size": [20.0, 20.0, 20.0],
    },
    "ace2": {
        "pdb_id": "1R42",
        "output": "ace2_receptor.pdbqt",
        "description": "Angiotensin-Converting Enzyme 2 (ACE2)",
        "center": [15.1, 22.5, 9.0],
        "box_size": [20.0, 20.0, 20.0],
    },
}


def check_obabel():
    """Verify Open Babel CLI is available."""
    if shutil.which("obabel") is None:
        print("ERROR: 'obabel' not found. Install with: brew install open-babel")
        sys.exit(1)
    print("✓ Open Babel (obabel) found")


def download_pdb(pdb_id: str, dest: Path) -> Path:
    """Download a PDB file from RCSB."""
    url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    pdb_file = dest / f"{pdb_id}.pdb"

    if pdb_file.exists():
        print(f"  → {pdb_id}.pdb already exists, skipping download")
        return pdb_file

    print(f"  → Downloading {pdb_id} from RCSB...")
    try:
        urllib.request.urlretrieve(url, pdb_file)
        size_kb = pdb_file.stat().st_size / 1024
        print(f"  → Downloaded {size_kb:.0f} KB")
    except Exception as e:
        print(f"ERROR: Failed to download {pdb_id}: {e}")
        sys.exit(1)

    return pdb_file


def clean_pdb(pdb_file: Path) -> Path:
    """
    Remove water molecules (HOH), non-standard ligands, and keep only
    protein ATOM/HETATM records needed for docking.
    """
    cleaned = pdb_file.with_suffix(".clean.pdb")
    kept = 0
    removed_waters = 0
    removed_hetero = 0

    with open(pdb_file) as fin, open(cleaned, "w") as fout:
        for line in fin:
            record = line[:6].strip()

            # Keep header/metadata
            if record in ("HEADER", "TITLE", "REMARK", "CRYST1", "MODEL", "ENDMDL", "END", "TER"):
                fout.write(line)
                continue

            # Remove waters
            if record in ("HETATM", "ATOM"):
                res_name = line[17:20].strip()
                if res_name == "HOH":
                    removed_waters += 1
                    continue
                # Keep only standard amino acids and common cofactors
                standard_residues = {
                    "ALA", "ARG", "ASN", "ASP", "CYS", "GLN", "GLU", "GLY",
                    "HIS", "ILE", "LEU", "LYS", "MET", "PHE", "PRO", "SER",
                    "THR", "TRP", "TYR", "VAL",
                    # Common modified residues / cofactors to keep
                    "MSE", "SEC", "PYL",
                }
                if record == "HETATM" and res_name not in standard_residues:
                    removed_hetero += 1
                    continue

                fout.write(line)
                kept += 1
                continue

        # Ensure END record
        fout.write("END\n")

    print(f"  → Cleaned: kept {kept} atoms, removed {removed_waters} waters, {removed_hetero} hetero atoms")
    return cleaned


def convert_to_pdbqt(pdb_file: Path, pdbqt_file: Path) -> Path:
    """Convert cleaned PDB to PDBQT using Open Babel."""
    cmd = [
        "obabel",
        str(pdb_file),
        "-O", str(pdbqt_file),
        "-xr",      # receptor mode (no flexible residues)
        "-xn",      # do not add hydrogens (obabel adds by default with -xr)
        "-h",       # add hydrogens
        "--partialcharge", "gasteiger",  # Gasteiger partial charges
    ]

    print(f"  → Converting to PDBQT: {pdbqt_file.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"  WARNING: obabel returned code {result.returncode}")
        if result.stderr:
            # obabel writes info to stderr even on success
            for line in result.stderr.strip().split("\n"):
                if "error" in line.lower() or "warning" in line.lower():
                    print(f"    {line}")

    if not pdbqt_file.exists() or pdbqt_file.stat().st_size == 0:
        print(f"ERROR: PDBQT conversion failed for {pdb_file.name}")
        sys.exit(1)

    size_kb = pdbqt_file.stat().st_size / 1024
    print(f"  → PDBQT file: {size_kb:.0f} KB")
    return pdbqt_file


def main():
    print("=" * 60)
    print("DrugForge — Protein Target Downloader & Preparer")
    print("=" * 60)

    check_obabel()
    TARGETS_DIR.mkdir(parents=True, exist_ok=True)

    for target_key, cfg in TARGETS.items():
        print(f"\n--- {cfg['description']} ({cfg['pdb_id']}) ---")

        pdbqt_path = TARGETS_DIR / cfg["output"]

        # Skip if PDBQT already exists
        if pdbqt_path.exists() and pdbqt_path.stat().st_size > 1000:
            print(f"  → {cfg['output']} already exists ({pdbqt_path.stat().st_size / 1024:.0f} KB), skipping")
            continue

        # Download
        pdb_file = download_pdb(cfg["pdb_id"], TARGETS_DIR)

        # Clean
        cleaned_pdb = clean_pdb(pdb_file)

        # Convert to PDBQT
        convert_to_pdbqt(cleaned_pdb, pdbqt_path)

        # Cleanup intermediate files
        cleaned_pdb.unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("Summary:")
    for target_key, cfg in TARGETS.items():
        pdbqt_path = TARGETS_DIR / cfg["output"]
        status = "✓" if pdbqt_path.exists() else "✗"
        size = f"{pdbqt_path.stat().st_size / 1024:.0f} KB" if pdbqt_path.exists() else "MISSING"
        print(f"  {status} {cfg['output']:30s} {size}")
    print("=" * 60)


if __name__ == "__main__":
    main()
