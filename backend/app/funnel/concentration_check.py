"""
funnel.concentration_check -- how much of cox2_v1's recall@5 signal is really
just "was CHEMBL2315019 docked yet"?

Offline. Reads only already-committed run artifacts from Passes 4-7 (the v7
frontier, the Pass-5 surrogate variants, the Pass-6 two-phase grid, the Pass-7
seed-diversity grid). No new computation of any ranking or fit -- this pass
only re-derives, for each already-computed policy curve, whether the N at
which literal recall@5 first reaches 5/5 is the SAME N at which
CHEMBL2315019 first enters the docked set.

This quantifies a benchmark-limitation claim, not a policy result: if that
coincidence rate is high, cox2_v1's literal-recall@5 headline is largely a
single-molecule detection test, which limits how well it can discriminate
between policies that all handle the other four true-top-5 molecules easily.

  cd backend/app && ../venv/bin/python -m funnel.concentration_check
"""

from __future__ import annotations

import csv
import json

from funnel.candidate_set import load_candidate_set
from funnel.features import load_features
from funnel.frontier import prescreen_order
from funnel.policy import DEFAULT_POLICY
from funnel.schema import RUNS_DIR

SET_ID = "cox2_v1"
NAMED_FAILURE = "CHEMBL2315019"


def _first_true(seq) -> int | None:
    for i, v in enumerate(seq, 1):
        if v:
            return i
    return None


def main() -> int:
    policies: list[tuple[str, int | None, int | None]] = []  # (label, N_at_5of5, N_named_enters)

    # ---- v7 (Pass 3/4) ----
    features = load_features(SET_ID)
    cs = load_candidate_set()
    cand_ids = [c.ligand_id for c in cs.candidates]
    v7_order = prescreen_order(DEFAULT_POLICY, features, cand_ids)
    v7_csv = list(csv.DictReader((RUNS_DIR / f"frontier_{SET_ID}.csv").open()))
    v7_r5 = {int(r["N"]): int(r["recall5_literal"]) for r in v7_csv}
    n5 = next((n for n in sorted(v7_r5) if v7_r5[n] >= 5), None)
    n_named = v7_order.index(NAMED_FAILURE) + 1
    policies.append(("v7 (frozen policy)", n5, n_named))

    # ---- Pass 5: surrogate variants (ridge, rf, krr_tanimoto), 41-survivor ranking ----
    surr = json.loads((RUNS_DIR / f"surrogate_{SET_ID}.json").read_text())
    for kind, v in surr["variants"].items():
        order = v["order_41survivors"]
        n_named = order.index(NAMED_FAILURE) + 1 if NAMED_FAILURE in order else None
        fr = v["frontier_41survivors"]
        n5 = next((r["N"] for r in fr if r["r5l"] >= 5), None)
        policies.append((f"Pass-5 surrogate ({kind})", n5, n_named))

    # ---- Pass 6: two-phase, per S ----
    tp = json.loads((RUNS_DIR / f"two_phase_{SET_ID}.json").read_text())
    by_s: dict[int, list[dict]] = {}
    for row in tp["grid"]:
        by_s.setdefault(row["S"], []).append(row)
    for S, rows in sorted(by_s.items()):
        rows.sort(key=lambda r: r["N"])
        n5 = next((r["N"] for r in rows if r["r5_lit"] >= 5), None)
        n_named = next((r["N"] for r in rows if r["named_docked"]), None)
        policies.append((f"Pass-6 two-phase (S={S})", n5, n_named))

    # ---- Pass 7: seed-diversity, per strategy x S ----
    sd = json.loads((RUNS_DIR / f"seed_diversity_{SET_ID}.json").read_text())
    by_strat_s: dict[tuple[str, int], list[dict]] = {}
    for row in sd["grid"]:
        by_strat_s.setdefault((row["strategy"], row["S"]), []).append(row)
    for (strat, S), rows in sorted(by_strat_s.items()):
        rows.sort(key=lambda r: r["N"])
        n5 = next((r["N"] for r in rows if r["r5_lit"] >= 5), None)
        n_named = next((r["N"] for r in rows if r["named_docked"]), None)
        policies.append((f"Pass-7 {strat} (S={S})", n5, n_named))

    # ---- tally ----
    print(f"{'policy':<38} {'N@5/5':>7} {'N(named docked)':>17} {'same N?':>8}")
    print("-" * 74)
    coincide = 0
    determined = 0  # policies where recall@5 reached 5/5 at all
    for label, n5, n_named in policies:
        if n5 is None:
            print(f"{label:<38} {'never':>7} {str(n_named):>17} {'-':>8}")
            continue
        determined += 1
        same = (n5 == n_named)
        coincide += int(same)
        print(f"{label:<38} {n5:>7} {str(n_named):>17} {('YES' if same else 'no'):>8}")

    print("-" * 74)
    print(f"\n{coincide}/{determined} policies ({100*coincide/determined:.0f}%) have literal recall@5 "
          f"reach 5/5 at EXACTLY the N where {NAMED_FAILURE} first enters the docked set.")

    out = RUNS_DIR / f"concentration_{SET_ID}.json"
    out.write_text(json.dumps({
        "set_id": SET_ID,
        "named_failure": NAMED_FAILURE,
        "policies": [{"label": l, "N_at_5of5": n5, "N_named_docked": nn, "coincide": (n5 == nn) if n5 is not None else None}
                      for l, n5, nn in policies],
        "n_determined": determined,
        "n_coincide": coincide,
        "coincidence_rate": coincide / determined if determined else None,
    }, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
