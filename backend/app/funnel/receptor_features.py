"""
funnel.receptor_features -- Pass 10. Build four feature families for the cox2 and
ace2 candidate sets and cache them as content-hashed artifacts.

F1  control            ECFP4 1024 + 10 RDKit descriptors (Pass 5's exact set)   PRESCREEN-USABLE
F2  shape/geometry     ligand 3D shape vs pocket geometry + fit ratios          PRESCREEN-USABLE
F3  pharmacophore      ligand donor/acceptor/aromatic/etc counts x pocket       PRESCREEN-USABLE
F4  pose interaction   contacts / buried SASA / catalytic distances from the    CEILING ONLY -- NOT
                       docked pose (ACE2 only; cox2 poses were not retained)    a prescreen (circular)

No new docking. No new heavyweight dependency (RDKit + a hand-rolled PDB parser
+ numpy). Frozen contracts untouched. Pre-registered in CHANGELOG Pass 10.

  cd backend/app && ../venv/bin/python -m funnel.receptor_features
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
from rdkit import Chem, RDLogger
from rdkit.Chem import AllChem, ChemicalFeatures, Descriptors, Descriptors3D, RDConfig

from funnel.candidate_set import load_candidate_set
from funnel.policy import DESCRIPTOR_NAMES
from funnel.schema import RUNS_DIR
from funnel.surrogate import morgan_bits

RDLogger.DisableLog("rdApp.*")

HERE = Path(__file__).resolve().parent
TARGETS = HERE.parents[1] / "targets"
CONF_SEED = 42

BOX = {  # frozen, from jobs/workers/docking_worker.py TARGET_CONFIG
    "cox2": {"receptor": "cox2_receptor.pdbqt", "center": (22.1, 10.5, -14.3), "size": (20.0, 20.0, 20.0)},
    "ace2": {"receptor": "ace2_receptor.pdbqt", "center": (53.1, 68.6, 31.2), "size": (20.0, 20.0, 20.0)},
}
SETS = {"cox2": ("cox2_v1", HERE / "datasets" / "cox2_candidates_v1.csv"),
        "ace2": ("ace2_v1", HERE / "datasets" / "ace2_candidates_v1.csv")}
ACE2_JOB_DB = Path("/tmp/funnel_baseline_110aff1e6d6c.db")  # ephemeral; poses extracted to a committed artifact

POCKET_SHELL = 4.0   # A beyond the box edge: pocket-lining atoms count
VDW = {"C": 1.7, "N": 1.55, "O": 1.52, "S": 1.8, "P": 1.8, "F": 1.47,
       "CL": 1.75, "BR": 1.85, "I": 1.98, "H": 1.2, "ZN": 1.39}

DONOR_ATOMS = {  # (resname, atomname) that can donate an H-bond, plus backbone N
    ("SER", "OG"), ("THR", "OG1"), ("TYR", "OH"), ("LYS", "NZ"),
    ("ARG", "NE"), ("ARG", "NH1"), ("ARG", "NH2"), ("HIS", "ND1"), ("HIS", "NE2"),
    ("ASN", "ND2"), ("GLN", "NE2"), ("TRP", "NE1"), ("CYS", "SG"),
}
ACCEPTOR_ATOMS = {
    ("ASP", "OD1"), ("ASP", "OD2"), ("GLU", "OE1"), ("GLU", "OE2"),
    ("SER", "OG"), ("THR", "OG1"), ("TYR", "OH"), ("ASN", "OD1"), ("GLN", "OE1"),
    ("HIS", "ND1"), ("HIS", "NE2"),
}
AROM_RES = {"PHE", "TYR", "TRP", "HIS"}
HYDROPHOBIC_RES = {"ALA", "VAL", "LEU", "ILE", "MET", "PHE", "PRO", "TRP"}
POS_RES = {"LYS", "ARG", "HIS"}
NEG_RES = {"ASP", "GLU"}


# ---------------------------------------------------------------------------
# PDB / PDBQT parsing (hand-rolled -- no dependency)
# ---------------------------------------------------------------------------
def _elem_from_name(name: str) -> str:
    s = name.strip()
    while s and s[0].isdigit():
        s = s[1:]
    if len(s) >= 2 and s[:2].upper() in VDW:
        return s[:2].upper()
    return (s[:1] or "C").upper()


def parse_atoms(text: str, models: str = "all"):
    """Yield dicts for ATOM/HETATM lines. models='first' stops at ENDMDL 1."""
    out = []
    for ln in text.splitlines():
        rec = ln[:6]
        if rec not in ("ATOM  ", "HETATM"):
            if models == "first" and ln.startswith("ENDMDL"):
                break
            continue
        try:
            x, y, z = float(ln[30:38]), float(ln[38:46]), float(ln[46:54])
        except ValueError:
            continue
        name = ln[12:16].strip()
        out.append({
            "name": name, "resname": ln[17:20].strip(), "chain": ln[21:22].strip(),
            "resseq": ln[22:26].strip(), "x": x, "y": y, "z": z,
            "elem": _elem_from_name(ln[12:16] if ln[12:16].strip() else name),
        })
    return out


def pocket_atoms(target: str):
    b = BOX[target]
    txt = (TARGETS / b["receptor"]).read_text()
    cx, cy, cz = b["center"]
    hx, hy, hz = (s / 2 + POCKET_SHELL for s in b["size"])
    keep = []
    for a in parse_atoms(txt):
        if a["elem"] == "H":
            continue
        if abs(a["x"] - cx) <= hx and abs(a["y"] - cy) <= hy and abs(a["z"] - cz) <= hz:
            keep.append(a)
    return keep


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------
def _coords(atoms):
    return np.array([[a["x"], a["y"], a["z"]] for a in atoms], dtype=float)


def radius_of_gyration(P):
    c = P.mean(axis=0)
    return float(np.sqrt(((P - c) ** 2).sum(axis=1).mean()))


def cdist(A, B):
    return np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(axis=2))


def cavity_volume(pocket_P, center, size, spacing=1.0):
    """Grid points inside the box whose nearest pocket atom is 2.8-5.0 A away:
    accessible cavity, not clashing, near a wall. Crude, deterministic, dep-free."""
    cx, cy, cz = center
    axes = [np.arange(c - s / 2 + spacing / 2, c + s / 2, spacing) for c, s in zip(center, size)]
    G = np.array(np.meshgrid(*axes, indexing="ij")).reshape(3, -1).T
    d = cdist(G, pocket_P).min(axis=1)
    return float(((d >= 2.8) & (d <= 5.0)).sum() * spacing ** 3)


# ---------------------------------------------------------------------------
# ligand conformer (the pre-docking conformer the pipeline builds)
# ---------------------------------------------------------------------------
def ligand_conformer(smiles: str):
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    mol = Chem.AddHs(mol)
    p = AllChem.ETKDGv3()
    p.randomSeed = CONF_SEED
    if AllChem.EmbedMolecule(mol, p) != 0:
        if AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=CONF_SEED) != 0:
            return None
    try:
        AllChem.MMFFOptimizeMolecule(mol, maxIters=300)
    except Exception:
        pass
    return mol


_FACTORY = ChemicalFeatures.BuildFeatureFactory(str(Path(RDConfig.RDDataDir) / "BaseFeatures.fdef"))


def ligand_pharmacophore(smiles: str) -> dict:
    mol = Chem.MolFromSmiles(smiles)
    fam = {k: 0 for k in ("Donor", "Acceptor", "Aromatic", "Hydrophobe",
                          "LumpedHydrophobe", "PosIonizable", "NegIonizable")}
    for f in _FACTORY.GetFeaturesForMol(mol):
        if f.GetFamily() in fam:
            fam[f.GetFamily()] += 1
    return {
        "ph_donor": fam["Donor"], "ph_acceptor": fam["Acceptor"], "ph_aromatic": fam["Aromatic"],
        "ph_hydrophobe": fam["Hydrophobe"] + fam["LumpedHydrophobe"],
        "ph_pos": fam["PosIonizable"], "ph_neg": fam["NegIonizable"],
        "d_hbd": Descriptors.NumHDonors(mol), "d_hba": Descriptors.NumHAcceptors(mol),
        "d_aromrings": Descriptors.NumAromaticRings(mol),
        "d_rotb": Descriptors.NumRotatableBonds(mol),
        "d_formalq": Chem.GetFormalCharge(mol),
    }


# ---------------------------------------------------------------------------
# F2 / F3 pocket descriptors (constant per target)
# ---------------------------------------------------------------------------
def pocket_descriptors(target: str) -> dict:
    atoms = pocket_atoms(target)
    P = _coords(atoms)
    b = BOX[target]
    spans = P.max(axis=0) - P.min(axis=0)
    don = sum(1 for a in atoms if a["name"] == "N" or (a["resname"], a["name"]) in DONOR_ATOMS)
    acc = sum(1 for a in atoms if a["name"] in ("O", "OXT") or (a["resname"], a["name"]) in ACCEPTOR_ATOMS)
    res = {(a["chain"], a["resseq"], a["resname"]) for a in atoms}
    arom = sum(1 for _, _, rn in res if rn in AROM_RES)
    hyd = sum(1 for _, _, rn in res if rn in HYDROPHOBIC_RES)
    pos = sum(1 for _, _, rn in res if rn in POS_RES)
    neg = sum(1 for _, _, rn in res if rn in NEG_RES)
    return {
        "pk_natoms": len(atoms), "pk_nres": len(res), "pk_rg": radius_of_gyration(P),
        "pk_span_x": float(spans[0]), "pk_span_y": float(spans[1]), "pk_span_z": float(spans[2]),
        "pk_span_max": float(spans.max()),
        "pk_cavity_vol": cavity_volume(P, b["center"], b["size"]),
        "pk_don_atoms": don, "pk_acc_atoms": acc,
        "pk_arom_res": arom, "pk_hydrophobe_res": hyd, "pk_pos_res": pos, "pk_neg_res": neg,
    }


def f2_row(smiles: str, pk: dict):
    mol = ligand_conformer(smiles)
    if mol is None:
        return None
    conf = mol.GetConformer()
    P = np.array([list(conf.GetAtomPosition(i)) for i in range(mol.GetNumAtoms())
                  if mol.GetAtomWithIdx(i).GetAtomicNum() > 1])
    try:
        vol = AllChem.ComputeMolVolume(mol, confId=0, gridSpacing=0.3)
    except Exception:
        vol = float("nan")
    rg = radius_of_gyration(P)
    maxd = float(cdist(P, P).max())
    box_vol = 20.0 ** 3
    lig = {
        "l_rg": rg, "l_asphericity": Descriptors3D.Asphericity(mol),
        "l_eccentricity": Descriptors3D.Eccentricity(mol),
        "l_spherocity": Descriptors3D.SpherocityIndex(mol),
        "l_npr1": Descriptors3D.NPR1(mol), "l_npr2": Descriptors3D.NPR2(mol),
        "l_pmi1": Descriptors3D.PMI1(mol), "l_pmi2": Descriptors3D.PMI2(mol), "l_pmi3": Descriptors3D.PMI3(mol),
        "l_isf": Descriptors3D.InertialShapeFactor(mol),
        "l_vol": vol, "l_heavy": int(P.shape[0]), "l_maxdist": maxd,
    }
    comp = {
        "c_vol_ratio": vol / pk["pk_cavity_vol"] if pk["pk_cavity_vol"] else float("nan"),
        "c_rg_ratio": rg / pk["pk_rg"] if pk["pk_rg"] else float("nan"),
        "c_len_ratio": maxd / pk["pk_span_max"] if pk["pk_span_max"] else float("nan"),
        "c_vol_boxfrac": vol / box_vol,
        "c_heavy_ratio": P.shape[0] / pk["pk_natoms"] if pk["pk_natoms"] else float("nan"),
    }
    return {**lig, **{k: pk[k] for k in pk}, **comp}


def f3_row(smiles: str, pk: dict):
    lg = ligand_pharmacophore(smiles)
    prod = {
        "x_hbd_acc": lg["d_hbd"] * pk["pk_acc_atoms"],
        "x_hba_don": lg["d_hba"] * pk["pk_don_atoms"],
        "x_arom": lg["ph_aromatic"] * pk["pk_arom_res"],
        "x_hydrophobe": lg["ph_hydrophobe"] * pk["pk_hydrophobe_res"],
        "x_pos_neg": lg["ph_pos"] * pk["pk_neg_res"],
        "x_neg_pos": lg["ph_neg"] * pk["pk_pos_res"],
    }
    pkcols = {k: pk[k] for k in ("pk_don_atoms", "pk_acc_atoms", "pk_arom_res",
                                 "pk_hydrophobe_res", "pk_pos_res", "pk_neg_res")}
    return {**lg, **pkcols, **prod}


# ---------------------------------------------------------------------------
# F4 -- pose-derived (ACE2 only). CEILING ESTIMATE. NOT a prescreen.
# ---------------------------------------------------------------------------
def extract_ace2_poses() -> dict:
    """MODEL-1 heavy-atom coords per (ligand smiles, seed) from the ephemeral
    ACE2 job store -> a committed artifact so F4 survives /tmp being cleared."""
    out_path = RUNS_DIR / "poses_ace2_v1.json"
    if out_path.exists():
        return json.loads(out_path.read_text())
    if not ACE2_JOB_DB.exists():
        raise FileNotFoundError(f"{ACE2_JOB_DB} gone and {out_path} not built -- F4 needs re-docking (out of scope)")
    con = sqlite3.connect(str(ACE2_JOB_DB)); con.row_factory = sqlite3.Row
    poses: dict = {}
    for r in con.execute("SELECT input, output FROM jobs WHERE status='completed'"):
        inp, outp = json.loads(r["input"]), json.loads(r["output"])
        atoms = parse_atoms(outp["docked_ligand_pdbqt"], models="first")
        coords = [[a["x"], a["y"], a["z"], a["elem"]] for a in atoms if a["elem"] != "H"]
        poses.setdefault(inp["smiles"], {})[str(inp["seed"])] = coords
    out_path.write_text(json.dumps(poses))
    return poses


def _sasa(P_self, radii_self, P_occ, radii_occ, n_sphere=64):
    """Shrake-Rupley-lite: fraction of a probe sphere around each self atom not
    buried by any atom (self or occluder). Sum of per-atom accessible area."""
    idx = np.arange(0, n_sphere, dtype=float) + 0.5
    phi = np.arccos(1 - 2 * idx / n_sphere)
    theta = np.pi * (1 + 5 ** 0.5) * idx
    sph = np.stack([np.sin(phi) * np.cos(theta), np.sin(phi) * np.sin(theta), np.cos(phi)], axis=1)
    probe = 1.4
    allP = np.vstack([P_self, P_occ]) if len(P_occ) else P_self
    allR = np.concatenate([radii_self, radii_occ]) if len(P_occ) else radii_self
    total = 0.0
    for i in range(len(P_self)):
        R = radii_self[i] + probe
        pts = P_self[i] + R * sph
        d = cdist(pts, allP)
        occl = d < (allR + probe)[None, :]
        occl[:, i] = False
        acc = (~occl.any(axis=1)).mean()
        total += acc * 4 * np.pi * R ** 2
    return total


def f4_rows(poses: dict, smiles_by_id: dict) -> dict:
    rec_atoms = [a for a in parse_atoms((TARGETS / "ace2_receptor.pdbqt").read_text()) if a["elem"] != "H"]
    recP = _coords(rec_atoms)
    # Zn + catalytic HEXXH residues from raw 1R42
    pdb = parse_atoms((TARGETS / "1R42.pdb").read_text())
    znP = _coords([a for a in pdb if a["elem"] == "ZN"])
    cat = _coords([a for a in pdb if a["resseq"] in ("374", "378", "402")
                   and a["resname"] in ("HIS", "GLU") and a["elem"] != "H"])
    cx = np.array(BOX["ace2"]["center"])
    rows: dict = {}
    for lid, smi in smiles_by_id.items():
        by_seed = poses.get(smi)
        if not by_seed:
            rows[lid] = None
            continue
        vals = []
        for seed, coords in by_seed.items():
            L = np.array([c[:3] for c in coords], dtype=float)
            Lr = np.array([VDW.get(str(c[3]).upper(), 1.7) for c in coords])
            near = recP[cdist(cx[None], recP)[0] < 22]           # receptor atoms near the box
            nearR = np.array([VDW.get(rec_atoms[j]["elem"], 1.7)
                              for j in np.where(cdist(cx[None], recP)[0] < 22)[0]])
            D = cdist(L, near)
            sasa_alone = _sasa(L, Lr, np.empty((0, 3)), np.empty(0))
            sasa_cx = _sasa(L, Lr, near, nearR)
            vals.append([
                float((D < 4.0).sum()),
                float((D < 3.5).sum()),
                float((D.min(axis=1) < 4.0).sum()),
                float(1 - sasa_cx / sasa_alone) if sasa_alone else 0.0,
                float(cdist(L, znP).min()) if len(znP) else float("nan"),
                float(cdist(L, cat).min()) if len(cat) else float("nan"),
                radius_of_gyration(L),
                float(np.linalg.norm(L.mean(axis=0) - cx)),
                float((np.abs(L - cx) > 10.0).any(axis=1).sum()),
            ])
        m = np.array(vals).mean(axis=0)
        rows[lid] = dict(zip(
            ["i_contacts_4A", "i_contacts_3.5A", "i_ligatoms_in_contact", "i_buried_frac",
             "i_min_zn_dist", "i_min_cat_dist", "i_pose_rg", "i_centroid_offset", "i_atoms_outside_box"],
            [float(v) for v in m]))
    return rows


# ---------------------------------------------------------------------------
def build(target: str) -> dict:
    set_id, csv_path = SETS[target]
    cs = load_candidate_set(csv_path=csv_path, set_id=set_id)
    cached = json.loads((RUNS_DIR / f"features_{set_id}.json").read_text())["features"]
    pk = pocket_descriptors(target)
    print(f"[{target}] pocket: {pk['pk_natoms']} atoms, {pk['pk_nres']} residues, "
          f"cavity_vol~{pk['pk_cavity_vol']:.0f} A^3, don/acc atoms {pk['pk_don_atoms']}/{pk['pk_acc_atoms']}")

    rows: dict = {}
    fails = {"F2": [], "F3": []}
    for c in cs.candidates:
        lid, smi = c.ligand_id, c.smiles
        f1 = np.concatenate([morgan_bits(smi),
                             [cached[lid]["descriptors"][k] for k in DESCRIPTOR_NAMES]]).tolist()
        f2 = f2_row(smi, pk)
        f3 = f3_row(smi, pk)
        if f2 is None:
            fails["F2"].append(lid)
        rows[lid] = {"F1": f1,
                     "F2": [f2[k] for k in sorted(f2)] if f2 else None,
                     "F3": [f3[k] for k in sorted(f3)] if f3 else None,
                     "F4": None}

    f2_cols = sorted(f2_row(cs.candidates[0].smiles, pk).keys())
    f3_cols = sorted(f3_row(cs.candidates[0].smiles, pk).keys())
    f1_cols = [f"ecfp_{i}" for i in range(1024)] + list(DESCRIPTOR_NAMES)
    f4_cols = None

    if target == "ace2":
        poses = extract_ace2_poses()
        smiles_by_id = {c.ligand_id: c.smiles for c in cs.candidates}
        f4 = f4_rows(poses, smiles_by_id)
        n_f4 = sum(1 for v in f4.values() if v is not None)
        print(f"[ace2] F4 pose features computed for {n_f4}/45 (6 boronic acids never docked)")
        f4_cols = sorted(next(v for v in f4.values() if v is not None).keys())
        for lid in rows:
            rows[lid]["F4"] = [f4[lid][k] for k in f4_cols] if f4.get(lid) else None

    payload = {
        "set_id": set_id, "target": target,
        "columns": {"F1": f1_cols, "F2": f2_cols, "F3": f3_cols, "F4": f4_cols},
        "prescreen_usable": {"F1": True, "F2": True, "F3": True, "F4": False},
        "pocket_descriptors": pk,
        "computable": {
            "F1": f"{len(rows)}/{len(rows)}",
            "F2": f"{sum(1 for r in rows.values() if r['F2'])}/{len(rows)}",
            "F3": f"{sum(1 for r in rows.values() if r['F3'])}/{len(rows)}",
            "F4": (f"{sum(1 for r in rows.values() if r['F4'])}/{len(rows)}" if target == "ace2" else "n/a (cox2 poses not retained)"),
        },
        "failures": fails,
        "rows": rows,
    }
    blob = json.dumps({k: payload["rows"][k] for k in sorted(payload["rows"])}, sort_keys=True)
    payload["content_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    out = RUNS_DIR / f"features_receptor_{set_id}.json"
    out.write_text(json.dumps(payload, indent=2))
    print(f"[{target}] wrote {out}  sha={payload['content_sha256'][:16]}  "
          f"computable F2={payload['computable']['F2']} F3={payload['computable']['F3']} F4={payload['computable']['F4']}")
    return payload


def main() -> int:
    for t in ("cox2", "ace2"):
        build(t)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
