#!/usr/bin/env bash
# Executes REPRODUCTION.md steps 1-6 verbatim in a clean container and prints
# every command + its output. Exit non-zero on the first failure.
set -euo pipefail

PY=/app/backend/venv/bin/python
step() { printf '\n\033[1m### %s\033[0m\n' "$*"; }
run()  { printf '$ %s\n' "$*"; eval "$*"; }

cd /app

step "1. setup — verify Vina"
run "scripts/setup_vina.sh"
run "scripts/verify_vina.sh"

step "2. data — rebuild candidate sets and check the content hashes"
cd /app/backend/app
run "sha256sum funnel/datasets/cox2_candidates_v1.csv funnel/datasets/ace2_candidates_v1.csv"
run "$PY -m funnel.build_candidate_set --target cox2 2>&1 | grep -E 'unique molecules|content_sha256|wrote'"
run "$PY -m funnel.build_candidate_set --target ace2 2>&1 | grep -E 'unique molecules|content_sha256|wrote'"
echo '# expected content_sha256: cox2 9ae649ec19fe9a206e8bdbd3a2b43609e89623f8d713a511d05c0bd33c7d35af'
echo '#                          ace2 b55d875f1ad82fec5122cf54ce0730f41176621a1c617c2a59dd9296368f42ca'
run "sha256sum funnel/datasets/cox2_candidates_v1.csv funnel/datasets/ace2_candidates_v1.csv  # unchanged => deterministic rebuild"

step "3. baseline command — smoke test with --limit 2 (full run is ~2h; runs/baseline_cox2_v1.json is cached)"
run "$PY -m funnel.baseline --candidates funnel/datasets/cox2_candidates_v1.csv --set-id cox2_v1 --target cox2 --limit 2 --out /tmp/baseline_smoke.json 2>&1 | grep -E 'baseline [0-9]|mean=|jobs submitted|wall-clock|wrote'"

step "4. funnel — LOCAL prescreen then dock top-5 (20 jobs)"
run "$PY -m funnel.funnel --dry-run 2>&1 | grep -E 'run_id|<== dock|would dock'"
run "$PY -m funnel.funnel --out /app/runs/funnel_cox2_v1.json 2>&1 | grep -E 'funnel dock|mean=|jobs submitted|wall-clock|wrote'"

step "5. evaluation — funnel vs the CACHED baseline"
run "$PY -m funnel.evaluate --baseline /app/runs/baseline_cox2_v1.json --funnel /app/runs/funnel_cox2_v1.json 2>&1 | grep -vE 'InconsistentVersion|warnings.warn|scikit-learn.org|model_persist'"

step "6. offline sweep + frontier (no docking)"
run "$PY -m funnel.features 2>&1 | tail -1"
run "$PY -m funnel.sweep 2>&1 | grep -vE 'InconsistentVersion|warnings.warn|scikit|model_persist|Deprecat|Morgan|Database not|CORS|SUPABASE|Supabase|model_loader - INFO|main - INFO|services.db'"
run "$PY -m funnel.frontier 2>&1 | grep -vE 'InconsistentVersion|warnings.warn|scikit|model_persist|Deprecat|Morgan|Database not|CORS|SUPABASE|Supabase|model_loader - INFO|main - INFO|services.db'"

step "DONE — all steps completed"
