"""
Vehicle Service Layer.

Handles vehicle catalog lookups, customer vehicle registration, ownership verification,
model-brand relationship validation, and safe foreign-key deletion checks.
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_client, get_supabase_service_client
from app.schemas.vehicle import (
    VehicleBrandResponse,
    VehicleCreate,
    VehicleModelResponse,
    VehicleResponse,
    VehicleTypeResponse,
    VehicleUpdate,
)

logger = get_logger("services.vehicle")


class VehicleService:
    """Business operations for vehicle catalog and customer-owned vehicles."""

    def __init__(self):
        self.service_client = get_supabase_service_client()
        self.client = get_supabase_client()

    # ==========================================================================
    # Catalog Lookups
    # ==========================================================================

    async def list_vehicle_types(self) -> list[VehicleTypeResponse]:
        """Fetch active vehicle types (e.g. Car, Bike, Scooter)."""
        response = (
            self.client.table("vehicle_types")
            .select("*")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return [VehicleTypeResponse.model_validate(row) for row in response.data or []]

    async def list_vehicle_brands(self) -> list[VehicleBrandResponse]:
        """Fetch active vehicle manufacturers / brands."""
        response = (
            self.client.table("vehicle_brands")
            .select("*")
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return [VehicleBrandResponse.model_validate(row) for row in response.data or []]

    async def list_models_by_brand(self, brand_id: uuid.UUID) -> list[VehicleModelResponse]:
        """Fetch active vehicle models belonging to a specific brand."""
        response = (
            self.client.table("vehicle_models")
            .select("*")
            .eq("brand_id", str(brand_id))
            .eq("is_active", True)
            .order("name")
            .execute()
        )
        return [VehicleModelResponse.model_validate(row) for row in response.data or []]

    # ==========================================================================
    # Customer Vehicle Management
    # ==========================================================================

    async def list_customer_vehicles(self, customer_id: uuid.UUID) -> list[VehicleResponse]:
        """List all vehicles belonging to the authenticated customer."""
        response = (
            self.service_client.table("vehicles")
            .select(
                "*, vehicle_brands!brand_id(name), vehicle_models!model_id(name), vehicle_types!vehicle_type_id(name)"
            )
            .eq("customer_id", str(customer_id))
            .order("is_primary", desc=True)
            .order("created_at", desc=True)
            .execute()
        )
        result: list[VehicleResponse] = []
        for row in response.data or []:
            brand_info = row.pop("vehicle_brands", None) or {}
            model_info = row.pop("vehicle_models", None) or {}
            type_info = row.pop("vehicle_types", None) or {}
            row["brand_name"] = brand_info.get("name")
            row["model_name"] = model_info.get("name")
            row["vehicle_type_name"] = type_info.get("name")
            result.append(VehicleResponse.model_validate(row))
        return result

    async def get_customer_vehicle(
        self, vehicle_id: uuid.UUID, customer_id: uuid.UUID
    ) -> VehicleResponse:
        """
        Fetch customer vehicle by ID with strict server-side ownership verification.
        Raises 404 if vehicle does not exist or belongs to another customer.
        """
        response = (
            self.service_client.table("vehicles")
            .select(
                "*, vehicle_brands!brand_id(name), vehicle_models!model_id(name), vehicle_types!vehicle_type_id(name)"
            )
            .eq("id", str(vehicle_id))
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found.",
            )

        row = response.data[0]
        if str(row.get("customer_id")) != str(customer_id):
            logger.warning(
                "vehicle_access_denied",
                vehicle_id=str(vehicle_id),
                owner_id=row.get("customer_id"),
                requester_id=str(customer_id),
            )
            # Return 404 to avoid leaking existence of another customer's vehicle
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found.",
            )

        brand_info = row.pop("vehicle_brands", None) or {}
        model_info = row.pop("vehicle_models", None) or {}
        type_info = row.pop("vehicle_types", None) or {}
        row["brand_name"] = brand_info.get("name")
        row["model_name"] = model_info.get("name")
        row["vehicle_type_name"] = type_info.get("name")
        return VehicleResponse.model_validate(row)

    async def create_customer_vehicle(
        self, customer_id: uuid.UUID, payload: VehicleCreate
    ) -> VehicleResponse:
        """
        Register a new vehicle for the authenticated customer.
        Validates foreign key integrity and ensures model belongs to selected brand and type.
        """
        # 1. Validate vehicle_type exists
        type_res = (
            self.service_client.table("vehicle_types")
            .select("id, is_active")
            .eq("id", str(payload.vehicle_type_id))
            .execute()
        )
        if not type_res.data or not type_res.data[0].get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive vehicle type specified.",
            )

        # 2. Validate brand exists
        brand_res = (
            self.service_client.table("vehicle_brands")
            .select("id, is_active")
            .eq("id", str(payload.brand_id))
            .execute()
        )
        if not brand_res.data or not brand_res.data[0].get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive vehicle brand specified.",
            )

        # 3. Validate model exists and belongs to brand & vehicle_type
        model_res = (
            self.service_client.table("vehicle_models")
            .select("id, brand_id, vehicle_type_id, is_active")
            .eq("id", str(payload.model_id))
            .execute()
        )
        if not model_res.data or not model_res.data[0].get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or inactive vehicle model specified.",
            )

        model_row = model_res.data[0]
        if str(model_row.get("brand_id")) != str(payload.brand_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified model does not belong to the selected brand.",
            )
        if str(model_row.get("vehicle_type_id")) != str(payload.vehicle_type_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified model does not match the selected vehicle type.",
            )

        # 4. Check registration number uniqueness for this customer
        existing_reg = (
            self.service_client.table("vehicles")
            .select("id")
            .eq("customer_id", str(customer_id))
            .eq("registration_number", payload.registration_number)
            .execute()
        )
        if existing_reg.data and len(existing_reg.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A vehicle with registration number '{payload.registration_number}' is already registered to your account.",
            )

        # 5. Handle primary vehicle flag (if true, unset on other customer vehicles)
        if payload.is_primary:
            self.service_client.table("vehicles").update(
                {"is_primary": False}
            ).eq("customer_id", str(customer_id)).execute()

        # 6. Insert new vehicle
        insert_data = {
            "customer_id": str(customer_id),
            "vehicle_type_id": str(payload.vehicle_type_id),
            "brand_id": str(payload.brand_id),
            "model_id": str(payload.model_id),
            "registration_number": payload.registration_number,
            "manufacture_year": payload.manufacture_year,
            "color": payload.color,
            "nickname": payload.nickname,
            "fuel_type": payload.fuel_type.value if payload.fuel_type else None,
            "odometer_km": payload.odometer_km,
            "is_primary": payload.is_primary,
        }

        try:
            insert_res = (
                self.service_client.table("vehicles")
                .insert(insert_data)
                .execute()
            )
        except Exception as exc:
            logger.error("vehicle_insert_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to register vehicle.",
            )

        if not insert_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Vehicle creation did not return inserted record.",
            )

        new_vehicle_id = uuid.UUID(insert_res.data[0]["id"])
        return await self.get_customer_vehicle(new_vehicle_id, customer_id)

    async def update_customer_vehicle(
        self, vehicle_id: uuid.UUID, customer_id: uuid.UUID, payload: VehicleUpdate
    ) -> VehicleResponse:
        """
        Partially update an existing customer vehicle with ownership enforcement.
        Prevents modification of ownership fields and validates new model/brand combinations.
        """
        # Verify ownership first
        existing_vehicle = await self.get_customer_vehicle(vehicle_id, customer_id)

        update_dict: dict[str, Any] = {}

        # Determine target type, brand, model
        target_type_id = payload.vehicle_type_id or existing_vehicle.vehicle_type_id
        target_brand_id = payload.brand_id or existing_vehicle.brand_id
        target_model_id = payload.model_id or existing_vehicle.model_id

        # If any of the catalog references are being changed, re-validate relationship
        if (
            payload.vehicle_type_id is not None
            or payload.brand_id is not None
            or payload.model_id is not None
        ):
            model_res = (
                self.service_client.table("vehicle_models")
                .select("id, brand_id, vehicle_type_id, is_active")
                .eq("id", str(target_model_id))
                .execute()
            )
            if not model_res.data or not model_res.data[0].get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid or inactive vehicle model specified.",
                )
            model_row = model_res.data[0]
            if str(model_row.get("brand_id")) != str(target_brand_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The specified model does not belong to the selected brand.",
                )
            if str(model_row.get("vehicle_type_id")) != str(target_type_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="The specified model does not match the selected vehicle type.",
                )

            if payload.vehicle_type_id:
                update_dict["vehicle_type_id"] = str(payload.vehicle_type_id)
            if payload.brand_id:
                update_dict["brand_id"] = str(payload.brand_id)
            if payload.model_id:
                update_dict["model_id"] = str(payload.model_id)

        # Check registration number uniqueness if updated
        if payload.registration_number:
            conflict_res = (
                self.service_client.table("vehicles")
                .select("id")
                .eq("customer_id", str(customer_id))
                .eq("registration_number", payload.registration_number)
                .neq("id", str(vehicle_id))
                .execute()
            )
            if conflict_res.data and len(conflict_res.data) > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Another vehicle with registration number '{payload.registration_number}' is already registered in your account.",
                )
            update_dict["registration_number"] = payload.registration_number

        if payload.manufacture_year is not None:
            update_dict["manufacture_year"] = payload.manufacture_year
        if payload.color is not None:
            update_dict["color"] = payload.color
        if payload.nickname is not None:
            update_dict["nickname"] = payload.nickname
        if payload.fuel_type is not None:
            update_dict["fuel_type"] = payload.fuel_type.value
        if payload.odometer_km is not None:
            update_dict["odometer_km"] = payload.odometer_km

        if payload.is_primary is True:
            # Unset primary on other vehicles
            self.service_client.table("vehicles").update(
                {"is_primary": False}
            ).eq("customer_id", str(customer_id)).execute()
            update_dict["is_primary"] = True
        elif payload.is_primary is False:
            update_dict["is_primary"] = False

        if update_dict:
            try:
                self.service_client.table("vehicles").update(update_dict).eq(
                    "id", str(vehicle_id)
                ).execute()
            except Exception as exc:
                logger.error("vehicle_update_failed", vehicle_id=str(vehicle_id), error=str(exc))
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to update vehicle.",
                )

        return await self.get_customer_vehicle(vehicle_id, customer_id)

    async def delete_customer_vehicle(
        self, vehicle_id: uuid.UUID, customer_id: uuid.UUID
    ) -> None:
        """
        Delete a customer vehicle with ownership and historical foreign key protection.
        Prevents deletion if referenced by existing bookings.
        """
        # Verify vehicle ownership first (raises 404 if not found or not owner)
        await self.get_customer_vehicle(vehicle_id, customer_id)

        # Check for referencing bookings
        booking_check = (
            self.service_client.table("bookings")
            .select("id")
            .eq("vehicle_id", str(vehicle_id))
            .limit(1)
            .execute()
        )
        if booking_check.data and len(booking_check.data) > 0:
            logger.info("vehicle_deletion_blocked_history", vehicle_id=str(vehicle_id))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete vehicle because it is associated with existing service bookings. Historical service records must be preserved.",
            )

        # Delete vehicle record
        try:
            self.service_client.table("vehicles").delete().eq(
                "id", str(vehicle_id)
            ).execute()
        except Exception as exc:
            logger.error("vehicle_delete_failed", vehicle_id=str(vehicle_id), error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete vehicle.",
            )
