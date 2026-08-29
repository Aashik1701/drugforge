"""
funnel.two_phase -- the adaptive two-phase docking policy.

Phase 1: rank ALL v7 hard-filter survivors with the frozen v7 formula alone.
         Dock the top-S ("seed batch").
Phase 2: fit a surrogate on ONLY the seed batch's S real affinities. Rank the
         remaining survivors with it. Dock the next (N - S).
The union is ranked on mean affinity -- the one ranking function everywhere
else in this project uses (funnel.ranking) -- to produce the funnel's final
ordered shortlist.

Offline. Zero new docking: every "dock" is a lookup into the cached
runs/baseline_cox2_v1.json (45 molecules, real mean affinities). Reuses the
Pass-5 surrogate model (RandomForestRegressor, n_estimators=300, random_state=0)
completely unchanged -- no hyperparameter search, no tuning against recall.
Frozen v7 policy, docking params, and the four frozen contracts
(ComputeRouter / ResourceManager / JobStore / tool registry) are untouched.
ace2 data is not read.

Two leakage guards, enforced by assertion, not just by convention:

  G1 -- the Phase-1 seed batch is selected by v7 alone. seed_batch_for_S()
        takes ONLY the pre-computed v7 prescreen order as input -- an order
        built exclusively from funnel.frontier.prescreen_order (DEFAULT_POLICY
        + the cached features file). It never touches the baseline, the
        Pass-5 OOF predictions, or any real affinity. There is no such
        argument for it to consult even by accident.

  G2 -- fit_phase2() asserts x_tr/y_tr have exactly S rows before every
        model.fit() call, and asserts the training ids and the ids being
        predicted are disjoint. Each Phase-2 prediction therefore comes from
        a model that has seen exactly S real affinities and nothing else --
        not 45, not LOO over the full survivor set.

Declared S range (frozen BEFORE running, not extended after seeing results):
    S in {5, 8, 10, 13, 16, 20}
N range per S: N in [S, 41]  (41 = the v7 hard-filter survivor count; the
funnel can never dock more than that regardless of policy).

  cd backend/app && ../venv/bin/python -m funnel.two_phase
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.frontier import _tie_partners, prescreen_order
from funnel.policy import DEFAULT_POLICY, DESCRIPTOR_NAMES
from funnel.schema import RUNS_DIR, RunRecord
from funnel.surrogate import morgan_bits, spearman  # generic feature/metric utilities only -- no OOF, no baseline access here

SET_ID = "cox2_v1"
NAMED_FAILURE = "CHEMBL2315019"
SURVIVOR_CAP = 41

# Declared before running this pass. Do not extend after seeing results.
S_VALUES = [5, 8, 10, 13, 16, 20]

# Pass-5 rf settings (funnel/surrogate.py VARIANTS["rf"]), reused unchanged.
RF_KWARGS = dict(n_estimators=300, random_state=0, n_jobs=-1)


# ---------------------------------------------------------------------------
# Phase 1 -- seed batch selection. v7 ONLY.
# ---------------------------------------------------------------------------
def seed_batch_for_S(v7_order: list[str], S: int) -> list[str]:
    """G1: the seed batch is the top-S of the v7 prescreen order, and nothing
    else. v7_order is the ONLY argument -- it is built once, upstream, by
    funnel.frontier.prescreen_order(DEFAULT_POLICY, features, candidate_ids),
    which reads only the frozen policy and the cached per-candidate features.
    Neither this function nor its caller has a baseline, an affinity table, or
    a Pass-5 OOF-prediction argument available to leak from.
    """
    assert 0 < S <= len(v7_order), f"S={S} out of range for {len(v7_order)} survivors"
    return list(v7_order[:S])


# ---------------------------------------------------------------------------
# Phase 2 -- surrogate fit on the seed batch's real labels ONLY.
# ---------------------------------------------------------------------------
def fit_phase2(seed_ids: list[str], true_affinity: dict[str, float],
               x_by_id: dict[str, np.ndarray], remaining_ids: list[str]
               ) -> tuple[np.ndarray, RandomForestRegressor]:
    """G2: fit on exactly len(seed_ids) rows; predict on remaining_ids, which
    is asserted disjoint from seed_ids. y_tr is built by dict lookup keyed
    ONLY on seed_ids -- there is no way for a label outside the seed batch to
    enter y_tr, and no LOO fold ever refits with a held-out point added back.
    """
    S = len(seed_ids)
    assert len(set(seed_ids) & set(remaining_ids)) == 0, \
        "leakage: seed batch and held-out remainder overlap"
    x_tr = np.vstack([x_by_id[l] for l in seed_ids])
    y_tr = np.array([true_affinity[l] for l in seed_ids], dtype=float)
    assert x_tr.shape[0] == S and y_tr.shape[0] == S, \
        f"G2 violated: Phase-2 fit must see exactly S={S} rows, got {x_tr.shape[0]}"
    x_te = np.vstack([x_by_id[l] for l in remaining_ids])
    model = RandomForestRegressor(**RF_KWARGS)
    model.fit(x_tr, y_tr)
    assert model.n_features_in_ == x_tr.shape[1]
    pred = model.predict(x_te)
    assert len(pred) == len(remaining_ids)
    return pred, model


def phase2_order(seed_ids: list[str], remaining_ids: list[str],
                  true_affinity: dict[str, float], x_by_id: dict[str, np.ndarray]
                  ) -> tuple[list[str], np.ndarray]:
    pred, _ = fit_phase2(seed_ids, true_affinity, x_by_id, remaining_ids)
    order = [l for l, _ in sorted(zip(remaining_ids, pred), key=lambda t: t[1])]
    return order, pred


# ---------------------------------------------------------------------------
# Scoring -- identical recall / tie-credit logic to funnel.frontier / funnel.surrogate
# ---------------------------------------------------------------------------
def build_scorer(baseline: RunRecord):
    ties = _tie_partners(baseline)
    b_top5 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 5]
    b_top10 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 10]
    wall = {e.ligand_id: (e.dock_wall_s or 0.0) for e in baseline.results}
    full_wall = baseline.total_docking_wall_s

    def recall(target: list[str], docked: set[str], credited: bool) -> int:
        if credited:
            return sum(1 for m in target if m in docked or (ties.get(m, set()) & docked))
        return sum(1 for m in target if m in docked)

    return recall, b_top5, b_top10, wall, full_wall


# ---------------------------------------------------------------------------
def _json_default(o):
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    features = load_features(SET_ID)
    feats = features["features"]
    cs = load_candidate_set()
    cand_ids = [c.ligand_id for c in cs.candidates]

    true_affinity = {e.ligand_id: e.mean_affinity for e in baseline.results}
    assert not any(v is None for v in true_affinity.values())

    # --- Phase-1 order: v7 alone. Computed ONCE, shared by every S. ---
    v7_order = prescreen_order(DEFAULT_POLICY, features, cand_ids)
    assert len(v7_order) == SURVIVOR_CAP, f"expected {SURVIVOR_CAP} survivors, got {len(v7_order)}"

    # --- features for the Phase-2 model: identical to funnel.surrogate (ECFP4 1024 + 10 descriptors) ---
    smiles_by_id = {c.ligand_id: c.smiles for c in cs.candidates}
    x_by_id: dict[str, np.ndarray] = {}
    for l in v7_order:
        fp = morgan_bits(smiles_by_id[l])
        desc = np.array([feats[l]["descriptors"][k] for k in DESCRIPTOR_NAMES], dtype=float)
        x_by_id[l] = np.concatenate([fp, desc])

    recall, b_top5, b_top10, wall, full_wall = build_scorer(baseline)
    b_rank = {e.ligand_id: e.rank for e in baseline.results}
    print(f"v7 hard-filter survivors: {len(v7_order)}/45")
    print(f"baseline true top-5: {[(l, b_rank[l]) for l in b_top5]}")
    print(f"{NAMED_FAILURE}: baseline rank #{b_rank[NAMED_FAILURE]}, v7 prescreen rank #{v7_order.index(NAMED_FAILURE)+1}")
    print(f"declared S range: {S_VALUES}\n")

    # --- reference curves at the same N: frozen v7, Pass-5 LOO surrogate (rf, 41-survivor variant) ---
    v7_csv = list(csv.DictReader((RUNS_DIR / f"frontier_{SET_ID}.csv").open()))
    v7_by_n = {int(r["N"]): r for r in v7_csv}
    surr_csv = list(csv.DictReader((RUNS_DIR / f"frontier_surrogate_{SET_ID}.csv").open()))
    surr_by_n = {int(r["N"]): r for r in surr_csv}

    # ---- Phase 2, once per S ----
    per_s_quality: dict[int, dict] = {}
    per_s_order2: dict[int, list[str]] = {}
    for S in S_VALUES:
        seed_ids = seed_batch_for_S(v7_order, S)
        remaining_ids = [l for l in v7_order if l not in set(seed_ids)]
        assert len(seed_ids) + len(remaining_ids) == SURVIVOR_CAP
        order2, pred = phase2_order(seed_ids, remaining_ids, true_affinity, x_by_id)
        per_s_order2[S] = order2
        y_rem_true = [true_affinity[l] for l in remaining_ids]
        rho = spearman(pred, y_rem_true)
        mae = float(np.mean(np.abs(np.asarray(pred) - np.asarray(y_rem_true))))
        per_s_quality[S] = {
            "seed_ids": seed_ids,
            "n_remaining": len(remaining_ids),
            "held_out_spearman": rho,
            "held_out_mae": mae,
        }
        print(f"S={S:>2}  seed batch (v7 top-{S})  Phase-2 held-out remainder n={len(remaining_ids)}  "
              f"Spearman(pred, true) = {rho:+.3f}   MAE = {mae:.3f}")

    print()

    # ---- Grid: (S, N) cells ----
    grid_rows = []
    for S in S_VALUES:
        seed_ids = seed_batch_for_S(v7_order, S)
        order2 = per_s_order2[S]
        for N in range(S, SURVIVOR_CAP + 1):
            extra = order2[: N - S]
            docked = set(seed_ids) | set(extra)
            assert len(docked) == N, f"S={S} N={N}: expected {N} docked, got {len(docked)}"
            final_order = sorted(docked, key=lambda l: true_affinity[l])  # rank the union on mean affinity

            r5l = recall(b_top5, docked, False)
            r5t = recall(b_top5, docked, True)
            r10l = recall(b_top10, docked, False)
            r10t = recall(b_top10, docked, True)
            jobs = 4 * N
            est_wall = round(sum(wall[l] for l in docked), 1)
            speedup = round(full_wall / est_wall, 2) if est_wall else None
            named_docked = NAMED_FAILURE in docked
            named_rank = final_order.index(NAMED_FAILURE) + 1 if named_docked else None

            v7ref = v7_by_n.get(N, {})
            surref = surr_by_n.get(N, {})

            grid_rows.append({
                "S": S, "N": N, "jobs": jobs, "est_wall_s": est_wall, "speedup_vs_45": speedup,
                "r5_lit": r5l, "r5_tie": r5t, "r10_lit": r10l, "r10_tie": r10t,
                "named_docked": named_docked, "named_rank": named_rank,
                "v7_r5_lit": int(v7ref.get("recall5_literal", 0)), "v7_r5_tie": int(v7ref.get("recall5_tiecredit", 0)),
                "v7_r10_lit": int(v7ref.get("recall10_literal", 0)), "v7_r10_tie": int(v7ref.get("recall10_tiecredit", 0)),
                "surrRF_r5_lit": int(surref.get("surr41_rf_r5_literal", 0)) if surref else None,
                "surrRF_r5_tie": int(surref.get("surr41_rf_r5_tiecredit", 0)) if surref else None,
                "surrRF_r10_lit": int(surref.get("surr41_rf_r10_literal", 0)) if surref else None,
                "surrRF_r10_tie": int(surref.get("surr41_rf_r10_tiecredit", 0)) if surref else None,
            })

    # ---- write CSV grid ----
    out_csv = RUNS_DIR / f"two_phase_{SET_ID}.csv"
    fieldnames = list(grid_rows[0].keys())
    with out_csv.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(grid_rows)
    print(f"wrote {out_csv}  ({len(grid_rows)} (S,N) cells)")

    # ---- Task 3: first N (per S) reaching literal 5/5, vs the two references ----
    v7_full5_n = next((n for n in sorted(v7_by_n) if int(v7_by_n[n]["recall5_literal"]) >= 5), None)
    surr_full5_n = next((n for n in sorted(surr_by_n)
                          if surr_by_n[n].get("surr41_rf_r5_literal") not in (None, "")
                          and int(surr_by_n[n]["surr41_rf_r5_literal"]) >= 5), None)
    v7_full10_n = next((n for n in sorted(v7_by_n) if int(v7_by_n[n]["recall10_literal"]) >= 10), None)
    surr_full10_n = next((n for n in sorted(surr_by_n)
                           if surr_by_n[n].get("surr41_rf_r10_literal") not in (None, "")
                           and int(surr_by_n[n]["surr41_rf_r10_literal"]) >= 10), None)

    print(f"\nreferences: v7 reaches literal 5/5 at N={v7_full5_n}, 10/10 at N={v7_full10_n}")
    print(f"            Pass-5 rf surrogate reaches literal 5/5 at N={surr_full5_n}, 10/10 at N={surr_full10_n}")

    per_s_first5 = {}
    print("\nfirst N (per S) reaching two-phase literal recall@5 = 5/5:")
    for S in S_VALUES:
        rows_s = [r for r in grid_rows if r["S"] == S]
        hit = next((r for r in rows_s if r["r5_lit"] >= 5), None)
        per_s_first5[S] = hit["N"] if hit else None
        print(f"  S={S:>2}: N={hit['N'] if hit else 'never (max ' + str(max(r['r5_lit'] for r in rows_s)) + '/5)'}")

    best_S, best_N = None, None
    reached = [(S, n) for S, n in per_s_first5.items() if n is not None]
    if reached:
        best_S, best_N = min(reached, key=lambda t: t[1])
        best_speedup = next(r["speedup_vs_45"] for r in grid_rows if r["S"] == best_S and r["N"] == best_N)
        print(f"\nbest cell: S={best_S}, N={best_N} (jobs={4*best_N}, {best_speedup}x vs 45-candidate baseline)")
        if v7_full5_n:
            print(f"  saving vs v7      (N={v7_full5_n}): {round(v7_full5_n / best_N, 2)}x fewer docks for the same 5/5")
        if surr_full5_n:
            print(f"  saving vs Pass-5 surrogate (N={surr_full5_n}): {round(surr_full5_n / best_N, 2)}x fewer docks for the same 5/5")

        neighbours = {S: n for S, n in per_s_first5.items() if n is not None and S != best_S}
        print(f"  nearby-S stability: {neighbours}")

    # ---- write JSON (full grid + quality + summary) ----
    out_json = RUNS_DIR / f"two_phase_{SET_ID}.json"
    out_json.write_text(json.dumps({
        "set_id": SET_ID,
        "declared_s_values": S_VALUES,
        "survivor_cap": SURVIVOR_CAP,
        "model": {"kind": "rf", "kwargs": RF_KWARGS, "source": "funnel/surrogate.py Pass-5, unchanged"},
        "named_failure": NAMED_FAILURE,
        "named_failure_v7_rank": v7_order.index(NAMED_FAILURE) + 1,
        "named_failure_baseline_rank": b_rank[NAMED_FAILURE],
        "references": {
            "v7_full_literal_top5_at_N": v7_full5_n,
            "v7_full_literal_top10_at_N": v7_full10_n,
            "surrogate_rf_full_literal_top5_at_N": surr_full5_n,
            "surrogate_rf_full_literal_top10_at_N": surr_full10_n,
        },
        "per_s_phase2_quality": per_s_quality,
        "per_s_first_full_literal_top5_N": per_s_first5,
        "best_cell": {"S": best_S, "N": best_N} if best_S else None,
        "grid": grid_rows,
    }, indent=2, default=_json_default))
    print(f"wrote {out_json}")

    # ---- SVG: three curves -- two-phase(best S) vs v7 vs Pass-5 rf surrogate, recall@5 literal ----
    if best_S is not None:
        tp_rows = [r for r in grid_rows if r["S"] == best_S]
        write_svg(RUNS_DIR / f"two_phase_{SET_ID}.svg", tp_rows, v7_by_n, surr_by_n, best_S, SURVIVOR_CAP)
        print(f"wrote {RUNS_DIR / f'two_phase_{SET_ID}.svg'}")

    return 0


def write_svg(path: Path, tp_rows: list[dict], v7_by_n: dict, surr_by_n: dict,
              best_S: int, xmax: int) -> None:
    W, H = 780, 470
    ml, mr, mt, mb = 70, 30, 44, 58
    pw, ph = W - ml - mr, H - mt - mb
    ymax = 5

    def X(n):
        return ml + pw * (n / xmax)

    def Y(v):
        return mt + ph * (1 - v / ymax)

    tp_pts = " ".join(f"{X(r['N']):.1f},{Y(r['r5_lit']):.1f}" for r in tp_rows)
    v7_pts = " ".join(f"{X(n):.1f},{Y(int(v7_by_n[n]['recall5_literal'])):.1f}"
                       for n in sorted(v7_by_n) if n <= xmax)
    surr_pts = " ".join(f"{X(n):.1f},{Y(int(surr_by_n[n]['surr41_rf_r5_literal'])):.1f}"
                         for n in sorted(surr_by_n)
                         if n <= xmax and surr_by_n[n].get("surr41_rf_r5_literal") not in (None, ""))

    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="20" text-anchor="middle" font-size="14" font-weight="600">'
        f'Two-phase (S={best_S}) vs frozen v7 vs Pass-5 surrogate -- recall@5 literal (cox2_v1, offline)</text>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333"/>',
        f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333"/>',
    ]
    for v in range(0, ymax + 1):
        p.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{ml+pw}" y2="{Y(v):.1f}" stroke="#eee"/>'
                 f'<text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end">{v}</text>')
    for n in range(0, xmax + 1, 5):
        p.append(f'<text x="{X(n):.1f}" y="{mt+ph+18:.1f}" text-anchor="middle">{n}</text>')
    p.append(f'<text x="{ml+pw/2}" y="{H-14}" text-anchor="middle">docking budget N (jobs = 4N)</text>')
    p.append(f'<text x="16" y="{mt+ph/2}" text-anchor="middle" '
             f'transform="rotate(-90 16 {mt+ph/2})">baseline top-5 recovered (literal)</text>')
    p.append(f'<polyline fill="none" stroke="#d62728" stroke-width="2.5" points="{tp_pts}"/>')
    p.append(f'<polyline fill="none" stroke="#999" stroke-width="2" points="{v7_pts}"/>')
    p.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="2" points="{surr_pts}"/>')
    lx, ly = ml + 20, mt + 14
    legend = [
        ("#d62728", f"two-phase S={best_S} recall@5 literal"),
        ("#999", "frozen v7 recall@5 literal"),
        ("#1f77b4", "Pass-5 rf surrogate (41-survivor) recall@5 literal"),
    ]
    for i, (col, lbl) in enumerate(legend):
        yy = ly + i * 17
        p.append(f'<line x1="{lx}" y1="{yy}" x2="{lx+22}" y2="{yy}" stroke="{col}" stroke-width="2.5"/>'
                 f'<text x="{lx+28}" y="{yy+4}">{lbl}</text>')
    p.append("</svg>")
    path.write_text("\n".join(p))


if __name__ == "__main__":
    raise SystemExit(main())
