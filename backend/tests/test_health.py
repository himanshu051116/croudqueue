import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.mark.asyncio
async def test_health_live():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"


@pytest.mark.asyncio
async def test_health_ready():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health/ready")
    # The local test database is authoritative; optional Redis cannot veto readiness.
    assert response.status_code == 200
    assert response.json()["status"] == "OK"
