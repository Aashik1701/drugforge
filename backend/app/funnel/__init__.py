"""
funnel — the computational funnel as a real code path, plus a brute-force
baseline and an evaluation harness that compares them.

No LLM, no planner. The funnel's filter thresholds and ranking function live
in ONE place (`funnel.policy.FunnelPolicy`) — that dataclass is the seam an
LLM planner replaces later without touching anything else.

Both execution paths (`funnel.baseline`, `funnel.funnel`) emit the SAME run
record shape (`funnel.schema.RunRecord`) to `runs/`. `funnel.evaluate` diffs
two records and prints the headline comparison.
"""
