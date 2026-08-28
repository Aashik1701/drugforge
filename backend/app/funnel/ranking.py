"""
The ONE ranking function both paths use. Baseline and funnel rank docked
candidates identically — the only difference between the paths is WHICH
candidates were docked, never HOW they are ordered.

Rank on MEAN best-affinity across the seed replicas (ascending: most negative
= rank 1). Ranks are sequential (1..N) — never collapsed — so there is no
false precision AND no transitive-chaining pathology. Separately, entries that
are statistically indistinguishable get a shared `tie_group` label: an entry
joins a group while it is within max(TIE_EPSILON, pooled seed stdev) of the
group's FIRST member (comparing to the group anchor, not the previous entry,
bounds a group's span to ~TIE_EPSILON and stops long chains). Known near-ties
— celecoxib/rofecoxib (~0.007) and ibuprofen/acetaminophen (~0.063) — land in
the same group; a 0.65 kcal/mol spread never does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from funnel.fabric import DockResult
from funnel.schema import RankedEntry

TIE_EPSILON = 0.10  # kcal/mol


@dataclass
class _Row:
    ligand_id: str
    smiles: str
    mean: Optional[float]
    stdev: Optional[float]
    per_seed: dict[str, Optional[float]]
    wall_s: float


def _assign(rows: list[_Row]) -> list[RankedEntry]:
    ok = sorted([r for r in rows if r.mean is not None], key=lambda r: r.mean)
    bad = sorted([r for r in rows if r.mean is None], key=lambda r: r.ligand_id)

    # Non-chaining tie groups: an entry joins the current group only if it is
    # within tolerance of the group's ANCHOR (first member).
    group_of: dict[int, Optional[str]] = {}
    tie_counter = 0
    anchor_idx = 0
    for i in range(len(ok)):
        if i == anchor_idx:
            group_of[i] = None
            continue
        anchor = ok[anchor_idx]
        cur = ok[i]
        tol = max(TIE_EPSILON, (anchor.stdev or 0.0) + (cur.stdev or 0.0))
        if (cur.mean - anchor.mean) <= tol:
            if group_of[anchor_idx] is None:
                tie_counter += 1
                group_of[anchor_idx] = f"tie{tie_counter}"
            group_of[i] = group_of[anchor_idx]
        else:
            anchor_idx = i
            group_of[i] = None

    entries: list[RankedEntry] = []
    for i, r in enumerate(ok, 1):
        entries.append(RankedEntry(
            rank=i, ligand_id=r.ligand_id, smiles=r.smiles,
            mean_affinity=round(r.mean, 4),
            seed_stdev=round(r.stdev, 4) if r.stdev is not None else None,
            per_seed_affinities={k: (round(v, 4) if v is not None else None)
                                 for k, v in r.per_seed.items()},
            dock_wall_s=round(r.wall_s, 2),
            tie_group=group_of[i - 1],
        ))
    for j, r in enumerate(bad, len(ok) + 1):
        entries.append(RankedEntry(
            rank=j, ligand_id=r.ligand_id, smiles=r.smiles,
            mean_affinity=None, seed_stdev=None,
            per_seed_affinities={k: (round(v, 4) if v is not None else None)
                                 for k, v in r.per_seed.items()},
            dock_wall_s=round(r.wall_s, 2), tie_group=None,
        ))
    return entries


def rank_docked(results: list[DockResult]) -> list[RankedEntry]:
    rows = [
        _Row(r.ligand_id, r.smiles, r.mean_affinity, r.seed_stdev, r.per_seed_map, r.wall_s_total)
        for r in results
    ]
    return _assign(rows)


def rerank_entries(entries: list[RankedEntry]) -> list[RankedEntry]:
    """Re-run the ranking from stored per-seed affinities (no re-docking)."""
    rows: list[_Row] = []
    for e in entries:
        vals = [v for v in e.per_seed_affinities.values() if v is not None]
        mean = sum(vals) / len(vals) if vals else None
        if len(vals) >= 2:
            m = mean
            sd = (sum((x - m) ** 2 for x in vals) / len(vals)) ** 0.5
        else:
            sd = 0.0 if vals else None
        rows.append(_Row(e.ligand_id, e.smiles, mean, sd, dict(e.per_seed_affinities),
                         e.dock_wall_s or 0.0))
    return _assign(rows)
