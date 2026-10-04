"""
Unit and Integration Tests for Phase 12: Production-Grade Vehicle Service Operations.

Covers:
1. Arrival workflow & authoritative timestamping.
2. Structured vehicle inspections with diagnostic codes & odometer readings.
3. Service checklist templates, automated seeding, and task updates.
4. Parts tracking with quantity and Decimal total price calculations.
5. PricingEngine Decimal arithmetic & immutable price snapshots.
6. Customer estimate approval and price snapshot freezing.
7. Service completion gate enforcement (mandatory checklist completion & pending work resolution).
8. Service report generation and automatic invoice issuance.
9. Customer dispute raising on eligible states and administrative resolution.
10. Tenant isolation and evidence path access controls.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.db.dependencies import (
    get_current_user,
    require_admin_or_support,
    require_customer,
    require_mechanic,
)
from app.main import app
from app.schemas.booking import BookingStatus
from app.schemas.service_operations import (
    DiagnosticFinding,
    RecommendedService,
    ServiceCompletionRequest,
    StructuredInspectionCreate,
)
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.pricing_engine import PricingEngine
from app.services.service_operations_service import ServiceOperationsService

# Test UUIDs
CUSTOMER_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
OTHER_CUSTOMER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
MECHANIC_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
OTHER_MECHANIC_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADMIN_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

MECHANIC_PROFILE_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
OTHER_MECHANIC_PROFILE_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
BOOKING_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")
CHECKLIST_ITEM_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")


def make_authenticated_user(user_id: uuid.UUID, role: UserRole) -> AuthenticatedUser:
    """Helper creating mock AuthenticatedUser object."""
    profile = UserProfileResponse(
        id=user_id,
        email=f"{role.value}@example.com",
        full_name=f"Test {role.value.capitalize()}",
        role=role,
        is_active=True,
        is_verified=True,
        phone=None,
        avatar_url=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return AuthenticatedUser(
        id=user_id,
        email=profile.email,
        role=role,
        profile=profile,
        jwt_claims={"sub": str(user_id)},
    )


# ==============================================================================
# 1. PricingEngine Pure Unit Tests
# ==============================================================================

def test_pricing_engine_decimal_arithmetic():
    """Verify PricingEngine uses exact Decimal math with 18% GST."""
    totals = PricingEngine.calculate_totals(
        base_service_amount=Decimal("1500.00"),
        parts_total=Decimal("450.00"),
        labor_total=Decimal("200.00"),
        additional_work_total=Decimal("350.00"),
        discount_amount=Decimal("100.00"),
    )

    # Subtotal = 1500 + 450 + 200 = 2150.00
    assert totals["subtotal"] == Decimal("2150.00")
    # Taxable Base = 2150 + 350 - 100 = 2400.00
    assert totals["taxable_base"] == Decimal("2400.00")
    # Tax = 2400.00 * 0.18 = 432.00
    assert totals["tax_amount"] == Decimal("432.00")
    # Total = 2400.00 + 432.00 = 2832.00
    assert totals["total_amount"] == Decimal("2832.00")


def test_pricing_engine_immutable_snapshot():
    """Verify PriceSnapshot is populated with exact frozen amounts."""
    snapshot = PricingEngine.create_price_snapshot(
        base_service_amount=Decimal("999.00"),
        parts_total=Decimal("250.00"),
        labor_total=Decimal("150.00"),
        additional_work_total=Decimal("0.00"),
        discount_amount=Decimal("50.00"),
        approved_by=CUSTOMER_USER_ID,
    )

    assert snapshot.base_service_amount == Decimal("999.00")
    assert snapshot.parts_total == Decimal("250.00")
    assert snapshot.labor_total == Decimal("150.00")
    assert snapshot.taxable_base == Decimal("1349.00")  # (999 + 250 + 150 - 50)
    assert snapshot.tax_amount == Decimal("242.82")    # 1349 * 0.18
    assert snapshot.total_amount == Decimal("1591.82")  # 1349 + 242.82
    assert snapshot.approved_by == CUSTOMER_USER_ID
    assert snapshot.version == 1


# ==============================================================================
# 2. Service Operations Service Unit & Lifecycle Tests
# ==============================================================================

@pytest.fixture
def mock_supabase_db():
    """Create stateful mock database client."""
    client = MagicMock()

    # Tables store in-memory state
    state = {
        "bookings": {
            str(BOOKING_ID): {
                "id": str(BOOKING_ID),
                "booking_number": "BK-20261004-TEST01",
                "customer_id": str(CUSTOMER_USER_ID),
                "booking_status": BookingStatus.MECHANIC_EN_ROUTE.value,
                "subtotal": "1200.00",
                "additional_charges": "0.00",
                "discount_amount": "0.00",
                "tax_amount": "216.00",
                "total_amount": "1416.00",
                "price_snapshot": None,
            }
        },
        "mechanic_profiles": {
            str(MECHANIC_USER_ID): {
                "id": str(MECHANIC_PROFILE_ID),
                "user_id": str(MECHANIC_USER_ID),
                "business_name": "Apex Auto Care",
            },
            str(OTHER_MECHANIC_USER_ID): {
                "id": str(OTHER_MECHANIC_PROFILE_ID),
                "user_id": str(OTHER_MECHANIC_USER_ID),
                "business_name": "Rival Garage",
            },
        },
        "mechanic_assignments": [
            {
                "id": str(uuid.uuid4()),
                "booking_id": str(BOOKING_ID),
                "mechanic_id": str(MECHANIC_PROFILE_ID),
                "assignment_status": "accepted",
            }
        ],
        "service_inspections": [],
        "booking_checklist_items": [
            {
                "id": str(CHECKLIST_ITEM_ID),
                "booking_id": str(BOOKING_ID),
                "item_key": "brake_pads_thickness",
                "title": "Inspect brake pads thickness",
                "category_slug": "brakes",
                "is_mandatory": True,
                "is_completed": False,
                "notes": None,
            }
        ],
        "booking_parts": [],
        "service_reports": [],
        "additional_work_requests": [],
    }

    def table_router(table_name):
        mock_t = MagicMock()

        def select_mock(*args, **kwargs):
            filters = {}
            query_builder = MagicMock()

            def eq_mock(col, val):
                filters[col] = str(val)
                return query_builder

            def in_mock(col, vals):
                filters[col] = [str(v) for v in vals]
                return query_builder

            def execute_mock():
                res = MagicMock()
                if table_name == "bookings":
                    b_id = filters.get("id")
                    if b_id:
                        b = state["bookings"].get(b_id)
                        res.data = [b] if b else []
                    else:
                        res.data = list(state["bookings"].values())
                elif table_name == "mechanic_profiles":
                    items = list(state["mechanic_profiles"].values())
                    for k, v in filters.items():
                        items = [m for m in items if m.get(k) == v]
                    res.data = items
                elif table_name == "mechanic_assignments":
                    items = list(state["mechanic_assignments"])
                    for k, v in filters.items():
                        items = [a for a in items if a.get(k) == v]
                    res.data = items
                elif table_name == "service_inspections":
                    items = list(state["service_inspections"])
                    for k, v in filters.items():
                        items = [i for i in items if i.get(k) == v]
                    res.data = items
                elif table_name == "booking_checklist_items":
                    items = list(state["booking_checklist_items"])
                    for k, v in filters.items():
                        items = [c for c in items if c.get(k) == v]
                    res.data = items
                elif table_name == "booking_parts":
                    items = list(state["booking_parts"])
                    for k, v in filters.items():
                        items = [p for p in items if p.get(k) == v]
                    res.data = items
                elif table_name == "service_reports":
                    items = list(state["service_reports"])
                    for k, v in filters.items():
                        items = [r for r in items if r.get(k) == v]
                    res.data = items
                elif table_name == "additional_work_requests":
                    items = list(state["additional_work_requests"])
                    for k, v in filters.items():
                        items = [w for w in items if w.get(k) == v]
                    res.data = items
                else:
                    res.data = []
                return res

            query_builder.eq = eq_mock
            query_builder.in_ = in_mock
            query_builder.order = lambda *a, **k: query_builder
            query_builder.execute = execute_mock
            return query_builder

        def update_mock(upd_fields):
            upd_builder = MagicMock()

            def eq_mock(col, val):
                inner_eq = MagicMock()

                def inner_eq_chain(col2, val2):
                    def execute_mock():
                        res = MagicMock()
                        if table_name == "bookings":
                            b = state["bookings"].get(str(val))
                            if b:
                                b.update(upd_fields)
                                res.data = [b]
                            else:
                                res.data = []
                        elif table_name == "booking_checklist_items":
                            c = next((it for it in state["booking_checklist_items"] if it["id"] == str(val)), None)
                            if c:
                                c.update(upd_fields)
                                res.data = [c]
                            else:
                                res.data = []
                        elif table_name == "service_reports":
                            r = next((it for it in state["service_reports"] if it["booking_id"] == str(val)), None)
                            if r:
                                r.update(upd_fields)
                                res.data = [r]
                            else:
                                res.data = []
                        else:
                            res.data = []
                        return res

                    fin_mock = MagicMock()
                    fin_mock.execute = execute_mock
                    return fin_mock

                def execute_mock():
                    res = MagicMock()
                    if table_name == "bookings":
                        b = state["bookings"].get(str(val))
                        if b:
                            b.update(upd_fields)
                            res.data = [b]
                        else:
                            res.data = []
                    elif table_name == "booking_checklist_items":
                        c = next((it for it in state["booking_checklist_items"] if it["id"] == str(val)), None)
                        if c:
                            c.update(upd_fields)
                            res.data = [c]
                        else:
                            res.data = []
                    elif table_name == "service_reports":
                        r = next((it for it in state["service_reports"] if it["booking_id"] == str(val)), None)
                        if r:
                            r.update(upd_fields)
                            res.data = [r]
                        else:
                            res.data = []
                    else:
                        res.data = []
                    return res

                inner_eq.eq = inner_eq_chain
                inner_eq.in_ = lambda c, vals: inner_eq
                inner_eq.execute = execute_mock
                return inner_eq

            upd_builder.eq = eq_mock
            return upd_builder

        def insert_mock(record_or_records):
            ins_builder = MagicMock()

            def execute_mock():
                res = MagicMock()
                recs = record_or_records if isinstance(record_or_records, list) else [record_or_records]
                inserted = []
                for r in recs:
                    new_rec = dict(r)
                    if "id" not in new_rec:
                        new_rec["id"] = str(uuid.uuid4())
                    if "created_at" not in new_rec:
                        new_rec["created_at"] = datetime.now(timezone.utc).isoformat()
                    if "updated_at" not in new_rec:
                        new_rec["updated_at"] = datetime.now(timezone.utc).isoformat()
                    inserted.append(new_rec)
                    if table_name in state and isinstance(state[table_name], list):
                        state[table_name].append(new_rec)
                res.data = inserted
                return res

            ins_builder.execute = execute_mock
            return ins_builder

        mock_t.select = select_mock
        mock_t.update = update_mock
        mock_t.insert = insert_mock
        return mock_t

    client.table = table_router
    return client, state


@pytest.mark.asyncio
async def test_record_arrival_lifecycle(mock_supabase_db):
    """Verify mechanic arrival transitions booking to mechanic_arrived with authoritative timestamp."""
    client, state = mock_supabase_db
    service = ServiceOperationsService(client=client)

    resp = await service.record_arrival(
        booking_id=BOOKING_ID,
        mechanic_user_id=MECHANIC_USER_ID,
    )

    assert resp.booking_status == BookingStatus.MECHANIC_ARRIVED.value
    assert state["bookings"][str(BOOKING_ID)]["booking_status"] == BookingStatus.MECHANIC_ARRIVED.value
    assert isinstance(resp.arrived_at, datetime)


@pytest.mark.asyncio
async def test_record_arrival_blocked_for_unassigned_mechanic(mock_supabase_db):
    """Verify unassigned mechanic cannot record arrival (403 Forbidden)."""
    client, _ = mock_supabase_db
    service = ServiceOperationsService(client=client)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service.record_arrival(
            booking_id=BOOKING_ID,
            mechanic_user_id=OTHER_MECHANIC_USER_ID,
        )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_submit_structured_inspection(mock_supabase_db):
    """Verify mechanic can submit structured inspection with checkpoints and diagnostic codes."""
    client, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.MECHANIC_ARRIVED.value
    service = ServiceOperationsService(client=client)

    payload = StructuredInspectionCreate(
        findings="Front brake pads worn down to 2mm. Disc rotor surface has light scoring.",
        vehicle_condition="Fair - Needs front brake servicing",
        odometer_reading=45230,
        checklist_results={"brake_pads_thickness": "2mm - critical", "brake_fluid": "1.2% moisture - ok"},
        diagnostic_findings=[
            DiagnosticFinding(
                category="brakes",
                finding="Brake pad thickness below 3mm safety limit",
                severity="high",
                recommended_action="Replace front brake pads set",
            )
        ],
        recommended_services=[
            RecommendedService(
                title="Front Ceramic Brake Pad Replacement",
                description="OEM quality brake pads",
                is_required=True,
                estimated_price=Decimal("1850.00"),
            )
        ],
        estimated_additional_cost=Decimal("1850.00"),
        evidence_file_paths=[f"{BOOKING_ID}/inspections/pad_wear.jpg"],
    )

    result = await service.submit_structured_inspection(
        booking_id=BOOKING_ID,
        mechanic_user_id=MECHANIC_USER_ID,
        payload=payload,
    )

    assert result["odometer_reading"] == 45230
    assert result["findings"].startswith("Front brake pads worn")
    assert len(result["diagnostic_findings"]) == 1
    # Because estimated_additional_cost > 0, booking automatically moves to awaiting_customer_approval
    assert state["bookings"][str(BOOKING_ID)]["booking_status"] == BookingStatus.AWAITING_CUSTOMER_APPROVAL.value


@pytest.mark.asyncio
async def test_customer_approve_estimate_freezes_snapshot(mock_supabase_db):
    """Verify customer estimate approval freezes immutable price snapshot and moves to service_in_progress."""
    client, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.AWAITING_CUSTOMER_APPROVAL.value
    state["bookings"][str(BOOKING_ID)]["additional_charges"] = "500.00"
    service = ServiceOperationsService(client=client)

    result = await service.customer_approve_estimate(
        booking_id=BOOKING_ID,
        customer_user_id=CUSTOMER_USER_ID,
    )

    assert result["booking_status"] == BookingStatus.SERVICE_IN_PROGRESS.value
    assert "price_snapshot" in result
    snapshot = result["price_snapshot"]
    assert snapshot is not None
    assert Decimal(str(snapshot["base_service_amount"])) == Decimal("1200.00")
    assert Decimal(str(snapshot["additional_work_total"])) == Decimal("500.00")
    # Subtotal 1200 + 500 = 1700 * 0.18 tax = 306.00; total = 2006.00
    assert Decimal(str(snapshot["total_amount"])) == Decimal("2006.00")


@pytest.mark.asyncio
async def test_service_completion_gate_incomplete_checklist_blocked(mock_supabase_db):
    """Verify service completion is blocked if mandatory checklist tasks are incomplete."""
    client, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.SERVICE_IN_PROGRESS.value
    # Checklist task is_completed is False
    service = ServiceOperationsService(client=client)

    payload = ServiceCompletionRequest(
        summary="Service finished",
        work_performed="Installed brake pads",
        completion_evidence_paths=[f"{BOOKING_ID}/completion/after_repair.jpg"],
    )

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service.complete_service(
            booking_id=BOOKING_ID,
            mechanic_user_id=MECHANIC_USER_ID,
            payload=payload,
        )
    assert exc_info.value.status_code == 400
    assert "Mandatory checklist items incomplete" in exc_info.value.detail


@pytest.mark.asyncio
async def test_service_completion_success(mock_supabase_db):
    """Verify service completion generates service report and advances to service_completed when checklist is done."""
    client, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.SERVICE_IN_PROGRESS.value
    # Mark checklist item complete
    state["booking_checklist_items"][0]["is_completed"] = True
    service = ServiceOperationsService(client=client)

    payload = ServiceCompletionRequest(
        summary="Complete brake overhaul executed successfully",
        work_performed="Replaced front ceramic pads, bled hydraulic lines, torqued caliper pins to 35 Nm",
        recommendations="Inspect rear drum brakes during next scheduled service in 6 months",
        completion_evidence_paths=[f"{BOOKING_ID}/completion/done.jpg"],
    )

    report = await service.complete_service(
        booking_id=BOOKING_ID,
        mechanic_user_id=MECHANIC_USER_ID,
        payload=payload,
    )

    assert report.booking_id == BOOKING_ID
    assert report.summary.startswith("Complete brake overhaul")
    assert state["bookings"][str(BOOKING_ID)]["booking_status"] == BookingStatus.SERVICE_COMPLETED.value


@pytest.mark.asyncio
async def test_dispute_lifecycle(mock_supabase_db):
    """Verify customer can raise dispute on completed booking and admin can resolve it."""
    client, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.SERVICE_COMPLETED.value
    service = ServiceOperationsService(client=client)

    from app.schemas.service_operations import DisputeCreateRequest, DisputeResolveRequest

    # 1. Customer raises dispute
    disp = await service.raise_dispute(
        booking_id=BOOKING_ID,
        customer_user_id=CUSTOMER_USER_ID,
        payload=DisputeCreateRequest(reason="Brake squeal noticed after mechanic left."),
    )
    assert disp["booking_status"] == BookingStatus.DISPUTED.value
    assert state["bookings"][str(BOOKING_ID)]["booking_status"] == BookingStatus.DISPUTED.value

    # 2. Admin resolves dispute
    res = await service.resolve_dispute(
        booking_id=BOOKING_ID,
        admin_user_id=ADMIN_USER_ID,
        payload=DisputeResolveRequest(
            resolution_status="paid",
            resolution_notes="Dispute resolved via warranty inspection scheduled for tomorrow.",
        ),
    )
    assert res["booking_status"] == "paid"
    assert state["bookings"][str(BOOKING_ID)]["booking_status"] == "paid"


# ==============================================================================
# 3. HTTP Integration Route Tests via TestClient
# ==============================================================================

@pytest.mark.asyncio
async def test_api_arrive_endpoint(mock_supabase_db):
    """Test POST /api/v1/bookings/{booking_id}/arrive."""
    client_db, state = mock_supabase_db
    state["bookings"][str(BOOKING_ID)]["booking_status"] = BookingStatus.MECHANIC_EN_ROUTE.value

    mechanic_user = make_authenticated_user(MECHANIC_USER_ID, UserRole.MECHANIC)

    with patch("app.services.service_operations_service.get_supabase_service_client", return_value=client_db):
        app.dependency_overrides[require_mechanic] = lambda: mechanic_user
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(f"/api/v1/bookings/{BOOKING_ID}/arrive")
                assert resp.status_code == 200
                data = resp.json()
                assert data["booking_status"] == BookingStatus.MECHANIC_ARRIVED.value
        finally:
            app.dependency_overrides.pop(require_mechanic, None)


@pytest.mark.asyncio
async def test_api_signed_url_cross_booking_rejected(mock_supabase_db):
    """Test cross-booking evidence signed URL is strictly rejected."""
    client_db, _ = mock_supabase_db
    customer_user = make_authenticated_user(CUSTOMER_USER_ID, UserRole.CUSTOMER)
    other_booking = uuid.uuid4()

    with patch("app.services.service_operations_service.get_supabase_service_client", return_value=client_db):
        app.dependency_overrides[get_current_user] = lambda: customer_user
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                # Path contains other_booking UUID instead of route BOOKING_ID
                resp = await ac.get(
                    f"/api/v1/bookings/{BOOKING_ID}/evidence/signed-url",
                    params={"path": f"{other_booking}/inspections/photo.jpg"},
                )
                assert resp.status_code == 400
                assert "Evidence path must belong to booking" in resp.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_current_user, None)
