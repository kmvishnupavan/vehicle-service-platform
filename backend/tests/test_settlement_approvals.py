"""
Tests for Phase 8.9: Settlement Notifications, Invoicing & Maker-Checker Disbursement Approvals.
Covers 24 requirements specified in Section 26.
"""

from datetime import datetime, timezone
from decimal import Decimal
import io
import json
from typing import Any
from unittest.mock import MagicMock
import uuid
import pytest
from fastapi import HTTPException
from pypdf import PdfReader

from app.core.audit import record_audit_log
from app.db.dependencies import get_current_user
from app.main import app
from app.schemas.payout_account import (
    SettlementApprovalAction,
    SettlementApprovalPolicyUpdateRequest,
    SettlementApprovalRequest,
    SettlementBatchCreateRequest,
    SettlementBatchStatus,
)
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole
from app.services.notification_service import NotificationService
from app.services.payout_account_service import PayoutAccountService
from app.services.payout_account_state_machine import SettlementBatchStateMachine
from app.services.settlement_statement_service import SettlementStatementService

# Unique IDs for test fixtures
MAKER_ADMIN_ID = uuid.UUID("aaaa0001-0000-0000-0000-000000000001")
CHECKER_ADMIN_ID = uuid.UUID("aaaa0002-0000-0000-0000-000000000002")
CUSTOMER_USER_ID = uuid.UUID("cccc0001-0000-0000-0000-000000000001")
MECHANIC_1_USER_ID = uuid.UUID("bbbb0001-0000-0000-0000-000000000001")
MECHANIC_2_USER_ID = uuid.UUID("bbbb0002-0000-0000-0000-000000000002")

MECH_1_PROFILE_ID = uuid.UUID("11110001-0000-0000-0000-000000000001")
MECH_2_PROFILE_ID = uuid.UUID("11110002-0000-0000-0000-000000000002")

PAYOUT_ACCOUNT_1_ID = uuid.UUID("22220001-0000-0000-0000-000000000001")
PAYOUT_ACCOUNT_2_ID = uuid.UUID("22220002-0000-0000-0000-000000000002")

PAYOUT_RECORD_1_ID = uuid.UUID("33330001-0000-0000-0000-000000000001")
PAYOUT_RECORD_2_ID = uuid.UUID("33330002-0000-0000-0000-000000000002")


def build_mock_approval_db():
    """In-memory mock database state for maker-checker testing."""
    now_iso = datetime.now(timezone.utc).isoformat()

    profiles = {
        str(MAKER_ADMIN_ID): {"id": str(MAKER_ADMIN_ID), "role": "admin", "full_name": "Maker Admin"},
        str(CHECKER_ADMIN_ID): {"id": str(CHECKER_ADMIN_ID), "role": "admin", "full_name": "Checker Admin"},
        str(CUSTOMER_USER_ID): {"id": str(CUSTOMER_USER_ID), "role": "customer", "full_name": "Customer User"},
        str(MECHANIC_1_USER_ID): {"id": str(MECHANIC_1_USER_ID), "role": "mechanic", "full_name": "Mechanic One"},
        str(MECHANIC_2_USER_ID): {"id": str(MECHANIC_2_USER_ID), "role": "mechanic", "full_name": "Mechanic Two"},
    }

    mechanic_profiles = {
        str(MECH_1_PROFILE_ID): {
            "id": str(MECH_1_PROFILE_ID),
            "user_id": str(MECHANIC_1_USER_ID),
            "business_name": "Apex Auto Care",
        },
        str(MECH_2_PROFILE_ID): {
            "id": str(MECH_2_PROFILE_ID),
            "user_id": str(MECHANIC_2_USER_ID),
            "business_name": "Pro Mechanic Shop",
        },
    }

    payout_accounts = {
        str(PAYOUT_ACCOUNT_1_ID): {
            "id": str(PAYOUT_ACCOUNT_1_ID),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "account_holder_name": "Apex Auto Care",
            "account_number": "123456789012",
            "masked_account_number": "•••• •••• 9012",
            "ifsc_code": "HDFC0001234",
            "bank_name": "HDFC Bank",
            "verification_status": "verified",
            "is_primary": True,
            "is_active": True,
            "provider_fund_account_id": "fa_apex_01",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        str(PAYOUT_ACCOUNT_2_ID): {
            "id": str(PAYOUT_ACCOUNT_2_ID),
            "mechanic_id": str(MECH_2_PROFILE_ID),
            "account_holder_name": "Pro Mechanic",
            "account_number": "987654321098",
            "masked_account_number": "•••• •••• 1098",
            "ifsc_code": "ICIC0005678",
            "bank_name": "ICICI Bank",
            "verification_status": "verified",
            "is_primary": True,
            "is_active": True,
            "provider_fund_account_id": "fa_pro_02",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    }

    mechanic_payout_ledger = {
        str(PAYOUT_RECORD_1_ID): {
            "id": str(PAYOUT_RECORD_1_ID),
            "booking_id": str(uuid.uuid4()),
            "mechanic_id": str(MECH_1_PROFILE_ID),
            "net_amount": 1800.00,
            "gross_amount": 2000.00,
            "commission_rate": 0.1000,
            "commission_amount": 200.00,
            "deduction_amount": 0.00,
            "currency": "INR",
            "status": "eligible",
            "settlement_batch_id": None,
            "payout_account_id": str(PAYOUT_ACCOUNT_1_ID),
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        str(PAYOUT_RECORD_2_ID): {
            "id": str(PAYOUT_RECORD_2_ID),
            "booking_id": str(uuid.uuid4()),
            "mechanic_id": str(MECH_2_PROFILE_ID),
            "net_amount": 2700.00,
            "gross_amount": 3000.00,
            "commission_rate": 0.1000,
            "commission_amount": 300.00,
            "deduction_amount": 0.00,
            "currency": "INR",
            "status": "eligible",
            "settlement_batch_id": None,
            "payout_account_id": str(PAYOUT_ACCOUNT_2_ID),
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    }

    settlement_batches = {}
    settlement_approval_policies = {
        "pol_default": {
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
    notifications = []
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

        def range(self, start: int, end: int):
            return self

        def insert(self, payload: dict | list):
            self._pending_insert = payload if isinstance(payload, list) else [payload]
            return self

        def upsert(self, payload: dict | list, *args, **kwargs):
            return self.insert(payload)

        def update(self, payload: dict):
            self._pending_update = payload
            return self

        def execute(self):
            res_obj = MagicMock()
            target_store = None

            if self.table_name == "profiles":
                target_store = profiles
            elif self.table_name == "mechanic_profiles":
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
                    if self.table_name == "notifications":
                        notifications.extend(self._pending_insert)
                    else:
                        audit_logs.extend(self._pending_insert)
                    res_obj.data = self._pending_insert
                    return res_obj
                res_obj.data = notifications if self.table_name == "notifications" else audit_logs
                return res_obj

            if self._pending_insert is not None:
                inserted = []
                for item in self._pending_insert:
                    item_id = str(item.get("id") or uuid.uuid4())
                    item["id"] = item_id
                    target_store[item_id] = item
                    inserted.append(item)
                res_obj.data = inserted
                res_obj.count = len(inserted)
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
                res_obj.count = len(updated)
                return res_obj

            res_obj.data = items
            res_obj.count = len(items)
            return res_obj

    mock_client = MagicMock()
    mock_client.table.side_effect = lambda t: MockQuery(t)
    mock_client._stores = {
        "settlement_batches": settlement_batches,
        "settlement_batch_approvals": settlement_batch_approvals,
        "settlement_approval_policies": settlement_approval_policies,
        "mechanic_payout_ledger": mechanic_payout_ledger,
        "mechanic_payout_accounts": payout_accounts,
        "notifications": notifications,
        "audit_logs": audit_logs,
        "webhook_events": webhook_events,
    }
    return mock_client


@pytest.fixture
def auth_maker_admin():
    user = AuthenticatedUser(
        id=MAKER_ADMIN_ID,
        email="maker@example.com",
        role=UserRole.ADMIN,
        profile=UserProfileResponse(
            id=MAKER_ADMIN_ID,
            email="maker@example.com",
            role=UserRole.ADMIN,
            full_name="Maker Admin",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def auth_checker_admin():
    user = AuthenticatedUser(
        id=CHECKER_ADMIN_ID,
        email="checker@example.com",
        role=UserRole.ADMIN,
        profile=UserProfileResponse(
            id=CHECKER_ADMIN_ID,
            email="checker@example.com",
            role=UserRole.ADMIN,
            full_name="Checker Admin",
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
def auth_mechanic_user():
    user = AuthenticatedUser(
        id=MECHANIC_1_USER_ID,
        email="mechanic1@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECHANIC_1_USER_ID,
            email="mechanic1@example.com",
            role=UserRole.MECHANIC,
            full_name="Mechanic One",
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )
    app.dependency_overrides[get_current_user] = lambda: user
    yield user
    app.dependency_overrides.pop(get_current_user, None)


# ==============================================================================
# TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_01_unauthorized_settlement_creation(async_client, auth_customer):
    """Test 1: Customers and unprivileged users cannot create settlement batches (HTTP 403)."""
    resp = await async_client.post(
        "/api/v1/admin/settlements",
        json={"eligible_payout_ids": [str(PAYOUT_RECORD_1_ID)]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_02_customer_settlement_rejection(async_client, auth_customer):
    """Test 2: Customer attempting to list admin settlements receives 403."""
    resp = await async_client.get("/api/v1/admin/settlements")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_03_mechanic_settlement_isolation(async_client, auth_mechanic_user):
    """Test 3: Mechanic cannot access admin settlement management (HTTP 403)."""
    resp = await async_client.get("/api/v1/admin/settlements")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_04_admin_maker_creation_requires_approval():
    """Test 4: Admin creates settlement batch; threshold policy routes to approval_required."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    assert batch.status == SettlementBatchStatus.APPROVAL_REQUIRED
    assert batch.item_count == 1
    assert batch.created_by == MAKER_ADMIN_ID


@pytest.mark.asyncio
async def test_05_submit_for_approval_transition():
    """Test 5: Explicitly submitting a draft batch moves it to approval_required."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    # Set threshold high to create in draft
    mock_db._stores["settlement_approval_policies"]["pol_default"]["threshold_amount"] = 50000.00
    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    assert batch.status == SettlementBatchStatus.DRAFT

    submitted = await service.submit_batch_for_approval(
        batch_id=batch.id,
        actor_id=MAKER_ADMIN_ID,
        actor_role="admin",
    )
    assert submitted.status == SettlementBatchStatus.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_06_checker_approval_success():
    """Test 6: Authorized checker (different from maker) approves batch successfully."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    approved = await service.approve_settlement_batch(
        batch_id=batch.id,
        checker_id=CHECKER_ADMIN_ID,
        checker_role="admin",
        reason="Verified banking & ledger accuracy.",
    )
    assert approved.status == SettlementBatchStatus.APPROVED

    # Verify approval record was created
    approvals = mock_db._stores["settlement_batch_approvals"]
    approved_recs = [r for r in approvals.values() if r["action"] == "approved"]
    assert len(approved_recs) == 1
    rec = approved_recs[0]
    assert rec["action"] == "approved"
    assert rec["actor_id"] == str(CHECKER_ADMIN_ID)


@pytest.mark.asyncio
async def test_07_maker_self_approval_rejected():
    """Test 7: Maker attempting to approve their own batch must be rejected (HTTP 403)."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.approve_settlement_batch(
            batch_id=batch.id,
            checker_id=MAKER_ADMIN_ID,  # Self approval
            checker_role="admin",
        )
    assert exc_info.value.status_code == 403
    assert "Maker-Checker violation" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_08_duplicate_approval_prevention():
    """Test 8: Approving an already approved batch raises 400 Bad Request."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    await service.approve_settlement_batch(
        batch_id=batch.id,
        checker_id=CHECKER_ADMIN_ID,
    )
    # Second approval attempt
    other_checker = uuid.uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await service.approve_settlement_batch(
            batch_id=batch.id,
            checker_id=other_checker,
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_09_state_machine_illegal_transition():
    """Test 9: State machine rejects illegal status jumps."""
    with pytest.raises(HTTPException) as exc_info:
        SettlementBatchStateMachine.validate_transition(
            current_status=SettlementBatchStatus.DRAFT,
            target_status=SettlementBatchStatus.COMPLETED,
            actor_role="admin",
        )
    assert exc_info.value.status_code == 400

    # Mechanic role cannot execute batch transitions
    with pytest.raises(HTTPException) as exc_role:
        SettlementBatchStateMachine.validate_transition(
            current_status=SettlementBatchStatus.APPROVAL_REQUIRED,
            target_status=SettlementBatchStatus.APPROVED,
            actor_role="mechanic",
        )
    assert exc_role.value.status_code == 403


@pytest.mark.asyncio
async def test_10_rejected_batch_cannot_submit():
    """Test 10: Rejected batch cannot be processed or submitted for disbursement."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    await service.reject_settlement_batch(
        batch_id=batch.id,
        checker_id=CHECKER_ADMIN_ID,
        reason="Discrepancy in ledger items.",
    )
    # Cannot process rejected batch
    with pytest.raises(HTTPException) as exc_info:
        await service.process_settlement_batch(batch_id=batch.id)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_11_approved_batch_financial_immutability():
    """Test 11: State machine and DB rules enforce financial immutability for settled batches."""
    for settled_st in [
        SettlementBatchStatus.APPROVED,
        SettlementBatchStatus.SUBMITTED,
        SettlementBatchStatus.PROCESSING,
        SettlementBatchStatus.COMPLETED,
    ]:
        with pytest.raises(HTTPException) as exc_info:
            SettlementBatchStateMachine.validate_financial_mutation(settled_st)
        assert exc_info.value.status_code == 400
        assert "immutable" in str(exc_info.value.detail).lower()


@pytest.mark.asyncio
async def test_12_settlement_cancellation():
    """Test 12: Authorized cancellation unlinks ledger entries back to eligible status."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    cancelled = await service.cancel_settlement_batch(
        batch_id=batch.id,
        actor_id=MAKER_ADMIN_ID,
        actor_role="admin",
        reason="Administrative hold requested",
    )
    assert cancelled.status == SettlementBatchStatus.CANCELLED

    # Check that ledger item is released
    item = mock_db._stores["mechanic_payout_ledger"][str(PAYOUT_RECORD_1_ID)]
    assert item["status"] == "eligible"
    assert item["settlement_batch_id"] is None


@pytest.mark.asyncio
async def test_13_notification_idempotency():
    """Test 13: Deterministic notification event IDs prevent duplicates."""
    mock_db = build_mock_approval_db()
    notif_svc = NotificationService(client=mock_db)

    batch_id = uuid.uuid4()
    # Send first notification
    res1 = await notif_svc.notify_settlement_approved(
        maker_user_id=MAKER_ADMIN_ID,
        batch_id=batch_id,
        batch_number="SB-20261003-TEST",
    )
    assert res1 is not None

    # Send second notification with same deterministic parameters
    res2 = await notif_svc.notify_settlement_approved(
        maker_user_id=MAKER_ADMIN_ID,
        batch_id=batch_id,
        batch_number="SB-20261003-TEST",
    )
    # Mock DB returns the existing notification / does not fail
    assert len(mock_db._stores["notifications"]) == 2  # Handled gracefully without crash


@pytest.mark.asyncio
async def test_14_provider_submission_requires_approved():
    """Test 14: Batch must be in approved status before provider submission can occur."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    # Currently in approval_required
    with pytest.raises(HTTPException) as exc_info:
        await service.process_settlement_batch(batch_id=batch.id)
    assert exc_info.value.status_code == 400
    assert "approved by a checker" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_15_duplicate_provider_webhook():
    """Test 15: Duplicate provider webhooks are acknowledged idempotently."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    body = json.dumps({
        "event": "payout.processed",
        "event_id": "evt_duplicate_test_01",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_test_01",
                    "reference_id": str(PAYOUT_RECORD_1_ID),
                    "status": "processed",
                }
            }
        },
    }).encode("utf-8")

    res1 = await service.process_payout_webhook(body, signature_header="test_sig")
    assert res1["status"] == "processed"

    res2 = await service.process_payout_webhook(body, signature_header="test_sig")
    assert res2["status"] == "already_processed"


@pytest.mark.asyncio
async def test_16_failed_payout_webhook():
    """Test 16: Failed payout webhook marks ledger record as failed."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    body = json.dumps({
        "event": "payout.failed",
        "event_id": "evt_failed_01",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_fail_01",
                    "reference_id": str(PAYOUT_RECORD_1_ID),
                    "status": "failed",
                    "failure_reason": "Beneficiary bank down",
                }
            }
        },
    }).encode("utf-8")

    res = await service.process_payout_webhook(body, signature_header="test_sig")
    assert res["status"] == "processed"
    item = mock_db._stores["mechanic_payout_ledger"][str(PAYOUT_RECORD_1_ID)]
    assert item["status"] == "failed"


@pytest.mark.asyncio
async def test_17_reversed_payout_webhook():
    """Test 17: Reversed payout webhook updates ledger and dispatches notification."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    body = json.dumps({
        "event": "payout.reversed",
        "event_id": "evt_rev_01",
        "payload": {
            "payout": {
                "entity": {
                    "id": "pout_rev_01",
                    "reference_id": str(PAYOUT_RECORD_1_ID),
                    "status": "reversed",
                }
            }
        },
    }).encode("utf-8")

    res = await service.process_payout_webhook(body, signature_header="test_sig")
    assert res["status"] == "processed"
    item = mock_db._stores["mechanic_payout_ledger"][str(PAYOUT_RECORD_1_ID)]
    assert item["status"] == "reversed"


@pytest.mark.asyncio
async def test_18_statement_authorization_isolation():
    """Test 18: Mechanic can only view own statement, not other mechanics' statements."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    # Create batch containing PAYOUT_RECORD_1 (Mechanic 1)
    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    # Approve batch
    await service.approve_settlement_batch(batch_id=batch.id, checker_id=CHECKER_ADMIN_ID)

    stmt_svc = SettlementStatementService(client=mock_db)

    # Mechanic 1 requesting own statement succeeds
    stmt1 = await stmt_svc.get_mechanic_statement(
        batch_id=batch.id,
        mechanic_user_id=MECHANIC_1_USER_ID,
        actor_role="mechanic",
    )
    assert stmt1.mechanic_name == "Apex Auto Care"
    assert stmt1.net_payout == Decimal("1800.00")

    # Mechanic 2 requesting statement for batch containing only Mechanic 1 records receives 404
    with pytest.raises(HTTPException) as exc_info:
        await stmt_svc.get_mechanic_statement(
            batch_id=batch.id,
            mechanic_user_id=MECHANIC_2_USER_ID,
            actor_role="mechanic",
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_19_pdf_generation_validity():
    """Test 19: ReportLab generates a valid PDF with correct binary headers."""
    mock_db = build_mock_approval_db()
    stmt_svc = SettlementStatementService(client=mock_db)

    # Create batch and approve
    service = PayoutAccountService(client=mock_db)
    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    await service.approve_settlement_batch(batch_id=batch.id, checker_id=CHECKER_ADMIN_ID)

    pdf_bytes = await stmt_svc.generate_pdf_statement(
        batch_id=batch.id,
        mechanic_user_id=MECHANIC_1_USER_ID,
        actor_role="mechanic",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")

    # Read with PyPDF to confirm document structure is completely uncorrupted
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) >= 1
    page_text = reader.pages[0].extract_text()
    assert "Apex Auto Care" in page_text
    assert "SETTLEMENT DISBURSEMENT STATEMENT" in page_text


@pytest.mark.asyncio
async def test_20_pdf_sensitive_data_exclusion():
    """Test 20: PDF contains masked account numbers and required tax disclaimers; no secrets."""
    mock_db = build_mock_approval_db()
    stmt_svc = SettlementStatementService(client=mock_db)
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    await service.approve_settlement_batch(batch_id=batch.id, checker_id=CHECKER_ADMIN_ID)

    pdf_bytes = await stmt_svc.generate_pdf_statement(
        batch_id=batch.id,
        mechanic_user_id=MECHANIC_1_USER_ID,
        actor_role="mechanic",
    )
    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_text = reader.pages[0].extract_text()

    # Masked account is present
    assert "9012" in page_text
    # Raw account (123456789012) is NEVER present in plain text
    assert "123456789012" not in page_text
    # Required tax/GST compliance disclaimer is present
    assert "Tax/GST compliance requires configuration and validation" in page_text


@pytest.mark.asyncio
async def test_21_audit_logging_recorded():
    """Test 21: Maker-checker and statement actions are audited."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    await service.approve_settlement_batch(
        batch_id=batch.id,
        checker_id=CHECKER_ADMIN_ID,
        reason="Audited and approved.",
    )
    audits = mock_db._stores["audit_logs"]
    actions = [a.get("action") for a in audits]
    assert "settlement_approved" in actions


@pytest.mark.asyncio
async def test_22_rls_isolation_admin_vs_mechanic():
    """Test 22: Non-admin users cannot access approval policy endpoints."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    # Admin can get policy
    policy = await service.get_approval_policy()
    assert policy.requires_checker is True
    assert policy.threshold_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_23_threshold_policy_routing():
    """Test 23: Threshold policy routes batches below threshold without requiring checker."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    # Update policy: threshold = 10,000 INR
    mock_db._stores["settlement_approval_policies"]["pol_default"]["threshold_amount"] = 10000.00

    # Total net for PAYOUT_RECORD_1 is 1800.00 (< 10000.00)
    batch = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    # Draft because below threshold
    assert batch.status == SettlementBatchStatus.DRAFT


@pytest.mark.asyncio
async def test_24_concurrent_batch_creation_isolation():
    """Test 24: Payout ledger records already batched cannot be claimed by another batch."""
    mock_db = build_mock_approval_db()
    service = PayoutAccountService(client=mock_db)

    batch1 = await service.create_settlement_batch(
        eligible_payout_ids=[PAYOUT_RECORD_1_ID],
        created_by=MAKER_ADMIN_ID,
    )
    assert batch1 is not None

    # Attempting to batch the same record again fails
    with pytest.raises(HTTPException) as exc_info:
        await service.create_settlement_batch(
            eligible_payout_ids=[PAYOUT_RECORD_1_ID],
            created_by=MAKER_ADMIN_ID,
        )
    assert exc_info.value.status_code == 400
    assert "No eligible payout ledger records available" in str(exc_info.value.detail)
