import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete orchestration pipeline"""
    async with AsyncClient(base_url="http://orchestrator:8000") as client:
        # Test multimodal request
        response = await client.post(
            "/api/v1/orchestrate",
            json={
                "query": "Explain this image",
                "user_id": "test-user",
                "session_id": "test-session",
                "context": {}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

