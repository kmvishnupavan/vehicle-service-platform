"""
Audit Logging Module.

Provides secure, structured persistence for security-relevant and financial lifecycle events.
Logs to PostgreSQL public.audit_logs via Supabase service-role client.
Ensures zero secret leakage (redacts authorization tokens, gateway secrets, signatures, and cardholder data).
"""

from datetime import datetime, timezone
from typing import Any
import uuid
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("core.audit")

SENSITIVE_KEYS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "key_secret",
    "webhook_secret",
    "razorpay_key_secret",
    "razorpay_webhook_secret",
    "razorpay_signature",
    "signature",
    "pan",
    "cvv",
    "card_number",
    "authorization",
}


def sanitize_audit_payload(payload: Any) -> Any:
    """Recursively redact sensitive keys from audit log dictionaries."""
    if isinstance(payload, dict):
        sanitized = {}
        for k, v in payload.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_audit_payload(v)
        return sanitized
    elif isinstance(payload, list):
        return [sanitize_audit_payload(item) for item in payload]
    return payload


def record_audit_log(
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | str | None = None,
    actor_id: uuid.UUID | str | None = None,
    actor_role: str | None = None,
    old_data: dict[str, Any] | None = None,
    new_data: dict[str, Any] | None = None,
    old_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    client: Any = None,
) -> None:
    """
    Persist an audit log record to public.audit_logs matching PostgreSQL schema:
    Columns: id, actor_id, action, entity_type, entity_id, old_data, new_data, ip_address, user_agent, created_at.

    Fails safely in production without raising exceptions to calling application flows.
    In testing environment, raises schema/column errors to prevent silent schema drift.
    """
    try:
        supabase_client = client or get_supabase_service_client()
        record: dict[str, Any] = {
            "action": action,
            "entity_type": entity_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Resolve payload data (support new_data and legacy new_state)
        merged_new = dict(new_data) if new_data is not None else (dict(new_state) if new_state is not None else {})
        if actor_role and "actor_role" not in merged_new:
            merged_new["actor_role"] = actor_role

        merged_old = dict(old_data) if old_data is not None else (dict(old_state) if old_state is not None else None)

        if entity_id:
            try:
                record["entity_id"] = str(uuid.UUID(str(entity_id)))
            except (ValueError, TypeError):
                # If not a valid UUID (e.g. string order_id or event_id), save reference in new_data
                merged_new["entity_ref"] = str(entity_id)

        if actor_id:
            try:
                record["actor_id"] = str(uuid.UUID(str(actor_id)))
            except (ValueError, TypeError):
                merged_new["actor_ref"] = str(actor_id)

        if merged_old is not None:
            record["old_data"] = sanitize_audit_payload(merged_old)
        if merged_new:
            record["new_data"] = sanitize_audit_payload(merged_new)
        if ip_address:
            record["ip_address"] = str(ip_address)
        if user_agent:
            record["user_agent"] = str(user_agent)[:255]

        supabase_client.table("audit_logs").insert(record).execute()
        logger.info(
            "audit_log_recorded",
            action=action,
            entity_type=entity_type,
            entity_id=record.get("entity_id"),
            actor_role=actor_role,
        )
    except Exception as exc:
        logger.warning(
            "audit_log_insertion_failed",
            action=action,
            entity_type=entity_type,
            error=str(exc),
        )
        import os
        import sys
        from app.core.config import get_settings
        is_testing = (
            "pytest" in sys.modules
            or os.environ.get("ENVIRONMENT") == "testing"
            or get_settings().ENVIRONMENT == "testing"
        )
        # In testing environment, do not silently swallow schema or column errors
        if is_testing and any(
            term in str(exc).lower() for term in ["column", "schema", "syntax", "does not exist", "relation", "type"]
        ):
            raise exc
