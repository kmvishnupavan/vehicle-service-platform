"""
Comprehensive Phase 7 Tests: Inspections, Additional Work, Customer Approval, and Concurrency.

Covers:
PHASE 7A: Inspections (Tests 1-9)
1. mechanic creates inspection
2. non-mechanic rejected
3. wrong mechanic rejected
4. wrong booking rejected
5. customer can read own booking inspection
6. unrelated customer rejected
7. duplicate inspection rejected
8. invalid negative estimated cost rejected
9. PATCH cannot change booking_id/mechanic_id

PHASE 7B: Additional Work (Tests 10-17)
10. mechanic creates request
11. wrong mechanic rejected
12. unrelated mechanic rejected
13. customer can read own request
14. unrelated customer rejected
15. negative price rejected
16. invalid evidence path rejected
17. booking lifecycle enforced

PHASE 7C: Customer Response (Tests 18-32)
18. customer approves request
19. request becomes approved
20. additional_charges updated
21. tax recalculated
22. total recalculated
23. booking becomes service_in_progress
24. customer rejects request
25. no financial amount changes on rejection
26. mechanic cannot approve
27. unrelated customer cannot approve
28. already-approved request rejected
29. already-rejected request rejected
30. cancelled booking cannot be approved
31. duplicate/concurrent approval only succeeds once
32. concurrent approve vs reject only one succeeds
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import threading
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.user import AuthenticatedUser
from tests.conftest import (
    CUSTOMER_1_ID,
    CUSTOMER_2_ID,
    MECHANIC_ID,
    OTHER_MECHANIC_ID,
)

BOOKING_TEST_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_BOOKING_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000002")

MECH_1_PROFILE_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
MECH_2_PROFILE_ID = uuid.UUID("cccccccc-0000-0000-0000-000000000002")

INSPECTION_TEST_ID = uuid.UUID("dddddddd-0000-0000-0000-000000000001")
REQUEST_TEST_ID = uuid.UUID("eeeeeeee-0000-0000-0000-000000000001")


def build_phase7_mock_db(
    booking_status: str = "inspection",
    has_inspection: bool = False,
    request_status: str = "pending",
    subtotal: str = "1000.00",
    additional_charges: str = "0.00",
    tax_amount: str = "180.00",
    total_amount: str = "1180.00",
    request_price: str = "500.00",
):
    """Construct in-memory database mock for Phase 7 testing."""
    mock_client = MagicMock()

    db_state = {
        "bookings": {
            str(BOOKING_TEST_ID): {
                "id": str(BOOKING_TEST_ID),
                "customer_id": str(CUSTOMER_1_ID),
                "booking_status": booking_status,
                "subtotal": subtotal,
                "additional_charges": additional_charges,
                "discount_amount": "0.00",
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "created_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
            }
        },
        "mechanic_profiles": {
            str(MECHANIC_ID): {"id": str(MECH_1_PROFILE_ID), "user_id": str(MECHANIC_ID)},
            str(OTHER_MECHANIC_ID): {"id": str(MECH_2_PROFILE_ID), "user_id": str(OTHER_MECHANIC_ID)},
        },
        "mechanic_assignments": [
            {
                "id": str(uuid.uuid4()),
                "booking_id": str(BOOKING_TEST_ID),
                "mechanic_id": str(MECH_1_PROFILE_ID),
                "assignment_status": "accepted",
            }
        ],
        "service_inspections": {},
        "additional_work_requests": {
            str(REQUEST_TEST_ID): {
                "id": str(REQUEST_TEST_ID),
                "booking_id": str(BOOKING_TEST_ID),
                "mechanic_id": str(MECH_1_PROFILE_ID),
                "title": "Brake Pad Replacement",
                "description": "Front brake pads worn down to 1mm.",
                "price": request_price,
                "evidence_file_paths": [f"{BOOKING_TEST_ID}/additional_work/brake_pad.jpg"],
                "status": request_status,
                "customer_response": None,
                "responded_at": None,
                "created_at": "2026-10-02T11:00:00Z",
                "updated_at": "2026-10-02T11:00:00Z",
            }
        },
    }

    if has_inspection:
        db_state["service_inspections"][str(BOOKING_TEST_ID)] = {
            "id": str(INSPECTION_TEST_ID),
            "booking_id": str(BOOKING_TEST_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "findings": "Oil filter degraded, brake pads worn.",
            "vehicle_condition": "Fair, needs immediate brake service.",
            "estimated_additional_cost": "500.00",
            "created_at": "2026-10-02T10:30:00Z",
            "updated_at": "2026-10-02T10:30:00Z",
        }

    def table_handler(table_name: str):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.limit.return_value = query

        filters = {}

        def eq_mock(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_mock
        query.in_.return_value = query

        def execute_mock():
            if table_name == "bookings":
                b_id = filters.get("id")
                if b_id in db_state["bookings"]:
                    b = db_state["bookings"][b_id]
                    if "booking_status" in filters and filters["booking_status"] != b["booking_status"]:
                        return MagicMock(data=[])
                    return MagicMock(data=[dict(b)])
                return MagicMock(data=[])

            elif table_name == "mechanic_profiles":
                u_id = filters.get("user_id")
                if u_id in db_state["mechanic_profiles"]:
                    return MagicMock(data=[dict(db_state["mechanic_profiles"][u_id])])
                return MagicMock(data=[])

            elif table_name == "mechanic_assignments":
                b_id = filters.get("booking_id")
                m_id = filters.get("mechanic_id")
                status_filter = filters.get("assignment_status")
                matching = [
                    dict(a) for a in db_state["mechanic_assignments"]
                    if (not b_id or a["booking_id"] == b_id)
                    and (not m_id or a["mechanic_id"] == m_id)
                    and (not status_filter or a["assignment_status"] == status_filter)
                ]
                return MagicMock(data=matching)

            elif table_name == "service_inspections":
                b_id = filters.get("booking_id")
                if b_id and b_id in db_state["service_inspections"]:
                    return MagicMock(data=[dict(db_state["service_inspections"][b_id])])
                return MagicMock(data=[])

            elif table_name == "additional_work_requests":
                r_id = filters.get("id")
                b_id = filters.get("booking_id")
                if r_id and r_id in db_state["additional_work_requests"]:
                    r = db_state["additional_work_requests"][r_id]
                    if b_id and r["booking_id"] != b_id:
                        return MagicMock(data=[])
                    return MagicMock(data=[dict(r)])
                elif b_id:
                    matching = [
                        dict(r) for r in db_state["additional_work_requests"].values()
                        if r["booking_id"] == b_id
                    ]
                    return MagicMock(data=matching)
                return MagicMock(data=[])

            return MagicMock(data=[])

        query.execute.side_effect = execute_mock

        def insert_mock(payload):
            ins_query = MagicMock()
            if table_name == "service_inspections":
                rec = {
                    "id": str(INSPECTION_TEST_ID),
                    "created_at": "2026-10-02T10:30:00Z",
                    "updated_at": "2026-10-02T10:30:00Z",
                    **payload,
                }
                db_state["service_inspections"][payload["booking_id"]] = rec
                ins_query.execute.return_value = MagicMock(data=[dict(rec)])
            elif table_name == "additional_work_requests":
                rec_id = str(uuid.uuid4())
                rec = {
                    "id": rec_id,
                    "created_at": "2026-10-02T11:00:00Z",
                    "updated_at": "2026-10-02T11:00:00Z",
                    "customer_response": None,
                    "responded_at": None,
                    **payload,
                }
                db_state["additional_work_requests"][rec_id] = rec
                ins_query.execute.return_value = MagicMock(data=[dict(rec)])
            else:
                ins_query.execute.return_value = MagicMock(data=[payload])
            return ins_query

        query.insert.side_effect = insert_mock

        def update_mock(payload):
            upd_query = MagicMock()
            upd_filters = {}

            def upd_eq(col, val):
                upd_filters[col] = str(val)
                return upd_query

            upd_query.eq.side_effect = upd_eq

            def upd_execute():
                if table_name == "bookings":
                    b_id = upd_filters.get("id")
                    expected_status = upd_filters.get("booking_status")
                    if b_id in db_state["bookings"]:
                        b = db_state["bookings"][b_id]
                        if expected_status and b["booking_status"] != expected_status:
                            return MagicMock(data=[])
                        b.update(payload)
                        return MagicMock(data=[dict(b)])
                    return MagicMock(data=[])

                elif table_name == "additional_work_requests":
                    r_id = upd_filters.get("id")
                    expected_status = upd_filters.get("status")
                    if r_id in db_state["additional_work_requests"]:
                        r = db_state["additional_work_requests"][r_id]
                        if expected_status and r["status"] != expected_status:
                            return MagicMock(data=[])
                        r.update(payload)
                        return MagicMock(data=[dict(r)])
                    return MagicMock(data=[])

                elif table_name == "service_inspections":
                    for b_id, insp in db_state["service_inspections"].items():
                        if insp["id"] == upd_filters.get("id"):
                            insp.update(payload)
                            return MagicMock(data=[dict(insp)])
                    return MagicMock(data=[])

                return MagicMock(data=[])

            upd_query.execute.side_effect = upd_execute
            return upd_query

        query.update.side_effect = update_mock
        return query

    mock_client.table.side_effect = table_handler
    return mock_client, db_state


# ==============================================================================
# PHASE 7A: INSPECTION TESTS (Tests 1 - 9)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_mechanic_creates_inspection(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """1. Assigned mechanic successfully creates an inspection report."""
    mock_db, db_state = build_phase7_mock_db(booking_status="mechanic_arrived", has_inspection=False)
    payload = {
        "findings": "Coolant reservoir level low, front brake pads worn.",
        "vehicle_condition": "Good overall, minor brake wear.",
        "estimated_additional_cost": "350.00",
        "evidence_file_paths": [f"{BOOKING_TEST_ID}/inspections/brake_photo.jpg"],
    }
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspections", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["findings"] == payload["findings"]
        assert Decimal(str(data["estimated_additional_cost"])) == Decimal("350.00")
        assert data["booking_id"] == str(BOOKING_TEST_ID)
        assert data["mechanic_id"] == str(MECH_1_PROFILE_ID)
        # Verify booking status transitioned from mechanic_arrived to inspection
        assert db_state["bookings"][str(BOOKING_TEST_ID)]["booking_status"] == "inspection"


@pytest.mark.asyncio
async def test_02_non_mechanic_cannot_create_inspection(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """2. Non-mechanic (customer) is rejected with 403 Forbidden."""
    payload = {
        "findings": "Customer attempting inspection.",
        "estimated_additional_cost": "100.00",
    }
    res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspections", json=payload)
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_03_wrong_mechanic_rejected(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """3. Mechanic who is not assigned to the booking is rejected with 403."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=False)
    payload = {
        "findings": "Unassigned mechanic report.",
        "estimated_additional_cost": "200.00",
    }
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspections", json=payload)
        assert res.status_code == 403
        assert "not have an accepted assignment" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_04_wrong_booking_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """4. Non-existent booking returns 404 Not Found."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=False)
    non_existent = uuid.uuid4()
    payload = {"findings": "Test findings", "estimated_additional_cost": "100.00"}
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{non_existent}/inspections", json=payload)
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_05_customer_can_read_own_booking_inspection(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """5. Customer can read the inspection report for their own booking."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=True)
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspection")
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == str(INSPECTION_TEST_ID)
        assert "brake pads worn" in data["findings"]


@pytest.mark.asyncio
async def test_06_unrelated_customer_rejected_from_reading_inspection(
    async_client: AsyncClient, mock_other_customer: AuthenticatedUser
):
    """6. Unrelated customer attempting to read inspection receives 404 (no leak)."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=True)
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspection")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_07_duplicate_inspection_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """7. Submitting duplicate inspection returns 409 Conflict."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=True)
    payload = {"findings": "Duplicate inspection submission", "estimated_additional_cost": "100.00"}
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspections", json=payload)
        assert res.status_code == 409
        assert "already exists" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_08_invalid_negative_estimated_cost_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """8. Invalid negative estimated additional cost returns 422."""
    payload = {"findings": "Test findings", "estimated_additional_cost": "-50.00"}
    res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspections", json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_09_patch_cannot_change_booking_id_or_mechanic_id(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """9. Client injection of booking_id or mechanic_id in PATCH is rejected with 422."""
    payload = {
        "findings": "Updated findings.",
        "booking_id": str(OTHER_BOOKING_ID),  # Attempted override
        "mechanic_id": str(MECH_2_PROFILE_ID),  # Attempted override
    }
    res = await async_client.patch(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspection", json=payload)
    assert res.status_code == 422

    # Valid PATCH succeeds
    mock_db, _ = build_phase7_mock_db(booking_status="inspection", has_inspection=True)
    valid_payload = {"findings": "Updated diagnostic findings."}
    with patch("app.services.inspection_service.get_supabase_service_client", return_value=mock_db):
        res2 = await async_client.patch(f"/api/v1/bookings/{BOOKING_TEST_ID}/inspection", json=valid_payload)
        assert res2.status_code == 200
        assert res2.json()["findings"] == "Updated diagnostic findings."


# ==============================================================================
# PHASE 7B: ADDITIONAL WORK TESTS (Tests 10 - 17)
# ==============================================================================

@pytest.mark.asyncio
async def test_10_mechanic_creates_additional_work_request(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """10. Assigned mechanic successfully creates an additional work request."""
    mock_db, db_state = build_phase7_mock_db(booking_status="inspection")
    payload = {
        "title": "Air Filter Replacement",
        "description": "Cabin air filter heavily clogged with debris.",
        "price": "450.00",
        "evidence_file_paths": [f"{BOOKING_TEST_ID}/additional_work/filter.jpg"],
    }
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["title"] == payload["title"]
        assert Decimal(str(data["price"])) == Decimal("450.00")
        assert data["status"] == "pending"
        assert data["booking_id"] == str(BOOKING_TEST_ID)
        # Booking transitioned to awaiting_customer_approval
        assert db_state["bookings"][str(BOOKING_TEST_ID)]["booking_status"] == "awaiting_customer_approval"


@pytest.mark.asyncio
async def test_11_wrong_mechanic_cannot_create_additional_work(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """11. Unassigned mechanic cannot create additional work request -> 403."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection")
    payload = {
        "title": "Battery Replacement",
        "description": "Dead cell.",
        "price": "3500.00",
    }
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=payload)
        assert res.status_code == 403
        assert "not have an accepted assignment" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_12_unrelated_mechanic_cannot_read_additional_work(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """12. Unassigned mechanic cannot read additional work requests -> 403."""
    mock_db, _ = build_phase7_mock_db(booking_status="awaiting_customer_approval")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work")
        assert res.status_code == 403


@pytest.mark.asyncio
async def test_13_customer_can_read_own_additional_work_requests(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """13. Customer can view additional work requests for their own booking."""
    mock_db, _ = build_phase7_mock_db(booking_status="awaiting_customer_approval")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 1
        assert items[0]["id"] == str(REQUEST_TEST_ID)
        assert items[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_14_unrelated_customer_rejected_from_reading_additional_work(
    async_client: AsyncClient, mock_other_customer: AuthenticatedUser
):
    """14. Unrelated customer attempting to read additional work receives 404."""
    mock_db, _ = build_phase7_mock_db(booking_status="awaiting_customer_approval")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work")
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_15_negative_price_rejected_for_additional_work(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """15. Negative price in additional work request returns 422."""
    payload = {
        "title": "Brake Service",
        "description": "Negative price attempt",
        "price": "-150.00",
    }
    res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=payload)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_16_invalid_evidence_path_rejected(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """16. Evidence path traversal (../) or wrong booking ID is rejected with 400."""
    mock_db, _ = build_phase7_mock_db(booking_status="inspection")

    # Path traversal attempt
    traversal_payload = {
        "title": "Part Replacement",
        "description": "Valid description",
        "price": "200.00",
        "evidence_file_paths": [f"{BOOKING_TEST_ID}/additional_work/../../etc/passwd"],
    }
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res1 = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=traversal_payload)
        assert res1.status_code == 400
        assert "traversal" in res1.json()["detail"].lower()

    # Cross-booking path attempt
    cross_booking_payload = {
        "title": "Part Replacement",
        "description": "Valid description",
        "price": "200.00",
        "evidence_file_paths": [f"{OTHER_BOOKING_ID}/additional_work/image.png"],
    }
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res2 = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=cross_booking_payload)
        assert res2.status_code == 400
        assert "cross-booking" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_17_booking_lifecycle_enforced_for_additional_work(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """17. Cannot create additional work when booking is in 'pending' or 'cancelled' status."""
    mock_db, _ = build_phase7_mock_db(booking_status="pending")
    payload = {
        "title": "Premature additional work",
        "description": "Booking hasn't started yet.",
        "price": "100.00",
    }
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work", json=payload)
        assert res.status_code == 400
        assert "cannot create additional work" in res.json()["detail"].lower()


# ==============================================================================
# PHASE 7C: CUSTOMER APPROVAL & REJECTION (Tests 18 - 32)
# ==============================================================================

@pytest.mark.asyncio
async def test_18_customer_approves_request(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """18. Customer approves request successfully -> 200 OK."""
    mock_db, _ = build_phase7_mock_db(booking_status="awaiting_customer_approval", request_status="pending")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={"customer_response": "Approved"},
        )
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_19_request_becomes_approved(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """19. Approved request status becomes 'approved' and records responded_at."""
    mock_db, db_state = build_phase7_mock_db(booking_status="awaiting_customer_approval", request_status="pending")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={"customer_response": "Authorized"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "approved"
        assert data["customer_response"] == "Authorized"
        assert data["responded_at"] is not None
        assert db_state["additional_work_requests"][str(REQUEST_TEST_ID)]["status"] == "approved"


@pytest.mark.asyncio
async def test_20_additional_charges_updated(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """20. Authoritative request price increases booking additional_charges."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
        additional_charges="100.00",
        request_price="350.00",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 200
        booking = db_state["bookings"][str(BOOKING_TEST_ID)]
        # 100.00 + 350.00 = 450.00
        assert Decimal(str(booking["additional_charges"])) == Decimal("450.00")


@pytest.mark.asyncio
async def test_21_tax_recalculated(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """21. Tax amount is recalculated with Decimal precision (18% GST)."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
        subtotal="1000.00",
        additional_charges="0.00",
        request_price="500.00",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 200
        booking = db_state["bookings"][str(BOOKING_TEST_ID)]
        # Taxable base = 1000 + 500 = 1500. 1500 * 0.18 = 270.00
        assert Decimal(str(booking["tax_amount"])) == Decimal("270.00")


@pytest.mark.asyncio
async def test_22_total_recalculated(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """22. Total amount is recalculated authoritatively (base + tax)."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
        subtotal="1000.00",
        additional_charges="0.00",
        request_price="500.00",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 200
        booking = db_state["bookings"][str(BOOKING_TEST_ID)]
        # Total = 1000 + 500 + 270 = 1770.00
        assert Decimal(str(booking["total_amount"])) == Decimal("1770.00")


@pytest.mark.asyncio
async def test_23_booking_becomes_service_in_progress(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """23. Booking status transitions to 'service_in_progress' upon customer approval."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 200
        booking = db_state["bookings"][str(BOOKING_TEST_ID)]
        assert booking["booking_status"] == "service_in_progress"


@pytest.mark.asyncio
async def test_24_customer_rejects_request(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """24. Customer rejects request: status becomes 'rejected', responded_at recorded."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/reject",
            json={"reason": "Customer declined service."},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "rejected"
        assert data["customer_response"] == "Customer declined service."
        assert data["responded_at"] is not None
        assert db_state["additional_work_requests"][str(REQUEST_TEST_ID)]["status"] == "rejected"


@pytest.mark.asyncio
async def test_25_no_financial_amount_changes_on_rejection(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """25. Rejection does NOT alter additional_charges, tax, or total amount."""
    mock_db, db_state = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="pending",
        subtotal="1000.00",
        additional_charges="0.00",
        tax_amount="180.00",
        total_amount="1180.00",
        request_price="500.00",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/reject",
            json={"reason": "Decline"},
        )
        assert res.status_code == 200
        booking = db_state["bookings"][str(BOOKING_TEST_ID)]
        assert booking["booking_status"] == "service_in_progress"
        assert Decimal(str(booking["additional_charges"])) == Decimal("0.00")
        assert Decimal(str(booking["tax_amount"])) == Decimal("180.00")
        assert Decimal(str(booking["total_amount"])) == Decimal("1180.00")



@pytest.mark.asyncio
async def test_26_mechanic_cannot_approve(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """26. Mechanic cannot approve customer additional work -> 403 Forbidden."""
    res = await async_client.post(
        f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
        json={"customer_response": "Mechanic attempting self-approval"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_27_unrelated_customer_cannot_approve(
    async_client: AsyncClient, mock_other_customer: AuthenticatedUser
):
    """27. Customer 2 cannot approve Customer 1's work request -> 404 Not Found."""
    mock_db, _ = build_phase7_mock_db(booking_status="awaiting_customer_approval")
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_28_already_approved_request_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """28. Attempting to approve an already approved request returns 409 Conflict."""
    mock_db, _ = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="approved",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 409
        assert "already been approved" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_29_already_rejected_request_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """29. Attempting to approve an already rejected request returns 409 Conflict."""
    mock_db, _ = build_phase7_mock_db(
        booking_status="awaiting_customer_approval",
        request_status="rejected",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 409
        assert "already been rejected" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_30_cancelled_booking_cannot_be_approved(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """30. Approval on a cancelled booking returns 400 Bad Request."""
    mock_db, _ = build_phase7_mock_db(
        booking_status="cancelled",
        request_status="pending",
    )
    with patch("app.services.additional_work_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/additional-work/{REQUEST_TEST_ID}/approve",
            json={},
        )
        assert res.status_code == 400
        assert "cannot approve additional work when booking is in 'cancelled'" in res.json()["detail"].lower()


# ==============================================================================
# CONCURRENCY TESTS (Tests 31 & 32)
# ==============================================================================

@pytest.mark.asyncio
async def test_31_duplicate_concurrent_approval_only_succeeds_once():
    """
    31. Two simultaneous requests attempt to approve the same additional work item concurrently.
    Guarantees:
    - Exactly ONE request succeeds (200 OK).
    - Exactly ONE request receives 409 Conflict.
    - Financial addition commits exactly ONCE.
    """
    from app.services.additional_work_service import AdditionalWorkService

    db_lock = threading.Lock()
    db_state = {
        "booking": {
            "id": str(BOOKING_TEST_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "awaiting_customer_approval",
            "subtotal": "1000.00",
            "additional_charges": "0.00",
            "discount_amount": "0.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
        },
        "request": {
            "id": str(REQUEST_TEST_ID),
            "booking_id": str(BOOKING_TEST_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "price": "500.00",
            "status": "pending",
            "customer_response": None,
            "responded_at": None,
        },
    }

    def concurrent_table_handler(table_name: str):
        query = MagicMock()
        query.select.return_value = query
        filters = {}

        def eq_fn(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_fn

        def exec_fn():
            with db_lock:
                if table_name == "bookings":
                    return MagicMock(data=[dict(db_state["booking"])])
                elif table_name == "additional_work_requests":
                    return MagicMock(data=[dict(db_state["request"])])
                return MagicMock(data=[])

        query.execute.side_effect = exec_fn

        def update_fn(payload):
            upd = MagicMock()
            upd_filters = {}

            def upd_eq(col, val):
                upd_filters[col] = str(val)
                return upd

            upd.eq.side_effect = upd_eq

            def upd_exec():
                with db_lock:
                    if table_name == "additional_work_requests":
                        # Conditional update on status == 'pending'
                        if db_state["request"]["status"] != "pending":
                            return MagicMock(data=[])
                        db_state["request"].update(payload)
                        return MagicMock(data=[dict(db_state["request"])])
                    elif table_name == "bookings":
                        db_state["booking"].update(payload)
                        return MagicMock(data=[dict(db_state["booking"])])
                    return MagicMock(data=[])

            upd.execute.side_effect = upd_exec
            return upd

        query.update.side_effect = update_fn
        return query

    client1 = MagicMock()
    client1.table.side_effect = concurrent_table_handler

    client2 = MagicMock()
    client2.table.side_effect = concurrent_table_handler

    service1 = AdditionalWorkService()
    service1.client = client1

    service2 = AdditionalWorkService()
    service2.client = client2

    async def approve_task_1():
        return await service1.approve_additional_work_request(
            booking_id=BOOKING_TEST_ID,
            request_id=REQUEST_TEST_ID,
            customer_user_id=CUSTOMER_1_ID,
        )

    async def approve_task_2():
        return await service2.approve_additional_work_request(
            booking_id=BOOKING_TEST_ID,
            request_id=REQUEST_TEST_ID,
            customer_user_id=CUSTOMER_1_ID,
        )

    results = await asyncio.gather(approve_task_1(), approve_task_2(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"

    from fastapi import HTTPException
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == 409

    # Additional charges incremented exactly ONCE (500.00, not 1000.00)
    assert Decimal(str(db_state["booking"]["additional_charges"])) == Decimal("500.00")
    assert db_state["request"]["status"] == "approved"


@pytest.mark.asyncio
async def test_32_concurrent_approve_vs_reject_only_one_succeeds():
    """
    32. Simultaneous approve vs reject on the same request.
    Guarantees:
    - Exactly ONE operation succeeds (200 OK).
    - Exactly ONE operation receives 409 Conflict.
    - Final state is deterministically either 'approved' or 'rejected'.
    """
    from app.services.additional_work_service import AdditionalWorkService

    db_lock = threading.Lock()
    db_state = {
        "booking": {
            "id": str(BOOKING_TEST_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "awaiting_customer_approval",
            "subtotal": "1000.00",
            "additional_charges": "0.00",
            "discount_amount": "0.00",
            "tax_amount": "180.00",
            "total_amount": "1180.00",
        },
        "request": {
            "id": str(REQUEST_TEST_ID),
            "booking_id": str(BOOKING_TEST_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "price": "500.00",
            "status": "pending",
            "customer_response": None,
            "responded_at": None,
        },
    }

    def concurrent_table_handler(table_name: str):
        query = MagicMock()
        query.select.return_value = query
        filters = {}

        def eq_fn(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_fn

        def exec_fn():
            with db_lock:
                if table_name == "bookings":
                    return MagicMock(data=[dict(db_state["booking"])])
                elif table_name == "additional_work_requests":
                    return MagicMock(data=[dict(db_state["request"])])
                return MagicMock(data=[])

        query.execute.side_effect = exec_fn

        def update_fn(payload):
            upd = MagicMock()
            upd_filters = {}

            def upd_eq(col, val):
                upd_filters[col] = str(val)
                return upd

            upd.eq.side_effect = upd_eq

            def upd_exec():
                with db_lock:
                    if table_name == "additional_work_requests":
                        if db_state["request"]["status"] != "pending":
                            return MagicMock(data=[])
                        db_state["request"].update(payload)
                        return MagicMock(data=[dict(db_state["request"])])
                    elif table_name == "bookings":
                        db_state["booking"].update(payload)
                        return MagicMock(data=[dict(db_state["booking"])])
                    return MagicMock(data=[])

            upd.execute.side_effect = upd_exec
            return upd

        query.update.side_effect = update_fn
        return query

    client1 = MagicMock()
    client1.table.side_effect = concurrent_table_handler

    client2 = MagicMock()
    client2.table.side_effect = concurrent_table_handler

    service1 = AdditionalWorkService()
    service1.client = client1

    service2 = AdditionalWorkService()
    service2.client = client2

    async def approve_task():
        return await service1.approve_additional_work_request(
            booking_id=BOOKING_TEST_ID,
            request_id=REQUEST_TEST_ID,
            customer_user_id=CUSTOMER_1_ID,
        )

    async def reject_task():
        return await service2.reject_additional_work_request(
            booking_id=BOOKING_TEST_ID,
            request_id=REQUEST_TEST_ID,
            customer_user_id=CUSTOMER_1_ID,
        )

    results = await asyncio.gather(approve_task(), reject_task(), return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {results}"
    assert len(failures) == 1, f"Expected exactly 1 failure, got {len(failures)}: {results}"

    from fastapi import HTTPException
    assert isinstance(failures[0], HTTPException)
    assert failures[0].status_code == 409

    final_status = db_state["request"]["status"]
    assert final_status in ["approved", "rejected"]
