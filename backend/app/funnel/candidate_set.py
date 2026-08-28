"""
Loader for the versioned candidate set. Read-only.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_CSV = HERE / "datasets" / "cox2_candidates_v1.csv"
DEFAULT_SET_ID = "cox2_v1"


@dataclass(frozen=True)
class Candidate:
    ligand_id: str
    name: str
    smiles: str
    source: str
    chembl_id: str
    activity_pchembl_max: str
    activity_note: str
    is_reference: bool


@dataclass(frozen=True)
class CandidateSet:
    set_id: str
    csv_path: Path
    content_sha256: str
    candidates: list[Candidate]

    def __len__(self) -> int:
        return len(self.candidates)


def load_candidate_set(csv_path: Path | None = None, set_id: str = DEFAULT_SET_ID) -> CandidateSet:
    csv_path = Path(csv_path or DEFAULT_CSV)
    rows: list[Candidate] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append(Candidate(
                ligand_id=r["ligand_id"],
                name=r["name"],
                smiles=r["smiles"],
                source=r["source"],
                chembl_id=r.get("chembl_id", ""),
                activity_pchembl_max=r.get("activity_pchembl_max", ""),
                activity_note=r.get("activity_note", ""),
                is_reference=r.get("is_reference", "false").strip().lower() == "true",
            ))
    content_hash = hashlib.sha256(
        "\n".join(sorted(c.smiles for c in rows)).encode()
    ).hexdigest()
    return CandidateSet(set_id=set_id, csv_path=csv_path, content_sha256=content_hash, candidates=rows)
