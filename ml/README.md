# ML Training & Research

This directory holds everything used to **produce** the models that run in
`backend/models/`. Nothing here is imported by the production API — it's the
offline training side of the pipeline. Promoting a newly trained model to
production is a manual step (see `training/train_all_models.py`'s final
printout).

## Layout

```
ml/
├── training/
│   ├── train_all_models.py     # Unified trainer for the ADMET + target-ID models
│   └── notebooks/               # Original exploratory notebooks per model family
│       ├── admet/
│       ├── target_identification/
│       └── binding/
├── datasets/
│   ├── admet/                   # Used by train_all_models.py
│   ├── target_identification/   # Used by train_all_models.py
│   └── extended_admet/          # NOT currently used by any training script (see below)
├── models/
│   └── binding_model_notebook_output.pkl
└── requirements.txt
```

## Datasets

| Dataset | Format | Used by | Runtime dependency? |
|---|---|---|---|
| `datasets/admet/bbb_martins.tab` | TSV | `train_bbbp()` | No — training only |
| `datasets/admet/cyp3a4_veith.csv` | CSV | `train_cyp3a4()` | No — training only |
| `datasets/admet/half_life_obach.csv` | CSV | `train_half_life()` | No — training only |
| `datasets/admet/herg_karim.tab` | TSV | `train_toxicity()` | No — training only |
| `datasets/admet/solubility_aqsoldb.tab` | TSV | Solubility notebook (not yet wired into `train_all_models.py`) | No |
| `datasets/target_identification/ACE-2.csv` | CSV (`;`-sep) | `train_ace2()` | No — training only |
| `datasets/target_identification/COX-2.csv` | CSV (`;`-sep) | `train_cox2()` | No — training only |
| `datasets/extended_admet/*.tab` (bindingdb_kd, caco2_wang, lipophilicity_astrazeneca, ppbr_az, tox21, vdss_lombardo) | TSV, TDC-style | Nothing yet | No — moved here from `backend/data/`, where they sat unused by any runtime code. Reserved for future ADMET model expansion. |

None of these are redistribution-restricted beyond their original public sources (TDC / ChEMBL-derived benchmark sets); no license file accompanied them in the original checkout, so verify upstream terms before redistributing outside this project.

## Models

| Model | Status |
|---|---|
| `bbbp`, `cyp3a4`, `toxicity` (herg-based), `half_life`, `ace2`, `cox2` | Reproducible from this directory via `python training/train_all_models.py <name>`. Their production copies live in `backend/models/`. |
| `hepg2` | **Not reproducible from this repo.** `train_all_models.py` expects `datasets/target_identification/ptd.csv`, which was never checked in. `backend/models/hepg2_model.pkl` exists and is loaded in production, but its training data/notebook is not present here. |
| `solubility` | Trained from `Notebook/Solubility.ipynb`, not yet ported into `train_all_models.py`. |
| `binding_score` (production, `backend/models/binding_model.pkl`, 64MB) | **Not reproducible from this repo either.** `models/binding_model_notebook_output.pkl` (9.9MB) is `Binding_Score.ipynb`'s last saved output, but it is a *different, smaller* file than what's actually running in production — the production model was retrained or extended after this notebook copy was saved, and no script here reproduces that version. Kept for reference only; do not assume it's interchangeable with the production model. |

Byte-identical duplicate `.pkl` files that used to live alongside these notebooks (`ADMET Properties/models/*.pkl`) were removed — `backend/models/` is the single authoritative copy of every runtime model.

## Research

Notebook-based experiments that aren't part of the model-training pipeline live in `research/`, not here:
- `research/docking_experiments/` — standalone AutoDock Vina notebook + scratch ligand files, separate from the production docking path (`backend/routers/dock.py`, `backend/bin/vina`).
- `research/papers/` — reference PDFs.
- `research/archive/legacy-flask-backend/` — the pre-FastAPI backend and its deployment tooling, kept for history.
