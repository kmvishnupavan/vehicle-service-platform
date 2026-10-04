"""
Chat Service Layer (Phase 8.4).

Manages:
- Authorization and participant verification (Customer, Assigned Mechanic, Admin)
- Room creation and retrieval linked to bookings
- Message sending, validation, and deterministic notification integration
- Read receipts enforcement
- Controlled attachment uploads and signed URL generation with path traversal guards
"""

from datetime import datetime, timezone
import os
from typing import Any, Tuple
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.chat import (
    ChatAttachmentRulesResponse,
    ChatAttachmentUploadResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatRoomResponse,
    MarkReadResponse,
)
from app.services.notification_service import NotificationService

logger = get_logger("services.chat")

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}

DISALLOWED_EXTENSIONS = {
    ".exe",
    ".bat",
    ".cmd",
    ".ps1",
    ".js",
    ".sh",
    ".dll",
    ".zip",
    ".svg",
}

MAX_ATTACHMENT_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class ChatService:
    """Business logic for secure, scoped customer <-> mechanic chat."""

    def __init__(self):
        self.client = get_supabase_service_client()
        self.notification_service = NotificationService()

    # =========================================================================
    # Participant & Room Resolution
    # =========================================================================

    async def resolve_participant_and_room(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> Tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]]:
        """
        Verifies that current_user is an authorized participant in the booking's chat:
        - Customer who owns the booking
        - Mechanic with accepted assignment on the booking
        - Admin or platform support

        Returns: (booking, room, participant_role, other_participant_info)
        """
        # 1. Fetch booking
        booking_res = (
            self.client.table("bookings")
            .select("id, customer_id, booking_number, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not booking_res.data or len(booking_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Booking {booking_id} not found.",
            )
        booking = booking_res.data[0]

        # 2. Check accepted assignment
        assignment_res = (
            self.client.table("mechanic_assignments")
            .select("id, mechanic_id, assignment_status")
            .eq("booking_id", str(booking_id))
            .eq("assignment_status", "accepted")
            .execute()
        )
        has_accepted_assignment = bool(assignment_res.data and len(assignment_res.data) > 0)
        accepted_mechanic_profile_id = (
            assignment_res.data[0]["mechanic_id"] if has_accepted_assignment else None
        )

        # 3. Determine if current user is participant
        is_customer = booking["customer_id"] == str(user_id)
        is_admin_or_support = user_role in ("admin", "support")
        is_assigned_mechanic = False
        user_mechanic_profile_id = None

        if not is_customer and not is_admin_or_support:
            # Check if user is a mechanic whose profile matches the accepted assignment
            mech_profile_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if mech_profile_res.data and len(mech_profile_res.data) > 0:
                user_mechanic_profile_id = mech_profile_res.data[0]["id"]
                if (
                    has_accepted_assignment
                    and accepted_mechanic_profile_id == user_mechanic_profile_id
                ):
                    is_assigned_mechanic = True

        if not (is_customer or is_assigned_mechanic or is_admin_or_support):
            logger.warning(
                "chat_access_denied_unauthorized_user",
                booking_id=str(booking_id),
                user_id=str(user_id),
                user_role=user_role,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not an authorized participant in this booking's chat.",
            )

        # 4. Fetch or ensure chat room
        room_res = (
            self.client.table("chat_rooms")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )

        if not room_res.data or len(room_res.data) == 0:
            if not has_accepted_assignment:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Chat is unavailable until a mechanic accepts the service assignment.",
                )

            # Create chat room on-demand if trigger hadn't fired yet
            create_room_res = (
                self.client.table("chat_rooms")
                .insert({
                    "booking_id": str(booking_id),
                    "customer_id": booking["customer_id"],
                    "mechanic_id": accepted_mechanic_profile_id,
                    "is_active": True,
                })
                .execute()
            )
            room = create_room_res.data[0]
        else:
            room = room_res.data[0]

        # 5. Resolve other participant details for header display
        participant_role = "customer" if is_customer else ("mechanic" if is_assigned_mechanic else "admin")
        other_participant_info: dict[str, Any] = {}

        if is_customer:
            # Look up mechanic business info
            mech_info_res = (
                self.client.table("mechanic_profiles")
                .select("id, user_id, business_name")
                .eq("id", room["mechanic_id"])
                .execute()
            )
            if mech_info_res.data and len(mech_info_res.data) > 0:
                mech_rec = mech_info_res.data[0]
                other_participant_info["name"] = mech_rec.get("business_name") or "Service Specialist"
                other_participant_info["role"] = "mechanic"
                other_participant_info["user_id"] = mech_rec.get("user_id")
        else:
            # Look up customer name
            cust_info_res = (
                self.client.table("profiles")
                .select("id, full_name")
                .eq("id", room["customer_id"])
                .execute()
            )
            if cust_info_res.data and len(cust_info_res.data) > 0:
                cust_rec = cust_info_res.data[0]
                other_participant_info["name"] = cust_rec.get("full_name") or "Vehicle Owner"
                other_participant_info["role"] = "customer"
                other_participant_info["user_id"] = cust_rec.get("id")

        return booking, room, participant_role, other_participant_info

    # =========================================================================
    # Room & Message Querying
    # =========================================================================

    async def get_chat_room(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        limit: int = 50,
        before: datetime | None = None,
    ) -> ChatRoomResponse:
        """Retrieves authorized chat room, recent message history, and unread counts."""
        booking, room, participant_role, other_info = await self.resolve_participant_and_room(
            booking_id, user_id, user_role
        )

        # Query messages for room
        query = (
            self.client.table("chat_messages")
            .select("*")
            .eq("room_id", room["id"])
            .order("created_at", desc=True)
            .limit(min(limit, 100))
        )
        if before:
            query = query.lt("created_at", before.isoformat())

        msg_res = query.execute()
        raw_messages = msg_res.data or []

        # Chronological ascending sort
        sorted_messages = sorted(raw_messages, key=lambda m: m["created_at"])

        # Format message objects and generate signed URLs for attachments
        formatted_messages: list[ChatMessageResponse] = []
        unread_count = 0

        for m in sorted_messages:
            is_sender = m["sender_id"] == str(user_id)
            if not is_sender and not m.get("is_read", False):
                unread_count += 1

            attachment_url = None
            if m.get("attachment_path"):
                attachment_url = await self.create_attachment_signed_url(m["attachment_path"])

            formatted_messages.append(
                ChatMessageResponse(
                    id=uuid.UUID(m["id"]),
                    room_id=uuid.UUID(m["room_id"]),
                    sender_id=uuid.UUID(m["sender_id"]),
                    message=m["message"],
                    message_type=m["message_type"],
                    attachment_path=m.get("attachment_path"),
                    attachment_url=attachment_url,
                    is_read=m.get("is_read", False),
                    created_at=datetime.fromisoformat(m["created_at"]),
                    sender_role="me" if is_sender else ("mechanic" if participant_role == "customer" else "customer"),
                )
            )

        # Determine if chat is read-only
        can_send = booking.get("booking_status") not in ("cancelled", "disputed")

        return ChatRoomResponse(
            id=uuid.UUID(room["id"]),
            booking_id=uuid.UUID(room["booking_id"]),
            customer_id=uuid.UUID(room["customer_id"]),
            mechanic_id=uuid.UUID(room["mechanic_id"]),
            is_active=room["is_active"] and can_send,
            created_at=datetime.fromisoformat(room["created_at"]),
            updated_at=datetime.fromisoformat(room["updated_at"]),
            other_participant_name=other_info.get("name"),
            other_participant_role=other_info.get("role"),
            booking_number=booking.get("booking_number"),
            booking_status=booking.get("booking_status"),
            can_send_messages=can_send,
            messages=formatted_messages,
            unread_count=unread_count,
        )

    # =========================================================================
    # Message Dispatch
    # =========================================================================

    async def send_message(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        payload: ChatMessageCreate,
    ) -> ChatMessageResponse:
        """Sends an authoritative chat message and dispatches recipient notifications."""
        booking, room, participant_role, other_info = await self.resolve_participant_and_room(
            booking_id, user_id, user_role
        )

        # 1. Enforce lifecycle rule: cancelled / disputed bookings are read-only
        if booking.get("booking_status") in ("cancelled", "disputed"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Messaging is disabled because booking is {booking.get('booking_status')}.",
            )

        # 2. Path validation if attachment present
        if payload.attachment_path:
            self._validate_attachment_path(booking_id, payload.attachment_path)

        # 3. Insert message into chat_messages
        msg_payload = {
            "room_id": room["id"],
            "sender_id": str(user_id),
            "message": payload.message,
            "message_type": payload.message_type,
            "attachment_path": payload.attachment_path,
            "is_read": False,
        }

        insert_res = self.client.table("chat_messages").insert(msg_payload).execute()
        if not insert_res.data or len(insert_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record chat message.",
            )
        msg_rec = insert_res.data[0]

        # 4. Generate signed URL if attachment exists
        attachment_url = None
        if msg_rec.get("attachment_path"):
            attachment_url = await self.create_attachment_signed_url(msg_rec["attachment_path"])

        # 5. Dispatch notification to recipient (asynchronous / non-blocking side effect)
        recipient_user_id = other_info.get("user_id")
        if recipient_user_id:
            msg_snippet = (
                payload.message[:80] + ("..." if len(payload.message) > 80 else "")
                if payload.message_type == "text"
                else f"Sent an attachment: {payload.message_type}"
            )
            b_num = booking.get("booking_number", "")
            await self.notification_service.send_notification(
                user_id=uuid.UUID(str(recipient_user_id)),
                title=f"New Message • Booking #{b_num}" if b_num else "New Chat Message",
                message=msg_snippet,
                notification_type="chat",
                data={
                    "booking_id": str(booking_id),
                    "room_id": room["id"],
                    "message_id": msg_rec["id"],
                },
                event_id=f"chat_msg_{msg_rec['id']}",
            )

        return ChatMessageResponse(
            id=uuid.UUID(msg_rec["id"]),
            room_id=uuid.UUID(msg_rec["room_id"]),
            sender_id=uuid.UUID(msg_rec["sender_id"]),
            message=msg_rec["message"],
            message_type=msg_rec["message_type"],
            attachment_path=msg_rec.get("attachment_path"),
            attachment_url=attachment_url,
            is_read=False,
            created_at=datetime.fromisoformat(msg_rec["created_at"]),
            sender_role="me",
        )

    # =========================================================================
    # Read Receipts
    # =========================================================================

    async def mark_message_read(
        self,
        message_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> MarkReadResponse:
        """
        Marks a received chat message as read.
        Enforces:
        - Sender cannot mark their own message as read.
        - User must be a participant in the message's chat room.
        """
        # Fetch message
        msg_res = (
            self.client.table("chat_messages")
            .select("id, room_id, sender_id, is_read")
            .eq("id", str(message_id))
            .execute()
        )
        if not msg_res.data or len(msg_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message {message_id} not found.",
            )
        msg = msg_res.data[0]

        # Prevent sender marking own message
        if msg["sender_id"] == str(user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sender cannot mark own message as read.",
            )

        # Check room participant
        room_res = (
            self.client.table("chat_rooms")
            .select("id, customer_id, mechanic_id")
            .eq("id", msg["room_id"])
            .execute()
        )
        if not room_res.data or len(room_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat room not found.",
            )
        room = room_res.data[0]

        is_participant = (
            room["customer_id"] == str(user_id)
            or user_role in ("admin", "support")
        )
        if not is_participant:
            mech_profile_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if mech_profile_res.data and mech_profile_res.data[0]["id"] == room["mechanic_id"]:
                is_participant = True

        if not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this message's chat room.",
            )

        # Update is_read
        self.client.table("chat_messages").update({"is_read": True}).eq("id", str(message_id)).execute()

        return MarkReadResponse(
            success=True,
            message_id=message_id,
            is_read=True,
        )

    # =========================================================================
    # Media Attachments & Storage
    # =========================================================================

    def get_attachment_rules(self) -> ChatAttachmentRulesResponse:
        """Returns storage constraints and allowed MIME specifications."""
        return ChatAttachmentRulesResponse()

    async def upload_attachment(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> ChatAttachmentUploadResponse:
        """
        Validates and uploads media to the participant-scoped chat-attachments bucket.
        Guarantees path isolation: {booking_id}/{uuid}.{ext}
        """
        # 1. Verify participant authorization
        await self.resolve_participant_and_room(booking_id, user_id, user_role)

        # 2. Check file size
        file_size = len(file_bytes)
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file cannot be empty.",
            )
        if file_size > MAX_ATTACHMENT_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)} MB.",
            )

        # 3. Check MIME type and extension
        clean_ext = os.path.splitext(filename)[1].lower()
        if clean_ext in DISALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Files with extension '{clean_ext}' are prohibited for security.",
            )

        if content_type not in ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"MIME type '{content_type}' is not supported. Permitted types: {list(ALLOWED_MIME_TYPES.keys())}.",
            )

        # 4. Generate safe deterministic path: {booking_id}/{uuid}{ext}
        expected_ext = ALLOWED_MIME_TYPES[content_type]
        safe_path = f"{booking_id}/{uuid.uuid4()}{expected_ext}"

        # 5. Upload to Supabase Storage
        try:
            self.client.storage.from_("chat-attachments").upload(
                path=safe_path,
                file=file_bytes,
                file_options={"content-type": content_type},
            )
        except Exception as exc:
            logger.error(
                "attachment_storage_upload_error",
                booking_id=str(booking_id),
                path=safe_path,
                error=str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to store attachment in private storage bucket.",
            )

        # 6. Generate signed URL
        signed_url = await self.create_attachment_signed_url(safe_path)

        return ChatAttachmentUploadResponse(
            attachment_path=safe_path,
            signed_url=signed_url,
            filename=filename,
            content_type=content_type,
            size_bytes=file_size,
        )

    async def create_attachment_signed_url(self, path: str, expires_in: int = 3600) -> str:
        """Generates a short-lived signed URL for reading private chat attachments."""
        try:
            res = self.client.storage.from_("chat-attachments").create_signed_url(path, expires_in)
            if isinstance(res, dict) and "signedURL" in res:
                return res["signedURL"]
            elif isinstance(res, str):
                return res
            elif isinstance(res, dict) and "signedUrl" in res:
                return res["signedUrl"]
            return str(res)
        except Exception as exc:
            logger.warning("failed_to_sign_attachment_url", path=path, error=str(exc))
            return ""

    def _validate_attachment_path(self, booking_id: uuid.UUID, path: str) -> None:
        """Validates that attachment path adheres strictly to {booking_id}/ prefix with no traversal."""
        if ".." in path or "\\" in path or path.startswith("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid attachment path: path traversal is strictly prohibited.",
            )
        expected_prefix = f"{booking_id}/"
        if not path.startswith(expected_prefix):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Attachment path must begin with booking directory: '{expected_prefix}'.",
            )

    # =========================================================================
    # Aggregated Unread Count
    # =========================================================================

    async def get_total_unread_count(self, user_id: uuid.UUID, user_role: str) -> int:
        """Returns total unread chat messages for current user across all active bookings."""
        # Find all rooms user participates in
        if user_role == "customer":
            rooms_res = self.client.table("chat_rooms").select("id").eq("customer_id", str(user_id)).execute()
        elif user_role == "mechanic":
            mech_res = self.client.table("mechanic_profiles").select("id").eq("user_id", str(user_id)).execute()
            if not mech_res.data:
                return 0
            mech_profile_id = mech_res.data[0]["id"]
            rooms_res = self.client.table("chat_rooms").select("id").eq("mechanic_id", mech_profile_id).execute()
        else:
            return 0

        room_ids = [r["id"] for r in (rooms_res.data or [])]
        if not room_ids:
            return 0

        # Count unread
        unread_res = (
            self.client.table("chat_messages")
            .select("id")
            .in_("room_id", room_ids)
            .neq("sender_id", str(user_id))
            .eq("is_read", False)
            .execute()
        )
        return len(unread_res.data or [])
