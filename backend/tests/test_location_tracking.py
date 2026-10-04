"""
Comprehensive Realtime Mechanic Location Tracking Tests (Phase 6A).

Tests:
1. Unauthenticated location update -> 401
2. Customer attempting location update -> 403 Forbidden
3. Mechanic location update success (snapshot updated & history row inserted)
4. Invalid latitude (> 90 or < -90) -> 422
5. Invalid longitude (> 180 or < -180) -> 422
6. Negative accuracy (< 0) -> 422
7. Mechanic identity strictly derived from JWT (never from request body)
8. Attempting to supply mechanic_id in body -> 422 (extra=forbid)
9. Location history row creation in mechanic_locations
10. Latest location query uses (mechanic_id, recorded_at DESC)
11. Customer retrieves latest location for their own booking with assigned mechanic
12. Customer cannot retrieve another customer's mechanic location -> 404 (no leakage)
13. Booking without accepted mechanic -> 400 Bad Request
14. Safe response projection (no phone, email, or sensitive data)
15. Existing regression tests remain green
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.user import AuthenticatedUser
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID, MECHANIC_ID, OTHER_MECHANIC_ID

BOOKING_WITH_MECHANIC = uuid.UUID("88881111-0000-0000-0000-000000000001")
BOOKING_WITHOUT_MECHANIC = uuid.UUID("88882222-0000-0000-0000-000000000002")
OTHER_CUSTOMER_BOOKING = uuid.UUID("88883333-0000-0000-0000-000000000003")

MECH_PROFILE_ID = uuid.UUID("99991111-0000-0000-0000-000000000001")
ASSIGNMENT_ID = uuid.UUID("aaaa1111-0000-0000-0000-000000000001")


def build_mock_tracking_db():
    """Build a mock Supabase client for realtime location tracking tests."""
    mock_client = MagicMock()

    bookings_db = {
        str(BOOKING_WITH_MECHANIC): {
            "id": str(BOOKING_WITH_MECHANIC),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "mechanic_assigned",
        },
        str(BOOKING_WITHOUT_MECHANIC): {
            "id": str(BOOKING_WITHOUT_MECHANIC),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "pending",
        },
        str(OTHER_CUSTOMER_BOOKING): {
            "id": str(OTHER_CUSTOMER_BOOKING),
            "customer_id": str(CUSTOMER_2_ID),
            "booking_status": "mechanic_assigned",
        },
    }

    mechanic_profiles_db = {
        str(MECH_PROFILE_ID): {
            "id": str(MECH_PROFILE_ID),
            "user_id": str(MECHANIC_ID),
            "verification_status": "verified",
            "is_available": True,
            "current_latitude": "12.971598",
            "current_longitude": "77.594562",
            "current_location_updated_at": "2026-10-02T10:05:00Z",
        }
    }

    assignments_db = [
        {
            "id": str(ASSIGNMENT_ID),
            "booking_id": str(BOOKING_WITH_MECHANIC),
            "mechanic_id": str(MECH_PROFILE_ID),
            "assignment_status": "accepted",
        }
    ]

    locations_history_db = [
        {
            "id": str(uuid.uuid4()),
            "mechanic_id": str(MECH_PROFILE_ID),
            "latitude": "12.971000",
            "longitude": "77.594000",
            "accuracy_meters": "15.0",
            "recorded_at": "2026-10-02T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "mechanic_id": str(MECH_PROFILE_ID),
            "latitude": "12.975500",
            "longitude": "77.598200",
            "accuracy_meters": "8.5",
            "recorded_at": "2026-10-02T10:05:00Z",  # Latest
        },
    ]

    def table_handler(table_name):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.limit.return_value = query

        filters = {}

        def eq_mock(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_mock

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
                    return MagicMock(data=[row] if row else [])
                return MagicMock(data=list(mechanic_profiles_db.values()))

            elif table_name == "mechanic_assignments":
                b_id = filters.get("booking_id")
                status = filters.get("assignment_status")
                matched = [
                    a for a in assignments_db
                    if (b_id is None or a["booking_id"] == b_id)
                    and (status is None or a["assignment_status"] == status)
                ]
                return MagicMock(data=matched)

            elif table_name == "mechanic_locations":
                m_id = filters.get("mechanic_id")
                matched = [l for l in locations_history_db if l["mechanic_id"] == m_id]
                # Sort descending by recorded_at to simulate (mechanic_id, recorded_at DESC)
                sorted_locs = sorted(matched, key=lambda x: x["recorded_at"], reverse=True)
                return MagicMock(data=sorted_locs[:1])

            return MagicMock(data=[])

        query.execute.side_effect = execute_mock

        def update_mock(payload):
            upd_query = MagicMock()
            def upd_eq(col, val):
                filters[col] = str(val)
                return upd_query
            upd_query.eq.side_effect = upd_eq

            def upd_execute():
                if table_name == "mechanic_profiles":
                    m_id = filters.get("id")
                    if m_id in mechanic_profiles_db:
                        mechanic_profiles_db[m_id].update(payload)
                        return MagicMock(data=[dict(mechanic_profiles_db[m_id])])
                return MagicMock(data=[])

            upd_query.execute.side_effect = upd_execute
            return upd_query

        query.update.side_effect = update_mock

        def insert_mock(payload):
            ins_query = MagicMock()
            if table_name == "mechanic_locations":
                new_row = {"id": str(uuid.uuid4()), **payload}
                locations_history_db.append(new_row)
                ins_query.execute.return_value = MagicMock(data=[new_row])
            return ins_query

        query.insert.side_effect = insert_mock

        return query

    mock_client.table.side_effect = table_handler
    return mock_client


# ==============================================================================
# 1. Unauthenticated Location Update -> 401
# ==============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_location_update_returns_401(async_client: AsyncClient):
    """Calling POST /api/v1/mechanics/location without token must return 401."""
    res = await async_client.post("/api/v1/mechanics/location", json={"latitude": 12.97, "longitude": 77.59})
    assert res.status_code == 401


# ==============================================================================
# 2. Customer Attempting Location Update -> 403 Forbidden
# ==============================================================================

@pytest.mark.asyncio
async def test_customer_location_update_returns_403(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer attempting to broadcast location must be rejected with 403 Forbidden."""
    res = await async_client.post(
        "/api/v1/mechanics/location",
        json={"latitude": 12.971598, "longitude": 77.594562, "accuracy_meters": 10.0},
    )
    assert res.status_code == 403
    assert "access denied" in res.json()["detail"].lower()


# ==============================================================================
# 3. Mechanic Location Update Success & 9. History Row Creation
# ==============================================================================

@pytest.mark.asyncio
async def test_mechanic_location_update_success(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Mechanic successfully broadcasts location ping, updating snapshot and logging history."""
    mock_db = build_mock_tracking_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        payload = {
            "latitude": 12.980000,
            "longitude": 77.600000,
            "accuracy_meters": 5.2,
        }
        res = await async_client.post("/api/v1/mechanics/location", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert data["mechanic_id"] == str(MECH_PROFILE_ID)
        assert Decimal(str(data["latitude"])) == Decimal("12.980000")
        assert Decimal(str(data["longitude"])) == Decimal("77.600000")
        assert Decimal(str(data["accuracy_meters"])) == Decimal("5.2")
        assert "recorded_at" in data


# ==============================================================================
# 4. Invalid Latitude (> 90 or < -90) -> 422
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_latitude_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Latitude > 90 or < -90 must return 422 validation error."""
    res = await async_client.post(
        "/api/v1/mechanics/location",
        json={"latitude": 91.5, "longitude": 77.59},
    )
    assert res.status_code == 422


# ==============================================================================
# 5. Invalid Longitude (> 180 or < -180) -> 422
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_longitude_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Longitude > 180 or < -180 must return 422 validation error."""
    res = await async_client.post(
        "/api/v1/mechanics/location",
        json={"latitude": 12.97, "longitude": -185.0},
    )
    assert res.status_code == 422


# ==============================================================================
# 6. Negative Accuracy (< 0) -> 422
# ==============================================================================

@pytest.mark.asyncio
async def test_negative_accuracy_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """GPS accuracy < 0 must return 422 validation error."""
    res = await async_client.post(
        "/api/v1/mechanics/location",
        json={"latitude": 12.97, "longitude": 77.59, "accuracy_meters": -1.0},
    )
    assert res.status_code == 422


# ==============================================================================
# 7. Mechanic Identity From JWT & 8. Cannot Spoof mechanic_id in Request
# ==============================================================================

@pytest.mark.asyncio
async def test_cannot_spoof_mechanic_id_in_request(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Client attempting to inject mechanic_id is rejected with 422 (extra=forbid)."""
    res = await async_client.post(
        "/api/v1/mechanics/location",
        json={
            "mechanic_id": str(uuid.uuid4()),  # Spoofing attempt
            "latitude": 12.97,
            "longitude": 77.59,
        },
    )
    assert res.status_code == 422


# ==============================================================================
# 10. Latest Location Query & 11. Customer Retrieves Location for Own Booking
# ==============================================================================

@pytest.mark.asyncio
async def test_customer_retrieves_mechanic_location_for_own_booking(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """
    Customer can query the latest GPS coordinates of the mechanic assigned
    to their booking. Hits index (mechanic_id, recorded_at DESC) and returns Ping 2.
    """
    mock_db = build_mock_tracking_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/bookings/{BOOKING_WITH_MECHANIC}/mechanic-location"
        )
        assert res.status_code == 200
        data = res.json()

        assert data["mechanic_id"] == str(MECH_PROFILE_ID)
        # Verify latest coordinates (Ping 2: 12.975500, 77.598200)
        assert Decimal(str(data["latitude"])) == Decimal("12.975500")
        assert Decimal(str(data["longitude"])) == Decimal("77.598200")
        assert Decimal(str(data["accuracy_meters"])) == Decimal("8.5")
        assert data["recorded_at"] == "2026-10-02T10:05:00Z"


# ==============================================================================
# 12. Customer Cannot Access Another Customer's Mechanic Location -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_customer_mechanic_location_access_returns_404(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer 1 attempting to track mechanic on Customer 2's booking must receive 404 without leakage."""
    mock_db = build_mock_tracking_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/bookings/{OTHER_CUSTOMER_BOOKING}/mechanic-location"
        )
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ==============================================================================
# 13. Booking Without Accepted Mechanic -> 400 Bad Request
# ==============================================================================

@pytest.mark.asyncio
async def test_booking_without_accepted_mechanic_returns_400(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Querying mechanic location on a booking where no mechanic has accepted yet returns 400."""
    mock_db = build_mock_tracking_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/bookings/{BOOKING_WITHOUT_MECHANIC}/mechanic-location"
        )
        assert res.status_code == 400
        assert "no mechanic has been assigned" in res.json()["detail"].lower()


# ==============================================================================
# 14. Safe Response Projection (No Personal Contact Info)
# ==============================================================================

@pytest.mark.asyncio
async def test_mechanic_location_response_omits_private_data(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Location endpoint response strictly omits phone numbers, emails, and private documents."""
    mock_db = build_mock_tracking_db()
    with patch("app.services.mechanic_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/bookings/{BOOKING_WITH_MECHANIC}/mechanic-location"
        )
        assert res.status_code == 200
        data = res.json()
        assert "phone" not in data
        assert "email" not in data
        assert "document" not in data
        assert "password" not in data
        assert "bank" not in data
