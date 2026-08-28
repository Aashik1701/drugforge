"""
DrugForge — Unified Model Training Script
==========================================
Trains all ML models from the notebook pipelines.
All models use Morgan Fingerprints (ECFP4, radius=2, nBits=1024)
and RandomForest (Classifier or Regressor).

Usage:
    python train_all_models.py          # Train all models
    python train_all_models.py bbbp     # Train specific model
    python train_all_models.py cyp3a4 toxicity  # Train multiple
"""

import os
import sys
import time
import pickle
import warnings
import numpy as np
import pandas as pd
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.metrics import (
    roc_auc_score,
    accuracy_score,
    mean_squared_error,
    mean_absolute_error,
    r2_score,
)

warnings.filterwarnings("ignore", category=UserWarning)

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
ML_DIR = BASE_DIR.parent
ADMET_DATA = ML_DIR / "datasets" / "admet"
TARGET_DATA = ML_DIR / "datasets" / "target_identification"
OUTPUT_DIR = ML_DIR / "models"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ─── Feature Extraction ─────────────────────────────────────────────────────
def smiles_to_fingerprint(smiles: str, radius: int = 2, n_bits: int = 1024) -> np.ndarray | None:
    """Convert a SMILES string to a Morgan fingerprint bit vector."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        fp = AllChem.GetMorganFingerprintAsBitVect(mol, radius, nBits=n_bits)
        arr = np.zeros((n_bits,), dtype=np.int8)
        DataStructs.ConvertToNumpyArray(fp, arr)
        return arr
    except Exception:
        return None


def featurize_dataset(
    df: pd.DataFrame, smiles_col: str, label_col: str
) -> tuple[np.ndarray, np.ndarray]:
    """Convert a DataFrame with SMILES + labels into feature matrix and label array."""
    features, labels = [], []
    skipped = 0
    for _, row in df.iterrows():
        fp = smiles_to_fingerprint(str(row[smiles_col]))
        if fp is not None:
            features.append(fp)
            labels.append(row[label_col])
        else:
            skipped += 1
    if skipped > 0:
        print(f"  ⚠️  Skipped {skipped} invalid SMILES ({skipped}/{skipped + len(features)})")
    return np.array(features), np.array(labels)


# ─── Training Functions ─────────────────────────────────────────────────────

def train_bbbp() -> dict:
    """Train BBBP (Blood-Brain Barrier Penetration) classifier."""
    print("\n🧠 Training BBBP model...")
    df = pd.read_csv(ADMET_DATA / "bbb_martins.tab", sep="\t")
    print(f"  Dataset: {len(df)} compounds")

    X, y = featurize_dataset(df, smiles_col="Drug", label_col="Y")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(n_estimators=150, random_state=44, n_jobs=-1)
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0

    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, model.predict(X_test))

    out_path = OUTPUT_DIR / "bbbp_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)

    print(f"  ✅ AUC={auc:.4f}  Accuracy={acc:.4f}  Time={train_time:.1f}s")
    print(f"  📁 Saved: {out_path}")
    return {"model": "bbbp", "auc": auc, "accuracy": acc, "path": str(out_path)}


def train_cyp3a4() -> dict:
    """Train CYP3A4 Inhibition classifier."""
    print("\n💊 Training CYP3A4 model...")
    df = pd.read_csv(ADMET_DATA / "cyp3a4_veith.csv")
    print(f"  Dataset: {len(df)} compounds")

    X, y = featurize_dataset(df, smiles_col="Drug", label_col="Y")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(n_estimators=150, random_state=44, n_jobs=-1)
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0

    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, model.predict(X_test))

    out_path = OUTPUT_DIR / "cyp3a4_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)

    print(f"  ✅ AUC={auc:.4f}  Accuracy={acc:.4f}  Time={train_time:.1f}s")
    print(f"  📁 Saved: {out_path}")
    return {"model": "cyp3a4", "auc": auc, "accuracy": acc, "path": str(out_path)}


def train_toxicity() -> dict:
    """Train Toxicity (hERG channel inhibition) classifier."""
    print("\n☠️  Training Toxicity model...")
    df = pd.read_csv(ADMET_DATA / "herg_karim.tab", sep="\t")
    print(f"  Dataset: {len(df)} compounds")

    X, y = featurize_dataset(df, smiles_col="Drug", label_col="Y")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    model = RandomForestClassifier(n_estimators=150, random_state=44, n_jobs=-1)
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0

    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, model.predict(X_test))

    out_path = OUTPUT_DIR / "toxicity_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)

    print(f"  ✅ AUC={auc:.4f}  Accuracy={acc:.4f}  Time={train_time:.1f}s")
    print(f"  📁 Saved: {out_path}")
    return {"model": "toxicity", "auc": auc, "accuracy": acc, "path": str(out_path)}


def train_half_life() -> dict:
    """Train Half-Life (Excretion) regressor."""
    print("\n⏱️  Training Half-Life model...")
    df = pd.read_csv(ADMET_DATA / "half_life_obach.csv")
    print(f"  Dataset: {len(df)} compounds")

    X, y = featurize_dataset(df, smiles_col="X", label_col="Y")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    model = RandomForestRegressor(n_estimators=150, random_state=44, n_jobs=-1)
    t0 = time.time()
    model.fit(X_train, y_train)
    train_time = time.time() - t0

    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)

    out_path = OUTPUT_DIR / "half_life_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)

    print(f"  ✅ RMSE={rmse:.4f}  MAE={mae:.4f}  R²={r2:.4f}  Time={train_time:.1f}s")
    print(f"  📁 Saved: {out_path}")
    return {"model": "half_life", "rmse": rmse, "mae": mae, "r2": r2, "path": str(out_path)}


def _train_target_id(
    name: str, csv_file: str, emoji: str
) -> dict:
    """
    Train a Target Identification classifier (ACE2, COX2).
    Uses GridSearchCV for hyperparameter tuning.
    Labels derived from IC50: active (≤ median) = 1, inactive = 0.
    """
    print(f"\n{emoji} Training {name.upper()} model...")
    df = pd.read_csv(TARGET_DATA / csv_file, sep=";")
    print(f"  Raw dataset: {len(df)} rows")

    # Filter for activity types with numeric values
    df["Standard Value"] = pd.to_numeric(df["Standard Value"], errors="coerce")
    df = df.dropna(subset=["Standard Value", "Smiles"])
    # Keep only rows with exact measurement (=)
    df = df[df["Standard Relation"].str.contains("=", na=False)]
    # Prefer IC50/Ki (binding affinity), fall back to all types if too few
    binding_df = df[df["Standard Type"].isin(["IC50", "Ki"])]
    if len(binding_df) >= 50:
        df = binding_df
        print(f"  After filtering (IC50+Ki, numeric, '='): {len(df)} compounds")
    else:
        print(f"  After filtering (all types, numeric, '='): {len(df)} compounds")

    if len(df) < 50:
        print(f"  ❌ Not enough data ({len(df)} < 50). Skipping.")
        return {"model": name, "error": "insufficient data"}

    # Derive binary class: active if IC50 ≤ median
    median_ic50 = df["Standard Value"].median()
    df["class"] = (df["Standard Value"] <= median_ic50).astype(int)
    print(f"  Median IC50: {median_ic50:.2f} nM → {df['class'].sum()} active / {(~df['class'].astype(bool)).sum()} inactive")

    X, y = featurize_dataset(df, smiles_col="Smiles", label_col="class")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # GridSearchCV (matching notebook)
    param_grid = {
        "n_estimators": [100, 200],
        "max_depth": [None, 10, 20],
        "min_samples_split": [2, 5],
        "min_samples_leaf": [1, 2],
    }
    grid = GridSearchCV(
        RandomForestClassifier(random_state=42, n_jobs=-1),
        param_grid,
        cv=3,
        scoring="accuracy",
        n_jobs=-1,
        verbose=0,
    )
    t0 = time.time()
    grid.fit(X_train, y_train)
    train_time = time.time() - t0
    model = grid.best_estimator_

    y_prob = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, y_prob)
    acc = accuracy_score(y_test, model.predict(X_test))

    out_path = OUTPUT_DIR / f"{name}_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump(model, f)

    print(f"  Best params: {grid.best_params_}")
    print(f"  ✅ AUC={auc:.4f}  Accuracy={acc:.4f}  Time={train_time:.1f}s")
    print(f"  📁 Saved: {out_path}")
    return {"model": name, "auc": auc, "accuracy": acc, "best_params": grid.best_params_, "path": str(out_path)}


def train_ace2() -> dict:
    """Train ACE2 target identification classifier."""
    return _train_target_id("ace2", "ACE-2.csv", "🎯")


def train_cox2() -> dict:
    """Train COX2 target identification classifier."""
    return _train_target_id("cox2", "COX-2.csv", "🔬")


# ─── HepG2 — Missing dataset (ptd.csv not in repo) ─────────────────────────
def train_hepg2() -> dict:
    """Train HepG2 hepatotoxicity classifier (requires ptd.csv)."""
    ptd_path = TARGET_DATA / "ptd.csv"
    if not ptd_path.exists():
        print("\n🔴 HepG2: Dataset 'ptd.csv' not found — skipping.")
        print(f"  Expected at: {ptd_path}")
        return {"model": "hepg2", "error": "dataset ptd.csv not found"}
    return _train_target_id("hepg2", "ptd.csv", "🧫")


# ─── Main ────────────────────────────────────────────────────────────────────
TRAINERS = {
    "bbbp": train_bbbp,
    "cyp3a4": train_cyp3a4,
    "toxicity": train_toxicity,
    "half_life": train_half_life,
    "ace2": train_ace2,
    "cox2": train_cox2,
    "hepg2": train_hepg2,
}


def main():
    """Run training for specified models (or all if none specified)."""
    if len(sys.argv) > 1:
        names = [n.lower().strip() for n in sys.argv[1:]]
    else:
        names = list(TRAINERS.keys())

    print("=" * 60)
    print("🚀 DrugForge Model Training")
    print(f"   Models to train: {', '.join(names)}")
    print("=" * 60)

    results = []
    for name in names:
        if name not in TRAINERS:
            print(f"\n❌ Unknown model: {name}. Available: {list(TRAINERS.keys())}")
            continue
        try:
            result = TRAINERS[name]()
            results.append(result)
        except Exception as e:
            print(f"\n❌ {name} training failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({"model": name, "error": str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("📊 Training Summary")
    print("=" * 60)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['model']}: FAILED — {r['error']}")
        elif "auc" in r:
            print(f"  ✅ {r['model']}: AUC={r['auc']:.4f}  Acc={r['accuracy']:.4f}")
        elif "rmse" in r:
            print(f"  ✅ {r['model']}: RMSE={r['rmse']:.4f}  R²={r['r2']:.4f}")

    success = sum(1 for r in results if "error" not in r)
    total = len(results)
    print(f"\n  {success}/{total} models trained successfully")

    if success > 0:
        print(f"\n  Models saved to: {OUTPUT_DIR}")
        print("  Next: promote to production by copying to backend/models/:")
        print(f"    cp {OUTPUT_DIR}/*_model.pkl ../../backend/models/")


if __name__ == "__main__":
    main()
