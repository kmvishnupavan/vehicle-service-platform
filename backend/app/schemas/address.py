"""
Address Pydantic Schemas.

Maps to database table:
- public.addresses
"""

from datetime import datetime
import uuid
from pydantic import BaseModel, ConfigDict, Field


class AddressBase(BaseModel):
    """Common address fields."""
    label: str = Field(default="Home", min_length=1, max_length=50, description="Address label (e.g. Home, Office, Other)")
    address_line: str = Field(..., min_length=1, max_length=255, description="Street address / flat / house details")
    area: str = Field(..., min_length=1, max_length=100, description="Locality / neighborhood / sector")
    city: str = Field(..., min_length=1, max_length=100, description="City / municipality")
    state: str = Field(..., min_length=1, max_length=100, description="State / province")
    postal_code: str = Field(..., min_length=3, max_length=20, description="Postal / ZIP code")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="GPS latitude coordinate")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="GPS longitude coordinate")
    landmark: str | None = Field(default=None, max_length=150, description="Nearby landmark for mechanic navigation")
    is_default: bool = Field(default=False, description="Flag setting this address as customer's default")


class AddressCreate(AddressBase):
    """Payload for creating a new customer address."""
    pass


class AddressUpdate(BaseModel):
    """Payload for updating an existing customer address (partial update)."""
    label: str | None = Field(default=None, min_length=1, max_length=50)
    address_line: str | None = Field(default=None, min_length=1, max_length=255)
    area: str | None = Field(default=None, min_length=1, max_length=100)
    city: str | None = Field(default=None, min_length=1, max_length=100)
    state: str | None = Field(default=None, min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, min_length=3, max_length=20)
    latitude: float | None = Field(default=None, ge=-90.0, le=90.0)
    longitude: float | None = Field(default=None, ge=-180.0, le=180.0)
    landmark: str | None = Field(default=None, max_length=150)
    is_default: bool | None = Field(default=None)


class AddressResponse(AddressBase):
    """Address details response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
