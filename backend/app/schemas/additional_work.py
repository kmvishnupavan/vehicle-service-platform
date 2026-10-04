"""
Additional Work Request Pydantic Schemas.

Maps to database table:
- public.additional_work_requests
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdditionalWorkStatus(str, Enum):
    """Authoritative additional work lifecycle states matching DB constraint."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class AdditionalWorkCreate(BaseModel):
    """
    Payload for creating an additional work request.
    Strictly forbids client-injected identity, booking_id, or mechanic_id.
    """
    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Concise title for the additional work item",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Detailed description of why additional work/parts are needed",
    )
    price: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        description="Price for the additional work item (>= 0)",
    )
    evidence_file_paths: list[str] = Field(
        default=[],
        description="Storage paths for evidence media files within service-evidence bucket",
    )

    @field_validator("title")
    @classmethod
    def validate_title_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Title must not be empty.")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Description must not be empty.")
        return stripped


class CustomerApprovalRequest(BaseModel):
    """
    Payload for customer approving an additional work request.
    DO NOT accept price from request body. Strictly extra='forbid'.
    """
    model_config = ConfigDict(extra="forbid")

    customer_response: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional customer message or authorization note",
    )


class CustomerRejectRequest(BaseModel):
    """
    Payload for customer rejecting an additional work request.
    Strictly extra='forbid'.
    """
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(
        default=None,
        max_length=1000,
        description="Reason for rejecting additional work",
    )
    customer_response: str | None = Field(
        default=None,
        max_length=1000,
        description="Alternative field for customer rejection message",
    )


class AdditionalWorkResponse(BaseModel):
    """Authoritative additional work request response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    title: str
    description: str
    price: Decimal
    evidence_file_paths: list[str] = Field(default=[])
    status: AdditionalWorkStatus
    customer_response: str | None = None
    responded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
