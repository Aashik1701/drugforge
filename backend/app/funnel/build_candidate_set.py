"""
Build a versioned candidate set from PUBLIC ChEMBL data.

Source: the ChEMBL bioactivity exports vendored under
ml/datasets/target_identification/ (see ml/README.md). No molecules are
invented; no activity labels are fabricated. The ChEMBL activity fields are
carried through verbatim as metadata and used only to stratify a deterministic
sample — they are NOT the evaluation's ground truth.

Run:  cd backend/app && ../venv/bin/python -m funnel.build_candidate_set            # cox2 (default)
      cd backend/app && ../venv/bin/python -m funnel.build_candidate_set --target ace2

Every target uses the IDENTICAL pipeline (same functions, same filter, same
stratified deterministic sample) — only the source file, the ChEMBL target id,
the per-bin sample sizes, and the reference-ligand list differ.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
DATASET_DIR = REPO_ROOT / "ml" / "datasets" / "target_identification"

RNG_SEED = 20260228

# Set-construction filter (docking tractability only — applied equally to every
# path, NOT the funnel's ADMET filter). Same for every target.
MW_MIN, MW_MAX = 150.0, 600.0
MAX_HEAVY_ATOMS = 45


@dataclass(frozen=True)
class TargetConfig:
    set_id: str
    source_csv: Path
    chembl_target: str          # e.g. "CHEMBL230"
    target_name: str
    source_tag: str             # value written to the CSV `source` column for sampled rows
    per_bin: dict               # {"potent": int, "moderate": int, "weak_or_inactive": int}
    references: list             # [(name, smiles), ...]


# 11 already-profiled reference ligands for cox2 (docs/development/local-worker.md).
COX2_REFERENCES = [
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

# ACE2 references: the 3 known binders used in the Task-2 box sanity check plus
# the ethanol negative control, so those measurements stay comparable.
ACE2_REFERENCES = [
    ("MLN-4760",   "CC(C)C[C@@H](C(=O)O)N[C@@H](Cc1cncn1Cc1cc(Cl)cc(Cl)c1)C(=O)O"),
    ("lisinopril", "NCCCC[C@H](N[C@@H](CCc1ccccc1)C(=O)O)C(=O)N1CCC[C@H]1C(=O)O"),
    ("captopril",  "CC(CS)C(=O)N1CCC[C@H]1C(=O)O"),
    ("ethanol",    "CCO"),
]

CONFIGS = {
    "cox2": TargetConfig(
        set_id="cox2_v1",
        source_csv=DATASET_DIR / "COX-2.csv",
        chembl_target="CHEMBL230",
        target_name="Cyclooxygenase-2",
        source_tag="chembl_cox2_CHEMBL230",
        per_bin={"potent": 12, "moderate": 11, "weak_or_inactive": 11},
        references=COX2_REFERENCES,
    ),
    "ace2": TargetConfig(
        set_id="ace2_v1",
        source_csv=DATASET_DIR / "ACE-2.csv",
        chembl_target="CHEMBL3736",
        target_name="Angiotensin-converting enzyme 2",
        source_tag="chembl_ace2_CHEMBL3736",
        per_bin={"potent": 14, "moderate": 13, "weak_or_inactive": 14},
        references=ACE2_REFERENCES,
    ),
}


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


def build(cfg: TargetConfig) -> int:
    out_csv = HERE / "datasets" / f"{cfg.set_id.replace('_v1', '')}_candidates_v1.csv"
    out_prov = out_csv.with_suffix(".provenance.md")
    if not cfg.source_csv.exists():
        print(f"FATAL: source not found: {cfg.source_csv}", file=sys.stderr)
        return 1

    n_rows = n_no_smiles = n_parse_fail = n_filtered_setconstruction = 0
    agg: dict[str, dict] = {}  # canonical_smiles -> aggregated record

    with cfg.source_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh, delimiter=";"):
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
                "pchembl_values": [], "types": set(), "comments": set(), "n_records": 0,
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

    print(f"[{cfg.set_id}] source rows                : {n_rows}")
    print(f"  dropped (no SMILES)      : {n_no_smiles}")
    print(f"  dropped (RDKit parse)    : {n_parse_fail}")
    print(f"  dropped (set-construction filter MW/heavy): {n_filtered_setconstruction}")
    print(f"unique molecules (canonical, deduped): {len(agg)}")

    ref_canon: dict[str, str] = {}
    for name, smi in cfg.references:
        c = largest_fragment_canonical(smi)
        if c is None:
            print(f"FATAL: reference ligand {name} failed to parse", file=sys.stderr)
            return 1
        ref_canon[c] = name

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
    for b, k in cfg.per_bin.items():
        pool = sorted(bins[b])
        rng.shuffle(pool)
        take = pool[:k]
        bin_counts[b] = len(take)
        sampled.extend(take)

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
        add_row(lid, rec["name"], canon, cfg.source_tag, rec, is_ref=False)

    for canon, refname in ref_canon.items():
        rec = agg.get(canon)
        if rec:
            lid = rec["chembl_id"] or f"REF_{refname}"
            add_row(lid, rec["name"] or refname, canon, "reference+chembl", rec, is_ref=True)
        else:
            add_row(f"REF_{refname}", refname, canon, "reference", None, is_ref=True)

    seen: dict[str, dict] = {}
    for r in out_rows:
        key = r["smiles"]
        if key in seen:
            if r["is_reference"] == "true":
                seen[key] = r
        else:
            seen[key] = r
    final = sorted(seen.values(), key=lambda r: (r["is_reference"] == "false", r["ligand_id"]))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["ligand_id", "name", "smiles", "source", "chembl_id",
                  "activity_pchembl_max", "activity_pchembl_n", "activity_types",
                  "activity_note", "is_reference"]
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(final)

    content_hash = hashlib.sha256(
        "\n".join(sorted(r["smiles"] for r in final)).encode()
    ).hexdigest()
    n_ref = sum(1 for r in final if r["is_reference"] == "true")

    prov = f"""# Candidate set `{cfg.set_id}` — provenance

- **set_id:** `{cfg.set_id}`
- **content_sha256** (sorted canonical SMILES): `{content_hash}`
- **size:** {len(final)} molecules ({len(final) - n_ref} sampled from ChEMBL + {n_ref} reference)
- **file:** `backend/app/funnel/datasets/{out_csv.name}`
- **generated by:** `backend/app/funnel/build_candidate_set.py --target {cfg.set_id.replace('_v1', '')}` (RNG seed `{RNG_SEED}`)

## Source

`ml/datasets/target_identification/{cfg.source_csv.name}` — a ChEMBL bioactivity
export for target **{cfg.chembl_target}** ({cfg.target_name}, *Homo sapiens*),
vendored in this repo (see `ml/README.md`). Public data. No molecules invented,
no activity labels fabricated — ChEMBL `pChEMBL`, `Standard Type`, and `Comment`
fields are carried through verbatim as metadata and used ONLY to stratify the sample.

## Pipeline (identical to every other target set)

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
7. Deterministic shuffle (seed {RNG_SEED}) + take per bin: {bin_counts}.
8. Add the {n_ref} reference ligands (canonicalised). References bypass step 4.
   If a reference also occurs in ChEMBL its row is marked `is_reference=true`.

## Columns

`ligand_id, name, smiles, source, chembl_id, activity_pchembl_max,
activity_pchembl_n, activity_types, activity_note, is_reference`

`activity_*` are descriptive only. The evaluation does not use them.
"""
    out_prov.write_text(prov)

    print(f"\nwrote {out_csv}  ({len(final)} molecules, {n_ref} reference)")
    print(f"wrote {out_prov}")
    print(f"content_sha256 = {content_hash}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", choices=sorted(CONFIGS), default="cox2")
    args = ap.parse_args()
    return build(CONFIGS[args.target])


if __name__ == "__main__":
    raise SystemExit(main())
