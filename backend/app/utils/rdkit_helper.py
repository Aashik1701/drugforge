"""
RDKit helper utilities for SMILES validation and feature extraction.

All molecule processing is wrapped in try/except to handle
invalid SMILES gracefully.
"""

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, Descriptors


def validate_smiles(smiles: str) -> Chem.Mol:
    """
    Parse and sanitize a SMILES string into an RDKit Mol object.

    Args:
        smiles: SMILES string.

    Returns:
        Sanitized RDKit Mol object.

    Raises:
        ValueError: If the SMILES string is invalid or cannot be sanitized.
    """
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise ValueError(f"Invalid SMILES string: {smiles}")
        Chem.SanitizeMol(mol)
        return mol
    except Exception as e:
        raise ValueError(f"Error processing molecule: {str(e)}")


def extract_features(smiles: str, radius: int = 2, n_bits: int = 1024) -> np.ndarray:
    """
    Convert a SMILES string into a Morgan fingerprint (ECFP) vector.

    Uses the same parameters as model training:
    radius=2, nBits=1024 (ECFP4 fingerprint).

    Args:
        smiles: SMILES string.
        radius: Morgan fingerprint radius (default 2 = ECFP4).
        n_bits: Length of the bit vector (default 1024).

    Returns:
        numpy array of shape (1, n_bits) with Morgan fingerprint bits.

    Raises:
        ValueError: If the SMILES string is invalid.
    """
    mol = validate_smiles(smiles)

    fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
    arr = np.zeros((1,), dtype=np.int8)
    arr = np.array(fp, dtype=np.float64).reshape(1, -1)

    return arr


def extract_descriptors(smiles: str) -> np.ndarray:
    """
    Calculate 10 molecular descriptors for a SMILES string.

    Useful for models trained on physicochemical descriptors
    rather than fingerprints.

    Args:
        smiles: SMILES string.

    Returns:
        numpy array of shape (1, 10) with molecular descriptors.

    Raises:
        ValueError: If the SMILES string is invalid.
    """
    mol = validate_smiles(smiles)

    features = [
        Descriptors.MolWt(mol),
        Descriptors.MolLogP(mol),
        Descriptors.NumHDonors(mol),
        Descriptors.NumHAcceptors(mol),
        Descriptors.TPSA(mol),
        Descriptors.NumRotatableBonds(mol),
        Descriptors.NumAromaticRings(mol),
        Descriptors.NumSaturatedRings(mol),
        Descriptors.RingCount(mol),
        Descriptors.FractionCSP3(mol),
    ]

    return np.array(features, dtype=np.float64).reshape(1, -1)


def get_molecular_weight(smiles: str) -> float:
    """
    Calculate molecular weight from a SMILES string.

    Args:
        smiles: SMILES string.

    Returns:
        Molecular weight in g/mol.

    Raises:
        ValueError: If the SMILES string is invalid.
    """
    mol = validate_smiles(smiles)
    return round(Descriptors.MolWt(mol), 2)
