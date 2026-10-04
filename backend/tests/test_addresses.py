"""
Customer Address Management Tests.

Tests address CRUD, ownership isolation, default address promotion,
and historical booking reference protection.
"""

from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID

ADDRESS_1_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
ADDRESS_2_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")


@pytest.mark.asyncio
async def test_unauthenticated_address_request_returns_401(async_client: AsyncClient):
    """Accessing customer addresses without JWT returns 401."""
    res = await async_client.get("/api/v1/addresses")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_customer_can_list_own_addresses(async_client: AsyncClient, mock_customer):
    """Customer can retrieve list of saved addresses."""
    mock_addresses = [
        {
            "id": str(ADDRESS_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "label": "Home",
            "address_line": "Flat 402, Green Towers",
            "area": "HSR Layout",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560102",
            "latitude": 12.9141,
            "longitude": 77.6511,
            "landmark": "Near BDA Complex",
            "is_default": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    ]

    with patch("app.services.address_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.order.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=mock_addresses)

        res = await async_client.get("/api/v1/addresses")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["label"] == "Home"
        assert data[0]["is_default"] is True


@pytest.mark.asyncio
async def test_customer_cannot_access_other_customer_address(async_client: AsyncClient, mock_customer):
    """Customer attempting to fetch another customer's address receives 404."""
    other_address = {
        "id": str(ADDRESS_2_ID),
        "customer_id": str(CUSTOMER_2_ID),  # Owned by Customer 2
        "label": "Office",
        "address_line": "Building 5, Tech Park",
        "area": "Whitefield",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560066",
        "latitude": 12.9850,
        "longitude": 77.7300,
        "is_default": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.address_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[other_address])

        res = await async_client.get(f"/api/v1/addresses/{ADDRESS_2_ID}")
        assert res.status_code == 404
        assert "not found" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_address_default_promotion(async_client: AsyncClient, mock_customer):
    """Creating customer's first address automatically sets it as default."""
    created_record = {
        "id": str(ADDRESS_1_ID),
        "customer_id": str(CUSTOMER_1_ID),
        "label": "Home",
        "address_line": "Flat 402, Green Towers",
        "area": "HSR Layout",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560102",
        "latitude": 12.9141,
        "longitude": 77.6511,
        "landmark": None,
        "is_default": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.address_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.insert.return_value = mock_table
        # Simulate 0 existing addresses
        mock_table.execute.side_effect = [
            MagicMock(data=[]),  # count check
            MagicMock(data=[created_record]),  # insert result
        ]

        payload = {
            "label": "Home",
            "address_line": "Flat 402, Green Towers",
            "area": "HSR Layout",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560102",
            "latitude": 12.9141,
            "longitude": 77.6511,
            "is_default": False,  # Customer didn't request default, but being first it is promoted
        }

        res = await async_client.post("/api/v1/addresses", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert data["is_default"] is True


@pytest.mark.asyncio
async def test_address_deletion_blocked_if_historical_bookings_exist(async_client: AsyncClient, mock_customer):
    """Deleting an address referenced by existing service bookings returns 400 Bad Request."""
    own_address = {
        "id": str(ADDRESS_1_ID),
        "customer_id": str(CUSTOMER_1_ID),
        "label": "Home",
        "address_line": "123 Street",
        "area": "Indiranagar",
        "city": "Bengaluru",
        "state": "Karnataka",
        "postal_code": "560038",
        "latitude": 12.9784,
        "longitude": 77.6408,
        "is_default": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.address_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            sub_mock.limit.return_value = sub_mock
            if table_name == "addresses":
                sub_mock.execute.return_value = MagicMock(data=[own_address])
            elif table_name == "bookings":
                # Simulated historical booking referencing address
                sub_mock.execute.return_value = MagicMock(data=[{"id": str(uuid.uuid4())}])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.delete(f"/api/v1/addresses/{ADDRESS_1_ID}")
        assert res.status_code == 400
        assert "associated with existing service bookings" in res.json()["detail"].lower()
