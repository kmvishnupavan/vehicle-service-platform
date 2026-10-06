"""
Supabase Client Factory and Database Health Check.

Initializes isolated clients for:
1. Normal operations (publishable/anon key)
2. Privileged backend operations (service-role key)

CRITICAL SECURITY RULE:
The service-role key is backend-only and must NEVER be serialized, logged,
or exposed through any API response or React client payload.
"""

from contextvars import ContextVar
from typing import Any
from supabase import create_client, Client
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("db.supabase")

_supabase_publishable_client: Client | None = None
_supabase_service_client: Client | None = None
_current_auth_token: ContextVar[str | None] = ContextVar("current_auth_token", default=None)


def set_current_auth_token(token: str | None) -> None:
    """Bind verified Bearer token to current async request context."""
    _current_auth_token.set(token)


def get_current_auth_token() -> str | None:
    """Retrieve current async request context Bearer token."""
    return _current_auth_token.get()


def get_supabase_client() -> Client:
    """
    Get or create the Supabase client initialized with the publishable/anon key.
    Safe for non-privileged client operations subject to public/authenticated RLS.
    """
    global _supabase_publishable_client
    if _supabase_publishable_client is None:
        settings = get_settings()
        if not settings.SUPABASE_URL or not settings.SUPABASE_PUBLISHABLE_KEY:
            raise ValueError("SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be configured.")
        _supabase_publishable_client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_PUBLISHABLE_KEY,
        )
    return _supabase_publishable_client


def get_supabase_service_client() -> Client:
    """
    Get or create the privileged Supabase client initialized with the service-role key.
    
    WARNING:
    This client bypasses Row Level Security (RLS). It must only be used by authorized
    backend business logic and services (e.g. system transitions, admin overrides, payments).
    In development environments where SUPABASE_SERVICE_ROLE_KEY is a placeholder,
    falls back to publishable client authenticated with the request's Bearer token.
    """
    global _supabase_service_client
    settings = get_settings()
    token = get_current_auth_token()

    # If active valid service role key is configured, use service-role singleton
    if settings.SUPABASE_SERVICE_ROLE_KEY and not settings.SUPABASE_SERVICE_ROLE_KEY.startswith("placeholder"):
        if _supabase_service_client is None:
            if not settings.SUPABASE_URL:
                raise ValueError("SUPABASE_URL must be configured.")
            _supabase_service_client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY,
            )
        return _supabase_service_client

    # Fallback for development/testing: use publishable client with request-level auth if available
    client = create_client(settings.SUPABASE_URL, settings.SUPABASE_PUBLISHABLE_KEY)
    if token:
        client.postgrest.auth(token)
    return client


async def check_database_connection() -> dict[str, Any]:
    """
    Verify database connectivity by executing a lightweight read query against the profiles table.
    Returns status dictionary indicating connectivity and latency.
    """
    try:
        # We attempt using publishable client first or service client
        client = get_supabase_client()
        # Simple limit 1 query against public.profiles
        response = client.table("profiles").select("id").limit(1).execute()
        return {
            "status": "connected",
            "healthy": True,
            "error": None,
        }
    except Exception as exc:
        logger.error("database_health_check_failed", error=str(exc))
        return {
            "status": "disconnected",
            "healthy": False,
            "error": "Failed to connect to Supabase database",
        }
