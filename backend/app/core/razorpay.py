"""
Razorpay Integration & Cryptographic Verification Module.

Enforces server-side Razorpay client creation and HMAC-SHA256 signature verification.
Uses constant-time comparison (hmac.compare_digest) to prevent timing attacks.
Ensures zero secret leakage to clients or logs.
"""

import hashlib
import hmac
from fastapi import HTTPException, status
import razorpay
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("core.razorpay")


def get_razorpay_client() -> razorpay.Client:
    """
    Instantiate and return official Razorpay SDK client.

    Raises:
        HTTPException(500): If Razorpay API credentials are not configured on the server.
    """
    settings = get_settings()
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        logger.error("razorpay_credentials_missing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Razorpay payment gateway credentials are not configured on the server.",
        )
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def verify_payment_signature(
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """
    Cryptographically verify Razorpay payment signature using HMAC-SHA256.

    Uses hmac.compare_digest() for constant-time comparison against timing attacks.
    Formula: HMAC-SHA256(order_id + "|" + payment_id, RAZORPAY_KEY_SECRET)
    """
    settings = get_settings()
    if not settings.RAZORPAY_KEY_SECRET:
        logger.error("razorpay_key_secret_missing_for_signature_verification")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server payment configuration is incomplete.",
        )

    message = f"{razorpay_order_id}|{razorpay_payment_id}".encode("utf-8")
    expected_signature = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, razorpay_signature)


def verify_webhook_signature(
    raw_body: bytes,
    signature_header: str,
) -> bool:
    """
    Cryptographically verify Razorpay Webhook signature using HMAC-SHA256.

    Uses hmac.compare_digest() for constant-time comparison.
    Formula: HMAC-SHA256(raw_request_body, RAZORPAY_WEBHOOK_SECRET)
    """
    settings = get_settings()
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("razorpay_webhook_secret_missing")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server payment webhook configuration is incomplete.",
        )

    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_signature, signature_header)
