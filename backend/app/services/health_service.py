"""
Health & Readiness Diagnostics Service (Phase 9).

Provides production probes:
- Liveness Probe (/health/live): Lightweight process alive check.
- Readiness Probe (/health/ready): Evaluates dependencies required to accept traffic
  (Database, Schema, Environment Configuration, Payout Safety Sandbox, Notification Infra).
- Zero secrets or internal database connection strings leaked.
"""

from datetime import datetime, timezone
from typing import Any
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.safety import ProductionSafetyGuard, validate_environment_configuration
from app.db.supabase import check_database_connection, get_supabase_service_client

logger = get_logger("services.health")


class HealthService:
    """Evaluates component readiness and system operational metrics."""

    @classmethod
    async def get_liveness(cls) -> dict[str, Any]:
        """Lightweight process liveness check."""
        return {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def get_readiness(cls) -> tuple[int, dict[str, Any]]:
        """
        Deep readiness probe verifying critical runtime prerequisites.
        Returns (http_status_code, response_payload).
        """
        settings = get_settings()
        now_iso = datetime.now(timezone.utc).isoformat()
        checks: dict[str, str] = {}
        all_ready = True

        # 1. Database Connectivity
        db_res = await check_database_connection()
        if db_res.get("healthy"):
            checks["database"] = "connected"
        else:
            checks["database"] = "unreachable"
            all_ready = False

        # 2. Schema Verification (Core Tables Accessibility)
        try:
            client = get_supabase_service_client()
            # Verify primary operational tables
            client.table("bookings").select("id").limit(1).execute()
            client.table("payments").select("id").limit(1).execute()
            client.table("mechanic_payout_ledger").select("id").limit(1).execute()
            client.table("webhook_events").select("id").limit(1).execute()
            client.table("settlement_batches").select("id").limit(1).execute()
            checks["schema"] = "verified"
        except Exception as schema_err:
            logger.warning("readiness_schema_check_failed", error=str(schema_err))
            checks["schema"] = "degraded"
            if settings.is_production:
                all_ready = False

        # 3. Environment Configuration
        env_val = validate_environment_configuration()
        if env_val.get("valid"):
            checks["configuration"] = "valid"
        else:
            checks["configuration"] = "invalid"
            all_ready = False

        # 4. Payout Safety Isolation
        safety_status = ProductionSafetyGuard.get_safety_status()
        if safety_status.get("real_money_movement") == "STRICTLY_DISABLED":
            checks["payout_safety"] = "sandbox_enforced"
        else:
            checks["payout_safety"] = "unverified"
            all_ready = False

        # 5. Notification Infrastructure
        try:
            client = get_supabase_service_client()
            client.table("notifications").select("id").limit(1).execute()
            checks["notifications"] = "operational"
        except Exception as notif_err:
            logger.warning("readiness_notifications_check_failed", error=str(notif_err))
            checks["notifications"] = "degraded"
            # notifications degrade doesn't strictly fail overall ingress if DB works

        status_label = "ready" if all_ready else ("degraded" if checks.get("database") == "connected" else "not_ready")
        http_code = 200 if (all_ready or (not settings.is_production and checks.get("database") == "connected")) else 503

        payload = {
            "status": status_label,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
            "timestamp": now_iso,
        }

        if not all_ready:
            logger.warning("service_not_ready", checks=checks)

        return http_code, payload
