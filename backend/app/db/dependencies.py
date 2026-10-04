"""
FastAPI Authentication and Role-Based Access Control (RBAC) Dependencies.

Extracts and validates Supabase JWT bearer tokens, resolves database profiles,
and enforces authoritative server-side role validation without trusting client headers.
"""

from typing import Callable, Sequence
import uuid
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.core.logging import get_logger
from app.core.security import verify_supabase_jwt
from app.db.supabase import get_supabase_service_client
from app.schemas.user import (
    AuthenticatedUser,
    CustomerProfileResponse,
    MechanicProfileResponse,
    UserProfileResponse,
    UserRole,
)

logger = get_logger("db.dependencies")

# Bearer security scheme (auto_error=False to allow clean custom 401 response handling)
oauth2_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(oauth2_bearer_scheme),
) -> AuthenticatedUser:
    """
    Authenticate the incoming request by extracting and validating the Bearer JWT.
    Resolves the authoritative user profile from the database public.profiles table.
    
    Raises:
        HTTPException(401): If token is missing, invalid, expired, or user not found.
        HTTPException(403): If the user profile is marked inactive.
    """
    if not credentials or not credentials.credentials:
        logger.debug("auth_failed_missing_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate JWT claims and extract subject UUID
    payload = verify_supabase_jwt(credentials.credentials)
    user_id_str = payload.get("sub")
    user_uuid = uuid.UUID(str(user_id_str))

    # Bind user_id to request state for structured request logging
    request.state.user_id = str(user_uuid)

    # Fetch authoritative profile from Supabase using privileged backend service client
    # This prevents tampering and guarantees role consistency with RLS and schema rules
    service_client = get_supabase_service_client()
    try:
        response = (
            service_client.table("profiles")
            .select("*")
            .eq("id", str(user_uuid))
            .execute()
        )
    except Exception as exc:
        logger.error("profile_lookup_database_error", user_id=str(user_uuid), error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to verify user account due to internal database error.",
        )

    if not response.data or len(response.data) == 0:
        logger.warning("auth_failed_user_profile_not_found", user_id=str(user_uuid))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User identity verified in auth, but no active platform profile exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    profile_row = response.data[0]
    profile = UserProfileResponse.model_validate(profile_row)

    if not profile.is_active:
        logger.warning("auth_failed_user_deactivated", user_id=str(user_uuid))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is suspended or deactivated. Please contact platform support.",
        )

    email = payload.get("email") or profile.email

    return AuthenticatedUser(
        id=user_uuid,
        email=email,
        role=profile.role,
        profile=profile,
        jwt_claims=payload,
    )


def require_roles(*allowed_roles: UserRole | str) -> Callable:
    """
    Factory creating a dependency that enforces the user possesses one of the allowed roles.
    Never relies on client-supplied headers or body parameters.
    """
    normalized_roles = {
        role.value if isinstance(role, UserRole) else str(role)
        for role in allowed_roles
    }

    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        user_role_str = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        if user_role_str not in normalized_roles:
            logger.warning(
                "rbac_permission_denied",
                user_id=str(user.id),
                user_role=user_role_str,
                allowed_roles=list(normalized_roles),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires one of the following roles: {list(normalized_roles)}",
            )
        return user

    return role_checker


# Preconfigured Role Dependencies
require_customer = require_roles(UserRole.CUSTOMER)
require_mechanic = require_roles(UserRole.MECHANIC)
require_admin = require_roles(UserRole.ADMIN)
require_support = require_roles(UserRole.ADMIN, UserRole.SUPPORT)
require_admin_or_support = require_roles(UserRole.ADMIN, UserRole.SUPPORT)


async def get_customer_profile(
    user: AuthenticatedUser = Depends(require_customer),
) -> CustomerProfileResponse:
    """Retrieve detailed customer profile for verified customer user."""
    service_client = get_supabase_service_client()
    response = (
        service_client.table("customer_profiles")
        .select("*")
        .eq("user_id", str(user.id))
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer profile details not found.",
        )
    return CustomerProfileResponse.model_validate(response.data[0])


async def get_mechanic_profile(
    user: AuthenticatedUser = Depends(require_mechanic),
) -> MechanicProfileResponse:
    """Retrieve detailed mechanic profile for verified mechanic user."""
    service_client = get_supabase_service_client()
    response = (
        service_client.table("mechanic_profiles")
        .select("*")
        .eq("user_id", str(user.id))
        .execute()
    )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanic profile details not found.",
        )
    return MechanicProfileResponse.model_validate(response.data[0])
