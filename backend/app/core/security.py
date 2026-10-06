"""
Security and JWT Verification Module.

Handles validation of Supabase-issued JSON Web Tokens (JWTs).
Supports:
1. Modern Supabase ES256 asymmetric signatures validated via cached JWKS endpoint.
2. Legacy/testing HS256 symmetric signatures validated via SUPABASE_JWT_SECRET.

Enforces cryptographic signature verification, expiration, issuer, audience,
and valid subject UUID extraction without trusting unverified payloads.
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    InvalidTokenError,
    PyJWKClientError,
    PyJWKError,
)
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("security.jwt")

_jwks_client: PyJWKClient | None = None
_jwks_url: str | None = None


def get_jwks_client() -> PyJWKClient:
    """Retrieve or initialize the cached PyJWKClient for the configured Supabase project."""
    global _jwks_client, _jwks_url
    settings = get_settings()
    url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json"
    if _jwks_client is None or _jwks_url != url:
        _jwks_url = url
        # Cache JWK set for 1 hour; automatically refetches on unknown kid for safe key rotation
        _jwks_client = PyJWKClient(url, cache_jwk_set=True, lifespan=3600)
    return _jwks_client


def set_jwks_client(client: PyJWKClient | None) -> None:
    """Override or reset the JWKS client (primarily for testing and mocking)."""
    global _jwks_client, _jwks_url
    _jwks_client = client
    settings = get_settings()
    _jwks_url = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if client is not None else None


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Validate a Supabase JWT token and return its payload claims.

    Validates:
    - Token structure and format.
    - Algorithm: ES256 (via JWKS) or HS256 (via SUPABASE_JWT_SECRET).
    - Cryptographic signature (never skipped).
    - Token expiration (exp).
    - Issuer (iss) for ES256 tokens matching the Supabase auth issuer.
    - Audience (aud) for ES256 tokens matching 'authenticated'.
    - Subject (sub) claim presence and valid UUID formatting.

    Raises:
        HTTPException(401): If token is missing, expired, has invalid signature,
                            wrong issuer/audience, or is malformed.
    """
    settings = get_settings()

    if not token or not isinstance(token, str):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Clean potential Bearer prefix if passed directly
    token_str = token.strip()
    if token_str.lower().startswith("bearer "):
        token_str = token_str[7:].strip()

    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or empty authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 1. Read JWT header to inspect alg and kid
    try:
        header = jwt.get_unverified_header(token_str)
    except Exception as exc:
        logger.warning("token_validation_failed", reason="malformed_header", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials: malformed token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg")
    if not alg or alg not in ["ES256", "HS256"]:
        logger.warning("token_validation_failed", reason="disallowed_algorithm", alg=alg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication credentials: algorithm '{alg}' is not allowed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Cryptographic verification branch based on alg
    try:
        if alg == "ES256":
            kid = header.get("kid")
            if not kid:
                logger.warning("token_validation_failed", reason="missing_kid_for_es256")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials: token missing key identifier (kid).",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Retrieve signing key from cached JWKS client
            try:
                jwks = get_jwks_client()
                signing_key = jwks.get_signing_key_from_jwt(token_str)
            except (PyJWKClientError, PyJWKError) as jwk_err:
                logger.warning("token_validation_failed", reason="jwks_key_not_found", kid=kid, error=str(jwk_err))
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials: unknown or unresolvable key identifier.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            expected_issuer = f"{settings.SUPABASE_URL.rstrip('/')}/auth/v1"
            payload = jwt.decode(
                token_str,
                signing_key.key,
                algorithms=["ES256"],
                audience="authenticated",
                issuer=expected_issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )

        elif alg == "HS256":
            secret = settings.SUPABASE_JWT_SECRET
            if not secret or len(secret) < 16 or secret.startswith("placeholder_"):
                logger.warning("token_validation_failed", reason="hs256_secret_not_configured")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials: HS256 secret is not configured.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            payload = jwt.decode(
                token_str,
                secret,
                algorithms=["HS256"],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": False,
                },
            )

    except ExpiredSignatureError:
        logger.warning("token_validation_failed", reason="token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidIssuerError as iss_err:
        logger.warning("token_validation_failed", reason="invalid_issuer", error=str(iss_err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials: wrong token issuer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidAudienceError as aud_err:
        logger.warning("token_validation_failed", reason="invalid_audience", error=str(aud_err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials: wrong token audience.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidSignatureError as sig_err:
        logger.warning("token_validation_failed", reason="invalid_signature", error=str(sig_err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials: signature verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as token_err:
        logger.warning("token_validation_failed", reason="invalid_token", error=str(token_err))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        # Re-raise already constructed HTTPExceptions
        raise
    except Exception as exc:
        logger.error("token_validation_unexpected_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Ensure subject ('sub') exists and is a valid UUID
    user_id_str = payload.get("sub")
    if not user_id_str:
        logger.warning("token_validation_failed", reason="missing_sub_claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject identity claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        uuid.UUID(str(user_id_str))
    except (ValueError, TypeError):
        logger.warning("token_validation_failed", reason="malformed_sub_uuid", sub=user_id_str)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: subject claim is not a valid UUID.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload

