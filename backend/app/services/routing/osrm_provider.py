"""
OpenStreetMap / OSRM Routing Provider (Phase 11 & Phase 13 Hardened).

Integrates with OSRM (Open Source Routing Machine) REST API for road routing and turn-by-turn ETA.
Includes:
- Circuit Breaker: Trips after 3 consecutive failures to avoid blocking calls with network timeouts.
- Fallback Distinction: Tags fallback calculations explicitly as 'fallback'.
- In-memory spatial quantization caching.
"""

from datetime import datetime, timedelta, timezone
import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.routing.base import ETAResult, RouteResult, RoutingProvider
from app.services.routing.cache import ETACache
from app.services.routing.mock_provider import MockRoutingProvider

logger = get_logger("services.routing.osrm")


class OSRMRoutingProvider(RoutingProvider):
    """OSRM HTTP client with automatic resilient fallback and circuit breaker."""

    def __init__(
        self,
        base_url: str | None = None,
        cache: ETACache | None = None,
        timeout_seconds: float = 3.0,
        max_consecutive_failures: int = 3,
        circuit_cooldown_seconds: int = 60,
    ):
        self.base_url = (base_url or get_settings().OSRM_BASE_URL).rstrip("/")
        self.cache = cache or ETACache()
        self.timeout = timeout_seconds
        self.fallback = MockRoutingProvider(cache=self.cache)
        self.max_consecutive_failures = max_consecutive_failures
        self.circuit_cooldown_seconds = circuit_cooldown_seconds
        self._consecutive_failures: int = 0
        self._circuit_open_until: datetime | None = None

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        if not self._circuit_open_until:
            return False
        now = datetime.now(timezone.utc)
        if now < self._circuit_open_until:
            return True
        # Cooldown expired, half-open
        self._circuit_open_until = None
        self._consecutive_failures = 0
        return False

    async def calculate_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> RouteResult:
        """Call OSRM /route/v1/driving; uses fallback if circuit open or request fails."""
        # Check circuit breaker or operational kill switch
        if self.is_circuit_open or get_settings().KILL_SWITCH_FORCE_ROUTING_FALLBACK:
            reason = "kill_switch_active" if get_settings().KILL_SWITCH_FORCE_ROUTING_FALLBACK else "circuit_breaker_active"
            logger.info("osrm_fallback_active", reason=reason)
            fallback_res = await self.fallback.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
            return RouteResult(
                distance_km=fallback_res.distance_km,
                duration_minutes=fallback_res.duration_minutes,
                provider_source="fallback",
                polyline=fallback_res.polyline,
            )

        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
            f"?overview=simplified&geometries=geojson"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.get(url)
                if res.status_code == 200:
                    data = res.json()
                    routes = data.get("routes", [])
                    if routes:
                        primary = routes[0]
                        distance_km = round(primary.get("distance", 0.0) / 1000.0, 2)
                        duration_mins = max(5, int(round(primary.get("duration", 0.0) / 60.0)))
                        coordinates = primary.get("geometry", {}).get("coordinates", [])
                        polyline = [(c[1], c[0]) for c in coordinates] if coordinates else None

                        # Reset circuit failure counter on success
                        self._consecutive_failures = 0
                        return RouteResult(
                            distance_km=distance_km,
                            duration_minutes=duration_mins,
                            provider_source="osrm",
                            polyline=polyline,
                        )
        except Exception as exc:
            self._consecutive_failures += 1
            logger.warning(
                "osrm_routing_request_failed",
                error=str(exc),
                consecutive_failures=self._consecutive_failures,
            )
            if self._consecutive_failures >= self.max_consecutive_failures:
                self._circuit_open_until = datetime.now(timezone.utc) + timedelta(seconds=self.circuit_cooldown_seconds)
                logger.warning("osrm_circuit_breaker_tripped", cooldown_seconds=self.circuit_cooldown_seconds)

        # Graceful fallback marked with 'fallback'
        fallback_res = await self.fallback.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
        return RouteResult(
            distance_km=fallback_res.distance_km,
            duration_minutes=fallback_res.duration_minutes,
            provider_source="fallback",
            polyline=fallback_res.polyline,
        )

    async def calculate_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> ETAResult:
        """Calculate road transit ETA using OSRM or fallback, caching the response."""
        cached = self.cache.get(origin_lat, origin_lng, dest_lat, dest_lng)
        if cached:
            return cached

        route = await self.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
        result = ETAResult(
            duration_minutes=route.duration_minutes,
            distance_km=route.distance_km,
            is_cached=False,
            provider_source=route.provider_source,
        )
        self.cache.set(origin_lat, origin_lng, dest_lat, dest_lng, result)
        return result
