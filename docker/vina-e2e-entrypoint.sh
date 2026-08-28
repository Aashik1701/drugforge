#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# vina-e2e-entrypoint.sh — boot API + LocalWorker, run a real docking job,
# assert the result is real. Exit non-zero on any failure.
# ---------------------------------------------------------------------------
set -euo pipefail

cd /app/backend/app

echo "=================================================================="
echo " DrugForge Vina end-to-end test (clean container)"
echo "=================================================================="
scripts_dir=/app/scripts
"$scripts_dir/verify_vina.sh"
echo "------------------------------------------------------------------"

# --- 1. Start the two backend processes --------------------------------
python -m uvicorn main:app --host 127.0.0.1 --port 5001 --log-level warning &
API_PID=$!
python -m jobs.workers.local_worker &
WORKER_PID=$!

cleanup() {
	echo "--- shutting down (api=$API_PID worker=$WORKER_PID) ---"
	kill "$API_PID" "$WORKER_PID" 2>/dev/null || true
	wait 2>/dev/null || true
}
trap cleanup EXIT

# --- 2. Wait for /health ---------------------------------------------
echo -n "waiting for API health"
for _ in $(seq 1 60); do
	if curl -sf http://127.0.0.1:5001/health >/dev/null 2>&1; then
		echo " — up"
		break
	fi
	echo -n "."
	sleep 1
done

echo "------------------------------------------------------------------"
echo "GET /health:"
curl -s http://127.0.0.1:5001/health | python -m json.tool
echo "------------------------------------------------------------------"

# Fail early if the worker died on startup.
if ! kill -0 "$WORKER_PID" 2>/dev/null; then
	echo "FATAL: LocalWorker process exited during startup" >&2
	exit 1
fi

# --- 3. Submit + poll + assert (real docking) ----------------------
python /app/docker/vina_e2e_check.py
