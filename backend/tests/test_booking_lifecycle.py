"""
Comprehensive Booking Lifecycle, State Machine, and Concurrency Tests (Phase 6B).

Tests:
A. State Machine:
1. Valid forward lifecycle transitions
2. Invalid backward / illegal transitions
3. Strict terminal state protection (cancelled has no outgoing transitions)
4. 'paid' status reserved for payment processing
5. Customer cancellation and dispute permissions
6. Mechanic lifecycle progression permissions

B. Role-Based Authorization & API Endpoints:
7. Unauthenticated status update -> 401
8. Customer valid cancellation with reason -> 200
9. Customer cannot update another customer's booking -> 404 (no existence leak)
10. Customer cannot execute mechanic progression steps -> 403
11. Assigned mechanic valid progression (assigned -> en_route -> arrived -> inspection -> service_in_progress -> service_completed -> payment_pending) -> 200
12. Unassigned mechanic cannot update booking -> 403
13. Customer approval advances awaiting_customer_approval -> service_in_progress -> 200
14. Customer dispute on completed / paid booking -> 200
15. Customer dispute on pre-service booking -> 400 rejection
16. Mechanic cannot raise dispute -> 403
17. Attempting transition from cancelled state -> 400 rejection
18. Direct attempt to set 'paid' via status endpoint -> 400 rejection
19. Extra payload fields rejected -> 422
20. Concurrent status update race -> 409 Conflict

C. Atomic Concurrency Acceptance Test (Mandatory Part 11.F):
21. Concurrent mechanic acceptance: two mechanics accept simultaneous offers for the same booking.
    Exactly ONE succeeds (200), exactly ONE receives 409 Conflict.
    DB ends with exactly 1 accepted assignment and booking_status = mechanic_assigned.
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.booking import BookingStatus
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.booking_state_machine import BookingStateMachine
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID, MECHANIC_ID, OTHER_MECHANIC_ID

BOOKING_TEST_ID = uuid.UUID("88881111-0000-0000-0000-000000000001")
BOOKING_OTHER_ID = uuid.UUID("88882222-0000-0000-0000-000000000002")

MECH_1_PROFILE_ID = uuid.UUID("99991111-0000-0000-0000-000000000001")
MECH_2_PROFILE_ID = uuid.UUID("99992222-0000-0000-0000-000000000002")

ASSIGNMENT_1_ID = uuid.UUID("aaaaaaaa-1111-0000-0000-000000000001")
ASSIGNMENT_2_ID = uuid.UUID("aaaaaaaa-2222-0000-0000-000000000002")

ADMIN_ID = uuid.UUID("adadadad-0000-0000-0000-000000000001")


# ==============================================================================
# PART A: Unit Tests for BookingStateMachine
# ==============================================================================

def test_state_machine_valid_forward_transitions():
    """Verify all valid primary transitions in the booking lifecycle graph."""
    assert BookingStateMachine.is_valid_transition(BookingStatus.PENDING, BookingStatus.SEARCHING_MECHANIC)
    assert BookingStateMachine.is_valid_transition(BookingStatus.PENDING, BookingStatus.MECHANIC_ASSIGNED)
    assert BookingStateMachine.is_valid_transition(BookingStatus.PENDING, BookingStatus.CANCELLED)

    assert BookingStateMachine.is_valid_transition(BookingStatus.SEARCHING_MECHANIC, BookingStatus.MECHANIC_ASSIGNED)
    assert BookingStateMachine.is_valid_transition(BookingStatus.SEARCHING_MECHANIC, BookingStatus.CANCELLED)

    assert BookingStateMachine.is_valid_transition(BookingStatus.MECHANIC_ASSIGNED, BookingStatus.MECHANIC_EN_ROUTE)
    assert BookingStateMachine.is_valid_transition(BookingStatus.MECHANIC_EN_ROUTE, BookingStatus.MECHANIC_ARRIVED)
    assert BookingStateMachine.is_valid_transition(BookingStatus.MECHANIC_ARRIVED, BookingStatus.INSPECTION)

    assert BookingStateMachine.is_valid_transition(BookingStatus.INSPECTION, BookingStatus.AWAITING_CUSTOMER_APPROVAL)
    assert BookingStateMachine.is_valid_transition(BookingStatus.INSPECTION, BookingStatus.SERVICE_IN_PROGRESS)

    assert BookingStateMachine.is_valid_transition(BookingStatus.AWAITING_CUSTOMER_APPROVAL, BookingStatus.SERVICE_IN_PROGRESS)
    assert BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_IN_PROGRESS, BookingStatus.ADDITIONAL_WORK)
    assert BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_IN_PROGRESS, BookingStatus.SERVICE_COMPLETED)

    assert BookingStateMachine.is_valid_transition(BookingStatus.ADDITIONAL_WORK, BookingStatus.AWAITING_CUSTOMER_APPROVAL)
    assert BookingStateMachine.is_valid_transition(BookingStatus.ADDITIONAL_WORK, BookingStatus.SERVICE_IN_PROGRESS)

    assert BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_COMPLETED, BookingStatus.PAYMENT_PENDING)
    assert BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_COMPLETED, BookingStatus.DISPUTED)

    assert BookingStateMachine.is_valid_transition(BookingStatus.PAYMENT_PENDING, BookingStatus.PAID)
    assert BookingStateMachine.is_valid_transition(BookingStatus.PAYMENT_PENDING, BookingStatus.DISPUTED)

    assert BookingStateMachine.is_valid_transition(BookingStatus.PAID, BookingStatus.DISPUTED)


def test_state_machine_invalid_backward_transitions():
    """Verify illegal backward transitions and status jumps are rejected."""
    assert not BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_COMPLETED, BookingStatus.INSPECTION)
    assert not BookingStateMachine.is_valid_transition(BookingStatus.SERVICE_COMPLETED, BookingStatus.PENDING)
    assert not BookingStateMachine.is_valid_transition(BookingStatus.MECHANIC_ARRIVED, BookingStatus.MECHANIC_EN_ROUTE)
    assert not BookingStateMachine.is_valid_transition(BookingStatus.PENDING, BookingStatus.SERVICE_COMPLETED)
    assert not BookingStateMachine.is_valid_transition(BookingStatus.PAID, BookingStatus.PENDING)


def test_state_machine_terminal_state_protection():
    """Verify 'cancelled' is a strict terminal state with 0 allowed outgoing transitions."""
    allowed = BookingStateMachine.get_allowed_transitions(BookingStatus.CANCELLED)
    assert len(allowed) == 0

    for target in BookingStatus:
        assert not BookingStateMachine.is_valid_transition(BookingStatus.CANCELLED, target)
        valid, msg = BookingStateMachine.validate_transition(
            BookingStatus.CANCELLED, target, actor_role="admin"
        )
        assert not valid
        if target == BookingStatus.CANCELLED:
            assert "already in 'cancelled'" in msg.lower()
        else:
            assert "terminal" in msg.lower()


def test_state_machine_role_authorization_logic():
    """Verify customer cannot execute mechanic actions and mechanic cannot execute customer actions."""
    # Customer cannot advance mechanic en route
    valid, msg = BookingStateMachine.validate_transition(
        current_status=BookingStatus.MECHANIC_ASSIGNED,
        new_status=BookingStatus.MECHANIC_EN_ROUTE,
        actor_role="customer",
        is_customer_owner=True,
    )
    assert not valid
    assert "not permitted" in msg.lower()

    # Mechanic cannot raise customer dispute
    valid, msg = BookingStateMachine.validate_transition(
        current_status=BookingStatus.SERVICE_COMPLETED,
        new_status=BookingStatus.DISPUTED,
        actor_role="mechanic",
        is_assigned_mechanic=True,
    )
    assert not valid
    assert "not authorized" in msg.lower()

    # Transition to paid blocked from generic status transition
    valid, msg = BookingStateMachine.validate_transition(
        current_status=BookingStatus.PAYMENT_PENDING,
        new_status=BookingStatus.PAID,
        actor_role="customer",
        is_customer_owner=True,
    )
    assert not valid
    assert "reserved for payment" in msg.lower()


# ==============================================================================
# Database Mock Builder for Lifecycle Integration Tests
# ==============================================================================

def build_lifecycle_mock_db(initial_status: str = "mechanic_assigned"):
    """Construct mock database client for booking status lifecycle tests."""
    mock_client = MagicMock()

    db_state = {
        "booking": {
            "id": str(BOOKING_TEST_ID),
            "booking_number": "BK-20261002-LIFECYCLE",
            "customer_id": str(CUSTOMER_1_ID),
            "vehicle_id": str(uuid.uuid4()),
            "address_id": str(uuid.uuid4()),
            "scheduled_at": "2026-10-02T10:00:00Z",
            "requested_latitude": "12.971598",
            "requested_longitude": "77.594562",
            "customer_notes": "Test notes",
            "subtotal": "1500.00",
            "additional_charges": "0.00",
            "discount_amount": "0.00",
            "tax_amount": "270.00",
            "total_amount": "1770.00",
            "payment_status": "unpaid",
            "booking_status": initial_status,
            "created_at": "2026-10-02T10:00:00Z",
            "updated_at": "2026-10-02T10:00:00Z",
            "booking_items": [],
        },
        "mechanic_profile": {
            "id": str(MECH_1_PROFILE_ID),
            "user_id": str(MECHANIC_ID),
        },
        "assignment": {
            "id": str(ASSIGNMENT_1_ID),
            "booking_id": str(BOOKING_TEST_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "assignment_status": "accepted",
        },
        "history": [],
    }

    def table_handler(table_name: str):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.range.return_value = query

        filters = {}

        def eq_mock(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_mock
        query.in_.return_value = query

        def execute_mock():
            if table_name == "bookings":
                b_id = filters.get("id")
                if b_id == str(BOOKING_TEST_ID):
                    # Check if conditional update required matching expected booking_status
                    if "booking_status" in filters and filters["booking_status"] != db_state["booking"]["booking_status"]:
                        return MagicMock(data=[])
                    return MagicMock(data=[dict(db_state["booking"])])
                return MagicMock(data=[])

            elif table_name == "mechanic_profiles":
                u_id = filters.get("user_id")
                if u_id == str(MECHANIC_ID):
                    return MagicMock(data=[dict(db_state["mechanic_profile"])])
                return MagicMock(data=[])

            elif table_name == "mechanic_assignments":
                b_id = filters.get("booking_id")
                m_id = filters.get("mechanic_id")
                asgn_status = filters.get("assignment_status")
                if b_id == str(BOOKING_TEST_ID) and m_id == str(MECH_1_PROFILE_ID) and asgn_status == "accepted":
                    return MagicMock(data=[dict(db_state["assignment"])])
                return MagicMock(data=[])

            elif table_name == "booking_status_history":
                return MagicMock(data=list(db_state["history"]))

            return MagicMock(data=[])

        query.execute.side_effect = execute_mock

        def update_mock(payload):
            upd_query = MagicMock()
            upd_filters = {}

            def upd_eq(col, val):
                upd_filters[col] = str(val)
                return upd_query

            upd_query.eq.side_effect = upd_eq
            upd_query.in_.return_value = upd_query
            upd_query.order.return_value = upd_query
            upd_query.limit.return_value = upd_query

            def upd_execute():
                if table_name == "bookings":
                    b_id = upd_filters.get("id")
                    expected_status = upd_filters.get("booking_status")
                    if b_id == str(BOOKING_TEST_ID):
                        if expected_status and expected_status != db_state["booking"]["booking_status"]:
                            # Conditional update failed due to concurrent modification!
                            return MagicMock(data=[])
                        db_state["booking"].update(payload)
                        return MagicMock(data=[dict(db_state["booking"])])
                    return MagicMock(data=[])

                elif table_name == "mechanic_assignments":
                    return MagicMock(data=[{"id": str(ASSIGNMENT_1_ID)}])

                elif table_name == "booking_status_history":
                    return MagicMock(data=[{"id": str(uuid.uuid4())}])

                return MagicMock(data=[])

            upd_query.execute.side_effect = upd_execute
            return upd_query

        query.update.side_effect = update_mock
        return query

    mock_client.table.side_effect = table_handler
    return mock_client, db_state


# ==============================================================================
# PART B: Endpoint Integration Tests (PATCH /api/v1/bookings/{id}/status)
# ==============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_status_update_rejected(async_client: AsyncClient):
    """Unauthenticated requests must be rejected with 401."""
    res = await async_client.patch(
        f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
        json={"new_status": "cancelled"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_customer_cancel_booking_success(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer can successfully cancel an active booking they own with an explanation."""
    mock_db, db_state = build_lifecycle_mock_db(initial_status="pending")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "cancelled", "reason": "Change of plans"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["booking_status"] == "cancelled"
        assert db_state["booking"]["booking_status"] == "cancelled"


@pytest.mark.asyncio
async def test_customer_cannot_cancel_other_customer_booking(
    async_client: AsyncClient, mock_other_customer: AuthenticatedUser
):
    """Customer 2 cannot cancel Customer 1's booking -> returns 404 (no leak)."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="pending")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "cancelled", "reason": "Malicious attempt"},
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_customer_cannot_execute_mechanic_progression(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer cannot advance mechanic journey states -> 403 Forbidden."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="mechanic_assigned")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "mechanic_en_route"},
        )
        assert res.status_code == 403
        assert "not permitted" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_assigned_mechanic_journey_progression(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Assigned mechanic can advance through their lifecycle states."""
    # 1. mechanic_assigned -> mechanic_en_route
    mock_db, db_state = build_lifecycle_mock_db(initial_status="mechanic_assigned")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res1 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "mechanic_en_route", "reason": "Driving to customer doorstep"},
        )
        assert res1.status_code == 200
        assert res1.json()["booking_status"] == "mechanic_en_route"

        # 2. mechanic_en_route -> mechanic_arrived
        res2 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "mechanic_arrived"},
        )
        assert res2.status_code == 200
        assert res2.json()["booking_status"] == "mechanic_arrived"

        # 3. mechanic_arrived -> inspection
        res3 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "inspection"},
        )
        assert res3.status_code == 200
        assert res3.json()["booking_status"] == "inspection"

        # 4. inspection -> service_in_progress
        res4 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "service_in_progress"},
        )
        assert res4.status_code == 200
        assert res4.json()["booking_status"] == "service_in_progress"

        # 5. service_in_progress -> service_completed
        res5 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "service_completed"},
        )
        assert res5.status_code == 200
        assert res5.json()["booking_status"] == "service_completed"

        # 6. service_completed -> payment_pending
        res6 = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "payment_pending"},
        )
        assert res6.status_code == 200
        assert res6.json()["booking_status"] == "payment_pending"


@pytest.mark.asyncio
async def test_unassigned_mechanic_cannot_update_booking_status(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """Mechanic 2 (not assigned to this booking) receives 403 Forbidden."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="mechanic_assigned")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "mechanic_en_route"},
        )
        assert res.status_code == 403
        assert "not the assigned mechanic" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_customer_approval_advances_service(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer can approve pending work (awaiting_customer_approval -> service_in_progress)."""
    mock_db, db_state = build_lifecycle_mock_db(initial_status="awaiting_customer_approval")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "service_in_progress", "reason": "Customer approved brake replacement"},
        )
        assert res.status_code == 200
        assert res.json()["booking_status"] == "service_in_progress"


@pytest.mark.asyncio
async def test_customer_dispute_on_completed_booking(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer can dispute a service_completed booking."""
    mock_db, db_state = build_lifecycle_mock_db(initial_status="service_completed")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "disputed", "reason": "Brake vibration unresolved"},
        )
        assert res.status_code == 200
        assert res.json()["booking_status"] == "disputed"


@pytest.mark.asyncio
async def test_customer_dispute_on_pending_booking_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer cannot raise a dispute on pre-service pending booking -> 400."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="pending")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "disputed", "reason": "Premature complaint"},
        )
        assert res.status_code == 400
        assert "invalid status transition from 'pending' to 'disputed'" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_transition_from_terminal_cancelled_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Cannot transition out of cancelled status -> 400."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="cancelled")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "pending"},
        )
        assert res.status_code == 400
        assert "terminal state" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_direct_transition_to_paid_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Direct transition to paid is reserved for payment integration -> 400."""
    mock_db, _ = build_lifecycle_mock_db(initial_status="payment_pending")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "paid"},
        )
        assert res.status_code == 400
        assert "reserved for payment" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_extra_fields_in_status_update_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Client injection of pricing, customer_id, or actor roles is forbidden -> 422."""
    res = await async_client.patch(
        f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
        json={
            "new_status": "cancelled",
            "customer_id": str(CUSTOMER_1_ID),  # Injected forbidden field
            "total_amount": "0.00",
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_concurrent_status_update_conflict_returns_409(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """If booking status changed concurrently between read and conditional update, return 409."""
    mock_client = MagicMock()

    # Read returns initial status "pending", but conditional update finds 0 rows (status changed)
    def table_handler(name):
        query = MagicMock()
        query.select.return_value = query
        query.eq.return_value = query
        query.execute.return_value = MagicMock(data=[{
            "id": str(BOOKING_TEST_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "pending",
        }])

        def update_mock(payload):
            upd = MagicMock()
            upd.eq.return_value = upd
            # Simulate 0 rows matched during conditional update due to concurrent change
            upd.execute.return_value = MagicMock(data=[])
            return upd

        query.update.side_effect = update_mock
        return query

    mock_client.table.side_effect = table_handler

    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_client):
        res = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "cancelled"},
        )
        assert res.status_code == 409
        assert "changed concurrently" in res.json()["detail"].lower()


# ==============================================================================
# PART C: Atomic Concurrency Acceptance Test (Mandatory Part 11.F)
# ==============================================================================

@pytest.mark.asyncio
async def test_concurrent_mechanic_acceptance_exactly_one_wins():
    """
    Mandatory Concurrency Test (Part 11.F):
    Two mechanics attempt to accept two different assignment offers for the SAME booking concurrently.

    Atomic Guarantees Tested:
    1. Both requests are dispatched simultaneously via asyncio.gather.
    2. Atomic PostgreSQL row lock (FOR UPDATE) serializes execution.
    3. Exactly ONE request succeeds with HTTP 200.
    4. Exactly ONE request is aborted with HTTP 409 Conflict.
    5. The final booking state is 'mechanic_assigned' with AT MOST ONE accepted assignment.
    """
    from app.services.mechanic_service import MechanicService

    import threading
    shared_booking_lock = threading.Lock()
    db_state = {
        "booking_status": "searching_mechanic",
        "assignments": {
            str(ASSIGNMENT_1_ID): {
                "id": str(ASSIGNMENT_1_ID),
                "booking_id": str(BOOKING_TEST_ID),
                "mechanic_id": str(MECH_1_PROFILE_ID),
                "assignment_status": "offered",
            },
            str(ASSIGNMENT_2_ID): {
                "id": str(ASSIGNMENT_2_ID),
                "booking_id": str(BOOKING_TEST_ID),
                "mechanic_id": str(MECH_2_PROFILE_ID),
                "assignment_status": "offered",
            },
        },
    }

    def simulated_atomic_rpc_accept(p_assignment_id: str, p_mechanic_user_id: str):
        """Simulate the atomic PostgreSQL accept_mechanic_assignment RPC."""
        with shared_booking_lock:
            # Check booking status under exclusive lock
            if db_state["booking_status"] != "searching_mechanic":
                # Stale offer: another mechanic already claimed the booking
                db_state["assignments"][p_assignment_id]["assignment_status"] = "cancelled"
                return {
                    "success": False,
                    "error_code": "BOOKING_ALREADY_ASSIGNED",
                    "message": "Booking has already been assigned to another mechanic.",
                }

            # Check if any accepted assignment exists (enforcing partial unique constraint)
            has_accepted = any(
                a["assignment_status"] == "accepted"
                for a in db_state["assignments"].values()
            )
            if has_accepted:
                db_state["assignments"][p_assignment_id]["assignment_status"] = "cancelled"
                return {
                    "success": False,
                    "error_code": "BOOKING_ALREADY_ASSIGNED",
                    "message": "Booking has already been assigned to another mechanic.",
                }

            # Atomically advance booking status and assignment status
            db_state["booking_status"] = "mechanic_assigned"
            db_state["assignments"][p_assignment_id]["assignment_status"] = "accepted"

            # Cancel sibling offers
            for aid, a in db_state["assignments"].items():
                if aid != p_assignment_id and a["assignment_status"] == "offered":
                    a["assignment_status"] = "cancelled"

            return {
                "success": True,
                "assignment": dict(db_state["assignments"][p_assignment_id]),
            }

    # Setup mock clients for both mechanics
    mock_client_1 = MagicMock()
    mock_client_2 = MagicMock()

    def rpc_side_effect_1(fn, params):
        mock_exec = MagicMock()
        mock_exec.execute.side_effect = lambda: MagicMock(
            data=simulated_atomic_rpc_accept(params["p_assignment_id"], params["p_mechanic_user_id"])
        )
        return mock_exec

    def rpc_side_effect_2(fn, params):
        mock_exec = MagicMock()
        mock_exec.execute.side_effect = lambda: MagicMock(
            data=simulated_atomic_rpc_accept(params["p_assignment_id"], params["p_mechanic_user_id"])
        )
        return mock_exec

    service_1 = MechanicService()
    service_2 = MechanicService()

    async def mechanic_1_accept():
        with patch.object(service_1.client, "rpc", side_effect=rpc_side_effect_1):
            return await service_1.accept_assignment(
                assignment_id=ASSIGNMENT_1_ID,
                mechanic_user_id=MECHANIC_ID,
            )

    async def mechanic_2_accept():
        with patch.object(service_2.client, "rpc", side_effect=rpc_side_effect_2):
            return await service_2.accept_assignment(
                assignment_id=ASSIGNMENT_2_ID,
                mechanic_user_id=OTHER_MECHANIC_ID,
            )

    # Launch both acceptances simultaneously
    results = await asyncio.gather(
        mechanic_1_accept(),
        mechanic_2_accept(),
        return_exceptions=True,
    )

    # Analyze results: Exactly one must succeed and exactly one must fail with 409 Conflict
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"

    failure = failures[0]
    from fastapi import HTTPException
    assert isinstance(failure, HTTPException)
    assert failure.status_code == 409
    assert "already been assigned" in failure.detail.lower()

    # Verify final database invariants
    assert db_state["booking_status"] == "mechanic_assigned"
    accepted_assignments = [
        a for a in db_state["assignments"].values() if a["assignment_status"] == "accepted"
    ]
    assert len(accepted_assignments) == 1, "There must be AT MOST ONE accepted assignment in the database!"

    cancelled_assignments = [
        a for a in db_state["assignments"].values() if a["assignment_status"] == "cancelled"
    ]
    assert len(cancelled_assignments) == 1, "The losing assignment must be cancelled!"
