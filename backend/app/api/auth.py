"""
Authentication Endpoints.

Mounts under /api/v1/auth.
Supabase Auth handles password, OTP, and OAuth lifecycle.
These endpoints expose profile introspection and session validation.
"""

from fastapi import APIRouter, Depends
from app.db.dependencies import get_current_user
from app.schemas.user import AuthenticatedUser, UserProfileResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile")
async def get_my_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> UserProfileResponse:
    """
    Returns the authenticated user's database profile.
    Requires Bearer JWT in Authorization header.
    """
    if current_user.profile is None:
        raise ValueError("Authenticated profile is missing from context")
    return current_user.profile
