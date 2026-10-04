"""
Authoritative Booking Pricing Engine.

This service is the single authoritative source of truth for:
1. Validating service existence, active status, category active status, and vehicle compatibility.
2. Resolving official base_price, minimum_price floor, and pricing parameters from service_pricing.
3. Calculating line totals and subtotal using exact Python Decimal arithmetic.
4. Setting zero/default values for additional charges, discounts, and taxes in alignment with the database schema.

Never uses float for monetary amounts. Never trusts client-supplied monetary values.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.booking import BookingItemCreate

logger = get_logger("services.booking_pricing")

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class PricedBookingItem:
    """Authoritative priced booking line item."""
    service_id: uuid.UUID
    service_name: str
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    notes: str | None = None


@dataclass(frozen=True)
class CalculatedPricing:
    """Authoritative financial totals for a booking."""
    subtotal: Decimal
    additional_charges: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    items: list[PricedBookingItem]


class BookingPricingService:
    """
    Authoritative pricing and service compatibility engine.
    Calculates subtotal and line items without trusting any client-provided prices.
    """

    def __init__(self):
        self.client = get_supabase_service_client()

    async def calculate_pricing(
        self,
        vehicle_type_id: uuid.UUID,
        items: list[BookingItemCreate],
    ) -> CalculatedPricing:
        """
        Calculates authoritative pricing for requested services and vehicle type.
        
        Validations performed:
        - items list is non-empty
        - no duplicate service_id entries
        - each quantity > 0
        - vehicle_type exists and is active
        - each service exists and is active
        - each service category is active
        - each service is compatible with vehicle_type
        - active pricing exists for each service
        """
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Booking must contain at least one service item.",
            )

        # 1. Enforce unique service items
        service_ids = [item.service_id for item in items]
        if len(service_ids) != len(set(service_ids)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Duplicate service item detected. Each service can only appear once in a booking. Adjust quantity instead.",
            )

        # 2. Verify vehicle type exists and is active
        vt_res = (
            self.client.table("vehicle_types")
            .select("id, name, is_active")
            .eq("id", str(vehicle_type_id))
            .execute()
        )
        if not vt_res.data or len(vt_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle type associated with vehicle does not exist.",
            )
        vt_row = vt_res.data[0]
        if not vt_row.get("is_active"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Vehicle type '{vt_row['name']}' is currently inactive.",
            )
        vt_name = vt_row["name"].lower()

        # 3. For each requested service, validate and authoritatively price
        priced_items: list[PricedBookingItem] = []

        for item in items:
            if item.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Quantity for service {item.service_id} must be greater than zero.",
                )

            # Query service and its category
            svc_res = (
                self.client.table("services")
                .select("id, name, is_active, vehicle_type, category_id, service_categories!category_id(is_active)")
                .eq("id", str(item.service_id))
                .execute()
            )
            if not svc_res.data or len(svc_res.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Service '{item.service_id}' does not exist in catalog.",
                )

            svc_row = svc_res.data[0]
            if not svc_row.get("is_active"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service '{svc_row['name']}' is currently inactive.",
                )

            # Verify category is active if present
            cat_info = svc_row.get("service_categories")
            if isinstance(cat_info, dict) and not cat_info.get("is_active", True):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Service category for '{svc_row['name']}' is currently inactive.",
                )

            # Validate vehicle type compatibility
            svc_type = (svc_row.get("vehicle_type") or "both").lower()
            if svc_type != "both":
                is_bike = any(b in vt_name for b in ["bike", "motorcycle", "scooter", "two_wheeler"])
                is_car = any(c in vt_name for c in ["car", "four_wheeler", "sedan", "suv", "hatchback"])
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

            # Query active service pricing
            pricing_res = (
                self.client.table("service_pricing")
                .select("id, base_price, minimum_price, pricing_parameters, vehicle_type_id")
                .eq("service_id", str(item.service_id))
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
                    "service_pricing_missing",
                    service_id=str(item.service_id),
                    vehicle_type_id=str(vehicle_type_id),
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"No active pricing configured for service '{svc_row['name']}' and vehicle type '{vt_row['name']}'.",
                )

            # Authoritative pricing calculation with Decimal
            base_price = Decimal(str(chosen_pricing["base_price"]))
            minimum_price = Decimal(str(chosen_pricing.get("minimum_price") or "0.00"))
            
            # Unit price is base_price, respecting minimum billable floor
            unit_price = max(base_price, minimum_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            total_price = (unit_price * Decimal(item.quantity)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            priced_items.append(
                PricedBookingItem(
                    service_id=item.service_id,
                    service_name=svc_row["name"],
                    quantity=item.quantity,
                    unit_price=unit_price,
                    total_price=total_price,
                    notes=item.notes,
                )
            )

        # 4. Aggregate financial totals
        subtotal = sum(p.total_price for p in priced_items).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        additional_charges = Decimal("0.00")
        discount_amount = Decimal("0.00")
        tax_amount = Decimal("0.00")
        total_amount = (subtotal + additional_charges + tax_amount - discount_amount).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

        return CalculatedPricing(
            subtotal=subtotal,
            additional_charges=additional_charges,
            discount_amount=discount_amount,
            tax_amount=tax_amount,
            total_amount=total_amount,
            items=priced_items,
        )
