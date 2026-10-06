"""
Authentication & JWT Validation Tests.

Validates:
1. Missing JWT returns HTTP 401.
2. Malformed / invalid JWT returns HTTP 401.
3. Expired HS256 and ES256 JWTs return HTTP 401.
4. Valid modern Supabase ES256 JWTs are accepted via JWKS.
5. ES256 invalid signature, wrong issuer, wrong audience, unknown kid are rejected.
6. Malformed and disallowed algorithms (e.g. none) are rejected.
7. Subject identity and user role claims are preserved.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import uuid
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from fastapi import HTTPException
import jwt
from jwt.exceptions import PyJWKClientError
import pytest
from httpx import AsyncClient
from app.core.config import get_settings
from app.core.security import get_jwks_client, set_jwks_client, verify_supabase_jwt


@pytest.fixture
def es256_setup():
    """Generates an ephemeral EC P-256 key pair and mocks JWKS signing key lookup."""
    settings = get_settings()
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    pem_priv = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    kid = "test-es256-key-id-001"
    mock_jwk = MagicMock()
    mock_jwk.key = public_key
    mock_jwk.key_id = kid

    mock_jwks = MagicMock()
    mock_jwks.get_signing_key_from_jwt.return_value = mock_jwk

    set_jwks_client(mock_jwks)

    yield {
        "private_key_pem": pem_priv,
        "public_key": public_key,
        "kid": kid,
        "mock_jwks": mock_jwks,
        "issuer": f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1",
    }

    set_jwks_client(None)


# ==============================================================================
# Existing HTTP API Contract Tests
# ==============================================================================

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


# ==============================================================================
# Comprehensive Phase 15.4 ES256 & JWKS Validation Tests
# ==============================================================================

def test_valid_es256_supabase_jwt_accepted(es256_setup):
    """Valid ES256 Supabase JWT with correct kid, issuer, and audience is accepted."""
    user_id = str(uuid.uuid4())
    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=2)).timestamp())
    payload = {
        "sub": user_id,
        "email": "customer@example.com",
        "aud": "authenticated",
        "iss": es256_setup["issuer"],
        "exp": future_exp,
        "role": "authenticated",
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Test Customer"},
    }
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
        headers={"kid": es256_setup["kid"]},
    )

    claims = verify_supabase_jwt(token)
    assert claims["sub"] == user_id
    assert claims["email"] == "customer@example.com"
    assert claims["aud"] == "authenticated"
    assert claims["iss"] == es256_setup["issuer"]


def test_expired_es256_jwt_rejected(es256_setup):
    """Expired ES256 JWT is rejected with HTTP 401."""
    expired_time = int((datetime.now(timezone.utc) - timedelta(minutes=10)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "expired@example.com",
        "aud": "authenticated",
        "iss": es256_setup["issuer"],
        "exp": expired_time,
    }
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
        headers={"kid": es256_setup["kid"]},
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_invalid_signature_es256_jwt_rejected(es256_setup):
    """ES256 JWT signed by an unauthorized private key fails cryptographic verification."""
    # Generate an untrusted rogue key pair
    rogue_private_key = ec.generate_private_key(ec.SECP256R1())
    rogue_pem = rogue_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "tampered@example.com",
        "aud": "authenticated",
        "iss": es256_setup["issuer"],
        "exp": future_exp,
    }
    # Token uses the valid kid in header but signed with rogue key
    tampered_token = jwt.encode(
        payload,
        rogue_pem,
        algorithm="ES256",
        headers={"kid": es256_setup["kid"]},
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(tampered_token)
    assert exc_info.value.status_code == 401
    assert "signature" in exc_info.value.detail.lower() or "invalid" in exc_info.value.detail.lower()


def test_wrong_issuer_es256_jwt_rejected(es256_setup):
    """ES256 JWT with spoofed issuer is rejected with HTTP 401."""
    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "spoofed@example.com",
        "aud": "authenticated",
        "iss": "https://spoofed-supabase-project.supabase.co/auth/v1",
        "exp": future_exp,
    }
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
        headers={"kid": es256_setup["kid"]},
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "issuer" in exc_info.value.detail.lower()


def test_wrong_audience_es256_jwt_rejected(es256_setup):
    """ES256 JWT with wrong audience is rejected with HTTP 401."""
    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "wrong_aud@example.com",
        "aud": "anon_unauthenticated",
        "iss": es256_setup["issuer"],
        "exp": future_exp,
    }
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
        headers={"kid": es256_setup["kid"]},
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "audience" in exc_info.value.detail.lower()


def test_missing_token_rejected():
    """Empty or None token is rejected with HTTP 401."""
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt("")
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info2:
        verify_supabase_jwt("   ")
    assert exc_info2.value.status_code == 401


def test_malformed_token_rejected():
    """Malformed non-JWT token is rejected with HTTP 401."""
    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt("this-is-not-a-valid-jwt")
    assert exc_info.value.status_code == 401
    assert "malformed" in exc_info.value.detail.lower() or "invalid" in exc_info.value.detail.lower()


def test_unknown_kid_es256_jwt_rejected(es256_setup):
    """ES256 JWT with an unknown kid that cannot be resolved in JWKS is rejected with HTTP 401."""
    es256_setup["mock_jwks"].get_signing_key_from_jwt.side_effect = PyJWKClientError(
        'Unable to find a signing key that matches: "unknown-rotated-kid"'
    )

    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "unknown_kid@example.com",
        "aud": "authenticated",
        "iss": es256_setup["issuer"],
        "exp": future_exp,
    }
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
        headers={"kid": "unknown-rotated-kid"},
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "key identifier" in exc_info.value.detail.lower()


def test_missing_kid_es256_jwt_rejected(es256_setup):
    """ES256 JWT without a kid in the header is rejected with HTTP 401."""
    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "no_kid@example.com",
        "aud": "authenticated",
        "iss": es256_setup["issuer"],
        "exp": future_exp,
    }
    # Encode with ES256 but without 'kid' in header
    token = jwt.encode(
        payload,
        es256_setup["private_key_pem"],
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "key identifier" in exc_info.value.detail.lower() or "kid" in exc_info.value.detail.lower()


def test_disallowed_algorithm_rejected():
    """Tokens with disallowed algorithms (e.g. none, RS256, etc.) are rejected with HTTP 401."""
    future_exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
    payload = {
        "sub": str(uuid.uuid4()),
        "email": "unsupported@example.com",
        "aud": "authenticated",
        "exp": future_exp,
    }
    # Unsigned algorithm 'none'
    token = jwt.encode(payload, key="", algorithm="none")

    with pytest.raises(HTTPException) as exc_info:
        verify_supabase_jwt(token)
    assert exc_info.value.status_code == 401
    assert "not allowed" in exc_info.value.detail.lower()
