"""
Additional Work Service Layer (Phase 7B & 7C).

Handles mechanic additional work proposals, customer approval/rejection lifecycle,
atomic financial adjustments, and concurrency controls.
"""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.evidence import validate_evidence_paths
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.additional_work import (
    AdditionalWorkCreate,
    CustomerApprovalRequest,
    CustomerRejectRequest,
)
from app.schemas.booking import BookingStatus
from app.services.booking_state_machine import BookingStateMachine

from app.services.notification_service import NotificationService

logger = get_logger("services.additional_work")

TWO_PLACES = Decimal("0.01")
TAX_RATE = Decimal("0.18")  # 18% GST for automotive services


class AdditionalWorkService:
    """Encapsulates additional work proposals, lifecycle guards, and atomic customer response."""

    def __init__(self, notif_service: NotificationService | None = None):
        self.client = get_supabase_service_client()
        self.notif_service = notif_service or NotificationService()

    async def create_additional_work_request(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: AdditionalWorkCreate,
    ) -> dict[str, Any]:
        """
        Mechanic creates an additional work request for a booking.

        Rules:
        1. Authenticated mechanic required.
        2. Mechanic must have an ACCEPTED assignment for this booking.
        3. Booking lifecycle permits additional work creation (inspection, service_in_progress, additional_work, awaiting_customer_approval).
        4. Derive mechanic_id from JWT/profile, never from request body.
        5. Title, description validated. Price >= 0.
        6. Evidence paths validated to belong to booking.
        7. Request created with status=pending.
        8. Transitions booking toward awaiting_customer_approval via BookingStateMachine.
        9. Relies on DB trigger trg_track_booking_status for history.
        """
        # 1. Resolve mechanic profile
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id")
            .eq("user_id", str(mechanic_user_id))
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found for authenticated user.",
            )
        mechanic_profile_id = uuid.UUID(m_res.data[0]["id"])

        # 2. Retrieve booking
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]
        cur_status = booking.get("booking_status")

        # 3. Verify accepted assignment
        asgn_res = (
            self.client.table("mechanic_assignments")
            .select("id, mechanic_id, assignment_status")
            .eq("booking_id", str(booking_id))
            .eq("mechanic_id", str(mechanic_profile_id))
            .eq("assignment_status", "accepted")
            .execute()
        )
        if not asgn_res.data or len(asgn_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have an accepted assignment for this booking.",
            )

        # 4. Verify booking lifecycle allows additional work creation
        allowed_creation_states = {
            BookingStatus.INSPECTION.value,
            BookingStatus.SERVICE_IN_PROGRESS.value,
            BookingStatus.ADDITIONAL_WORK.value,
            BookingStatus.AWAITING_CUSTOMER_APPROVAL.value,
        }
        if cur_status not in allowed_creation_states:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create additional work request for booking with status '{cur_status}'.",
            )

        # 5. Validate evidence file paths
        if payload.evidence_file_paths:
            validate_evidence_paths(
                payload.evidence_file_paths,
                expected_booking_id=booking_id,
                allowed_categories=["additional_work", "inspections"],
            )

        # 6. Insert additional_work_requests record
        insert_payload = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic_profile_id),
            "title": payload.title.strip(),
            "description": payload.description.strip(),
            "price": str(payload.price),
            "evidence_file_paths": payload.evidence_file_paths or [],
            "status": "pending",
        }

        try:
            ins_res = self.client.table("additional_work_requests").insert(insert_payload).execute()
        except Exception as exc:
            logger.error("failed_to_insert_additional_work_request", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record additional work request.",
            )

        if not ins_res.data or len(ins_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record additional work request.",
            )

        created_request = ins_res.data[0]

        # 7. Progress booking lifecycle to awaiting_customer_approval if needed
        # Transitions:
        # - inspection -> awaiting_customer_approval
        # - service_in_progress -> additional_work -> awaiting_customer_approval
        # - additional_work -> awaiting_customer_approval
        # (DB trigger trg_track_booking_status records each change)
        if cur_status == BookingStatus.INSPECTION.value:
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.AWAITING_CUSTOMER_APPROVAL.value}
            ).eq("id", str(booking_id)).eq("booking_status", BookingStatus.INSPECTION.value).execute()

        elif cur_status == BookingStatus.SERVICE_IN_PROGRESS.value:
            # Step 1: service_in_progress -> additional_work
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.ADDITIONAL_WORK.value}
            ).eq("id", str(booking_id)).eq("booking_status", BookingStatus.SERVICE_IN_PROGRESS.value).execute()
            # Step 2: additional_work -> awaiting_customer_approval
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.AWAITING_CUSTOMER_APPROVAL.value}
            ).eq("id", str(booking_id)).eq("booking_status", BookingStatus.ADDITIONAL_WORK.value).execute()

        elif cur_status == BookingStatus.ADDITIONAL_WORK.value:
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.AWAITING_CUSTOMER_APPROVAL.value}
            ).eq("id", str(booking_id)).eq("booking_status", BookingStatus.ADDITIONAL_WORK.value).execute()

        logger.info(
            "additional_work_request_created",
            request_id=created_request["id"],
            booking_id=str(booking_id),
            mechanic_id=str(mechanic_profile_id),
            price=str(payload.price),
        )

        # 8. Dispatch customer notification
        try:
            await self.notif_service.notify_additional_work_requested(
                booking_id=booking_id,
                customer_id=uuid.UUID(str(booking.get("customer_id"))),
                request_id=uuid.UUID(str(created_request["id"])),
                title=payload.title,
                price=payload.price,
            )
        except Exception as notify_err:
            logger.warning("additional_work_notification_failed", error=str(notify_err))

        return created_request

    async def list_additional_work_requests(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> list[dict[str, Any]]:
        """
        List all additional work requests for a booking.
        Authorized for: booking customer owner, assigned mechanic, admin/support.
        Returns 404 for unauthorized customer to avoid resource enumeration.
        """
        role = user_role.lower()

        # 1. Fetch booking
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]

        # 2. RBAC check
        if role == "customer":
            if str(booking.get("customer_id")) != str(user_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found.",
                )
        elif role == "mechanic":
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if not m_res.data or len(m_res.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Mechanic profile not found.",
                )
            mechanic_id = m_res.data[0]["id"]
            asgn_res = (
                self.client.table("mechanic_assignments")
                .select("id")
                .eq("booking_id", str(booking_id))
                .eq("mechanic_id", str(mechanic_id))
                .eq("assignment_status", "accepted")
                .execute()
            )
            if not asgn_res.data or len(asgn_res.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You are not the assigned mechanic for this booking.",
                )
        elif role not in ["admin", "support"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )

        # 3. Retrieve requests
        res = (
            self.client.table("additional_work_requests")
            .select("*")
            .eq("booking_id", str(booking_id))
            .order("created_at", desc=False)
            .execute()
        )
        return res.data or []

    async def approve_additional_work_request(
        self,
        booking_id: uuid.UUID,
        request_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        payload: CustomerApprovalRequest | None = None,
    ) -> dict[str, Any]:
        """
        Customer approves a pending additional work request.

        Atomic Operation & Security:
        1. Authenticated customer required.
        2. Customer must own the booking (404 if not found).
        3. Request must belong to booking (404 if not found).
        4. Request must be in 'pending' status.
        5. Booking must be in 'awaiting_customer_approval' status.
        6. Authoritative price read from additional_work_requests.price (never client body).
        7. Atomic conditional update on additional_work_requests with 409 conflict detection.
        8. Atomic recalculation of additional_charges, tax_amount, and total_amount using Decimal.
        9. Advances booking status to 'service_in_progress'.
        10. Compensating rollback on failure to maintain strict atomicity.
        """
        # 1. Fetch booking
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id, subtotal, additional_charges, discount_amount, tax_amount, total_amount, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]

        # 2. Customer ownership verification
        if str(booking.get("customer_id")) != str(customer_user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # 3. Fetch additional work request
        r_res = (
            self.client.table("additional_work_requests")
            .select("*")
            .eq("id", str(request_id))
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not r_res.data or len(r_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Additional work request not found.",
            )
        work_req = r_res.data[0]

        # 4. Check if request was already approved or rejected
        if work_req.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Additional work request has already been {work_req.get('status')}.",
            )

        # 5. Booking lifecycle verification
        cur_status = booking.get("booking_status")
        if cur_status == BookingStatus.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve additional work when booking is in 'cancelled' status.",
            )
        if cur_status != BookingStatus.AWAITING_CUSTOMER_APPROVAL.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot approve additional work when booking is in '{cur_status}' status.",
            )


        # 6. Authoritative price read from database
        request_price = Decimal(str(work_req["price"]))
        if request_price < Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid work request price.",
            )

        # 7. Recalculate financial totals with Decimal
        current_additional = Decimal(str(booking.get("additional_charges") or "0.00"))
        new_additional = (current_additional + request_price).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        subtotal = Decimal(str(booking.get("subtotal") or "0.00"))
        discount = Decimal(str(booking.get("discount_amount") or "0.00"))

        taxable_base = subtotal + new_additional - discount
        new_tax = (taxable_base * TAX_RATE).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        new_total = (taxable_base + new_tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        now_iso = datetime.now(timezone.utc).isoformat()
        customer_msg = payload.customer_response if payload else None

        # 8. Conditional update on additional_work_requests (atomic lock)
        upd_req = (
            self.client.table("additional_work_requests")
            .update({
                "status": "approved",
                "customer_response": customer_msg,
                "responded_at": now_iso,
            })
            .eq("id", str(request_id))
            .eq("booking_id", str(booking_id))
            .eq("status", "pending")
            .execute()
        )
        if not upd_req.data or len(upd_req.data) == 0:
            logger.warning(
                "additional_work_concurrent_conflict",
                booking_id=str(booking_id),
                request_id=str(request_id),
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Additional work request was already approved or rejected concurrently.",
            )

        approved_work_req = upd_req.data[0]

        # 9. Conditional update on bookings (financial totals + status transition)
        try:
            upd_b = (
                self.client.table("bookings")
                .update({
                    "additional_charges": str(new_additional),
                    "tax_amount": str(new_tax),
                    "total_amount": str(new_total),
                    "booking_status": BookingStatus.SERVICE_IN_PROGRESS.value,
                })
                .eq("id", str(booking_id))
                .eq("booking_status", BookingStatus.AWAITING_CUSTOMER_APPROVAL.value)
                .execute()
            )
            if not upd_b.data or len(upd_b.data) == 0:
                raise RuntimeError("Concurrent status modification on booking header.")
        except Exception as exc:
            logger.critical(
                "booking_financial_update_failed_compensating_rollback",
                booking_id=str(booking_id),
                request_id=str(request_id),
                error=str(exc),
            )
            # Roll back additional_work_requests status
            try:
                self.client.table("additional_work_requests").update({
                    "status": "pending",
                    "customer_response": None,
                    "responded_at": None,
                }).eq("id", str(request_id)).execute()
            except Exception as rb_exc:
                logger.critical("compensating_rollback_failed", error=str(rb_exc))

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking status was modified concurrently. Approval aborted.",
            )

        logger.info(
            "additional_work_approved_successfully",
            booking_id=str(booking_id),
            request_id=str(request_id),
            price=str(request_price),
            new_additional_charges=str(new_additional),
            new_tax_amount=str(new_tax),
            new_total_amount=str(new_total),
        )

        # 10. Dispatch mechanic notification
        try:
            m_prof = (
                self.client.table("mechanic_profiles")
                .select("user_id")
                .eq("id", str(work_req["mechanic_id"]))
                .execute()
            )
            if m_prof.data and len(m_prof.data) > 0:
                mech_user_id = uuid.UUID(str(m_prof.data[0]["user_id"]))
                await self.notif_service.notify_additional_work_approved(
                    booking_id=booking_id,
                    mechanic_user_id=mech_user_id,
                    request_id=request_id,
                    title=work_req.get("title", "Additional Work"),
                )
        except Exception as notify_err:
            logger.warning("additional_work_approval_notification_failed", error=str(notify_err))

        return approved_work_req

    async def reject_additional_work_request(
        self,
        booking_id: uuid.UUID,
        request_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        payload: CustomerRejectRequest | None = None,
    ) -> dict[str, Any]:
        """
        Customer rejects a pending additional work request.

        Rules:
        1. Authenticated customer ownership required.
        2. Request must be pending.
        3. Booking must be awaiting_customer_approval.
        4. Request status becomes 'rejected'.
        5. responded_at and customer_response populated.
        6. Booking transitions to 'service_in_progress'.
        7. NO financial amount changes on rejection.
        """
        # 1. Fetch booking
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]

        # 2. Ownership check
        if str(booking.get("customer_id")) != str(customer_user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # 3. Fetch request
        r_res = (
            self.client.table("additional_work_requests")
            .select("*")
            .eq("id", str(request_id))
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not r_res.data or len(r_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Additional work request not found.",
            )
        work_req = r_res.data[0]

        # 4. Check status is pending
        if work_req.get("status") != "pending":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Additional work request has already been {work_req.get('status')}.",
            )

        # 5. Booking lifecycle verification
        cur_status = booking.get("booking_status")
        if cur_status == BookingStatus.CANCELLED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reject additional work when booking is in 'cancelled' status.",
            )
        if cur_status != BookingStatus.AWAITING_CUSTOMER_APPROVAL.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot reject additional work when booking is in '{cur_status}' status.",
            )


        now_iso = datetime.now(timezone.utc).isoformat()
        reason_text = None
        if payload:
            reason_text = payload.reason or payload.customer_response

        # 6. Conditional update on additional_work_requests
        upd_req = (
            self.client.table("additional_work_requests")
            .update({
                "status": "rejected",
                "customer_response": reason_text,
                "responded_at": now_iso,
            })
            .eq("id", str(request_id))
            .eq("booking_id", str(booking_id))
            .eq("status", "pending")
            .execute()
        )
        if not upd_req.data or len(upd_req.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Additional work request was already approved or rejected concurrently.",
            )

        rejected_work_req = upd_req.data[0]

        # 7. Advance booking status to 'service_in_progress' (NO financial changes)
        try:
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.SERVICE_IN_PROGRESS.value}
            ).eq("id", str(booking_id)).eq("booking_status", BookingStatus.AWAITING_CUSTOMER_APPROVAL.value).execute()
        except Exception as exc:
            logger.warning("failed_to_advance_booking_on_reject", error=str(exc))

        logger.info(
            "additional_work_rejected_successfully",
            booking_id=str(booking_id),
            request_id=str(request_id),
            reason=reason_text,
        )

        # 8. Dispatch mechanic notification
        try:
            m_prof = (
                self.client.table("mechanic_profiles")
                .select("user_id")
                .eq("id", str(work_req["mechanic_id"]))
                .execute()
            )
            if m_prof.data and len(m_prof.data) > 0:
                mech_user_id = uuid.UUID(str(m_prof.data[0]["user_id"]))
                await self.notif_service.notify_additional_work_rejected(
                    booking_id=booking_id,
                    mechanic_user_id=mech_user_id,
                    request_id=request_id,
                    title=work_req.get("title", "Additional Work"),
                    reason=reason_text,
                )
        except Exception as notify_err:
            logger.warning("additional_work_rejection_notification_failed", error=str(notify_err))

        return rejected_work_req
