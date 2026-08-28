"""
The ONE ranking function both paths use. Baseline and funnel must rank docked
candidates identically — the only difference between the paths is WHICH
candidates were docked, never HOW they are scored or ordered.

Rank on MEAN best-affinity across the seed replicas (ascending: most negative
= rank 1). Candidates whose means are within TIE_EPSILON kcal/mol — or within
their pooled seed stdev — share a rank and carry a `tie_group` label, so known
near-ties (celecoxib/rofecoxib ~0.007; ibuprofen/acetaminophen ~0.063) are
reported as ties, not false-precision ranks.
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


def _rows_from_dock_results(results: list[DockResult]) -> list[_Row]:
    return [
        _Row(r.ligand_id, r.smiles, r.mean_affinity, r.seed_stdev, r.per_seed_map, r.wall_s_total)
        for r in results
    ]


def rank_docked(results: list[DockResult]) -> list[RankedEntry]:
    """Return RankedEntry list, best (most negative mean) first, with tie groups."""
    rows = _rows_from_dock_results(results)
    # Failed docks (mean is None) sink to the bottom, order stable by ligand_id.
    ok = sorted([r for r in rows if r.mean is not None], key=lambda r: r.mean)
    bad = sorted([r for r in rows if r.mean is None], key=lambda r: r.ligand_id)

    entries: list[RankedEntry] = []
    rank = 0
    tie_counter = 0
    i = 0
    while i < len(ok):
        # Grow a tie cluster starting at i.
        cluster = [ok[i]]
        j = i + 1
        while j < len(ok):
            prev = cluster[-1]
            cur = ok[j]
            pooled = (prev.stdev or 0.0) + (cur.stdev or 0.0)
            if (cur.mean - prev.mean) <= max(TIE_EPSILON, pooled):
                cluster.append(cur)
                j += 1
            else:
                break
        rank += 1
        tie_group = None
        if len(cluster) > 1:
            tie_counter += 1
            tie_group = f"tie{tie_counter}"
        for r in cluster:
            entries.append(RankedEntry(
                rank=rank, ligand_id=r.ligand_id, smiles=r.smiles,
                mean_affinity=round(r.mean, 4),
                seed_stdev=round(r.stdev, 4) if r.stdev is not None else None,
                per_seed_affinities={k: (round(v, 4) if v is not None else None)
                                     for k, v in r.per_seed.items()},
                dock_wall_s=round(r.wall_s, 2),
                tie_group=tie_group,
            ))
        i = j

    for r in bad:
        rank += 1
        entries.append(RankedEntry(
            rank=rank, ligand_id=r.ligand_id, smiles=r.smiles,
            mean_affinity=None, seed_stdev=None,
            per_seed_affinities={k: (round(v, 4) if v is not None else None)
                                 for k, v in r.per_seed.items()},
            dock_wall_s=round(r.wall_s, 2), tie_group=None,
        ))
    return entries
