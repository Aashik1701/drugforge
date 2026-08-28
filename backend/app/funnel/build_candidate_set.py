"""
Build the versioned COX-2 candidate set from PUBLIC ChEMBL data.

Source: ml/datasets/target_identification/COX-2.csv — a ChEMBL bioactivity
export for target CHEMBL230 (Cyclooxygenase-2, Homo sapiens), already vendored
in this repo (see ml/README.md). No molecules are invented; no activity labels
are fabricated. The ChEMBL activity fields are carried through verbatim as
metadata and used only to stratify a deterministic sample — they are NOT the
evaluation's ground truth (the eval compares funnel-vs-baseline docking).

Output: funnel/datasets/cox2_candidates_v1.csv  + .provenance.md

Run:  cd backend/app && ../venv/bin/python -m funnel.build_candidate_set
"""

from __future__ import annotations

import csv
import hashlib
import random
import sys
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SOURCE_CSV = REPO_ROOT / "ml" / "datasets" / "target_identification" / "COX-2.csv"
OUT_CSV = HERE / "datasets" / "cox2_candidates_v1.csv"
OUT_PROV = HERE / "datasets" / "cox2_candidates_v1.provenance.md"

SET_ID = "cox2_v1"
RNG_SEED = 20260228
TARGET_SAMPLED = 34          # sampled from ChEMBL; references are added on top
PER_BIN = {"potent": 12, "moderate": 11, "weak_or_inactive": 11}

# Set-construction filter (docking tractability only — applied equally to every
# path, NOT the funnel's ADMET filter). Documented in the provenance file.
MW_MIN, MW_MAX = 150.0, 600.0
MAX_HEAVY_ATOMS = 45

# 11 already-profiled reference ligands (docs/development/local-worker.md).
# Standard drug structures; canonicalised by RDKit below. Included verbatim so
# prior seed-variance / gap measurements stay comparable. References BYPASS the
# set-construction filter (ethanol is an intentional negative control).
REFERENCE_LIGANDS = [
    ("celecoxib",     "Cc1ccc(-c2cc(C(F)(F)F)nn2-c2ccc(S(N)(=O)=O)cc2)cc1"),
    ("rofecoxib",     "O=C1OCC(=C1c1ccccc1)c1ccc(S(C)(=O)=O)cc1"),
    ("indomethacin",  "COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c1ccc(Cl)cc1"),
    ("meloxicam",     "CN1C(=C(O)c2ccccc2S1(=O)=O)C(=O)Nc1ncc(C)s1"),
    ("diclofenac",    "O=C(O)Cc1ccccc1Nc1c(Cl)cccc1Cl"),
    ("naproxen",      "COc1ccc2cc(C(C)C(=O)O)ccc2c1"),
    ("ibuprofen",     "CC(C)Cc1ccc(C(C)C(=O)O)cc1"),
    ("aspirin",       "CC(=O)Oc1ccccc1C(=O)O"),
    ("acetaminophen", "CC(=O)Nc1ccc(O)cc1"),
    ("caffeine",      "Cn1cnc2c1c(=O)n(C)c(=O)n2C"),
    ("ethanol",       "CCO"),
]


def largest_fragment_canonical(smiles: str) -> str | None:
    """Parse, strip to the largest fragment (salt/counter-ion removal), canonicalise."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    frags = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=True)
    if not frags:
        return None
    biggest = max(frags, key=lambda m: m.GetNumHeavyAtoms())
    try:
        return Chem.MolToSmiles(biggest)
    except Exception:
        return None


def bin_for(pchembl: float | None, comment: str) -> str:
    if "not active" in (comment or "").lower():
        return "weak_or_inactive"
    if pchembl is None:
        return "weak_or_inactive"
    if pchembl >= 7.0:
        return "potent"
    if pchembl >= 5.0:
        return "moderate"
    return "weak_or_inactive"


def main() -> int:
    if not SOURCE_CSV.exists():
        print(f"FATAL: source not found: {SOURCE_CSV}", file=sys.stderr)
        return 1

    n_rows = 0
    n_no_smiles = 0
    n_parse_fail = 0
    n_filtered_setconstruction = 0

    # canonical_smiles -> aggregated record
    agg: dict[str, dict] = {}

    with SOURCE_CSV.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        for row in reader:
            n_rows += 1
            smi_raw = (row.get("Smiles") or "").strip()
            if not smi_raw:
                n_no_smiles += 1
                continue
            canon = largest_fragment_canonical(smi_raw)
            if canon is None:
                n_parse_fail += 1
                continue

            mol = Chem.MolFromSmiles(canon)
            mw = Descriptors.MolWt(mol)
            heavy = mol.GetNumHeavyAtoms()
            has_c = any(a.GetSymbol() == "C" for a in mol.GetAtoms())
            if not (MW_MIN <= mw <= MW_MAX and heavy <= MAX_HEAVY_ATOMS and has_c):
                n_filtered_setconstruction += 1
                continue

            try:
                pchembl = float(row.get("pChEMBL Value") or "")
            except ValueError:
                pchembl = None
            comment = (row.get("Comment") or "").strip()

            rec = agg.setdefault(canon, {
                "chembl_id": (row.get("Molecule ChEMBL ID") or "").strip(),
                "name": (row.get("Molecule Name") or "").strip(),
                "pchembl_values": [],
                "types": set(),
                "comments": set(),
                "n_records": 0,
            })
            rec["n_records"] += 1
            if pchembl is not None:
                rec["pchembl_values"].append(pchembl)
            if row.get("Standard Type"):
                rec["types"].add(row["Standard Type"].strip())
            if comment:
                rec["comments"].add(comment)
            if not rec["name"] and row.get("Molecule Name"):
                rec["name"] = row["Molecule Name"].strip()

    print(f"source rows                : {n_rows}")
    print(f"  dropped (no SMILES)      : {n_no_smiles}")
    print(f"  dropped (RDKit parse)    : {n_parse_fail}")
    print(f"  dropped (set-construction filter MW/heavy): {n_filtered_setconstruction}")
    print(f"unique molecules (canonical, deduped): {len(agg)}")

    # Reference canonical SMILES first, so we can exclude them from the sample pool.
    ref_canon: dict[str, str] = {}
    for name, smi in REFERENCE_LIGANDS:
        c = largest_fragment_canonical(smi)
        if c is None:
            print(f"FATAL: reference ligand {name} failed to parse", file=sys.stderr)
            return 1
        ref_canon[c] = name

    # Bin the pool (excluding anything that is a reference structure).
    bins: dict[str, list[str]] = {"potent": [], "moderate": [], "weak_or_inactive": []}
    for canon, rec in agg.items():
        if canon in ref_canon:
            continue
        pmax = max(rec["pchembl_values"]) if rec["pchembl_values"] else None
        comm = " ; ".join(sorted(rec["comments"]))
        bins[bin_for(pmax, comm)].append(canon)

    rng = random.Random(RNG_SEED)
    sampled: list[str] = []
    bin_counts: dict[str, int] = {}
    for b, k in PER_BIN.items():
        pool = sorted(bins[b])          # sort for determinism before shuffle
        rng.shuffle(pool)
        take = pool[:k]
        bin_counts[b] = len(take)
        sampled.extend(take)

    # Assemble final rows.
    out_rows: list[dict] = []

    def add_row(ligand_id, name, canon, source, rec, is_ref):
        pvals = rec["pchembl_values"] if rec else []
        out_rows.append({
            "ligand_id": ligand_id,
            "name": name or "",
            "smiles": canon,
            "source": source,
            "chembl_id": (rec or {}).get("chembl_id", ""),
            "activity_pchembl_max": f"{max(pvals):.2f}" if pvals else "",
            "activity_pchembl_n": len(pvals),
            "activity_types": "|".join(sorted((rec or {}).get("types", []))) if rec else "",
            "activity_note": " ; ".join(sorted((rec or {}).get("comments", []))) if rec else "",
            "is_reference": "true" if is_ref else "false",
        })

    for canon in sampled:
        rec = agg[canon]
        lid = rec["chembl_id"] or ("MOL_" + hashlib.sha1(canon.encode()).hexdigest()[:10])
        add_row(lid, rec["name"], canon, "chembl_cox2_CHEMBL230", rec, is_ref=False)

    for canon, refname in ref_canon.items():
        rec = agg.get(canon)  # a reference may also appear in ChEMBL
        if rec:
            lid = rec["chembl_id"] or f"REF_{refname}"
            add_row(lid, rec["name"] or refname, canon, "reference+chembl", rec, is_ref=True)
        else:
            add_row(f"REF_{refname}", refname, canon, "reference", None, is_ref=True)

    # Final dedup by canonical smiles (reference that was also sampled: keep ref row).
    seen: dict[str, dict] = {}
    for r in out_rows:
        key = r["smiles"]
        if key in seen:
            if r["is_reference"] == "true":
                seen[key] = r
        else:
            seen[key] = r
    final = sorted(seen.values(), key=lambda r: (r["is_reference"] == "false", r["ligand_id"]))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ligand_id", "name", "smiles", "source", "chembl_id",
                  "activity_pchembl_max", "activity_pchembl_n", "activity_types",
                  "activity_note", "is_reference"]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(final)

    content_hash = hashlib.sha256(
        "\n".join(sorted(r["smiles"] for r in final)).encode()
    ).hexdigest()

    n_ref = sum(1 for r in final if r["is_reference"] == "true")
    prov = f"""# Candidate set `{SET_ID}` — provenance

- **set_id:** `{SET_ID}`
- **content_sha256** (sorted canonical SMILES): `{content_hash}`
- **size:** {len(final)} molecules ({len(final) - n_ref} sampled from ChEMBL + {n_ref} reference)
- **file:** `backend/app/funnel/datasets/cox2_candidates_v1.csv`
- **generated by:** `backend/app/funnel/build_candidate_set.py` (RNG seed `{RNG_SEED}`)

## Source

`ml/datasets/target_identification/COX-2.csv` — a ChEMBL bioactivity export for
target **CHEMBL230** (Cyclooxygenase-2, *Homo sapiens*), vendored in this repo
(see `ml/README.md`). Public data. No molecules invented, no activity labels
fabricated — ChEMBL `pChEMBL`, `Standard Type`, and `Comment` fields are carried
through verbatim as metadata and used ONLY to stratify the sample.

## Pipeline

1. Read {n_rows} activity rows.
2. Drop rows with no SMILES: {n_no_smiles}.
3. Parse each SMILES with RDKit; strip to the largest fragment (salt / counter-ion
   removal); canonicalise. RDKit parse failures dropped: {n_parse_fail}.
4. Set-construction filter (docking tractability, applied to ALL paths equally,
   NOT the funnel ADMET filter): {MW_MIN:.0f} <= MW <= {MW_MAX:.0f}, heavy atoms
   <= {MAX_HEAVY_ATOMS}, must contain carbon. Dropped: {n_filtered_setconstruction}.
5. Deduplicate on canonical SMILES: {len(agg)} unique molecules remain.
6. Bin by max pChEMBL across records: potent (>=7), moderate (5-7),
   weak_or_inactive (<5, or "Not Active" comment, or no pChEMBL).
7. Deterministic shuffle (seed {RNG_SEED}) + take per bin:
   {bin_counts}.
8. Add the {n_ref} reference ligands (canonicalised). References bypass step 4
   (ethanol is an intentional negative control). If a reference also occurs in
   ChEMBL, its row is marked `is_reference=true` and keeps the ChEMBL id.

## Columns

`ligand_id, name, smiles, source, chembl_id, activity_pchembl_max,
activity_pchembl_n, activity_types, activity_note, is_reference`

`activity_*` are descriptive only. The evaluation does not use them.
"""
    OUT_PROV.write_text(prov)

    print(f"\nwrote {OUT_CSV}  ({len(final)} molecules, {n_ref} reference)")
    print(f"wrote {OUT_PROV}")
    print(f"content_sha256 = {content_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
