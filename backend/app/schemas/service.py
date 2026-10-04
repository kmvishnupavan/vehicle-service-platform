"""
Service Catalog Pydantic Schemas.

Maps directly to database tables:
- public.service_categories
- public.services
- public.service_pricing

CRITICAL FINANCIAL RULE:
All monetary values (base_price, minimum_price) MUST use Decimal, never float.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class ServiceCategoryResponse(BaseModel):
    """Service category schema matching public.service_categories."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    icon_url: str | None = None
    display_order: int = 0
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class ServicePricingResponse(BaseModel):
    """Authoritative pricing schema matching public.service_pricing."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_id: uuid.UUID
    vehicle_type_id: uuid.UUID | None = None
    vehicle_type_name: str | None = None
    base_price: Decimal = Field(..., ge=0, description="Authoritative base service labor price")
    minimum_price: Decimal = Field(..., ge=0, description="Minimum billable price floor")
    pricing_parameters: dict[str, Any] = Field(default_factory=dict, description="Tier/vehicle specific pricing factors")
    effective_from: datetime
    effective_to: datetime | None = None
    is_active: bool = True


class ServiceResponse(BaseModel):
    """Service item summary schema matching public.services."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    category_name: str | None = None
    name: str
    description: str | None = None
    vehicle_type: str = Field(..., description="Target vehicle category: bike, car, or both")
    estimated_duration_minutes: int = 60
    is_emergency: bool = False
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    pricing: list[ServicePricingResponse] = Field(default_factory=list, description="Available pricing tiers")


class ServiceDetailResponse(ServiceResponse):
    """Detailed service item including category metadata and supported vehicle types."""
    category: ServiceCategoryResponse | None = None
    supported_vehicle_types: list[str] = Field(default_factory=list, description="List of supported vehicle types")


class ServicePriceResponse(BaseModel):
    """Authoritative price calculation response for a specific service and vehicle type."""
    model_config = ConfigDict(from_attributes=True)

    service_id: uuid.UUID
    service_name: str
    vehicle_type_id: uuid.UUID
    vehicle_type_name: str
    base_price: Decimal = Field(..., ge=0, description="Authoritative base price from service_pricing")
    minimum_price: Decimal = Field(..., ge=0, description="Minimum price floor from service_pricing")
    pricing_parameters: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime
