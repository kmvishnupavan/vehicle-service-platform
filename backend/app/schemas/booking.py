"""
Booking Pydantic Schemas.

Maps to database tables:
- public.bookings
- public.booking_items
- public.booking_status_history
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
import uuid
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class BookingStatus(str, Enum):
    """Authoritative booking lifecycle status states matching DB constraint."""
    PENDING = "pending"
    SEARCHING_MECHANIC = "searching_mechanic"
    MECHANIC_ASSIGNED = "mechanic_assigned"
    MECHANIC_EN_ROUTE = "mechanic_en_route"
    MECHANIC_ARRIVED = "mechanic_arrived"
    INSPECTION = "inspection"
    AWAITING_CUSTOMER_APPROVAL = "awaiting_customer_approval"
    SERVICE_IN_PROGRESS = "service_in_progress"
    ADDITIONAL_WORK = "additional_work"
    SERVICE_COMPLETED = "service_completed"
    PAYMENT_PENDING = "payment_pending"
    PAID = "paid"
    CANCELLED = "cancelled"
    DISPUTED = "disputed"


class PaymentStatus(str, Enum):
    """Booking payment lifecycle status states matching DB constraint."""
    UNPAID = "unpaid"
    PARTIALLY_PAID = "partially_paid"
    PAID = "paid"
    REFUNDED = "refunded"
    FAILED = "failed"


# ==============================================================================
# Request Schemas
# ==============================================================================

class BookingItemCreate(BaseModel):
    """Client input for a single service item inside a booking request."""
    model_config = ConfigDict(extra="forbid")

    service_id: uuid.UUID = Field(..., description="UUID of catalog service to book")
    quantity: int = Field(default=1, gt=0, description="Quantity of service, must be positive integer")
    notes: str | None = Field(default=None, max_length=500, description="Optional customer instructions for this item")


class BookingCreate(BaseModel):
    """
    Authoritative client request schema for booking creation.
    Strictly forbids client-injected monetary, status, or identity fields.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    vehicle_id: uuid.UUID = Field(..., description="UUID of customer-owned vehicle")
    address_id: uuid.UUID = Field(..., description="UUID of customer-owned address")
    items: list[BookingItemCreate] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("items", "booking_items"),
        description="List of requested services",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description="Optional scheduled time. Defaults to now if omitted.",
    )
    customer_notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional overall booking instructions or symptom notes",
    )


class BookingStatusUpdate(BaseModel):
    """
    Authoritative request schema for booking lifecycle state transitions.
    Strictly forbids client-injected monetary, customer/mechanic identity, or timestamp fields.
    """
    model_config = ConfigDict(extra="forbid")

    new_status: BookingStatus = Field(..., description="Target booking lifecycle status")
    reason: str | None = Field(
        default=None,
        max_length=500,
        description="Optional or required explanation for status change (e.g. cancellation or dispute reason)",
    )


# ==============================================================================
# Response Schemas
# ==============================================================================

class BookingItemResponse(BaseModel):
    """Authoritative booking line item response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    service_id: uuid.UUID
    service_name: str | None = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    notes: str | None = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def extract_joined_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Extract service name from Supabase relation join if present
            if not data.get("service_name"):
                services = data.get("services")
                if isinstance(services, dict):
                    data["service_name"] = services.get("name")
        return data


class BookingResponse(BaseModel):
    """Authoritative booking details response schema."""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    booking_number: str
    customer_id: uuid.UUID
    vehicle_id: uuid.UUID
    address_id: uuid.UUID
    scheduled_at: datetime
    requested_latitude: Decimal
    requested_longitude: Decimal
    customer_notes: str | None = None
    subtotal: Decimal
    additional_charges: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    payment_status: PaymentStatus
    booking_status: BookingStatus
    items: list[BookingItemResponse] = Field(
        default=[],
        validation_alias=AliasChoices("items", "booking_items"),
    )
    created_at: datetime
    updated_at: datetime

