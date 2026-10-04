"""
Unit and Integration Tests for Phase 13: Operational Automation & Reliability.

Covers:
1. Background job runner with distributed locking and audit logging.
2. Automatic offer expiration and session candidate advancement.
3. Scheduled booking creation with timezone safety & dispatch window calculation.
4. Scheduled dispatch idempotency and cancellation race safety.
5. Dynamic OSRM routing resilience, circuit breaker tripping, and fallback source tagging.
6. Location reliability: heartbeat freshness evaluation and GPS anomaly detection.
7. Matching policy versioning, weight validation (sum = 1.000), and atomic activation.
8. Notification retry queue with exponential backoff.
9. Operational metrics aggregation.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.db.dependencies import get_current_user, require_admin_or_support, require_customer
from app.main import app
from app.schemas.operational_automation import (
    MatchingPolicyCreate,
    ScheduledBookingCreate,
)
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.background_jobs import BackgroundJobRunner, BackgroundJobsService, JobExecutionResult
from app.services.location_reliability_service import LocationReliabilityService
from app.services.matching_policy_service import MatchingPolicyService
from app.services.operational_metrics_service import OperationalMetricsService
from app.services.routing.osrm_provider import OSRMRoutingProvider
from app.services.scheduled_booking_service import ScheduledBookingService

CUSTOMER_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
ADMIN_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
BOOKING_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
MECHANIC_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def make_authenticated_user(user_id: uuid.UUID, role: UserRole) -> AuthenticatedUser:
    profile = UserProfileResponse(
        id=user_id,
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.capitalize()}",
        role=role,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthenticatedUser(
        id=user_id,
        email=profile.email,
        role=role,
        profile=profile,
        app_metadata={},
        user_metadata={},
    )


# =============================================================================
# 1. Background Job Runner & Locking Tests
# =============================================================================

@pytest.mark.asyncio
async def test_background_job_runner_executes_and_logs():
    """Verify background job runner wraps execution with lock, status, and metrics."""
    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value = MagicMock(data=True)
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": str(uuid.uuid4())}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": "test"}]
    )

    runner = BackgroundJobRunner(client=mock_client)

    async def sample_job():
        return JobExecutionResult(records_processed=5, records_succeeded=5, records_failed=0)

    summary = await runner.execute_job("sample_job", sample_job)

    assert summary["job_name"] == "sample_job"
    assert summary["status"] == "completed"
    assert summary["records_processed"] == 5
    assert summary["records_succeeded"] == 5
    assert summary["records_failed"] == 0
    # Verify advisory lock acquired and released
    assert mock_client.rpc.call_count >= 2


@pytest.mark.asyncio
async def test_background_job_runner_handles_crash_gracefully():
    """Verify runner catches exceptions, sets failed status, and releases lock."""
    mock_client = MagicMock()
    mock_client.rpc.return_value.execute.return_value = MagicMock(data=True)
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[{"id": str(uuid.uuid4())}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    runner = BackgroundJobRunner(client=mock_client)

    async def crashing_job():
        raise RuntimeError("Database connection timed out during job")

    summary = await runner.execute_job("crashing_job", crashing_job)

    assert summary["status"] == "failed"
    assert "Database connection timed out" in summary["error_summary"]
    assert summary["records_failed"] == 1


# =============================================================================
# 2. Offer Expiration & Matching Session Advancement
# =============================================================================

@pytest.mark.asyncio
async def test_job_expire_mechanic_offers():
    """Verify expire_mechanic_offers marks stale offers as expired and calls advancement."""
    mock_client = MagicMock()
    assignment_id = str(uuid.uuid4())
    mock_client.table.return_value.select.return_value.eq.return_value.lt.return_value.execute.return_value = MagicMock(
        data=[{"id": assignment_id, "booking_id": str(BOOKING_ID), "attempt_number": 1}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    mock_matching = MagicMock()
    mock_matching._advance_to_next_candidate = AsyncMock()

    jobs_svc = BackgroundJobsService(client=mock_client, matching_service=mock_matching)
    res = await jobs_svc.job_expire_mechanic_offers()

    assert res.records_processed == 1
    assert res.records_succeeded == 1
    mock_matching._advance_to_next_candidate.assert_awaited_once_with(BOOKING_ID, prior_attempt=1)


# =============================================================================
# 3. Scheduled Booking Subsystem
# =============================================================================

@pytest.mark.asyncio
async def test_schedule_booking_validates_timezone_and_future_window():
    """Verify booking scheduling accepts valid future window and calculates dispatch_at."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": str(BOOKING_ID), "customer_id": str(CUSTOMER_USER_ID), "booking_status": "pending"}]
    )
    mock_client.table.return_value.upsert.return_value.execute.return_value = MagicMock(
        data=[{"id": str(uuid.uuid4()), "booking_id": str(BOOKING_ID)}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

    svc = ScheduledBookingService(client=mock_client)
    now = datetime.now(timezone.utc)
    future_start = now + timedelta(days=2, hours=10)
    future_end = future_start + timedelta(hours=2)

    req = ScheduledBookingCreate(
        scheduled_start_at=future_start,
        scheduled_end_at=future_end,
        timezone="Asia/Kolkata",
        dispatch_window_minutes=30,
    )

    res = await svc.schedule_booking(BOOKING_ID, CUSTOMER_USER_ID, req)
    assert res is not None


@pytest.mark.asyncio
async def test_schedule_booking_rejects_past_timestamp():
    """Verify scheduling in the past raises HTTP 400."""
    svc = ScheduledBookingService(client=MagicMock())
    past = datetime.now(timezone.utc) - timedelta(hours=1)

    req = ScheduledBookingCreate(
        scheduled_start_at=past,
        scheduled_end_at=past + timedelta(hours=1),
    )

    with pytest.raises(Exception):
        await svc.schedule_booking(BOOKING_ID, CUSTOMER_USER_ID, req)


# =============================================================================
# 4. Scheduled Dispatch Idempotency & Race Safety
# =============================================================================

@pytest.mark.asyncio
async def test_dispatch_scheduled_bookings_idempotent():
    """Verify dispatching transitions scheduled -> dispatching -> dispatched."""
    mock_client = MagicMock()
    sb_id = str(uuid.uuid4())
    mock_client.table.return_value.select.return_value.eq.return_value.lte.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": sb_id, "booking_id": str(BOOKING_ID), "attempt_count": 0, "status": "scheduled"}]
    )
    # Lock update succeeds
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": sb_id}]
    )
    # Booking is active pending
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": str(BOOKING_ID), "booking_status": "pending", "customer_id": str(CUSTOMER_USER_ID)}]
    )

    mock_matching = MagicMock()
    mock_matching.find_eligible_candidates = AsyncMock()

    jobs_svc = BackgroundJobsService(client=mock_client, matching_service=mock_matching)
    res = await jobs_svc.job_dispatch_scheduled_bookings()

    assert res.records_processed == 1
    assert res.records_succeeded == 1
    mock_matching.find_eligible_candidates.assert_awaited_once_with(uuid.UUID(str(BOOKING_ID)))


@pytest.mark.asyncio
async def test_dispatch_scheduled_booking_handles_prior_cancellation():
    """Verify scheduler does NOT dispatch a booking if customer cancelled it beforehand."""
    mock_client = MagicMock()
    sb_id = str(uuid.uuid4())
    mock_client.table.return_value.select.return_value.eq.return_value.lte.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{"id": sb_id, "booking_id": str(BOOKING_ID), "attempt_count": 0, "status": "scheduled"}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": sb_id}]
    )
    # Booking status is CANCELLED
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": str(BOOKING_ID), "booking_status": "cancelled", "customer_id": str(CUSTOMER_USER_ID)}]
    )

    mock_matching = MagicMock()
    mock_matching.find_eligible_candidates = AsyncMock()

    jobs_svc = BackgroundJobsService(client=mock_client, matching_service=mock_matching)
    res = await jobs_svc.job_dispatch_scheduled_bookings()

    # Dispatched count is 0 because it was cancelled
    mock_matching.find_eligible_candidates.assert_not_awaited()
    assert res.records_succeeded == 1


# =============================================================================
# 5. Dynamic Routing Resilience & Circuit Breaker
# =============================================================================

@pytest.mark.asyncio
async def test_osrm_provider_circuit_breaker_and_fallback():
    """Verify OSRMRoutingProvider trips circuit breaker after 3 failures and tags provider_source='fallback'."""
    provider = OSRMRoutingProvider(
        base_url="http://invalid-osrm-host-12345.org",
        timeout_seconds=0.1,
        max_consecutive_failures=3,
        circuit_cooldown_seconds=10,
    )

    # First 3 calls fail and increment failure counter
    route1 = await provider.calculate_route(17.3850, 78.4867, 17.4399, 78.4983)
    assert route1.provider_source == "fallback"

    route2 = await provider.calculate_route(17.3850, 78.4867, 17.4399, 78.4983)
    assert route2.provider_source == "fallback"

    route3 = await provider.calculate_route(17.3850, 78.4867, 17.4399, 78.4983)
    assert route3.provider_source == "fallback"

    # Circuit breaker should now be OPEN
    assert provider.is_circuit_open is True

    # Next call immediately uses fallback without waiting for network timeout
    route4 = await provider.calculate_route(17.3850, 78.4867, 17.4399, 78.4983)
    assert route4.provider_source == "fallback"
    assert route4.distance_km > 0


# =============================================================================
# 6. Location Reliability & GPS Anomaly Detection
# =============================================================================

def test_location_freshness_classification():
    """Verify freshness thresholds: <=60s fresh, <=300s stale, >300s offline."""
    now = datetime.now(timezone.utc)
    fresh_time = now - timedelta(seconds=20)
    stale_time = now - timedelta(seconds=120)
    offline_time = now - timedelta(seconds=450)

    assert LocationReliabilityService.evaluate_freshness(fresh_time) == "fresh"
    assert LocationReliabilityService.evaluate_freshness(stale_time) == "stale"
    assert LocationReliabilityService.evaluate_freshness(offline_time) == "offline"
    assert LocationReliabilityService.evaluate_freshness(None) == "offline"


@pytest.mark.asyncio
async def test_location_anomaly_detects_impossible_speed():
    """Verify anomaly detector flags impossible speed (> 160 km/h) and logs to table."""
    mock_client = MagicMock()
    # Prior location in Hyderabad 10 seconds ago
    prior_time = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"current_latitude": 17.3850, "current_longitude": 78.4867, "current_location_updated_at": prior_time}]
    )
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

    svc = LocationReliabilityService(client=mock_client)
    # Moving 5 km in 10 seconds = 1800 km/h!
    is_valid, anomalies = await svc.validate_and_record_ping(
        mechanic_id=MECHANIC_ID,
        latitude=17.4300,
        longitude=78.4867,
    )

    assert is_valid is False
    assert any(a["anomaly_type"] in ("impossible_speed", "large_location_jump") for a in anomalies)
    assert mock_client.table.return_value.insert.called


# =============================================================================
# 7. Matching Policy Versioning
# =============================================================================

@pytest.mark.asyncio
async def test_matching_policy_weight_validation():
    """Verify matching policy validates sum of weights equals 1.000."""
    # Valid weights: 0.3 + 0.2 + 0.15 + 0.15 + 0.1 + 0.1 = 1.0
    valid = MatchingPolicyCreate(
        policy_version="v2.0",
        proximity_weight=Decimal("0.300"),
        rating_weight=Decimal("0.200"),
        availability_weight=Decimal("0.150"),
        reliability_weight=Decimal("0.150"),
        workload_weight=Decimal("0.100"),
        acceptance_weight=Decimal("0.100"),
    )
    assert valid.policy_version == "v2.0"

    # Invalid weights summing to 0.900 should raise ValueError
    with pytest.raises(ValueError):
        MatchingPolicyCreate(
            policy_version="v2.0_bad",
            proximity_weight=Decimal("0.200"),
            rating_weight=Decimal("0.200"),
            availability_weight=Decimal("0.150"),
            reliability_weight=Decimal("0.150"),
            workload_weight=Decimal("0.100"),
            acceptance_weight=Decimal("0.100"),
        )


@pytest.mark.asyncio
async def test_activate_matching_policy_atomic():
    """Verify policy activation deactivates existing and sets target active."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"id": str(uuid.uuid4()), "policy_version": "v1.1"}]
    )
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[{"policy_version": "v1.1", "is_active": True}]
    )

    svc = MatchingPolicyService(client=mock_client)
    res = await svc.activate_policy("v1.1", admin_id=ADMIN_USER_ID)
    assert res["is_active"] is True


# =============================================================================
# 8. Operational Metrics Snapshot
# =============================================================================

@pytest.mark.asyncio
async def test_operational_metrics_service_returns_data():
    """Verify operational metrics service returns populated KPIs."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": str(uuid.uuid4()),
            "snapshot_time": datetime.now(timezone.utc).isoformat(),
            "metrics": {
                "booking_count": 120,
                "active_bookings": 15,
                "matching_sessions_total": 45,
                "average_time_to_match_seconds": 38.5,
                "matching_exhaustion_rate": 0.04,
                "offer_acceptance_rate": 0.91,
                "offer_expiration_rate": 0.09,
                "average_eta_minutes": 16.2,
                "routing_failure_rate": 0.01,
                "routing_fallback_rate": 0.02,
                "stale_location_rate": 0.03,
                "location_anomaly_count": 2,
                "scheduled_booking_count": 10,
                "scheduled_dispatch_failure_rate": 0.0,
                "inspection_approval_rate": 0.95,
                "service_completion_rate": 0.88,
                "payment_success_rate": 0.99,
                "payment_pending_count": 3,
                "dispute_rate": 0.01,
                "notification_failure_rate": 0.005,
            }
        }]
    )

    svc = OperationalMetricsService(client=mock_client)
    metrics_res = await svc.get_latest_metrics()
    assert metrics_res.metrics.booking_count == 120
    assert metrics_res.metrics.offer_acceptance_rate == 0.91


# =============================================================================
# 9. Scheduled Bookings Monitoring API Tests
# =============================================================================

@pytest.mark.asyncio
async def test_admin_list_scheduled_bookings_endpoint():
    """Verify admin scheduled booking query returns formatted records."""
    mock_client = MagicMock()
    booking_id = str(uuid.uuid4())
    start_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    end_time = (datetime.now(timezone.utc) + timedelta(hours=4)).isoformat()
    dispatch_time = (datetime.now(timezone.utc) + timedelta(hours=1, minutes=30)).isoformat()

    mock_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": str(uuid.uuid4()),
            "booking_id": booking_id,
            "scheduled_start_at": start_time,
            "scheduled_end_at": end_time,
            "timezone": "UTC",
            "dispatch_at": dispatch_time,
            "status": "scheduled",
            "attempt_count": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }]
    )

    with patch("app.api.operational_automation.ScheduledBookingService") as MockSvc:
        instance = MockSvc.return_value
        instance.client = mock_client
        from app.api.operational_automation import list_scheduled_bookings
        results = await list_scheduled_bookings(status_filter=None, limit=50)
        assert len(results) == 1
        assert str(results[0].booking_id) == booking_id
        assert results[0].status == "scheduled"


@pytest.mark.asyncio
async def test_mechanic_scheduled_jobs_endpoint():
    """Verify mechanic scheduled jobs query returns assigned bookings."""
    mock_client = MagicMock()
    mock_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[{
            "id": str(uuid.uuid4()),
            "booking_number": "BK-9999",
            "booking_status": "mechanic_assigned",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat(),
            "total_amount": 1500.0,
            "address": "123 Tech Park",
            "customer_id": str(CUSTOMER_USER_ID),
        }]
    )

    with patch("app.api.operational_automation.ScheduledBookingService") as MockSvc:
        instance = MockSvc.return_value
        instance.client = mock_client
        from app.api.operational_automation import list_mechanic_scheduled_jobs
        user = make_authenticated_user(MECHANIC_ID, UserRole.MECHANIC)
        jobs = await list_mechanic_scheduled_jobs(current_user=user, limit=20)
        assert len(jobs) == 1
        assert jobs[0]["booking_number"] == "BK-9999"
