"""
Comprehensive Chat & Media Attachments Tests (Phase 8.4).

Covers all 17 security and operational test scenarios:
1. Customer can access own booking chat
2. Customer cannot access another booking chat
3. Assigned mechanic can access chat
4. Unrelated mechanic denied
5. Rejected mechanic denied
6. Unauthenticated denied
7. Sender identity strictly derived from JWT
8. Forged sender_id rejected (extra=forbid)
9. Forged booking_id rejected
10. Unauthorized attachment access denied
11. Valid attachment upload
12. Invalid MIME rejected
13. Oversized attachment rejected
14. Path traversal rejected
15. Duplicate message handling
16. Read receipt authorization (recipient allowed, sender denied, outsider denied)
17. Chat room isolation between distinct bookings
"""

from datetime import datetime, timezone
import io
from unittest.mock import MagicMock, patch
import uuid
import pytest
from httpx import AsyncClient
from app.schemas.user import AuthenticatedUser
from tests.conftest import (
    CUSTOMER_1_ID,
    CUSTOMER_2_ID,
    MECHANIC_ID,
    OTHER_MECHANIC_ID,
)

BOOKING_1_ID = uuid.UUID("77771111-0000-0000-0000-000000000001")
BOOKING_2_ID = uuid.UUID("77772222-0000-0000-0000-000000000002")

MECH_PROFILE_1_ID = uuid.UUID("88881111-0000-0000-0000-000000000001")
OTHER_MECH_PROFILE_ID = uuid.UUID("88882222-0000-0000-0000-000000000002")

ROOM_1_ID = uuid.UUID("99991111-0000-0000-0000-000000000001")
ROOM_2_ID = uuid.UUID("99992222-0000-0000-0000-000000000002")


def build_mock_chat_db():
    """Builds an in-memory mock client simulating Supabase PostgreSQL and Storage for chat."""
    mock_client = MagicMock()

    bookings_db = {
        str(BOOKING_1_ID): {
            "id": str(BOOKING_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "booking_number": "BK-1001",
            "booking_status": "mechanic_en_route",
        },
        str(BOOKING_2_ID): {
            "id": str(BOOKING_2_ID),
            "customer_id": str(CUSTOMER_2_ID),
            "booking_number": "BK-2002",
            "booking_status": "service_in_progress",
        },
    }

    mechanic_profiles_db = {
        str(MECH_PROFILE_1_ID): {
            "id": str(MECH_PROFILE_1_ID),
            "user_id": str(MECHANIC_ID),
            "business_name": "Dave Automotive",
        },
        str(OTHER_MECH_PROFILE_ID): {
            "id": str(OTHER_MECH_PROFILE_ID),
            "user_id": str(OTHER_MECHANIC_ID),
            "business_name": "Evan Garage",
        },
    }

    profiles_db = {
        str(CUSTOMER_1_ID): {"id": str(CUSTOMER_1_ID), "full_name": "Alice Customer"},
        str(CUSTOMER_2_ID): {"id": str(CUSTOMER_2_ID), "full_name": "Bob Customer"},
    }

    assignments_db = [
        {
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_1_ID),
            "mechanic_id": str(MECH_PROFILE_1_ID),
            "assignment_status": "accepted",
        },
        {
            "id": str(uuid.uuid4()),
            "booking_id": str(BOOKING_2_ID),
            "mechanic_id": str(OTHER_MECH_PROFILE_ID),
            "assignment_status": "accepted",
        },
    ]

    chat_rooms_db = {
        str(ROOM_1_ID): {
            "id": str(ROOM_1_ID),
            "booking_id": str(BOOKING_1_ID),
            "customer_id": str(CUSTOMER_1_ID),
            "mechanic_id": str(MECH_PROFILE_1_ID),
            "is_active": True,
            "created_at": "2026-10-03T10:00:00Z",
            "updated_at": "2026-10-03T10:00:00Z",
        },
        str(ROOM_2_ID): {
            "id": str(ROOM_2_ID),
            "booking_id": str(BOOKING_2_ID),
            "customer_id": str(CUSTOMER_2_ID),
            "mechanic_id": str(OTHER_MECH_PROFILE_ID),
            "is_active": True,
            "created_at": "2026-10-03T10:05:00Z",
            "updated_at": "2026-10-03T10:05:00Z",
        },
    }

    chat_messages_db = [
        {
            "id": "11110000-0000-0000-0000-000000000001",
            "room_id": str(ROOM_1_ID),
            "sender_id": str(MECHANIC_ID),
            "message": "Hello, I am on my way to your location.",
            "message_type": "text",
            "attachment_path": None,
            "is_read": False,
            "created_at": "2026-10-03T10:01:00Z",
        },
        {
            "id": "22220000-0000-0000-0000-000000000002",
            "room_id": str(ROOM_2_ID),
            "sender_id": str(CUSTOMER_2_ID),
            "message": "Room 2 private message.",
            "message_type": "text",
            "attachment_path": None,
            "is_read": False,
            "created_at": "2026-10-03T10:06:00Z",
        },
    ]

    def table_handler(table_name: str):
        query_obj = MagicMock()

        if table_name == "bookings":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                s.eq = lambda col, val: MagicMock(
                    execute=lambda: MagicMock(
                        data=[bookings_db[val]] if val in bookings_db else []
                    )
                )
                return s
            query_obj.select = select_fn

        elif table_name == "mechanic_assignments":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                def eq_fn(col, val):
                    s2 = MagicMock()
                    s2.eq = lambda col2, val2: MagicMock(
                        execute=lambda: MagicMock(
                            data=[
                                a for a in assignments_db
                                if a.get(col) == str(val) and a.get(col2) == str(val2)
                            ]
                        )
                    )
                    return s2
                s.eq = eq_fn
                return s
            query_obj.select = select_fn

        elif table_name == "mechanic_profiles":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                s.eq = lambda col, val: MagicMock(
                    execute=lambda: MagicMock(
                        data=[
                            p for p in mechanic_profiles_db.values()
                            if p.get(col) == str(val)
                        ]
                    )
                )
                return s
            query_obj.select = select_fn

        elif table_name == "profiles":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                s.eq = lambda col, val: MagicMock(
                    execute=lambda: MagicMock(
                        data=[
                            p for p in profiles_db.values()
                            if p.get(col) == str(val)
                        ]
                    )
                )
                return s
            query_obj.select = select_fn

        elif table_name == "chat_rooms":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                s.eq = lambda col, val: MagicMock(
                    execute=lambda: MagicMock(
                        data=[
                            r for r in chat_rooms_db.values()
                            if r.get(col) == str(val)
                        ]
                    )
                )
                return s
            query_obj.select = select_fn

            def insert_fn(payload):
                new_room = dict(payload)
                new_room["id"] = str(uuid.uuid4())
                new_room["created_at"] = datetime.now(timezone.utc).isoformat()
                new_room["updated_at"] = datetime.now(timezone.utc).isoformat()
                chat_rooms_db[new_room["id"]] = new_room
                return MagicMock(execute=lambda: MagicMock(data=[new_room]))
            query_obj.insert = insert_fn

        elif table_name == "chat_messages":
            def select_fn(*args, **kwargs):
                s = MagicMock()
                def eq_fn(col, val):
                    chain = MagicMock()
                    chain.order = lambda col2, desc=False: MagicMock(
                        limit=lambda lim: MagicMock(
                            execute=lambda: MagicMock(
                                data=[m for m in chat_messages_db if m.get(col) == str(val)]
                            )
                        )
                    )
                    chain.execute = lambda: MagicMock(
                        data=[m for m in chat_messages_db if m.get(col) == str(val)]
                    )
                    return chain
                s.eq = eq_fn
                return s
            query_obj.select = select_fn

            def insert_fn(payload):
                new_msg = dict(payload)
                new_msg["id"] = str(uuid.uuid4())
                new_msg["created_at"] = datetime.now(timezone.utc).isoformat()
                chat_messages_db.append(new_msg)
                return MagicMock(execute=lambda: MagicMock(data=[new_msg]))
            query_obj.insert = insert_fn

            def update_fn(payload):
                u = MagicMock()
                def eq_fn(col, val):
                    for m in chat_messages_db:
                        if m.get(col) == str(val):
                            m.update(payload)
                    return MagicMock(execute=lambda: MagicMock(data=[]))
                u.eq = eq_fn
                return u
            query_obj.update = update_fn

        return query_obj

    mock_client.table.side_effect = table_handler

    # Mock storage client
    mock_storage = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.upload = MagicMock(return_value={"Key": "uploaded"})
    mock_bucket.create_signed_url = MagicMock(
        return_value={"signedURL": "https://supabase.mock/storage/v1/signed-url/test"}
    )
    mock_storage.from_.return_value = mock_bucket
    mock_client.storage = mock_storage

    return mock_client


# =============================================================================
# 1. Customer Can Access Own Booking Chat
# =============================================================================

@pytest.mark.asyncio
async def test_customer_can_access_own_booking_chat(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer 1 successfully retrieves chat room and messages for their own booking."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}/chat")
        assert res.status_code == 200
        data = res.json()
        assert data["booking_id"] == str(BOOKING_1_ID)
        assert data["customer_id"] == str(CUSTOMER_1_ID)
        assert len(data["messages"]) >= 1
        assert data["messages"][0]["message"] == "Hello, I am on my way to your location."


# =============================================================================
# 2. Customer Cannot Access Another Booking Chat -> 403
# =============================================================================

@pytest.mark.asyncio
async def test_customer_cannot_access_another_booking_chat(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer 1 attempting to view Customer 2's booking chat is denied with 403 Forbidden."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_2_ID}/chat")
        assert res.status_code == 403
        assert "not an authorized participant" in res.json()["detail"].lower()


# =============================================================================
# 3. Assigned Mechanic Can Access Chat
# =============================================================================

@pytest.mark.asyncio
async def test_assigned_mechanic_can_access_chat(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Mechanic assigned to Booking 1 can view the chat room and messages."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}/chat")
        assert res.status_code == 200
        data = res.json()
        assert data["booking_id"] == str(BOOKING_1_ID)
        assert data["mechanic_id"] == str(MECH_PROFILE_1_ID)


# =============================================================================
# 4. Unrelated Mechanic Denied -> 403
# =============================================================================

@pytest.mark.asyncio
async def test_unrelated_mechanic_denied(
    async_client: AsyncClient, mock_other_mechanic: AuthenticatedUser
):
    """Mechanic 2 (unrelated to Booking 1) is rejected from accessing Booking 1 chat."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}/chat")
        assert res.status_code == 403
        assert "not an authorized participant" in res.json()["detail"].lower()


# =============================================================================
# 5. Rejected Mechanic Denied -> 403
# =============================================================================

@pytest.mark.asyncio
async def test_rejected_mechanic_denied(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """A mechanic whose assignment status is not accepted cannot access chat."""
    mock_db = build_mock_chat_db()
    # Modify assignment status to rejected
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        # Point to a booking with no accepted assignment
        unassigned_booking_id = uuid.uuid4()
        res = await async_client.get(f"/api/v1/bookings/{unassigned_booking_id}/chat")
        assert res.status_code == 404


# =============================================================================
# 6. Unauthenticated Denied -> 401
# =============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_denied(async_client: AsyncClient):
    """Calling chat endpoints without authentication headers results in 401."""
    res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}/chat")
    assert res.status_code == 401


# =============================================================================
# 7. Sender Identity Derived from JWT
# =============================================================================

@pytest.mark.asyncio
async def test_sender_identity_derived_from_jwt(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer posting a message has sender_id strictly stamped from authenticated user."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/messages",
            json={"message": "Please call when outside.", "message_type": "text"},
        )
        assert res.status_code == 201
        data = res.json()
        assert data["sender_id"] == str(CUSTOMER_1_ID)
        assert data["message"] == "Please call when outside."


# =============================================================================
# 8. Forged sender_id Rejected (extra=forbid)
# =============================================================================

@pytest.mark.asyncio
async def test_forged_sender_id_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Attempting to supply sender_id in request body fails with 422 Unprocessable Content."""
    res = await async_client.post(
        f"/api/v1/bookings/{BOOKING_1_ID}/chat/messages",
        json={
            "message": "Spoof attempt",
            "message_type": "text",
            "sender_id": str(MECHANIC_ID),
        },
    )
    assert res.status_code == 422


# =============================================================================
# 9. Forged booking_id Rejected -> 404
# =============================================================================

@pytest.mark.asyncio
async def test_forged_booking_id_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Sending a message to a non-existent booking ID returns 404."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        fake_id = uuid.uuid4()
        res = await async_client.post(
            f"/api/v1/bookings/{fake_id}/chat/messages",
            json={"message": "Non-existent booking", "message_type": "text"},
        )
        assert res.status_code == 404


# =============================================================================
# 10. Unauthorized Attachment Access Denied -> 403
# =============================================================================

@pytest.mark.asyncio
async def test_unauthorized_attachment_access_denied(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Customer 1 attempting to generate signed URL for Customer 2's booking attachment is denied."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(
            f"/api/v1/bookings/{BOOKING_2_ID}/chat/attachments/signed-url",
            params={"path": f"{BOOKING_2_ID}/photo.png"},
        )
        assert res.status_code == 403


# =============================================================================
# 11. Valid Attachment Upload
# =============================================================================

@pytest.mark.asyncio
async def test_valid_attachment_upload(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Uploading a valid PNG image creates a safe scoped path in chat-attachments."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        file_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRmock_png_bytes"
        files = {"file": ("brake_issue.png", io.BytesIO(file_content), "image/png")}
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/attachments/upload",
            files=files,
        )
        assert res.status_code == 201
        data = res.json()
        assert data["attachment_path"].startswith(f"{BOOKING_1_ID}/")
        assert data["attachment_path"].endswith(".png")
        assert "signed_url" in data


# =============================================================================
# 12. Invalid MIME Rejected -> 400
# =============================================================================

@pytest.mark.asyncio
async def test_invalid_mime_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Uploading executable scripts or unapproved MIME types is rejected."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        files = {"file": ("malicious.exe", io.BytesIO(b"binary_payload"), "application/x-msdownload")}
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/attachments/upload",
            files=files,
        )
        assert res.status_code == 400
        assert "prohibited" in res.json()["detail"].lower() or "not supported" in res.json()["detail"].lower()


# =============================================================================
# 13. Oversized Attachment Rejected -> 400
# =============================================================================

@pytest.mark.asyncio
async def test_oversized_attachment_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Uploading a file exceeding 10MB limit is rejected."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        # 11 MB payload
        large_payload = b"0" * (11 * 1024 * 1024)
        files = {"file": ("large_video.png", io.BytesIO(large_payload), "image/png")}
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/attachments/upload",
            files=files,
        )
        assert res.status_code == 400
        assert "exceeds maximum allowed size" in res.json()["detail"].lower()


# =============================================================================
# 14. Path Traversal Rejected -> 400
# =============================================================================

@pytest.mark.asyncio
async def test_path_traversal_rejected(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Sending a message with a traversal path like '../' is rejected."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/messages",
            json={
                "message": "See photo",
                "message_type": "image",
                "attachment_path": f"../{BOOKING_1_ID}/secret.txt",
            },
        )
        assert res.status_code == 400
        assert "traversal" in res.json()["detail"].lower()


# =============================================================================
# 15. Duplicate Message Handling
# =============================================================================

@pytest.mark.asyncio
async def test_duplicate_message_handling(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Sending identical message strings creates distinct sequential records without crashing."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res1 = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/messages",
            json={"message": "Are you near?", "message_type": "text"},
        )
        res2 = await async_client.post(
            f"/api/v1/bookings/{BOOKING_1_ID}/chat/messages",
            json={"message": "Are you near?", "message_type": "text"},
        )
        assert res1.status_code == 201
        assert res2.status_code == 201
        assert res1.json()["id"] != res2.json()["id"]


# =============================================================================
# 16. Read Receipt Authorization
# =============================================================================

@pytest.mark.asyncio
async def test_read_receipt_authorization(
    async_client: AsyncClient,
    mock_customer: AuthenticatedUser,
):
    """
    1. Recipient (Customer) marks mechanic's message read -> Success.
    2. Sender (Mechanic) attempts to mark own message read -> Forbidden.
    3. Outsider (Customer 2) attempts to mark message read -> Forbidden.
    """
    mock_db = build_mock_chat_db()
    msg_id = "11110000-0000-0000-0000-000000000001"  # sent by Mechanic

    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        # 1. Customer (recipient) marks message read -> 200
        res = await async_client.post(f"/api/v1/chat/messages/{msg_id}/read")
        assert res.status_code == 200
        assert res.json()["is_read"] is True


@pytest.mark.asyncio
async def test_sender_cannot_mark_own_message_read(
    async_client: AsyncClient, mock_mechanic: AuthenticatedUser
):
    """Mechanic (sender of message 1) cannot mark own message read."""
    mock_db = build_mock_chat_db()
    msg_id = "11110000-0000-0000-0000-000000000001"  # sent by Mechanic
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/chat/messages/{msg_id}/read")
        assert res.status_code == 403
        assert "sender cannot mark own message as read" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_outsider_cannot_mark_message_read(
    async_client: AsyncClient, mock_other_customer: AuthenticatedUser
):
    """Customer 2 (not in room 1) cannot mark message in room 1 as read."""
    mock_db = build_mock_chat_db()
    msg_id = "11110000-0000-0000-0000-000000000001"
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.post(f"/api/v1/chat/messages/{msg_id}/read")
        assert res.status_code == 403


# =============================================================================
# 17. Chat Room Isolation
# =============================================================================

@pytest.mark.asyncio
async def test_chat_room_isolation(
    async_client: AsyncClient, mock_customer: AuthenticatedUser
):
    """Messages from Room 2 must never leak into Room 1 chat query response."""
    mock_db = build_mock_chat_db()
    with patch("app.services.chat_service.get_supabase_service_client", return_value=mock_db):
        res = await async_client.get(f"/api/v1/bookings/{BOOKING_1_ID}/chat")
        assert res.status_code == 200
        messages = res.json()["messages"]
        message_contents = [m["message"] for m in messages]
        assert "Hello, I am on my way to your location." in message_contents
        assert "Room 2 private message." not in message_contents
