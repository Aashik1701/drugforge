"""
Evaluation harness — diff two run records and print the headline comparison.

  cd backend/app && ../venv/bin/python -m funnel.evaluate \
      --baseline ../../runs/baseline_cox2_v1.json \
      --funnel   ../../runs/funnel_cox2_v1.json

The false-negative count (a candidate the funnel FILTERED OUT that the baseline
ranked in its top-5) is the honest failure metric and is printed first.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from funnel.schema import RunRecord

TOP_K = 5


def _rank_of(rec: RunRecord) -> dict[str, int]:
    return {e.ligand_id: e.rank for e in rec.results}


def _top_k_ligands(rec: RunRecord, k: int = TOP_K) -> list[str]:
    """Ligands at rank <= k (strict — the headline denominator)."""
    return [e.ligand_id for e in rec.results if e.rank is not None and e.rank <= k]


def _tie_straddle(rec: RunRecord, k: int = TOP_K) -> list[str]:
    """Ligands at rank > k that share a tie_group with a rank <= k entry —
    statistically indistinguishable from a top-k hit, reported alongside."""
    top_groups = {e.tie_group for e in rec.results
                  if e.tie_group and e.rank and e.rank <= k}
    return [e.ligand_id for e in rec.results
            if e.tie_group in top_groups and e.rank and e.rank > k]


def _docked_ligands(rec: RunRecord) -> set[str]:
    # An entry with any non-null per-seed affinity was actually docked.
    out = set()
    for e in rec.results:
        if e.mean_affinity is not None or any(v is not None for v in e.per_seed_affinities.values()):
            out.add(e.ligand_id)
    return out


def _spearman(pairs: list[tuple[float, float]]) -> float | None:
    n = len(pairs)
    if n < 2:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]

    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    d2 = sum((a - b) ** 2 for a, b in zip(rx, ry))
    return 1 - (6 * d2) / (n * (n * n - 1))


def _fmt_entry(e) -> str:
    m = f"{e.mean_affinity:+.3f}" if e.mean_affinity is not None else "  FAIL"
    sd = f"{e.seed_stdev:.3f}" if e.seed_stdev is not None else "  -  "
    tie = f" [{e.tie_group}]" if e.tie_group else ""
    return f"#{e.rank:<2} {e.ligand_id:<14} {m} kcal/mol  (sd {sd}){tie}"


def compare(baseline: RunRecord, funnel: RunRecord) -> None:
    assert baseline.candidate_set_id == funnel.candidate_set_id, "different candidate sets"

    b_rank = _rank_of(baseline)
    f_rank = _rank_of(funnel)
    b_top = _top_k_ligands(baseline)
    b_straddle = _tie_straddle(baseline)
    f_docked = _docked_ligands(funnel)
    b_docked = _docked_ligands(baseline)
    filtered_ids = {f.ligand_id: f for f in funnel.filtered_out}

    # --- false negatives: baseline top-5 that the funnel FILTERED OUT (never docked)
    false_negatives = [lid for lid in b_top if lid in filtered_ids]
    # --- selection misses: baseline top-5 that survived the funnel filter but were
    #     not in its top-N (docked neither) — softer miss
    selection_misses = [lid for lid in b_top if lid not in f_docked and lid not in filtered_ids]

    overlap = [lid for lid in b_top if lid in f_docked]

    # tie-credited recall@5 — same metric funnel.sweep uses for policy selection,
    # so the live result can be checked against the offline prediction.
    tie_groups: dict[str, set] = {}
    for e in baseline.results:
        if e.tie_group:
            tie_groups.setdefault(e.tie_group, set()).add(e.ligand_id)
    def _partners(lid):
        e = next((x for x in baseline.results if x.ligand_id == lid), None)
        return (tie_groups.get(e.tie_group, set()) - {lid}) if (e and e.tie_group) else set()
    recall5_hits = [m for m in b_top if m in f_docked or (_partners(m) & f_docked)]
    recall5 = len(recall5_hits)

    common = sorted(f_docked & b_docked)
    sp_pairs = [(b_rank[l], f_rank[l]) for l in common if l in b_rank and l in f_rank]
    spearman = _spearman(sp_pairs)

    b1 = next((e.ligand_id for e in baseline.results if e.rank == 1), None)
    f1 = next((e.ligand_id for e in funnel.results if e.rank == 1), None)

    line = "=" * 74
    print(line)
    print("  FUNNEL vs BASELINE  —  candidate set:", baseline.candidate_set_id,
          f"(N={baseline.candidate_set_size})")
    print(line)

    print("\n>>> FALSE NEGATIVES (funnel filtered out a baseline top-5 hit) <<<")
    if false_negatives:
        for lid in false_negatives:
            f = filtered_ids[lid]
            be = next(e for e in baseline.results if e.ligand_id == lid)
            print(f"    !! {lid}  baseline rank #{be.rank} ({be.mean_affinity:+.3f})  "
                  f"— dropped at stage '{f.stage}': {f.reason}")
        print(f"    false-negative count: {len(false_negatives)} / {len(b_top)} baseline top-5")
    else:
        print("    0  — the funnel filtered out none of the baseline's top-5")
    if selection_misses:
        print(f"    (plus {len(selection_misses)} 'selection miss(es)': survived the filter "
              f"but not picked for docking: {selection_misses})")

    print("\n--- headline table ---")
    rows = [
        ("docking jobs submitted", baseline.total_docking_jobs_submitted, funnel.total_docking_jobs_submitted),
        ("candidates docked", len(b_docked), len(f_docked)),
        ("docking wall-clock (s)", round(baseline.total_docking_wall_s, 1), round(funnel.total_docking_wall_s, 1)),
        ("total run wall-clock (s)", round(baseline.total_run_wall_s, 1), round(funnel.total_run_wall_s, 1)),
    ]
    print(f"    {'metric':<28} {'baseline':>12} {'funnel':>12}")
    for name, b, f in rows:
        print(f"    {name:<28} {b:>12} {f:>12}")
    if baseline.total_docking_wall_s and funnel.total_docking_wall_s:
        sx = baseline.total_docking_wall_s / funnel.total_docking_wall_s
        print(f"    {'docking speedup (x)':<28} {'':>12} {sx:>12.1f}")

    straddle_hit = [l for l in b_straddle if l in f_docked]
    print("\n--- agreement ---")
    print(f"    recall@5 (tie-credited)      : {recall5} / {len(b_top)}   hits={recall5_hits}")
    print(f"    top-5 overlap (literal)      : {len(overlap)} / {len(b_top)}   {overlap}")
    if b_straddle:
        print(f"    (rank-6+ tied with a top-5   : {b_straddle} — funnel recovered "
              f"{len(straddle_hit)} of these)")
    print(f"    funnel #1 == baseline #1     : {f1 == b1}   (baseline={b1}, funnel={f1})")
    if spearman is not None:
        print(f"    Spearman rho (commonly docked, n={len(sp_pairs)}) : {spearman:+.3f}")
    else:
        print(f"    Spearman rho                 : n/a (n={len(sp_pairs)})")

    print("\n--- baseline top-5 ---")
    seen = set()
    for e in baseline.results:
        if e.rank and e.rank <= TOP_K and e.ligand_id not in seen:
            seen.add(e.ligand_id)
            tag = ""
            if e.ligand_id in false_negatives:
                tag = "   <<< FUNNEL FILTERED THIS OUT"
            elif e.ligand_id in overlap:
                tag = "   (funnel also docked)"
            elif e.ligand_id in selection_misses:
                tag = "   (funnel kept but didn't dock)"
            print("   ", _fmt_entry(e), tag)

    print("\n--- funnel top-5 (all it docked) ---")
    for e in funnel.results:
        if e.mean_affinity is not None or any(v is not None for v in e.per_seed_affinities.values()):
            b_r = b_rank.get(e.ligand_id, "?")
            print("   ", _fmt_entry(e), f"   baseline rank #{b_r}")

    print("\n" + line)
    verdict = (
        "CLAIM HOLDS" if (not false_negatives and len(overlap) >= 4 and f1 == b1)
        else "CLAIM PARTIALLY HOLDS" if (not false_negatives and len(overlap) >= 3)
        else "CLAIM DOES NOT HOLD"
    )
    print(f"  verdict: {verdict}")
    print(f"  \"funnel docked {funnel.total_docking_jobs_submitted} jobs vs baseline "
          f"{baseline.total_docking_jobs_submitted}; recovered {len(overlap)}/{len(b_top)} "
          f"of the baseline's top-5; {len(false_negatives)} false negative(s).\"")
    print(line)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--funnel", required=True)
    args = ap.parse_args()
    b = RunRecord.load(Path(args.baseline))
    f = RunRecord.load(Path(args.funnel))
    compare(b, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
