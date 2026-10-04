"""
Configuration and Environment Settings Tests.
"""

from app.core.config import Settings


def test_settings_initialization():
    """Test that settings instantiate with valid environment variables."""
    settings = Settings(
        ENVIRONMENT="development",
        DEBUG=True,
        SUPABASE_URL="https://dfigtryvvujhwuiyzdvs.supabase.co",
        SUPABASE_PUBLISHABLE_KEY="sb_publishable_test_key",
        SUPABASE_SERVICE_ROLE_KEY="test_service_role_key",
        SUPABASE_JWT_SECRET="test_jwt_secret_with_sufficient_length",
    )
    assert settings.ENVIRONMENT == "development"
    assert settings.DEBUG is True
    assert settings.is_development is True
    assert settings.is_production is False
    assert settings.API_V1_PREFIX == "/api/v1"


def test_cors_origins_parsing():
    """Test that CORS origins properly parse JSON strings and lists."""
    # List format
    s1 = Settings(
        SUPABASE_URL="https://example.com",
        SUPABASE_PUBLISHABLE_KEY="key",
        SUPABASE_SERVICE_ROLE_KEY="key",
        CORS_ORIGINS=["http://localhost:3000", "http://localhost:5173"],
    )
    assert "http://localhost:3000" in s1.CORS_ORIGINS
    assert len(s1.CORS_ORIGINS) == 2

    # Comma-separated string format
    s2 = Settings(
        SUPABASE_URL="https://example.com",
        SUPABASE_PUBLISHABLE_KEY="key",
        SUPABASE_SERVICE_ROLE_KEY="key",
        CORS_ORIGINS="http://localhost:3000, http://localhost:5173",
    )
    assert "http://localhost:3000" in s2.CORS_ORIGINS
    assert "http://localhost:5173" in s2.CORS_ORIGINS
