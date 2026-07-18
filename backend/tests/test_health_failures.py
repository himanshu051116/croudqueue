from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.main import app


# Reset dependency overrides after each test
@pytest.fixture(autouse=True)
def clean_overrides() -> None:
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health_live_always_200() -> None:
    """Verifies that liveness check is always 200 and includes timestamp."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "OK"
    assert "timestamp" in response.json()


@pytest.mark.asyncio
async def test_health_ready_db_failure() -> None:
    """Verifies readiness returns 503 with components details when DB is disconnected."""

    async def mock_get_db():
        session = AsyncMock()
        # Simulate db execution failure
        session.execute.side_effect = OperationalError(
            "SELECT 1", (), Exception("DB Connection refused")
        )
        yield session

    app.dependency_overrides[get_db] = mock_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health/ready")

    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert data["detail"]["status"] == "UNAVAILABLE"
    assert "DISCONNECTED" in data["detail"]["components"]["database"]


@pytest.mark.asyncio
async def test_health_ready_redis_failure() -> None:
    """Optional Redis is reported without making PostgreSQL readiness fail."""
    # Patch redis.asyncio.from_url to raise connection error
    with patch("redis.asyncio.from_url") as mock_from_url:
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Redis Connection refused")
        mock_from_url.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/api/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "OK"
        assert data["components"]["redis"] == "DISCONNECTED"
        assert "redis" in data["optional_components"]


@pytest.mark.asyncio
async def test_health_ready_required_redis_failure() -> None:
    """A deployment that explicitly requires Redis still fails readiness."""

    with (
        patch.object(settings, "REDIS_REQUIRED", True),
        patch("redis.asyncio.from_url") as mock_from_url,
    ):
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Redis Connection refused")
        mock_from_url.return_value = mock_client

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            response = await ac.get("/api/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["components"]["redis"] == "DISCONNECTED"
