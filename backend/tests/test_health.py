"""
Health Check Endpoints Tests.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: AsyncClient):
    """Test that GET /health returns 200 and status ok."""
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data == {"status": "ok"}
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_database_health_endpoint_structure(async_client: AsyncClient):
    """Test that GET /health/database returns valid health response schema."""
    response = await async_client.get("/health/database")
    # Response can be 200 regardless of whether live database is reachable in test env
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "healthy" in data
    assert isinstance(data["healthy"], bool)
