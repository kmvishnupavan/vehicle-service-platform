"""
Tests for Phase 10: Environment Configuration & Validation Strategy.

Covers:
- Configuration validation across all 4 environments (development, test, staging, production)
- Financial safety invariant: LIVE_PAYOUTS_ENABLED must be False in development, test, and staging
- Strict production checks: debug mode forbidden, wildcards forbidden, localhost origins forbidden
- Actionable error reporting on missing secrets
- Startup failure behavior on invalid production configuration
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.safety import validate_environment_configuration


# ---------------------------------------------------------------------------
# 1. Development Environment Validation
# ---------------------------------------------------------------------------

def test_development_valid_configuration():
    """Development environment permits localhost CORS and standard test values."""
    settings = Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_dev_key",
        SUPABASE_SERVICE_ROLE_KEY="placeholder_service_role_key",
        CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"],
        LIVE_PAYOUTS_ENABLED=False,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert result["environment"] == "development"


def test_development_blocks_live_payouts_flag():
    """Development environment fails validation if LIVE_PAYOUTS_ENABLED is accidentally True."""
    settings = Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_dev_key",
        SUPABASE_SERVICE_ROLE_KEY="placeholder_service_role_key",
        LIVE_PAYOUTS_ENABLED=True,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("LIVE_PAYOUTS_ENABLED must be False" in err for err in result["errors"])


def test_development_blocks_live_payout_provider_mode():
    """Development environment blocks PAYOUT_PROVIDER_MODE='live'."""
    settings = Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_dev_key",
        SUPABASE_SERVICE_ROLE_KEY="placeholder_service_role_key",
        PAYOUT_PROVIDER_MODE="live",
        LIVE_PAYOUTS_ENABLED=False,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("PAYOUT_PROVIDER_MODE cannot be 'live'" in err for err in result["errors"])


# ---------------------------------------------------------------------------
# 2. Test Environment Validation
# ---------------------------------------------------------------------------

def test_test_environment_valid_configuration():
    """Test environment allows mocked values but enforces payout safety."""
    settings = Settings(
        ENVIRONMENT="test",
        DEBUG=False,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test_key",
        SUPABASE_SERVICE_ROLE_KEY="service_role_test_key",
        LIVE_PAYOUTS_ENABLED=False,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is True
    assert result["environment"] == "test"


def test_test_environment_blocks_live_payouts():
    """Test environment blocks real money disbursement."""
    settings = Settings(
        ENVIRONMENT="test",
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test_key",
        SUPABASE_SERVICE_ROLE_KEY="service_role_test_key",
        LIVE_PAYOUTS_ENABLED=True,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("LIVE_PAYOUTS_ENABLED must be False" in err for err in result["errors"])


# ---------------------------------------------------------------------------
# 3. Staging Environment Validation
# ---------------------------------------------------------------------------

def test_staging_valid_configuration():
    """Staging environment accepts valid staging URLs and non-wildcard CORS."""
    settings = Settings(
        ENVIRONMENT="staging",
        DEBUG=False,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_staging_key",
        SUPABASE_SERVICE_ROLE_KEY="service_role_staging_key",
        CORS_ORIGINS=["https://staging.vehiclecare.app"],
        LIVE_PAYOUTS_ENABLED=False,
        PAYOUT_PROVIDER_MODE="sandbox",
        RAZORPAY_KEY_ID="rzp_test_staging_key",
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is True
    assert result["environment"] == "staging"


def test_staging_blocks_live_payouts():
    """Staging environment strictly forbids real-money payout activation."""
    settings = Settings(
        ENVIRONMENT="staging",
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_staging_key",
        SUPABASE_SERVICE_ROLE_KEY="service_role_staging_key",
        CORS_ORIGINS=["https://staging.vehiclecare.app"],
        LIVE_PAYOUTS_ENABLED=True,
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("LIVE_PAYOUTS_ENABLED must be False" in err for err in result["errors"])


def test_staging_rejects_wildcard_cors():
    """Staging rejects wildcard CORS origins via Pydantic model validator."""
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="staging",
            SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_staging_key",
            SUPABASE_SERVICE_ROLE_KEY="service_role_staging_key",
            CORS_ORIGINS=["*"],
        )


# ---------------------------------------------------------------------------
# 4. Production Environment Validation
# ---------------------------------------------------------------------------

def test_production_valid_configuration():
    """Valid production configuration passes with explicit domains, no debug, and real keys."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_prod_real_key_001",
        SUPABASE_SERVICE_ROLE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.prod_real_key_999",
        SUPABASE_JWT_SECRET="production_jwt_secret_min_32_characters_strictly_long",
        CORS_ORIGINS=["https://app.vehiclecare.com", "https://admin.vehiclecare.com"],
        LIVE_PAYOUTS_ENABLED=False,
        RAZORPAY_KEY_ID="rzp_test_prod_gate",
        RAZORPAY_KEY_SECRET="prod_secret_12345",
        RAZORPAY_WEBHOOK_SECRET="prod_wh_secret_9999",
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is True
    assert len(result["errors"]) == 0
    assert result["environment"] == "production"


def test_production_rejects_debug_true():
    """Production fails if DEBUG is enabled."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_prod_key",
        SUPABASE_SERVICE_ROLE_KEY="real_key_secret_not_placeholder_123",
        CORS_ORIGINS=["https://app.vehiclecare.com"],
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("DEBUG mode must be False in production" in err for err in result["errors"])


def test_production_rejects_wildcard_cors():
    """Production rejects wildcard '*' CORS origins."""
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
            SUPABASE_PUBLISHABLE_KEY="sb_publishable_prod_key",
            SUPABASE_SERVICE_ROLE_KEY="real_key_secret_not_placeholder_123",
            CORS_ORIGINS=["*"],
        )


def test_production_rejects_localhost_cors():
    """Production fails if localhost or 127.0.0.1 is in CORS_ORIGINS."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_prod_key",
        SUPABASE_SERVICE_ROLE_KEY="real_key_secret_not_placeholder_123",
        CORS_ORIGINS=["http://localhost:3000", "https://app.vehiclecare.com"],
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("Localhost CORS origin forbidden in production" in err for err in result["errors"])


def test_production_rejects_placeholder_service_role_key():
    """Production fails if placeholder service role key is configured."""
    settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_prod_key",
        SUPABASE_SERVICE_ROLE_KEY="placeholder_service_role_key_value",
        CORS_ORIGINS=["https://app.vehiclecare.com"],
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("placeholder values" in err for err in result["errors"])


def test_invalid_environment_name_rejected():
    """Unknown environment string produces clear error."""
    settings = Settings(
        ENVIRONMENT="sandbox-custom-env",
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_key",
        SUPABASE_SERVICE_ROLE_KEY="service_key",
    )
    result = validate_environment_configuration(settings)
    assert result["valid"] is False
    assert any("Invalid ENVIRONMENT" in err for err in result["errors"])
