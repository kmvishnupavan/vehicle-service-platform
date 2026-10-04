"""
Application Configuration Module.

Loads and validates environment variables using Pydantic Settings v2.
Ensures zero hardcoded secrets and enforces secure defaults.
"""

from functools import lru_cache
import json
from typing import Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application
    ENVIRONMENT: str = Field(default="development", description="Environment mode: development, staging, production")
    DEBUG: bool = Field(default=False, description="Debug mode flag")
    PROJECT_NAME: str = Field(default="Vehicle Service Platform API", description="Project display title")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL prefix for API version 1")
    LIVE_PAYOUTS_ENABLED: bool = Field(default=False, description="Hard gate for real-money payouts (MUST be false in test/dev)")

    # Server Bindings
    HOST: str = Field(default="0.0.0.0", description="Host address for Uvicorn server")
    PORT: int = Field(default=8000, description="Port number for Uvicorn server")

    # CORS Configuration
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "http://127.0.0.1:5173"],
        description="Allowed CORS origins list"
    )

    # Supabase Credentials (Required)
    SUPABASE_URL: str = Field(..., description="Supabase project API URL")
    SUPABASE_PUBLISHABLE_KEY: str = Field(..., description="Supabase publishable or anon key")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(..., description="Supabase service role secret key (NEVER expose to client)")
    SUPABASE_JWT_SECRET: str = Field(default="", description="Supabase JWT secret for symmetric token verification")

    # Payment Gateway (Razorpay)
    RAZORPAY_KEY_ID: str | None = Field(default=None, description="Razorpay key ID")
    RAZORPAY_KEY_SECRET: str | None = Field(default=None, description="Razorpay key secret")
    RAZORPAY_WEBHOOK_SECRET: str | None = Field(default=None, description="Razorpay webhook secret")

    # Routing & Maps (Phase 15 Production Hardened)
    ROUTING_PROVIDER: str | None = Field(default="osrm", description="Routing service provider")
    ROUTING_API_KEY: str | None = Field(default=None, description="Routing service API key")
    OSRM_BASE_URL: str = Field(default="http://router.project-osrm.org", description="OSRM endpoint (dedicated or self-hosted in production)")

    # Realtime & Location Tracking Guards
    MECHANIC_LOCATION_MIN_INTERVAL_SECONDS: int = Field(
        default=5, ge=1, le=60, description="Minimum seconds between mechanic location GPS history updates"
    )

    # Platform & Storage Identifiers
    APP_NAME: str = Field(default="Vehicle Service Platform", description="Application name")
    FRONTEND_URL: str = Field(default="http://localhost:5173", description="Frontend application URL")
    PAYOUT_PROVIDER_MODE: str = Field(default="sandbox", description="Payout provider mode: sandbox, test, live")
    STORAGE_BUCKET_ATTACHMENTS: str = Field(default="attachments", description="Evidence attachments bucket")
    STORAGE_BUCKET_AVATARS: str = Field(default="avatars", description="User avatars bucket")

    # Web Push / VAPID (Phase 15.1 Production Hardened)
    VAPID_PUBLIC_KEY: str | None = Field(default=None, description="VAPID public key for Web Push")
    VAPID_PRIVATE_KEY: str | None = Field(default=None, description="VAPID private key for Web Push (backend secret)")
    VAPID_CLAIM_EMAIL: str = Field(default="admin@vehiclecare.app", description="Contact email for VAPID push claims")

    # Operational Alerting
    ALERT_WEBHOOK_URL: str | None = Field(default=None, description="Webhook endpoint for SEV-1/SEV-2 incident alerts (Slack/PagerDuty)")

    # Phase 15.1 Controlled Pilot Safety Kill Switches (Operational Circuit Breakers)
    KILL_SWITCH_MATCHING_DISABLED: bool = Field(default=False, description="Emergency stop: halt new matching sessions")
    KILL_SWITCH_NEW_BOOKINGS_DISABLED: bool = Field(default=False, description="Emergency stop: halt new customer bookings")
    KILL_SWITCH_SCHEDULED_DISPATCH_DISABLED: bool = Field(default=False, description="Emergency stop: halt scheduled booking dispatch worker")
    KILL_SWITCH_NOTIFICATIONS_DISABLED: bool = Field(default=False, description="Emergency stop: halt notification retry worker")
    KILL_SWITCH_FORCE_ROUTING_FALLBACK: bool = Field(default=False, description="Emergency stop: bypass OSRM and force Haversine fallback")

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        """Parse CORS origins from a list, JSON string, or comma-separated string."""
        if isinstance(v, str):
            v_trimmed = v.strip()
            if v_trimmed.startswith("[") and v_trimmed.endswith("]"):
                try:
                    return json.loads(v_trimmed)
                except json.JSONDecodeError:
                    pass
            return [i.strip() for i in v_trimmed.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(i).strip() for i in v if str(i).strip()]
        return []

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_production(cls, v: list[str], info) -> list[str]:
        """Ensure wildcards are rejected in production and staging."""
        env = str(info.data.get("ENVIRONMENT", "")).lower()
        if env in ("production", "staging") and "*" in v:
            raise ValueError(f"Wildcard '*' CORS origins are strictly forbidden in {env}.")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_staging(self) -> bool:
        return self.ENVIRONMENT.lower() == "staging"

    @property
    def is_test(self) -> bool:
        return self.ENVIRONMENT.lower() in ("test", "testing")

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Retrieve cached application settings instance."""
    return Settings()
