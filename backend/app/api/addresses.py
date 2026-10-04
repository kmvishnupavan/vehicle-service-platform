"""
Addresses API Router.

Mounts under /api/v1/addresses.
Delegates address persistence, ownership verification, and default address logic to AddressService.
"""

import uuid
from fastapi import APIRouter, Depends, status
from app.db.dependencies import require_customer
from app.schemas.address import AddressCreate, AddressResponse, AddressUpdate
from app.schemas.common import MessageResponse
from app.schemas.user import AuthenticatedUser
from app.services.address_service import AddressService

router = APIRouter(prefix="/addresses", tags=["Addresses"])


@router.get(
    "",
    response_model=list[AddressResponse],
    summary="List customer saved addresses",
)
async def list_addresses(
    current_user: AuthenticatedUser = Depends(require_customer),
) -> list[AddressResponse]:
    """
    Retrieve all addresses saved by the authenticated customer.
    The customer default address is listed first.
    """
    service = AddressService()
    return await service.list_customer_addresses(current_user.id)


@router.get(
    "/{address_id}",
    response_model=AddressResponse,
    summary="Get customer address by ID",
)
async def get_address(
    address_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> AddressResponse:
    """
    Retrieve details of a single address owned by the authenticated customer.
    Enforces server-side ownership: returns 404 if address belongs to another customer.
    """
    service = AddressService()
    return await service.get_customer_address(address_id, current_user.id)


@router.post(
    "",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save a new customer address",
)
async def create_address(
    payload: AddressCreate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> AddressResponse:
    """
    Save a new service address under the authenticated customer.
    If marked as default, unsets default status on previously saved addresses.
    """
    service = AddressService()
    return await service.create_customer_address(current_user.id, payload)


@router.patch(
    "/{address_id}",
    response_model=AddressResponse,
    summary="Update customer address details",
)
async def update_address(
    address_id: uuid.UUID,
    payload: AddressUpdate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> AddressResponse:
    """
    Partially update an existing address owned by the customer.
    """
    service = AddressService()
    return await service.update_customer_address(address_id, current_user.id, payload)


@router.delete(
    "/{address_id}",
    response_model=MessageResponse,
    summary="Delete a customer address",
)
async def delete_address(
    address_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> MessageResponse:
    """
    Delete an address owned by the authenticated customer.
    Rejects deletion with a clean error if historical bookings reference the address.
    """
    service = AddressService()
    await service.delete_customer_address(address_id, current_user.id)
    return MessageResponse(message="Address deleted successfully.")
