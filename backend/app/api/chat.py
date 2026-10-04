"""
Chat Endpoints (Phase 8.4).

Mounts under /api/v1.
Provides secure endpoints for:
- Retrieving booking chat history and participant metadata
- Posting messages with JWT-derived sender identity
- Marking messages as read
- Attachment rules, uploads, and signed URLs
- Aggregate unread count across bookings
"""

from datetime import datetime
from typing import Any
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from app.db.dependencies import get_current_user
from app.schemas.chat import (
    ChatAttachmentRulesResponse,
    ChatAttachmentUploadResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatRoomResponse,
    MarkReadResponse,
    UnreadCountResponse,
)
from app.schemas.user import AuthenticatedUser
from app.services.chat_service import ChatService

router = APIRouter(tags=["Chat"])


# =============================================================================
# Booking Chat Room & Messages
# =============================================================================

@router.get(
    "/bookings/{booking_id}/chat",
    response_model=ChatRoomResponse,
    summary="Get booking chat room and message history",
    description="Returns authorized chat room metadata, participant details, and paginated messages.",
)
async def get_booking_chat(
    booking_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100, description="Max messages to return."),
    before: datetime | None = Query(None, description="Cursor for pagination (older than timestamp)."),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatRoomResponse:
    """Retrieve booking chat room and messages for authorized participant."""
    chat_service = ChatService()
    return await chat_service.get_chat_room(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=current_user.role,
        limit=limit,
        before=before,
    )


@router.post(
    "/bookings/{booking_id}/chat/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Send a chat message",
    description="Posts an authoritative chat message. Sender identity is derived strictly from JWT.",
)
async def send_chat_message(
    booking_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatMessageResponse:
    """Send a new message to the booking chat room."""
    chat_service = ChatService()
    return await chat_service.send_message(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=current_user.role,
        payload=payload,
    )


# =============================================================================
# Read Receipts
# =============================================================================

@router.post(
    "/chat/messages/{message_id}/read",
    response_model=MarkReadResponse,
    summary="Mark a received message as read",
    description="Marks message read. Senders cannot mark their own messages as read.",
)
async def mark_message_as_read(
    message_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MarkReadResponse:
    """Mark a message received by the user as read."""
    chat_service = ChatService()
    return await chat_service.mark_message_read(
        message_id=message_id,
        user_id=current_user.id,
        user_role=current_user.role,
    )


# =============================================================================
# Media Attachments
# =============================================================================

@router.get(
    "/bookings/{booking_id}/chat/attachments/rules",
    response_model=ChatAttachmentRulesResponse,
    summary="Get permitted attachment rules",
)
async def get_chat_attachment_rules(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatAttachmentRulesResponse:
    """Returns constraints, allowed MIME types, and maximum sizes for attachments."""
    chat_service = ChatService()
    # Verify participant access
    await chat_service.resolve_participant_and_room(booking_id, current_user.id, current_user.role)
    return chat_service.get_attachment_rules()


@router.post(
    "/bookings/{booking_id}/chat/attachments/upload",
    response_model=ChatAttachmentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload chat attachment",
    description="Uploads a media attachment to private storage after verifying participant authorization.",
)
async def upload_chat_attachment(
    booking_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ChatAttachmentUploadResponse:
    """Controlled upload of images/documents for chat."""
    chat_service = ChatService()
    file_bytes = await file.read()
    content_type = file.content_type or "application/octet-stream"
    filename = file.filename or "attachment"

    return await chat_service.upload_attachment(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=current_user.role,
        filename=filename,
        content_type=content_type,
        file_bytes=file_bytes,
    )


@router.get(
    "/bookings/{booking_id}/chat/attachments/signed-url",
    summary="Get short-lived signed URL for an attachment",
)
async def get_attachment_signed_url(
    booking_id: uuid.UUID,
    path: str = Query(..., description="Storage path within chat-attachments bucket."),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    """Generates a temporary signed URL to view or download a private attachment."""
    chat_service = ChatService()
    # Verify participant access
    await chat_service.resolve_participant_and_room(booking_id, current_user.id, current_user.role)
    chat_service._validate_attachment_path(booking_id, path)
    signed_url = await chat_service.create_attachment_signed_url(path)
    return {"signed_url": signed_url}


# =============================================================================
# Aggregated Unread Counter
# =============================================================================

@router.get(
    "/chat/unread-count",
    response_model=UnreadCountResponse,
    summary="Get total unread chat messages for current user",
)
async def get_unread_count(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UnreadCountResponse:
    """Returns total unread count across all rooms where current user is a participant."""
    chat_service = ChatService()
    count = await chat_service.get_total_unread_count(current_user.id, current_user.role)
    return UnreadCountResponse(unread_count=count)
