"""
User and Profile Pydantic Schemas.

Maps to database tables:
- public.profiles
- public.customer_profiles
- public.mechanic_profiles
"""

from datetime import datetime
from enum import Enum
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    """Platform user roles corresponding to database CHECK constraint."""
    CUSTOMER = "customer"
    MECHANIC = "mechanic"
    ADMIN = "admin"
    SUPPORT = "support"


class MechanicVerificationStatus(str, Enum):
    """Mechanic verification lifecycle status."""
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    VERIFIED = "verified"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class UserProfileBase(BaseModel):
    """Base user profile attributes."""
    full_name: str = Field(..., min_length=1, max_length=150, description="User full display name")
    phone: str | None = Field(default=None, description="Contact phone number")
    email: str | None = Field(default=None, description="Contact email address")
    avatar_url: str | None = Field(default=None, description="Profile avatar picture URL")


class UserProfileResponse(UserProfileBase):
    """User profile response including system-managed fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Unique profile and auth user UUID")
    role: UserRole = Field(..., description="Assigned platform role")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation timestamp")
    updated_at: datetime = Field(..., description="Last profile update timestamp")


class CustomerProfileResponse(BaseModel):
    """Customer-specific profile attributes."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Customer profile ID")
    user_id: uuid.UUID = Field(..., description="Associated user ID")
    emergency_contact_name: str | None = Field(default=None, description="Emergency contact person")
    emergency_contact_phone: str | None = Field(default=None, description="Emergency contact phone number")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class CustomerProfileDetailedResponse(BaseModel):
    """Unified customer profile combining base profile and customer-specific details."""
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID = Field(..., description="User auth and profile UUID")
    full_name: str = Field(..., description="Full display name")
    phone: str | None = Field(default=None, description="Customer phone number")
    email: str | None = Field(default=None, description="Customer email address")
    avatar_url: str | None = Field(default=None, description="Customer avatar URL")
    role: UserRole = Field(default=UserRole.CUSTOMER, description="Platform role")
    is_active: bool = Field(default=True, description="Account active status")
    emergency_contact_name: str | None = Field(default=None, description="Emergency contact person")
    emergency_contact_phone: str | None = Field(default=None, description="Emergency contact phone number")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class CustomerProfileUpdate(BaseModel):
    """
    Allowed customer profile edits.
    Strictly forbids client modification of user_id, role, is_active, email, or audit fields.
    """
    full_name: str | None = Field(default=None, min_length=1, max_length=150, description="Updated full name")
    phone: str | None = Field(default=None, min_length=7, max_length=20, description="Updated contact phone")
    avatar_url: str | None = Field(default=None, max_length=500, description="Updated avatar URL")
    emergency_contact_name: str | None = Field(default=None, max_length=150, description="Updated emergency contact name")
    emergency_contact_phone: str | None = Field(default=None, min_length=7, max_length=20, description="Updated emergency contact phone")


class MechanicProfileResponse(BaseModel):
    """Mechanic-specific profile attributes."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Mechanic profile ID")
    user_id: uuid.UUID = Field(..., description="Associated user ID")
    business_name: str | None = Field(default=None, description="Registered business / workshop name")
    experience_years: int = Field(default=0, ge=0, description="Years of professional mechanical experience")
    bio: str | None = Field(default=None, description="Mechanic professional biography")
    verification_status: MechanicVerificationStatus = Field(..., description="Profile verification status")
    is_available: bool = Field(..., description="Active availability status for dispatch")
    service_radius_km: float = Field(..., description="Service coverage radius in kilometers")
    average_rating: float = Field(default=0.0, ge=0.0, le=5.0, description="Average customer review rating")
    total_completed_jobs: int = Field(default=0, ge=0, description="Total completed service jobs")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Update timestamp")


class AuthenticatedUser(BaseModel):
    """
    Session container for the currently authenticated user in request context.
    Encapsulates identity, verified role, database profile, and JWT claims.
    """
    id: uuid.UUID = Field(..., description="Supabase auth UUID")
    email: str | None = Field(default=None, description="Email extracted from claims or profile")
    role: UserRole = Field(..., description="Authoritative database role (never trusted from frontend)")
    profile: UserProfileResponse | None = Field(default=None, description="Detailed profile record")
    jwt_claims: dict[str, Any] = Field(default_factory=dict, description="Raw validated token claims")
