import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_search_endpoint():
    """Test document search endpoint"""
    async with AsyncClient(base_url="http://rag-service:8002") as client:
        response = await client.post(
            "/search",
            json={"query": "test search", "top_k": 5}
        )
        assert response.status_code == 200
        assert "documents" in response.json()

@pytest.mark.asyncio
async def test_embed_endpoint():
    """Test embedding generation endpoint"""
    async with AsyncClient(base_url="http://rag-service:8002") as client:
        response = await client.post(
            "/embed",
            json={"texts": ["test text 1", "test text 2"]}
        )
        assert response.status_code == 200
        assert "embeddings" in response.json()

