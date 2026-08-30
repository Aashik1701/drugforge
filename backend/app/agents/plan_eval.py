"""
agents.plan_eval -- Phase-4 offline evaluation.

The narrow claim under test: given a discovery goal and a candidate set, does an
LLM pick a docking budget N BETTER than the fixed N=10 heuristic? "Better" =
reaches the goal's stated recall requirement at fewer docks, OR higher recall at
the same docks. Scored against the cached frontier CSV -- the same baseline
every prior pass used. No new docking.

  cd backend/app && ../venv/bin/python -m agents.plan_eval            # full (needs GEMINI_API_KEY)
  cd backend/app && ../venv/bin/python -m agents.plan_eval --frontier-only   # the N-vs-N=10 reference table, no LLM

Writes runs/plan_eval_v1.json  (+ prints the tables that go in the report).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import time
from collections import Counter
from pathlib import Path

from agents.plan_goals import GOALS, RECOMMENDED_N
from agents.planner import (
    PROMPT_VERSION, PlannerError, PlannerUnavailable, _first_n_to_reach, _row_for, make_plan,
)
from funnel.service import load_frontier

TARGETS = {"cox2": "cox2_v1", "ace2": "ace2_v1"}
REPEATS = 3
RUNS_DIR = Path(__file__).resolve().parents[3] / "runs"

# The configured key is on the Gemini free tier (5 requests/min). Pace calls so a
# 36-call run stays under that -- this is rate-limit compliance, not a tuning
# knob. Overridable via PLAN_EVAL_CALL_SPACING_S.
CALL_SPACING_S = float(os.getenv("PLAN_EVAL_CALL_SPACING_S", "20"))
_last_call = [0.0]


def _paced_make_plan(prompt, sid, tname):
    """make_plan with client-side pacing (the configured key is Gemini free
    tier, ~5-20 req/min) + waits on a 429 using the server's own retry hint.
    NOT the unparseable-output retry -- that cap lives in the planner, untouched.
    The LLM parameters (model, temperature) are never changed."""
    for attempt in range(10):
        wait = CALL_SPACING_S - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
        try:
            return make_plan(prompt, sid, tname)
        except Exception as exc:  # google.genai ClientError 429
            msg = str(exc)
            if "RESOURCE_EXHAUSTED" not in msg and "429" not in msg:
                raise
            m = re.search(r"retry in ([0-9.]+)s", msg)
            delay = min(float(m.group(1)) if m else 30.0, 90.0)
            print(f"  [429] rate-limited; sleeping {delay + 3:.0f}s (wait {attempt + 1}/10)", flush=True)
            time.sleep(delay + 3)
            _last_call[0] = time.monotonic()
    raise RuntimeError("still rate-limited after 10 waits -- free-tier quota likely exhausted")

METRICS = ("recall5_literal", "recall5_tiecredit", "recall10_literal", "recall10_tiecredit")


def score_n(rows: list[dict], n: int) -> dict:
    r = _row_for(rows, n)
    return {
        "N": r["N"], "docked": r["docked"], "jobs": r["jobs"],
        "est_dock_wall_s": r["est_dock_wall_s"], "speedup_vs_full": r["speedup_vs_full"],
        **{m: r[m] for m in METRICS},
    }


def judge(goal: dict, planner_s: dict, fixed_s: dict) -> dict:
    """Compare the planner's N to fixed N=10 for THIS goal. Honest framing: the
    frontier is monotone, so 'strictly dominates' is rare; most differences are
    trade-offs along the curve, which we label as aligned-with-goal or not."""
    pm = goal["priority"]
    floor = goal["floor"]
    p_rec, f_rec = planner_s[pm], fixed_s[pm]
    p_dock, f_dock = planner_s["docked"], fixed_s["docked"]

    p_meets = (floor is not None) and p_rec >= floor
    f_meets = (floor is not None) and f_rec >= floor

    # strict Pareto on (docks lower-better, priority-recall higher-better)
    if p_dock <= f_dock and p_rec >= f_rec and (p_dock < f_dock or p_rec > f_rec):
        pareto = "planner_dominates"
    elif p_dock >= f_dock and p_rec <= f_rec and (p_dock > f_dock or p_rec < f_rec):
        pareto = "fixed_dominates"
    else:
        pareto = "trade_off"

    # does the move serve what the goal asked for?
    if floor is not None:
        if p_meets and not f_meets:
            verdict = "planner_better"        # meets a floor N=10 misses
        elif p_meets and f_meets and p_dock < f_dock:
            verdict = "planner_better"        # meets the same floor for cheaper
        elif not p_meets and f_meets:
            verdict = "planner_worse"         # misses a floor N=10 meets
        elif p_meets == f_meets and p_dock == f_dock:
            verdict = "equivalent"
        else:
            verdict = "trade_off"
    else:
        spirit = goal["spirit"]
        if p_dock == f_dock:
            verdict = "equivalent"
        elif spirit == "cheap":
            verdict = "planner_better" if p_dock < f_dock else "planner_worse"
        elif spirit == "balanced":
            # near N=10 either way is fine; only flag a big swing
            verdict = "equivalent" if abs(planner_s["N"] - RECOMMENDED_N) <= 3 else "trade_off"
        else:  # recall
            verdict = "planner_better" if p_rec > f_rec else "planner_worse" if p_rec < f_rec else "equivalent"

    return {
        "priority_metric": pm, "floor": floor,
        "planner_priority_recall": p_rec, "fixed_priority_recall": f_rec,
        "planner_docked": p_dock, "fixed_docked": f_dock,
        "planner_meets_floor": p_meets, "fixed_meets_floor": f_meets,
        "pareto": pareto, "verdict": verdict,
    }


def _frontier_only() -> None:
    """The N-vs-N=10 reference: what recall each candidate N buys on each target.
    Needs no LLM -- this is the cached baseline the planner is scored against."""
    probe = [1, 2, 3, 5, 8, 10, 13, 15, 20, 24, 30, 32, 36, 45]
    for tname, sid in TARGETS.items():
        rows = load_frontier(sid)
        fixed = score_n(rows, RECOMMENDED_N)
        print(f"\n=== {sid}  (frontier reference; fixed N={RECOMMENDED_N} row marked *) ===")
        print(f"{'N':>3} {'dock':>4} {'jobs':>4} {'r5_lit':>6} {'r5_tie':>6} "
              f"{'r10_lit':>7} {'r10_tie':>7} {'dock_s':>7} {'speedup':>7}")
        for n in probe:
            s = score_n(rows, n)
            star = " *" if s["N"] == RECOMMENDED_N else "  "
            print(f"{s['N']:>3} {s['docked']:>4} {s['jobs']:>4} {s['recall5_literal']:>6} "
                  f"{s['recall5_tiecredit']:>6} {s['recall10_literal']:>7} {s['recall10_tiecredit']:>7} "
                  f"{s['est_dock_wall_s']:>7.0f} {s['speedup_vs_full']:>6.1f}x{star}")
        print(f"  fixed N=10: r10_lit={fixed['recall10_literal']}/10  r10_tie={fixed['recall10_tiecredit']}/10  "
              f"r5_lit={fixed['recall5_literal']}/5  r5_tie={fixed['recall5_tiecredit']}/5  "
              f"docks={fixed['docked']}  ~{fixed['est_dock_wall_s']:.0f}s")


def stub_choose_n(goal_text: str, rows: list[dict]) -> tuple[int, str]:
    """A deliberately dumb, DETERMINISTIC curve-reader -- NOT the LLM. Used with
    --stub when GEMINI_API_KEY is unavailable, to exercise the scoring/verdict
    pipeline and show what plain keyword matching + the frontier knee can do.
    This is the 'fixed heuristic reading the same curve' Task 4 hypothesises."""
    t = goal_text.lower()
    knee_lit = _first_n_to_reach(rows, "recall10_literal")
    knee_tie = _first_n_to_reach(rows, "recall10_tiecredit")
    cheap = any(w in t for w in ("cheap", "cheaply", "minimum", "minimal", "quick",
                                 "cannot spend", "can't spend", "rough sense", "closer look later"))
    max_effort = any(w in t for w in ("cost is no object", "spend whatever", "spend what it takes",
                                      "maximum confidence", "at least 8"))
    if cheap:
        return 3, "goal signals minimal compute; take the cheapest useful point"
    if max_effort:
        return knee_lit, f"goal signals spend-what-it-takes; go to the literal-recall knee (N={knee_lit})"
    if "top 5" in t or "hour" in t:
        return knee_tie, f"moderate goal; the tie-credited recall knee at N={knee_tie}"
    return RECOMMENDED_N, "no strong signal either way; use the recommended operating point"


def _load_stub_choices() -> dict:
    """{(set_id, goal_id): stub_modal_n} from a prior --stub run, if present."""
    p = RUNS_DIR / "plan_eval_v1_stub.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    out = {}
    for sid, block in d.get("targets", {}).items():
        for g in block.get("goals", []):
            if "chosen_n_modal" in g:
                out[(sid, g["goal_id"])] = g["chosen_n_modal"]
    return out


def run_eval(use_stub: bool = False) -> dict:
    out: dict = {"prompt_version": PROMPT_VERSION, "recommended_n": RECOMMENDED_N,
                 "repeats": REPEATS, "chooser": "stub_keyword_curve_reader" if use_stub else "llm",
                 "targets": {}}
    tallies: Counter = Counter()
    stub_choices = {} if use_stub else _load_stub_choices()

    for tname, sid in TARGETS.items():
        rows = load_frontier(sid)
        fixed_s = score_n(rows, RECOMMENDED_N)
        per_goal = []
        for g in GOALS:
            chosen = []
            rationales = []
            errors = []
            for _ in range(REPEATS):
                try:
                    if use_stub:
                        n, why = stub_choose_n(g["prompt"], rows)
                        chosen.append(n)
                        rationales.append(why)
                    else:
                        plan = _paced_make_plan(g["prompt"], sid, tname)
                        chosen.append(plan["chosen_n"])
                        rationales.append(plan["rationale"])
                except (PlannerUnavailable, PlannerError, RuntimeError) as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
            if not chosen:
                per_goal.append({"goal_id": g["id"], "error": errors[0] if errors else "no result"})
                continue
            modal_n = Counter(chosen).most_common(1)[0][0]
            planner_s = score_n(rows, modal_n)
            j = judge(g, planner_s, fixed_s)
            tallies[j["verdict"]] += 1
            entry = {
                "goal_id": g["id"], "spirit": g["spirit"], "prompt": g["prompt"],
                "chosen_n_runs": chosen,
                "chosen_n_modal": modal_n,
                "determinism_spread": {"min": min(chosen), "max": max(chosen),
                                       "unique": sorted(set(chosen)),
                                       "stdev": round(statistics.pstdev(chosen), 2) if len(chosen) > 1 else 0.0},
                "rationale_sample": rationales[0] if rationales else None,
                "rationales_all": rationales,
                "planner_score": planner_s, "fixed_score": fixed_s,
                "judgement": j,
            }
            stub_n = stub_choices.get((sid, g["id"]))
            if stub_n is not None:
                entry["stub_n"] = stub_n
                entry["stub_score"] = score_n(rows, stub_n)
                entry["judgement_vs_stub"] = judge(g, planner_s, score_n(rows, stub_n))
            per_goal.append(entry)
            print(f"  {sid:9} {g['id']:<32} runs={chosen} spread={entry['determinism_spread']['unique']}")
            # checkpoint so a mid-run rate-limit crash doesn't lose completed cells
            out["targets"][sid] = {"fixed_score": fixed_s, "goals": per_goal}
            (RUNS_DIR / "plan_eval_v1.partial.json").write_text(json.dumps(out, indent=2))
        out["targets"][sid] = {"fixed_score": fixed_s, "goals": per_goal}

    out["verdict_tally"] = dict(tallies)
    return out


def _print_report(out: dict) -> None:
    for sid, block in out["targets"].items():
        print(f"\n================  {sid}  ================")
        print(f"{'goal':<32} {'N (3 runs)':<14} {'mdl':>3} {'spread':>10} "
              f"{'vs N=10':>15} {'stub':>4} {'vs stub':>15}")
        for gr in block["goals"]:
            if "error" in gr:
                print(f"{gr['goal_id']:<32} {gr['error'][:70]}")
                continue
            j = gr["judgement"]
            sp = gr["determinism_spread"]
            runs = ",".join(str(x) for x in gr["chosen_n_runs"])
            spread = f"{sp['min']}-{sp['max']} sd{sp['stdev']}"
            vs_stub = gr.get("judgement_vs_stub", {}).get("verdict", "-")
            stub_n = gr.get("stub_n", "-")
            print(f"{gr['goal_id']:<32} {runs:<14} {gr['chosen_n_modal']:>3} {spread:>10} "
                  f"{j['verdict']:>15} {str(stub_n):>4} {vs_stub:>15}")
    print(f"\nverdict tally vs N=10: {out['verdict_tally']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frontier-only", action="store_true",
                    help="print the N-vs-N=10 frontier reference and exit (no LLM)")
    ap.add_argument("--stub", action="store_true",
                    help="use the deterministic keyword curve-reader instead of the LLM "
                         "(for when GEMINI_API_KEY is unavailable)")
    args = ap.parse_args()

    if args.frontier_only:
        _frontier_only()
        return 0

    out = run_eval(use_stub=args.stub)
    _print_report(out)
    if not out["verdict_tally"] and not args.stub:
        print("\nNo LLM results -- GEMINI_API_KEY is unset. Set it and re-run "
              "`python -m agents.plan_eval` for the real planner numbers. "
              "`--stub` and `--frontier-only` run without a key.")
        return 1
    suffix = "_stub" if args.stub else ""
    path = RUNS_DIR / f"plan_eval_v1{suffix}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
