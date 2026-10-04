"""
Booking Service Layer.

Authoritative coordinator for booking lifecycle operations, ownership validation,
pricing calculations, and database state transitions.
Communicates directly with Supabase via privileged backend service client.
"""

from datetime import datetime, timezone
import secrets
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.booking import BookingCreate, BookingStatus
from app.services.booking_pricing_service import BookingPricingService
from app.services.booking_state_machine import BookingStateMachine

logger = get_logger("services.booking")


class BookingService:
    """Encapsulates booking domain logic, ownership enforcement, and database queries."""

    def __init__(self):
        self.client = get_supabase_service_client()
        self.pricing_service = BookingPricingService()

    async def create_booking(
        self,
        customer_id: uuid.UUID,
        payload: BookingCreate,
    ) -> dict[str, Any]:
        """
        Create a new customer booking authoritatively.

        Workflow:
        1. Verify vehicle belongs to authenticated customer (404 if not found/accessible).
        2. Verify address belongs to authenticated customer (404 if not found/accessible).
        3. Authoritatively validate service catalog items, category, and vehicle compatibility.
        4. Calculate subtotal and monetary totals via BookingPricingService with Decimal precision.
        5. Insert bookings record with initial status 'pending' and payment_status 'unpaid'.
           (Note: DB trigger trg_track_booking_status automatically records initial status history).
        6. Insert booking_items. If item insertion fails, perform compensating deletion of
           the booking header to preserve atomicity and prevent orphan booking headers.
        """
        # 1. Ownership & existence check for vehicle
        v_res = (
            self.client.table("vehicles")
            .select("id, customer_id, vehicle_type_id")
            .eq("id", str(payload.vehicle_id))
            .eq("customer_id", str(customer_id))
            .execute()
        )
        if not v_res.data or len(v_res.data) == 0:
            logger.warning(
                "booking_creation_vehicle_inaccessible",
                customer_id=str(customer_id),
                vehicle_id=str(payload.vehicle_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found.",
            )
        vehicle_record = v_res.data[0]
        vehicle_type_id = uuid.UUID(vehicle_record["vehicle_type_id"])

        # 2. Ownership & existence check for address
        addr_res = (
            self.client.table("addresses")
            .select("id, customer_id, latitude, longitude")
            .eq("id", str(payload.address_id))
            .eq("customer_id", str(customer_id))
            .execute()
        )
        if not addr_res.data or len(addr_res.data) == 0:
            logger.warning(
                "booking_creation_address_inaccessible",
                customer_id=str(customer_id),
                address_id=str(payload.address_id),
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Address not found.",
            )
        address_record = addr_res.data[0]
        requested_latitude = address_record["latitude"]
        requested_longitude = address_record["longitude"]

        # 3. Calculate authoritative pricing & validate services
        pricing = await self.pricing_service.calculate_pricing(
            vehicle_type_id=vehicle_type_id,
            items=payload.items,
        )

        # 4. Determine schedule timestamp
        scheduled_at = payload.scheduled_at or datetime.now(timezone.utc)

        # 5. Generate unique booking number
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        rand_suffix = secrets.token_hex(3).upper()
        booking_number = f"BK-{date_str}-{rand_suffix}"

        # 6. Insert parent booking record
        booking_insert_data = {
            "booking_number": booking_number,
            "customer_id": str(customer_id),
            "vehicle_id": str(payload.vehicle_id),
            "address_id": str(payload.address_id),
            "scheduled_at": scheduled_at.isoformat(),
            "requested_latitude": str(requested_latitude),
            "requested_longitude": str(requested_longitude),
            "customer_notes": payload.customer_notes,
            "subtotal": str(pricing.subtotal),
            "additional_charges": str(pricing.additional_charges),
            "discount_amount": str(pricing.discount_amount),
            "tax_amount": str(pricing.tax_amount),
            "total_amount": str(pricing.total_amount),
            "payment_status": "unpaid",
            "booking_status": "pending",
        }

        try:
            booking_res = (
                self.client.table("bookings")
                .insert(booking_insert_data)
                .execute()
            )
        except Exception as exc:
            logger.error("booking_header_insert_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize booking record.",
            )

        if not booking_res.data or len(booking_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to initialize booking record.",
            )

        created_booking = booking_res.data[0]
        booking_id = created_booking["id"]

        # 7. Insert booking items with compensating rollback on failure
        items_payload = [
            {
                "booking_id": booking_id,
                "service_id": str(p_item.service_id),
                "quantity": p_item.quantity,
                "unit_price": str(p_item.unit_price),
                "total_price": str(p_item.total_price),
                "notes": p_item.notes,
            }
            for p_item in pricing.items
        ]

        try:
            items_res = (
                self.client.table("booking_items")
                .insert(items_payload)
                .execute()
            )
            if not items_res.data or len(items_res.data) != len(items_payload):
                raise RuntimeError("Mismatch in number of inserted booking items.")
        except Exception as exc:
            logger.error(
                "booking_items_insert_failed_compensating_delete",
                booking_id=booking_id,
                error=str(exc),
            )
            # Compensating rollback to maintain application atomicity
            try:
                self.client.table("bookings").delete().eq("id", booking_id).execute()
            except Exception as rollback_exc:
                logger.critical(
                    "compensating_delete_failed_orphan_risk",
                    booking_id=booking_id,
                    error=str(rollback_exc),
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record booking items. Booking creation was rolled back.",
            )

        # Assemble saved items with service_names from pricing engine
        saved_items = items_res.data
        for idx, saved_item in enumerate(saved_items):
            if idx < len(pricing.items):
                saved_item["service_name"] = pricing.items[idx].service_name

        created_booking["items"] = saved_items
        created_booking["booking_items"] = saved_items

        logger.info(
            "booking_created_successfully",
            booking_id=booking_id,
            booking_number=booking_number,
            customer_id=str(customer_id),
            subtotal=str(pricing.subtotal),
            total_amount=str(pricing.total_amount),
        )

        return created_booking

    async def get_booking_by_id(self, booking_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch booking details by UUID with booking items and service names joined."""
        response = (
            self.client.table("bookings")
            .select("*, booking_items(*, services(name))")
            .eq("id", str(booking_id))
            .execute()
        )
        if response.data and len(response.data) > 0:
            booking = response.data[0]
            # Ensure items key is populated for response model
            booking["items"] = booking.get("booking_items", [])
            return booking
        return None

    async def list_customer_bookings(
        self, customer_id: uuid.UUID, limit: int = 20, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List bookings for a specific customer with booking items joined."""
        response = (
            self.client.table("bookings")
            .select("*, booking_items(*, services(name))")
            .eq("customer_id", str(customer_id))
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
        results = response.data or []
        for b in results:
            b["items"] = b.get("booking_items", [])
        return results

    async def update_booking_status(
        self,
        booking_id: uuid.UUID,
        new_status: BookingStatus,
        user_id: uuid.UUID,
        user_role: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute an authoritative booking status transition.

        Validates the transition graph and role permissions via BookingStateMachine.
        Enforces conditional concurrency check (returns 409 if modified concurrently).
        Delegates history recording to DB trigger trg_track_booking_status.
        """
        # 1. Fetch current booking record
        booking_res = (
            self.client.table("bookings")
            .select("*")
            .eq("id", str(booking_id))
            .execute()
        )
        if not booking_res.data or len(booking_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = booking_res.data[0]

        # 2. Check role, ownership, and assignment association
        role = user_role.lower()
        is_customer_owner = False
        is_assigned_mechanic = False

        if role == "customer":
            if str(booking.get("customer_id")) != str(user_id):
                # 404 to avoid leaking booking existence to unauthorized customer
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found.",
                )
            is_customer_owner = True

        elif role == "mechanic":
            # Check if this mechanic has an accepted assignment for this booking
            m_profile_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if m_profile_res.data and len(m_profile_res.data) > 0:
                mechanic_profile_id = m_profile_res.data[0]["id"]
                asgn_res = (
                    self.client.table("mechanic_assignments")
                    .select("id")
                    .eq("booking_id", str(booking_id))
                    .eq("mechanic_id", str(mechanic_profile_id))
                    .eq("assignment_status", "accepted")
                    .execute()
                )
                if asgn_res.data and len(asgn_res.data) > 0:
                    is_assigned_mechanic = True

            if not is_assigned_mechanic:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You are not the assigned mechanic for this booking.",
                )

        elif role not in ["admin", "support"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user_role}' is not authorized to transition booking status.",
            )

        # 3. Read current status and validate through BookingStateMachine
        current_status_str = booking.get("booking_status", "pending")
        current_status = BookingStateMachine.to_enum(current_status_str)

        is_valid, error_msg = BookingStateMachine.validate_transition(
            current_status=current_status,
            new_status=new_status,
            actor_role=role,
            is_customer_owner=is_customer_owner,
            is_assigned_mechanic=is_assigned_mechanic,
            reason=reason,
        )

        if not is_valid:
            # Differentiate between role permission denial and invalid state transitions
            if (
                "not permitted" in error_msg.lower()
                or "not authorized" in error_msg.lower()
                or "does not own" in error_msg.lower()
                or "only the assigned" in error_msg.lower()
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=error_msg,
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg,
            )

        # 4. Perform atomic conditional update on bookings
        upd_res = (
            self.client.table("bookings")
            .update({"booking_status": new_status.value})
            .eq("id", str(booking_id))
            .eq("booking_status", current_status.value)
            .execute()
        )

        if not upd_res.data or len(upd_res.data) == 0:
            logger.warning(
                "booking_status_concurrent_conflict",
                booking_id=str(booking_id),
                expected_status=current_status.value,
                target_status=new_status.value,
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking status was changed concurrently. Please refresh and try again.",
            )

        # 5. Handle cancellation side effects
        if new_status == BookingStatus.CANCELLED:
            try:
                self.client.table("mechanic_assignments").update(
                    {"assignment_status": "cancelled"}
                ).eq("booking_id", str(booking_id)).in_(
                    "assignment_status", ["offered", "accepted"]
                ).execute()
            except Exception as exc:
                logger.warning("failed_to_cancel_assignments_on_booking_cancellation", error=str(exc))

        # 6. If custom reason provided, update the latest status history entry created by DB trigger
        if reason:
            try:
                self.client.table("booking_status_history").update(
                    {"reason": reason}
                ).eq("booking_id", str(booking_id)).eq(
                    "new_status", new_status.value
                ).order("created_at", desc=True).limit(1).execute()
            except Exception as exc:
                logger.warning("failed_to_update_status_history_reason", error=str(exc))

        # 6b. Dispatch lifecycle notification (side effect, never breaks booking transition)
        try:
            from app.services.notification_service import NotificationService
            notifier = NotificationService()
            assigned_mech_user_id = None
            if new_status in [BookingStatus.CANCELLED, BookingStatus.DISPUTED]:
                try:
                    asgn_check = (
                        self.client.table("mechanic_assignments")
                        .select("mechanic_id, mechanic_profiles(user_id)")
                        .eq("booking_id", str(booking_id))
                        .eq("assignment_status", "accepted")
                        .execute()
                    )
                    if asgn_check.data and len(asgn_check.data) > 0:
                        m_row = asgn_check.data[0]
                        mp = m_row.get("mechanic_profiles")
                        if isinstance(mp, dict) and mp.get("user_id"):
                            assigned_mech_user_id = uuid.UUID(str(mp["user_id"]))
                except Exception:
                    pass

            await notifier.notify_booking_status_change(
                booking_id=booking_id,
                customer_id=uuid.UUID(str(booking.get("customer_id"))),
                new_status=new_status.value,
                mechanic_user_id=assigned_mech_user_id,
                booking_number=booking.get("booking_number"),
            )
        except Exception as notify_err:
            logger.warning("booking_status_notification_failed", error=str(notify_err))

        logger.info(
            "booking_status_transition_success",
            booking_id=str(booking_id),
            from_status=current_status.value,
            to_status=new_status.value,
            user_id=str(user_id),
            user_role=role,
        )

        # 7. Return refreshed booking with items joined
        refreshed = await self.get_booking_by_id(booking_id)
        return refreshed or upd_res.data[0]

