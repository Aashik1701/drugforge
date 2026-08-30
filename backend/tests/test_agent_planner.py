"""
Phase-4 planner tests (POST /api/agent/plan + plan_id on /api/agent/runs).

The LLM is faked -- these tests cover the code around it: plan/execute
separation, N clamping to the server ceiling, malformed-output handling with a
DECLARED attempt cap, the missing-key 503, and that a planner-emitted sequence
is run through the Phase-3 submission validator before it is runnable.

Run:  cd backend && python -m pytest tests/test_agent_planner.py -v
"""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import services.llm as llm_registry
from agents import planner as planner_mod
from agents import service as agent_service
from agents.planner import PLANNER_MAX_ATTEMPTS, PlannerError, PlannerUnavailable, make_plan
from funnel import service as funnel_service
from main import app


class FakeProvider:
    """Returns canned strings in order; repeats the last one after it runs out."""

    _model = "fake-model"

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls = 0

    def generate(self, prompt: str, system_prompt=None) -> str:
        self.calls += 1
        return self.responses[min(self.calls - 1, len(self.responses) - 1)]


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def _isolate(monkeypatch):
    monkeypatch.setattr(agent_service, "CHILD_POLL_INTERVAL", 0.2)
    monkeypatch.setattr(funnel_service, "DOCK_POLL_INTERVAL", 0.2)
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
    await asyncio.sleep(0.2)


def _use(monkeypatch, provider):
    monkeypatch.setattr(llm_registry, "get_provider", lambda: provider)


async def _mode(client, mode):
    assert (await client.post("/api/compute/mode", json={"mode": mode})).status_code == 200


# ---------------------------------------------------------------------------
# missing API key
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_api_key_returns_503_chat_shape(client, monkeypatch):
    _use(monkeypatch, None)
    r = await client.post("/api/agent/plan", json={
        "goal": "find the best binder", "candidate_set_id": "cox2_v1", "target": "cox2"})
    assert r.status_code == 503
    assert "GEMINI_API_KEY" in r.json()["error"]


@pytest.mark.asyncio
async def test_make_plan_raises_planner_unavailable_without_key(monkeypatch):
    _use(monkeypatch, None)
    with pytest.raises(PlannerUnavailable):
        make_plan("goal", "cox2_v1", "cox2")


# ---------------------------------------------------------------------------
# plan / execute separation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_plan_does_not_execute(client, monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 8, "rationale": "moderate budget fits the goal"}'))
    from main import job_store

    before = len(await job_store.list_jobs(job_type="agent", limit=200))
    r = await client.post("/api/agent/plan", json={
        "goal": "find good candidates", "candidate_set_id": "cox2_v1", "target": "cox2"})
    assert r.status_code == 200
    body = r.json()
    assert body["plan_id"].startswith("plan_")
    assert body["chosen_n"] == 8
    assert body["tool_sequence"][0]["name"] == "run_funnel"
    assert body["tool_sequence"][0]["args"]["budget_n"] == 8
    assert body["frontier_context"]["recommended_n"] == 10
    # nothing ran
    assert len(await job_store.list_jobs(job_type="agent", limit=200)) == before
    assert (await client.get(f"/api/agent/plans/{body['plan_id']}")).status_code == 200


@pytest.mark.asyncio
async def test_plan_id_executes_the_stored_sequence(client, monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 2, "rationale": "cheap look"}'))
    await _mode(client, "balanced")
    plan = (await client.post("/api/agent/plan", json={
        "goal": "quick look", "candidate_set_id": "cox2_v1", "target": "cox2"})).json()

    run = await client.post("/api/agent/runs", json={"plan_id": plan["plan_id"]})
    assert run.status_code == 200, run.text
    rid = run.json()["run_id"]
    assert run.json()["accepted_steps"] == 1 and run.json()["heavy_steps"] == 1
    assert plan["plan_id"] in run.json()["message"]

    st = (await client.get(f"/api/agent/runs/{rid}")).json()
    assert st["run_id"] == rid
    from main import job_store
    assert (await job_store.get_job(rid)).input["plan_id"] == plan["plan_id"]
    await client.post(f"/api/agent/runs/{rid}/cancel")


@pytest.mark.asyncio
async def test_runs_rejects_both_or_neither(client, monkeypatch):
    both = await client.post("/api/agent/runs", json={
        "plan_id": "plan_x", "requests": [{"name": "parse_smiles", "args": {"smiles": "CCO"}}]})
    assert both.status_code == 400 and "exactly one" in both.json()["error"]
    neither = await client.post("/api/agent/runs", json={"goal": "nothing"})
    assert neither.status_code == 400 and "exactly one" in neither.json()["error"]


@pytest.mark.asyncio
async def test_runs_unknown_plan_id_404(client):
    r = await client.post("/api/agent/runs", json={"plan_id": "plan_doesnotexist"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# N clamping  (LLM cannot raise the ceiling)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_chosen_n_clamped_to_server_ceiling(client, monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 9999, "rationale": "dock everything"}'))
    r = await client.post("/api/agent/plan", json={
        "goal": "cost no object", "candidate_set_id": "cox2_v1", "target": "cox2"})
    assert r.status_code == 200
    b = r.json()
    assert b["chosen_n"] == min(funnel_service.MAX_BUDGET_N, 45)   # == 45 (set size)
    assert b["clamp"]["raw_n"] == 9999 and b["clamp"]["clamped"] is True
    assert b["tool_sequence"][0]["args"]["budget_n"] == b["chosen_n"]


@pytest.mark.asyncio
async def test_chosen_n_floored_at_one(monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 0, "rationale": "nothing"}'))
    # chosen_n=0 fails parse (>=1 check) -> retried -> 422; test the clamp helper directly too
    with pytest.raises(PlannerError):
        make_plan("g", "cox2_v1", "cox2")
    n, info = planner_mod.clamp_n(-5, 45)
    assert n == 1 and info["clamped"] is True


# ---------------------------------------------------------------------------
# malformed output  (declared attempt cap, no silent retry)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unparseable_output_fails_after_declared_attempts(client, monkeypatch):
    fp = FakeProvider("I'm sorry, I can't help with that.",
                      "still prose, no json",
                      '{"chosen_n": 5, "rationale": "would have worked"}')  # 3rd never reached
    _use(monkeypatch, fp)
    r = await client.post("/api/agent/plan", json={
        "goal": "x", "candidate_set_id": "cox2_v1", "target": "cox2"})
    assert r.status_code == 422
    assert fp.calls == PLANNER_MAX_ATTEMPTS          # exactly the declared cap, not more
    assert r.json()["error"]["attempts"] == PLANNER_MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_json_without_rationale_is_rejected(monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 7}'))
    with pytest.raises(PlannerError) as ei:
        make_plan("x", "cox2_v1", "cox2")
    assert ei.value.status == 422


@pytest.mark.asyncio
async def test_second_attempt_can_succeed(monkeypatch):
    fp = FakeProvider("garbage", '{"chosen_n": 12, "rationale": "second try parses"}')
    _use(monkeypatch, fp)
    plan = make_plan("x", "cox2_v1", "cox2")
    assert plan["chosen_n"] == 12 and fp.calls == 2 and plan["llm"]["attempts"] == 2


# ---------------------------------------------------------------------------
# emitted sequence goes through the Phase-3 validator
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emitted_sequence_validates_through_phase3(monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 10, "rationale": "default"}'))
    plan = make_plan("x", "cox2_v1", "cox2")
    # feed the planner's own output to the Phase-3 validator: it must pass
    from schemas.agent import AgentToolRequest
    eff, _, _ = agent_service.clamp_budget(None)
    heavy = agent_service.validate_submission(
        [AgentToolRequest(**s) for s in plan["tool_sequence"]], eff)
    assert heavy == ["run_funnel"]


@pytest.mark.asyncio
async def test_malformed_emitted_sequence_is_400_not_a_run(client, monkeypatch):
    # force the planner to emit a policy id the frozen funnel validator rejects
    monkeypatch.setattr(planner_mod, "FROZEN_POLICY_ID", "not_the_frozen_policy")
    _use(monkeypatch, FakeProvider('{"chosen_n": 10, "rationale": "default"}'))
    r = await client.post("/api/agent/plan", json={
        "goal": "x", "candidate_set_id": "cox2_v1", "target": "cox2"})
    assert r.status_code == 400
    assert "invalid tool sequence" in r.json()["error"]["reason"] or \
           "v7_binding_weak_cox2" in str(r.json()["error"])


# ---------------------------------------------------------------------------
# input guards that don't need the LLM
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unknown_set_404_before_llm(client, monkeypatch):
    fp = FakeProvider('{"chosen_n": 10, "rationale": "x"}')
    _use(monkeypatch, fp)
    r = await client.post("/api/agent/plan", json={
        "goal": "x", "candidate_set_id": "nope_v1", "target": "cox2"})
    assert r.status_code == 404
    assert fp.calls == 0                       # LLM never called for a bad set


@pytest.mark.asyncio
async def test_bad_target_400(client, monkeypatch):
    _use(monkeypatch, FakeProvider('{"chosen_n": 10, "rationale": "x"}'))
    r = await client.post("/api/agent/plan", json={
        "goal": "x", "candidate_set_id": "cox2_v1", "target": "egfr"})
    assert r.status_code == 400
