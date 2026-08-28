"""
Smoke tests for the FastAPI application.

Run with:  cd backend && python -m pytest tests/ -v
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


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    """GET / should return API info."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "DrugForge API"


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    """GET /health should return healthy status."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_models_endpoint(client: AsyncClient):
    """GET /models should list all registered models."""
    resp = await client.get("/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "solubility" in data
    assert "bbbp" in data


@pytest.mark.asyncio
async def test_predict_solubility_invalid_smiles(client: AsyncClient):
    """POST /predict/solubility with invalid SMILES should return 400."""
    resp = await client.post(
        "/predict/solubility",
        json={"smiles": "INVALID_SMILES_STRING"},
    )
    # 400 if SMILES invalid, 503 if model not loaded – both are acceptable
    assert resp.status_code in (400, 503)


@pytest.mark.asyncio
async def test_predict_solubility_empty(client: AsyncClient):
    """POST /predict/solubility with empty SMILES should return 422."""
    resp = await client.post(
        "/predict/solubility",
        json={"smiles": ""},
    )
    assert resp.status_code == 422  # Pydantic validation error
