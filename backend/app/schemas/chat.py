"""
Chat Schemas (Phase 8.4).

Defines Pydantic request and response schemas for in-app customer <-> mechanic chat,
media attachments, message validation, and read receipts.
"""

from datetime import datetime
from typing import Any, Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


MessageType = Literal["text", "image", "file", "system", "location"]


class ChatMessageCreate(BaseModel):
    """Client request schema to post a new chat message."""

    message: str = Field(..., max_length=2000, description="Chat message body content.")
    message_type: MessageType = Field(default="text", description="Type of chat message.")
    attachment_path: str | None = Field(default=None, description="Optional path to attachment in chat-attachments.")

    model_config = ConfigDict(extra="forbid")

    @field_validator("message")
    @classmethod
    def validate_message_content(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Message body cannot be empty or contain only whitespace.")
        return trimmed


class ChatMessageResponse(BaseModel):
    """Authoritative chat message representation returned by the backend."""

    id: uuid.UUID
    room_id: uuid.UUID
    sender_id: uuid.UUID
    message: str
    message_type: str
    attachment_path: str | None = None
    attachment_url: str | None = None
    is_read: bool = False
    created_at: datetime
    sender_role: str | None = None
    sender_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ChatRoomResponse(BaseModel):
    """Authorized chat room representation for a booking."""

    id: uuid.UUID
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    mechanic_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
    other_participant_name: str | None = None
    other_participant_role: str | None = None
    booking_number: str | None = None
    booking_status: str | None = None
    can_send_messages: bool = True
    messages: list[ChatMessageResponse] = Field(default_factory=list)
    unread_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class ChatAttachmentRulesResponse(BaseModel):
    """Storage and upload constraints for chat media attachments."""

    bucket: str = "chat-attachments"
    path_pattern: str = "{booking_id}/{filename}"
    max_file_size_bytes: int = 10 * 1024 * 1024  # 10 MB
    allowed_mime_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "text/plain",
    ]
    allowed_extensions: list[str] = [".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"]
    disallowed_extensions: list[str] = [
        ".exe",
        ".bat",
        ".cmd",
        ".ps1",
        ".js",
        ".sh",
        ".dll",
        ".zip",
        ".svg",
    ]


class ChatAttachmentUploadResponse(BaseModel):
    """Metadata returned after controlled attachment upload."""

    attachment_path: str
    signed_url: str
    filename: str
    content_type: str
    size_bytes: int


class MarkReadResponse(BaseModel):
    """Response returned after marking a message as read."""

    success: bool
    message_id: uuid.UUID
    is_read: bool


class UnreadCountResponse(BaseModel):
    """Total unread chat messages for authenticated user."""

    unread_count: int
