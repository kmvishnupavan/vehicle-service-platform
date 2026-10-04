"""
Customer Vehicle Management Tests.

Tests ownership isolation, catalog relationships, registration number normalization,
and foreign-key booking protection.
"""

from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID

VEHICLE_1_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VEHICLE_2_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TYPE_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
BRAND_ID = uuid.UUID("20000000-0000-0000-0000-000000000002")
MODEL_ID = uuid.UUID("30000000-0000-0000-0000-000000000003")


# ==============================================================================
# Authentication Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_vehicle_request_returns_401(async_client: AsyncClient):
    """Accessing customer vehicle endpoints without token must return 401."""
    res = await async_client.get("/api/v1/vehicles/my-vehicles")
    assert res.status_code == 401

    res = await async_client.post("/api/v1/vehicles", json={})
    assert res.status_code == 401


# ==============================================================================
# Ownership Isolation Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_customer_can_list_own_vehicles(async_client: AsyncClient, mock_customer):
    """Customer can retrieve list of vehicles registered to their account."""
    mock_vehicles = [
        {
            "id": str(VEHICLE_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "vehicle_type_id": str(TYPE_ID),
            "brand_id": str(BRAND_ID),
            "model_id": str(MODEL_ID),
            "registration_number": "KA01AB1234",
            "nickname": "Daily Car",
            "manufacture_year": 2022,
            "color": "Silver",
            "fuel_type": "petrol",
            "odometer_km": 15000,
            "is_primary": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "vehicle_brands": {"name": "Honda"},
            "vehicle_models": {"name": "City"},
            "vehicle_types": {"name": "Car"},
        }
    ]

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=mock_vehicles)

        res = await async_client.get("/api/v1/vehicles/my-vehicles")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["registration_number"] == "KA01AB1234"
        assert data[0]["brand_name"] == "Honda"
        assert data[0]["model_name"] == "City"


@pytest.mark.asyncio
async def test_customer_cannot_access_other_customer_vehicle(async_client: AsyncClient, mock_customer):
    """Customer attempting to fetch another customer's vehicle receives 404 (not found)."""
    other_vehicle = {
        "id": str(VEHICLE_2_ID),
        "customer_id": str(CUSTOMER_2_ID),  # Owned by Customer 2
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "TS09CD5678",
        "is_primary": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[other_vehicle])

        res = await async_client.get(f"/api/v1/vehicles/{VEHICLE_2_ID}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_customer_cannot_modify_other_customer_vehicle(async_client: AsyncClient, mock_customer):
    """Customer attempting to modify another customer's vehicle receives 404."""
    other_vehicle = {
        "id": str(VEHICLE_2_ID),
        "customer_id": str(CUSTOMER_2_ID),
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "TS09CD5678",
        "is_primary": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[other_vehicle])

        res = await async_client.patch(
            f"/api/v1/vehicles/{VEHICLE_2_ID}",
            json={"color": "Red"},
        )
        assert res.status_code == 404


@pytest.mark.asyncio
async def test_customer_cannot_delete_other_customer_vehicle(async_client: AsyncClient, mock_customer):
    """Customer attempting to delete another customer's vehicle receives 404."""
    other_vehicle = {
        "id": str(VEHICLE_2_ID),
        "customer_id": str(CUSTOMER_2_ID),
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "TS09CD5678",
        "is_primary": False,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[other_vehicle])

        res = await async_client.delete(f"/api/v1/vehicles/{VEHICLE_2_ID}")
        assert res.status_code == 404


# ==============================================================================
# Validation & Registration Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_invalid_model_brand_combination_rejected(async_client: AsyncClient, mock_customer):
    """Creating a vehicle with a model that does not belong to the brand must return 400."""
    WRONG_BRAND_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table

        # Return active vehicle_type, active brand, but model having different brand_id
        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            if table_name == "vehicle_types":
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(TYPE_ID), "is_active": True}])
            elif table_name == "vehicle_brands":
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(WRONG_BRAND_ID), "is_active": True}])
            elif table_name == "vehicle_models":
                # Model belongs to BRAND_ID, NOT WRONG_BRAND_ID
                sub_mock.execute.return_value = MagicMock(
                    data=[{"id": str(MODEL_ID), "brand_id": str(BRAND_ID), "vehicle_type_id": str(TYPE_ID), "is_active": True}]
                )
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        payload = {
            "vehicle_type_id": str(TYPE_ID),
            "brand_id": str(WRONG_BRAND_ID),
            "model_id": str(MODEL_ID),
            "registration_number": "TS 09 AB 1234",
            "manufacture_year": 2023,
            "color": "Black",
        }
        res = await async_client.post("/api/v1/vehicles", json=payload)
        assert res.status_code == 400
        assert "does not belong" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_invalid_vehicle_input_rejected(async_client: AsyncClient, mock_customer):
    """Manufacture year before 1970 or empty registration number must return 422."""
    payload_bad_year = {
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "TS09AB1234",
        "manufacture_year": 1950,  # Invalid
    }
    res = await async_client.post("/api/v1/vehicles", json=payload_bad_year)
    assert res.status_code == 422

    payload_empty_reg = {
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "   ",  # Invalid
    }
    res = await async_client.post("/api/v1/vehicles", json=payload_empty_reg)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_registration_number_normalization(async_client: AsyncClient, mock_customer):
    """Registration numbers with spaces/hyphens are normalized to uppercase alphanumeric."""
    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        inserted_record = {
            "id": str(VEHICLE_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "vehicle_type_id": str(TYPE_ID),
            "brand_id": str(BRAND_ID),
            "model_id": str(MODEL_ID),
            "registration_number": "TS09AB1234",
            "is_primary": False,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }

        mock_vehicles_table = MagicMock()
        mock_vehicles_table.select.return_value = mock_vehicles_table
        mock_vehicles_table.eq.return_value = mock_vehicles_table
        mock_vehicles_table.order.return_value = mock_vehicles_table
        mock_vehicles_table.insert.return_value.execute.return_value = MagicMock(data=[inserted_record])
        mock_vehicles_table.execute.side_effect = [
            MagicMock(data=[]),  # duplicate check returns empty
            MagicMock(data=[inserted_record]),  # get_customer_vehicle returns created record
        ]

        def table_side_effect(table_name):
            if table_name == "vehicles":
                return mock_vehicles_table
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            sub_mock.order.return_value = sub_mock
            if table_name == "vehicle_types":
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(TYPE_ID), "is_active": True}])
            elif table_name == "vehicle_brands":
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(BRAND_ID), "is_active": True}])
            elif table_name == "vehicle_models":
                sub_mock.execute.return_value = MagicMock(
                    data=[{"id": str(MODEL_ID), "brand_id": str(BRAND_ID), "vehicle_type_id": str(TYPE_ID), "is_active": True}]
                )
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        payload = {
            "vehicle_type_id": str(TYPE_ID),
            "brand_id": str(BRAND_ID),
            "model_id": str(MODEL_ID),
            "registration_number": "ts - 09 ab 1234",
            "manufacture_year": 2024,
            "color": "Pearl White",
        }
        res = await async_client.post("/api/v1/vehicles", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["registration_number"] == "TS09AB1234"


@pytest.mark.asyncio
async def test_vehicle_deletion_blocked_if_historical_bookings_exist(async_client: AsyncClient, mock_customer):
    """Deleting a vehicle referenced by existing bookings must return 400 Bad Request."""
    own_vehicle = {
        "id": str(VEHICLE_1_ID),
        "customer_id": str(CUSTOMER_1_ID),
        "vehicle_type_id": str(TYPE_ID),
        "brand_id": str(BRAND_ID),
        "model_id": str(MODEL_ID),
        "registration_number": "KA01AB1234",
        "is_primary": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.vehicle_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            sub_mock.limit.return_value = sub_mock
            if table_name == "vehicles":
                sub_mock.execute.return_value = MagicMock(data=[own_vehicle])
            elif table_name == "bookings":
                # Simulated historical booking referencing this vehicle
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.delete(f"/api/v1/vehicles/{VEHICLE_1_ID}")
        assert res.status_code == 400
        assert "associated with existing service bookings" in res.json()["detail"].lower()
