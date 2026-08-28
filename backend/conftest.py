"""
Makes `app/` importable as a top-level package for tests, matching how
`uvicorn main:app` is run from inside `app/` in development and in
render.yaml. Lets tests/test_main.py keep doing `from main import app`
unchanged after the routers/schemas/services/utils/main.py move into app/.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _clean_job_store():
    """
    JobStore's SQLite file (backend/app/jobs/jobs.db) is a real, persistent
    file shared across the dev server, manual testing, AND every pytest
    invocation — without this, a job left 'queued' from a previous test run
    (or from manually poking the API) silently occupies the concurrency
    slot and breaks docking tests that assume a clean start, in a way that
    only shows up on a second run, not the first. Deletes and recreates the
    schema fresh at the start of every test session.
    """
    import main

    if main.job_store.db_path.exists():
        main.job_store.db_path.unlink()
    main.job_store._init_schema()
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _run_app_lifespan(_clean_job_store):
    """
    httpx's ASGITransport does NOT run FastAPI's lifespan by default, so
    without this, model_loader is never populated and every test hitting a
    prediction endpoint silently gets 503 regardless of whether the code
    under test is correct — the original test suite never noticed because
    it only asserted validation-error paths (400/422) that don't touch
    models. Runs main.py's real startup/shutdown functions directly.
    Depends on _clean_job_store so the DB is reset before startup logs
    queue state.
    """
    from main import startup_event, shutdown_event

    await startup_event()
    yield
    await shutdown_event()
