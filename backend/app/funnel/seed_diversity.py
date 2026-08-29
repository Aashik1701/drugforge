"""
funnel.seed_diversity -- does a diversity-selected seed batch fix Pass 6?

Pass 6 diagnosed: v7's top-S seed batch is a narrow affinity band (0.9-2.0
kcal/mol of a 5.0 kcal/mol range), which is why the Phase-2 fit's held-out
Spearman is NEGATIVE below S=13. This pass tests whether selecting the seed
batch a different way -- for feature-space diversity, or spread across v7's
own score distribution, or uniformly at random -- gives the surrogate a wider
label range and clears the noise floor at a smaller S, and whether any of
that closes the gap to the Pass-5 LOO surrogate (N=21).

Offline. Zero new docking. Reuses the Pass-6 harness UNCHANGED:
`fit_phase2` (leakage guard G2), `phase2_order`, `build_scorer`, the frozen rf
model config, `seed_batch_for_S` (the control strategy), all imported from
`funnel.two_phase`. Only the SEED-SELECTION step is new; everything
downstream of "here is a seed batch of S ligand ids" is identical to Pass 6.

Four strategies, declared and frozen in funnel/CHANGELOG.md ("Pass 7 --
pre-registration") BEFORE this file was written:
    control_v7_topS       -- Pass 6's own strategy, for direct comparison
    maxmin_diversity       -- greedy farthest-point, standardized feature space
    stratified_v7_score    -- S points evenly spaced across v7's own ranking
    random_seed0           -- uniform random sample, numpy default_rng(seed=0)

Leakage guard G1: every strategy function takes only `ctx` = {v7_order,
v7_scores, x_by_id, survivors_sorted} -- no baseline, no affinity, no OOF
prediction. Asserted at every call site.

  cd backend/app && ../venv/bin/python -m funnel.two_phase   # must run first (references)
  cd backend/app && ../venv/bin/python -m funnel.seed_diversity
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.frontier import prescreen_order
from funnel.policy import DEFAULT_POLICY, DESCRIPTOR_NAMES
from funnel.schema import RUNS_DIR, RunRecord
from funnel.surrogate import morgan_bits, spearman
from funnel.two_phase import (
    NAMED_FAILURE,
    S_VALUES,
    SET_ID,
    SURVIVOR_CAP,
    _json_default,
    build_scorer,
    fit_phase2,
    phase2_order,
    seed_batch_for_S,
)

CTX_KEYS = {"v7_order", "v7_scores", "x_by_id", "survivors_sorted"}


# ---------------------------------------------------------------------------
# strategies -- each takes ONLY ctx (see CTX_KEYS) and S
# ---------------------------------------------------------------------------
def control_v7_topS(ctx: dict, S: int) -> list[str]:
    return seed_batch_for_S(ctx["v7_order"], S)


def maxmin_diversity(ctx: dict, S: int) -> list[str]:
    """Greedy farthest-point over standardized (z-score) feature space.
    Starting point = closest to the feature-space centroid, NOT v7's #1 pick,
    so v7's ranking preference cannot anchor (leak into) the search. Ties in
    the greedy step are broken by a v7-independent canonical order
    (survivors_sorted = sorted ligand ids)."""
    order = ctx["survivors_sorted"]          # canonical, v7-independent order
    x_by_id = ctx["x_by_id"]
    X = np.vstack([x_by_id[l] for l in order])
    mu, sigma = X.mean(axis=0), X.std(axis=0)
    sigma = np.where(sigma == 0, 1.0, sigma)
    Xs = (X - mu) / sigma
    idx_of = {l: i for i, l in enumerate(order)}

    centroid = Xs.mean(axis=0)
    start_i = int(np.argmin(np.linalg.norm(Xs - centroid, axis=1)))
    chosen_idx = [start_i]
    remaining = [i for i in range(len(order)) if i != start_i]

    while len(chosen_idx) < S:
        chosen_X = Xs[chosen_idx]
        best_i, best_d = None, -1.0
        for i in remaining:                  # `remaining` iterates in canonical order -> deterministic tie-break
            d = float(np.min(np.linalg.norm(chosen_X - Xs[i], axis=1)))
            if d > best_d:
                best_d, best_i = d, i
        chosen_idx.append(best_i)
        remaining.remove(best_i)

    return [order[i] for i in chosen_idx]


def stratified_v7_score(ctx: dict, S: int) -> list[str]:
    """S positions evenly spaced across the v7 rank-score ordering (best
    first). Spreads the seed across the whole ranking instead of the top."""
    v7_order = ctx["v7_order"]
    n = len(v7_order)
    if S == 1:
        return [v7_order[0]]
    idxs = sorted({round(i * (n - 1) / (S - 1)) for i in range(S)})
    i = 0
    while len(idxs) < S:                      # pad on rare rounding collisions (not expected at n=41)
        for cand in range(n):
            if cand not in idxs:
                idxs.append(cand)
                break
        idxs = sorted(idxs)
    return [v7_order[i] for i in idxs[:S]]


def random_seed0(ctx: dict, S: int) -> list[str]:
    """Uniform random sample, single fixed-seed draw."""
    order = ctx["survivors_sorted"]           # canonical, v7-independent order
    rng = np.random.default_rng(0)
    idx = rng.choice(len(order), size=S, replace=False)
    return [order[i] for i in sorted(idx.tolist())]


STRATEGIES = {
    "control_v7_topS": control_v7_topS,
    "maxmin_diversity": maxmin_diversity,
    "stratified_v7_score": stratified_v7_score,
    "random_seed0": random_seed0,
}


# ---------------------------------------------------------------------------
def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    features = load_features(SET_ID)
    feats = features["features"]
    cs = load_candidate_set()
    cand_ids = [c.ligand_id for c in cs.candidates]

    true_affinity = {e.ligand_id: e.mean_affinity for e in baseline.results}
    assert not any(v is None for v in true_affinity.values())

    v7_order = prescreen_order(DEFAULT_POLICY, features, cand_ids)
    assert len(v7_order) == SURVIVOR_CAP

    smiles_by_id = {c.ligand_id: c.smiles for c in cs.candidates}
    x_by_id: dict[str, np.ndarray] = {}
    for l in v7_order:
        fp = morgan_bits(smiles_by_id[l])
        desc = np.array([feats[l]["descriptors"][k] for k in DESCRIPTOR_NAMES], dtype=float)
        x_by_id[l] = np.concatenate([fp, desc])

    # G1: ctx carries ONLY v7-derived / feature-space material. No baseline,
    # no affinity, no OOF prediction is reachable from it.
    ctx = {
        "v7_order": v7_order,
        "v7_scores": None,           # not needed by any strategy that uses the pre-sorted order directly
        "x_by_id": x_by_id,
        "survivors_sorted": sorted(v7_order),
    }
    assert set(ctx.keys()) == CTX_KEYS
    assert not any(isinstance(v, (RunRecord, dict)) and v is true_affinity for v in ctx.values())

    recall, b_top5, b_top10, wall, full_wall = build_scorer(baseline)
    b_rank = {e.ligand_id: e.rank for e in baseline.results}
    print(f"v7 hard-filter survivors: {len(v7_order)}/45")
    print(f"{NAMED_FAILURE}: baseline rank #{b_rank[NAMED_FAILURE]}, v7 prescreen rank #{v7_order.index(NAMED_FAILURE)+1}")
    print(f"strategies: {list(STRATEGIES)}")
    print(f"declared S range: {S_VALUES}\n")

    # references at the same N
    v7_csv = list(csv.DictReader((RUNS_DIR / f"frontier_{SET_ID}.csv").open()))
    v7_by_n = {int(r["N"]): r for r in v7_csv}
    surr_csv = list(csv.DictReader((RUNS_DIR / f"frontier_surrogate_{SET_ID}.csv").open()))
    surr_by_n = {int(r["N"]): r for r in surr_csv}
    v7_full5_n = next((n for n in sorted(v7_by_n) if int(v7_by_n[n]["recall5_literal"]) >= 5), None)
    surr_full5_n = next((n for n in sorted(surr_by_n)
                          if surr_by_n[n].get("surr41_rf_r5_literal") not in (None, "")
                          and int(surr_by_n[n]["surr41_rf_r5_literal"]) >= 5), None)
    print(f"references: v7 full literal 5/5 at N={v7_full5_n}; Pass-5 rf surrogate at N={surr_full5_n}\n")

    # ---- Phase 2 per (strategy, S) ----
    quality: dict[str, dict[int, dict]] = {s: {} for s in STRATEGIES}
    order2_by: dict[str, dict[int, list[str]]] = {s: {} for s in STRATEGIES}
    for sname, sfn in STRATEGIES.items():
        for S in S_VALUES:
            seed_ids = sfn(ctx, S)
            assert len(seed_ids) == S and len(set(seed_ids)) == S, f"{sname} S={S}: bad seed batch size"
            assert set(seed_ids) <= set(v7_order), f"{sname} S={S}: seed ids outside survivor set"
            remaining_ids = [l for l in v7_order if l not in set(seed_ids)]
            order2, pred = phase2_order(seed_ids, remaining_ids, true_affinity, x_by_id)
            order2_by[sname][S] = order2

            vals = [true_affinity[l] for l in seed_ids]
            y_rem_true = [true_affinity[l] for l in remaining_ids]
            rho = spearman(pred, y_rem_true)
            quality[sname][S] = {
                "seed_ids": seed_ids,
                "affinity_min": min(vals), "affinity_max": max(vals),
                "affinity_range": round(max(vals) - min(vals), 3),
                "held_out_spearman": rho,
                "held_out_mae": float(np.mean(np.abs(np.asarray(pred) - np.asarray(y_rem_true)))),
            }
            print(f"{sname:<22} S={S:>2}  range=[{min(vals):+.2f},{max(vals):+.2f}] "
                  f"({max(vals)-min(vals):.2f} kcal/mol)  rho={rho:+.3f}")
    print()

    # ---- Grid ----
    grid_rows = []
    for sname in STRATEGIES:
        for S in S_VALUES:
            seed_ids = quality[sname][S]["seed_ids"]
            order2 = order2_by[sname][S]
            for N in range(S, SURVIVOR_CAP + 1):
                extra = order2[: N - S]
                docked = set(seed_ids) | set(extra)
                assert len(docked) == N
                final_order = sorted(docked, key=lambda l: true_affinity[l])

                r5l = recall(b_top5, docked, False)
                r5t = recall(b_top5, docked, True)
                r10l = recall(b_top10, docked, False)
                r10t = recall(b_top10, docked, True)
                est_wall = round(sum(wall[l] for l in docked), 1)
                speedup = round(full_wall / est_wall, 2) if est_wall else None
                named_docked = NAMED_FAILURE in docked
                named_rank = final_order.index(NAMED_FAILURE) + 1 if named_docked else None

                v7ref = v7_by_n.get(N, {})
                surref = surr_by_n.get(N, {})

                grid_rows.append({
                    "strategy": sname, "S": S, "N": N, "jobs": 4 * N,
                    "est_wall_s": est_wall, "speedup_vs_45": speedup,
                    "r5_lit": r5l, "r5_tie": r5t, "r10_lit": r10l, "r10_tie": r10t,
                    "named_docked": named_docked, "named_rank": named_rank,
                    "v7_r5_lit": int(v7ref.get("recall5_literal", 0)) if v7ref else None,
                    "surrRF_r5_lit": int(surref.get("surr41_rf_r5_literal", 0)) if surref else None,
                })

    out_csv = RUNS_DIR / f"seed_diversity_{SET_ID}.csv"
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(grid_rows[0].keys()))
        w.writeheader()
        w.writerows(grid_rows)
    print(f"wrote {out_csv}  ({len(grid_rows)} (strategy,S,N) cells)")

    # ---- first N (per strategy, S) reaching literal 5/5 ----
    first5: dict[str, dict[int, int | None]] = {s: {} for s in STRATEGIES}
    print("\nfirst N reaching two-phase literal recall@5 = 5/5, per strategy x S:")
    for sname in STRATEGIES:
        for S in S_VALUES:
            rows_s = [r for r in grid_rows if r["strategy"] == sname and r["S"] == S]
            hit = next((r for r in rows_s if r["r5_lit"] >= 5), None)
            first5[sname][S] = hit["N"] if hit else None
        print(f"  {sname:<22} {first5[sname]}")

    beats_surrogate = [(s, S, n) for s in STRATEGIES for S, n in first5[s].items()
                        if n is not None and surr_full5_n is not None and n < surr_full5_n]
    beats_v7_only = [(s, S, n) for s in STRATEGIES for S, n in first5[s].items()
                      if n is not None and v7_full5_n is not None and n < v7_full5_n
                      and not (surr_full5_n is not None and n < surr_full5_n)]
    print(f"\ncells beating the Pass-5 LOO surrogate (N<{surr_full5_n}): {beats_surrogate or 'NONE'}")

    best_overall = None
    all_hits = [(s, S, n) for s in STRATEGIES for S, n in first5[s].items() if n is not None]
    if all_hits:
        best_overall = min(all_hits, key=lambda t: t[2])
    print(f"best cell overall: {best_overall}")

    # ---- Task 4: seed affinity range vs held-out Spearman, all (strategy,S) cells ----
    scatter = [{"strategy": s, "S": S, "range": quality[s][S]["affinity_range"], "rho": quality[s][S]["held_out_spearman"]}
               for s in STRATEGIES for S in S_VALUES]
    ranges = np.array([p["range"] for p in scatter])
    rhos = np.array([p["rho"] for p in scatter])
    range_quality_corr = float(np.corrcoef(ranges, rhos)[0, 1]) if len(ranges) > 1 else None
    print(f"\nseed affinity range vs held-out Spearman, Pearson r across all {len(scatter)} (strategy,S) cells: "
          f"{range_quality_corr:+.3f}" if range_quality_corr is not None else "n/a")

    crossover_below_13 = [s for s in STRATEGIES
                           if any(S < 13 and quality[s][S]["held_out_spearman"] > 0 for S in S_VALUES)]
    print(f"strategies with ANY positive held-out Spearman at S<13: {crossover_below_13 or 'NONE'}")

    out_json = RUNS_DIR / f"seed_diversity_{SET_ID}.json"
    out_json.write_text(json.dumps({
        "set_id": SET_ID,
        "strategies": list(STRATEGIES),
        "declared_s_values": S_VALUES,
        "survivor_cap": SURVIVOR_CAP,
        "references": {"v7_full_literal_top5_at_N": v7_full5_n, "surrogate_rf_full_literal_top5_at_N": surr_full5_n},
        "per_strategy_quality": quality,
        "per_strategy_first_full_literal_top5_N": first5,
        "cells_beating_surrogate": beats_surrogate,
        "best_cell_overall": best_overall,
        "range_vs_spearman_pearson_r": range_quality_corr,
        "strategies_with_positive_spearman_below_S13": crossover_below_13,
        "scatter": scatter,
        "grid": grid_rows,
    }, indent=2, default=_json_default))
    print(f"wrote {out_json}")

    write_scatter_svg(RUNS_DIR / f"seed_diversity_{SET_ID}.svg", scatter)
    print(f"wrote {RUNS_DIR / f'seed_diversity_{SET_ID}.svg'}")

    return 0


def write_scatter_svg(path: Path, scatter: list[dict]) -> None:
    W, H = 760, 460
    ml, mr, mt, mb = 70, 30, 44, 58
    pw, ph = W - ml - mr, H - mt - mb
    xmax = max(p["range"] for p in scatter) * 1.1
    ymin, ymax = -1.0, 1.0

    def X(v):
        return ml + pw * (v / xmax)

    def Y(v):
        return mt + ph * (1 - (v - ymin) / (ymax - ymin))

    colors = {"control_v7_topS": "#999", "maxmin_diversity": "#d62728",
              "stratified_v7_score": "#2ca02c", "random_seed0": "#1f77b4"}

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="20" text-anchor="middle" font-size="14" font-weight="600">'
        f'Seed-batch affinity range vs Phase-2 held-out Spearman (cox2_v1, offline)</text>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333"/>',
        f'<line x1="{ml}" y1="{Y(0):.1f}" x2="{ml+pw}" y2="{Y(0):.1f}" stroke="#ccc"/>',
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333"/>',
    ]
    for v in (-1.0, -0.5, 0.0, 0.5, 1.0):
        p.append(f'<text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end">{v:+.1f}</text>')
    for v in np.arange(0, xmax, 0.5):
        p.append(f'<text x="{X(v):.1f}" y="{mt+ph+18:.1f}" text-anchor="middle">{v:.1f}</text>')
    p.append(f'<text x="{ml+pw/2}" y="{H-14}" text-anchor="middle">seed-batch affinity range (kcal/mol)</text>')
    p.append(f'<text x="16" y="{mt+ph/2}" text-anchor="middle" '
             f'transform="rotate(-90 16 {mt+ph/2})">held-out Spearman rho</text>')
    for pt in scatter:
        c = colors[pt["strategy"]]
        p.append(f'<circle cx="{X(pt["range"]):.1f}" cy="{Y(pt["rho"]):.1f}" r="4.5" fill="{c}" fill-opacity="0.85"/>')
    lx, ly = ml + 20, mt + 14
    for i, (sname, c) in enumerate(colors.items()):
        yy = ly + i * 17
        p.append(f'<circle cx="{lx}" cy="{yy}" r="4.5" fill="{c}"/><text x="{lx+10}" y="{yy+4}">{sname}</text>')
    p.append("</svg>")
    path.write_text("\n".join(p))


if __name__ == "__main__":
    raise SystemExit(main())
