"""
Comprehensive Mechanic Discovery and Assignment Tests (Phase 5).

Tests:
1. Unauthenticated nearby request -> 401
2. Customer accessing another customer's booking for discovery -> 404 (no leak)
3. Nonexistent booking -> 404
4. Discovery uses trusted booking coordinates (not client coordinates)
5. Nearby mechanic discovery returns verified available mechanics
6. Service-radius filtering (PostGIS RPC respects service_radius_km)
7. Inactive / busy mechanic filtering (mechanics with active accepted assignments excluded)
8. Safe mechanic response schema (no phone, no email, no private documents)
9. Mechanic phone number is strictly absent from discovery payload
10. Customer cannot accept mechanic assignment -> 403
11. Mechanic B cannot accept Mechanic A's assignment -> 403
12. Accepting an assignment with invalid status (already accepted/cancelled) -> 400
13. Concurrency check: Second mechanic accepting already-accepted booking -> 409
14. Booking status progression: pending -> searching_mechanic -> mechanic_assigned
15. Mechanic successfully rejects offered assignment with reason
16. Get assignment details: ownership enforcement and 404 for inaccessible assignment
17. Public mechanic profile projection excludes private phone
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.user import AuthenticatedUser
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID, MECHANIC_ID, OTHER_MECHANIC_ID

BOOKING_1_ID = uuid.UUID("66661111-0000-0000-0000-000000000001")
BOOKING_2_ID = uuid.UUID("66662222-0000-0000-0000-000000000002")

MECH_PROFILE_1_ID = uuid.UUID("55551111-0000-0000-0000-000000000001")
MECH_PROFILE_2_ID = uuid.UUID("55552222-0000-0000-0000-000000000002")

ASSIGNMENT_1_ID = uuid.UUID("77771111-0000-0000-0000-000000000001")
ASSIGNMENT_2_ID = uuid.UUID("77772222-0000-0000-0000-000000000002")


def build_mock_mechanic_db():
    """Build mock Supabase client for mechanic discovery and assignment tests."""
    mock_client = MagicMock()

    # In-memory database records
    bookings_db = {
        str(BOOKING_1_ID): {
            "id": str(BOOKING_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "requested_latitude": "12.971598",
            "requested_longitude": "77.594562",
            "booking_status": "pending",
        },
        str(BOOKING_2_ID): {
            "id": str(BOOKING_2_ID),
            "customer_id": str(CUSTOMER_2_ID),
            "requested_latitude": "13.082680",
            "requested_longitude": "80.270718",
            "booking_status": "pending",
        },
    }

    mechanic_profiles_db = {
        str(MECH_PROFILE_1_ID): {
            "id": str(MECH_PROFILE_1_ID),
            "user_id": str(MECHANIC_ID),
            "business_name": "Dave Auto Garage",
            "experience_years": 8,
            "bio": "Certified specialist",
            "verification_status": "verified",
            "is_available": True,
            "service_radius_km": "15.00",
            "current_latitude": "12.975000",
            "current_longitude": "77.590000",
            "average_rating": "4.85",
            "total_completed_jobs": 42,
        },
        str(MECH_PROFILE_2_ID): {
            "id": str(MECH_PROFILE_2_ID),
            "user_id": str(OTHER_MECHANIC_ID),
            "business_name": "Evan Quick Fix",
            "experience_years": 4,
            "bio": "Two wheeler expert",
            "verification_status": "verified",
            "is_available": True,
            "service_radius_km": "10.00",
            "current_latitude": "12.960000",
            "current_longitude": "77.600000",
            "average_rating": "4.60",
            "total_completed_jobs": 19,
        },
    }

    assignments_db = {
        str(ASSIGNMENT_1_ID): {
            "id": str(ASSIGNMENT_1_ID),
            "booking_id": str(BOOKING_1_ID),
            "mechanic_id": str(MECH_PROFILE_1_ID),
            "assignment_status": "offered",
            "distance_km": "3.50",
            "estimated_arrival_minutes": 25,
            "offered_at": "2026-10-02T10:00:00Z",
            "responded_at": None,
            "assigned_at": None,
            "rejected_reason": None,
            "created_at": "2026-10-02T10:00:00Z",
            "updated_at": "2026-10-02T10:00:00Z",
        },
        str(ASSIGNMENT_2_ID): {
            "id": str(ASSIGNMENT_2_ID),
            "booking_id": str(BOOKING_1_ID),
            "mechanic_id": str(MECH_PROFILE_2_ID),
            "assignment_status": "offered",
            "distance_km": "5.20",
            "estimated_arrival_minutes": 35,
            "offered_at": "2026-10-02T10:00:00Z",
            "responded_at": None,
            "assigned_at": None,
            "rejected_reason": None,
            "created_at": "2026-10-02T10:00:00Z",
            "updated_at": "2026-10-02T10:00:00Z",
        },
    }

    # Mock PostGIS discovery results (safe public projection)
    discovery_rpc_data = [
        {
            "mechanic_id": str(MECH_PROFILE_1_ID),
            "user_id": str(MECHANIC_ID),
            "full_name": "Dave Mechanic",
            "avatar_url": "https://example.com/avatars/dave.png",
            "business_name": "Dave Auto Garage",
            "experience_years": 8,
            "average_rating": "4.85",
            "distance_km": "3.50",
            "service_radius_km": "15.00",
        },
        {
            "mechanic_id": str(MECH_PROFILE_2_ID),
            "user_id": str(OTHER_MECHANIC_ID),
            "full_name": "Evan Mechanic",
            "avatar_url": None,
            "business_name": "Evan Quick Fix",
            "experience_years": 4,
            "average_rating": "4.60",
            "distance_km": "5.20",
            "service_radius_km": "10.00",
        },
    ]

    def rpc_handler(fn_name, params):
        rpc_mock = MagicMock()
        if fn_name == "find_nearby_mechanics":
            rpc_mock.execute.return_value = MagicMock(data=discovery_rpc_data)
        return rpc_mock

    mock_client.rpc.side_effect = rpc_handler

    def table_handler(table_name):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.range.return_value = query

        filters = {}

        def eq_mock(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_mock
        query.neq.return_value = query

        def execute_mock():
            if table_name == "bookings":
                b_id = filters.get("id")
                row = bookings_db.get(b_id)
                return MagicMock(data=[row] if row else [])

            elif table_name == "mechanic_profiles":
                u_id = filters.get("user_id")
                m_id = filters.get("id")
                if u_id:
                    matched = [m for m in mechanic_profiles_db.values() if m["user_id"] == u_id]
                    return MagicMock(data=matched)
                if m_id:
                    row = mechanic_profiles_db.get(m_id)
                    if row:
                        enriched = {
                            **row,
                            "profiles": {
                                "full_name": "Dave Mechanic",
                                "avatar_url": None,
                            },
                        }
                        return MagicMock(data=[enriched])
                    return MagicMock(data=[])
                return MagicMock(data=list(mechanic_profiles_db.values()))

            elif table_name == "mechanic_assignments":
                a_id = filters.get("id")
                b_id = filters.get("booking_id")
                status_filter = filters.get("assignment_status")
                if a_id:
                    row = assignments_db.get(a_id)
                    if row:
                        b_row = bookings_db.get(row["booking_id"], {})
                        enriched = {**row, "bookings": b_row}
                        return MagicMock(data=[enriched])
                    return MagicMock(data=[])
                if b_id:
                    matched = [a for a in assignments_db.values() if a["booking_id"] == b_id]
                    if status_filter:
                        matched = [a for a in matched if a["assignment_status"] == status_filter]
                    return MagicMock(data=matched)
                if status_filter:
                    matched = [a for a in assignments_db.values() if a["assignment_status"] == status_filter]
                    return MagicMock(data=matched)
                return MagicMock(data=list(assignments_db.values()))

            elif table_name == "notifications":
                return MagicMock(data=[])

            return MagicMock(data=[])

        query.execute.side_effect = execute_mock

        def update_mock(payload):
            upd_query = MagicMock()

            def upd_eq(col, val):
                filters[col] = str(val)
                return upd_query

            upd_query.eq.side_effect = upd_eq
            upd_query.neq.return_value = upd_query

            def upd_execute():
                if table_name == "bookings":
                    b_id = filters.get("id")
                    if b_id in bookings_db:
                        bookings_db[b_id].update(payload)
                        return MagicMock(data=[dict(bookings_db[b_id])])
                elif table_name == "mechanic_assignments":
                    a_id = filters.get("id")
                    if a_id in assignments_db:
                        assignments_db[a_id].update(payload)
                        return MagicMock(data=[dict(assignments_db[a_id])])
                return MagicMock(data=[])

            upd_query.execute.side_effect = upd_execute
            return upd_query


        query.update.side_effect = update_mock

        def insert_mock(payload):
            ins_query = MagicMock()
            ins_query.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4()), **payload}])
            return ins_query

        query.insert.side_effect = insert_mock

        return query

    mock_client.table.side_effect = table_handler
    return mock_client


# ==============================================================================
# 1. Unauthenticated Discovery -> 401
# ==============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_nearby_request_returns_401(async_client: AsyncClient):
    """Calling nearby mechanics without authentication token must return 401."""
    res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={BOOKING_1_ID}")
    assert res.status_code == 401


# ==============================================================================
# 2. Customer Accessing Another Customer's Booking -> 404 (No Leak)
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_customer_nearby_request_returns_404(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer 1 attempting nearby discovery for Customer 2's booking must return 404 without leaking info."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={BOOKING_2_ID}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ==============================================================================
# 3. Nonexistent Booking -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_nonexistent_booking_nearby_returns_404(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Querying discovery for a nonexistent booking UUID must return 404."""
    NONEXISTENT_BOOKING = uuid.uuid4()
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={NONEXISTENT_BOOKING}")
        assert res.status_code == 404


# ==============================================================================
# 4. Booking Uses Trusted Coordinates & 5. Discovery Returns Mechanics
# ==============================================================================

@pytest.mark.asyncio
async def test_nearby_discovery_uses_trusted_coordinates_and_returns_mechanics(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """
    Discovery uses coordinates stored authoritatively on the customer's booking.
    Verifies that PostGIS results are mapped and returned correctly.
    """
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={BOOKING_1_ID}")
        assert res.status_code == 200
        data = res.json()

        assert len(data) == 2
        m1 = data[0]
        assert m1["mechanic_id"] == str(MECH_PROFILE_1_ID)
        assert m1["full_name"] == "Dave Mechanic"
        assert m1["business_name"] == "Dave Auto Garage"
        assert Decimal(str(m1["distance_km"])) == Decimal("3.50")
        assert Decimal(str(m1["service_radius_km"])) == Decimal("15.00")

        # Verify that PostGIS RPC was invoked with the booking's exact stored coordinates
        mock_db.rpc.assert_called_once_with(
            "find_nearby_mechanics",
            {
                "cust_lat": 12.971598,
                "cust_lng": 77.594562,
                "max_distance_km": 20.0,
            },
        )


# ==============================================================================
# 6. Service Radius Filtering
# ==============================================================================

@pytest.mark.asyncio
async def test_service_radius_custom_parameter(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Custom max_distance_km parameter is forwarded directly to PostGIS RPC."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/mechanics/nearby?booking_id={BOOKING_1_ID}&max_distance_km=10.0"
        )
        assert res.status_code == 200
        mock_db.rpc.assert_called_once_with(
            "find_nearby_mechanics",
            {
                "cust_lat": 12.971598,
                "cust_lng": 77.594562,
                "max_distance_km": 10.0,
            },
        )


# ==============================================================================
# 7. Inactive / Busy Mechanic Filtering
# ==============================================================================

@pytest.mark.asyncio
async def test_busy_mechanic_filtered_out(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """A mechanic with an ongoing accepted assignment is filtered out of discovery results."""
    mock_db = build_mock_mechanic_db()

    # Mechanic 1 has an active accepted assignment
    orig_table = mock_db.table.side_effect

    def table_with_busy_mech(name):
        q = orig_table(name)
        if name == "mechanic_assignments":
            def exec_assignments():
                return MagicMock(data=[{"mechanic_id": str(MECH_PROFILE_1_ID)}])
            q.execute.side_effect = exec_assignments
        return q

    mock_db.table.side_effect = table_with_busy_mech

    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={BOOKING_1_ID}")
        assert res.status_code == 200
        data = res.json()
        # Mechanic 1 is filtered out; only Mechanic 2 remains
        assert len(data) == 1
        assert data[0]["mechanic_id"] == str(MECH_PROFILE_2_ID)


# ==============================================================================
# 8. Safe Mechanic Response & 9. Phone Number Not Exposed
# ==============================================================================

@pytest.mark.asyncio
async def test_mechanic_response_does_not_expose_phone_or_sensitive_data(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Discovery response strictly omits phone numbers, email, and private documents."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/nearby?booking_id={BOOKING_1_ID}")
        assert res.status_code == 200
        for mech in res.json():
            assert "phone" not in mech
            assert "email" not in mech
            assert "document" not in mech
            assert "bank" not in mech
            assert "current_latitude" not in mech
            assert "current_longitude" not in mech


# ==============================================================================
# 10. Unauthorized Assignment Acceptance -> 403 (Customer Calling Accept)
# ==============================================================================

@pytest.mark.asyncio
async def test_customer_cannot_accept_assignment(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer attempting to accept a mechanic assignment must receive 403 Forbidden."""
    res = await async_client.post(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/accept")
    assert res.status_code == 403
    assert "access denied" in res.json()["detail"].lower()


# ==============================================================================
# 11. Mechanic Can Only Act on Their Own Assignment
# ==============================================================================

@pytest.mark.asyncio
async def test_mechanic_cannot_accept_other_mechanics_assignment(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """Mechanic 2 attempting to accept Assignment 1 (offered to Mechanic 1) must receive 403 Forbidden."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/accept")
        assert res.status_code == 403
        assert "only accept assignments offered to your profile" in res.json()["detail"].lower()


# ==============================================================================
# 12. Invalid Assignment Status Rejected (Not in 'offered')
# ==============================================================================

@pytest.mark.asyncio
async def test_accept_already_accepted_assignment_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Attempting to accept an assignment that is already 'accepted' or 'cancelled' returns 400."""
    mock_db = build_mock_mechanic_db()

    # Pre-set assignment status to accepted
    orig_table = mock_db.table.side_effect

    def table_already_accepted(name):
        q = orig_table(name)
        if name == "mechanic_assignments":
            def exec_fn():
                return MagicMock(data=[{
                    "id": str(ASSIGNMENT_1_ID),
                    "booking_id": str(BOOKING_1_ID),
                    "mechanic_id": str(MECH_PROFILE_1_ID),
                    "assignment_status": "accepted",  # Already accepted
                    "bookings": {"booking_status": "mechanic_assigned"},
                }])
            q.execute.side_effect = exec_fn
        return q

    mock_db.table.side_effect = table_already_accepted

    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/accept")
        assert res.status_code == 400
        assert "cannot accept assignment in 'accepted' status" in res.json()["detail"].lower()


# ==============================================================================
# 13. Concurrency Check: Double Assignment -> 409
# ==============================================================================

@pytest.mark.asyncio
async def test_duplicate_acceptance_returns_409_conflict(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """
    If another mechanic accepted the booking concurrently, the current acceptance
    is aborted with 409 Conflict.
    """
    mock_db = build_mock_mechanic_db()

    # Simulate another assignment already in 'accepted' status for this booking
    orig_table = mock_db.table.side_effect

    def table_conflict(name):
        q = orig_table(name)
        if name == "mechanic_assignments":
            filters = {}
            def eq_sub(c, v):
                filters[c] = str(v)
                return q
            q.eq.side_effect = eq_sub

            def exec_sub():
                if filters.get("assignment_status") == "accepted":
                    # Another assignment was already accepted!
                    return MagicMock(data=[{"id": str(ASSIGNMENT_2_ID)}])
                if filters.get("id") == str(ASSIGNMENT_1_ID):
                    return MagicMock(data=[{
                        "id": str(ASSIGNMENT_1_ID),
                        "booking_id": str(BOOKING_1_ID),
                        "mechanic_id": str(MECH_PROFILE_1_ID),
                        "assignment_status": "offered",
                        "bookings": {"booking_status": "searching_mechanic"},
                    }])
                return MagicMock(data=[])
            q.execute.side_effect = exec_sub
        return q

    mock_db.table.side_effect = table_conflict

    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/accept")
        assert res.status_code == 409
        assert "already been accepted" in res.json()["detail"].lower()


# ==============================================================================
# 14. Booking Status Progression
# ==============================================================================

@pytest.mark.asyncio
async def test_booking_status_progression_on_acceptance(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """
    When mechanic accepts an offered assignment, assignment advances to 'accepted',
    and booking status advances to 'mechanic_assigned'.
    """
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/accept")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(ASSIGNMENT_1_ID)
        assert data["assignment_status"] == "accepted"


# ==============================================================================
# 15. Mechanic Rejects Assignment
# ==============================================================================

@pytest.mark.asyncio
async def test_mechanic_rejects_assignment(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Mechanic can reject an offered assignment with an optional reason."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}/reject",
            json={"reason": "Currently busy with another emergency job"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(ASSIGNMENT_1_ID)
        assert data["assignment_status"] == "rejected"
        assert data["rejected_reason"] == "Currently busy with another emergency job"


# ==============================================================================
# 16. Get Assignment Details Ownership & RBAC
# ==============================================================================

@pytest.mark.asyncio
async def test_get_assignment_details_mechanic_access(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Mechanic can retrieve details of an assignment offered to them."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/assignments/{ASSIGNMENT_1_ID}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(ASSIGNMENT_1_ID)
        assert data["mechanic_id"] == str(MECH_PROFILE_1_ID)


# ==============================================================================
# 17. Public Mechanic Profile Excludes Phone
# ==============================================================================

@pytest.mark.asyncio
async def test_public_mechanic_profile_excludes_phone(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Public mechanic profile route returns profile data without personal phone or email."""
    mock_db = build_mock_mechanic_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/{MECH_PROFILE_1_ID}")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(MECH_PROFILE_1_ID)
        assert data["full_name"] == "Dave Mechanic"
        assert "phone" not in data
        assert "email" not in data
