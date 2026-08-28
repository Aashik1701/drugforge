# `runs/` — funnel / baseline run records

Schema: `backend/app/funnel/schema.py` (`RunRecord`, version `1.0.0`).
See `docs/development/funnel.md`.

| file | what |
|---|---|
| `baseline_cox2_v1.json` | **reference artifact.** The brute-force path: every candidate in `cox2_v1` docked (4 seeds), ranked on mean affinity. Expensive to regenerate (~M×4 Vina runs). A reviewer replays the comparison from this file instead of re-docking. Regenerate with `python -m funnel.baseline` or `scripts/run_funnel_eval.sh --with-baseline`. |
| `funnel_cox2_v1.json` | the funnel path: SMILES→drug-likeness→toxicity filter, multi-objective prescreen, dock only the top-5. Cheap to regenerate: `python -m funnel.funnel`. |

Both are platform- and Vina-version-stamped in the record. Docked affinities
shift ~0.01 kcal/mol between CPU architectures and more between Vina versions —
regenerate the baseline if either changes.

`_*.json` here are scratch/smoke outputs and are git-ignored.
