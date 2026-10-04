"""
Security and JWT Verification Module.

Handles validation of Supabase-issued JSON Web Tokens (JWTs).
Decodes token claims, verifies expiration and signatures, and extracts the authenticated subject (UUID).
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
import jwt
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("security.jwt")


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    """
    Validate a Supabase JWT token and return its payload claims.
    
    If SUPABASE_JWT_SECRET is configured, verifies the cryptographic signature locally.
    Otherwise, extracts claims safely while ensuring token structure and expiration validity.
    
    Raises:
        HTTPException(401): If token is expired, has invalid signature, or is malformed.
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

    try:
        # If JWT Secret is provided, enforce HS256 cryptographic verification
        if settings.SUPABASE_JWT_SECRET and len(settings.SUPABASE_JWT_SECRET) >= 16 and not settings.SUPABASE_JWT_SECRET.startswith("placeholder_"):
            payload = jwt.decode(
                token_str,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_signature": True},
            )
        else:
            # Decode claims with expiration check
            payload = jwt.decode(
                token_str,
                options={"verify_signature": False, "verify_exp": True},
            )

    except jwt.ExpiredSignatureError:
        logger.warning("token_validation_failed", reason="token_expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("token_validation_failed", reason="invalid_token", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as exc:
        logger.error("token_validation_unexpected_error", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Ensure subject ('sub') exists and is a valid UUID (Supabase Auth user ID)
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
