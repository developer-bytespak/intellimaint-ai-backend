import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_orchestrate_endpoint():
    """Test orchestration endpoint"""
    async with AsyncClient(base_url="http://orchestrator:8000") as client:
        response = await client.post(
            "/api/v1/orchestrate",
            json={"query": "test query", "user_id": "123"}
        )
        assert response.status_code == 200
        assert "status" in response.json()

@pytest.mark.asyncio
async def test_status_endpoint():
    """Test job status endpoint"""
    async with AsyncClient(base_url="http://orchestrator:8000") as client:
        response = await client.get("/api/v1/status/test-job-id")
        assert response.status_code == 200

