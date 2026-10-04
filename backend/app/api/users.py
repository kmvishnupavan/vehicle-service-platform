"""
User & Profile API Router.

Mounts under /api/v1/users.
Provides role-specific profile introspection and controlled customer profile updates.
"""

from fastapi import APIRouter, Depends
from app.db.dependencies import get_mechanic_profile, require_customer
from app.schemas.user import (
    AuthenticatedUser,
    CustomerProfileDetailedResponse,
    CustomerProfileUpdate,
    MechanicProfileResponse,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "/customer-profile",
    response_model=CustomerProfileDetailedResponse,
    summary="Get unified customer profile",
)
async def read_customer_profile(
    current_user: AuthenticatedUser = Depends(require_customer),
) -> CustomerProfileDetailedResponse:
    """Retrieve personal and emergency contact details for the authenticated customer."""
    service = UserService()
    return await service.get_customer_profile(current_user.id)


@router.patch(
    "/customer-profile",
    response_model=CustomerProfileDetailedResponse,
    summary="Update customer profile details",
)
async def update_customer_profile(
    payload: CustomerProfileUpdate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> CustomerProfileDetailedResponse:
    """
    Partially update allowed customer profile fields:
    - full_name
    - phone
    - avatar_url
    - emergency_contact_name
    - emergency_contact_phone
    
    Security: Client-side tampering with user ID, role, active status, or audit fields is impossible.
    """
    service = UserService()
    return await service.update_customer_profile(current_user.id, payload)


@router.get(
    "/mechanic-profile",
    response_model=MechanicProfileResponse,
    summary="Get mechanic-specific profile details",
)
async def read_mechanic_profile(
    profile: MechanicProfileResponse = Depends(get_mechanic_profile),
) -> MechanicProfileResponse:
    """Retrieve operational status, rating, and service radius for authenticated mechanic."""
    return profile
