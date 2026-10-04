"""
Thread-Safe In-Memory Routing and ETA Cache (Phase 11).

Caches road network ETA calculations to prevent excessive routing API requests.
Uses spatial quantization (rounding lat/long to 3 decimal places ~110m) to group nearby queries.
"""

from datetime import datetime, timezone
import threading
from typing import Any
from app.services.routing.base import ETAResult


class ETACache:
    """In-memory thread-safe cache for routing ETA calculations."""

    def __init__(self, default_ttl_seconds: int = 300, max_entries: int = 1000):
        self._default_ttl = default_ttl_seconds
        self._max_entries = max_entries
        self._store: dict[str, tuple[ETAResult, datetime]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def generate_spatial_key(
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> str:
        """Quantize coordinates to 3 decimal places (~110m grid) for key grouping."""
        return (
            f"{round(origin_lat, 3)}:{round(origin_lng, 3)}->"
            f"{round(dest_lat, 3)}:{round(dest_lng, 3)}"
        )

    def get(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> ETAResult | None:
        """Retrieve non-expired ETA result from cache."""
        key = self.generate_spatial_key(origin_lat, origin_lng, dest_lat, dest_lng)
        now = datetime.now(timezone.utc)

        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None

            result, expires_at = entry
            if now > expires_at:
                del self._store[key]
                return None

            # Return a copy marked as cached
            return ETAResult(
                duration_minutes=result.duration_minutes,
                distance_km=result.distance_km,
                is_cached=True,
                provider_source=result.provider_source,
            )

    def set(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
        result: ETAResult,
        ttl_seconds: int | None = None,
    ) -> None:
        """Store an ETA result in the cache."""
        key = self.generate_spatial_key(origin_lat, origin_lng, dest_lat, dest_lng)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        now = datetime.now(timezone.utc)
        expires_at = datetime.fromtimestamp(now.timestamp() + ttl, tz=timezone.utc)

        with self._lock:
            # Simple eviction if max capacity reached
            if len(self._store) >= self._max_entries:
                # Evict first 100 expired or arbitrary keys
                expired_keys = [k for k, (_, exp) in self._store.items() if now > exp]
                if expired_keys:
                    for k in expired_keys[:100]:
                        del self._store[k]
                else:
                    # Evict oldest entry
                    oldest_key = next(iter(self._store))
                    del self._store[oldest_key]

            self._store[key] = (result, expires_at)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._store.clear()
