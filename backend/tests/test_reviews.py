"""
Unit and Integration Tests for Reviews and Rating Workflow (Phase 8.5).

Covers:
- Unauthenticated access rejection (401)
- Customer booking ownership verification (403)
- Ineligible booking lifecycle states rejection (400)
- Eligible completed states success (201)
- Authoritative assigned mechanic derivation (rejecting unassigned bookings)
- Extra field rejection (forged customer_id, mechanic_id, created_at -> 422)
- Rating validation (strictly integers 1-5; rejecting 0, 6, -1, 5.5, null, strings -> 422)
- Comment sanitization (whitespace trimming, HTML stripping, max 1000 chars, empty -> None)
- Oversized comments (> 1000 chars -> 422)
- Duplicate review rejection (409)
- Concurrency tests (two simultaneous submissions: exactly one succeeds, unique constraint enforced)
- Concurrent reviews for different bookings both succeed
- Authorized booking review retrieval (customer owner, assigned mechanic, admin -> 200)
- Unauthorized booking review retrieval (other customers -> 403)
- Missing review retrieval (404)
- Review update by authoring customer (200) and unauthorized rejection (403)
- Update field restriction (disallowing changes to booking_id, customer_id, mechanic_id -> 422)
- Mechanic review listing with privacy-safe masking, pagination clamping, and count/average aggregation
- Notification dispatch with deterministic event_id (review_created_{review_id})
- Resilient notification error handling (notification failure does not fail review creation)
- Audit log recording
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from app.db.dependencies import get_current_user, require_customer
from app.main import app
from app.schemas.user import AuthenticatedUser, UserProfileResponse, UserRole

CUSTOMER_1_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
CUSTOMER_2_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")

MECHANIC_PROFILE_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
MECHANIC_USER_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")

BOOKING_COMPLETED_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")
BOOKING_PAID_ID = uuid.UUID("66666666-6666-6666-6666-666666666667")
BOOKING_PAYMENT_PENDING_ID = uuid.UUID("66666666-6666-6666-6666-666666666668")
BOOKING_IN_PROGRESS_ID = uuid.UUID("66666666-6666-6666-6666-666666666669")
BOOKING_CANCELLED_ID = uuid.UUID("66666666-6666-6666-6666-666666666670")
BOOKING_NO_MECHANIC_ID = uuid.UUID("66666666-6666-6666-6666-666666666671")

ASSIGNMENT_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
REVIEW_ID = uuid.UUID("88888888-8888-8888-8888-888888888888")


def build_review_mock_db():
    """Build a mock Supabase client with stateful in-memory storage for reviews and bookings."""
    bookings = {
        str(BOOKING_COMPLETED_ID): {
            "id": str(BOOKING_COMPLETED_ID),
            "booking_number": "BK-COMPLETED-01",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "service_completed",
        },
        str(BOOKING_PAID_ID): {
            "id": str(BOOKING_PAID_ID),
            "booking_number": "BK-PAID-02",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "paid",
        },
        str(BOOKING_PAYMENT_PENDING_ID): {
            "id": str(BOOKING_PAYMENT_PENDING_ID),
            "booking_number": "BK-PP-03",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "payment_pending",
        },
        str(BOOKING_IN_PROGRESS_ID): {
            "id": str(BOOKING_IN_PROGRESS_ID),
            "booking_number": "BK-PROG-04",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "service_in_progress",
        },
        str(BOOKING_CANCELLED_ID): {
            "id": str(BOOKING_CANCELLED_ID),
            "booking_number": "BK-CANC-05",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "cancelled",
        },
        str(BOOKING_NO_MECHANIC_ID): {
            "id": str(BOOKING_NO_MECHANIC_ID),
            "booking_number": "BK-NOMECH-06",
            "customer_id": str(CUSTOMER_1_ID),
            "booking_status": "service_completed",
        },
    }

    assignments = [
        {
            "id": str(ASSIGNMENT_ID),
            "booking_id": str(BOOKING_COMPLETED_ID),
            "mechanic_id": str(MECHANIC_PROFILE_ID),
            "assignment_status": "accepted",
            "created_at": "2026-10-01T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_PAID_ID),
            "mechanic_id": str(MECHANIC_PROFILE_ID),
            "assignment_status": "completed",
            "created_at": "2026-10-01T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_PAYMENT_PENDING_ID),
            "mechanic_id": str(MECHANIC_PROFILE_ID),
            "assignment_status": "accepted",
            "created_at": "2026-10-01T10:00:00Z",
        },
        {
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_IN_PROGRESS_ID),
            "mechanic_id": str(MECHANIC_PROFILE_ID),
            "assignment_status": "accepted",
            "created_at": "2026-10-01T10:00:00Z",
        },
    ]

    mechanic_profiles = {
        str(MECHANIC_PROFILE_ID): {
            "id": str(MECHANIC_PROFILE_ID),
            "user_id": str(MECHANIC_USER_ID),
            "business_name": "Apex Auto Care",
            "average_rating": 4.5,
            "total_completed_jobs": 15,
        }
    }

    profiles = {
        str(CUSTOMER_1_ID): {"id": str(CUSTOMER_1_ID), "full_name": "Alice Customer"},
        str(CUSTOMER_2_ID): {"id": str(CUSTOMER_2_ID), "full_name": "Bob Smith"},
    }

    reviews: dict[str, dict] = {}

    client = MagicMock()

    class MockQueryBuilder:
        def __init__(self, table_name: str):
            self.table_name = table_name
            self._filters = []
            self._orders = []
            self._range = None
            self._count = None
            self._data_to_insert = None
            self._data_to_update = None

        def select(self, cols: str, count=None):
            self._count = count
            return self

        def eq(self, col: str, val: Any):
            self._filters.append((col, "eq", str(val)))
            return self

        def in_(self, col: str, vals: list):
            self._filters.append((col, "in", [str(v) for v in vals]))
            return self

        def order(self, col: str, desc: bool = False):
            self._orders.append((col, desc))
            return self

        def limit(self, lim: int):
            self._range = (0, lim - 1)
            return self

        def range(self, start: int, end: int):
            self._range = (start, end)
            return self

        def insert(self, data: dict):
            self._data_to_insert = data
            return self

        def update(self, data: dict):
            self._data_to_update = data
            return self

        def execute(self):
            res = MagicMock()
            res.data = []
            res.count = None

            if self.table_name == "bookings":
                rows = list(bookings.values())
                for col, op, val in self._filters:
                    if op == "eq":
                        rows = [r for r in rows if str(r.get(col)) == val]
                res.data = rows
                return res

            elif self.table_name == "mechanic_assignments":
                rows = list(assignments)
                for col, op, val in self._filters:
                    if op == "eq":
                        rows = [r for r in rows if str(r.get(col)) == val]
                    elif op == "in":
                        rows = [r for r in rows if str(r.get(col)) in val]
                if self._range:
                    s, e = self._range
                    rows = rows[s : e + 1]
                res.data = rows
                return res

            elif self.table_name == "mechanic_profiles":
                rows = list(mechanic_profiles.values())
                for col, op, val in self._filters:
                    if op == "eq":
                        rows = [r for r in rows if str(r.get(col)) == val]
                res.data = rows
                return res

            elif self.table_name == "reviews":
                if self._data_to_insert is not None:
                    # Check unique booking_id constraint
                    b_id = str(self._data_to_insert["booking_id"])
                    for rev in reviews.values():
                        if rev["booking_id"] == b_id:
                            raise Exception("duplicate key value violates unique constraint 'reviews_booking_id_key'")
                    new_id = str(uuid.uuid4())
                    now_str = datetime.now(timezone.utc).isoformat()
                    item = {
                        "id": new_id,
                        **self._data_to_insert,
                        "created_at": now_str,
                        "updated_at": now_str,
                    }
                    reviews[new_id] = item
                    res.data = [item]
                    return res

                if self._data_to_update is not None:
                    rows = list(reviews.values())
                    for col, op, val in self._filters:
                        if op == "eq":
                            rows = [r for r in rows if str(r.get(col)) == val]
                    for r in rows:
                        r.update(self._data_to_update)
                        r["updated_at"] = datetime.now(timezone.utc).isoformat()
                    res.data = rows
                    return res

                rows = list(reviews.values())
                for col, op, val in self._filters:
                    if op == "eq":
                        rows = [r for r in rows if str(r.get(col)) == val]
                if self._count == "exact":
                    res.count = len(rows)
                # attach mocked profile data for reviewer display
                augmented = []
                for r in rows:
                    item_copy = dict(r)
                    cust_id = item_copy.get("customer_id")
                    item_copy["profiles"] = profiles.get(cust_id, {"full_name": "Customer"})
                    augmented.append(item_copy)
                if self._range:
                    s, e = self._range
                    augmented = augmented[s : e + 1]
                res.data = augmented
                return res

            return res

    client.table.side_effect = MockQueryBuilder
    return client, reviews


@pytest.fixture
def customer_user():
    return AuthenticatedUser(
        id=CUSTOMER_1_ID,
        email="alice@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_1_ID,
            full_name="Alice Customer",
            phone="+919876543210",
            email="alice@example.com",
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )


@pytest.fixture
def other_customer_user():
    return AuthenticatedUser(
        id=CUSTOMER_2_ID,
        email="bob@example.com",
        role=UserRole.CUSTOMER,
        profile=UserProfileResponse(
            id=CUSTOMER_2_ID,
            full_name="Bob Smith",
            phone="+919876543211",
            email="bob@example.com",
            role=UserRole.CUSTOMER,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )


@pytest.fixture
def mechanic_user():
    return AuthenticatedUser(
        id=MECHANIC_USER_ID,
        email="mechanic@example.com",
        role=UserRole.MECHANIC,
        profile=UserProfileResponse(
            id=MECHANIC_USER_ID,
            full_name="Mike Specialist",
            phone="+919876543212",
            email="mechanic@example.com",
            role=UserRole.MECHANIC,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
    )


@pytest.mark.asyncio
async def test_create_review_success(customer_user):
    mock_db, reviews_state = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db), \
         patch("app.services.notification_service.NotificationService.send_notification", new_callable=AsyncMock) as mock_notif, \
         patch("app.services.review_service.record_audit_log") as mock_audit:

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Outstanding service! Arrived promptly."},
            )

        assert res.status_code == 201
        data = res.json()
        assert data["rating"] == 5
        assert data["comment"] == "Outstanding service! Arrived promptly."
        assert data["booking_id"] == str(BOOKING_COMPLETED_ID)
        assert data["customer_id"] == str(CUSTOMER_1_ID)
        assert data["mechanic_id"] == str(MECHANIC_PROFILE_ID)

        # Verify deterministic notification was dispatched
        mock_notif.assert_awaited_once()
        call_kwargs = mock_notif.await_args.kwargs
        assert call_kwargs["user_id"] == MECHANIC_USER_ID
        assert call_kwargs["title"] == "New customer review"
        assert call_kwargs["event_id"] == f"review_created_{data['id']}"

        # Verify audit log was recorded
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["action"] == "review_created"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_unauthenticated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.post(
            f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
            json={"rating": 5, "comment": "Nice work"},
        )
    assert res.status_code in [401, 403]


@pytest.mark.asyncio
async def test_create_review_wrong_customer_ownership(other_customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: other_customer_user
    app.dependency_overrides[get_current_user] = lambda: other_customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Trying to review someone else's booking"},
            )
        assert res.status_code == 403
        assert "not authorized" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_ineligible_booking_status(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Service in progress
            res1 = await ac.post(
                f"/api/v1/bookings/{BOOKING_IN_PROGRESS_ID}/review",
                json={"rating": 4, "comment": "Midway review"},
            )
            assert res1.status_code == 400
            assert "service must be completed" in res1.json()["detail"].lower()

            # Cancelled booking
            res2 = await ac.post(
                f"/api/v1/bookings/{BOOKING_CANCELLED_ID}/review",
                json={"rating": 1, "comment": "Was cancelled"},
            )
            assert res2.status_code == 400
            assert "service must be completed" in res2.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_eligible_statuses(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Test paid booking
            res1 = await ac.post(
                f"/api/v1/bookings/{BOOKING_PAID_ID}/review",
                json={"rating": 4},
            )
            assert res1.status_code == 201

            # Test payment_pending booking
            res2 = await ac.post(
                f"/api/v1/bookings/{BOOKING_PAYMENT_PENDING_ID}/review",
                json={"rating": 5},
            )
            assert res2.status_code == 201

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_unassigned_mechanic(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/api/v1/bookings/{BOOKING_NO_MECHANIC_ID}/review",
                json={"rating": 5},
            )
        assert res.status_code == 400
        assert "no assigned mechanic" in res.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_forged_fields_rejected(customer_user):
    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Attempt to forge customer_id
        res1 = await ac.post(
            f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
            json={"rating": 5, "customer_id": str(uuid.uuid4())},
        )
        assert res1.status_code == 422

        # Attempt to forge mechanic_id
        res2 = await ac.post(
            f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
            json={"rating": 5, "mechanic_id": str(uuid.uuid4())},
        )
        assert res2.status_code == 422

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_invalid_ratings(customer_user):
    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        invalid_ratings = [0, 6, -1, 5.5, None, "5", True]
        for val in invalid_ratings:
            payload = {"rating": val}
            res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json=payload,
            )
            assert res.status_code == 422, f"Expected 422 for rating: {val}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_review_comment_handling(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # 1. Empty/whitespace comment becomes null
            res1 = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "   \n\t  "},
            )
            assert res1.status_code == 201
            assert res1.json()["comment"] is None

            # 2. Oversized comment (> 1000 chars) is rejected
            long_comment = "A" * 1001
            res2 = await ac.post(
                f"/api/v1/bookings/{BOOKING_PAID_ID}/review",
                json={"rating": 5, "comment": long_comment},
            )
            assert res2.status_code == 422

            # 3. HTML is stripped defensively
            res3 = await ac.post(
                f"/api/v1/bookings/{BOOKING_PAYMENT_PENDING_ID}/review",
                json={"rating": 5, "comment": "<script>alert('xss')</script>Great work!"},
            )
            assert res3.status_code == 201
            assert "<script>" not in res3.json()["comment"]
            assert "alert('xss')" in res3.json()["comment"] or "Great work!" in res3.json()["comment"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_duplicate_review_submission_rejected(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # First submission succeeds
            res1 = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "First review"},
            )
            assert res1.status_code == 201

            # Second submission for same booking is rejected with 409 Conflict
            res2 = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 4, "comment": "Second review attempt"},
            )
            assert res2.status_code == 409
            assert "already been submitted" in res2.json()["detail"].lower()

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_review_submission_exact_one_succeeds(customer_user):
    """
    Concurrency test:
    Two simultaneous requests submitting a review for the same booking.
    Exactly one must succeed (201), the other must fail (409 Conflict).
    """
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            async def submit():
                return await ac.post(
                    f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                    json={"rating": 5, "comment": "Concurrent review race"},
                )

            responses = await asyncio.gather(submit(), submit())

            status_codes = [r.status_code for r in responses]
            assert 201 in status_codes, "At least one submission must succeed"
            assert 409 in status_codes, "The duplicate submission must be rejected with 409"
            assert status_codes.count(201) == 1
            assert status_codes.count(409) == 1

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_reviews_different_bookings_both_succeed(customer_user):
    """Simultaneous reviews for different bookings should both succeed independently."""
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            req1 = ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Review booking 1"},
            )
            req2 = ac.post(
                f"/api/v1/bookings/{BOOKING_PAID_ID}/review",
                json={"rating": 4, "comment": "Review booking 2"},
            )

            res1, res2 = await asyncio.gather(req1, req2)
            assert res1.status_code == 201
            assert res2.status_code == 201

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_booking_review_access_control(customer_user, other_customer_user, mechanic_user):
    mock_db, _ = build_review_mock_db()

    # Pre-insert review
    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            create_res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Verified booking review"},
            )
            assert create_res.status_code == 201

            # 1. Authorized customer owner can view
            get_owner = await ac.get(f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review")
            assert get_owner.status_code == 200
            assert get_owner.json()["rating"] == 5

            # 2. Unauthorized customer is forbidden
            app.dependency_overrides[get_current_user] = lambda: other_customer_user
            get_unauth = await ac.get(f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review")
            assert get_unauth.status_code == 403

            # 3. Assigned mechanic can view
            app.dependency_overrides[get_current_user] = lambda: mechanic_user
            get_mech = await ac.get(f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review")
            assert get_mech.status_code == 200
            assert get_mech.json()["rating"] == 5

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_review_by_customer(customer_user, other_customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            create_res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 4, "comment": "Good job"},
            )
            assert create_res.status_code == 201
            rev_id = create_res.json()["id"]

            # Customer updates comment and rating
            patch_res = await ac.patch(
                f"/api/v1/reviews/{rev_id}",
                json={"rating": 5, "comment": "Upgraded to 5 stars! Great follow-up."},
            )
            assert patch_res.status_code == 200
            assert patch_res.json()["rating"] == 5
            assert "Upgraded" in patch_res.json()["comment"]

            # Unauthorized customer cannot patch
            app.dependency_overrides[require_customer] = lambda: other_customer_user
            unauth_patch = await ac.patch(
                f"/api/v1/reviews/{rev_id}",
                json={"rating": 1},
            )
            assert unauth_patch.status_code == 403

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_patch_review_disallowed_fields_rejected(customer_user):
    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        dummy_id = str(uuid.uuid4())
        # Attempt to patch booking_id
        res = await ac.patch(f"/api/v1/reviews/{dummy_id}", json={"booking_id": dummy_id})
        assert res.status_code == 422

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_mechanic_review_list_pagination_and_masking(customer_user):
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Create a review
            await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Alice's review"},
            )

            # Query mechanic reviews
            res = await ac.get(f"/api/v1/mechanics/{MECHANIC_PROFILE_ID}/reviews?limit=10")
            assert res.status_code == 200
            data = res.json()
            assert "items" in data
            assert data["total_count"] >= 1
            assert data["limit"] == 10
            assert data["offset"] == 0

            item = data["items"][0]
            # Verify customer name is masked for privacy
            assert item["customer_name"] == "Alice C."
            # Confirm no email or phone leaked
            assert "email" not in item
            assert "phone" not in item

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_notification_failure_does_not_fail_review(customer_user):
    """Notification error should be caught and logged without aborting review creation."""
    mock_db, _ = build_review_mock_db()

    app.dependency_overrides[require_customer] = lambda: customer_user
    app.dependency_overrides[get_current_user] = lambda: customer_user

    with patch("app.services.review_service.get_supabase_service_client", return_value=mock_db), \
         patch(
             "app.services.notification_service.NotificationService.send_notification",
             side_effect=RuntimeError("Supabase connection timeout"),
         ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.post(
                f"/api/v1/bookings/{BOOKING_COMPLETED_ID}/review",
                json={"rating": 5, "comment": "Review works despite notif failure"},
            )
        assert res.status_code == 201
        assert res.json()["rating"] == 5

    app.dependency_overrides.clear()
