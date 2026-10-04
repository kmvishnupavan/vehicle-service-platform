"""
Service Catalog Domain Layer.

Handles service categories, catalog browsing, vehicle-type compatibility validation,
and authoritative labor and service pricing lookups.
"""

from decimal import Decimal
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_client
from app.schemas.service import (
    ServiceCategoryResponse,
    ServiceDetailResponse,
    ServicePriceResponse,
    ServicePricingResponse,
    ServiceResponse,
)

logger = get_logger("services.catalog")


class ServiceCatalogService:
    """Business operations for service catalog, packages, and authoritative pricing."""

    def __init__(self):
        # Catalog is public read, so publishable/anon client subject to SELECT RLS is used
        self.client = get_supabase_client()

    # ==========================================================================
    # Service Categories
    # ==========================================================================

    async def list_categories(self, active_only: bool = True) -> list[ServiceCategoryResponse]:
        """
        Fetch service categories in display order.
        """
        query = self.client.table("service_categories").select("*")
        if active_only:
            query = query.eq("is_active", True)
        
        response = query.order("display_order").order("name").execute()
        return [ServiceCategoryResponse.model_validate(row) for row in response.data or []]

    # ==========================================================================
    # Service Items
    # ==========================================================================

    async def list_services(
        self,
        category_id: uuid.UUID | None = None,
        vehicle_type_id: uuid.UUID | None = None,
        active_only: bool = True,
    ) -> list[ServiceResponse]:
        """
        List catalog services with optional filtering by category, vehicle type, and active status.
        Includes configured pricing tiers.
        """
        # If vehicle_type_id provided, verify its existence and fetch name
        target_vt_name = None
        if vehicle_type_id:
            vt_res = (
                self.client.table("vehicle_types")
                .select("id, name, is_active")
                .eq("id", str(vehicle_type_id))
                .execute()
            )
            if not vt_res.data or len(vt_res.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Specified vehicle type does not exist in catalog.",
                )
            if active_only and not vt_res.data[0].get("is_active"):
                return []
            target_vt_name = vt_res.data[0]["name"].lower()

        # Query services with category name join
        query = self.client.table("services").select(
            "*, service_categories!category_id(name), service_pricing(*, vehicle_types!vehicle_type_id(name))"
        )

        if active_only:
            query = query.eq("is_active", True)
        if category_id:
            query = query.eq("category_id", str(category_id))

        response = query.order("name").execute()

        results: list[ServiceResponse] = []
        for row in response.data or []:
            category_info = row.pop("service_categories", None) or {}
            pricing_rows = row.pop("service_pricing", None) or []

            # Check vehicle type compatibility if vehicle_type_id was filtered
            svc_type = (row.get("vehicle_type") or "both").lower()
            if target_vt_name and svc_type != "both":
                is_bike = any(b in target_vt_name for b in ["bike", "motorcycle", "scooter", "two_wheeler"])
                is_car = any(c in target_vt_name for c in ["car", "four_wheeler", "sedan", "suv", "hatchback"])
                if svc_type == "car" and is_bike and not is_car:
                    continue
                if svc_type == "bike" and is_car and not is_bike:
                    continue

            # Format pricing tiers with Decimal
            formatted_pricing: list[ServicePricingResponse] = []
            for p in pricing_rows:
                if active_only and not p.get("is_active", True):
                    continue
                # If filtered by vehicle_type_id, only include matching or universal pricing
                if vehicle_type_id:
                    p_vt_id = p.get("vehicle_type_id")
                    if p_vt_id and p_vt_id != str(vehicle_type_id):
                        continue

                vt_info = p.pop("vehicle_types", None) or {}
                p["vehicle_type_name"] = vt_info.get("name")
                p["base_price"] = Decimal(str(p["base_price"]))
                p["minimum_price"] = Decimal(str(p["minimum_price"]))
                formatted_pricing.append(ServicePricingResponse.model_validate(p))

            # If vehicle_type_id filter was requested, only include services that have active pricing
            if vehicle_type_id and not formatted_pricing:
                continue

            row["category_name"] = category_info.get("name")
            row["pricing"] = formatted_pricing
            results.append(ServiceResponse.model_validate(row))

        return results

    async def get_service_by_id(
        self, service_id: uuid.UUID, active_only: bool = True
    ) -> ServiceDetailResponse:
        """
        Fetch full details of a specific service including category and all pricing tiers.
        """
        response = (
            self.client.table("services")
            .select(
                "*, service_categories!category_id(*), service_pricing(*, vehicle_types!vehicle_type_id(name))"
            )
            .eq("id", str(service_id))
            .execute()
        )

        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in catalog.",
            )

        row = response.data[0]
        if active_only and not row.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found or is currently inactive.",
            )

        category_data = row.pop("service_categories", None)
        pricing_rows = row.pop("service_pricing", None) or []

        formatted_pricing: list[ServicePricingResponse] = []
        for p in pricing_rows:
            if active_only and not p.get("is_active", True):
                continue
            vt_info = p.pop("vehicle_types", None) or {}
            p["vehicle_type_name"] = vt_info.get("name")
            p["base_price"] = Decimal(str(p["base_price"]))
            p["minimum_price"] = Decimal(str(p["minimum_price"]))
            formatted_pricing.append(ServicePricingResponse.model_validate(p))

        # Determine supported vehicle types string list
        svc_type = row.get("vehicle_type", "both").lower()
        if svc_type == "both":
            supported_types = ["Car", "Bike / Motorcycle"]
        elif svc_type == "car":
            supported_types = ["Car"]
        else:
            supported_types = ["Bike / Motorcycle"]

        row["category_name"] = category_data.get("name") if category_data else None
        row["category"] = (
            ServiceCategoryResponse.model_validate(category_data)
            if category_data
            else None
        )
        row["pricing"] = formatted_pricing
        row["supported_vehicle_types"] = supported_types

        return ServiceDetailResponse.model_validate(row)

    # ==========================================================================
    # Authoritative Pricing Determination
    # ==========================================================================

    async def get_service_price(
        self, service_id: uuid.UUID, vehicle_type_id: uuid.UUID
    ) -> ServicePriceResponse:
        """
        Authoritatively determine service price for a specific vehicle type.
        
        Steps:
        1. Verify service exists and is active.
        2. Verify vehicle type exists and is active.
        3. Verify vehicle type compatibility against services.vehicle_type.
        4. Locate the active applicable service_pricing record (specific or universal fallback).
        5. Return authoritative price using Decimal without trusting client calculation.
        """
        # 1. Verify service
        svc_res = (
            self.client.table("services")
            .select("id, name, is_active, vehicle_type")
            .eq("id", str(service_id))
            .execute()
        )
        if not svc_res.data or len(svc_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Service not found in catalog.",
            )
        svc_row = svc_res.data[0]
        if not svc_row.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service '{svc_row['name']}' is currently inactive.",
            )

        # 2. Verify vehicle type
        vt_res = (
            self.client.table("vehicle_types")
            .select("id, name, is_active")
            .eq("id", str(vehicle_type_id))
            .execute()
        )
        if not vt_res.data or len(vt_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle type not found.",
            )
        vt_row = vt_res.data[0]
        if not vt_row.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle type '{vt_row['name']}' is currently inactive.",
            )

        # 3. Check compatibility
        vt_name_lower = vt_row["name"].lower()
        svc_type = (svc_row.get("vehicle_type") or "both").lower()
        if svc_type != "both":
            is_bike = any(b in vt_name_lower for b in ["bike", "motorcycle", "scooter", "two_wheeler"])
            is_car = any(c in vt_name_lower for c in ["car", "four_wheeler", "sedan", "suv", "hatchback"])
            if svc_type == "car" and is_bike and not is_car:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service '{svc_row['name']}' is only available for cars, not {vt_row['name']}.",
                )
            if svc_type == "bike" and is_car and not is_bike:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service '{svc_row['name']}' is only available for two-wheelers, not {vt_row['name']}.",
                )

        # 4. Locate applicable pricing record in public.service_pricing
        pricing_res = (
            self.client.table("service_pricing")
            .select("*")
            .eq("service_id", str(service_id))
            .eq("is_active", True)
            .execute()
        )

        matched_pricing = None
        fallback_pricing = None

        for p in pricing_res.data or []:
            p_vt_id = p.get("vehicle_type_id")
            if p_vt_id == str(vehicle_type_id):
                matched_pricing = p
                break
            elif p_vt_id is None:
                fallback_pricing = p

        chosen_pricing = matched_pricing or fallback_pricing

        if not chosen_pricing:
            logger.warning(
                "pricing_not_configured",
                service_id=str(service_id),
                vehicle_type_id=str(vehicle_type_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No active pricing configured for service '{svc_row['name']}' and vehicle type '{vt_row['name']}'.",
            )

        return ServicePriceResponse(
            service_id=uuid.UUID(svc_row["id"]),
            service_name=svc_row["name"],
            vehicle_type_id=uuid.UUID(vt_row["id"]),
            vehicle_type_name=vt_row["name"],
            base_price=Decimal(str(chosen_pricing["base_price"])),
            minimum_price=Decimal(str(chosen_pricing["minimum_price"])),
            pricing_parameters=chosen_pricing.get("pricing_parameters") or {},
            effective_from=chosen_pricing["effective_from"],
        )
