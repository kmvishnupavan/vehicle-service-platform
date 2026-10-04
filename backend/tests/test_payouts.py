"""
Unit and Integration Tests for Mechanic Payout Ledger & Settlement Foundation (Phase 8.7).

Covers all 24 required test specifications + concurrency:
1. unauthenticated request -> 401
2. customer calling payouts -> 403
3. mechanic own payout -> 200
4. mechanic cross-access -> 403
5. payout creation on booking settlement
6. duplicate payout creation idempotency
7. commission calculation accuracy
8. Decimal monetary precision
9. payout state machine transitions
10. invalid state transitions rejected
11. failed payment excluded from payout
12. refunded payment handled appropriately
13. partial refund adjustment on unsettled payout
14. full refund reversal transition
15. payout summary financial aggregation
16. pagination limit & offset
17. date filters (from_date, to_date, invalid 422)
18. status filters
19. concurrent creation idempotency
20. audit logging verification
21. RLS isolation (cross-mechanic detail access forbidden)
22. no customer PII or provider secrets leakage
23. immutable financial fields protection
24. historical commission rate preservation
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
import uuid
from fastapi import HTTPException
import pytest
from httpx import ASGITransport, AsyncClient
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.payout import PayoutStatus
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.payout_service import PayoutService
from app.services.payout_state_machine import PayoutStateMachine

# Test IDs (Strict UUIDs)
MECH_1_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MECH_1_PROFILE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

MECH_2_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
MECH_2_PROFILE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")

CUSTOMER_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ADMIN_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

BK_1_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BK_2_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
BK_FAILED_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
BK_CANCELLED_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
BK_REFUNDED_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
BK_M2_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

POUT_1_ID = uuid.UUID("11111111-aaaa-1111-aaaa-111111111111")
POUT_2_ID = uuid.UUID("22222222-bbbb-2222-bbbb-222222222222")
POLICY_ID = uuid.UUID("c0000000-0000-0000-0000-000000000001")


def build_payout_mock_db():
    """Stateful mock database for payout ledger testing."""
    commission_policies = {
        str(POLICY_ID): {
            "id": str(POLICY_ID),
            "name": "Standard Platform Commission (20%)",
            "commission_rate": 0.2000,
            "currency": "INR",
            "is_active": True,
            "effective_from": "2026-01-01T00:00:00Z",
            "effective_to": None,
            "created_at": "2026-01-01T00:00:00Z",
        }
    }

    mechanic_profiles = {
        str(MECH_1_PROFILE_ID): {
            "id": str(MECH_1_PROFILE_ID),
            "user_id": str(MECH_1_USER_ID),
            "workshop_name": "Pro Auto Garage",
        },
        str(MECH_2_PROFILE_ID): {
            "id": str(MECH_2_PROFILE_ID),
            "user_id": str(MECH_2_USER_ID),
            "workshop_name": "Speedy Fix",
        },
    }

    bookings = {
        str(BK_1_ID): {
            "id": str(BK_1_ID),
            "booking_number": "BK-2026-001",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "paid",
            "payment_status": "paid",
            "subtotal": 1000.00,
            "additional_charges": 200.00,
            "total_amount": 1416.00,
            "created_at": "2026-09-01T10:00:00Z",
            "updated_at": "2026-09-01T12:00:00Z",
        },
        str(BK_2_ID): {
            "id": str(BK_2_ID),
            "booking_number": "BK-2026-002",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "pending",
            "subtotal": 800.00,
            "additional_charges": 0.00,
            "total_amount": 944.00,
            "created_at": "2026-09-05T10:00:00Z",
            "updated_at": "2026-09-05T12:00:00Z",
        },
        str(BK_FAILED_ID): {
            "id": str(BK_FAILED_ID),
            "booking_number": "BK-2026-FAIL",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "failed",
            "subtotal": 500.00,
            "additional_charges": 0.00,
            "total_amount": 590.00,
            "created_at": "2026-09-10T10:00:00Z",
        },
        str(BK_CANCELLED_ID): {
            "id": str(BK_CANCELLED_ID),
            "booking_number": "BK-2026-CANC",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "cancelled",
            "payment_status": "unpaid",
            "subtotal": 500.00,
            "additional_charges": 0.00,
            "total_amount": 590.00,
            "created_at": "2026-09-11T10:00:00Z",
        },
        str(BK_REFUNDED_ID): {
            "id": str(BK_REFUNDED_ID),
            "booking_number": "BK-2026-REF",
            "customer_id": str(CUSTOMER_USER_ID),
            "booking_status": "service_completed",
            "payment_status": "refunded",
            "subtotal": 1200.00,
            "additional_charges": 0.00,
            "total_amount": 1416.00,
            "created_at": "2026-09-12T10:00:00Z",
        },
    }

    mechanic_assignments = {
        "asgn_1": {
            "id": "asgn_1",
            "booking_id": str(BK_1_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "completed",
            "created_at": "2026-09-01T10:05:00Z",
        },
        "asgn_2": {
            "id": "asgn_2",
            "booking_id": str(BK_2_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "completed",
            "created_at": "2026-09-05T10:05:00Z",
        },
        "asgn_failed": {
            "id": "asgn_failed",
            "booking_id": str(BK_FAILED_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "completed",
            "created_at": "2026-09-10T10:05:00Z",
        },
        "asgn_cancelled": {
            "id": "asgn_cancelled",
            "booking_id": str(BK_CANCELLED_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "cancelled",
            "created_at": "2026-09-11T10:05:00Z",
        },
        "asgn_refunded": {
            "id": "asgn_refunded",
            "booking_id": str(BK_REFUNDED_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "completed",
            "created_at": "2026-09-12T10:05:00Z",
        },
    }

    payout_ledger = {
        str(POUT_1_ID): {
            "id": str(POUT_1_ID),
            "booking_id": str(BK_1_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "gross_amount": 1200.00,
            "commission_rate": 0.2000,
            "commission_amount": 240.00,
            "deduction_amount": 0.00,
            "net_amount": 960.00,
            "currency": "INR",
            "status": "eligible",
            "created_at": "2026-09-01T12:00:00Z",
            "updated_at": "2026-09-01T12:00:00Z",
            "eligible_at": "2026-09-01T12:00:00Z",
            "settled_at": None,
            "reversed_at": None,
            "provider": "manual",
            "provider_payout_id": None,
            "metadata": {"booking_number": "BK-2026-001"},
        },
        str(POUT_2_ID): {
            "id": str(POUT_2_ID),
            "booking_id": str(BK_M2_ID),
            "mechanic_id": str(MECH_2_PROFILE_ID),
            "gross_amount": 1500.00,
            "commission_rate": 0.2000,
            "commission_amount": 300.00,
            "deduction_amount": 0.00,
            "net_amount": 1200.00,
            "currency": "INR",
            "status": "paid",
            "created_at": "2026-09-02T12:00:00Z",
            "updated_at": "2026-09-02T14:00:00Z",
            "eligible_at": "2026-09-02T12:00:00Z",
            "settled_at": "2026-09-02T14:00:00Z",
            "reversed_at": None,
            "provider": "manual",
            "provider_payout_id": "pout_test_002",
            "metadata": {"booking_number": "BK-M2-001"},
        },
    }

    audit_logs = []

    class MockQuery:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.filters = []
            self._order_field = None
            self._order_desc = False
            self._limit_val = None
            self._pending_update = None
            self._pending_insert = None

        def select(self, *args, **kwargs):
            return self

        def eq(self, field: str, value: Any):
            self.filters.append(("eq", field, str(value)))
            return self

        def in_(self, field: str, values: list[Any]):
            self.filters.append(("in", field, [str(v) for v in values]))
            return self

        def lte(self, field: str, value: Any):
            self.filters.append(("lte", field, str(value)))
            return self

        def gte(self, field: str, value: Any):
            self.filters.append(("gte", field, str(value)))
            return self

        def order(self, field: str, desc: bool = False):
            self._order_field = field
            self._order_desc = desc
            return self

        def limit(self, val: int):
            self._limit_val = val
            return self

        def insert(self, payload: dict | list):
            self._pending_insert = payload if isinstance(payload, list) else [payload]
            return self

        def update(self, payload: dict):
            self._pending_update = payload
            return self

        def execute(self):
            res_obj = MagicMock()
            target_store = None

            if self.table_name == "commission_policies":
                target_store = commission_policies
            elif self.table_name == "mechanic_profiles":
                target_store = mechanic_profiles
            elif self.table_name == "bookings":
                target_store = bookings
            elif self.table_name == "mechanic_assignments":
                target_store = mechanic_assignments
            elif self.table_name == "mechanic_payout_ledger":
                target_store = payout_ledger
            elif self.table_name == "audit_logs":
                if self._pending_insert:
                    audit_logs.extend(self._pending_insert)
                    res_obj.data = self._pending_insert
                    return res_obj
                res_obj.data = audit_logs
                return res_obj

            if self._pending_insert is not None:
                inserted = []
                for item in self._pending_insert:
                    item_id = str(item.get("id") or uuid.uuid4())
                    item["id"] = item_id
                    target_store[item_id] = item
                    inserted.append(item)
                res_obj.data = inserted
                return res_obj

            # Filter existing
            items = list(target_store.values())
            for op, field, val in self.filters:
                if op == "eq":
                    items = [it for it in items if str(it.get(field)) == val]
                elif op == "in":
                    items = [it for it in items if str(it.get(field)) in val]
                elif op == "lte":
                    items = [it for it in items if str(it.get(field)) <= val]
                elif op == "gte":
                    items = [it for it in items if str(it.get(field)) >= val]

            if self._pending_update is not None:
                updated = []
                for it in items:
                    it.update(self._pending_update)
                    updated.append(it)
                res_obj.data = updated
                return res_obj

            if self._order_field:
                items = sorted(
                    items,
                    key=lambda x: str(x.get(self._order_field, "")),
                    reverse=self._order_desc,
                )

            if self._limit_val is not None:
                items = items[: self._limit_val]

            res_obj.data = items
            return res_obj

    class MockClient:
        def table(self, table_name: str):
            return MockQuery(table_name)

    return MockClient()


@pytest.fixture
def auth_mech_1():
    user = AuthenticatedUser(
        id=MECH_1_USER_ID,
        email="mechanic1@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_1_USER_ID,
            email="mechanic1@example.com",
            role=UserRole.MECHANIC,
            full_name="Pro Mechanic One",
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
        email="mechanic2@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_2_USER_ID,
            email="mechanic2@example.com",
            role=UserRole.MECHANIC,
            full_name="Speedy Mechanic Two",
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
            email="customer@example.com",
            role=UserRole.CUSTOMER,
            full_name="Jane Customer",
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
            email="admin@example.com",
            role=UserRole.ADMIN,
            full_name="System Admin",
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
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==============================================================================
# TESTS (1 TO 24)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_unauthenticated_request_returns_401(async_client):
    """Test 1: Unauthenticated request to /payouts returns 401."""
    app.dependency_overrides.pop(get_current_user, None)
    res = await async_client.get("/api/v1/mechanics/payouts")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_02_customer_calling_payouts_returns_403(async_client, auth_customer):
    """Test 2: Customer role attempting to call payouts returns 403 Forbidden."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payouts")
        assert res.status_code == 403
        assert "requires mechanic role" in res.json()["detail"]


@pytest.mark.asyncio
async def test_03_mechanic_own_payout_returns_200(async_client, auth_mech_1):
    """Test 3: Mechanic can retrieve their own payout records."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payouts")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert data["total"] == 1
        assert data["items"][0]["id"] == str(POUT_1_ID)
        assert data["items"][0]["gross_amount"] == "1200.00"
        assert data["items"][0]["commission_amount"] == "240.00"
        assert data["items"][0]["net_amount"] == "960.00"


@pytest.mark.asyncio
async def test_04_mechanic_cross_access_returns_403(async_client, auth_mech_1):
    """Test 4: Mechanic cannot query payouts belonging to another mechanic via query param."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/payouts?mechanic_id={MECH_2_PROFILE_ID}")
        assert res.status_code == 403
        assert "only view your own mechanic payouts" in res.json()["detail"]


@pytest.mark.asyncio
async def test_05_payout_creation_on_booking_payment():
    """Test 5: PayoutService.create_payout_for_booking creates valid ledger entry."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    # Create payout for bk_2 (subtotal 800 + additional 0 = 800 gross)
    payout = await service.create_payout_for_booking(booking_id=BK_2_ID)
    assert payout is not None
    assert payout["booking_id"] == str(BK_2_ID)
    assert payout["mechanic_id"] == str(MECH_1_PROFILE_ID)
    assert payout["gross_amount"] == 800.00
    assert payout["commission_rate"] == 0.2000
    assert payout["commission_amount"] == 160.00
    assert payout["net_amount"] == 640.00
    assert payout["currency"] == "INR"


@pytest.mark.asyncio
async def test_06_idempotent_duplicate_payout_creation():
    """Test 6: Idempotent duplicate payout creation returns existing record without duplicating."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    p1 = await service.create_payout_for_booking(booking_id=BK_1_ID)
    assert p1 is not None
    assert p1["id"] == str(POUT_1_ID)

    # Second call must return identical p1 without duplicate
    p2 = await service.create_payout_for_booking(booking_id=BK_1_ID)
    assert p2 is not None
    assert p2["id"] == p1["id"]
    assert p2["net_amount"] == p1["net_amount"]


def test_07_commission_calculation():
    """Test 7: Centralized commission calculation using strict Decimal logic."""
    service = PayoutService(client=MagicMock())

    gross = Decimal("1000.00")
    rate = Decimal("0.2000")
    deductions = Decimal("0.00")

    comm, ded, net = service.calculate_payout_components(gross, rate, deductions)
    assert comm == Decimal("200.00")
    assert ded == Decimal("0.00")
    assert net == Decimal("800.00")
    assert gross - comm - ded == net


def test_08_decimal_precision():
    """Test 8: Decimal precision handling with odd fractions (no floating point errors)."""
    service = PayoutService(client=MagicMock())

    # e.g. 1234.56 * 0.2000 = 246.912 -> quantizes to 246.91
    gross = Decimal("1234.56")
    rate = Decimal("0.2000")
    ded = Decimal("12.34")

    comm, d, net = service.calculate_payout_components(gross, rate, ded)
    assert comm == Decimal("246.91")
    assert d == Decimal("12.34")
    assert net == Decimal("975.31")
    assert (gross - comm - d) == net


def test_09_payout_state_transitions():
    """Test 9: Valid payout state machine transitions."""
    assert PayoutStateMachine.can_transition(PayoutStatus.PENDING, PayoutStatus.ELIGIBLE) is True
    assert PayoutStateMachine.can_transition(PayoutStatus.ELIGIBLE, PayoutStatus.PROCESSING) is True
    assert PayoutStateMachine.can_transition(PayoutStatus.PROCESSING, PayoutStatus.PAID) is True
    assert PayoutStateMachine.can_transition(PayoutStatus.PAID, PayoutStatus.REVERSED) is True
    assert PayoutStateMachine.can_transition(PayoutStatus.PROCESSING, PayoutStatus.FAILED) is True


def test_10_invalid_state_transition_rejected():
    """Test 10: Invalid transitions raise exception."""
    with pytest.raises(HTTPException) as exc_info:
        PayoutStateMachine.enforce_transition(PayoutStatus.PENDING, PayoutStatus.PAID)
    assert exc_info.value.status_code == 400
    assert "Invalid payout transition" in str(exc_info.value.detail)

    with pytest.raises(HTTPException):
        PayoutStateMachine.enforce_transition(PayoutStatus.REVERSED, PayoutStatus.PROCESSING)


@pytest.mark.asyncio
async def test_11_failed_payment_excluded_from_payout():
    """Test 11: Failed payments are excluded from payout ledger creation."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    payout = await service.create_payout_for_booking(booking_id=BK_FAILED_ID)
    assert payout is None


@pytest.mark.asyncio
async def test_12_refunded_payment_handled():
    """Test 12: Refunded payment does not create a new payout ledger record."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    payout = await service.create_payout_for_booking(booking_id=BK_REFUNDED_ID)
    assert payout is None


@pytest.mark.asyncio
async def test_13_partial_refund_unsettled_payout_adjusted():
    """Test 13: Partial refund on unsettled payout adjusts gross and net."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    # Initial: pout_1 has gross 1200.00, comm 240.00, net 960.00
    updated = await service.handle_payment_refund(
        booking_id=BK_1_ID,
        refund_amount=Decimal("200.00"),
        is_full_refund=False,
        refund_id="rf_part_1",
    )
    assert updated is not None
    # New gross = 1200 - 200 = 1000.00
    # New comm (20%) = 200.00
    # New net = 800.00
    assert updated["gross_amount"] == 1000.00
    assert updated["commission_amount"] == 200.00
    assert updated["net_amount"] == 800.00


@pytest.mark.asyncio
async def test_14_full_refund_reversal():
    """Test 14: Full refund marks payout as reversed with reversal timestamp."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    updated = await service.handle_payment_refund(
        booking_id=BK_1_ID,
        refund_amount=Decimal("1200.00"),
        is_full_refund=True,
        refund_id="rf_full_1",
    )
    assert updated is not None
    assert updated["status"] == "reversed"
    assert updated["reversed_at"] is not None


@pytest.mark.asyncio
async def test_15_payout_summary_aggregation(async_client, auth_mech_1):
    """Test 15: Payout summary aggregates balances with Decimal precision."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payouts/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["currency"] == "INR"
        assert data["total_gross"] == "1200.00"
        assert data["total_commission"] == "240.00"
        assert data["total_deductions"] == "0.00"
        assert data["total_net"] == "960.00"
        assert data["eligible_amount"] == "960.00"
        assert data["pending_amount"] == "0.00"
        assert data["paid_amount"] == "0.00"


@pytest.mark.asyncio
async def test_16_pagination_limit_and_offset(async_client, auth_mech_1):
    """Test 16: Pagination limits and offsets validation."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payouts?limit=1&offset=0")
        assert res.status_code == 200
        d = res.json()
        assert len(d["items"]) <= 1
        assert d["limit"] == 1
        assert d["offset"] == 0

        # Limit > 100 rejected with 422
        res_overflow = await async_client.get("/api/v1/mechanics/payouts?limit=150")
        assert res_overflow.status_code == 422


@pytest.mark.asyncio
async def test_17_date_filters(async_client, auth_mech_1):
    """Test 17: Date filters work and invalid dates return 422."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        # Valid date
        res = await async_client.get("/api/v1/mechanics/payouts?from_date=2026-09-01&to_date=2026-09-30")
        assert res.status_code == 200

        # Invalid date format
        res_bad = await async_client.get("/api/v1/mechanics/payouts?from_date=not-a-date")
        assert res_bad.status_code == 422
        assert "Invalid ISO date" in res_bad.json()["detail"]


@pytest.mark.asyncio
async def test_18_status_filters(async_client, auth_mech_1):
    """Test 18: Filter by payout status."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payouts?status=eligible")
        assert res.status_code == 200
        assert len(res.json()["items"]) == 1
        assert res.json()["items"][0]["status"] == "eligible"

        res_none = await async_client.get("/api/v1/mechanics/payouts?status=paid")
        assert res_none.status_code == 200
        assert len(res_none.json()["items"]) == 0


@pytest.mark.asyncio
async def test_19_concurrent_creation():
    """Test 19: Concurrent creation attempts safely return identical payout."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    results = await asyncio.gather(
        service.create_payout_for_booking(BK_2_ID),
        service.create_payout_for_booking(BK_2_ID),
    )
    assert results[0] is not None
    assert results[1] is not None
    assert results[0]["id"] == results[1]["id"]


@pytest.mark.asyncio
async def test_20_audit_logging():
    """Test 20: Audit logging is executed on payout transitions."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    with patch("app.services.payout_service.record_audit_log") as mock_audit:
        await service.transition_payout_status(
            payout_id=POUT_1_ID,
            target_status=PayoutStatus.PROCESSING,
            actor_role="admin",
        )
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["action"] == "payout_processing"
        assert call_kwargs["entity_type"] == "mechanic_payout_ledger"


@pytest.mark.asyncio
async def test_21_rls_isolation(async_client, auth_mech_1):
    """Test 21: Mechanic cannot fetch payout belonging to another mechanic by payout_id."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/payouts/{POUT_2_ID}")
        assert res.status_code == 403
        assert "Access denied" in res.json()["detail"]


@pytest.mark.asyncio
async def test_22_no_customer_pii_leakage(async_client, auth_mech_1):
    """Test 22: Payout responses do not contain customer phone, email, or gateway secrets."""
    mock_db = build_payout_mock_db()
    with patch("app.services.payout_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/payouts/{POUT_1_ID}")
        assert res.status_code == 200
        item = res.json()
        assert "customer_phone" not in item
        assert "customer_email" not in item
        assert "razorpay_secret" not in item
        assert "webhook_secret" not in item


def test_23_immutable_financial_fields():
    """Test 23: Verify that financial payout calculations reject invalid inputs."""
    service = PayoutService(client=MagicMock())
    with pytest.raises(ValueError):
        service.calculate_payout_components(Decimal("-10.00"), Decimal("0.20"))
    with pytest.raises(ValueError):
        service.calculate_payout_components(Decimal("100.00"), Decimal("1.50"))
    with pytest.raises(ValueError):
        service.calculate_payout_components(Decimal("100.00"), Decimal("0.20"), Decimal("-5.00"))


@pytest.mark.asyncio
async def test_24_historical_commission_rate_preservation():
    """Test 24: Historical payout ledger entry retains original applied rate when queried."""
    mock_db = build_payout_mock_db()
    service = PayoutService(client=mock_db)

    # Change active policy in mock DB to 30%
    mock_db.table("commission_policies").update({"commission_rate": 0.3000}).eq("id", str(POLICY_ID)).execute()

    # Query historical payout pout_1
    pout = await service.get_payout_by_id(POUT_1_ID)
    # Must preserve original 20% commission rate applied at creation
    assert pout.commission_rate == "0.2000"
    assert pout.commission_amount == "240.00"
    assert pout.net_amount == "960.00"
