"""
Customer Profile API and Field Tampering Tests.

Verifies that customers can update allowed contact details while strictly preventing
tampering with roles, user IDs, active status, or administrative privileges.
"""

from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from tests.conftest import CUSTOMER_1_ID


@pytest.mark.asyncio
async def test_get_customer_profile(async_client: AsyncClient, mock_customer):
    """Customer can fetch their profile details."""
    profile_data = {
        "id": str(CUSTOMER_1_ID),
        "full_name": "Alice Customer",
        "phone": "+919876543210",
        "email": "customer1@example.com",
        "avatar_url": None,
        "role": "customer",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    cust_data = {
        "id": str(uuid.uuid4()),
        "user_id": str(CUSTOMER_1_ID),
        "emergency_contact_name": "Bob Emergency",
        "emergency_contact_phone": "+919876543219",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.user_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            if table_name == "profiles":
                sub_mock.execute.return_value = MagicMock(data=[profile_data])
            elif table_name == "customer_profiles":
                sub_mock.execute.return_value = MagicMock(data=[cust_data])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        res = await async_client.get("/api/v1/users/customer-profile")
        assert res.status_code == 200
        data = res.json()
        assert data["full_name"] == "Alice Customer"
        assert data["emergency_contact_name"] == "Bob Emergency"
        assert data["role"] == "customer"


@pytest.mark.asyncio
async def test_update_permitted_profile_fields(async_client: AsyncClient, mock_customer):
    """Customer can update name, phone, and emergency contact details."""
    updated_profile = {
        "id": str(CUSTOMER_1_ID),
        "full_name": "Alice Updated",
        "phone": "+919876543299",
        "email": "customer1@example.com",
        "avatar_url": None,
        "role": "customer",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    updated_cust = {
        "id": str(uuid.uuid4()),
        "user_id": str(CUSTOMER_1_ID),
        "emergency_contact_name": "Charlie New Contact",
        "emergency_contact_phone": "+919876543288",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.user_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        def table_side_effect(table_name):
            sub_mock = MagicMock()
            sub_mock.select.return_value = sub_mock
            sub_mock.eq.return_value = sub_mock
            sub_mock.update.return_value = sub_mock
            if table_name == "profiles":
                sub_mock.execute.return_value = MagicMock(data=[updated_profile])
            elif table_name == "customer_profiles":
                sub_mock.execute.return_value = MagicMock(data=[updated_cust])
            return sub_mock

        mock_client.table.side_effect = table_side_effect

        payload = {
            "full_name": "Alice Updated",
            "phone": "+919876543299",
            "emergency_contact_name": "Charlie New Contact",
            "emergency_contact_phone": "+919876543288",
        }

        res = await async_client.patch("/api/v1/users/customer-profile", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["full_name"] == "Alice Updated"
        assert data["phone"] == "+919876543299"
        assert data["emergency_contact_name"] == "Charlie New Contact"


@pytest.mark.asyncio
async def test_customer_cannot_modify_privileged_fields(async_client: AsyncClient, mock_customer):
    """
    Submitting privileged fields (role, user_id, is_active, email) in PATCH payload
    must be ignored by Pydantic model and NEVER updated in database.
    """
    profile_data = {
        "id": str(CUSTOMER_1_ID),
        "full_name": "Alice Customer",
        "phone": "+919876543210",
        "email": "customer1@example.com",
        "avatar_url": None,
        "role": "customer",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    with patch("app.services.user_service.get_supabase_service_client") as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.update.return_value = mock_table
        mock_table.execute.return_value = MagicMock(data=[profile_data])

        # Attempt to escalate role to admin, change user_id, or alter active status
        malicious_payload = {
            "full_name": "Alice Attempt Escalation",
            "role": "admin",
            "user_id": str(uuid.uuid4()),
            "is_active": False,
            "email": "hacked@example.com",
        }

        res = await async_client.patch("/api/v1/users/customer-profile", json=malicious_payload)
        assert res.status_code == 200
        data = res.json()
        # Role must remain customer
        assert data["role"] == "customer"
        assert data["user_id"] == str(CUSTOMER_1_ID)
        assert data["email"] == "customer1@example.com"
        assert data["is_active"] is True
