"""
Vehicle and Catalog Pydantic Schemas.

Maps to database tables:
- public.vehicle_types
- public.vehicle_brands
- public.vehicle_models
- public.vehicles
"""

from datetime import datetime, date
from enum import Enum
import re
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FuelType(str, Enum):
    """Allowed fuel types matching database CHECK constraint."""
    PETROL = "petrol"
    DIESEL = "diesel"
    ELECTRIC = "electric"
    HYBRID = "hybrid"
    CNG = "cng"
    LPG = "lpg"
    OTHER = "other"


# ==============================================================================
# Catalog Schemas
# ==============================================================================

class VehicleTypeResponse(BaseModel):
    """Vehicle type category (Car, Motorcycle, Scooter, etc.)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    icon_url: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime


class VehicleBrandResponse(BaseModel):
    """Vehicle manufacturer / brand (Honda, Hyundai, Toyota, etc.)."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    logo_url: str | None = None
    is_active: bool
    created_at: datetime


class VehicleModelResponse(BaseModel):
    """Vehicle model belonging to a brand and vehicle type."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    brand_id: uuid.UUID
    vehicle_type_id: uuid.UUID
    name: str
    year_start: int | None = None
    year_end: int | None = None
    is_active: bool
    created_at: datetime


# ==============================================================================
# Customer Vehicle Schemas
# ==============================================================================

def normalize_reg_num(v: str) -> str:
    """Normalize vehicle registration numbers (e.g. 'TS 09 AB 1234' -> 'TS09AB1234')."""
    if not v or not isinstance(v, str):
        raise ValueError("Registration number cannot be empty.")
    normalized = re.sub(r"[\s\-]+", "", v).upper()
    if len(normalized) < 4 or len(normalized) > 20:
        raise ValueError("Registration number must be between 4 and 20 alphanumeric characters.")
    return normalized


def validate_mfg_year(v: int | None) -> int | None:
    """Validate vehicle manufacture year between 1970 and current_year + 2."""
    if v is None:
        return None
    max_year = date.today().year + 2
    if v < 1970 or v > max_year:
        raise ValueError(f"Manufacture year must be between 1970 and {max_year}.")
    return v


class VehicleCreate(BaseModel):
    """Payload for registering a customer vehicle."""
    vehicle_type_id: uuid.UUID = Field(..., description="Vehicle type UUID (e.g. Car, Bike)")
    brand_id: uuid.UUID = Field(..., description="Brand / Make UUID")
    model_id: uuid.UUID = Field(..., description="Model UUID")
    registration_number: str = Field(..., min_length=4, max_length=30, description="License registration number")
    manufacture_year: int | None = Field(default=None, description="Year of manufacture")
    color: str | None = Field(default=None, max_length=50, description="Vehicle exterior color")
    nickname: str | None = Field(default=None, max_length=100, description="User friendly nickname")
    fuel_type: FuelType | None = Field(default=None, description="Fuel category")
    odometer_km: int | None = Field(default=None, ge=0, description="Current odometer reading in km")
    is_primary: bool = Field(default=False, description="Set as customer primary vehicle")

    @field_validator("registration_number")
    @classmethod
    def check_reg_num(cls, v: str) -> str:
        return normalize_reg_num(v)

    @field_validator("manufacture_year")
    @classmethod
    def check_year(cls, v: int | None) -> int | None:
        return validate_mfg_year(v)


class VehicleUpdate(BaseModel):
    """Payload for updating an existing customer vehicle (partial update)."""
    vehicle_type_id: uuid.UUID | None = Field(default=None, description="Updated vehicle type UUID")
    brand_id: uuid.UUID | None = Field(default=None, description="Updated brand UUID")
    model_id: uuid.UUID | None = Field(default=None, description="Updated model UUID")
    registration_number: str | None = Field(default=None, min_length=4, max_length=30, description="Updated registration number")
    manufacture_year: int | None = Field(default=None, description="Updated manufacture year")
    color: str | None = Field(default=None, max_length=50, description="Updated vehicle exterior color")
    nickname: str | None = Field(default=None, max_length=100, description="Updated vehicle nickname")
    fuel_type: FuelType | None = Field(default=None, description="Updated fuel category")
    odometer_km: int | None = Field(default=None, ge=0, description="Updated odometer reading in km")
    is_primary: bool | None = Field(default=None, description="Set or unset primary vehicle flag")

    @field_validator("registration_number")
    @classmethod
    def check_reg_num(cls, v: str | None) -> str | None:
        if v is not None:
            return normalize_reg_num(v)
        return None

    @field_validator("manufacture_year")
    @classmethod
    def check_year(cls, v: int | None) -> int | None:
        return validate_mfg_year(v)


class VehicleResponse(BaseModel):
    """Customer vehicle details response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    vehicle_type_id: uuid.UUID
    brand_id: uuid.UUID
    model_id: uuid.UUID
    registration_number: str
    nickname: str | None = None
    manufacture_year: int | None = None
    color: str | None = None
    fuel_type: str | None = None
    odometer_km: int | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    # Convenient joined display fields if populated
    brand_name: str | None = None
    model_name: str | None = None
    vehicle_type_name: str | None = None
