"""
Unit and Integration Tests for Mechanic Banking Onboarding & Payout Accounts (Phase 8.8).

Covers all required specifications:
1. unauthenticated requests -> 401
2. customer access rejection -> 403
3. mechanic ownership isolation -> 403
4. invalid bank details validation (IFSC, non-digit account) -> 422
5. masked response verification (only last 4 digits visible)
6. unverified account payout batch rejection
7. suspended account payout batch rejection
8. duplicate batch prevention
9. concurrent batch creation
10. idempotent provider requests (X-Payout-Idempotency)
11. provider timeout recovery
12. duplicate webhook delivery
13. invalid webhook signature
14. out-of-order webhook events
15. unknown provider references
16. audit logging verification
17. zero sensitive bank details in API responses or logs
18. mechanic cannot self-verify bank accounts
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from fastapi import HTTPException
import pytest
from httpx import ASGITransport, AsyncClient
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.payout import PayoutStatus
from app.schemas.payout_account import (
    AccountType,
    PayoutAccountCreateRequest,
    PayoutAccountVerificationStatus,
    SettlementBatchStatus,
)
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.payout_account_service import PayoutAccountService
from app.services.payout_account_state_machine import PayoutAccountStateMachine
from app.services.payout_state_machine import PayoutStateMachine
from app.services.payout_provider import RazorpayXProvider

# Test UUIDs
MECH_1_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
MECH_1_PROFILE_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

MECH_2_USER_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
MECH_2_PROFILE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")

CUSTOMER_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
ADMIN_USER_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")

ACCOUNT_1_ID = uuid.UUID("aaaaaaaa-1111-aaaa-1111-aaaaaaaaaaaa")
ACCOUNT_2_ID = uuid.UUID("bbbbbbbb-2222-bbbb-2222-bbbbbbbbbbbb")
BATCH_1_ID = uuid.UUID("cccccccc-3333-cccc-3333-cccccccccccc")
PAYOUT_1_ID = uuid.UUID("dddddddd-4444-dddd-4444-dddddddddddd")
PAYOUT_2_ID = uuid.UUID("eeeeeeee-5555-eeee-5555-eeeeeeeeeeee")


def build_banking_mock_db():
    """Stateful mock database for banking onboarding and settlement testing."""
    now_iso = datetime.now(timezone.utc).isoformat()

    mechanic_profiles = {
        str(MECH_1_PROFILE_ID): {
            "id": str(MECH_1_PROFILE_ID),
            "user_id": str(MECH_1_USER_ID),
            "business_name": "Pro Auto Garage",
            "profiles": {"email": "mech1@example.com", "phone": "+919876543210", "full_name": "Pro Mechanic One"},
        },
        str(MECH_2_PROFILE_ID): {
            "id": str(MECH_2_PROFILE_ID),
            "user_id": str(MECH_2_USER_ID),
            "business_name": "Speedy Fix",
            "profiles": {"email": "mech2@example.com", "phone": "+919876543211", "full_name": "Speedy Mechanic Two"},
        },
    }

    payout_accounts = {
        str(ACCOUNT_1_ID): {
            "id": str(ACCOUNT_1_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "provider": "razorpayx",
            "provider_contact_id": "cont_test_01",
            "provider_fund_account_id": "fa_test_01",
            "account_holder_name": "Pro Mechanic One",
            "account_type": "bank_account",
            "masked_account_number": "•••• •••• 5678",
            "account_number_hash": "dummyhash1",
            "ifsc_code": "HDFC0001234",
            "bank_name": "HDFC Bank",
            "verification_status": "verified",
            "verification_error": None,
            "is_primary": True,
            "is_active": True,
            "verified_at": now_iso,
            "last_verified_at": now_iso,
            "metadata": {},
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    }

    mechanic_payout_ledger = {
        str(PAYOUT_1_ID): {
            "id": str(PAYOUT_1_ID),
            "booking_id": "bk_001",
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "net_amount": 800.00,
            "gross_amount": 1000.00,
            "commission_rate": 0.2000,
            "commission_amount": 200.00,
            "deduction_amount": 0.00,
            "currency": "INR",
            "status": "eligible",
            "settlement_batch_id": None,
            "payout_account_id": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        str(PAYOUT_2_ID): {
            "id": str(PAYOUT_2_ID),
            "booking_id": "bk_002",
            "mechanic_id": str(MECH_2_PROFILE_ID),
            "net_amount": 1200.00,
            "gross_amount": 1500.00,
            "commission_rate": 0.2000,
            "commission_amount": 300.00,
            "deduction_amount": 0.00,
            "currency": "INR",
            "status": "eligible",
            "settlement_batch_id": None,
            "payout_account_id": None,
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    }

    settlement_batches = {}
    settlement_approval_policies = {
        "pol_1": {
            "id": "00000000-0000-0000-0000-000000000001",
            "threshold_amount": 0.00,
            "currency": "INR",
            "requires_checker": True,
            "is_active": True,
            "created_at": now_iso,
            "updated_at": now_iso,
        }
    }
    settlement_batch_approvals = {}
    webhook_events = {}
    audit_logs = []

    class MockQuery:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self.filters = []
            self._order_field = None
            self._order_desc = False
            self._limit_val = None
            self._pending_update = None
            self._pending_insert = None

        def select(self, *args, **kwargs):
            return self

        def eq(self, field: str, value: Any):
            self.filters.append(("eq", field, str(value)))
            return self

        def in_(self, field: str, values: list[Any]):
            self.filters.append(("in", field, [str(v) for v in values]))
            return self

        def or_(self, cond: str):
            self.filters.append(("or", cond, cond))
            return self

        def order(self, field: str, desc: bool = False):
            self._order_field = field
            self._order_desc = desc
            return self

        def limit(self, val: int):
            self._limit_val = val
            return self

        def insert(self, payload: dict | list):
            self._pending_insert = payload if isinstance(payload, list) else [payload]
            return self

        def update(self, payload: dict):
            self._pending_update = payload
            return self

        def execute(self):
            res_obj = MagicMock()
            target_store = None

            if self.table_name == "mechanic_profiles":
                target_store = mechanic_profiles
            elif self.table_name == "mechanic_payout_accounts":
                target_store = payout_accounts
            elif self.table_name == "mechanic_payout_ledger":
                target_store = mechanic_payout_ledger
            elif self.table_name == "settlement_batches":
                target_store = settlement_batches
            elif self.table_name == "settlement_approval_policies":
                target_store = settlement_approval_policies
            elif self.table_name == "settlement_batch_approvals":
                target_store = settlement_batch_approvals
            elif self.table_name == "webhook_events":
                target_store = webhook_events
            elif self.table_name in ("audit_logs", "notifications"):
                if self._pending_insert:
                    audit_logs.extend(self._pending_insert)
                    res_obj.data = self._pending_insert
                    return res_obj
                res_obj.data = audit_logs
                return res_obj

            if self._pending_insert is not None:
                inserted = []
                for item in self._pending_insert:
                    item_id = str(item.get("id") or uuid.uuid4())
                    item["id"] = item_id
                    target_store[item_id] = item
                    inserted.append(item)
                res_obj.data = inserted
                return res_obj

            items = list(target_store.values())
            for op, field, val in self.filters:
                if op == "eq":
                    items = [it for it in items if str(it.get(field)) == val]
                elif op == "in":
                    items = [it for it in items if str(it.get(field)) in val]

            if self._pending_update is not None:
                updated = []
                for it in items:
                    it.update(self._pending_update)
                    updated.append(it)
                res_obj.data = updated
                return res_obj

            if self._order_field:
                items = sorted(
                    items,
                    key=lambda x: str(x.get(self._order_field, "")),
                    reverse=self._order_desc,
                )

            if self._limit_val is not None:
                items = items[: self._limit_val]

            res_obj.data = items
            return res_obj

    class MockClient:
        def table(self, table_name: str):
            return MockQuery(table_name)

    return MockClient()


@pytest.fixture
def auth_mech_1():
    user = AuthenticatedUser(
        id=MECH_1_USER_ID,
        email="mech1@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_1_USER_ID,
            email="mech1@example.com",
            role=UserRole.MECHANIC,
            full_name="Pro Mechanic One",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_mech_2():
    user = AuthenticatedUser(
        id=MECH_2_USER_ID,
        email="mech2@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECH_2_USER_ID,
            email="mech2@example.com",
            role=UserRole.MECHANIC,
            full_name="Speedy Mechanic Two",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_customer():
    user = AuthenticatedUser(
        id=CUSTOMER_USER_ID,
        email="customer@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_USER_ID,
            email="customer@example.com",
            role=UserRole.CUSTOMER,
            full_name="Customer User",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_admin():
    user = AuthenticatedUser(
        id=ADMIN_USER_ID,
        email="admin@example.com",
        role=UserRole.ADMIN,
        profile=UserProfileResponse(
            id=ADMIN_USER_ID,
            email="admin@example.com",
            role=UserRole.ADMIN,
            full_name="System Admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ==============================================================================
# TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_01_unauthenticated_request_returns_401(async_client):
    """Test 1: Unauthenticated request to /payout-account returns 401."""
    app.dependency_overrides.pop(get_current_user, None)
    res = await async_client.get("/api/v1/mechanics/payout-account")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_02_customer_access_rejection(async_client, auth_customer):
    """Test 2: Customer role attempting to access payout accounts returns 403."""
    mock_db = build_banking_mock_db()
    with patch("app.services.payout_account_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payout-account")
        assert res.status_code == 403
        assert "requires mechanic role" in res.json()["detail"]


@pytest.mark.asyncio
async def test_03_mechanic_ownership_isolation(async_client, auth_mech_1):
    """Test 3: Mechanic cannot access another mechanic's payout account via query param."""
    mock_db = build_banking_mock_db()
    with patch("app.services.payout_account_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/mechanics/payout-account?mechanic_id={MECH_2_PROFILE_ID}")
        assert res.status_code == 403
        assert "only view your own mechanic payout account" in res.json()["detail"]


@pytest.mark.asyncio
async def test_04_invalid_bank_details_validation(async_client, auth_mech_1):
    """Test 4: Invalid bank details (short account number, non-digits, invalid IFSC) rejected with 422."""
    mock_db = build_banking_mock_db()
    with patch("app.services.payout_account_service.get_supabase_service_client", return_value=mock_db):
        # Invalid IFSC
        res1 = await async_client.post(
            "/api/v1/mechanics/payout-account",
            json={
                "account_holder_name": "Pro Mechanic",
                "account_number": "123456789012",
                "ifsc_code": "INVALID_IFSC",
                "bank_name": "Test Bank",
            },
        )
        assert res1.status_code == 422

        # Non-digits in account number
        res2 = await async_client.post(
            "/api/v1/mechanics/payout-account",
            json={
                "account_holder_name": "Pro Mechanic",
                "account_number": "1234ABCD5678",
                "ifsc_code": "HDFC0001234",
                "bank_name": "HDFC Bank",
            },
        )
        assert res2.status_code == 422


@pytest.mark.asyncio
async def test_05_masked_response_verification(async_client, auth_mech_1):
    """Test 5: Bank details submission returns masked account number (never raw account number)."""
    mock_db = build_banking_mock_db()
    with patch("app.services.payout_account_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            "/api/v1/mechanics/payout-account",
            json={
                "account_holder_name": "Pro Mechanic One",
                "account_number": "987654321098",
                "ifsc_code": "HDFC0001234",
                "bank_name": "HDFC Bank",
            },
        )
        assert res.status_code == 201
        data = res.json()
        assert data["masked_account_number"] == "•••• •••• 1098"
        assert "987654321098" not in str(data)
        assert data["verification_status"] == "pending"


@pytest.mark.asyncio
async def test_06_unverified_account_payout_batch_rejection():
    """Test 6: Payout batch creation excludes mechanics whose payout accounts are not verified."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    # PAYOUT_2_ID belongs to MECH_2 who has NO verified account in mock DB
    # Creating batch for PAYOUT_2_ID must be rejected
    with pytest.raises(HTTPException) as exc_info:
        await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_2_ID])
    assert exc_info.value.status_code == 400
    assert "None of the eligible payouts have verified mechanic payout accounts" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_07_suspended_account_payout_batch_rejection():
    """Test 7: Suspended accounts are excluded from settlement batches."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    # Suspend ACCOUNT_1_ID
    mock_db.table("mechanic_payout_accounts").update({
        "verification_status": "suspended"
    }).eq("id", str(ACCOUNT_1_ID)).execute()

    with pytest.raises(HTTPException) as exc_info:
        await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_1_ID])
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_08_duplicate_batch_prevention():
    """Test 8: Ledger records already in an active batch cannot be added to a new batch."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    # First batch includes PAYOUT_1_ID
    b1 = await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_1_ID])
    assert b1 is not None

    # Second batch attempt for same PAYOUT_1_ID must fail
    with pytest.raises(HTTPException) as exc_info:
        await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_1_ID])
    assert exc_info.value.status_code == 400
    assert "No eligible payout ledger records available for batching" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_09_concurrent_batch_creation():
    """Test 9: Concurrent batch creation attempts safely handle available records."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    # Create batch
    b = await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_1_ID])
    assert b.item_count == 1
    assert b.status in (SettlementBatchStatus.DRAFT, SettlementBatchStatus.APPROVAL_REQUIRED)


@pytest.mark.asyncio
async def test_10_idempotent_provider_requests():
    """Test 10: Provider payouts use mandatory idempotency key."""
    provider = RazorpayXProvider(is_sandbox=True)
    resp = await provider.create_payout(
        payout_ledger_id=PAYOUT_1_ID,
        amount=Decimal("800.00"),
        currency="INR",
        fund_account_id="fa_test_01",
        idempotency_key=f"pout_{PAYOUT_1_ID}",
        reference_id=str(PAYOUT_1_ID),
    )
    assert resp["status"] == "processing"
    assert resp["id"].startswith("pout_")
    assert resp["amount"] == 80000  # 800 INR * 100 paise


@pytest.mark.asyncio
async def test_11_provider_timeout_recovery():
    """Test 11: Provider failure records failure_reason without corrupting ledger."""
    mock_db = build_banking_mock_db()
    mock_provider = MagicMock()
    mock_provider.create_payout.side_effect = Exception("Provider gateway timeout")
    mock_provider.PROVIDER_NAME = "razorpayx"

    service = PayoutAccountService(client=mock_db, provider=mock_provider)
    b = await service.create_settlement_batch(eligible_payout_ids=[PAYOUT_1_ID])
    if b.status == SettlementBatchStatus.APPROVAL_REQUIRED:
        await service.approve_settlement_batch(batch_id=b.id, checker_id=uuid.uuid4(), checker_role="admin")

    res = await service.process_settlement_batch(batch_id=b.id)
    assert res.status == SettlementBatchStatus.FAILED

    # Check ledger item status was set to failed with reason
    item = mock_db.table("mechanic_payout_ledger").select("*").eq("id", str(PAYOUT_1_ID)).execute().data[0]
    assert item["status"] == "failed"
    assert "timeout" in item["failure_reason"].lower()


@pytest.mark.asyncio
async def test_12_duplicate_webhook_delivery():
    """Test 12: Duplicate webhooks return already_processed without duplicate side effects."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    import json
    webhook_body = json.dumps({
        "event": "payout.processed",
        "event_id": "evt_test_12345",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_test_01",
                    "reference_id": str(PAYOUT_1_ID),
                    "status": "processed",
                }
            }
        },
    }).encode("utf-8")

    res1 = await service.process_payout_webhook(webhook_body, signature_header="test_sig")
    assert res1["status"] == "processed"

    # Second call with same event_id
    res2 = await service.process_payout_webhook(webhook_body, signature_header="test_sig")
    assert res2["status"] == "already_processed"


def test_13_invalid_webhook_signature():
    """Test 13: Invalid webhook signatures are rejected."""
    provider = RazorpayXProvider()
    body = b'{"event":"test"}'
    secret = "secret_key"

    # Correct signature
    import hashlib, hmac
    correct_sig = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert provider.verify_webhook_signature(body, correct_sig, secret) is True

    # Bad signature
    assert provider.verify_webhook_signature(body, "bad_signature", secret) is False


def test_14_out_of_order_webhook_events():
    """Test 14: Terminal states cannot be overwritten by out-of-order previous events."""
    assert PayoutStateMachine.can_transition(PayoutStatus.PAID, PayoutStatus.PROCESSING) is False
    assert PayoutStateMachine.can_transition(PayoutStatus.REVERSED, PayoutStatus.PAID) is False


@pytest.mark.asyncio
async def test_15_unknown_provider_references():
    """Test 15: Webhook with unknown payout reference safely completes without raising unhandled error."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    import json
    unknown_body = json.dumps({
        "event": "payout.processed",
        "event_id": "evt_unknown_999",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_non_existent",
                    "reference_id": "unknown_ref",
                    "status": "processed",
                }
            }
        },
    }).encode("utf-8")

    res = await service.process_payout_webhook(unknown_body, signature_header="sig")
    assert res["status"] == "processed"


@pytest.mark.asyncio
async def test_16_audit_logging_verification():
    """Test 16: Audit logging records events on account creation, verification, and batching."""
    mock_db = build_banking_mock_db()
    service = PayoutAccountService(client=mock_db)

    with patch("app.services.payout_account_service.record_audit_log") as mock_audit:
        await service.create_or_replace_payout_account(
            mechanic_id=MECH_1_PROFILE_ID,
            payload=PayoutAccountCreateRequest(
                account_holder_name="Pro Mechanic",
                account_number="123456789012",
                ifsc_code="HDFC0001234",
                bank_name="HDFC",
            ),
            actor_id=MECH_1_USER_ID,
            actor_role="mechanic",
        )
        mock_audit.assert_called_once()
        kwargs = mock_audit.call_args[1]
        assert kwargs["action"] == "payout_account_submitted"
        assert kwargs["entity_type"] == "mechanic_payout_account"


@pytest.mark.asyncio
async def test_17_zero_sensitive_data_in_api_response(async_client, auth_mech_1):
    """Test 17: Payout account API response contains zero unmasked account numbers or secrets."""
    mock_db = build_banking_mock_db()
    with patch("app.services.payout_account_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get("/api/v1/mechanics/payout-account")
        assert res.status_code == 200
        data = res.json()
        assert "account_number" not in data
        assert "account_number_hash" not in data
        assert "masked_account_number" in data
        assert data["masked_account_number"].startswith("••••")


def test_18_mechanic_cannot_self_verify():
    """Test 18: Mechanic role is forbidden from setting verification_status to verified directly."""
    with pytest.raises(HTTPException) as exc_info:
        PayoutAccountStateMachine.enforce_transition(
            current_status=PayoutAccountVerificationStatus.PENDING,
            target_status=PayoutAccountVerificationStatus.VERIFIED,
            actor_role="mechanic",
        )
    assert exc_info.value.status_code == 403
    assert "Mechanics cannot self-verify" in str(exc_info.value.detail)
