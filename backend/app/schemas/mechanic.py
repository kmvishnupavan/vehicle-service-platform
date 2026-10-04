"""
Mechanic and Assignment Pydantic Schemas.

Maps to database tables:
- public.mechanic_profiles
- public.mechanic_assignments
- public.mechanic_locations
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class AssignmentStatus(str, Enum):
    """Authoritative assignment lifecycle states matching DB constraint."""
    OFFERED = "offered"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class NearbyMechanicResponse(BaseModel):
    """
    Publicly safe mechanic discovery response.
    Explicitly excludes phone numbers, personal email, and private documents.
    """
    model_config = ConfigDict(from_attributes=True)

    mechanic_id: uuid.UUID = Field(..., description="Mechanic profile UUID")
    user_id: uuid.UUID = Field(..., description="User account UUID")
    full_name: str = Field(..., description="Mechanic full name")
    avatar_url: str | None = Field(default=None, description="Profile avatar URL")
    business_name: str | None = Field(default=None, description="Registered workshop or business name")
    experience_years: int = Field(default=0, ge=0, description="Years of mechanical experience")
    average_rating: Decimal = Field(default=Decimal("0.00"), ge=0, le=5, description="Average review rating")
    distance_km: Decimal = Field(..., description="Calculated geodesic/straight-line distance in km")
    service_radius_km: Decimal = Field(..., description="Configured operating service radius in km")


class AssignmentOfferCreate(BaseModel):
    """Payload to dispatch an assignment offer to a discovered mechanic."""
    model_config = ConfigDict(extra="forbid")

    mechanic_id: uuid.UUID = Field(..., description="UUID of the mechanic to offer assignment to")
    estimated_arrival_minutes: int | None = Field(
        default=None, ge=1, le=480, description="Estimated arrival time in minutes"
    )


class AssignmentRejectRequest(BaseModel):
    """Payload when a mechanic rejects an offered assignment."""
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500, description="Reason for assignment rejection")


class AssignmentResponse(BaseModel):
    """Authoritative mechanic assignment record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Assignment UUID")
    booking_id: uuid.UUID = Field(..., description="Associated booking UUID")
    mechanic_id: uuid.UUID = Field(..., description="Assigned mechanic profile UUID")
    assignment_status: AssignmentStatus = Field(..., description="Current assignment lifecycle status")
    distance_km: Decimal | None = Field(default=None, description="Geodesic distance at time of dispatch")
    estimated_arrival_minutes: int | None = Field(default=None, description="Estimated arrival time in minutes")
    offered_at: datetime = Field(..., description="Timestamp offer was dispatched")
    responded_at: datetime | None = Field(default=None, description="Timestamp mechanic responded")
    assigned_at: datetime | None = Field(default=None, description="Timestamp assignment was confirmed")
    rejected_reason: str | None = Field(default=None, description="Recorded rejection reason if rejected")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


# ==============================================================================
# Realtime Location Schemas
# ==============================================================================

class MechanicLocationUpdate(BaseModel):
    """
    Payload for mechanic GPS ping.
    Strictly forbids client injection of mechanic_id, user_id, or customer_id.
    """
    model_config = ConfigDict(extra="forbid")

    latitude: Decimal = Field(
        ...,
        ge=Decimal("-90.0"),
        le=Decimal("90.0"),
        description="Current latitude (-90 to 90)",
    )
    longitude: Decimal = Field(
        ...,
        ge=Decimal("-180.0"),
        le=Decimal("180.0"),
        description="Current longitude (-180 to 180)",
    )
    accuracy_meters: Decimal | None = Field(
        default=None,
        ge=Decimal("0.0"),
        description="Optional GPS horizontal accuracy in meters (>= 0)",
    )
    sequence: int | None = Field(
        default=None,
        ge=0,
        description="Optional monotonic client packet sequence number",
    )


class MechanicLocationResponse(BaseModel):
    """
    Authoritative latest location for assigned mechanic on an active booking.
    Contains strictly safe fields without leaking personal contact details.
    """
    model_config = ConfigDict(from_attributes=True)

    mechanic_id: uuid.UUID = Field(..., description="Mechanic profile UUID")
    latitude: Decimal = Field(..., description="Latest latitude")
    longitude: Decimal = Field(..., description="Latest longitude")
    accuracy_meters: Decimal | None = Field(default=None, description="GPS accuracy in meters")
    recorded_at: datetime = Field(..., description="Timestamp of recorded location")

