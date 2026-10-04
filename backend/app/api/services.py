"""
Services Catalog and Authoritative Pricing API Router.

Mounts under /api/v1/services.
Provides public access to service categories, catalog services, and authoritative pricing.
Delegates all business logic and catalog filtering to ServiceCatalogService.
"""

import uuid
from fastapi import APIRouter, Query, status
from app.schemas.service import (
    ServiceCategoryResponse,
    ServiceDetailResponse,
    ServicePriceResponse,
    ServiceResponse,
)
from app.services.service_catalog_service import ServiceCatalogService

router = APIRouter(prefix="/services", tags=["Services"])


@router.get(
    "/categories",
    response_model=list[ServiceCategoryResponse],
    summary="List active service categories",
)
async def list_categories(
    active_only: bool = Query(default=True, description="Return active categories only"),
) -> list[ServiceCategoryResponse]:
    """
    Retrieve active service categories (e.g. Periodic Maintenance, Inspection, Tyres, Brakes).
    Ordered by display order.
    """
    service = ServiceCatalogService()
    return await service.list_categories(active_only=active_only)


@router.get(
    "/items",
    response_model=list[ServiceResponse],
    summary="List catalog services with optional filtering",
)
async def list_services(
    category_id: uuid.UUID | None = Query(default=None, description="Filter by service category UUID"),
    vehicle_type_id: uuid.UUID | None = Query(default=None, description="Filter by vehicle type UUID"),
    active: bool = Query(default=True, description="Filter active services only"),
) -> list[ServiceResponse]:
    """
    Retrieve catalog of available services with configured labor pricing.
    Supports filtering by category and vehicle type compatibility.
    """
    service = ServiceCatalogService()
    return await service.list_services(
        category_id=category_id,
        vehicle_type_id=vehicle_type_id,
        active_only=active,
    )


@router.get(
    "/{service_id}",
    response_model=ServiceDetailResponse,
    summary="Get service details and available pricing tiers",
)
async def get_service_details(
    service_id: uuid.UUID,
    active_only: bool = Query(default=True, description="Filter active service only"),
) -> ServiceDetailResponse:
    """
    Retrieve full details of a specific service including category and pricing options.
    """
    service = ServiceCatalogService()
    return await service.get_service_by_id(service_id=service_id, active_only=active_only)


@router.get(
    "/{service_id}/price",
    response_model=ServicePriceResponse,
    summary="Get authoritative labor/service price for vehicle type",
)
async def get_service_pricing(
    service_id: uuid.UUID,
    vehicle_type_id: uuid.UUID = Query(..., description="Target vehicle type UUID"),
) -> ServicePriceResponse:
    """
    Retrieve authoritative base and minimum labor price from public.service_pricing.
    Validates service active state, vehicle type existence, and compatibility.
    
    SECURITY RULE:
    Prices calculated by the frontend are strictly untrusted; this endpoint provides
    the single source of truth for service checkout and booking estimation.
    """
    service = ServiceCatalogService()
    return await service.get_service_price(
        service_id=service_id,
        vehicle_type_id=vehicle_type_id,
    )
