"""
Address Service Layer.

Handles customer address CRUD operations, ownership verification,
default address state synchronization, and historical booking reference checks.
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.address import AddressCreate, AddressResponse, AddressUpdate

logger = get_logger("services.address")


class AddressService:
    """Business operations for customer service addresses."""

    def __init__(self):
        self.service_client = get_supabase_service_client()

    async def list_customer_addresses(self, customer_id: uuid.UUID) -> list[AddressResponse]:
        """Fetch all addresses saved by the customer, ordered with default address first."""
        response = (
            self.service_client.table("addresses")
            .select("*")
            .eq("customer_id", str(customer_id))
            .order("is_default", desc=True)
            .order("created_at", desc=True)
            .execute()
        )
        return [AddressResponse.model_validate(row) for row in response.data or []]

    async def get_customer_address(
        self, address_id: uuid.UUID, customer_id: uuid.UUID
    ) -> AddressResponse:
        """
        Fetch specific customer address with strict server-side ownership enforcement.
        Raises 404 if address does not exist or belongs to another customer.
        """
        response = (
            self.service_client.table("addresses")
            .select("*")
            .eq("id", str(address_id))
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found.",
            )

        row = response.data[0]
        if str(row.get("customer_id")) != str(customer_id):
            logger.warning(
                "address_access_denied",
                address_id=str(address_id),
                owner_id=row.get("customer_id"),
                requester_id=str(customer_id),
            )
            # Return 404 to avoid leaking existence of another customer's address
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found.",
            )

        return AddressResponse.model_validate(row)

    async def create_customer_address(
        self, customer_id: uuid.UUID, payload: AddressCreate
    ) -> AddressResponse:
        """
        Create a new address for the customer.
        If marked default, unsets default flag on previous customer addresses.
        If this is customer's first address, automatically promotes to default.
        """
        # Check existing count
        existing_res = (
            self.service_client.table("addresses")
            .select("id")
            .eq("customer_id", str(customer_id))
            .execute()
        )
        is_first_address = not existing_res.data or len(existing_res.data) == 0

        target_default = payload.is_default or is_first_address

        # If setting as default, clear default status from other addresses
        if target_default:
            self.service_client.table("addresses").update(
                {"is_default": False}
            ).eq("customer_id", str(customer_id)).execute()

        insert_data = {
            "customer_id": str(customer_id),
            "label": payload.label,
            "address_line": payload.address_line,
            "area": payload.area,
            "city": payload.city,
            "state": payload.state,
            "postal_code": payload.postal_code,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
            "landmark": payload.landmark,
            "is_default": target_default,
        }

        try:
            insert_res = (
                self.service_client.table("addresses")
                .insert(insert_data)
                .execute()
            )
        except Exception as exc:
            logger.error("address_create_failed", customer_id=str(customer_id), error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save address.",
            )

        if not insert_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Address creation failed.",
            )

        return AddressResponse.model_validate(insert_res.data[0])

    async def update_customer_address(
        self, address_id: uuid.UUID, customer_id: uuid.UUID, payload: AddressUpdate
    ) -> AddressResponse:
        """
        Partially update customer address with ownership check and default address management.
        """
        # Verify ownership first
        await self.get_customer_address(address_id, customer_id)

        update_dict: dict[str, Any] = {}

        if payload.label is not None:
            update_dict["label"] = payload.label
        if payload.address_line is not None:
            update_dict["address_line"] = payload.address_line
        if payload.area is not None:
            update_dict["area"] = payload.area
        if payload.city is not None:
            update_dict["city"] = payload.city
        if payload.state is not None:
            update_dict["state"] = payload.state
        if payload.postal_code is not None:
            update_dict["postal_code"] = payload.postal_code
        if payload.latitude is not None:
            update_dict["latitude"] = payload.latitude
        if payload.longitude is not None:
            update_dict["longitude"] = payload.longitude
        if payload.landmark is not None:
            update_dict["landmark"] = payload.landmark

        if payload.is_default is True:
            # Unset default on other customer addresses
            self.service_client.table("addresses").update(
                {"is_default": False}
            ).eq("customer_id", str(customer_id)).execute()
            update_dict["is_default"] = True
        elif payload.is_default is False:
            update_dict["is_default"] = False

        if update_dict:
            try:
                self.service_client.table("addresses").update(update_dict).eq(
                    "id", str(address_id)
                ).execute()
            except Exception as exc:
                logger.error("address_update_failed", address_id=str(address_id), error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update address.",
                )

        return await self.get_customer_address(address_id, customer_id)

    async def delete_customer_address(
        self, address_id: uuid.UUID, customer_id: uuid.UUID
    ) -> None:
        """
        Delete a customer address with ownership and booking history protection.
        Prevents deletion if referenced by existing service bookings.
        """
        # Verify address ownership
        await self.get_customer_address(address_id, customer_id)

        # Check for referencing bookings
        booking_check = (
            self.service_client.table("bookings")
            .select("id")
            .eq("address_id", str(address_id))
            .limit(1)
            .execute()
        )
        if booking_check.data and len(booking_check.data) > 0:
            logger.info("address_deletion_blocked_history", address_id=str(address_id))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete address because it is associated with existing service bookings. Historical booking records must be preserved.",
            )

        # Delete address
        try:
            self.service_client.table("addresses").delete().eq(
                "id", str(address_id)
            ).execute()
        except Exception as exc:
            logger.error("address_delete_failed", address_id=str(address_id), error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete address.",
            )
