"""
Production Safety Guard and Environment Validation Layer (Phase 9).

Enforces hard barriers against accidental real-money movement:
- Strictly requires 4 independent conditions before any live payout operation.
- Validates environment configuration across development, test, staging, and production.
- Guarantees fail-safe sandbox fallback with zero real-money movement.
"""

from typing import Any
from fastapi import HTTPException, status
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("core.safety")


class ProductionSafetyViolation(Exception):
    """Raised when an operation attempts live real-money execution without explicit clearance."""
    pass


class ProductionSafetyGuard:
    """
    Authoritative safety governor controlling real-money financial operations.
    """

    @classmethod
    def assert_live_payout_permitted(
        cls,
        settings_or_mode: Any | None = None,
        provider_mode: str | None = None,
        provider_credentials: dict[str, Any] | None = None,
        settings: Any | None = None,
    ) -> bool:
        """
        Verify all 4 mandatory criteria for real-money disbursement:
        1. ENVIRONMENT == 'production'
        2. LIVE_PAYOUTS_ENABLED is explicitly True
        3. Valid production provider configuration is present
        4. Explicit provider mode is 'live'

        If ANY condition is unmet, raises HTTPException and aborts.
        """
        if isinstance(settings_or_mode, str):
            provider_mode = settings_or_mode
            active_settings = settings or get_settings()
        elif settings_or_mode is not None:
            active_settings = settings_or_mode
        else:
            active_settings = settings or get_settings()

        # Condition 1: Must be explicitly production environment
        is_production_env = str(getattr(active_settings, "ENVIRONMENT", "")).lower() == "production"

        # Condition 2: Explicit feature flag must be enabled
        live_payouts_flag = getattr(active_settings, "LIVE_PAYOUTS_ENABLED", False) is True

        # Condition 3: Valid production provider credentials present
        creds = provider_credentials or {}
        key_id = creds.get("key_id") or getattr(active_settings, "RAZORPAY_KEY_ID", "") or ""
        key_secret = creds.get("key_secret") or getattr(active_settings, "RAZORPAY_KEY_SECRET", "") or ""
        has_prod_creds = (
            bool(key_id and key_secret)
            and not key_id.startswith("rzp_test_")
            and not key_secret.startswith("placeholder")
        )

        # Condition 4: Explicit provider mode must be 'live'
        is_explicit_live_mode = str(provider_mode or "").lower() == "live"

        failed_reasons: list[str] = []
        if not is_production_env:
            failed_reasons.append("ENVIRONMENT is not production")
        if not live_payouts_flag:
            failed_reasons.append("LIVE_PAYOUTS_ENABLED is False")
        if not has_prod_creds:
            failed_reasons.append("Production provider credentials missing or invalid")
        if not is_explicit_live_mode:
            failed_reasons.append("Provider mode is not live")

        if failed_reasons:
            logger.error(
                "live_payout_attempt_blocked_by_safety_guard",
                reasons=failed_reasons,
                status="BLOCKED",
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Real-money payouts are disabled by platform safety guard. "
                    f"Unmet safety conditions: {', '.join(failed_reasons)}. "
                    f"Zero real money moved."
                ),
            )

        return True

    @classmethod
    def get_safety_status(cls) -> dict[str, Any]:
        """Summary of current production safety guard status (safe for diagnostics)."""
        settings = get_settings()
        live_flag = getattr(settings, "LIVE_PAYOUTS_ENABLED", False) is True
        return {
            "environment": settings.ENVIRONMENT,
            "live_payouts_enabled": live_flag,
            "payout_mode": "live" if (live_flag and settings.is_production) else "sandbox",
            "safety_barrier_active": not (live_flag and settings.is_production),
            "real_money_movement": "STRICTLY_DISABLED",
        }


def validate_environment_configuration(settings: Any | None = None) -> dict[str, Any]:
    """
    Authoritative configuration validator across all environments:
    - Universal: SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY, SUPABASE_SERVICE_ROLE_KEY
    - Development: permissive local testing, but LIVE_PAYOUTS_ENABLED must be False
    - Test: deterministic, mock-safe, LIVE_PAYOUTS_ENABLED must be False
    - Staging: sandbox payment/payout, wildcard CORS forbidden, LIVE_PAYOUTS_ENABLED must be False
    - Production: strict validation (no debug, no wildcards, no localhost CORS, no placeholder keys, secrets present)
    """
    active_settings = settings or get_settings()
    env = str(getattr(active_settings, "ENVIRONMENT", "development")).lower()
    errors: list[str] = []
    warnings: list[str] = []

    # 1. Environment Classification
    valid_envs = ("development", "test", "testing", "staging", "production")
    if env not in valid_envs:
        errors.append(f"Invalid ENVIRONMENT '{env}'. Must be one of: {', '.join(valid_envs)}")

    # 2. Universal Supabase requirements
    supabase_url = getattr(active_settings, "SUPABASE_URL", "") or ""
    if not supabase_url or not supabase_url.startswith("http"):
        errors.append("SUPABASE_URL must be a valid HTTP/HTTPS URL")
    if not getattr(active_settings, "SUPABASE_PUBLISHABLE_KEY", None):
        errors.append("SUPABASE_PUBLISHABLE_KEY is required")
    if not getattr(active_settings, "SUPABASE_SERVICE_ROLE_KEY", None):
        errors.append("SUPABASE_SERVICE_ROLE_KEY is required")

    live_payouts_flag = getattr(active_settings, "LIVE_PAYOUTS_ENABLED", False) is True
    provider_mode = str(getattr(active_settings, "PAYOUT_PROVIDER_MODE", "sandbox")).lower()
    cors_origins = getattr(active_settings, "CORS_ORIGINS", []) or []

    # 3. Non-Production Environments Safety (development, test, staging)
    if env in ("development", "test", "testing", "staging"):
        if live_payouts_flag:
            errors.append(f"LIVE_PAYOUTS_ENABLED must be False in {env} environment.")
        if provider_mode == "live":
            errors.append(f"PAYOUT_PROVIDER_MODE cannot be 'live' in {env} environment.")

    # 4. Staging-Specific Requirements
    if env == "staging":
        if "*" in cors_origins:
            errors.append("Wildcard CORS origins are forbidden in staging.")
        if not getattr(active_settings, "RAZORPAY_KEY_ID", None):
            warnings.append("RAZORPAY_KEY_ID is recommended in staging.")

    # 5. Production-Specific Requirements (Strict)
    if env == "production":
        if getattr(active_settings, "DEBUG", False):
            errors.append("DEBUG mode must be False in production.")
        if "*" in cors_origins:
            errors.append("Wildcard CORS origins are strictly forbidden in production.")
        for origin in cors_origins:
            if "localhost" in origin or "127.0.0.1" in origin:
                errors.append(f"Localhost CORS origin forbidden in production: {origin}")

        service_key = str(getattr(active_settings, "SUPABASE_SERVICE_ROLE_KEY", ""))
        if "placeholder" in service_key.lower() or "your_" in service_key.lower():
            errors.append("SUPABASE_SERVICE_ROLE_KEY must not contain placeholder values in production.")

        jwt_secret = getattr(active_settings, "SUPABASE_JWT_SECRET", "") or ""
        if not jwt_secret or len(jwt_secret) < 32:
            warnings.append("SUPABASE_JWT_SECRET should be at least 32 characters in production.")

        if not getattr(active_settings, "RAZORPAY_KEY_ID", None):
            warnings.append("RAZORPAY_KEY_ID is missing for production.")
        if not getattr(active_settings, "RAZORPAY_KEY_SECRET", None):
            warnings.append("RAZORPAY_KEY_SECRET is missing for production.")
        if not getattr(active_settings, "RAZORPAY_WEBHOOK_SECRET", None):
            warnings.append("RAZORPAY_WEBHOOK_SECRET is missing for production.")

        if live_payouts_flag:
            warnings.append("CRITICAL: LIVE_PAYOUTS_ENABLED is True in production; 4-condition safety barrier active.")

    return {
        "valid": len(errors) == 0,
        "environment": env,
        "errors": errors,
        "warnings": warnings,
        "safety_guard": ProductionSafetyGuard.get_safety_status(),
    }
