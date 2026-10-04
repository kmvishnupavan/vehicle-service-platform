"""
Vehicle Catalog and Customer Vehicles API Router.

Mounts under /api/v1/vehicles.
Delegates all business logic, validation, and database operations to VehicleService.
"""

import uuid
from fastapi import APIRouter, Depends, status
from app.db.dependencies import get_current_user, require_customer
from app.schemas.common import MessageResponse
from app.schemas.user import AuthenticatedUser
from app.schemas.vehicle import (
    VehicleBrandResponse,
    VehicleCreate,
    VehicleModelResponse,
    VehicleResponse,
    VehicleTypeResponse,
    VehicleUpdate,
)
from app.services.vehicle_service import VehicleService

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


# ==============================================================================
# Catalog Endpoints (Public / Authenticated)
# ==============================================================================

@router.get(
    "/makes",
    response_model=list[VehicleBrandResponse],
    summary="List supported vehicle brands / makes",
)
async def list_vehicle_makes() -> list[VehicleBrandResponse]:
    """Retrieve catalog of supported vehicle manufacturers (Honda, Maruti, Hyundai, etc.)."""
    service = VehicleService()
    return await service.list_vehicle_brands()


@router.get(
    "/models/{brand_id}",
    response_model=list[VehicleModelResponse],
    summary="List models for a specific vehicle brand",
)
async def list_brand_models(brand_id: uuid.UUID) -> list[VehicleModelResponse]:
    """Retrieve active models belonging to the specified vehicle brand UUID."""
    service = VehicleService()
    return await service.list_models_by_brand(brand_id)


@router.get(
    "/types",
    response_model=list[VehicleTypeResponse],
    summary="List supported vehicle types",
)
async def list_vehicle_types() -> list[VehicleTypeResponse]:
    """Retrieve catalog of vehicle categories (Car, Motorcycle, Scooter, etc.)."""
    service = VehicleService()
    return await service.list_vehicle_types()


# ==============================================================================
# Customer Vehicle Endpoints (Authenticated Customer Only)
# ==============================================================================

@router.get(
    "/my-vehicles",
    response_model=list[VehicleResponse],
    summary="List customer registered vehicles",
)
async def list_my_vehicles(
    current_user: AuthenticatedUser = Depends(require_customer),
) -> list[VehicleResponse]:
    """
    Retrieve all vehicles registered to the authenticated customer's account.
    Customer identity is derived strictly from the verified JWT.
    """
    service = VehicleService()
    return await service.list_customer_vehicles(current_user.id)


@router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Get vehicle details by ID",
)
async def get_vehicle(
    vehicle_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> VehicleResponse:
    """
    Retrieve details of a single vehicle owned by the authenticated customer.
    Enforces server-side ownership: returns 404 if vehicle belongs to another user.
    """
    service = VehicleService()
    return await service.get_customer_vehicle(vehicle_id, current_user.id)


@router.post(
    "",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new customer vehicle",
)
async def create_vehicle(
    payload: VehicleCreate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> VehicleResponse:
    """
    Register a new vehicle under the authenticated customer.
    Normalizes registration numbers, validates model-brand relationships,
    and enforces ownership derived solely from JWT.
    """
    service = VehicleService()
    return await service.create_customer_vehicle(current_user.id, payload)


@router.patch(
    "/{vehicle_id}",
    response_model=VehicleResponse,
    summary="Update customer vehicle details",
)
async def update_vehicle(
    vehicle_id: uuid.UUID,
    payload: VehicleUpdate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> VehicleResponse:
    """
    Partially update attributes of an existing vehicle owned by the customer.
    Ownership fields cannot be modified.
    """
    service = VehicleService()
    return await service.update_customer_vehicle(vehicle_id, current_user.id, payload)


@router.delete(
    "/{vehicle_id}",
    response_model=MessageResponse,
    summary="Delete a customer vehicle",
)
async def delete_vehicle(
    vehicle_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> MessageResponse:
    """
    Delete a vehicle owned by the authenticated customer.
    Rejects deletion with a clean error if historical bookings reference the vehicle.
    """
    service = VehicleService()
    await service.delete_customer_vehicle(vehicle_id, current_user.id)
    return MessageResponse(message="Vehicle deleted successfully.")
