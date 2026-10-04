"""
Deterministic Mock and Heuristic Routing Provider (Phase 11).

Provides offline, predictable routing and ETA calculations for tests and local development.
Uses standard urban transport heuristics:
- Road Detour Factor: 1.35x geodesic distance (accounting for street grids and detours)
- Average Urban Speed: 25 km/h
- Dispatch Overhead: 3 minutes base dispatch time
- Minimum transit time: 5 minutes
"""

import math
from app.services.routing.base import ETAResult, RouteResult, RoutingProvider
from app.services.routing.cache import ETACache


class MockRoutingProvider(RoutingProvider):
    """Deterministic routing provider using mathematical urban transport heuristics."""

    def __init__(
        self,
        average_speed_kmh: float = 25.0,
        detour_factor: float = 1.35,
        cache: ETACache | None = None,
    ):
        self.average_speed_kmh = average_speed_kmh
        self.detour_factor = detour_factor
        self.cache = cache or ETACache()

    @staticmethod
    def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate great-circle distance between two points in km."""
        r = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r * c, 2)

    async def calculate_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> RouteResult:
        """Compute synthetic route polyline, distance, and duration."""
        geodesic_km = self.haversine_km(origin_lat, origin_lng, dest_lat, dest_lng)
        road_km = round(max(0.1, geodesic_km * self.detour_factor), 2)

        # Base 3 mins overhead + transit time at average speed
        transit_hours = road_km / self.average_speed_kmh
        duration_mins = max(5, int(round(transit_hours * 60 + 3)))

        # Simple synthetic 3-point polyline: origin, midpoint with jitter, destination
        mid_lat = (origin_lat + dest_lat) / 2 + 0.002
        mid_lng = (origin_lng + dest_lng) / 2 - 0.002
        polyline = [
            (origin_lat, origin_lng),
            (mid_lat, mid_lng),
            (dest_lat, dest_lng),
        ]

        return RouteResult(
            distance_km=road_km,
            duration_minutes=duration_mins,
            provider_source="mock_heuristic",
            polyline=polyline,
        )

    async def calculate_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> ETAResult:
        """Compute or retrieve cached ETA."""
        cached = self.cache.get(origin_lat, origin_lng, dest_lat, dest_lng)
        if cached:
            return cached

        route = await self.calculate_route(origin_lat, origin_lng, dest_lat, dest_lng)
        result = ETAResult(
            duration_minutes=route.duration_minutes,
            distance_km=route.distance_km,
            is_cached=False,
            provider_source="mock_heuristic",
        )
        self.cache.set(origin_lat, origin_lng, dest_lat, dest_lng, result)
        return result
