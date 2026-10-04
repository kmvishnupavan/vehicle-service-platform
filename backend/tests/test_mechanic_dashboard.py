"""
Unit and Integration Tests for Mechanic Performance, Earnings & Dashboard (Phase 8.6).

Covers all 28 mandatory test specifications:
1. unauthenticated request -> 401
2. customer calling dashboard -> 403
3. mechanic can read own dashboard
4. mechanic cannot read another mechanic's dashboard
5. overview values use database data
6. completed jobs calculation
7. cancelled jobs calculation
8. active jobs calculation
9. completion rate
10. zero denominator
11. rating average
12. rating distribution
13. review count
14. earnings calculation
15. additional work included correctly
16. failed payment handling
17. refunded payment handling
18. date filtering
19. pagination
20. limit bounds
21. invalid dates
22. recent jobs ownership
23. recent reviews ownership
24. no customer PII leakage
25. Decimal monetary precision
26. empty dashboard
27. admin/support access if supported
28. concurrent-safe read behavior where relevant
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole

# Test UUIDs
MECH_1_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MECH_1_PROFILE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

MECH_2_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
MECH_2_PROFILE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")

CUSTOMER_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ADMIN_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def build_dashboard_mock_db():
    """Stateful mock database for mechanic dashboard testing."""
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    bookings = {
        # Mech 1 bookings
        "b1": {
            "id": "b1",
            "booking_number": "BK-M1-001",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "paid",
            "payment_status": "paid",
            "subtotal": 1200.50,
            "additional_charges": 300.25,
            "discount_amount": 50.0,
            "tax_amount": 270.0,
            "total_amount": 1720.75,
            "scheduled_at": f"{today_str}T10:00:00Z",
            "created_at": f"{today_str}T08:00:00Z",
            "updated_at": f"{today_str}T11:00:00Z",
        },
        "b2": {
            "id": "b2",
            "booking_number": "BK-M1-002",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "pending",
            "subtotal": 800.00,
            "additional_charges": 0.00,
            "discount_amount": 0.0,
            "tax_amount": 144.0,
            "total_amount": 944.00,
            "scheduled_at": f"{today_str}T12:00:00Z",
            "created_at": f"{today_str}T09:00:00Z",
            "updated_at": f"{today_str}T13:00:00Z",
        },
        "b3": {
            "id": "b3",
            "booking_number": "BK-M1-003",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_in_progress",
            "payment_status": "unpaid",
            "subtotal": 500.00,
            "additional_charges": 0.00,
            "discount_amount": 0.0,
            "tax_amount": 90.0,
            "total_amount": 590.00,
            "scheduled_at": f"{today_str}T14:00:00Z",
            "created_at": f"{today_str}T13:30:00Z",
            "updated_at": f"{today_str}T14:00:00Z",
        },
        "b4": {
            "id": "b4",
            "booking_number": "BK-M1-004",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "cancelled",
            "payment_status": "unpaid",
            "subtotal": 600.00,
            "additional_charges": 0.00,
            "discount_amount": 0.0,
            "tax_amount": 108.0,
            "total_amount": 708.00,
            "scheduled_at": f"{today_str}T16:00:00Z",
            "created_at": f"{today_str}T15:00:00Z",
            "updated_at": f"{today_str}T15:30:00Z",
        },
        "b5_failed": {
            "id": "b5_failed",
            "booking_number": "BK-M1-005-FAIL",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "failed",
            "subtotal": 1000.00,
            "additional_charges": 0.00,
            "discount_amount": 0.0,
            "tax_amount": 180.0,
            "total_amount": 1180.00,
            "scheduled_at": "2026-09-15T10:00:00Z",
            "created_at": "2026-09-15T08:00:00Z",
            "updated_at": "2026-09-15T11:00:00Z",
        },
        "b6_refunded": {
            "id": "b6_refunded",
            "booking_number": "BK-M1-006-REF",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "refunded",
            "subtotal": 1500.00,
            "additional_charges": 200.00,
            "discount_amount": 0.0,
            "tax_amount": 306.0,
            "total_amount": 2006.00,
            "scheduled_at": "2026-09-20T10:00:00Z",
            "created_at": "2026-09-20T08:00:00Z",
            "updated_at": "2026-09-20T11:00:00Z",
        },
        # Mech 2 booking
        "b_mech2": {
            "id": "b_mech2",
            "booking_number": "BK-M2-001",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "paid",
            "payment_status": "paid",
            "subtotal": 999.00,
            "additional_charges": 0.00,
            "discount_amount": 0.0,
            "tax_amount": 179.82,
            "total_amount": 1178.82,
            "scheduled_at": f"{today_str}T11:00:00Z",
            "created_at": f"{today_str}T10:00:00Z",
            "updated_at": f"{today_str}T12:00:00Z",
        },
    }

    assignments = [
        # Mech 1 assignments
        {"id": "a1", "booking_id": "b1", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "accepted", "created_at": f"{today_str}T08:30:00Z"},
        {"id": "a2", "booking_id": "b2", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "accepted", "created_at": f"{today_str}T09:30:00Z"},
        {"id": "a3", "booking_id": "b3", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "accepted", "created_at": f"{today_str}T13:40:00Z"},
        {"id": "a4", "booking_id": "b4", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "cancelled", "created_at": f"{today_str}T15:10:00Z"},
        {"id": "a5", "booking_id": "b5_failed", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "accepted", "created_at": "2026-09-15T08:30:00Z"},
        {"id": "a6", "booking_id": "b6_refunded", "mechanic_id": str(MECH_1_PROFILE_ID), "assignment_status": "accepted", "created_at": "2026-09-20T08:30:00Z"},
        # Mech 2 assignment
        {"id": "a_m2", "booking_id": "b_mech2", "mechanic_id": str(MECH_2_PROFILE_ID), "assignment_status": "accepted", "created_at": f"{today_str}T10:30:00Z"},
    ]

    mechanic_profiles = {
        str(MECH_1_PROFILE_ID): {
            "id": str(MECH_1_PROFILE_ID),
            "user_id": str(MECH_1_USER_ID),
            "business_name": "Mech 1 Garage",
            "average_rating": 4.67,
            "total_completed_jobs": 4,
        },
        str(MECH_2_PROFILE_ID): {
            "id": str(MECH_2_PROFILE_ID),
            "user_id": str(MECH_2_USER_ID),
            "business_name": "Mech 2 Motors",
            "average_rating": 5.0,
            "total_completed_jobs": 1,
        },
    }

    profiles = {
        str(MECH_1_USER_ID): {"id": str(MECH_1_USER_ID), "full_name": "Mike Mechanic", "role": "mechanic", "is_active": True},
        str(MECH_2_USER_ID): {"id": str(MECH_2_USER_ID), "full_name": "Dan Mechanic", "role": "mechanic", "is_active": True},
        str(CUSTOMER_USER_ID): {"id": str(CUSTOMER_USER_ID), "full_name": "John Customer Doe", "phone": "+919999999999", "email": "customer@secret.com", "role": "customer", "is_active": True},
        str(ADMIN_USER_ID): {"id": str(ADMIN_USER_ID), "full_name": "Adam Admin", "role": "admin", "is_active": True},
    }

    reviews = [
        {"id": str(uuid.uuid4()), "booking_id": "b1", "customer_id": str(CUSTOMER_USER_ID), "mechanic_id": str(MECH_1_PROFILE_ID), "rating": 5, "review_text": "Excellent work!", "created_at": f"{today_str}T12:00:00Z"},
        {"id": str(uuid.uuid4()), "booking_id": "b2", "customer_id": str(CUSTOMER_USER_ID), "mechanic_id": str(MECH_1_PROFILE_ID), "rating": 5, "review_text": "Prompt and polite", "created_at": f"{today_str}T13:30:00Z"},
        {"id": str(uuid.uuid4()), "booking_id": "b6_refunded", "customer_id": str(CUSTOMER_USER_ID), "mechanic_id": str(MECH_1_PROFILE_ID), "rating": 4, "review_text": "Good service overall", "created_at": "2026-09-21T10:00:00Z"},
        {"id": str(uuid.uuid4()), "booking_id": "b_mech2", "customer_id": str(CUSTOMER_USER_ID), "mechanic_id": str(MECH_2_PROFILE_ID), "rating": 5, "review_text": "Mech 2 was great", "created_at": f"{today_str}T13:00:00Z"},
    ]

    client = MagicMock()

    class MockQueryBuilder:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self._filters = []
            self._order = None
            self._range = None
            self._count = None

        def select(self, cols: str, count=None):
            self._count = count
            return self

        def eq(self, col: str, val: Any):
            self._filters.append((col, "eq", str(val)))
            return self

        def in_(self, col: str, vals: list):
            self._filters.append((col, "in", [str(v) for v in vals]))
            return self

        def order(self, col: str, desc: bool = False):
            self._order = (col, desc)
            return self

        def limit(self, lim: int):
            self._range = (0, lim - 1)
            return self

        def range(self, start: int, end: int):
            self._range = (start, end)
            return self

        def execute(self):
            # Resolve data
            if self.table_name == "mechanic_profiles":
                res = list(mechanic_profiles.values())
            elif self.table_name == "bookings":
                res = list(bookings.values())
            elif self.table_name == "mechanic_assignments":
                res = [dict(a) for a in assignments]
                # Embed bookings
                for item in res:
                    item["bookings"] = bookings.get(item["booking_id"])
            elif self.table_name == "reviews":
                res = list(reviews)
                for item in res:
                    item["profiles"] = profiles.get(item["customer_id"])
            elif self.table_name == "profiles":
                res = list(profiles.values())
            else:
                res = []

            # Apply filters
            for col, op, val in self._filters:
                if op == "eq":
                    res = [r for r in res if str(r.get(col)) == val]
                elif op == "in":
                    res = [r for r in res if str(r.get(col)) in val]

            # Apply ordering
            if self._order:
                col, desc = self._order
                res = sorted(res, key=lambda x: str(x.get(col) or ""), reverse=desc)

            total_count = len(res)

            # Apply pagination range
            if self._range:
                start, end = self._range
                res = res[start : end + 1]

            mock_res = MagicMock()
            mock_res.data = res
            mock_res.count = total_count
            return mock_res

    client.table.side_effect = lambda t: MockQueryBuilder(t)
    return client


# ==============================================================================
# FIXTURES
# ==============================================================================

@pytest.fixture
def auth_mech_1():
    user = AuthenticatedUser(
        id=MECH_1_USER_ID,
        email="mech1@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_1_USER_ID,
            full_name="Mike Mechanic",
            phone="+919876543210",
            email="mech1@example.com",
            avatar_url=None,
            role=UserRole.MECHANIC,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_mech_2():
    user = AuthenticatedUser(
        id=MECH_2_USER_ID,
        email="mech2@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_2_USER_ID,
            full_name="Dan Mechanic",
            phone="+919876543211",
            email="mech2@example.com",
            avatar_url=None,
            role=UserRole.MECHANIC,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_customer():
    user = AuthenticatedUser(
        id=CUSTOMER_USER_ID,
        email="customer@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_USER_ID,
            full_name="John Customer Doe",
            phone="+919999999999",
            email="customer@example.com",
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


@pytest.fixture
def auth_admin():
    user = AuthenticatedUser(
        id=ADMIN_USER_ID,
        email="admin@example.com",
        role=UserRole.ADMIN,
        profile=UserProfileResponse(
            id=ADMIN_USER_ID,
            full_name="Adam Admin",
            phone="+919876543299",
            email="admin@example.com",
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
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


# ==============================================================================
# TESTS (1 through 28)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_unauthenticated_request_overview_returns_401(async_client):
    """Test 1: Unauthenticated request returns 401."""
    # Ensure no auth override
    app.dependency_overrides.pop(get_current_user, None)
    res = await async_client.get("/api/v1/mechanics/dashboard/overview")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_02_customer_calling_dashboard_returns_403(async_client, auth_customer):
    """Test 2: Customer calling dashboard returns 403."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]


@pytest.mark.asyncio
async def test_03_mechanic_can_read_own_dashboard(async_client, auth_mech_1):
    """Test 3: Mechanic can read own dashboard."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        data = res.json()
        assert "today" in data
        assert "total_earnings" in data
        assert "average_rating" in data


@pytest.mark.asyncio
async def test_04_mechanic_cannot_read_another_mechanics_dashboard_403(async_client, auth_mech_1):
    """Test 4: Mechanic cannot read another mechanic's dashboard via target_mechanic_id."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/dashboard/overview?mechanic_id={MECH_2_PROFILE_ID}")
        assert res.status_code == 403
        assert "only view your own" in res.json()["detail"]


@pytest.mark.asyncio
async def test_05_overview_values_use_database_data(async_client, auth_mech_1):
    """Test 5: Overview values use actual database data."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        d = res.json()
        # Today's jobs for Mech 1 = 4 scheduled today (b1, b2, b3, b4)
        assert d["today"]["jobs"] == 4
        assert d["today"]["completed"] == 2  # b1 (paid) + b2 (service_completed)
        assert d["today"]["cancelled"] == 1  # b4


@pytest.mark.asyncio
async def test_06_completed_jobs_calculation(async_client, auth_mech_1):
    """Test 6: Completed jobs calculation."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # Completed jobs for Mech 1: b1, b2, b5_failed, b6_refunded (all in COMPLETED_STATUSES)
        assert res.json()["completed_jobs"] == 4


@pytest.mark.asyncio
async def test_07_cancelled_jobs_calculation(async_client, auth_mech_1):
    """Test 7: Cancelled jobs calculation."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # b4 is cancelled
        assert res.json()["cancelled_jobs"] == 1


@pytest.mark.asyncio
async def test_08_active_jobs_calculation(async_client, auth_mech_1):
    """Test 8: Active jobs calculation."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # b3 is service_in_progress
        assert res.json()["active_jobs"] == 1


@pytest.mark.asyncio
async def test_09_completion_rate_calculation(async_client, auth_mech_1):
    """Test 9: Completion rate calculation (completed / (completed + cancelled))."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # 4 completed / (4 completed + 1 cancelled) = 4/5 = 80.0%
        assert res.json()["completion_rate"] == 80.0


@pytest.mark.asyncio
async def test_10_zero_denominator_completion_rate_safe(async_client, auth_mech_2):
    """Test 10: Zero denominator completion rate handles division safely."""
    mock_db = build_dashboard_mock_db()
    # Remove assignments for mech 2 so denom is 0
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        # Override table to return empty assignments for mech 2
        orig_table = mock_db.table
        def custom_table(name):
            qb = orig_table(name)
            if name == "mechanic_assignments":
                qb.execute = MagicMock(return_value=MagicMock(data=[], count=0))
            return qb
        mock_db.table = custom_table

        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        assert res.json()["completion_rate"] == 0.0


@pytest.mark.asyncio
async def test_11_rating_average_calculation(async_client, auth_mech_1):
    """Test 11: Rating average calculation."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # Ratings for Mech 1: 5, 5, 4 -> sum=14, count=3 -> avg = 4.67
        assert res.json()["average_rating"] == 4.67


@pytest.mark.asyncio
async def test_12_rating_distribution_1_to_5(async_client, auth_mech_1):
    """Test 12: Rating distribution breakdown."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/performance")
        assert res.status_code == 200
        dist = res.json()["rating_distribution"]
        # 1: 0, 2: 0, 3: 0, 4: 1, 5: 2
        assert dist["1"] == 0
        assert dist["2"] == 0
        assert dist["3"] == 0
        assert dist["4"] == 1
        assert dist["5"] == 2


@pytest.mark.asyncio
async def test_13_review_count_calculation(async_client, auth_mech_1):
    """Test 13: Review count calculation."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        assert res.json()["review_count"] == 3


@pytest.mark.asyncio
async def test_14_earnings_calculation_gross_and_net(async_client, auth_mech_1):
    """Test 14: Earnings calculation gross and net."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # Paid earnings: b1 subtotal (1200.50) + additional (300.25) = 1500.75
        assert res.json()["total_earnings"] == "1500.75"
        # Pending earnings: b2 subtotal (800.00) = 800.00
        assert res.json()["pending_earnings"] == "800.00"


@pytest.mark.asyncio
async def test_15_additional_work_included_correctly(async_client, auth_mech_1):
    """Test 15: Additional work included in gross and net amounts."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/earnings?status=paid")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 1
        b1_item = items[0]
        assert b1_item["booking_number"] == "BK-M1-001"
        assert b1_item["gross_amount"] == "1200.50"
        assert b1_item["additional_work_amount"] == "300.25"
        assert b1_item["net_amount"] == "1500.75"


@pytest.mark.asyncio
async def test_16_failed_payment_excluded_from_earnings(async_client, auth_mech_1):
    """Test 16: Failed payment is not counted towards total or pending earnings."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # Total earnings is strictly 1500.75; b5_failed (1000.00) is NOT added
        assert res.json()["total_earnings"] == "1500.75"
        assert res.json()["pending_earnings"] == "800.00"


@pytest.mark.asyncio
async def test_17_refunded_payment_excluded_from_earnings(async_client, auth_mech_1):
    """Test 17: Refunded payment is not counted towards total or pending earnings."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        # b6_refunded (1700.00) is NOT added to total or pending earnings
        assert res.json()["total_earnings"] == "1500.75"
        assert res.json()["pending_earnings"] == "800.00"


@pytest.mark.asyncio
async def test_18_date_filtering_performance_and_earnings(async_client, auth_mech_1):
    """Test 18: Date filtering on performance and earnings."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        # Filter for September 2026 only
        res = await async_client.get(
            "/api/v1/mechanics/dashboard/performance?from_date=2026-09-01&to_date=2026-09-30"
        )
        assert res.status_code == 200
        data = res.json()
        # In Sept: b5_failed and b6_refunded were scheduled
        assert data["completed_jobs"] == 2
        assert data["cancelled_jobs"] == 0
        assert data["active_jobs"] == 0


@pytest.mark.asyncio
async def test_19_pagination_earnings_and_recent(async_client, auth_mech_1):
    """Test 19: Pagination works on earnings."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res1 = await async_client.get("/api/v1/mechanics/dashboard/earnings?limit=2&offset=0")
        assert res1.status_code == 200
        d1 = res1.json()
        assert len(d1["items"]) == 2
        assert d1["limit"] == 2
        assert d1["offset"] == 0

        res2 = await async_client.get("/api/v1/mechanics/dashboard/earnings?limit=2&offset=2")
        assert res2.status_code == 200
        d2 = res2.json()
        assert d2["offset"] == 2


@pytest.mark.asyncio
async def test_20_limit_bounds_clamping(async_client, auth_mech_1):
    """Test 20: Limit bounds enforcement (rejecting limit > 100 with 422)."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/earnings?limit=150")
        assert res.status_code == 422


@pytest.mark.asyncio
async def test_21_invalid_dates_return_422(async_client, auth_mech_1):
    """Test 21: Invalid date format returns 422."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/performance?from_date=not-a-date")
        assert res.status_code == 422
        assert "Invalid ISO date" in res.json()["detail"]


@pytest.mark.asyncio
async def test_22_recent_jobs_ownership(async_client, auth_mech_1):
    """Test 22: Recent jobs returns only jobs assigned to authenticated mechanic."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/recent-jobs")
        assert res.status_code == 200
        items = res.json()["items"]
        booking_numbers = [item["booking_number"] for item in items]
        assert "BK-M1-001" in booking_numbers
        # Mech 2's booking must NOT appear
        assert "BK-M2-001" not in booking_numbers


@pytest.mark.asyncio
async def test_23_recent_reviews_ownership(async_client, auth_mech_1):
    """Test 23: Recent reviews returns only reviews for authenticated mechanic."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/recent-reviews")
        assert res.status_code == 200
        items = res.json()["items"]
        assert len(items) == 3
        # Review for Mech 2 must NOT appear
        comments = [i["review_text"] for i in items]
        assert "Mech 2 was great" not in comments


@pytest.mark.asyncio
async def test_24_no_customer_pii_leakage(async_client, auth_mech_1):
    """Test 24: No customer phone, email, or unmasked name leaked in recent reviews and jobs."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        rev_res = await async_client.get("/api/v1/mechanics/dashboard/recent-reviews")
        assert rev_res.status_code == 200
        content_str = rev_res.text
        # Assert private identifiers are NOT leaked
        assert "+919999999999" not in content_str
        assert "customer@secret.com" not in content_str
        assert "John Customer Doe" not in content_str
        # Verify masked name is present
        assert "John D." in content_str


@pytest.mark.asyncio
async def test_25_decimal_monetary_precision(async_client, auth_mech_1):
    """Test 25: Monetary calculations preserve 2-decimal precision (e.g. 1500.75)."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        data = res.json()
        assert data["total_earnings"] == "1500.75"
        assert data["pending_earnings"] == "800.00"


@pytest.mark.asyncio
async def test_26_empty_dashboard_clean_defaults(async_client, auth_mech_2):
    """Test 26: Empty dashboard returns clean zero/empty values with no crashes."""
    mock_db = build_dashboard_mock_db()
    # Clear out all data for mech 2
    orig_table = mock_db.table
    def custom_table(name):
        qb = orig_table(name)
        if name in ["mechanic_assignments", "reviews"]:
            qb.execute = MagicMock(return_value=MagicMock(data=[], count=0))
        return qb
    mock_db.table = custom_table

    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/dashboard/overview")
        assert res.status_code == 200
        d = res.json()
        assert d["active_jobs"] == 0
        assert d["completed_jobs"] == 0
        assert d["cancelled_jobs"] == 0
        assert d["total_earnings"] == "0.00"
        assert d["pending_earnings"] == "0.00"
        assert d["review_count"] == 0
        assert d["completion_rate"] == 0.0


@pytest.mark.asyncio
async def test_27_admin_and_support_access(async_client, auth_admin):
    """Test 27: Admin can inspect a specific mechanic's dashboard."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/dashboard/overview?mechanic_id={MECH_1_PROFILE_ID}")
        assert res.status_code == 200
        assert res.json()["total_earnings"] == "1500.75"


@pytest.mark.asyncio
async def test_28_concurrent_safe_read_behavior(async_client, auth_mech_1):
    """Test 28: Concurrent parallel dashboard queries succeed safely without race conditions."""
    mock_db = build_dashboard_mock_db()
    with patch("app.services.mechanic_dashboard_service.get_supabase_service_client", return_value=mock_db):
        endpoints = [
            "/api/v1/mechanics/dashboard/overview",
            "/api/v1/mechanics/dashboard/performance",
            "/api/v1/mechanics/dashboard/earnings",
            "/api/v1/mechanics/dashboard/recent-jobs",
            "/api/v1/mechanics/dashboard/recent-reviews",
        ]
        tasks = [async_client.get(ep) for ep in endpoints]
        responses = await asyncio.gather(*tasks)
        for r in responses:
            assert r.status_code == 200
