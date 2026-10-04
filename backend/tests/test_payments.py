"""
Comprehensive Payment & Invoice Integration Tests (Phase 8).

Covers all 43 required verification scenarios:
A. Authentication (Tests 1-3)
B. Authorization (Tests 4-6)
C. Amount Integrity (Tests 7-10)
D. Cryptographic Signature (Tests 11-14)
E. Payment Settlement (Tests 15-20)
F. Idempotency (Tests 21-25)
G. Failure Handling (Tests 26-28)
H. Webhook Handling & Idempotency (Tests 29-34)
I. Invoice Production Quality (Tests 35-40)
J. Concurrency & Race Condition Safety (Tests 41-43)
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
from typing import Any
import uuid
import pytest
from httpx import AsyncClient
from app.core.config import Settings
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from tests.conftest import CUSTOMER_1_ID, CUSTOMER_2_ID, MECHANIC_ID

TEST_KEY_ID = "rzp_test_mock_key_id_12345"
TEST_KEY_SECRET = "mock_razorpay_secret_key_for_testing"
TEST_WEBHOOK_SECRET = "mock_razorpay_webhook_secret_for_testing"

BOOKING_TEST_ID = uuid.UUID("baaaaaaa-0000-0000-0000-000000000001")
OTHER_BOOKING_ID = uuid.UUID("baaaaaaa-0000-0000-0000-000000000002")
VEHICLE_TEST_ID = uuid.UUID("bbaaaaaa-0000-0000-0000-000000000001")


def make_payment_signature(order_id: str, payment_id: str, secret: str = TEST_KEY_SECRET) -> str:
    """Generate valid HMAC-SHA256 signature for test order + payment."""
    msg = f"{order_id}|{payment_id}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()


def make_webhook_signature(raw_body: bytes, secret: str = TEST_WEBHOOK_SECRET) -> str:
    """Generate valid HMAC-SHA256 webhook signature for raw request body."""
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


class MockTableQuery:
    """Chainable mock query builder mirroring Supabase PostgREST client."""

    def __init__(self, db_state: dict, table_name: str):
        self.db_state = db_state
        self.table_name = table_name
        self.filters = []
        self.neq_filters = []
        self.select_fields = "*"
        self.order_field = None
        self.limit_val = None
        self._update_data = None
        self._is_delete = False

    def select(self, fields: str = "*"):
        self.select_fields = fields
        return self

    def eq(self, column: str, value: Any):
        self.filters.append((column, value))
        return self

    def neq(self, column: str, value: Any):
        self.neq_filters.append((column, value))
        return self

    def order(self, field: str, desc: bool = False):
        self.order_field = field
        return self

    def limit(self, count: int):
        self.limit_val = count
        return self

    def insert(self, data: dict | list):
        items = [data] if isinstance(data, dict) else data
        rows = self.db_state.setdefault(self.table_name, [])
        for item in items:
            item_copy = dict(item)
            if "id" not in item_copy:
                item_copy["id"] = str(uuid.uuid4())
            # Enforce unique index for payment_transactions (provider, provider_transaction_id)
            if self.table_name == "payment_transactions" and item_copy.get("provider_transaction_id"):
                for existing in rows:
                    if (
                        existing.get("provider") == item_copy.get("provider")
                        and existing.get("provider_transaction_id") == item_copy.get("provider_transaction_id")
                    ):
                        raise Exception('duplicate key value violates unique constraint "uq_payment_transactions_provider_tx"')
            # Enforce unique index for webhook_events (provider, event_id)
            if self.table_name == "webhook_events" and item_copy.get("event_id"):
                for existing in rows:
                    if (
                        existing.get("provider") == item_copy.get("provider")
                        and existing.get("event_id") == item_copy.get("event_id")
                    ):
                        raise Exception('duplicate key value violates unique constraint "uq_webhook_events_provider_event"')
            rows.append(item_copy)
        mock_resp = MagicMock()
        mock_resp.data = items
        return MagicMock(execute=lambda: mock_resp)

    def upsert(self, data: dict | list, on_conflict: str = "", ignore_duplicates: bool = False):
        items = [data] if isinstance(data, dict) else data
        rows = self.db_state.setdefault(self.table_name, [])
        inserted = []
        for item in items:
            item_copy = dict(item)
            if "id" not in item_copy:
                item_copy["id"] = str(uuid.uuid4())

            conflict_cols = [c.strip() for c in on_conflict.split(",") if c.strip()]
            existing_match = None
            if conflict_cols:
                for existing in rows:
                    if all(existing.get(c) == item_copy.get(c) for c in conflict_cols):
                        existing_match = existing
                        break

            if not existing_match and self.table_name == "webhook_events":
                for existing in rows:
                    if existing.get("provider") == item_copy.get("provider") and existing.get("event_id") == item_copy.get("event_id"):
                        existing_match = existing
                        break

            if existing_match:
                if ignore_duplicates:
                    # ON CONFLICT DO NOTHING -> 0 rows inserted
                    continue
                else:
                    existing_match.update(item_copy)
                    inserted.append(existing_match)
            else:
                rows.append(item_copy)
                inserted.append(item_copy)

        mock_resp = MagicMock()
        mock_resp.data = inserted
        return MagicMock(execute=lambda: mock_resp)

    def update(self, data: dict):
        self._update_data = data
        return self

    def delete(self):
        self._is_delete = True
        return self

    def execute(self):
        rows = self.db_state.setdefault(self.table_name, [])
        filtered = []
        for r in rows:
            matches = True
            for col, val in self.filters:
                if "->>" in col:
                    # JSON path query like new_data->>event_id
                    field, subkey = col.split("->>")
                    field_dict = r.get(field) or {}
                    if str(field_dict.get(subkey)) != str(val):
                        matches = False
                        break
                else:
                    if str(r.get(col)) != str(val):
                        matches = False
                        break
            if matches:
                for col, val in self.neq_filters:
                    if "->>" in col:
                        field, subkey = col.split("->>")
                        field_dict = r.get(field) or {}
                        if str(field_dict.get(subkey)) == str(val):
                            matches = False
                            break
                    else:
                        if str(r.get(col)) == str(val):
                            matches = False
                            break
            if matches:
                filtered.append(r)

        if self._is_delete:
            remaining = [r for r in rows if r not in filtered]
            self.db_state[self.table_name] = remaining
            mock_resp = MagicMock()
            mock_resp.data = filtered
            return mock_resp

        if self._update_data is not None:
            for r in filtered:
                r.update(self._update_data)
            mock_resp = MagicMock()
            mock_resp.data = filtered
            return mock_resp

        mock_resp = MagicMock()
        mock_resp.data = filtered[: self.limit_val] if self.limit_val else filtered
        return mock_resp


def build_mock_db(
    booking_status: str = "payment_pending",
    payment_status: str = "unpaid",
    total_amount: str = "1180.00",
    subtotal: str = "1000.00",
    additional_charges: str = "0.00",
    tax_amount: str = "180.00",
    discount_amount: str = "0.00",
    has_invoice: bool = False,
    invoice_status: str = "issued",
    has_payment: bool = False,
    payment_gateway_status: str = "pending",
    order_id: str = "order_mock_test_12345",
):
    """Construct mock database state for testing."""
    db_state = {
        "bookings": [
            {
                "id": str(BOOKING_TEST_ID),
                "customer_id": str(CUSTOMER_1_ID),
                "vehicle_id": str(VEHICLE_TEST_ID),
                "booking_status": booking_status,
                "payment_status": payment_status,
                "subtotal": subtotal,
                "additional_charges": additional_charges,
                "discount_amount": discount_amount,
                "tax_amount": tax_amount,
                "total_amount": total_amount,
                "created_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
            },
            {
                "id": str(OTHER_BOOKING_ID),
                "customer_id": str(CUSTOMER_2_ID),
                "vehicle_id": str(VEHICLE_TEST_ID),
                "booking_status": "payment_pending",
                "payment_status": "unpaid",
                "subtotal": "500.00",
                "additional_charges": "0.00",
                "discount_amount": "0.00",
                "tax_amount": "90.00",
                "total_amount": "590.00",
                "created_at": "2026-10-02T10:00:00Z",
                "updated_at": "2026-10-02T10:00:00Z",
            },
        ],
        "booking_items": [
            {
                "id": str(uuid.uuid4()),
                "booking_id": str(BOOKING_TEST_ID),
                "service_name": "Standard General Service",
                "tier_name": "Comprehensive",
                "unit_price": "1000.00",
                "quantity": 1,
                "total_price": "1000.00",
            }
        ],
        "additional_work_requests": [
            {
                "id": str(uuid.uuid4()),
                "booking_id": str(BOOKING_TEST_ID),
                "description": "Front Brake Pad Replacement",
                "estimated_cost": "500.00",
                "status": "approved",
            },
            {
                "id": str(uuid.uuid4()),
                "booking_id": str(BOOKING_TEST_ID),
                "description": "Cabin Air Filter Replacement",
                "estimated_cost": "300.00",
                "status": "rejected",
            },
        ],
        "profiles": [
            {
                "id": str(CUSTOMER_1_ID),
                "full_name": "Alice Customer",
                "email": "customer1@example.com",
                "phone": "+919876543210",
                "role": "customer",
            }
        ],
        "vehicles": [
            {
                "id": str(VEHICLE_TEST_ID),
                "license_plate": "KA-01-AB-1234",
                "year": 2022,
                "vehicle_models": {
                    "name": "i20",
                    "vehicle_brands": {"name": "Hyundai"},
                },
            }
        ],
        "payments": [],
        "payment_transactions": [],
        "invoices": [],
        "audit_logs": [],
        "webhook_events": [],
    }

    if has_payment:
        db_state["payments"].append({
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_TEST_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "amount": float(total_amount),
            "currency": "INR",
            "status": payment_gateway_status,
            "provider": "razorpay",
            "provider_payment_id": order_id,
            "paid_at": "2026-10-02T12:00:00Z" if payment_gateway_status == "captured" else None,
            "created_at": "2026-10-02T11:00:00Z",
            "updated_at": "2026-10-02T11:00:00Z",
        })

    if has_invoice:
        db_state["invoices"].append({
            "id": str(uuid.uuid4()),
            "invoice_number": "INV-20261002-A1B2C3",
            "booking_id": str(BOOKING_TEST_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "subtotal": float(subtotal),
            "tax": float(tax_amount),
            "discount": float(discount_amount),
            "total": float(total_amount),
            "status": invoice_status,
            "issued_at": "2026-10-02T11:00:00Z",
            "paid_at": "2026-10-02T12:00:00Z" if invoice_status == "paid" else None,
            "created_at": "2026-10-02T11:00:00Z",
            "updated_at": "2026-10-02T11:00:00Z",
        })

    mock_client = MagicMock()
    mock_client.table.side_effect = lambda t: MockTableQuery(db_state, t)
    return mock_client, db_state


def get_mock_razorpay_client(
    order_id: str = "order_mock_test_12345",
    payment_id: str = "pay_mock_test_12345",
    amount_paise: int = 118000,
    status: str = "captured",
):
    """Instantiate mock Razorpay client."""
    rz_client = MagicMock()
    rz_client.order.create.return_value = {
        "id": order_id,
        "amount": amount_paise,
        "currency": "INR",
        "status": "created",
    }
    rz_client.payment.fetch.return_value = {
        "id": payment_id,
        "order_id": order_id,
        "amount": amount_paise,
        "currency": "INR",
        "status": status,
        "method": "card",
    }
    return rz_client


# ==============================================================================
# GROUP A: Authentication Tests (1-3)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_unauthenticated_create_order_rejected(async_client: AsyncClient, override_settings):
    """Test 1: Unauthenticated request to /create-order returns 401."""
    resp = await async_client.post(
        "/api/v1/payments/create-order",
        json={"booking_id": str(BOOKING_TEST_ID)},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_02_unauthenticated_verify_rejected(async_client: AsyncClient, override_settings):
    """Test 2: Unauthenticated request to /verify returns 401."""
    resp = await async_client.post(
        "/api/v1/payments/verify",
        json={
            "booking_id": str(BOOKING_TEST_ID),
            "razorpay_order_id": "order_123",
            "razorpay_payment_id": "pay_123",
            "razorpay_signature": "sig_123",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_03_unauthenticated_invoice_rejected(async_client: AsyncClient, override_settings):
    """Test 3: Unauthenticated request to invoice endpoint returns 401."""
    resp = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")
    assert resp.status_code == 401


# ==============================================================================
# GROUP B: Authorization Tests (4-6)
# ==============================================================================

@pytest.mark.asyncio
async def test_04_customer_cannot_create_payment_for_other_booking(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 4: Customer cannot create order for another customer's booking (returns 404 to avoid leak)."""
    mock_client, db = build_mock_db()
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(OTHER_BOOKING_ID)},
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_05_customer_cannot_retrieve_other_customer_invoice(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 5: Customer cannot retrieve another customer's invoice (returns 403)."""
    mock_client, db = build_mock_db(has_invoice=True)
    # Add invoice belonging to customer 2 for OTHER_BOOKING_ID
    db["invoices"].append({
        "id": str(uuid.uuid4()),
        "invoice_number": "INV-OTHER-001",
        "booking_id": str(OTHER_BOOKING_ID),
        "customer_id": str(CUSTOMER_2_ID),
        "subtotal": 500.0,
        "tax": 90.0,
        "discount": 0.0,
        "total": 590.0,
        "status": "issued",
        "issued_at": "2026-10-02T11:00:00Z",
        "paid_at": None,
        "created_at": "2026-10-02T11:00:00Z",
        "updated_at": "2026-10-02T11:00:00Z",
    })

    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.get(f"/api/v1/payments/booking/{OTHER_BOOKING_ID}/invoice")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_06_mechanic_cannot_access_customer_payment_data(
    async_client: AsyncClient, override_settings, mock_mechanic
):
    """Test 6: Mechanic role is forbidden from customer payment endpoints."""
    mock_client, db = build_mock_db(has_invoice=True)
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        # Create order requires customer
        resp_order = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
        assert resp_order.status_code == 403

        # Invoice requires customer or admin
        resp_inv = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")
        assert resp_inv.status_code == 403


# ==============================================================================
# GROUP C: Amount Integrity Tests (7-10)
# ==============================================================================

@pytest.mark.asyncio
async def test_07_client_cannot_supply_arbitrary_amount(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 7: Client supplying an amount in create-order request is rejected with 422."""
    resp = await async_client.post(
        "/api/v1/payments/create-order",
        json={"booking_id": str(BOOKING_TEST_ID), "amount": 10.00},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_08_backend_uses_booking_total_amount(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 8: Backend computes Razorpay amount strictly from booking.total_amount."""
    mock_client, db = build_mock_db(total_amount="2500.50")
    rz_mock = get_mock_razorpay_client(amount_paise=250050)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["amount"] == 250050  # 2500.50 * 100 paise


@pytest.mark.asyncio
async def test_09_altered_frontend_amount_in_verify_is_rejected(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 9: Passing extra fields (e.g. amount) in verify request is rejected with 422."""
    resp = await async_client.post(
        "/api/v1/payments/verify",
        json={
            "booking_id": str(BOOKING_TEST_ID),
            "razorpay_order_id": "order_12345",
            "razorpay_payment_id": "pay_12345",
            "razorpay_signature": "sig_12345",
            "amount": 100,
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_10_zero_or_negative_booking_total_rejected(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 10: Bookings with zero or negative total amount reject order creation."""
    mock_client, db = build_mock_db(total_amount="0.00")
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
    assert resp.status_code == 400
    assert "greater than zero" in resp.json()["detail"]


# ==============================================================================
# GROUP D: Cryptographic Signature Tests (11-14)
# ==============================================================================

@pytest.mark.asyncio
async def test_11_valid_signature_succeeds(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 11: Valid HMAC-SHA256 signature verifies successfully."""
    order_id = "order_valid_111"
    pay_id = "pay_valid_222"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, total_amount="1180.00")
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id, amount_paise=118000)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


@pytest.mark.asyncio
async def test_12_invalid_signature_fails(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 12: Fraudulent signature fails verification with 400."""
    order_id = "order_fraud_111"
    pay_id = "pay_fraud_222"
    invalid_sig = "fraudulent_signature_hex_1234567890abcdef"

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": invalid_sig,
            },
        )
    assert resp.status_code == 400
    assert "Invalid payment signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_13_altered_order_id_fails(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 13: Altering order_id causes signature mismatch or record mismatch."""
    order_id = "order_original_111"
    pay_id = "pay_test_222"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": "order_tampered_999",
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_14_altered_payment_id_fails(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 14: Altering payment_id invalidates cryptographic HMAC verification."""
    order_id = "order_test_111"
    pay_id = "pay_original_222"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": "pay_tampered_888",
                "razorpay_signature": valid_sig,
            },
        )
    assert resp.status_code == 400
    assert "Invalid payment signature" in resp.json()["detail"]


# ==============================================================================
# GROUP E: Payment Settlement Tests (15-20)
# ==============================================================================

@pytest.mark.asyncio
async def test_15_successful_payment_marks_payment_captured(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 15: Successful payment marks payment status as 'captured'."""
    order_id = "order_settle_15"
    pay_id = "pay_settle_15"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert resp.status_code == 200
    assert db["payments"][0]["status"] == "captured"
    assert db["payments"][0]["paid_at"] is not None


@pytest.mark.asyncio
async def test_16_successful_payment_marks_booking_payment_status_paid(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 16: Successful payment marks booking payment_status as 'paid'."""
    order_id = "order_settle_16"
    pay_id = "pay_settle_16"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert db["bookings"][0]["payment_status"] == "paid"


@pytest.mark.asyncio
async def test_17_successful_payment_marks_booking_booking_status_paid(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 17: Successful payment marks booking booking_status as 'paid'."""
    order_id = "order_settle_17"
    pay_id = "pay_settle_17"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert db["bookings"][0]["booking_status"] == "paid"


@pytest.mark.asyncio
async def test_18_successful_payment_marks_invoice_paid(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 18: Successful payment marks invoice status as 'paid'."""
    order_id = "order_settle_18"
    pay_id = "pay_settle_18"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True, invoice_status="issued")
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    assert db["invoices"][0]["status"] == "paid"
    assert db["invoices"][0]["paid_at"] is not None


@pytest.mark.asyncio
async def test_19_booking_history_not_manually_inserted(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 19: Payment settlement does not insert booking_status_history (handled by DB trigger)."""
    order_id = "order_hist_100"
    pay_id = "pay_hist_200"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
    # Ensure no manual table interaction with booking_status_history
    assert "booking_status_history" not in db


@pytest.mark.asyncio
async def test_20_customer_cannot_directly_set_booking_paid(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 20: Direct attempt to set booking_status to 'paid' via status endpoint is rejected."""
    mock_client, db = build_mock_db(booking_status="payment_pending")
    with patch("app.services.booking_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.patch(
            f"/api/v1/bookings/{BOOKING_TEST_ID}/status",
            json={"new_status": "paid"},
        )
    assert resp.status_code == 400
    assert "reserved for payment" in resp.json()["detail"]


# ==============================================================================
# GROUP F: Idempotency Tests (21-25)
# ==============================================================================

@pytest.mark.asyncio
async def test_21_same_payment_verification_twice_does_not_duplicate_transaction(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 21: Duplicate verification of the same payment does not duplicate transactions."""
    order_id = "order_dup_21"
    pay_id = "pay_dup_21"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp1 = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert resp1.status_code == 200

        resp2 = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_paid"

    assert len(db["payment_transactions"]) == 1


@pytest.mark.asyncio
async def test_22_same_payment_id_cannot_create_two_successful_transactions(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 22: Same payment ID cannot create two successful transaction records."""
    order_id = "order_dup_22"
    pay_id = "pay_dup_22"
    valid_sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )
        await async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": valid_sig,
            },
        )

    successful_txs = [t for t in db["payment_transactions"] if t.get("status") == "successful"]
    assert len(successful_txs) == 1


@pytest.mark.asyncio
async def test_23_already_paid_booking_cannot_create_new_order(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 23: Already-paid booking returns 409 Conflict when attempting to create a new order."""
    mock_client, db = build_mock_db(booking_status="paid", payment_status="paid")
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
    assert resp.status_code == 409
    assert "already been paid" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_24_invoice_is_not_duplicated_on_multiple_orders(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 24: Calling create-order multiple times produces exactly one invoice."""
    mock_client, db = build_mock_db(has_invoice=False)
    rz_mock = get_mock_razorpay_client()

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
        await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )

    # Exactly 1 invoice in database
    assert len(db["invoices"]) == 1


@pytest.mark.asyncio
async def test_25_duplicate_webhook_returns_safely(async_client: AsyncClient, override_settings):
    """Test 25: Replayed webhook event returns already_processed safely."""
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_duplicate_test_101",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dup_evt_202",
                    "order_id": "order_mock_test_12345",
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id="order_mock_test_12345")
    # Pre-populate webhook_events for this event_id (Phase 8.1B database-level reservation)
    db["webhook_events"].append({
        "provider": "razorpay",
        "event_id": "evt_duplicate_test_101",
        "event_type": "payment.captured",
    })

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_processed"


# ==============================================================================
# GROUP G: Failure Tests (26-28)
# ==============================================================================

@pytest.mark.asyncio
async def test_26_failed_payment_updates_correct_records(
    async_client: AsyncClient, override_settings
):
    """Test 26: Failed payment webhook records failure reason and transaction record."""
    order_id = "order_fail_26"
    event_payload = {
        "event": "payment.failed",
        "event_id": "evt_fail_26",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_fail_26",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Insufficient funds in bank account",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert db["payments"][0]["status"] == "failed"
    assert len(db["payment_transactions"]) == 1
    assert db["payment_transactions"][0]["status"] == "failed"
    assert "Insufficient funds" in db["payment_transactions"][0]["failure_reason"]


@pytest.mark.asyncio
async def test_27_failed_payment_does_not_mark_booking_paid(
    async_client: AsyncClient, override_settings
):
    """Test 27: Failed payment does not mark booking_status as paid (remains payment_pending)."""
    order_id = "order_fail_27"
    event_payload = {
        "event": "payment.failed",
        "event_id": "evt_fail_27",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_fail_27",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Payment authorization timed out",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert db["bookings"][0]["payment_status"] == "failed"
    assert db["bookings"][0]["booking_status"] == "payment_pending"


@pytest.mark.asyncio
async def test_28_failed_payment_allows_retry(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 28: Failed payment allows subsequent retry order creation and verification."""
    mock_client, db = build_mock_db(
        booking_status="payment_pending",
        payment_status="failed",
        has_payment=True,
        payment_gateway_status="failed",
    )
    rz_mock = get_mock_razorpay_client(order_id="order_retry_999")

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
    assert resp.status_code == 201
    assert resp.json()["order_id"] == "order_retry_999"


# ==============================================================================
# GROUP H: Webhook Tests (29-34)
# ==============================================================================

@pytest.mark.asyncio
async def test_29_invalid_webhook_signature_rejected(async_client: AsyncClient, override_settings):
    """Test 29: Invalid webhook signature returns 400 Bad Request."""
    raw_body = b'{"event": "payment.captured"}'
    resp = await async_client.post(
        "/api/v1/payments/webhook",
        content=raw_body,
        headers={"X-Razorpay-Signature": "invalid_signature_hex", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert "Invalid webhook signature" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_30_valid_webhook_accepted(async_client: AsyncClient, override_settings):
    """Test 30: Valid webhook signature processes successfully and returns 200."""
    order_id = "order_hook_1"
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_valid_hook_1",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_hook_1",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"


@pytest.mark.asyncio
async def test_31_duplicate_webhook_handled_idempotently(async_client: AsyncClient, override_settings):
    """Test 31: Duplicate webhook processed identically without duplicate DB mutations."""
    order_id = "order_dup_hook"
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_dup_31",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_dup_31",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        # 1st call
        resp1 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "processed"

        # 2nd call (duplicate)
        resp2 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"


@pytest.mark.asyncio
async def test_32_payment_webhook_updates_correct_booking(async_client: AsyncClient, override_settings):
    """Test 32: Webhook event settles the specific booking tied to the order ID."""
    order_id = "order_specific_32"
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_32",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_32",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    # First booking is paid
    assert db["bookings"][0]["booking_status"] == "paid"
    # Other booking untouched
    assert db["bookings"][1]["booking_status"] == "payment_pending"


@pytest.mark.asyncio
async def test_33_webhook_unrelated_order_ignored_safely(async_client: AsyncClient, override_settings):
    """Test 33: Webhook for unknown order ID is ignored safely without 500 error."""
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_unknown_33",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_unknown_33",
                    "order_id": "order_non_existent_999",
                    "amount": 50000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db()
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_34_malformed_webhook_rejected_safely(async_client: AsyncClient, override_settings):
    """Test 34: Non-JSON raw body with valid signature format rejected with 400."""
    raw_body = b"not-a-valid-json-string"
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db()
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
    assert resp.status_code == 400
    assert "Malformed webhook JSON" in resp.json()["detail"]


# ==============================================================================
# GROUP I: Invoice Tests (35-40)
# ==============================================================================

@pytest.mark.asyncio
async def test_35_invoice_number_unique(async_client: AsyncClient, override_settings, mock_customer):
    """Test 35: Invoice numbers generated have unique date-based formats."""
    mock_client, db = build_mock_db(has_invoice=False)
    rz_mock = get_mock_razorpay_client()

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )

    inv = db["invoices"][0]
    assert inv["invoice_number"].startswith("INV-")
    assert len(inv["invoice_number"]) >= 15


@pytest.mark.asyncio
async def test_36_invoice_generated_once_per_booking(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 36: Exactly one invoice row is generated per booking."""
    mock_client, db = build_mock_db(has_invoice=True, invoice_status="issued")
    rz_mock = get_mock_razorpay_client()

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        await async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
    assert len(db["invoices"]) == 1


@pytest.mark.asyncio
async def test_37_invoice_totals_match_booking_totals(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 37: Invoice total and subtotal match authoritative booking amounts."""
    mock_client, db = build_mock_db(has_invoice=True, total_amount="1680.00", subtotal="1000.00", tax_amount="180.00")
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1680.0
    assert data["subtotal"] == 1000.0


@pytest.mark.asyncio
async def test_38_invoice_contains_service_items(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 38: Invoice details include service package line items with pricing."""
    mock_client, db = build_mock_db(has_invoice=True)
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["service_name"] == "Standard General Service"
    assert data["items"][0]["total_price"] == 1000.0


@pytest.mark.asyncio
async def test_39_invoice_contains_approved_additional_work(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 39: Invoice details include customer-approved additional work requests."""
    mock_client, db = build_mock_db(has_invoice=True)
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["additional_work"]) == 1
    assert data["additional_work"][0]["description"] == "Front Brake Pad Replacement"
    assert data["additional_work"][0]["amount"] == 500.0


@pytest.mark.asyncio
async def test_40_rejected_additional_work_does_not_appear_in_invoice_totals(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 40: Rejected additional work items are excluded from invoice line items."""
    mock_client, db = build_mock_db(has_invoice=True)
    with patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client):
        resp = await async_client.get(f"/api/v1/payments/booking/{BOOKING_TEST_ID}/invoice")

    assert resp.status_code == 200
    data = resp.json()
    descriptions = [w["description"] for w in data["additional_work"]]
    assert "Cabin Air Filter Replacement" not in descriptions


# ==============================================================================
# GROUP J: Concurrency & Race Condition Tests (41-43)
# ==============================================================================

@pytest.mark.asyncio
async def test_41_verify_and_webhook_race_does_not_duplicate_capture(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 41: Simultaneous verify and webhook requests result in one capture and one transaction."""
    order_id = "order_race_41"
    pay_id = "pay_race_41"
    sig = make_payment_signature(order_id, pay_id)

    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_race_41",
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    webhook_sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        verify_task = async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
        )
        webhook_task = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": webhook_sig, "Content-Type": "application/json"},
        )

        resp_verify, resp_webhook = await asyncio.gather(verify_task, webhook_task)

    assert resp_verify.status_code == 200
    assert resp_webhook.status_code == 200

    # Exactly 1 captured payment and exactly 1 transaction recorded
    assert db["payments"][0]["status"] == "captured"
    assert len(db["payment_transactions"]) == 1


@pytest.mark.asyncio
async def test_42_concurrent_successful_verifications_result_in_one_settlement(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 42: Two simultaneous verification requests settle cleanly without duplicating transactions."""
    order_id = "order_race_42"
    pay_id = "pay_race_42"
    sig = make_payment_signature(order_id, pay_id)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        task1 = async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
        )
        task2 = async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
        )

        resps = await asyncio.gather(task1, task2)

    assert resps[0].status_code == 200
    assert resps[1].status_code == 200
    # Exactly 1 transaction recorded
    assert len(db["payment_transactions"]) == 1


@pytest.mark.asyncio
async def test_43_concurrent_invoice_creation_produces_one_invoice(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 43: Concurrent create-order calls produce exactly one invoice."""
    mock_client, db = build_mock_db(has_invoice=False)
    rz_mock = get_mock_razorpay_client()

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        task1 = async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
        task2 = async_client.post(
            "/api/v1/payments/create-order",
            json={"booking_id": str(BOOKING_TEST_ID)},
        )
        resps = await asyncio.gather(task1, task2)

    assert resps[0].status_code == 201
    assert resps[1].status_code == 201
    assert len(db["invoices"]) == 1


# ==============================================================================
# GROUP K: Phase 8.1A Idempotency Hardening Tests (44-50)
# ==============================================================================

@pytest.mark.asyncio
async def test_44_captured_payment_followed_by_payment_failed_ignored(
    async_client: AsyncClient, override_settings
):
    """Test 44 (Phase 8.1A - Req A): Captured payment followed by payment.failed leaves states intact."""
    order_id = "order_settled_44"
    pay_id = "pay_captured_44"
    event_payload = {
        "event": "payment.failed",
        "event_id": "evt_late_fail_44",
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Late failure event from gateway",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(
        booking_status="paid",
        payment_status="paid",
        has_payment=True,
        payment_gateway_status="captured",
        has_invoice=True,
        invoice_status="paid",
        order_id=order_id,
    )
    # Pre-existing captured transaction
    db["payment_transactions"].append({
        "id": str(uuid.uuid4()),
        "payment_id": db["payments"][0]["id"],
        "provider_transaction_id": pay_id,
        "amount": 1180.0,
        "status": "successful",
        "provider": "razorpay",
    })

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    # Core states remain settled
    assert db["payments"][0]["status"] == "captured"
    assert db["bookings"][0]["payment_status"] == "paid"
    assert db["bookings"][0]["booking_status"] == "paid"
    assert db["invoices"][0]["status"] == "paid"

    # No failed transaction added
    failed_txs = [t for t in db["payment_transactions"] if t.get("status") == "failed"]
    assert len(failed_txs) == 0

    # Audit log recorded with new_data
    audit_events = [a for a in db["audit_logs"] if a.get("action") == "payment_failed_ignored_already_settled"]
    assert len(audit_events) == 1
    assert audit_events[0]["new_data"]["current_payment_status"] == "captured"
    assert audit_events[0]["new_data"]["current_booking_payment_status"] == "paid"


@pytest.mark.asyncio
async def test_45_paid_booking_followed_by_late_payment_failed_no_regression(
    async_client: AsyncClient, override_settings
):
    """Test 45 (Phase 8.1A - Req B): Paid booking followed by late payment.failed causes no regression."""
    order_id = "order_paid_booking_45"
    pay_id = "pay_fail_45"
    event_payload = {
        "event": "payment.failed",
        "event_id": "evt_late_fail_45",
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Payment authorization timed out",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(
        booking_status="paid",
        payment_status="paid",
        has_payment=True,
        payment_gateway_status="pending",  # Payment row was pending, but booking was settled
        has_invoice=True,
        invoice_status="paid",
        order_id=order_id,
    )

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"

    # State does not regress
    assert db["bookings"][0]["payment_status"] == "paid"
    assert db["bookings"][0]["booking_status"] == "paid"
    assert db["invoices"][0]["status"] == "paid"
    assert db["payments"][0]["status"] == "pending"  # Unchanged, NOT overwritten to failed


@pytest.mark.asyncio
async def test_46_duplicate_refund_event_creates_only_one_transaction(
    async_client: AsyncClient, override_settings
):
    """Test 46 (Phase 8.1A - Req C): Duplicate refund event creates exactly one transaction record."""
    order_id = "order_refund_46"
    settled_pay_id = "pay_settled_46"
    refund_id = "rfnd_test_46_unique"

    mock_client, db = build_mock_db(
        booking_status="paid",
        payment_status="paid",
        has_payment=True,
        payment_gateway_status="captured",
        has_invoice=True,
        invoice_status="paid",
        order_id=order_id,
    )
    # Record original settled payment transaction
    db["payment_transactions"].append({
        "id": str(uuid.uuid4()),
        "payment_id": db["payments"][0]["id"],
        "provider_transaction_id": settled_pay_id,
        "amount": 1180.0,
        "status": "successful",
        "provider": "razorpay",
    })

    event_payload_1 = {
        "event": "refund.processed",
        "event_id": "evt_rfnd_46_1",
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": settled_pay_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "processed",
                }
            },
            "payment": {
                "entity": {
                    "id": settled_pay_id,
                    "order_id": order_id,
                }
            },
        },
    }
    raw_body_1 = json.dumps(event_payload_1).encode("utf-8")
    sig_1 = make_webhook_signature(raw_body_1)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        # 1st refund delivery
        resp1 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body_1,
            headers={"X-Razorpay-Signature": sig_1, "Content-Type": "application/json"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "processed"

        # Exactly 1 refund transaction created
        refund_txs = [t for t in db["payment_transactions"] if t.get("provider_transaction_id") == refund_id]
        assert len(refund_txs) == 1
        assert refund_txs[0]["status"] == "refunded"

        # 2nd refund delivery (identical refund_id, different webhook event_id)
        event_payload_2 = dict(event_payload_1)
        event_payload_2["event_id"] = "evt_rfnd_46_2"
        raw_body_2 = json.dumps(event_payload_2).encode("utf-8")
        sig_2 = make_webhook_signature(raw_body_2)

        resp2 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body_2,
            headers={"X-Razorpay-Signature": sig_2, "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"

        # Still exactly 1 refund transaction exists
        refund_txs = [t for t in db["payment_transactions"] if t.get("provider_transaction_id") == refund_id]
        assert len(refund_txs) == 1


@pytest.mark.asyncio
async def test_47_partial_refund_records_transaction_without_corrupting_state(
    async_client: AsyncClient, override_settings
):
    """Test 47 (Phase 8.1A - Req 3): Partial refund creates refund transaction without faking full refund."""
    order_id = "order_partial_47"
    settled_pay_id = "pay_settled_47"
    refund_id = "rfnd_part_47_unique"

    mock_client, db = build_mock_db(
        booking_status="paid",
        payment_status="paid",
        has_payment=True,
        payment_gateway_status="captured",
        has_invoice=True,
        invoice_status="paid",
        order_id=order_id,
        total_amount="1180.00",
    )
    # Record original settled payment transaction
    db["payment_transactions"].append({
        "id": str(uuid.uuid4()),
        "payment_id": db["payments"][0]["id"],
        "provider_transaction_id": settled_pay_id,
        "amount": 1180.0,
        "status": "successful",
        "provider": "razorpay",
    })

    # Refund 500 INR out of 1180 INR
    event_payload = {
        "event": "refund.processed",
        "event_id": "evt_part_rfnd_47",
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": settled_pay_id,
                    "amount": 50000,  # 500.00 INR
                    "currency": "INR",
                    "status": "processed",
                }
            },
            "payment": {
                "entity": {
                    "id": settled_pay_id,
                    "order_id": order_id,
                }
            },
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "partial_refund_recorded"

    # Transaction recorded for partial refund
    refund_txs = [t for t in db["payment_transactions"] if t.get("provider_transaction_id") == refund_id]
    assert len(refund_txs) == 1
    assert refund_txs[0]["amount"] == 500.0
    assert refund_txs[0]["status"] == "refunded"

    # Core states MUST NOT be corrupted to 'refunded'
    assert db["payments"][0]["status"] == "captured"
    assert db["bookings"][0]["payment_status"] == "paid"
    assert db["invoices"][0]["status"] == "paid"

    # Audit log recorded with partial refund semantics
    partial_audits = [a for a in db["audit_logs"] if a.get("action") == "payment_partial_refund_recorded"]
    assert len(partial_audits) == 1
    assert partial_audits[0]["new_data"]["is_full_refund"] is False
    assert partial_audits[0]["new_data"]["amount"] == 500.0


@pytest.mark.asyncio
async def test_48_concurrent_identical_payment_captured_deliveries(
    async_client: AsyncClient, override_settings
):
    """Test 48 (Phase 8.1A - Req D): Concurrent identical payment.captured webhook deliveries settle cleanly."""
    order_id = "order_concurrent_48"
    pay_id = "pay_concurrent_48"
    event_payload = {
        "event": "payment.captured",
        "event_id": "evt_concurrent_48",
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(
        booking_status="payment_pending",
        payment_status="unpaid",
        has_payment=True,
        payment_gateway_status="pending",
        has_invoice=True,
        invoice_status="issued",
        order_id=order_id,
    )

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        task1 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        task2 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        resps = await asyncio.gather(task1, task2)

    assert resps[0].status_code == 200
    assert resps[1].status_code == 200

    # Exactly 1 effective transaction recorded
    assert len(db["payment_transactions"]) == 1
    assert db["payment_transactions"][0]["status"] == "successful"

    # Exactly 1 effective booking settlement
    assert db["payments"][0]["status"] == "captured"
    assert db["bookings"][0]["payment_status"] == "paid"
    assert db["bookings"][0]["booking_status"] == "paid"
    assert db["invoices"][0]["status"] == "paid"


@pytest.mark.asyncio
async def test_49_audit_event_lookup_reads_from_new_data(
    async_client: AsyncClient, override_settings
):
    """Test 49 (Phase 8.1A - Req F): Webhook duplicate check specifically reads event_id from new_data."""
    event_id = "evt_lookup_new_data_49"
    order_id = "order_audit_49"
    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_audit_49",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)

    # 1. Pre-populate webhook_events using event_id
    db["webhook_events"].append({
        "provider": "razorpay",
        "event_id": event_id,
        "event_type": "payment.captured",
    })

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "already_processed"
    assert resp.json()["event_id"] == event_id

    # Verify audit log recorded with new_data
    dup_audits = [a for a in db["audit_logs"] if a.get("action") == "payment_webhook_duplicate"]
    assert len(dup_audits) == 1
    assert dup_audits[0]["new_data"]["event_id"] == event_id

    # 2. Verify an unmatched event_id is NOT treated as duplicate
    diff_payload = dict(event_payload)
    diff_payload["event_id"] = "evt_unmatched_50"
    diff_raw = json.dumps(diff_payload).encode("utf-8")
    diff_sig = make_webhook_signature(diff_raw)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp_diff = await async_client.post(
            "/api/v1/payments/webhook",
            content=diff_raw,
            headers={"X-Razorpay-Signature": diff_sig, "Content-Type": "application/json"},
        )

    assert resp_diff.status_code == 200
    assert resp_diff.json()["status"] == "processed"
    proc_audits = [a for a in db["audit_logs"] if a.get("action") == "payment_webhook_processed"]
    assert len(proc_audits) == 1
    assert proc_audits[0]["new_data"]["event_id"] == "evt_unmatched_50"


def test_50_record_audit_log_raises_on_schema_error_in_testing(override_settings):
    """Test 50: record_audit_log raises schema/column errors during tests to prevent silent schema drift."""
    from app.core.audit import record_audit_log
    mock_bad_client = MagicMock()
    mock_bad_client.table.return_value.insert.return_value.execute.side_effect = Exception(
        'column "old_state" of relation "audit_logs" does not exist'
    )

    with patch("app.core.audit.get_supabase_service_client", return_value=mock_bad_client):
        with pytest.raises(Exception) as exc_info:
            record_audit_log(
                action="test_schema_drift",
                entity_type="payment",
                entity_id=uuid.uuid4(),
                new_data={"test": 123},
            )
        assert "does not exist" in str(exc_info.value)


# ==============================================================================
# GROUP L: Phase 8.1B Database-Level Webhook Event Idempotency Tests (51-58)
# ==============================================================================

@pytest.mark.asyncio
async def test_51_phase81b_test_a_first_webhook_inserts_webhook_events(
    async_client: AsyncClient, override_settings
):
    """Test 51 (Phase 8.1B - TEST A): First webhook delivery inserts exactly 1 row into webhook_events."""
    order_id = "order_phase81b_51"
    event_id = "evt_phase81b_51"
    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_51",
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "processed"
    # Exactly 1 row in webhook_events
    assert len(db["webhook_events"]) == 1
    assert db["webhook_events"][0]["event_id"] == event_id
    assert db["webhook_events"][0]["provider"] == "razorpay"
    assert db["webhook_events"][0]["event_type"] == "payment.captured"
    assert "processed_at" in db["webhook_events"][0]


@pytest.mark.asyncio
async def test_52_phase81b_test_b_sequential_duplicate_webhook(
    async_client: AsyncClient, override_settings
):
    """Test 52 (Phase 8.1B - TEST B): Sequential duplicate webhook returns already_processed with 1 financial settlement."""
    order_id = "order_phase81b_52"
    event_id = "evt_phase81b_52"
    pay_id = "pay_52"
    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        # 1st delivery
        resp1 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "processed"

        # 2nd delivery (duplicate)
        resp2 = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "already_processed"

    # Exactly 1 webhook_events row
    assert len(db["webhook_events"]) == 1
    # Exactly 1 payment transaction (only 1 financial settlement)
    assert len(db["payment_transactions"]) == 1
    assert db["payments"][0]["status"] == "captured"
    assert db["bookings"][0]["payment_status"] == "paid"


@pytest.mark.asyncio
async def test_53_phase81b_test_c_concurrent_identical_payment_captured_webhooks(
    async_client: AsyncClient, override_settings
):
    """Test 53 (Phase 8.1B - TEST C): Two concurrent identical payment.captured webhooks settle cleanly with 1 event row."""
    order_id = "order_phase81b_53"
    event_id = "evt_phase81b_53"
    pay_id = "pay_53"
    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(
        booking_status="payment_pending",
        payment_status="unpaid",
        has_payment=True,
        payment_gateway_status="pending",
        has_invoice=True,
        invoice_status="issued",
        order_id=order_id,
    )

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        task1 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        task2 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        resps = await asyncio.gather(task1, task2)

    assert resps[0].status_code == 200
    assert resps[1].status_code == 200
    statuses = {resps[0].json()["status"], resps[1].json()["status"]}
    assert "processed" in statuses
    assert "already_processed" in statuses

    # Exactly ONE webhook_events row
    assert len(db["webhook_events"]) == 1
    # Exactly ONE payment transaction
    assert len(db["payment_transactions"]) == 1
    # Booking ends paid, invoice ends paid
    assert db["payments"][0]["status"] == "captured"
    assert db["bookings"][0]["payment_status"] == "paid"
    assert db["bookings"][0]["booking_status"] == "paid"
    assert db["invoices"][0]["status"] == "paid"


@pytest.mark.asyncio
async def test_54_phase81b_test_d_concurrent_identical_refund_webhooks(
    async_client: AsyncClient, override_settings
):
    """Test 54 (Phase 8.1B - TEST D): Two concurrent identical refund webhooks create exactly 1 refund event & transaction."""
    order_id = "order_phase81b_54"
    settled_pay_id = "pay_settled_54"
    refund_id = "rfnd_54_unique"
    event_id = "evt_rfnd_54"

    mock_client, db = build_mock_db(
        booking_status="paid",
        payment_status="paid",
        has_payment=True,
        payment_gateway_status="captured",
        has_invoice=True,
        invoice_status="paid",
        order_id=order_id,
    )
    # Existing settled payment transaction
    db["payment_transactions"].append({
        "id": str(uuid.uuid4()),
        "payment_id": db["payments"][0]["id"],
        "provider_transaction_id": settled_pay_id,
        "amount": 1180.0,
        "status": "successful",
        "provider": "razorpay",
    })

    event_payload = {
        "event": "refund.processed",
        "event_id": event_id,
        "payload": {
            "refund": {
                "entity": {
                    "id": refund_id,
                    "payment_id": settled_pay_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "processed",
                }
            },
            "payment": {
                "entity": {
                    "id": settled_pay_id,
                    "order_id": order_id,
                }
            },
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        task1 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        task2 = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )
        resps = await asyncio.gather(task1, task2)

    assert resps[0].status_code == 200
    assert resps[1].status_code == 200
    statuses = {resps[0].json()["status"], resps[1].json()["status"]}
    assert "processed" in statuses
    assert "already_processed" in statuses

    # Exactly ONE webhook event
    assert len(db["webhook_events"]) == 1
    # Exactly ONE refund transaction
    refund_txs = [t for t in db["payment_transactions"] if t.get("provider_transaction_id") == refund_id]
    assert len(refund_txs) == 1
    assert db["payments"][0]["status"] == "refunded"
    assert db["bookings"][0]["payment_status"] == "refunded"


@pytest.mark.asyncio
async def test_55_phase81b_test_e_verify_and_webhook_race_preservation(
    async_client: AsyncClient, override_settings, mock_customer
):
    """Test 55 (Phase 8.1B - TEST E): Verify + webhook race condition preservation."""
    order_id = "order_phase81b_55"
    pay_id = "pay_55"
    event_id = "evt_55"
    sig = make_payment_signature(order_id, pay_id)

    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    webhook_sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)
    rz_mock = get_mock_razorpay_client(order_id=order_id, payment_id=pay_id)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.services.payment_service.get_razorpay_client", return_value=rz_mock),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        verify_task = async_client.post(
            "/api/v1/payments/verify",
            json={
                "booking_id": str(BOOKING_TEST_ID),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": pay_id,
                "razorpay_signature": sig,
            },
        )
        webhook_task = async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": webhook_sig, "Content-Type": "application/json"},
        )
        resp_verify, resp_webhook = await asyncio.gather(verify_task, webhook_task)

    assert resp_verify.status_code == 200
    assert resp_webhook.status_code == 200
    assert db["payments"][0]["status"] == "captured"
    assert len(db["payment_transactions"]) == 1


@pytest.mark.asyncio
async def test_56_phase81b_test_f_failed_webhook_processing_is_retryable(
    async_client: AsyncClient, override_settings
):
    """Test 56 (Phase 8.1B - TEST F): Failed webhook processing releases reservation so retry can succeed."""
    order_id = "order_phase81b_56"
    event_id = "evt_phase81b_56"
    pay_id = "pay_56"
    event_payload = {
        "event": "payment.captured",
        "event_id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body = json.dumps(event_payload).encode("utf-8")
    sig = make_webhook_signature(raw_body)

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)

    # 1. First attempt: simulate a transient database exception during settlement
    from app.services.payment_service import PaymentService
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
        patch.object(PaymentService, "_settle_successful_payment", side_effect=RuntimeError("Transient DB connection drop")),
    ):
        with pytest.raises(RuntimeError):
            service = PaymentService()
            await service.process_webhook(raw_body=raw_body, signature_header=sig)

    # The reservation MUST have been released upon exception
    assert len(db["webhook_events"]) == 0

    # 2. Retry attempt: same event_id is re-sent by gateway
    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp_retry = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body,
            headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
        )

    # Retry is NOT rejected as already_processed! It succeeds!
    assert resp_retry.status_code == 200
    assert resp_retry.json()["status"] == "processed"
    assert len(db["webhook_events"]) == 1
    assert db["webhook_events"][0]["event_id"] == event_id
    assert db["payments"][0]["status"] == "captured"


@pytest.mark.asyncio
async def test_57_phase81b_test_g_different_event_ids_for_same_payment(
    async_client: AsyncClient, override_settings
):
    """Test 57 (Phase 8.1B - TEST G): Different event IDs for same payment both reserve in Layer 1; Layer 2 prevents duplicate transaction."""
    order_id = "order_phase81b_57"
    shared_pay_id = "pay_shared_57"
    event_id_a = "evt_gateway_event_A"
    event_id_b = "evt_gateway_event_B"

    mock_client, db = build_mock_db(has_payment=True, order_id=order_id, has_invoice=True)

    # Event A
    payload_a = {
        "event": "payment.captured",
        "event_id": event_id_a,
        "payload": {
            "payment": {
                "entity": {
                    "id": shared_pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body_a = json.dumps(payload_a).encode("utf-8")
    sig_a = make_webhook_signature(raw_body_a)

    # Event B (different event_id, same payment entity)
    payload_b = {
        "event": "payment.captured",
        "event_id": event_id_b,
        "payload": {
            "payment": {
                "entity": {
                    "id": shared_pay_id,
                    "order_id": order_id,
                    "amount": 118000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        },
    }
    raw_body_b = json.dumps(payload_b).encode("utf-8")
    sig_b = make_webhook_signature(raw_body_b)

    with (
        patch("app.services.payment_service.get_supabase_service_client", return_value=mock_client),
        patch("app.core.audit.get_supabase_service_client", return_value=mock_client),
    ):
        resp_a = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body_a,
            headers={"X-Razorpay-Signature": sig_a, "Content-Type": "application/json"},
        )
        assert resp_a.status_code == 200
        assert resp_a.json()["status"] == "processed"

        resp_b = await async_client.post(
            "/api/v1/payments/webhook",
            content=raw_body_b,
            headers={"X-Razorpay-Signature": sig_b, "Content-Type": "application/json"},
        )
        assert resp_b.status_code == 200
        assert resp_b.json()["status"] == "processed"

    # Layer 1: webhook_events constraint allows BOTH distinct event_ids
    assert len(db["webhook_events"]) == 2
    event_ids_saved = {row["event_id"] for row in db["webhook_events"]}
    assert event_ids_saved == {event_id_a, event_id_b}

    # Layer 2: financial transaction uniqueness prevents duplicate transaction settlement!
    assert len(db["payment_transactions"]) == 1
    assert db["payment_transactions"][0]["provider_transaction_id"] == shared_pay_id


@pytest.mark.asyncio
async def test_58_phase81b_test_h_different_providers_same_event_id_no_conflict(
    override_settings
):
    """Test 58 (Phase 8.1B - TEST H): Different providers with same event ID do not conflict (UNIQUE(provider, event_id))."""
    event_id = "evt_common_id_999"

    mock_client, db = build_mock_db()

    # Provider 1: razorpay
    mock_client.table("webhook_events").upsert(
        {
            "provider": "razorpay",
            "event_id": event_id,
            "event_type": "payment.captured",
            "payload": {"provider": "razorpay"},
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="provider,event_id",
        ignore_duplicates=True,
    ).execute()

    # Provider 2: other_gateway with identical event_id
    mock_client.table("webhook_events").upsert(
        {
            "provider": "other_gateway",
            "event_id": event_id,
            "event_type": "payment.captured",
            "payload": {"provider": "other_gateway"},
            "processed_at": datetime.now(timezone.utc).isoformat(),
        },
        on_conflict="provider,event_id",
        ignore_duplicates=True,
    ).execute()

    # Both must exist without conflict
    assert len(db["webhook_events"]) == 2
    providers = {row["provider"] for row in db["webhook_events"]}
    assert providers == {"razorpay", "other_gateway"}


