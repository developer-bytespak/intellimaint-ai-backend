import pytest
from httpx import AsyncClient
from io import BytesIO

@pytest.mark.asyncio
async def test_detect_endpoint():
    """Test object detection endpoint"""
    async with AsyncClient(base_url="http://vision-service:8001") as client:
        files = {"file": ("test.jpg", BytesIO(b"fake image data"), "image/jpeg")}
        response = await client.post("/detect", files=files)
        assert response.status_code == 200
        assert "objects" in response.json()

@pytest.mark.asyncio
async def test_ocr_endpoint():
    """Test OCR endpoint"""
    async with AsyncClient(base_url="http://vision-service:8001") as client:
        files = {"file": ("test.jpg", BytesIO(b"fake image data"), "image/jpeg")}
        response = await client.post("/ocr", files=files)
        assert response.status_code == 200
        assert "text" in response.json()

