"""
Notification Retry Service (Phase 13).

Provides:
- Persistent retry queue management in public.notification_retries
- Exponential backoff calculation (30s, 60s, 120s, 240s, 480s)
- Idempotent delivery protection via unique idempotency keys
"""

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client

logger = get_logger("services.notification_retry")


class NotificationRetryService:
    """Manages enqueueing and retrying failed user notifications."""

    def __init__(self, client: Any = None):
        self.client = client or get_supabase_service_client()

    async def enqueue_failed_notification(
        self,
        user_id: uuid.UUID,
        title: str,
        message: str,
        notification_type: str = "info",
        data: dict[str, Any] | None = None,
        event_id: str | None = None,
        last_error: str | None = None,
    ) -> dict[str, Any] | None:
        """Enqueue a failed notification for automated exponential backoff retry."""
        now = datetime.now(timezone.utc)
        idempotency_key = event_id or f"retry_{user_id}_{now.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        next_retry = now + timedelta(seconds=30)

        payload = {
            "title": title,
            "message": message,
            "type": notification_type,
            "data": data or {},
        }

        row = {
            "user_id": str(user_id),
            "idempotency_key": idempotency_key,
            "payload": payload,
            "attempt_count": 1,
            "max_attempts": 5,
            "last_attempt_at": now.isoformat(),
            "next_retry_at": next_retry.isoformat(),
            "status": "pending",
            "last_error": last_error,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        try:
            res = (
                self.client.table("notification_retries")
                .upsert(row, on_conflict="idempotency_key")
                .execute()
            )
            logger.info("notification_retry_enqueued", user_id=str(user_id), idempotency_key=idempotency_key)
            return res.data[0] if res.data else row
        except Exception as exc:
            logger.error("failed_to_enqueue_notification_retry", error=str(exc))
            return None
