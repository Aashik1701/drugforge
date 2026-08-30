"""
agents.plan_goals -- the six goal prompts for the Phase-4 planner evaluation,
PRE-REGISTERED before any planner run (same discipline as Passes 4-11).

Frozen once committed. The planner is shown ONLY `prompt`. Everything else here
is for the offline scorer in `agents.plan_eval` -- it never reaches the LLM.

`priority`   which frontier column this goal is really about.
`floor`      minimum acceptable value of `priority` for the goal to be "met"
             (None = the goal states no hard recall requirement; it is judged on
             the docks-vs-recall trade-off instead).
`spirit`     "cheap"    -> fewer docks is the point; losing some recall is fine.
             "recall"   -> hitting the recall bar is the point; docks are secondary.
             "balanced" -> should land near the recommended operating point.
"""

from __future__ import annotations

RECOMMENDED_N = 10  # the fixed heuristic the planner is measured against

GOALS: list[dict] = [
    {
        "id": "best_binder_cost_no_object",
        "prompt": (
            "Find the single best binder for this target. Cost is no object -- I "
            "want maximum confidence that the top-ranked candidate really is the "
            "strongest binder in the set."
        ),
        "priority": "recall10_tiecredit",
        "floor": 9,
        "spirit": "recall",
    },
    {
        "id": "top5_within_an_hour",
        "prompt": (
            "I need the top 5 candidates and I have about an hour of compute to "
            "spend on docking. Use the budget well."
        ),
        "priority": "recall5_tiecredit",
        "floor": None,
        "spirit": "balanced",
    },
    {
        "id": "good_candidates_cheaply",
        "prompt": (
            "Find some good candidates cheaply. I'm screening many candidate sets "
            "and cannot spend much compute on any one of them."
        ),
        "priority": "recall10_tiecredit",
        "floor": None,
        "spirit": "cheap",
    },
    {
        "id": "recover_8_of_top_10",
        "prompt": (
            "I need to recover at least 8 of the true top-10 binders by docking "
            "score. Spend whatever docking budget that takes."
        ),
        "priority": "recall10_literal",
        "floor": 8,
        "spirit": "recall",
    },
    {
        "id": "solid_shortlist_reasonable_cost",
        "prompt": (
            "Give me a solid shortlist with a reasonable amount of compute -- "
            "nothing extreme in either direction."
        ),
        "priority": "recall10_tiecredit",
        "floor": None,
        "spirit": "balanced",
    },
    {
        "id": "quick_exploratory_look",
        "prompt": (
            "Quick exploratory look. I just want a rough sense of which few "
            "molecules are worth a closer look later. Keep compute to a minimum."
        ),
        "priority": "recall10_tiecredit",
        "floor": None,
        "spirit": "cheap",
    },
]

assert len(GOALS) == 6, "cap is six goals"
assert len({g['id'] for g in GOALS}) == 6, "goal ids must be unique"
