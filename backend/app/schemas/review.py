"""
Review and Rating Pydantic Schemas (Phase 8.5).

Enforces:
- rating integer between 1 and 5 (strictly integers; no floats, strings, or zeros)
- optional comment up to 1000 characters with whitespace trimming and HTML sanitization
- strict extra="forbid" preventing injection of customer_id, mechanic_id, or timestamps
- privacy-safe public review listings omitting sensitive personal identifiable info
"""

from datetime import datetime
import re
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


def sanitize_text(value: str | None) -> str | None:
    """Trim whitespace, strip HTML tags, and return None if empty."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    # Strip HTML tags defensively to prevent stored XSS
    cleaned = re.sub(r"<[^>]*>", "", trimmed).strip()
    return cleaned if cleaned else None


class ReviewCreate(BaseModel):
    """Authoritative payload for submitting a customer review for a booking."""
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(..., ge=1, le=5, description="Integer rating between 1 and 5 stars")
    comment: str | None = Field(
        default=None, max_length=1000, description="Optional written review comment up to 1000 characters"
    )

    @field_validator("rating", mode="before")
    @classmethod
    def validate_rating_integer(cls, v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("Rating must be an integer between 1 and 5.")
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5.")
        return v

    @field_validator("comment", mode="before")
    @classmethod
    def sanitize_comment(cls, v: Any) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Comment must be a text string.")
        return sanitize_text(v)


class ReviewUpdate(BaseModel):
    """Payload for updating an existing customer review."""
    model_config = ConfigDict(extra="forbid")

    rating: int | None = Field(default=None, ge=1, le=5, description="Updated rating between 1 and 5 stars")
    comment: str | None = Field(
        default=None, max_length=1000, description="Updated review comment up to 1000 characters"
    )

    @field_validator("rating", mode="before")
    @classmethod
    def validate_rating_integer(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, int):
            raise ValueError("Rating must be an integer between 1 and 5.")
        if v < 1 or v > 5:
            raise ValueError("Rating must be between 1 and 5.")
        return v

    @field_validator("comment", mode="before")
    @classmethod
    def sanitize_comment(cls, v: Any) -> str | None:
        if v is None:
            return None
        if not isinstance(v, str):
            raise ValueError("Comment must be a text string.")
        return sanitize_text(v)


class ReviewResponse(BaseModel):
    """Authoritative representation of a single review."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    mechanic_id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime
    updated_at: datetime


class ReviewListItem(BaseModel):
    """
    Public, privacy-safe review summary for mechanic listings.
    Omits customer email, phone, physical address, and user profile internals.
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rating: int
    comment: str | None = None
    created_at: datetime
    customer_name: str = Field(..., description="Privacy-safe customer display name (e.g. 'Jane D.')")


class MechanicReviewsListResponse(BaseModel):
    """Paginated collection of reviews for a given mechanic."""
    items: list[ReviewListItem]
    total_count: int
    average_rating: float
    limit: int
    offset: int
