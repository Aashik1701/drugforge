# Archived: Legacy Flask Backend

This directory preserves the **original Flask-based backend** and its associated
deployment tooling, superseded by the current FastAPI backend in `backend/`.

`backend/main.py` states this explicitly: *"Migrated from deprecated Flask
backend to modern async FastAPI."* This archive is the retired half of that
migration — kept for reference, not for active use.

## What's here

| File | Was used for |
|---|---|
| `app.py` | The original Flask API server (routes, model loading, all in one file). Replaced by `backend/app/main.py` + `backend/app/routers/`. |
| `backendML_README.md` | Documentation for the Flask app above. |
| `requirements.txt` | Python deps for the Flask app (Flask, Flask-CORS, gunicorn, ...). Replaced by `backend/requirements.txt`. |
| `Dockerfile`, `Dockerfile.production` | Built the Flask app (`gunicorn app:app`) — one even referenced a `src/app.py` path that no longer exists in this repo. |
| `Dockerfile.frontend`, `nginx.conf`, `docker-compose.yml`, `docker-compose.dev.yml` | A self-hosted nginx + Flask deployment stack, proxying to the Flask app on port 5000. |
| `requirements-root-flask.txt` | Root-level Flask deps from an even earlier prototype (imported `src/app.py`, `src/solubility_model.pkl` — neither exists anymore). |
| `setup.sh`, `test-system.sh` | Dev setup / smoke-test scripts that instructed developers to `cd backendML && python app.py` — the Flask app, not the current FastAPI backend. |
| `project.config.json` | Project metadata describing the Flask-era layout. |

## Why archived, not deleted

These files still document a real, working stage of the project's history and
its deployment reasoning. But they were actively misleading as live
instructions: a new developer following `setup.sh` would start the wrong
backend, on the wrong port, disconnected from what the frontend
(`src/services/api.js`, now `frontend/src/services/api.js`) and the real
deployment (`backend/render.yaml`, `vercel.json`) actually use.

## Current, active equivalents

- Backend: `backend/` (FastAPI, deployed via `backend/render.yaml` on Render)
- Frontend: `frontend/` (Vite/React, deployed via `frontend/vercel.json` on Vercel)
- Dev setup: see the root `README.md`
