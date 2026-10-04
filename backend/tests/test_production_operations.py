"""
Tests for Phase 9: Production Hardening, Observability, Admin Operations & Disaster Recovery.
Validates:
- Request ID generation & propagation (X-Request-ID)
- Health and Readiness probes (/health/live, /health/ready, /health/database)
- Production Safety Guard (blocking accidental live payouts)
- Reconciliation Service (detecting payment, payout, settlement, webhook anomalies)
- Rate Limiting and Security Headers
- Standardized Error Envelope
- Admin Operations & Reconciliation API Authorization
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.safety import ProductionSafetyGuard
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.reconciliation_service import ReconciliationService


ADMIN_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
CUSTOMER_ID = uuid.UUID("cccccccc-1111-0000-0000-000000000001")
MECHANIC_ID = uuid.UUID("bbbbbbbb-1111-0000-0000-000000000001")


@pytest.fixture
def mock_admin():
    """Fixture providing an authenticated admin."""
    user = AuthenticatedUser(
        id=ADMIN_ID,
        email="admin@vehiclecare.test",
        role=UserRole.ADMIN,
        profile=UserProfileResponse(
            id=ADMIN_ID,
            full_name="Operations Admin",
            phone="+919876543999",
            email="admin@vehiclecare.test",
            avatar_url=None,
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def mock_customer():
    """Fixture providing an authenticated customer."""
    user = AuthenticatedUser(
        id=CUSTOMER_ID,
        email="customer@vehiclecare.test",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_ID,
            full_name="Alice Customer",
            phone="+919876543111",
            email="customer@vehiclecare.test",
            avatar_url=None,
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# 1. Request ID Generation & Propagation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_request_id_generated_when_missing(async_client: AsyncClient):
    """Verify that every response includes a valid generated X-Request-ID."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    req_id = response.headers["x-request-id"]
    assert req_id.startswith("req_")
    assert len(req_id) >= 12


@pytest.mark.asyncio
async def test_request_id_accepted_when_valid(async_client: AsyncClient):
    """Verify that a valid incoming X-Request-ID is retained and echoed back."""
    custom_id = "trace-test-uuid-9988776655"
    response = await async_client.get("/health/live", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_id


@pytest.mark.asyncio
async def test_request_id_regenerated_when_invalid(async_client: AsyncClient):
    """Verify that invalid/malicious request IDs are safely replaced."""
    malicious_id = "invalid;DROP TABLE users;--"
    response = await async_client.get("/health/live", headers={"X-Request-ID": malicious_id})
    assert response.status_code == 200
    assert response.headers["x-request-id"] != malicious_id
    assert response.headers["x-request-id"].startswith("req_")


# ---------------------------------------------------------------------------
# 2. Health & Readiness Probes Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_liveness_probe(async_client: AsyncClient):
    """GET /health/live returns HTTP 200 and status ok."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_success(async_client: AsyncClient):
    """GET /health/ready returns HTTP 200 and system checks when healthy."""
    from app.services.health_service import HealthService

    mock_ready = {
        "status": "ready",
        "environment": "testing",
        "checks": {
            "database": "connected",
            "schema": "verified",
            "configuration": "valid",
            "payout_safety": "sandbox_enforced",
            "notifications": "operational",
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with patch.object(HealthService, "get_readiness", return_value=mock_ready):
        response = await async_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["ready", "degraded", "not_ready"]
        assert "checks" in data
        assert "environment" in data
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_probe_failure_simulation(async_client: AsyncClient):
    """GET /health/ready returns HTTP 503 when a critical check is unhealthy."""
    from app.services.health_service import HealthService

    mock_readiness = {
        "status": "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": "testing",
        "checks": {
            "database": {"status": "unhealthy", "error": "Connection refused"},
            "schema": {"status": "unhealthy"},
            "configuration": {"status": "healthy"},
            "payout_safety": {"status": "healthy", "mode": "sandbox", "live_payouts_blocked": True},
            "notifications": {"status": "healthy"},
        },
    }

    with patch.object(HealthService, "get_readiness", return_value=mock_readiness):
        response = await async_client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "not_ready"
        assert data["checks"]["database"]["status"] == "unhealthy"


# ---------------------------------------------------------------------------
# 3. Production Safety Guard Tests
# ---------------------------------------------------------------------------

def test_safety_guard_blocks_when_live_payouts_disabled():
    """Verify that ProductionSafetyGuard blocks if LIVE_PAYOUTS_ENABLED is False."""
    settings = Settings(
        ENVIRONMENT="production",
        LIVE_PAYOUTS_ENABLED=False,
        RAZORPAY_KEY_ID="rzp_live_test",
        RAZORPAY_KEY_SECRET="secret",
    )
    with pytest.raises(HTTPException) as exc_info:
        ProductionSafetyGuard.assert_live_payout_permitted(settings, provider_mode="live")
    assert exc_info.value.status_code == 403
    assert "LIVE_PAYOUTS_ENABLED is False" in exc_info.value.detail


def test_safety_guard_blocks_when_environment_not_production():
    """Verify that ProductionSafetyGuard blocks if environment is not production."""
    settings = Settings(
        ENVIRONMENT="development",
        LIVE_PAYOUTS_ENABLED=True,
        RAZORPAY_KEY_ID="rzp_live_test",
        RAZORPAY_KEY_SECRET="secret",
    )
    with pytest.raises(HTTPException) as exc_info:
        ProductionSafetyGuard.assert_live_payout_permitted(settings, provider_mode="live")
    assert exc_info.value.status_code == 403
    assert "ENVIRONMENT is not production" in exc_info.value.detail


def test_safety_guard_blocks_when_provider_mode_not_live():
    """Verify that ProductionSafetyGuard blocks if provider mode is not live."""
    settings = Settings(
        ENVIRONMENT="production",
        LIVE_PAYOUTS_ENABLED=True,
        RAZORPAY_KEY_ID="rzp_live_test",
        RAZORPAY_KEY_SECRET="secret",
    )
    with pytest.raises(HTTPException) as exc_info:
        ProductionSafetyGuard.assert_live_payout_permitted(settings, provider_mode="sandbox")
    assert exc_info.value.status_code == 403
    assert "Provider mode is not live" in exc_info.value.detail


def test_safety_guard_permits_only_when_all_four_conditions_met():
    """Verify that ProductionSafetyGuard permits live payouts ONLY when all 4 conditions are met."""
    settings = Settings(
        ENVIRONMENT="production",
        LIVE_PAYOUTS_ENABLED=True,
        RAZORPAY_KEY_ID="rzp_live_test",
        RAZORPAY_KEY_SECRET="secret",
    )
    # Should not raise exception
    assert ProductionSafetyGuard.assert_live_payout_permitted(settings, provider_mode="live") is True


# ---------------------------------------------------------------------------
# 4. Reconciliation Engine Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reconciliation_detects_stuck_pending_payment():
    """Verify ReconciliationService detects payments stuck in pending longer than SLA."""
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=45)).isoformat()
    mock_payments = [
        {
            "id": "pay_111",
            "razorpay_order_id": "order_111",
            "status": "pending",
            "created_at": old_time,
            "booking_id": "b_1",
            "amount": 2500,
        }
    ]

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.execute.return_value.data = mock_payments

    service = ReconciliationService(db=mock_db)
    discrepancies = await service.reconcile_payments(persist=False)

    assert len(discrepancies) == 1
    assert discrepancies[0]["discrepancy_type"] == "PAYMENT_PENDING_TOO_LONG"
    assert discrepancies[0]["internal_id"] == "pay_111"
    assert discrepancies[0]["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_reconciliation_detects_stuck_payout():
    """Verify ReconciliationService detects payouts stuck in processing longer than SLA."""
    old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    mock_payouts = [
        {
            "id": "payout_222",
            "payout_provider_reference": "pout_mock_999",
            "status": "processing",
            "created_at": old_time,
            "mechanic_id": "m_1",
            "amount": 3500,
            "batch_id": "batch_1",
        }
    ]

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.execute.return_value.data = mock_payouts

    service = ReconciliationService(db=mock_db)
    discrepancies = await service.reconcile_payouts(persist=False)

    assert len(discrepancies) == 1
    assert discrepancies[0]["discrepancy_type"] == "STUCK_PAYOUT_PROCESSING"
    assert discrepancies[0]["internal_id"] == "payout_222"
    assert discrepancies[0]["severity"] == "HIGH"


@pytest.mark.asyncio
async def test_reconciliation_detects_stuck_webhook():
    """Verify ReconciliationService detects webhook reservations stuck in processing."""
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    mock_webhooks = [
        {
            "id": "wh_333",
            "event_id": "evt_abc123",
            "status": "processing",
            "processing_started_at": old_time,
            "processing_attempts": 2,
            "event_type": "payment.captured",
        }
    ]

    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.execute.return_value.data = mock_webhooks

    service = ReconciliationService(db=mock_db)
    discrepancies = await service.reconcile_webhooks(persist=False)

    assert len(discrepancies) == 1
    assert discrepancies[0]["discrepancy_type"] == "STUCK_WEBHOOK_RESERVATION"
    assert discrepancies[0]["internal_id"] == "wh_333"


# ---------------------------------------------------------------------------
# 5. Rate Limiting & Security Headers Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_security_headers_present(async_client: AsyncClient):
    """Verify production security headers are attached to responses."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "strict-origin-when-cross-origin" in response.headers["Referrer-Policy"]


@pytest.mark.asyncio
async def test_rate_limit_headers_present(async_client: AsyncClient):
    """Verify rate limit headers are present on API responses."""
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    assert "X-RateLimit-Limit" in response.headers
    assert "X-RateLimit-Remaining" in response.headers
    assert "X-RateLimit-Reset" in response.headers


# ---------------------------------------------------------------------------
# 6. Standardized Error Format Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_standardized_error_format_404(async_client: AsyncClient):
    """Verify 404 response uses the standardized error envelope."""
    response = await async_client.get("/api/v1/non-existent-endpoint-xyz")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert "code" in data["error"]
    assert "message" in data["error"]
    assert "request_id" in data["error"]
    assert data["error"]["code"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 7. Admin Operations & Reconciliation Authorization Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_operations_stats_allowed_for_admin(async_client: AsyncClient, mock_admin):
    """Admin user can access /api/v1/admin/operations/stats."""
    with patch("app.api.admin_operations.get_admin_db") as mock_db_getter:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.execute.return_value.data = []
        mock_db_getter.return_value = mock_db

        response = await async_client.get("/api/v1/admin/operations/stats")
        assert response.status_code == 200
        data = response.json()
        assert "bookings" in data
        assert "payments" in data
        assert "payouts" in data
        assert "webhooks" in data


@pytest.mark.asyncio
async def test_admin_reconciliation_forbidden_for_customer(async_client: AsyncClient, mock_customer):
    """Customer user receives HTTP 403 when accessing admin reconciliation endpoints."""
    response = await async_client.get("/api/v1/admin/reconciliation/payments")
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_admin_reconciliation_unauthorized_when_not_logged_in(async_client: AsyncClient):
    """Unauthenticated request receives HTTP 401 when accessing admin operations."""
    response = await async_client.get("/api/v1/admin/reconciliation/payments")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
