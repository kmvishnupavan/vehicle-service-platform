"""
Realtime Location Service (Phase 8.2B).

Authoritative coordinator for ephemeral live mechanic location broadcasts
via Supabase Realtime Broadcast Channels.

Architecture:
- High-frequency location updates are dispatched directly to the booking-specific private channel.
- Topic format: `booking-location:{booking_id}`
- Event name: `mechanic_location`
- Transport: Supabase Realtime REST broadcast (stateless, server-side, resilient).
- Error isolation: Realtime broadcast failures NEVER roll back or disrupt database operations.
"""

from datetime import datetime, timezone
from decimal import Decimal
import threading
from typing import Any
import uuid
import httpx
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("services.realtime_location")


class RealtimeLocationService:
    """Manages ephemeral Realtime Broadcast delivery for live mechanic tracking."""

    _sequence_lock = threading.Lock()
    _sequence_counter: int = 0

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self.settings = get_settings()
        self._http_client = http_client

    @classmethod
    def get_next_sequence(cls) -> int:
        """Generate a thread-safe monotonically increasing integer sequence number."""
        with cls._sequence_lock:
            cls._sequence_counter += 1
            return cls._sequence_counter

    @staticmethod
    def get_topic_for_booking(booking_id: uuid.UUID | str) -> str:
        """Derive the deterministic private topic for a booking."""
        return f"booking-location:{str(booking_id)}"

    def _get_api_key(self) -> str:
        """Retrieve appropriate server-side API key for Realtime REST broadcast."""
        sr_key = self.settings.SUPABASE_SERVICE_ROLE_KEY
        if sr_key and sr_key != "placeholder_service_role_key":
            return sr_key
        return self.settings.SUPABASE_PUBLISHABLE_KEY

    async def broadcast_mechanic_location(
        self,
        booking_id: uuid.UUID,
        mechanic_id: uuid.UUID,
        latitude: Decimal | float,
        longitude: Decimal | float,
        accuracy_meters: Decimal | float | None = None,
        recorded_at: str | datetime | None = None,
        sequence: int | None = None,
    ) -> bool:
        """
        Broadcast ephemeral live GPS coordinates to the authorized booking channel.

        Security & Privacy Guarantees:
        - Payload contains only safe tracking attributes (no phone, email, tokens, secrets).
        - Topic is strictly scoped to the specific booking: `booking-location:{booking_id}`.
        - Non-blocking: Errors are caught and logged without disrupting callers.
        """
        # Format recorded_at timestamp
        if recorded_at is None:
            now_iso = datetime.now(timezone.utc).isoformat()
        elif isinstance(recorded_at, datetime):
            now_iso = recorded_at.isoformat()
        else:
            now_iso = str(recorded_at)

        # Monotonic sequence
        seq_num = sequence if sequence is not None else self.get_next_sequence()

        # Build contract-compliant payload
        payload: dict[str, Any] = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic_id),
            "latitude": float(latitude),
            "longitude": float(longitude),
            "accuracy_meters": float(accuracy_meters) if accuracy_meters is not None else None,
            "recorded_at": now_iso,
            "sequence": seq_num,
        }

        topic = self.get_topic_for_booking(booking_id)
        api_key = self._get_api_key()
        broadcast_url = f"{self.settings.SUPABASE_URL.rstrip('/')}/realtime/v1/api/broadcast"

        request_body = {
            "messages": [
                {
                    "topic": topic,
                    "event": "mechanic_location",
                    "payload": payload,
                    "private": True,
                }
            ]
        }

        headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            if self._http_client is not None:
                resp = await self._http_client.post(
                    broadcast_url,
                    headers=headers,
                    json=request_body,
                    timeout=5.0,
                )
            else:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(
                        broadcast_url,
                        headers=headers,
                        json=request_body,
                    )

            if resp.status_code in (200, 202):
                logger.debug(
                    "realtime_location_broadcast_success",
                    booking_id=str(booking_id),
                    mechanic_id=str(mechanic_id),
                    sequence=seq_num,
                    status_code=resp.status_code,
                )
                return True
            else:
                logger.warning(
                    "realtime_location_broadcast_rejected",
                    booking_id=str(booking_id),
                    status_code=resp.status_code,
                    response=resp.text,
                )
                return False

        except Exception as exc:
            logger.warning(
                "realtime_location_broadcast_failed",
                booking_id=str(booking_id),
                mechanic_id=str(mechanic_id),
                error=str(exc),
            )
            return False
