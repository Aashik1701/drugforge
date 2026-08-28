#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# run_funnel_eval.sh — build (if needed) the candidate set, run the funnel
# path, and evaluate it against the cached baseline reference artifact.
#
#   scripts/run_funnel_eval.sh                 # funnel + eval vs cached baseline
#   scripts/run_funnel_eval.sh --with-baseline # ALSO re-run the (expensive) baseline
#   scripts/run_funnel_eval.sh --dry-run       # funnel LOCAL stages only, no docking
#
# Requires: scripts/setup_vina.sh already run (backend/bin/vina present).
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_DIR="${REPO_ROOT}/backend/app"
PY="${REPO_ROOT}/backend/venv/bin/python"
RUNS="${REPO_ROOT}/runs"

[ -x "$PY" ] || { echo "no venv python at $PY — create backend/venv first" >&2; exit 1; }
"${SCRIPT_DIR}/verify_vina.sh" >/dev/null || { echo "run scripts/setup_vina.sh first" >&2; exit 1; }

WITH_BASELINE=0
DRY_RUN=0
for a in "${@:-}"; do
	case "$a" in
	--with-baseline) WITH_BASELINE=1 ;;
	--dry-run) DRY_RUN=1 ;;
	"") ;;
	*) echo "unknown arg: $a" >&2; exit 2 ;;
	esac
done

export COMPUTE_MODE=balanced
cd "$APP_DIR"

CSV="${APP_DIR}/funnel/datasets/cox2_candidates_v1.csv"
if [ ! -f "$CSV" ]; then
	echo ">>> building candidate set"
	"$PY" -m funnel.build_candidate_set
fi

if [ "$DRY_RUN" = 1 ]; then
	exec "$PY" -m funnel.funnel --dry-run
fi

if [ "$WITH_BASELINE" = 1 ]; then
	echo ">>> running BASELINE (expensive: M x 4 docks) -> runs/baseline_cox2_v1.json"
	"$PY" -m funnel.baseline --out "${RUNS}/baseline_cox2_v1.json"
fi

[ -f "${RUNS}/baseline_cox2_v1.json" ] || {
	echo "no cached baseline at runs/baseline_cox2_v1.json — re-run with --with-baseline" >&2
	exit 1
}

echo ">>> running FUNNEL -> runs/funnel_cox2_v1.json"
"$PY" -m funnel.funnel --out "${RUNS}/funnel_cox2_v1.json"

echo ">>> evaluating"
exec "$PY" -m funnel.evaluate \
	--baseline "${RUNS}/baseline_cox2_v1.json" \
	--funnel "${RUNS}/funnel_cox2_v1.json"
