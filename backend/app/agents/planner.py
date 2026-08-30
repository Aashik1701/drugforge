"""
agents.planner -- the Phase-4 LLM budget planner.

One narrow decision: read a discovery goal + candidate-set metadata + the cached
recall-vs-budget frontier, and choose the docking budget N. Emit a tool sequence
in the POST /api/agent/runs format. Does NOT execute, does NOT do chemistry,
does NOT choose thresholds/weights, does NOT see docking results. See
docs/development/agent-planner.md for the full scope boundary.

Everything the LLM influences is a single integer, and that integer is clamped
and its tool sequence re-validated through the Phase-3 submission validator in
code (not in the prompt) before it can spend a dock.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from funnel.service import FROZEN_POLICY_ID, MAX_BUDGET_N, list_sets, load_frontier

logger = logging.getLogger("agents.planner")

RECOMMENDED_N = 10
PLANNER_MAX_ATTEMPTS = int(os.getenv("PLANNER_MAX_ATTEMPTS", "2"))

# Prompt version -- bump on every wording change; the eval report records which
# version produced the reported numbers. v1 is the pre-registered wording.
PROMPT_VERSION = "v1"


class PlannerUnavailable(RuntimeError):
    """No LLM provider configured -> HTTP 503, same shape as /api/chat/ask."""


class PlannerError(ValueError):
    """Any other planning failure -> HTTP 4xx. `status` + `detail` carry the
    response; nothing is executed."""

    def __init__(self, message: str, status: int = 400, detail: object | None = None):
        super().__init__(message)
        self.status = status
        self.detail = detail if detail is not None else message


# ---------------------------------------------------------------------------
# frontier helpers  (read-only; the curve produced by eleven prior passes)
# ---------------------------------------------------------------------------
def _row_for(rows: list[dict], n: int) -> dict:
    best = None
    for r in rows:
        if r["N"] == n:
            return r
        if best is None or abs(r["N"] - n) < abs(best["N"] - n):
            best = r
    return best


def _first_n_to_reach(rows: list[dict], key: str) -> Optional[int]:
    """First N at which `key` hits its maximum value over the whole curve."""
    if not rows:
        return None
    peak = max(r[key] for r in rows)
    for r in rows:
        if r[key] >= peak:
            return r["N"]
    return None


def _frontier_table(rows: list[dict]) -> str:
    head = "  N  docked  jobs  r5_lit  r5_tie  r10_lit  r10_tie  est_dock_s  speedup"
    out = [head]
    for r in rows:
        out.append(
            f"{r['N']:>3}  {r['docked']:>6}  {r['jobs']:>4}  {r['recall5_literal']:>6}  "
            f"{r['recall5_tiecredit']:>6}  {r['recall10_literal']:>7}  {r['recall10_tiecredit']:>7}  "
            f"{r['est_dock_wall_s']:>10.0f}  {r['speedup_vs_full']:>6.1f}x"
        )
    return "\n".join(out)


def frontier_context(rows: list[dict], chosen_n: int) -> dict:
    return {
        "recommended_n": RECOMMENDED_N,
        "n_rows": len(rows),
        "chosen_row": _row_for(rows, chosen_n),
        "recommended_row": _row_for(rows, RECOMMENDED_N),
        "knee_literal_r10": _first_n_to_reach(rows, "recall10_literal"),
        "knee_tiecredit_r10": _first_n_to_reach(rows, "recall10_tiecredit"),
        "knee_literal_r5": _first_n_to_reach(rows, "recall5_literal"),
    }


# ---------------------------------------------------------------------------
# clamping  (enforced in code, not in the prompt)
# ---------------------------------------------------------------------------
def clamp_n(raw_n: int, set_size: int) -> tuple[int, dict]:
    """chosen_n is bound by the SAME ceiling the funnel's own budget_n uses
    (FUNNEL_MAX_BUDGET_N) and by the candidate-set size, and floored at 1."""
    ceiling = min(MAX_BUDGET_N, set_size)
    n = max(1, min(int(raw_n), ceiling))
    return n, {
        "raw_n": raw_n,
        "chosen_n": n,
        "ceiling": ceiling,
        "set_size": set_size,
        "max_budget_n": MAX_BUDGET_N,
        "clamped": n != raw_n,
    }


# ---------------------------------------------------------------------------
# prompt  (PROMPT_VERSION -- logged in the eval report)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a planning component in a computational drug-discovery pipeline. "
    "Your ONLY job is to choose one number: N, the docking budget -- how many of "
    "the cheap-prescreen survivors get docked with AutoDock Vina (4 seeds each). "
    "You do not do chemistry, you do not pick filters or scoring weights, you do "
    "not see any docking results. You choose N and explain why in a sentence or "
    "two. Answer with a single JSON object and nothing else."
)


def build_prompt(goal: str, set_meta: dict, rows: list[dict]) -> str:
    fc = frontier_context(rows, RECOMMENDED_N)
    return f"""GOAL (from the researcher):
{goal.strip()}

CANDIDATE SET:
  id: {set_meta['set_id']}
  molecules: {set_meta['size']}  (of which {set_meta['n_reference']} are reference/known actives)
  content hash: {set_meta['content_sha256'][:16]}...

CACHED RECALL-vs-BUDGET FRONTIER for this set (offline, from prior research):
  Each row: docking budget N, molecules docked, Vina jobs (= docked x 4 seeds),
  recall@5 and recall@10 of the full-baseline ranking -- "lit" = exact top-k
  overlap, "tie" = credit for candidates tied with a true top-k within docking
  noise. est_dock_s = estimated docking wall-clock seconds. speedup vs docking
  everything.

{_frontier_table(rows)}

The fixed heuristic operating point is N={RECOMMENDED_N} (recommended by prior
research). Recall@10 tie-credited reaches its maximum first at N={fc['knee_tiecredit_r10']};
recall@10 literal at N={fc['knee_literal_r10']}.

Choose N for THIS goal. If N={RECOMMENDED_N} is the best fit, choose it.
Respond with exactly this JSON and nothing else:
{{"chosen_n": <integer between 1 and {min(MAX_BUDGET_N, set_meta['size'])}>, "rationale": "<one or two sentences>"}}"""


# ---------------------------------------------------------------------------
# response parsing  (bounded retries, fail cleanly)
# ---------------------------------------------------------------------------
def parse_plan_response(text: str) -> dict:
    """Extract {"chosen_n": int, "rationale": str}. Raises ValueError on any
    deviation -- the caller retries up to PLANNER_MAX_ATTEMPTS, then 422s."""
    if not text or not text.strip():
        raise ValueError("empty response")
    cleaned = text.strip()
    # strip ```json ... ``` fences if present
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.MULTILINE).strip()
    m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not m:
        raise ValueError(f"no JSON object in response: {text[:200]!r}")
    obj = json.loads(m.group(0))  # ValueError/JSONDecodeError on bad JSON
    if "chosen_n" not in obj:
        raise ValueError("JSON has no 'chosen_n'")
    try:
        n = int(obj["chosen_n"])
    except (TypeError, ValueError):
        raise ValueError(f"'chosen_n' is not an integer: {obj['chosen_n']!r}")
    if n < 1:
        raise ValueError(f"'chosen_n' must be >= 1, got {n}")
    rationale = str(obj.get("rationale", "")).strip()
    if not rationale:
        raise ValueError("'rationale' is empty")
    return {"chosen_n": n, "rationale": rationale}


# ---------------------------------------------------------------------------
# the plan
# ---------------------------------------------------------------------------
def _resolve_set_meta(candidate_set_id: str) -> dict:
    for s in list_sets():
        if s["set_id"] == candidate_set_id:
            return s
    raise PlannerError(
        f"unknown candidate_set_id '{candidate_set_id}'; see GET /api/funnel/sets",
        status=404,
    )


def _validate_emitted_sequence(tool_sequence: list[dict]) -> None:
    """Run the planner's own output through the Phase-3 submission validator.
    A malformed plan is a 400 here, never a run."""
    from agents.service import AgentInputError, clamp_budget, validate_submission
    from schemas.agent import AgentToolRequest

    effective, _, _ = clamp_budget(None)
    try:
        reqs = [AgentToolRequest(**step) for step in tool_sequence]
        validate_submission(reqs, effective)
    except AgentInputError as exc:
        raise PlannerError(
            f"planner emitted an invalid tool sequence: {exc}",
            status=400,
            detail={"reason": str(exc), "planner_detail": getattr(exc, "detail", None),
                    "tool_sequence": tool_sequence},
        )
    except Exception as exc:  # pydantic ValidationError etc.
        raise PlannerError(
            f"planner emitted a structurally invalid tool sequence: {exc}", status=400,
            detail={"reason": str(exc), "tool_sequence": tool_sequence},
        )


def make_plan(goal: str, candidate_set_id: str, target: str, *, provider=None) -> dict:
    """Produce a plan. Never executes. Raises PlannerUnavailable (503) or
    PlannerError (4xx)."""
    if provider is None:
        from services.llm import get_provider
        provider = get_provider()
    if provider is None:
        raise PlannerUnavailable("AI engine not configured. Set GEMINI_API_KEY in backend .env")

    target = (target or "").strip().lower()
    if target not in ("cox2", "ace2"):
        raise PlannerError("target must be 'cox2' or 'ace2'", status=400)

    set_meta = _resolve_set_meta(candidate_set_id)
    rows = load_frontier(candidate_set_id)
    if not rows:
        raise PlannerError(
            f"no cached frontier for '{candidate_set_id}' (runs/frontier_{candidate_set_id}.csv); "
            f"the planner reasons over the frontier and cannot proceed without it",
            status=404,
        )

    prompt = build_prompt(goal, set_meta, rows)
    model = getattr(provider, "_model", "unknown")

    parsed = None
    last_err = None
    for attempt in range(1, PLANNER_MAX_ATTEMPTS + 1):
        raw = provider.generate(prompt, system_prompt=SYSTEM_PROMPT)
        try:
            parsed = parse_plan_response(raw)
            logger.info("planner_llm_attempt n=%d parse_ok=1 chosen_n=%d", attempt, parsed["chosen_n"])
            break
        except ValueError as exc:
            last_err = str(exc)
            logger.warning("planner_llm_attempt n=%d parse_ok=0 error=%s raw=%r",
                           attempt, last_err, (raw or "")[:200])
    if parsed is None:
        raise PlannerError(
            f"LLM returned unparseable output after {PLANNER_MAX_ATTEMPTS} attempt(s): {last_err}",
            status=422,
            detail={"attempts": PLANNER_MAX_ATTEMPTS, "last_error": last_err,
                    "prompt_version": PROMPT_VERSION},
        )

    chosen_n, clamp = clamp_n(parsed["chosen_n"], set_meta["size"])
    tool_sequence = [{
        "name": "run_funnel",
        "args": {
            "candidate_set_id": candidate_set_id,
            "target": target,
            "budget_n": chosen_n,
            "policy_id": FROZEN_POLICY_ID,
        },
    }]
    _validate_emitted_sequence(tool_sequence)

    return {
        "goal": goal,
        "candidate_set_id": candidate_set_id,
        "target": target,
        "chosen_n": chosen_n,
        "rationale": parsed["rationale"],
        "tool_sequence": tool_sequence,
        "frontier_context": frontier_context(rows, chosen_n),
        "clamp": clamp,
        "llm": {
            "provider": os.getenv("LLM_PROVIDER", "gemini"),
            "model": model,
            "attempts": attempt,
            "parse_ok": True,
            "prompt_version": PROMPT_VERSION,
        },
    }
