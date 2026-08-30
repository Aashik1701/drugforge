"""
Funnel service tests (POST/GET /api/funnel/*).

Real Vina execution is not exercised -- like test_compute_fabric.py, the
in-process ASGI client has no LocalWorker, so a funnel run's child docking jobs
sit `queued`. That is exactly what lets these tests cover orchestration, stage
progression, gating, and cancellation without the binary. The full end-to-end
run against a live worker is pasted in the Pass-12 report / CHANGELOG.

Run:  cd backend && python -m pytest tests/test_funnel_service.py -v
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from funnel import service


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _fast_polls_and_isolation(monkeypatch):
    """Speed the executor's poll loops; isolate from heavy jobs another test
    file may have left in the shared jobs.db (it is wiped only once per session).
    A stale queued `docking` job would keep every HEAVY_LOCAL gate closed."""
    monkeypatch.setattr(service, "DOCK_POLL_INTERVAL", 0.2)
    monkeypatch.setattr(service, "COMPUTE_REJECT_SLEEP", 0.2)
    from main import job_store

    async def _neutralise():
        for jt in ("funnel", "docking"):
            for j in await job_store.list_jobs(job_type=jt, limit=200):
                if j.status.value in ("queued", "running"):
                    await job_store.cancel_job(j.id)

    await _neutralise()
    yield
    for j in await job_store.list_jobs(job_type="funnel", limit=50):
        if j.status.value in ("queued", "running"):
            await service.cancel_run(j.id)
    await _neutralise()
    await asyncio.sleep(0.3)


async def _mode(client, mode):
    r = await client.post("/api/compute/mode", json={"mode": mode})
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------
# read-only endpoints
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sets(client):
    r = await client.get("/api/funnel/sets")
    assert r.status_code == 200
    by_id = {s["set_id"]: s for s in r.json()}
    assert "cox2_v1" in by_id and by_id["cox2_v1"]["size"] == 45
    assert len(by_id["cox2_v1"]["content_sha256"]) == 64


@pytest.mark.asyncio
async def test_frontier(client):
    r = await client.get("/api/funnel/frontier/cox2_v1")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert any(row["N"] == 10 and row["recall10_literal"] == 5 for row in rows)
    assert (await client.get("/api/funnel/frontier/does_not_exist")).status_code == 404


# --------------------------------------------------------------------------
# start-time guards (no Job row should be created for any of these)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_budget_bound(client):
    await _mode(client, "balanced")
    r = await client.post("/api/funnel/start",
                          json={"candidate_set_id": "cox2_v1", "target": "cox2", "budget_n": 1000})
    assert r.status_code == 413
    assert "budget_n" in r.json()["error"]


@pytest.mark.asyncio
async def test_frozen_policy_only(client):
    r = await client.post("/api/funnel/start",
                          json={"candidate_set_id": "cox2_v1", "target": "cox2",
                                "budget_n": 3, "policy_id": "my_custom_policy"})
    assert r.status_code == 400
    assert "v7_binding_weak_cox2" in r.json()["error"]


@pytest.mark.asyncio
async def test_invalid_smiles_upload_reports_counts(client):
    r = await client.post("/api/funnel/start",
                          json={"smiles": ["CCO", "definitely not a molecule", "c1ccccc1"],
                                "target": "cox2", "budget_n": 1})
    assert r.status_code == 400
    payload = r.json()["error"]          # main.py wraps HTTPException.detail under "error"
    assert payload["n_valid"] == 2
    assert len(payload["parse_failures"]) == 1
    assert payload["parse_failures"][0]["index"] == 1


@pytest.mark.asyncio
async def test_upload_size_cap(client):
    r = await client.post("/api/funnel/start",
                          json={"smiles": ["CCO"] * (service.MAX_UPLOAD + 1),
                                "target": "cox2", "budget_n": 1})
    assert r.status_code == 413


@pytest.mark.asyncio
async def test_exactly_one_input(client):
    both = await client.post("/api/funnel/start",
                             json={"candidate_set_id": "cox2_v1", "smiles": ["CCO"],
                                   "target": "cox2", "budget_n": 1})
    assert both.status_code == 400
    neither = await client.post("/api/funnel/start", json={"target": "cox2", "budget_n": 1})
    assert neither.status_code == 400


@pytest.mark.asyncio
async def test_docking_disabled_rejected_via_compute_router(client):
    await _mode(client, "battery-saver")
    try:
        r = await client.post("/api/funnel/start",
                              json={"candidate_set_id": "cox2_v1", "target": "cox2", "budget_n": 3})
        assert r.status_code == 503
        assert "battery-saver" in r.json()["error"]
    finally:
        await _mode(client, "balanced")


# --------------------------------------------------------------------------
# a real run: stage progression, then cancellation mid-dock
# --------------------------------------------------------------------------
async def _poll_until(client, run_id, pred, timeout=25.0):
    import time
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        last = (await client.get(f"/api/funnel/status/{run_id}")).json()
        if pred(last):
            return last
        await asyncio.sleep(0.3)
    raise AssertionError(f"condition not met in {timeout}s; last status = {last}")


@pytest.mark.asyncio
async def test_run_progresses_to_docking_then_cancels(client):
    await _mode(client, "balanced")
    r = await client.post("/api/funnel/start",
                          json={"smiles": ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "c1ccncc1"],
                                "target": "cox2", "budget_n": 2})
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    assert r.json()["candidates_in"] == 3 and r.json()["budget_n"] == 2

    # screening -> prescreen -> docking; a child dock is submitted, none completes (no worker)
    st = await _poll_until(client, run_id, lambda s: s["stage"] == "docking")
    assert st["status"] == "running"
    assert st["stage_survivors"], "screening stage counts must be reported"
    assert len(st["prescreen_selected"]) == 2
    st = await _poll_until(client, run_id, lambda s: s["docks_submitted"] >= 1)
    assert st["docks_completed"] == 0
    assert st["current_dock_job_id"] and st["current_dock_job_id"].startswith(run_id)

    # /result is 409 until done
    assert (await client.get(f"/api/funnel/result/{run_id}")).status_code == 409

    # the in-flight child docking job exists and is queued
    from main import job_store
    child_id = st["current_dock_job_id"]
    child = await job_store.get_job(child_id)
    assert child is not None and child.type == "docking" and child.status.value == "queued"

    # cancel -- parent + in-flight child both go cancelled
    cx = await client.post(f"/api/funnel/cancel/{run_id}")
    assert cx.status_code == 200 and cx.json()["cancelled"] is True
    assert cx.json()["in_flight_dock_cancelled"] is True

    st = await _poll_until(client, run_id,
                           lambda s: s["status"] == "cancelled" and s["stage"] == "cancelled")
    child = await job_store.get_job(child_id)
    assert child.status.value == "cancelled"


@pytest.mark.asyncio
async def test_only_one_run_at_a_time(client):
    await _mode(client, "balanced")
    a = await client.post("/api/funnel/start",
                          json={"smiles": ["CCO", "c1ccccc1"], "target": "cox2", "budget_n": 1})
    assert a.status_code == 200
    run_a = a.json()["run_id"]
    await _poll_until(client, run_a, lambda s: s["stage"] in ("screening", "prescreen", "docking"))

    b = await client.post("/api/funnel/start",
                          json={"candidate_set_id": "cox2_v1", "target": "cox2", "budget_n": 3})
    assert b.status_code == 503
    assert "already active" in b.json()["error"]

    await client.post(f"/api/funnel/cancel/{run_a}")
