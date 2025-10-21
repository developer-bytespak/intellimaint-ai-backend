import pytest
from app.pipeline import orchestrate_request

@pytest.mark.asyncio
async def test_orchestrate_request():
    request = {"query": "test"}
    result = await orchestrate_request(request)
    assert result["status"] == "success"

