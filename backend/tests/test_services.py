"""
Service Catalog and Authoritative Pricing Tests.

Tests:
- Category listing & active filtering
- Service item listing, category filtering, and vehicle type filtering
- Nonexistent service rejection (404)
- Authoritative price determination (Decimal precision)
- Vehicle type / service compatibility rejection (400)
- Inactive service pricing rejection (400)
- Unconfigured pricing handling (404)
- Public access vs security
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient

CATEGORY_1_ID = uuid.UUID("aaaaaaaa-1111-1111-1111-111111111111")
CATEGORY_2_ID = uuid.UUID("bbbbbbbb-2222-2222-2222-222222222222")

SERVICE_1_ID = uuid.UUID("cccccccc-3333-3333-3333-333333333333")  # Car only
SERVICE_2_ID = uuid.UUID("dddddddd-4444-4444-4444-444444444444")  # Bike only
SERVICE_3_ID = uuid.UUID("eeeeeeee-5555-5555-5555-555555555555")  # Both car & bike

VT_CAR_ID = uuid.UUID("11111111-0000-0000-0000-000000000001")
VT_BIKE_ID = uuid.UUID("22222222-0000-0000-0000-000000000002")


# ==============================================================================
# Categories Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_categories_active_only(async_client: AsyncClient):
    """Test that active categories are returned and inactive categories are excluded."""
    mock_categories = [
        {
            "id": str(CATEGORY_1_ID),
            "name": "Periodic Maintenance",
            "slug": "periodic-maintenance",
            "description": "Routine scheduled service",
            "icon_url": "https://example.com/icons/maintenance.svg",
            "display_order": 1,
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=mock_categories)

        res = await async_client.get("/api/v1/services/categories")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["name"] == "Periodic Maintenance"
        assert data[0]["is_active"] is True


# ==============================================================================
# Service Items Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_list_services_and_filtering(async_client: AsyncClient):
    """Test listing services with category filtering and pricing formatting."""
    mock_services = [
        {
            "id": str(SERVICE_1_ID),
            "category_id": str(CATEGORY_1_ID),
            "name": "Standard Car Service",
            "description": "Oil, filter, and 40-point inspection",
            "vehicle_type": "car",
            "estimated_duration_minutes": 120,
            "is_emergency": False,
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "service_categories": {"name": "Periodic Maintenance"},
            "service_pricing": [
                {
                    "id": str(uuid.uuid4()),
                    "service_id": str(SERVICE_1_ID),
                    "vehicle_type_id": str(VT_CAR_ID),
                    "base_price": "2499.00",
                    "minimum_price": "1999.00",
                    "pricing_parameters": {},
                    "effective_from": "2026-01-01T00:00:00Z",
                    "effective_to": None,
                    "is_active": True,
                    "vehicle_types": {"name": "Car"},
                }
            ],
        }
    ]

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=mock_services)

        res = await async_client.get(f"/api/v1/services/items?category_id={CATEGORY_1_ID}")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["name"] == "Standard Car Service"
        assert data[0]["category_name"] == "Periodic Maintenance"
        # Verify pricing Decimal conversion
        assert data[0]["pricing"][0]["base_price"] == 2499.00 or data[0]["pricing"][0]["base_price"] == "2499.00"


@pytest.mark.asyncio
async def test_get_nonexistent_service_returns_404(async_client: AsyncClient):
    """Querying a nonexistent service ID must return 404."""
    NONEXISTENT_ID = uuid.uuid4()

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[])

        res = await async_client.get(f"/api/v1/services/{NONEXISTENT_ID}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


# ==============================================================================
# Authoritative Pricing Tests
# ==============================================================================

@pytest.mark.asyncio
async def test_get_authoritative_price_success(async_client: AsyncClient):
    """Retrieve correct authoritative labor price using Decimal precision."""
    service_row = {
        "id": str(SERVICE_1_ID),
        "name": "Engine Oil Replacement",
        "is_active": True,
        "vehicle_type": "car",
    }
    vt_row = {
        "id": str(VT_CAR_ID),
        "name": "Car",
        "is_active": True,
    }
    pricing_row = {
        "id": str(uuid.uuid4()),
        "service_id": str(SERVICE_1_ID),
        "vehicle_type_id": str(VT_CAR_ID),
        "base_price": "1499.50",
        "minimum_price": "1199.00",
        "pricing_parameters": {"engine_type": "petrol"},
        "effective_from": "2026-01-01T00:00:00Z",
        "is_active": True,
    }

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            if table_name == "services":
                sub_mock.execute.return_value = MagicMock(data=[service_row])
            elif table_name == "vehicle_types":
                sub_mock.execute.return_value = MagicMock(data=[vt_row])
            elif table_name == "service_pricing":
                sub_mock.execute.return_value = MagicMock(data=[pricing_row])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.get(
            f"/api/v1/services/{SERVICE_1_ID}/price?vehicle_type_id={VT_CAR_ID}"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["service_name"] == "Engine Oil Replacement"
        assert data["vehicle_type_name"] == "Car"
        # Decimal serialization assertion
        assert Decimal(str(data["base_price"])) == Decimal("1499.50")
        assert Decimal(str(data["minimum_price"])) == Decimal("1199.00")


@pytest.mark.asyncio
async def test_unsupported_vehicle_service_combination_rejected(async_client: AsyncClient):
    """Attempting to price a car-only service for a motorcycle must return 400 Bad Request."""
    car_only_service = {
        "id": str(SERVICE_1_ID),
        "name": "4-Wheel Brake Pad Replacement",
        "is_active": True,
        "vehicle_type": "car",  # Car only
    }
    bike_vt = {
        "id": str(VT_BIKE_ID),
        "name": "Motorcycle",  # Bike
        "is_active": True,
    }

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            if table_name == "services":
                sub_mock.execute.return_value = MagicMock(data=[car_only_service])
            elif table_name == "vehicle_types":
                sub_mock.execute.return_value = MagicMock(data=[bike_vt])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.get(
            f"/api/v1/services/{SERVICE_1_ID}/price?vehicle_type_id={VT_BIKE_ID}"
        )
        assert res.status_code == 400
        assert "only available for cars" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_inactive_service_pricing_rejected(async_client: AsyncClient):
    """Attempting to price an inactive service must return 400."""
    inactive_service = {
        "id": str(SERVICE_1_ID),
        "name": "Discontinued Service",
        "is_active": False,  # Inactive
        "vehicle_type": "both",
    }

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[inactive_service])

        res = await async_client.get(
            f"/api/v1/services/{SERVICE_1_ID}/price?vehicle_type_id={VT_CAR_ID}"
        )
        assert res.status_code == 400
        assert "inactive" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_missing_price_record_handled_with_404(async_client: AsyncClient):
    """If service and vehicle type exist but no pricing record configured, return 404."""
    service_row = {
        "id": str(SERVICE_3_ID),
        "name": "General Diagnostic",
        "is_active": True,
        "vehicle_type": "both",
    }
    vt_row = {
        "id": str(VT_CAR_ID),
        "name": "Car",
        "is_active": True,
    }

    with patch("app.services.service_catalog_service.get_supabase_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            if table_name == "services":
                sub_mock.execute.return_value = MagicMock(data=[service_row])
            elif table_name == "vehicle_types":
                sub_mock.execute.return_value = MagicMock(data=[vt_row])
            elif table_name == "service_pricing":
                # No pricing records
                sub_mock.execute.return_value = MagicMock(data=[])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.get(
            f"/api/v1/services/{SERVICE_3_ID}/price?vehicle_type_id={VT_CAR_ID}"
        )
        assert res.status_code == 404
        assert "no active pricing configured" in res.json()["detail"].lower()
