"""
Comprehensive Booking Creation & Authoritative Pricing Tests (Phase 4).

Tests:
1. Successful booking creation with authoritative pricing
2. Unauthenticated booking creation -> 401
3. Inaccessible/invalid vehicle -> 404
4. Vehicle belonging to another customer -> 404 (no leak)
5. Inaccessible/invalid address -> 404
6. Address belonging to another customer -> 404 (no leak)
7. Inactive service -> 400 rejection
8. Incompatible service/vehicle -> 400 rejection
9. Missing pricing -> 400 rejection
10. Quantity <= 0 -> 422 validation error
11. Client-supplied price -> 422 rejected (extra=forbid)
12. Client-supplied customer_id -> 422 rejected (extra=forbid)
13. Correct Decimal subtotal calculation
14. Multiple booking items with exact quantity multiplication
15. Duplicate service items in single booking -> 400 rejection
16. Initial booking status: pending, payment_status: unpaid
17. Booking ownership on GET -> 200
18. Cross-customer booking access on GET -> 404
19. Customer list my-bookings -> 200
20. Compensating delete rollback on item insertion failure -> 500
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.user import AuthenticatedUser

CUSTOMER_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

VEHICLE_1_ID = uuid.UUID("aaaa1111-0000-0000-0000-000000000001")
VEHICLE_2_ID = uuid.UUID("aaaa2222-0000-0000-0000-000000000002")

ADDRESS_1_ID = uuid.UUID("bbbb1111-0000-0000-0000-000000000001")
ADDRESS_2_ID = uuid.UUID("bbbb2222-0000-0000-0000-000000000002")

VT_CAR_ID = uuid.UUID("cccc1111-0000-0000-0000-000000000001")
VT_BIKE_ID = uuid.UUID("cccc2222-0000-0000-0000-000000000002")

CATEGORY_1_ID = uuid.UUID("dddd1111-0000-0000-0000-000000000001")

SERVICE_CAR_ID = uuid.UUID("eeee1111-0000-0000-0000-000000000001")
SERVICE_BIKE_ID = uuid.UUID("eeee2222-0000-0000-0000-000000000002")
SERVICE_EXTRA_ID = uuid.UUID("eeee3333-0000-0000-0000-000000000003")
SERVICE_INACTIVE_ID = uuid.UUID("eeee4444-0000-0000-0000-000000000004")
SERVICE_NO_PRICE_ID = uuid.UUID("eeee5555-0000-0000-0000-000000000005")

BOOKING_1_ID = uuid.UUID("ffff1111-0000-0000-0000-000000000001")


def build_mock_db_client():
    """Build a comprehensive Supabase mock client for booking operations."""
    mock_client = MagicMock()

    # Pre-defined database state records
    vehicles_db = {
        str(VEHICLE_1_ID): {
            "id": str(VEHICLE_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "vehicle_type_id": str(VT_CAR_ID),
        },
        str(VEHICLE_2_ID): {
            "id": str(VEHICLE_2_ID),
            "customer_id": str(CUSTOMER_2_ID),
            "vehicle_type_id": str(VT_CAR_ID),
        },
    }

    addresses_db = {
        str(ADDRESS_1_ID): {
            "id": str(ADDRESS_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "latitude": "12.971598",
            "longitude": "77.594562",
        },
        str(ADDRESS_2_ID): {
            "id": str(ADDRESS_2_ID),
            "customer_id": str(CUSTOMER_2_ID),
            "latitude": "13.082680",
            "longitude": "80.270718",
        },
    }

    vehicle_types_db = {
        str(VT_CAR_ID): {"id": str(VT_CAR_ID), "name": "Car", "is_active": True},
        str(VT_BIKE_ID): {"id": str(VT_BIKE_ID), "name": "Motorcycle", "is_active": True},
    }

    services_db = {
        str(SERVICE_CAR_ID): {
            "id": str(SERVICE_CAR_ID),
            "name": "Periodic General Service",
            "is_active": True,
            "vehicle_type": "car",
            "category_id": str(CATEGORY_1_ID),
            "service_categories": {"is_active": True},
        },
        str(SERVICE_BIKE_ID): {
            "id": str(SERVICE_BIKE_ID),
            "name": "Bike Chain Lubrication",
            "is_active": True,
            "vehicle_type": "bike",
            "category_id": str(CATEGORY_1_ID),
            "service_categories": {"is_active": True},
        },
        str(SERVICE_EXTRA_ID): {
            "id": str(SERVICE_EXTRA_ID),
            "name": "Brake Pad Replacement",
            "is_active": True,
            "vehicle_type": "car",
            "category_id": str(CATEGORY_1_ID),
            "service_categories": {"is_active": True},
        },
        str(SERVICE_INACTIVE_ID): {
            "id": str(SERVICE_INACTIVE_ID),
            "name": "Old Wash Service",
            "is_active": False,
            "vehicle_type": "car",
            "category_id": str(CATEGORY_1_ID),
            "service_categories": {"is_active": True},
        },
        str(SERVICE_NO_PRICE_ID): {
            "id": str(SERVICE_NO_PRICE_ID),
            "name": "Unpriced Custom Service",
            "is_active": True,
            "vehicle_type": "car",
            "category_id": str(CATEGORY_1_ID),
            "service_categories": {"is_active": True},
        },
    }

    service_pricing_db = {
        str(SERVICE_CAR_ID): [
            {
                "id": str(uuid.uuid4()),
                "service_id": str(SERVICE_CAR_ID),
                "vehicle_type_id": str(VT_CAR_ID),
                "base_price": "1499.50",
                "minimum_price": "1200.00",
                "pricing_parameters": {},
                "is_active": True,
            }
        ],
        str(SERVICE_BIKE_ID): [
            {
                "id": str(uuid.uuid4()),
                "service_id": str(SERVICE_BIKE_ID),
                "vehicle_type_id": str(VT_BIKE_ID),
                "base_price": "299.00",
                "minimum_price": "250.00",
                "pricing_parameters": {},
                "is_active": True,
            }
        ],
        str(SERVICE_EXTRA_ID): [
            {
                "id": str(uuid.uuid4()),
                "service_id": str(SERVICE_EXTRA_ID),
                "vehicle_type_id": str(VT_CAR_ID),
                "base_price": "850.25",
                "minimum_price": "750.00",
                "pricing_parameters": {},
                "is_active": True,
            }
        ],
    }

    def table_mock_factory(table_name):
        query = MagicMock()
        query.select.return_value = query
        query.order.return_value = query
        query.range.return_value = query

        # State tracking for eq filters
        filters = {}

        def eq_effect(col, val):
            filters[col] = str(val)
            return query

        query.eq.side_effect = eq_effect

        def execute_effect():
            if table_name == "vehicles":
                v_id = filters.get("id")
                cust_id = filters.get("customer_id")
                row = vehicles_db.get(v_id)
                if row and (cust_id is None or row["customer_id"] == cust_id):
                    return MagicMock(data=[row])
                return MagicMock(data=[])

            elif table_name == "addresses":
                a_id = filters.get("id")
                cust_id = filters.get("customer_id")
                row = addresses_db.get(a_id)
                if row and (cust_id is None or row["customer_id"] == cust_id):
                    return MagicMock(data=[row])
                return MagicMock(data=[])

            elif table_name == "vehicle_types":
                vt_id = filters.get("id")
                row = vehicle_types_db.get(vt_id)
                return MagicMock(data=[row] if row else [])

            elif table_name == "services":
                s_id = filters.get("id")
                row = services_db.get(s_id)
                return MagicMock(data=[row] if row else [])

            elif table_name == "service_pricing":
                s_id = filters.get("service_id")
                rows = service_pricing_db.get(s_id, [])
                return MagicMock(data=rows)

            elif table_name == "bookings":
                b_id = filters.get("id")
                c_id = filters.get("customer_id")
                if b_id:
                    if b_id == str(BOOKING_1_ID):
                        return MagicMock(
                            data=[
                                {
                                    "id": str(BOOKING_1_ID),
                                    "booking_number": "BK-20261002-TEST1",
                                    "customer_id": str(CUSTOMER_1_ID),
                                    "vehicle_id": str(VEHICLE_1_ID),
                                    "address_id": str(ADDRESS_1_ID),
                                    "scheduled_at": "2026-10-02T12:00:00Z",
                                    "requested_latitude": "12.971598",
                                    "requested_longitude": "77.594562",
                                    "customer_notes": "Call before arrival",
                                    "subtotal": "1499.50",
                                    "additional_charges": "0.00",
                                    "discount_amount": "0.00",
                                    "tax_amount": "0.00",
                                    "total_amount": "1499.50",
                                    "payment_status": "unpaid",
                                    "booking_status": "pending",
                                    "created_at": "2026-10-02T10:00:00Z",
                                    "updated_at": "2026-10-02T10:00:00Z",
                                    "booking_items": [
                                        {
                                            "id": str(uuid.uuid4()),
                                            "booking_id": str(BOOKING_1_ID),
                                            "service_id": str(SERVICE_CAR_ID),
                                            "quantity": 1,
                                            "unit_price": "1499.50",
                                            "total_price": "1499.50",
                                            "notes": None,
                                            "created_at": "2026-10-02T10:00:00Z",
                                            "services": {"name": "Periodic General Service"},
                                        }
                                    ],
                                }
                            ]
                        )
                    return MagicMock(data=[])
                if c_id:
                    if c_id == str(CUSTOMER_1_ID):
                        return MagicMock(
                            data=[
                                {
                                    "id": str(BOOKING_1_ID),
                                    "booking_number": "BK-20261002-TEST1",
                                    "customer_id": str(CUSTOMER_1_ID),
                                    "vehicle_id": str(VEHICLE_1_ID),
                                    "address_id": str(ADDRESS_1_ID),
                                    "scheduled_at": "2026-10-02T12:00:00Z",
                                    "requested_latitude": "12.971598",
                                    "requested_longitude": "77.594562",
                                    "customer_notes": None,
                                    "subtotal": "1499.50",
                                    "additional_charges": "0.00",
                                    "discount_amount": "0.00",
                                    "tax_amount": "0.00",
                                    "total_amount": "1499.50",
                                    "payment_status": "unpaid",
                                    "booking_status": "pending",
                                    "created_at": "2026-10-02T10:00:00Z",
                                    "updated_at": "2026-10-02T10:00:00Z",
                                    "booking_items": [],
                                }
                            ]
                        )
                    return MagicMock(data=[])

            return MagicMock(data=[])

        query.execute.side_effect = execute_effect

        def insert_effect(payload):
            insert_query = MagicMock()
            if table_name == "bookings":
                inserted_booking = {
                    **payload,
                    "id": str(BOOKING_1_ID),
                    "created_at": "2026-10-02T10:00:00Z",
                    "updated_at": "2026-10-02T10:00:00Z",
                }
                insert_query.execute.return_value = MagicMock(data=[inserted_booking])
            elif table_name == "booking_items":
                saved_items = [
                    {
                        **item,
                        "id": str(uuid.uuid4()),
                        "created_at": "2026-10-02T10:00:00Z",
                    }
                    for item in payload
                ]
                insert_query.execute.return_value = MagicMock(data=saved_items)
            return insert_query

        query.insert.side_effect = insert_effect

        def delete_effect():
            del_query = MagicMock()
            del_query.eq.return_value = del_query
            del_query.execute.return_value = MagicMock(data=[])
            return del_query

        query.delete.side_effect = delete_effect

        return query

    mock_client.table.side_effect = table_mock_factory
    return mock_client


# ==============================================================================
# 1. Successful Booking Creation
# ==============================================================================

@pytest.mark.asyncio
async def test_successful_booking_creation(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Customer can successfully create a booking with authoritative pricing."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [
            {
                "service_id": str(SERVICE_CAR_ID),
                "quantity": 1,
                "notes": "Check engine noise",
            }
        ],
        "customer_notes": "Please park at designated visitor spot",
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 201
        data = res.json()

        assert data["booking_number"].startswith("BK-")
        assert data["customer_id"] == str(CUSTOMER_1_ID)
        assert data["vehicle_id"] == str(VEHICLE_1_ID)
        assert data["address_id"] == str(ADDRESS_1_ID)
        assert data["booking_status"] == "pending"
        assert data["payment_status"] == "unpaid"
        assert Decimal(str(data["subtotal"])) == Decimal("1499.50")
        assert Decimal(str(data["total_amount"])) == Decimal("1499.50")
        assert Decimal(str(data["tax_amount"])) == Decimal("0.00")
        assert Decimal(str(data["discount_amount"])) == Decimal("0.00")
        assert len(data["items"]) == 1
        assert data["items"][0]["service_name"] == "Periodic General Service"
        assert Decimal(str(data["items"][0]["unit_price"])) == Decimal("1499.50")
        assert Decimal(str(data["items"][0]["total_price"])) == Decimal("1499.50")


# ==============================================================================
# 2. Unauthenticated Booking Creation -> 401
# ==============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_booking_creation_returns_401(async_client: AsyncClient):
    """Booking creation without credentials must return 401 Unauthorized."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }
    res = await async_client.post("/api/v1/bookings", json=payload)
    assert res.status_code == 401


# ==============================================================================
# 3. Invalid Vehicle -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_vehicle_returns_404(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Booking with nonexistent vehicle must return 404."""
    NONEXISTENT_VEHICLE_ID = uuid.uuid4()
    payload = {
        "vehicle_id": str(NONEXISTENT_VEHICLE_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 404
        assert "vehicle not found" in res.json()["detail"].lower()


# ==============================================================================
# 4. Vehicle Belonging to Another Customer -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_vehicle_belonging_to_another_customer_returns_404(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Customer 1 attempting to book with Customer 2's vehicle must return 404 without leaking info."""
    payload = {
        "vehicle_id": str(VEHICLE_2_ID),  # Owned by Customer 2
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 404
        assert "vehicle not found" in res.json()["detail"].lower()


# ==============================================================================
# 5. Invalid Address -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_address_returns_404(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Booking with nonexistent address must return 404."""
    NONEXISTENT_ADDR_ID = uuid.uuid4()
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(NONEXISTENT_ADDR_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 404
        assert "address not found" in res.json()["detail"].lower()


# ==============================================================================
# 6. Address Belonging to Another Customer -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_address_belonging_to_another_customer_returns_404(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Customer 1 attempting to book with Customer 2's address must return 404 without leaking info."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_2_ID),  # Owned by Customer 2
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 404
        assert "address not found" in res.json()["detail"].lower()


# ==============================================================================
# 7. Inactive Service -> 400 Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_inactive_service_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Attempting to book an inactive service must return 400 Bad Request."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_INACTIVE_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 400
        assert "inactive" in res.json()["detail"].lower()


# ==============================================================================
# 8. Incompatible Service / Vehicle -> 400 Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_incompatible_service_vehicle_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Attempting to book a bike-only service for a car must return 400 Bad Request."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),  # Car
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_BIKE_ID), "quantity": 1}],  # Bike only
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 400
        assert "two-wheelers" in res.json()["detail"].lower()


# ==============================================================================
# 9. Missing Pricing -> 400 Rejection
# ==============================================================================

@pytest.mark.asyncio
async def test_missing_pricing_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Attempting to book a service with unconfigured pricing must return 400 Bad Request."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_NO_PRICE_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 400
        assert "pricing" in res.json()["detail"].lower()


# ==============================================================================
# 10. Quantity <= 0 -> 422 Validation Error
# ==============================================================================

@pytest.mark.asyncio
async def test_quantity_zero_or_negative_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Quantity must be positive integer; 0 or negative must return 422."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 0}],
    }

    res = await async_client.post("/api/v1/bookings", json=payload)
    assert res.status_code == 422


# ==============================================================================
# 11. Client-Supplied Price Ignored / Rejected
# ==============================================================================

@pytest.mark.asyncio
async def test_client_supplied_price_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Client cannot supply unit_price or total_amount; extra=forbid rejects with 422."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [
            {
                "service_id": str(SERVICE_CAR_ID),
                "quantity": 1,
                "unit_price": "1.00",  # Attacker attempt
            }
        ],
        "total_amount": "1.00",  # Attacker attempt
    }

    res = await async_client.post("/api/v1/bookings", json=payload)
    assert res.status_code == 422


# ==============================================================================
# 12. Client-Supplied customer_id Ignored / Rejected
# ==============================================================================

@pytest.mark.asyncio
async def test_client_supplied_customer_id_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Client cannot override customer_id in request body; extra=forbid rejects with 422."""
    payload = {
        "customer_id": str(CUSTOMER_2_ID),  # Attacker attempt to book for another user
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    res = await async_client.post("/api/v1/bookings", json=payload)
    assert res.status_code == 422


# ==============================================================================
# 13. Correct Decimal Subtotal & 14. Multiple Booking Items
# ==============================================================================

@pytest.mark.asyncio
async def test_multiple_booking_items_and_decimal_totals(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """
    Multiple items calculate exact Decimal line totals and subtotal.
    Item 1: 1499.50 * 2 = 2999.00
    Item 2: 850.25 * 3 = 2550.75
    Subtotal: 2999.00 + 2550.75 = 5549.75
    """
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [
            {"service_id": str(SERVICE_CAR_ID), "quantity": 2},
            {"service_id": str(SERVICE_EXTRA_ID), "quantity": 3},
        ],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 201
        data = res.json()

        assert len(data["items"]) == 2
        item_1 = next(i for i in data["items"] if i["service_id"] == str(SERVICE_CAR_ID))
        item_2 = next(i for i in data["items"] if i["service_id"] == str(SERVICE_EXTRA_ID))

        assert Decimal(str(item_1["unit_price"])) == Decimal("1499.50")
        assert Decimal(str(item_1["total_price"])) == Decimal("2999.00")

        assert Decimal(str(item_2["unit_price"])) == Decimal("850.25")
        assert Decimal(str(item_2["total_price"])) == Decimal("2550.75")

        assert Decimal(str(data["subtotal"])) == Decimal("5549.75")
        assert Decimal(str(data["total_amount"])) == Decimal("5549.75")


# ==============================================================================
# 15. Duplicate Service Items Rejected
# ==============================================================================

@pytest.mark.asyncio
async def test_duplicate_service_items_rejected(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Passing duplicate service_id in the items array must return 400 Bad Request."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [
            {"service_id": str(SERVICE_CAR_ID), "quantity": 1},
            {"service_id": str(SERVICE_CAR_ID), "quantity": 2},
        ],
    }

    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 400
        assert "duplicate" in res.json()["detail"].lower()


# ==============================================================================
# 16. Initial Booking Status & 17. Booking Ownership on GET
# ==============================================================================

@pytest.mark.asyncio
async def test_get_booking_ownership_success(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Customer can view their own booking with items."""
    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}")
        assert res.status_code == 200
        data = res.json()

        assert data["id"] == str(BOOKING_1_ID)
        assert data["customer_id"] == str(CUSTOMER_1_ID)
        assert data["booking_status"] == "pending"
        assert data["payment_status"] == "unpaid"
        assert len(data["items"]) == 1
        assert data["items"][0]["service_name"] == "Periodic General Service"


# ==============================================================================
# 18. Cross-Customer Booking Access -> 404
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_customer_booking_access_returns_404(async_client: AsyncClient, mock_other_customer: AuthenticatedUser):
    """Customer 2 accessing Customer 1's booking must return 404 without leaking info."""
    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ==============================================================================
# 19. Customer List My-Bookings
# ==============================================================================

@pytest.mark.asyncio
async def test_list_my_bookings(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """Customer can list their bookings via /my-bookings."""
    mock_db = build_mock_db_client()
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/bookings/my-bookings")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["id"] == str(BOOKING_1_ID)
        assert data[0]["customer_id"] == str(CUSTOMER_1_ID)


# ==============================================================================
# 20. Compensating Delete Rollback on Item Insertion Failure
# ==============================================================================

@pytest.mark.asyncio
async def test_compensating_delete_on_items_insert_failure(async_client: AsyncClient, mock_customer: AuthenticatedUser):
    """If booking_items insert fails, booking header must be rolled back via compensating delete."""
    payload = {
        "vehicle_id": str(VEHICLE_1_ID),
        "address_id": str(ADDRESS_1_ID),
        "items": [{"service_id": str(SERVICE_CAR_ID), "quantity": 1}],
    }

    mock_db = build_mock_db_client()

    # Configure booking_items insert to throw an error
    def faulty_table(table_name):
        query = mock_db.table.side_effect(table_name)
        if table_name == "booking_items":
            query.insert.side_effect = Exception("DB network connection timeout")
        return query

    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.booking_pricing_service.get_supabase_service_client", return_value=mock_db):

        # Re-assign side effect with faulty booking_items
        orig_side_effect = mock_db.table.side_effect
        def table_with_error(name):
            t = orig_side_effect(name)
            if name == "booking_items":
                t.insert.side_effect = Exception("DB network connection timeout")
            return t

        mock_db.table.side_effect = table_with_error

        res = await async_client.post("/api/v1/bookings", json=payload)
        assert res.status_code == 500
        assert "rolled back" in res.json()["detail"].lower()
