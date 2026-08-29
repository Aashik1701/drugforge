"""
Recall vs docking-budget frontier — OFFLINE, zero docking.

For the selected policy (DEFAULT_POLICY = v7), sweep the docking budget N from 1
to 45 against the cached cox2 baseline. For each N the funnel would dock the
top-N of its prescreen ordering (over the hard-filter survivors); everything is
scored against runs/baseline_cox2_v1.json, and estimated docking wall-clock is
summed from the per-candidate dock_wall_s already stored there.

  cd backend/app && COMPUTE_MODE=balanced ../venv/bin/python -m funnel.frontier

Writes: runs/frontier_cox2_v1.csv  and  runs/frontier_cox2_v1.svg
"""

from __future__ import annotations

import csv
from pathlib import Path

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.policy import DEFAULT_POLICY
from funnel.schema import RUNS_DIR, RunRecord

SET_ID = "cox2_v1"


def _tie_partners(baseline: RunRecord) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for e in baseline.results:
        if e.tie_group:
            groups.setdefault(e.tie_group, set()).add(e.ligand_id)
    return {e.ligand_id: (groups.get(e.tie_group, set()) - {e.ligand_id}
                          if e.tie_group else set())
            for e in baseline.results}


def prescreen_order(policy, features, candidate_ids) -> list[str]:
    """The funnel's ordering of the hard-filter survivors, best first."""
    feats = features["features"]
    survivors = [l for l in candidate_ids
                 if policy.descriptors_pass(feats[l]["descriptors"])[0]
                 and policy.tox_pass(feats[l]["predictions"])[0]]
    bvals = [feats[l]["predictions"]["binding_score"] for l in survivors]
    b_min, b_max = (min(bvals), max(bvals)) if bvals else (0.0, 0.0)
    span = (b_max - b_min) or 1.0

    def bnorm(x: float) -> float:
        frac = (x - b_min) / span
        return (1.0 - frac) if policy.binding_lower_is_better else frac

    scored = [(l, policy.rank_score(feats[l], bnorm(feats[l]["predictions"]["binding_score"])))
              for l in survivors]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [l for l, _ in scored]


def main() -> int:
    baseline = RunRecord.load(RUNS_DIR / f"baseline_{SET_ID}.json")
    features = load_features(SET_ID)
    cs = load_candidate_set()
    cand_ids = [c.ligand_id for c in cs.candidates]

    b_rank = {e.ligand_id: e.rank for e in baseline.results}
    b_top5 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 5]
    b_top10 = [e.ligand_id for e in baseline.results if e.rank and e.rank <= 10]
    wall = {e.ligand_id: (e.dock_wall_s or 0.0) for e in baseline.results}
    ties = _tie_partners(baseline)
    full_wall = baseline.total_docking_wall_s
    full_jobs = baseline.total_docking_jobs_submitted

    order = prescreen_order(DEFAULT_POLICY, features, cand_ids)
    n_survivors = len(order)

    def recall(target: list[str], docked: set[str], credited: bool) -> tuple[int, int]:
        if credited:
            hits = sum(1 for m in target if m in docked or (ties.get(m, set()) & docked))
        else:
            hits = sum(1 for m in target if m in docked)
        return hits, len(target)

    rows = []
    for n in range(1, len(cand_ids) + 1):
        docked = set(order[:n])            # funnel can only dock survivors
        jobs = len(docked) * 4
        est_wall = sum(wall[l] for l in docked)
        r5l, _ = recall(b_top5, docked, credited=False)
        r5t, _ = recall(b_top5, docked, credited=True)
        r10l, _ = recall(b_top10, docked, credited=False)
        r10t, _ = recall(b_top10, docked, credited=True)
        rows.append({
            "N": n,
            "docked": len(docked),
            "jobs": jobs,
            "recall5_literal": r5l,
            "recall5_tiecredit": r5t,
            "recall10_literal": r10l,
            "recall10_tiecredit": r10t,
            "est_dock_wall_s": round(est_wall, 1),
            "speedup_vs_full": round(full_wall / est_wall, 1) if est_wall else None,
        })

    # --- table ---
    print(f"selected policy: ranker={DEFAULT_POLICY.ranker} filter={DEFAULT_POLICY.filter_mode}")
    print(f"hard-filter survivors: {n_survivors}/{len(cand_ids)} "
          f"(the funnel can never dock the {len(cand_ids)-n_survivors} it filters)")
    print(f"full baseline: {full_jobs} jobs, {full_wall:.0f}s dock wall, recall@5 = 5/5 by definition\n")
    hdr = ("N", "docked", "jobs", "r@5(lit)", "r@5(tie)", "r@10(lit)", "r@10(tie)",
           "est_wall_s", "speedup")
    print("{:>3} {:>6} {:>5} {:>8} {:>8} {:>9} {:>9} {:>10} {:>8}".format(*hdr))
    for r in rows:
        if r["N"] <= 12 or r["N"] % 3 == 0 or r["N"] in (n_survivors, len(cand_ids)) \
           or (rows[r["N"]-2]["recall5_tiecredit"] != r["recall5_tiecredit"]):
            print("{N:>3} {docked:>6} {jobs:>5} {recall5_literal:>6}/5 {recall5_tiecredit:>6}/5 "
                  "{recall10_literal:>7}/10 {recall10_tiecredit:>7}/10 {est_dock_wall_s:>10} "
                  "{speedup_vs_full:>7}x".format(**r))

    csv_path = RUNS_DIR / f"frontier_{SET_ID}.csv"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {csv_path}")

    # --- first N to reach each recall@5 level (tie-credited) ---
    print("\nfirst N to reach recall@5 (tie-credited):")
    for k in range(1, 6):
        hit = next((r for r in rows if r["recall5_tiecredit"] >= k), None)
        if hit:
            print(f"  {k}/5  at N={hit['N']:<2}  ({hit['jobs']} jobs, ~{hit['est_dock_wall_s']:.0f}s, "
                  f"{hit['speedup_vs_full']}x saving)  picks so far: {order[:hit['N']]}")
        else:
            print(f"  {k}/5  never (max reached = {max(r['recall5_tiecredit'] for r in rows)}/5)")

    _write_svg(rows, n_survivors, RUNS_DIR / f"frontier_{SET_ID}.svg")
    print(f"wrote {RUNS_DIR / f'frontier_{SET_ID}.svg'}")
    return 0


def _write_svg(rows, n_survivors, path: Path) -> None:
    W, H = 760, 460
    ml, mr, mt, mb = 70, 30, 40, 55
    pw, ph = W - ml - mr, H - mt - mb
    xmax = 45
    ymax = 10

    def X(n):
        return ml + pw * (n / xmax)

    def Y(v):
        return mt + ph * (1 - v / ymax)

    def poly(key):
        return " ".join(f"{X(r['N']):.1f},{Y(r[key]):.1f}" for r in rows)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'font-family="ui-sans-serif,system-ui,sans-serif" font-size="12">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="20" text-anchor="middle" font-size="14" font-weight="600">'
        f'Funnel recall vs docking budget — cox2_v1, policy v7</text>',
    ]
    # axes
    parts.append(f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{mt+ph}" stroke="#333"/>')
    parts.append(f'<line x1="{ml}" y1="{mt+ph}" x2="{ml+pw}" y2="{mt+ph}" stroke="#333"/>')
    for v in range(0, ymax + 1, 2):
        parts.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{ml+pw}" y2="{Y(v):.1f}" '
                     f'stroke="#eee"/><text x="{ml-8}" y="{Y(v)+4:.1f}" text-anchor="end">{v}</text>')
    for n in range(0, xmax + 1, 5):
        parts.append(f'<text x="{X(n):.1f}" y="{mt+ph+18:.1f}" text-anchor="middle">{n}</text>')
    parts.append(f'<text x="{ml+pw/2}" y="{H-12}" text-anchor="middle">docking budget N (candidates docked; jobs = 4N)</text>')
    parts.append(f'<text x="16" y="{mt+ph/2}" text-anchor="middle" '
                 f'transform="rotate(-90 16 {mt+ph/2})">molecules recovered</text>')
    # survivor cap line
    parts.append(f'<line x1="{X(n_survivors):.1f}" y1="{mt}" x2="{X(n_survivors):.1f}" y2="{mt+ph}" '
                 f'stroke="#c00" stroke-dasharray="4 3"/>'
                 f'<text x="{X(n_survivors):.1f}" y="{mt-6}" text-anchor="middle" fill="#c00">'
                 f'filter cap N={n_survivors}</text>')
    # curves
    parts.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="2" points="{poly("recall5_tiecredit")}"/>')
    parts.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="1.5" stroke-dasharray="3 2" points="{poly("recall5_literal")}"/>')
    parts.append(f'<polyline fill="none" stroke="#ff7f0e" stroke-width="2" points="{poly("recall10_tiecredit")}"/>')
    # full-baseline point (N=45, recall@5 = 5/5, recall@10 = 10/10)
    parts.append(f'<circle cx="{X(45):.1f}" cy="{Y(5):.1f}" r="4" fill="#1f77b4"/>')
    parts.append(f'<circle cx="{X(45):.1f}" cy="{Y(10):.1f}" r="4" fill="#ff7f0e"/>')
    parts.append(f'<text x="{X(45):.1f}" y="{Y(5)-8:.1f}" text-anchor="end" fill="#1f77b4">full baseline 5/5</text>')
    # legend
    lx, ly = ml + 20, mt + 14
    parts.append(f'<line x1="{lx}" y1="{ly}" x2="{lx+22}" y2="{ly}" stroke="#1f77b4" stroke-width="2"/>'
                 f'<text x="{lx+28}" y="{ly+4}">recall@5 (tie-credited)</text>')
    parts.append(f'<line x1="{lx}" y1="{ly+18}" x2="{lx+22}" y2="{ly+18}" stroke="#1f77b4" stroke-width="1.5" stroke-dasharray="3 2"/>'
                 f'<text x="{lx+28}" y="{ly+22}">recall@5 (literal)</text>')
    parts.append(f'<line x1="{lx}" y1="{ly+36}" x2="{lx+22}" y2="{ly+36}" stroke="#ff7f0e" stroke-width="2"/>'
                 f'<text x="{lx+28}" y="{ly+40}">recall@10 (tie-credited)</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts))


if __name__ == "__main__":
    raise SystemExit(main())
