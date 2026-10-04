"""
Routing and Road ETA Provider Abstraction (Phase 11).

Separates straight-line PostGIS geodesic distance from road network routing and ETA calculations.
Enables pluggable routing providers (Mock, OSRM, Google Maps, Mapbox) with standard contracts.
"""

from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class RouteResult(BaseModel):
    """Result of a road routing calculation."""
    distance_km: float = Field(..., description="Estimated road distance in kilometers")
    duration_minutes: int = Field(..., description="Estimated travel duration in minutes")
    provider_source: str = Field(..., description="Provider name (e.g., 'osrm', 'mock', 'heuristic')")
    polyline: list[tuple[float, float]] | None = Field(None, description="Optional list of [lat, lng] coordinates")


class ETAResult(BaseModel):
    """Result of an estimated time of arrival calculation."""
    duration_minutes: int = Field(..., description="Travel time in minutes")
    distance_km: float = Field(..., description="Road distance in kilometers")
    is_cached: bool = Field(False, description="Whether the result was served from cache")
    provider_source: str = Field(..., description="Originating provider")


class RoutingProvider(ABC):
    """Abstract interface for road network routing and travel time estimation."""

    @abstractmethod
    async def calculate_route(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> RouteResult:
        """Calculate road network distance, travel duration, and optional path."""
        pass

    @abstractmethod
    async def calculate_eta(
        self,
        origin_lat: float,
        origin_lng: float,
        dest_lat: float,
        dest_lng: float,
    ) -> ETAResult:
        """Calculate estimated travel duration in minutes and road distance."""
        pass
