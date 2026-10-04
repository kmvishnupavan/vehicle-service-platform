"""
User and Profile Service Layer.

Handles customer profile retrieval and updates.
Strictly safeguards immutable and privileged fields (role, is_active, user_id).
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.user import (
    CustomerProfileDetailedResponse,
    CustomerProfileUpdate,
    UserRole,
)

logger = get_logger("services.user")


class UserService:
    """Business operations for user profiles and customer profile attributes."""

    def __init__(self):
        self.service_client = get_supabase_service_client()

    async def get_customer_profile(self, user_id: uuid.UUID) -> CustomerProfileDetailedResponse:
        """Fetch customer profile combining profiles and customer_profiles records."""
        # 1. Base profile
        profile_res = (
            self.service_client.table("profiles")
            .select("*")
            .eq("id", str(user_id))
            .execute()
        )
        if not profile_res.data or len(profile_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found.",
            )
        profile_row = profile_res.data[0]

        # 2. Customer specific attributes
        cust_res = (
            self.service_client.table("customer_profiles")
            .select("*")
            .eq("user_id", str(user_id))
            .execute()
        )
        cust_row = cust_res.data[0] if (cust_res.data and len(cust_res.data) > 0) else {}

        return CustomerProfileDetailedResponse(
            user_id=uuid.UUID(profile_row["id"]),
            full_name=profile_row["full_name"],
            phone=profile_row.get("phone"),
            email=profile_row.get("email"),
            avatar_url=profile_row.get("avatar_url"),
            role=UserRole(profile_row["role"]),
            is_active=profile_row["is_active"],
            emergency_contact_name=cust_row.get("emergency_contact_name"),
            emergency_contact_phone=cust_row.get("emergency_contact_phone"),
            created_at=profile_row["created_at"],
            updated_at=profile_row["updated_at"],
        )

    async def update_customer_profile(
        self, user_id: uuid.UUID, payload: CustomerProfileUpdate
    ) -> CustomerProfileDetailedResponse:
        """
        Update customer profile fields safely.
        Only allows updating: full_name, phone, avatar_url, emergency_contact_name, emergency_contact_phone.
        Strictly prevents tampering with user_id, role, or active status.
        """
        # Update public.profiles if base profile fields provided
        profile_update: dict[str, Any] = {}
        if payload.full_name is not None:
            profile_update["full_name"] = payload.full_name
        if payload.phone is not None:
            profile_update["phone"] = payload.phone
        if payload.avatar_url is not None:
            profile_update["avatar_url"] = payload.avatar_url

        if profile_update:
            try:
                self.service_client.table("profiles").update(profile_update).eq(
                    "id", str(user_id)
                ).execute()
            except Exception as exc:
                logger.error("profile_update_failed", user_id=str(user_id), error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update profile.",
                )

        # Update or create public.customer_profiles if emergency contact fields provided
        cust_update: dict[str, Any] = {}
        if payload.emergency_contact_name is not None:
            cust_update["emergency_contact_name"] = payload.emergency_contact_name
        if payload.emergency_contact_phone is not None:
            cust_update["emergency_contact_phone"] = payload.emergency_contact_phone

        if cust_update:
            # Check if customer_profiles record exists
            existing_cust = (
                self.service_client.table("customer_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            try:
                if existing_cust.data and len(existing_cust.data) > 0:
                    self.service_client.table("customer_profiles").update(cust_update).eq(
                        "user_id", str(user_id)
                    ).execute()
                else:
                    cust_update["user_id"] = str(user_id)
                    self.service_client.table("customer_profiles").insert(cust_update).execute()
            except Exception as exc:
                logger.error("customer_profile_update_failed", user_id=str(user_id), error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update customer emergency contact details.",
                )

        return await self.get_customer_profile(user_id)
