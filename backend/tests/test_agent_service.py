"""
Agent service tests (POST/GET /api/agent/*).

Like test_funnel_service.py, the in-process ASGI client has no LocalWorker, so a
heavy child (docking / funnel) sits `queued` -- which is exactly what lets these
tests cover submission validation, budget clamping, the four ToolCall statuses,
the live audit trail, cancellation, and the funnel-concurrency interaction
without the Vina binary. The full end-to-end run against a live worker is pasted
in the report / CHANGELOG.

Run:  cd backend && python -m pytest tests/test_agent_service.py -v
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from main import app
from agents import service as agent_service
from agents.types import ToolCallStatus
from funnel import service as funnel_service


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _fast_and_isolated(monkeypatch):
    """Speed the poll loops; neutralise heavy jobs another test file may have
    left `queued` in the shared jobs.db (a stale one keeps every HEAVY_LOCAL
    gate closed and would occupy the single agent slot)."""
    monkeypatch.setattr(agent_service, "CHILD_POLL_INTERVAL", 0.2)
    monkeypatch.setattr(funnel_service, "DOCK_POLL_INTERVAL", 0.2)
    monkeypatch.setattr(funnel_service, "COMPUTE_REJECT_SLEEP", 0.2)
    from main import job_store

    async def _neutralise():
        for jt in ("agent", "funnel", "docking"):
            for j in await job_store.list_jobs(job_type=jt, limit=200):
                if j.status.value in ("queued", "running"):
                    await job_store.cancel_job(j.id)

    await _neutralise()
    yield
    for j in await job_store.list_jobs(job_type="agent", limit=50):
        if j.status.value in ("queued", "running"):
            await agent_service.cancel_run(j.id)
    for j in await job_store.list_jobs(job_type="funnel", limit=50):
        if j.status.value in ("queued", "running"):
            await funnel_service.cancel_run(j.id)
    await _neutralise()
    await asyncio.sleep(0.3)


async def _mode(client, mode):
    r = await client.post("/api/compute/mode", json={"mode": mode})
    assert r.status_code == 200, r.text


async def _poll(client, run_id, pred, timeout=25.0):
    import time
    t0 = time.monotonic()
    last = None
    while time.monotonic() - t0 < timeout:
        last = (await client.get(f"/api/agent/runs/{run_id}")).json()
        if pred(last):
            return last
        await asyncio.sleep(0.2)
    raise AssertionError(f"condition not met in {timeout}s; last = {last}")


# ---------------------------------------------------------------------------
# GET /api/agent/tools  -- planner-readable catalog
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tools_catalog_shape(client):
    r = await client.get("/api/agent/tools")
    assert r.status_code == 200
    by_name = {t["name"]: t for t in r.json()}
    assert {"parse_smiles", "predict_toxicity", "run_docking", "run_funnel"} <= set(by_name)
    tox = by_name["predict_toxicity"]
    assert tox["compute_class"] == "LOCAL" and tox["heavy"] is False
    assert tox["args_schema"]["type"] == "object"           # machine-readable
    assert isinstance(tox["description"], str) and tox["description"]  # human-readable
    assert by_name["run_docking"]["heavy"] is True
    assert by_name["run_funnel"]["compute_class"] == "HEAVY_LOCAL"


# ---------------------------------------------------------------------------
# submission validation  (no Job row for any of these)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_tool_rejected_at_submission(client):
    r = await client.post("/api/agent/runs", json={
        "requests": [{"name": "parse_smiles", "args": {"smiles": "CCO"}},
                     {"name": "frobnicate", "args": {}}],
    })
    assert r.status_code == 400
    detail = r.json()["error"]
    assert "frobnicate" in detail["unknown_tools"]
    assert "predict_toxicity" in detail["available"]   # tells the caller what IS available


@pytest.mark.asyncio
async def test_bad_args_rejected_at_submission_per_step(client):
    r = await client.post("/api/agent/runs", json={
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},
            {"name": "predict_toxicity", "args": {}},                       # missing smiles
            {"name": "run_docking", "args": {"smiles": "CCO", "target": "xyz"}},  # bad target
        ],
    })
    assert r.status_code == 400
    steps = {s["index"]: s for s in r.json()["error"]["invalid_steps"]}
    assert set(steps) == {1, 2}
    assert "smiles" in steps[1]["errors"][0]
    assert "target" in steps[2]["errors"][0].lower()


@pytest.mark.asyncio
async def test_more_heavy_tools_than_budget_rejected_with_arithmetic(client):
    await _mode(client, "balanced")
    r = await client.post("/api/agent/runs", json={
        "requests": [
            {"name": "run_docking", "args": {"smiles": "CCO", "target": "cox2"}},
            {"name": "run_docking", "args": {"smiles": "c1ccccc1", "target": "cox2"}},
        ],
        "budget": {"max_docking_jobs": 1},
    })
    assert r.status_code == 400
    d = r.json()["error"]
    assert d["heavy_steps"] == 2 and d["max_docking_jobs"] == 1


# ---------------------------------------------------------------------------
# budget clamping  (client can lower, never raise)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_budget_clamped_not_raised(client):
    r = await client.post("/api/agent/runs", json={
        "requests": [{"name": "parse_smiles", "args": {"smiles": "CCO"}}],
        "budget": {"max_tool_calls": 9999, "max_docking_jobs": 999},
    })
    assert r.status_code == 200
    b = r.json()["budget"]
    assert b["effective"]["max_tool_calls"] == b["ceilings"]["max_tool_calls"]
    assert b["effective"]["max_tool_calls"] < 9999
    assert b["clamped"]["max_tool_calls"]["requested"] == 9999
    assert b["clamped"]["max_docking_jobs"]["effective"] == b["ceilings"]["max_docking_jobs"]


@pytest.mark.asyncio
async def test_unknown_budget_field_rejected(client):
    r = await client.post("/api/agent/runs", json={
        "requests": [{"name": "parse_smiles", "args": {"smiles": "CCO"}}],
        "budget": {"max_concurrent_runs_local": 99},   # server-only, not settable
    })
    # pydantic drops unknown keys by default -> exclude_none passes {} -> 200,
    # OR the schema rejects it (422). Either way the ceiling is not raised.
    assert r.status_code in (200, 422)
    if r.status_code == 200:
        assert r.json()["budget"]["effective"]["max_concurrent_runs_local"] == \
            r.json()["budget"]["ceilings"]["max_concurrent_runs_local"]


# ---------------------------------------------------------------------------
# the four ToolCall statuses in a live audit trail
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cheap_sequence_three_successes(client):
    """parse_smiles -> calculate_descriptors -> predict_toxicity: 3 SUCCESS."""
    r = await client.post("/api/agent/runs", json={
        "goal": "characterise ethanol",
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},
            {"name": "calculate_descriptors", "args": {"smiles": "CCO"}},
            {"name": "predict_toxicity", "args": {"smiles": "CCO"}},
        ],
    })
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    st = await _poll(client, run_id, lambda s: s["status"] == "completed")
    assert [tc["status"] for tc in st["tool_calls"]] == ["success", "success", "success"]
    assert all(tc["duration_ms"] is not None for tc in st["tool_calls"])
    assert st["budget"]["consumed"]["tool_calls"] == 3

    res = (await client.get(f"/api/agent/runs/{run_id}/result")).json()
    assert res["status"] == "completed"
    assert res["tool_calls"][2]["result"] is not None     # a real predicted value, not mocked


@pytest.mark.asyncio
async def test_budget_exhaustion_records_exactly_two(client):
    r = await client.post("/api/agent/runs", json={
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},
            {"name": "parse_smiles", "args": {"smiles": "c1ccccc1"}},
            {"name": "parse_smiles", "args": {"smiles": "CC(=O)O"}},   # must never run
        ],
        "budget": {"max_tool_calls": 2},
    })
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    st = await _poll(client, run_id, lambda s: s["status"] in ("budget_exhausted", "completed", "failed"))
    assert st["status"] == "budget_exhausted"
    assert len(st["tool_calls"]) == 2
    assert st["budget"]["remaining"]["tool_calls"] == 0
    res = (await client.get(f"/api/agent/runs/{run_id}/result")).json()
    assert len(res["tool_calls"]) == 2


@pytest.mark.asyncio
async def test_failed_and_unknown_and_success_in_one_trail(client, monkeypatch):
    """FAILED (tool raised) + UNKNOWN_TOOL (name in catalog, absent from
    registry) + SUCCESS, in one run, run does not abort on the first two."""
    real = agent_service.get_catalog()
    from agents.catalog import ToolSpec
    phantom = ToolSpec(
        name="ghost_tool", category="chemistry", description="not in the registry",
        compute_class="LOCAL", heavy=False, is_async=False, version="v1",
        args_schema={"type": "object"}, _model=None, _kind="str_arg",
    )
    patched = dict(real)
    patched["ghost_tool"] = phantom
    monkeypatch.setattr(agent_service, "_CATALOG", patched)

    r = await client.post("/api/agent/runs", json={
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "NOT_A_REAL_SMILES!!!"}},  # raises -> FAILED
            {"name": "ghost_tool", "args": {"smiles": "CCO"}},                      # -> UNKNOWN_TOOL
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},                    # -> SUCCESS
        ],
    })
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    st = await _poll(client, run_id, lambda s: s["status"] == "completed")
    assert [tc["status"] for tc in st["tool_calls"]] == ["failed", "unknown_tool", "success"]
    assert st["tool_calls"][0]["error"] and st["tool_calls"][0]["result_kind"] is None


@pytest.mark.asyncio
async def test_rejection_comes_from_the_real_resource_manager(client):
    """run_docking in battery-saver -> REJECTED, from ResourceManager, not a mock."""
    await _mode(client, "battery-saver")
    try:
        r = await client.post("/api/agent/runs", json={
            "requests": [{"name": "run_docking", "args": {"smiles": "CCO", "target": "cox2"}}],
        })
        assert r.status_code == 200, r.text
        run_id = r.json()["run_id"]
        st = await _poll(client, run_id, lambda s: s["status"] == "completed")
        tc = st["tool_calls"][0]
        assert tc["status"] == "rejected"
        assert "battery-saver" in tc["error"]
    finally:
        await _mode(client, "balanced")


# ---------------------------------------------------------------------------
# live trail + cancellation mid-run (heavy child)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_mixed_run_with_funnel_updates_trail_then_cancels(client):
    await _mode(client, "balanced")
    r = await client.post("/api/agent/runs", json={
        "goal": "cheap then funnel",
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},
            {"name": "predict_toxicity", "args": {"smiles": "CCO"}},
            {"name": "run_funnel",
             "args": {"smiles": ["CCO", "CC(=O)Oc1ccccc1C(=O)O", "c1ccncc1"],
                      "target": "cox2", "budget_n": 2}},
        ],
    })
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]
    assert r.json()["heavy_steps"] == 1

    # cheap steps land first, then the funnel child appears and starts docking
    st = await _poll(client, run_id, lambda s: s.get("current_child")
                     and s["current_child"].get("stage") == "docking", timeout=30)
    assert [tc["status"] for tc in st["tool_calls"][:2]] == ["success", "success"]
    assert st["current_child"]["type"] == "funnel"
    assert st["tool_calls"][2]["tool_name"] == "run_funnel"
    assert st["tool_calls"][2]["duration_ms"] is None       # still in flight

    from main import job_store
    child_id = st["current_child"]["job_id"]
    assert (await job_store.get_job(child_id)).type == "funnel"

    cx = await client.post(f"/api/agent/runs/{run_id}/cancel")
    assert cx.status_code == 200 and cx.json()["cancelled"] is True
    assert cx.json()["in_flight_child_cancelled"] is True

    st = await _poll(client, run_id, lambda s: s["status"] == "cancelled", timeout=20)
    assert (await job_store.get_job(child_id)).status.value == "cancelled"
    # /result is available for a terminal (cancelled) run
    res = (await client.get(f"/api/agent/runs/{run_id}/result")).json()
    assert res["status"] == "cancelled"
    assert res["tool_calls"][2]["status"] == "failed"       # funnel child was cut short


# ---------------------------------------------------------------------------
# concurrency
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_one_agent_run_at_a_time(client):
    await _mode(client, "balanced")
    a = await client.post("/api/agent/runs", json={
        "requests": [{"name": "run_funnel",
                      "args": {"smiles": ["CCO", "c1ccccc1"], "target": "cox2", "budget_n": 1}}],
    })
    assert a.status_code == 200
    run_a = a.json()["run_id"]
    await _poll(client, run_a, lambda s: s["status"] == "running", timeout=15)

    b = await client.post("/api/agent/runs", json={
        "requests": [{"name": "parse_smiles", "args": {"smiles": "CCO"}}],
    })
    assert b.status_code == 503
    assert "already active" in b.json()["error"]
    await client.post(f"/api/agent/runs/{run_a}/cancel")


@pytest.mark.asyncio
async def test_agent_run_funnel_blocked_while_a_funnel_is_active(client):
    """concurrency interaction with an active funnel run (started via /api/funnel)."""
    await _mode(client, "balanced")
    f = await client.post("/api/funnel/start",
                          json={"smiles": ["CCO", "c1ccccc1"], "target": "cox2", "budget_n": 1})
    assert f.status_code == 200
    fid = f.json()["run_id"]
    # let the funnel take the 'funnel' slot
    for _ in range(50):
        s = (await client.get(f"/api/funnel/status/{fid}")).json()
        if s["stage"] in ("screening", "prescreen", "docking"):
            break
        await asyncio.sleep(0.2)

    r = await client.post("/api/agent/runs", json={
        "requests": [
            {"name": "parse_smiles", "args": {"smiles": "CCO"}},
            {"name": "run_funnel",
             "args": {"candidate_set_id": "cox2_v1", "target": "cox2", "budget_n": 2}},
        ],
    })
    assert r.status_code == 400
    assert "funnel run is already active" in r.json()["error"]
    await client.post(f"/api/funnel/cancel/{fid}")
