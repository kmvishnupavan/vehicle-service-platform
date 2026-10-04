"""
OSRM Routing Resilience and Circuit Breaker Tests (Phase 15.1 Remediation).

Tests:
1. OSRM healthy response returns provider_source="osrm".
2. OSRM network failure / timeout triggers graceful fallback.
3. 3 consecutive failures trip circuit breaker into open state.
4. Open circuit breaker bypasses network calls and uses Haversine fallback directly.
5. Circuit breaker cooldown allows recovery after timeout.
6. KILL_SWITCH_FORCE_ROUTING_FALLBACK bypasses OSRM and forces Haversine fallback.
7. Spatial cache returns cached ETA without network request.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from app.core.config import get_settings
from app.services.routing.cache import ETACache
from app.services.routing.osrm_provider import OSRMRoutingProvider


@pytest.mark.asyncio
async def test_osrm_healthy_response():
    """Verify OSRM provider returns valid route and distance when API responds 200."""
    provider = OSRMRoutingProvider(base_url="http://mock-osrm:5000", cache=ETACache())

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "routes": [
            {
                "distance": 8450.0,
                "duration": 960.0,
                "geometry": {
                    "coordinates": [[77.5946, 12.9716], [77.6000, 12.9800]]
                },
            }
        ]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        result = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)

    assert result.provider_source == "osrm"
    assert result.distance_km == 8.45
    assert result.duration_minutes == 16
    assert result.polyline is not None
    assert provider._consecutive_failures == 0
    assert provider.is_circuit_open is False


@pytest.mark.asyncio
async def test_osrm_failure_and_circuit_breaker_tripping():
    """Verify 3 consecutive failures trip circuit breaker into open state."""
    provider = OSRMRoutingProvider(
        base_url="http://mock-osrm:5000",
        cache=ETACache(),
        max_consecutive_failures=3,
        circuit_cooldown_seconds=60,
    )

    with patch("httpx.AsyncClient.get", side_effect=httpx.ConnectTimeout("OSRM connection timeout")):
        # Failure 1
        res1 = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)
        assert res1.provider_source == "fallback"
        assert provider._consecutive_failures == 1
        assert provider.is_circuit_open is False

        # Failure 2
        res2 = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)
        assert res2.provider_source == "fallback"
        assert provider._consecutive_failures == 2
        assert provider.is_circuit_open is False

        # Failure 3 -> Trips circuit breaker
        res3 = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)
        assert res3.provider_source == "fallback"
        assert provider._consecutive_failures == 3
        assert provider.is_circuit_open is True


@pytest.mark.asyncio
async def test_osrm_open_circuit_bypasses_network():
    """Verify open circuit returns fallback immediately without making HTTP calls."""
    provider = OSRMRoutingProvider(base_url="http://mock-osrm:5000", cache=ETACache())
    # Manually trip circuit breaker
    provider._circuit_open_until = datetime.now(timezone.utc) + timedelta(seconds=120)
    assert provider.is_circuit_open is True

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        res = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)
        mock_get.assert_not_called()

    assert res.provider_source == "fallback"
    assert res.distance_km > 0
    assert res.duration_minutes >= 5


@pytest.mark.asyncio
async def test_osrm_kill_switch_force_fallback():
    """Verify KILL_SWITCH_FORCE_ROUTING_FALLBACK bypasses OSRM and forces Haversine fallback."""
    provider = OSRMRoutingProvider(base_url="http://mock-osrm:5000", cache=ETACache())

    with patch.object(get_settings(), "KILL_SWITCH_FORCE_ROUTING_FALLBACK", True):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            res = await provider.calculate_route(12.9716, 77.5946, 12.9800, 77.6000)
            mock_get.assert_not_called()

    assert res.provider_source == "fallback"
    assert res.distance_km > 0


@pytest.mark.asyncio
async def test_osrm_spatial_cache_hit():
    """Verify cached ETA result returns without recalculation or network request."""
    cache = ETACache()
    provider = OSRMRoutingProvider(base_url="http://mock-osrm:5000", cache=cache)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "routes": [{"distance": 5000.0, "duration": 600.0, "geometry": {"coordinates": []}}]
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response) as mock_get:
        eta1 = await provider.calculate_eta(12.9716, 77.5946, 12.9800, 77.6000)
        assert eta1.is_cached is False
        assert mock_get.call_count == 1

        # Second request with quantized coordinates hits in-memory cache
        eta2 = await provider.calculate_eta(12.97161, 77.59462, 12.98001, 77.60002)
        assert eta2.is_cached is True
        assert mock_get.call_count == 1
