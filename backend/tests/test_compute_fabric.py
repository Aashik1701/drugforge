"""
Compute-fabric tests: compute mode control, batch safety limits, docking job
lifecycle (creation/status/cancel/history — real Vina execution is not
exercised here since it requires the binary + a running LocalWorker process,
neither of which this in-process ASGI test client provides; see
docs/development/local-worker.md for the manual end-to-end verification
that WAS run against a live worker process).

Run with: cd backend && python -m pytest tests/ -v
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _set_mode(client: AsyncClient, mode: str) -> None:
    resp = await client.post("/api/compute/mode", json={"mode": mode})
    assert resp.status_code == 200, resp.text


# ── Chemistry ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_3d(client: AsyncClient):
    resp = await client.post("/utils/generate-3d", json={"smiles": "CCO"})
    assert resp.status_code == 200
    assert "mol_block" in resp.json()


# ── Batch safety (spec §17/§15) ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_small_succeeds(client: AsyncClient):
    resp = await client.post("/predict/batch", json={"smiles_list": ["CCO", "c1ccccc1"]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_batch_oversized_rejected(client: AsyncClient):
    resp = await client.post("/predict/batch", json={"smiles_list": ["CCO"] * 150})
    assert resp.status_code == 413
    assert "exceeds the local limit" in resp.json()["error"]


# ── Compute mode control ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compute_policy_get(client: AsyncClient):
    resp = await client.get("/api/compute/policy")
    assert resp.status_code == 200
    assert resp.json()["mode"] in ("battery-saver", "balanced", "performance")


@pytest.mark.asyncio
async def test_compute_mode_invalid(client: AsyncClient):
    resp = await client.post("/api/compute/mode", json={"mode": "turbo"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_compute_mode_roundtrip(client: AsyncClient):
    await _set_mode(client, "performance")
    resp = await client.get("/api/compute/policy")
    data = resp.json()
    assert data["mode"] == "performance"
    assert data["allow_docking"] is True
    # restore default for subsequent tests
    await _set_mode(client, "battery-saver")


# ── Docking: gating ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_docking_disabled_by_default(client: AsyncClient):
    await _set_mode(client, "battery-saver")
    resp = await client.post("/api/dock/start", json={"smiles": "CCO", "target": "cox2"})
    assert resp.status_code == 503
    assert "disabled" in resp.json()["error"].lower()


@pytest.mark.asyncio
async def test_docking_unsupported_target(client: AsyncClient):
    await _set_mode(client, "balanced")
    resp = await client.post("/api/dock/start", json={"smiles": "CCO", "target": "nonexistent"})
    assert resp.status_code == 400
    await _set_mode(client, "battery-saver")


@pytest.mark.asyncio
async def test_docking_invalid_smiles(client: AsyncClient):
    await _set_mode(client, "balanced")
    resp = await client.post("/api/dock/start", json={"smiles": "not a smiles!!", "target": "cox2"})
    assert resp.status_code == 400
    await _set_mode(client, "battery-saver")


# ── Docking: job lifecycle (no worker running — job stays queued) ───────

@pytest.mark.asyncio
async def test_docking_job_lifecycle(client: AsyncClient):
    await _set_mode(client, "balanced")

    start_resp = await client.post("/api/dock/start", json={"smiles": "CCO", "target": "cox2"})
    assert start_resp.status_code == 200
    body = start_resp.json()
    assert body["status"] == "queued"
    assert body["task_id"].startswith("dock_")
    task_id = body["task_id"]

    # No LocalWorker process is running in this test — job should still be queued.
    status_resp = await client.get(f"/api/dock/status/{task_id}")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "queued"

    history_resp = await client.get("/api/dock/history")
    assert history_resp.status_code == 200
    assert any(t["task_id"] == task_id for t in history_resp.json())

    cancel_resp = await client.post(f"/api/dock/cancel/{task_id}")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["cancelled"] is True

    status_after_cancel = await client.get(f"/api/dock/status/{task_id}")
    assert status_after_cancel.json()["status"] == "cancelled"

    # Cancelling an already-terminal job should be a no-op, not an error.
    second_cancel = await client.post(f"/api/dock/cancel/{task_id}")
    assert second_cancel.status_code == 200
    assert second_cancel.json()["cancelled"] is False

    await _set_mode(client, "battery-saver")


@pytest.mark.asyncio
async def test_docking_status_404(client: AsyncClient):
    resp = await client.get("/api/dock/status/dock_doesnotexist")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_docking_concurrency_limit(client: AsyncClient):
    """
    MAX_DOCKING_CONCURRENT=1 (balanced mode default): a second submission
    must be rejected while the first job is still queued/running — no
    worker needs to be running for this to hold, since a queued-but-unclaimed
    job already occupies the one available slot.
    """
    await _set_mode(client, "balanced")

    first = await client.post("/api/dock/start", json={"smiles": "CCO", "target": "cox2"})
    assert first.status_code == 200

    second = await client.post("/api/dock/start", json={"smiles": "c1ccccc1", "target": "cox2"})
    assert second.status_code == 503
    assert "concurrency limit" in second.json()["error"].lower()

    # free the slot
    await client.post(f"/api/dock/cancel/{first.json()['task_id']}")
    third = await client.post("/api/dock/start", json={"smiles": "c1ccccc1", "target": "cox2"})
    assert third.status_code == 200

    await _set_mode(client, "battery-saver")


@pytest.mark.asyncio
async def test_docking_receptor_endpoint_ungated(client: AsyncClient):
    """Receptor lookup involves no job/compute gating — should work even in battery-saver."""
    await _set_mode(client, "battery-saver")
    resp = await client.get("/api/dock/receptor/cox2")
    assert resp.status_code == 200
    assert resp.json()["target"] == "cox2"
