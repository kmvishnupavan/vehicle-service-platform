"""
Authentication & JWT Validation Tests.
"""

from datetime import datetime, timezone, timedelta
import uuid
import jwt
import pytest
from httpx import AsyncClient
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_missing_jwt_returns_401(async_client: AsyncClient):
    """Test that accessing protected endpoint without token returns HTTP 401."""
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "Authentication credentials were not provided" in data["detail"]


@pytest.mark.asyncio
async def test_invalid_jwt_returns_401(async_client: AsyncClient):
    """Test that invalid signature or malformed JWT returns HTTP 401."""
    headers = {"Authorization": "Bearer invalid.token.payload"}
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_expired_jwt_returns_401(async_client: AsyncClient):
    """Test that expired JWT returns HTTP 401 with appropriate message."""
    settings = get_settings()
    secret = settings.SUPABASE_JWT_SECRET or "super_secret_test_key_with_at_least_32_characters"
    
    # Generate token expired 1 hour ago
    expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "test@example.com",
        "role": "authenticated",
        "exp": int(expired_time.timestamp()),
    }
    expired_token = jwt.encode(payload, secret, algorithm="HS256")

    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "expired" in data["detail"].lower()


@pytest.mark.asyncio
async def test_missing_sub_claim_returns_401(async_client: AsyncClient):
    """Test that token without subject UUID claim returns HTTP 401."""
    settings = get_settings()
    secret = settings.SUPABASE_JWT_SECRET or "super_secret_test_key_with_at_least_32_characters"
    
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    payload = {
        "email": "nosub@example.com",
        "role": "authenticated",
        "exp": int(future_time.timestamp()),
    }
    token_without_sub = jwt.encode(payload, secret, algorithm="HS256")

    headers = {"Authorization": f"Bearer {token_without_sub}"}
    response = await async_client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    data = response.json()
    assert "missing subject" in data["detail"].lower()
