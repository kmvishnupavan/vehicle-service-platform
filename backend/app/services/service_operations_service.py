"""
Service Operations Coordinator (Phase 12).

Orchestrates end-to-end doorstep vehicle service operations:
- Mechanic arrival verification
- Structured vehicle diagnostic inspections
- Service checklists and category template seeding
- Service parts tracking
- Customer estimate approval and immutable price snapshots
- Strict service completion verification with mandatory checklist gates
- Comprehensive service report generation
- Dispute recording and administrative resolution
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.audit import record_audit_log
from app.core.evidence import validate_evidence_paths
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.booking import BookingStatus
from app.schemas.service_operations import (
    ArrivalResponse,
    BatchChecklistUpdateRequest,
    BookingChecklistItemResponse,
    BookingChecklistItemUpdate,
    BookingPartCreate,
    BookingPartResponse,
    ChecklistTemplateResponse,
    DisputeCreateRequest,
    DisputeResolveRequest,
    ServiceCompletionRequest,
    ServiceReportResponse,
    StructuredInspectionCreate,
    StructuredInspectionResponse,
)
from app.services.booking_state_machine import BookingStateMachine
from app.services.notification_service import NotificationService
from app.services.payment_service import PaymentService
from app.services.pricing_engine import PricingEngine

logger = get_logger("services.service_operations")


class ServiceOperationsService:
    """Coordinates lifecycle transitions, inspections, checklists, parts, and completion."""

    def __init__(self, client=None, notif_service: NotificationService | None = None):
        self.client = client or get_supabase_service_client()
        self.notif_service = notif_service or NotificationService()
        self.payment_service = PaymentService()

    # ==========================================================================
    # Helper: Resolve Mechanic Identity & Verify Assignment
    # ==========================================================================

    def _resolve_mechanic_assignment(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        require_accepted: bool = True,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        """
        Verify that authenticated mechanic user has a valid assignment for the booking.
        Returns: (booking, mechanic_profile, mechanic_assignment)
        """
        # 1. Fetch booking
        b_res = (
            self.client.table("bookings")
            .select("id, booking_number, customer_id, booking_status, subtotal, additional_charges, discount_amount, tax_amount, total_amount, price_snapshot")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        booking = b_res.data[0]

        # 2. Fetch mechanic profile
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, user_id, business_name")
            .eq("user_id", str(mechanic_user_id))
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic profile not found.")
        mechanic = m_res.data[0]
        mechanic_id = mechanic["id"]

        # 3. Fetch assignment
        asgn_query = (
            self.client.table("mechanic_assignments")
            .select("id, assignment_status")
            .eq("booking_id", str(booking_id))
            .eq("mechanic_id", str(mechanic_id))
        )
        if require_accepted:
            asgn_query = asgn_query.eq("assignment_status", "accepted")

        asgn_res = asgn_query.execute()
        if not asgn_res.data or len(asgn_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not hold an active assignment for this booking.",
            )

        return booking, mechanic, asgn_res.data[0]

    # ==========================================================================
    # 1. Arrival Workflow
    # ==========================================================================

    async def record_arrival(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
    ) -> ArrivalResponse:
        """
        Record authoritative mechanic arrival at the customer's vehicle location.
        Requires:
        - Authenticated mechanic holds accepted assignment.
        - Booking is currently in 'mechanic_en_route'.
        - Authoritative server timestamp recorded.
        """
        booking, mechanic, _ = self._resolve_mechanic_assignment(booking_id, mechanic_user_id)
        current_status = booking.get("booking_status")

        if current_status != BookingStatus.MECHANIC_EN_ROUTE.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record arrival when booking status is '{current_status}'. Expected 'mechanic_en_route'.",
            )

        now = datetime.now(timezone.utc)

        # Atomic transition to mechanic_arrived
        upd = (
            self.client.table("bookings")
            .update({"booking_status": BookingStatus.MECHANIC_ARRIVED.value})
            .eq("id", str(booking_id))
            .eq("booking_status", BookingStatus.MECHANIC_EN_ROUTE.value)
            .execute()
        )
        if not upd.data or len(upd.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking status was modified concurrently. Please refresh.",
            )

        # Record audit log
        try:
            record_audit_log(
                action="mechanic_arrived",
                entity_type="booking",
                entity_id=str(booking_id),
                actor_id=str(mechanic_user_id),
                actor_role="mechanic",
                old_data={"booking_status": BookingStatus.MECHANIC_EN_ROUTE.value},
                new_data={"booking_status": BookingStatus.MECHANIC_ARRIVED.value, "arrived_at": now.isoformat()},
            )
        except Exception as audit_err:
            logger.warning("arrival_audit_log_failed", error=str(audit_err))

        # Notify customer
        try:
            await self.notif_service.notify_booking_status_change(
                booking_id=booking_id,
                customer_id=uuid.UUID(str(booking["customer_id"])),
                new_status=BookingStatus.MECHANIC_ARRIVED.value,
                mechanic_user_id=mechanic_user_id,
                booking_number=booking.get("booking_number"),
            )
        except Exception as notif_err:
            logger.warning("arrival_notification_failed", error=str(notif_err))

        return ArrivalResponse(
            booking_id=booking_id,
            mechanic_id=uuid.UUID(str(mechanic["id"])),
            arrived_at=now,
            booking_status=BookingStatus.MECHANIC_ARRIVED.value,
            message="Mechanic arrival verified and recorded successfully.",
        )

    # ==========================================================================
    # 2. Structured Vehicle Inspection
    # ==========================================================================

    async def submit_structured_inspection(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: StructuredInspectionCreate,
    ) -> dict[str, Any]:
        """Submit comprehensive diagnostic inspection with structured checkpoints and evidence."""
        booking, mechanic, _ = self._resolve_mechanic_assignment(booking_id, mechanic_user_id)
        cur_status = booking.get("booking_status")

        if cur_status not in [BookingStatus.MECHANIC_ARRIVED.value, BookingStatus.INSPECTION.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit inspection for booking in '{cur_status}' status.",
            )

        # Validate evidence paths
        if payload.evidence_file_paths:
            validate_evidence_paths(
                payload.evidence_file_paths,
                expected_booking_id=booking_id,
                allowed_categories=["inspections"],
            )

        # Check existing inspection
        existing = (
            self.client.table("service_inspections")
            .select("id")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An inspection report has already been submitted for this booking.",
            )

        # Advance booking status
        # If additional services or costs are recommended, move towards awaiting customer approval
        next_status = (
            BookingStatus.AWAITING_CUSTOMER_APPROVAL.value
            if (payload.estimated_additional_cost > Decimal("0.00") or len(payload.recommended_services) > 0)
            else BookingStatus.INSPECTION.value
        )

        self.client.table("bookings").update(
            {"booking_status": next_status}
        ).eq("id", str(booking_id)).in_(
            "booking_status", [BookingStatus.MECHANIC_ARRIVED.value, BookingStatus.INSPECTION.value]
        ).execute()

        # Insert structured inspection
        insert_payload = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic["id"]),
            "findings": payload.findings,
            "vehicle_condition": payload.vehicle_condition,
            "odometer_reading": payload.odometer_reading,
            "checklist_results": payload.checklist_results or {},
            "diagnostic_findings": [d.model_dump() for d in payload.diagnostic_findings],
            "recommended_services": [r.model_dump(mode="json") for r in payload.recommended_services],
            "parts_required": payload.parts_required or [],
            "labor_requirements": payload.labor_requirements,
            "estimated_additional_cost": str(payload.estimated_additional_cost),
            "evidence_file_paths": payload.evidence_file_paths or [],
        }

        res = self.client.table("service_inspections").insert(insert_payload).execute()
        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record structured inspection.",
            )

        created = res.data[0]

        # Audit log
        try:
            record_audit_log(
                action="inspection_submitted",
                entity_type="inspection",
                entity_id=str(created["id"]),
                actor_id=str(mechanic_user_id),
                actor_role="mechanic",
                new_data={"booking_id": str(booking_id), "next_status": next_status},
            )
        except Exception:
            pass

        return created

    async def get_structured_inspection(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """Fetch structured inspection with strict customer ownership and mechanic assignment check."""
        role = user_role.lower()

        # Fetch booking
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        booking = b_res.data[0]

        if role == "customer" and str(booking["customer_id"]) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        elif role == "mechanic":
            self._resolve_mechanic_assignment(booking_id, user_id, require_accepted=False)
        elif role not in ["admin", "support", "customer"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        ins_res = (
            self.client.table("service_inspections")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not ins_res.data or len(ins_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No inspection report found for this booking.")

        inspection = ins_res.data[0]
        return inspection

    # ==========================================================================
    # 3. Service Checklist Management
    # ==========================================================================

    async def get_or_initialize_booking_checklist(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> list[dict[str, Any]]:
        """
        Retrieve checklist items for a booking.
        If no checklist items exist yet, seeds them from standard templates matching booking services.
        """
        # 1. Fetch existing checklist items
        existing = (
            self.client.table("booking_checklist_items")
            .select("*")
            .eq("booking_id", str(booking_id))
            .order("created_at")
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            return existing.data

        # 2. Determine service categories from booking items
        items_res = (
            self.client.table("booking_items")
            .select("service_id, services(category_id, service_categories(slug))")
            .eq("booking_id", str(booking_id))
            .execute()
        )

        category_slugs: set[str] = {"general"}  # Always include general multi-point check
        for row in items_res.data or []:
            svc = row.get("services")
            if isinstance(svc, dict):
                sc = svc.get("service_categories")
                if isinstance(sc, dict) and sc.get("slug"):
                    category_slugs.add(sc["slug"].lower())

        # Map broad categories
        matching_slugs: list[str] = []
        for slug in category_slugs:
            if "brake" in slug:
                matching_slugs.append("brakes")
            elif "battery" in slug:
                matching_slugs.append("battery")
            elif "oil" in slug or "engine" in slug:
                matching_slugs.append("engine")
            elif "tire" in slug or "wheel" in slug:
                matching_slugs.append("tires")
            else:
                matching_slugs.append("general")

        matching_slugs = list(set(matching_slugs))

        # 3. Query templates
        templates_res = (
            self.client.table("service_checklist_templates")
            .select("*")
            .in_("category_slug", matching_slugs)
            .order("display_order")
            .execute()
        )

        templates = templates_res.data or []
        if not templates:
            # Fallback to general
            templates_res = (
                self.client.table("service_checklist_templates")
                .select("*")
                .eq("category_slug", "general")
                .execute()
            )
            templates = templates_res.data or []

        # 4. Insert booking checklist items
        to_insert = [
            {
                "booking_id": str(booking_id),
                "item_key": t["item_key"],
                "title": t["title"],
                "category_slug": t["category_slug"],
                "is_mandatory": t.get("is_mandatory", True),
                "is_completed": False,
                "notes": None,
            }
            for t in templates
        ]

        if to_insert:
            try:
                self.client.table("booking_checklist_items").insert(to_insert).execute()
            except Exception as ins_err:
                logger.warning("checklist_seed_insert_conflict", error=str(ins_err))

        # Re-query
        re_query = (
            self.client.table("booking_checklist_items")
            .select("*")
            .eq("booking_id", str(booking_id))
            .order("created_at")
            .execute()
        )
        return re_query.data or []

    async def update_checklist_item(
        self,
        booking_id: uuid.UUID,
        item_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: BookingChecklistItemUpdate,
    ) -> dict[str, Any]:
        """Update completion status of a checklist task."""
        _, mechanic, _ = self._resolve_mechanic_assignment(booking_id, mechanic_user_id)

        now_iso = datetime.now(timezone.utc).isoformat() if payload.is_completed else None

        upd = (
            self.client.table("booking_checklist_items")
            .update({
                "is_completed": payload.is_completed,
                "completed_at": now_iso,
                "notes": payload.notes,
                "completed_by": str(mechanic_user_id) if payload.is_completed else None,
            })
            .eq("id", str(item_id))
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not upd.data or len(upd.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Checklist task not found.")

        return upd.data[0]

    # ==========================================================================
    # 4. Parts Tracking
    # ==========================================================================

    async def add_booking_part(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: BookingPartCreate,
    ) -> dict[str, Any]:
        """Record replacement part installed during service."""
        booking, _, _ = self._resolve_mechanic_assignment(booking_id, mechanic_user_id)
        cur_status = booking.get("booking_status")

        if cur_status not in [
            BookingStatus.INSPECTION.value,
            BookingStatus.SERVICE_IN_PROGRESS.value,
            BookingStatus.ADDITIONAL_WORK.value,
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot record parts when booking is in '{cur_status}' status.",
            )

        total_price = PricingEngine.round_currency(payload.unit_price * Decimal(payload.quantity))

        insert_payload = {
            "booking_id": str(booking_id),
            "part_name": payload.part_name,
            "part_number": payload.part_number,
            "description": payload.description,
            "quantity": payload.quantity,
            "unit_price": str(payload.unit_price),
            "total_price": str(total_price),
            "supplier": payload.supplier,
            "warranty_months": payload.warranty_months,
            "warranty_notes": payload.warranty_notes,
        }

        res = self.client.table("booking_parts").insert(insert_payload).execute()
        if not res.data or len(res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record service part.",
            )

        return res.data[0]

    async def list_booking_parts(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> list[dict[str, Any]]:
        """List all parts installed on a booking with RBAC checks."""
        role = user_role.lower()
        b_res = self.client.table("bookings").select("id, customer_id").eq("id", str(booking_id)).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

        booking = b_res.data[0]
        if role == "customer" and str(booking["customer_id"]) != str(user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        elif role not in ["customer", "mechanic", "admin", "support"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

        res = (
            self.client.table("booking_parts")
            .select("*")
            .eq("booking_id", str(booking_id))
            .order("created_at")
            .execute()
        )
        return res.data or []

    # ==========================================================================
    # 5. Customer Estimate Approval & Price Snapshot
    # ==========================================================================

    async def customer_approve_estimate(
        self,
        booking_id: uuid.UUID,
        customer_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Customer approves diagnostic findings & estimate, advancing booking to service_in_progress
        and freezing an immutable price snapshot.
        """
        b_res = (
            self.client.table("bookings")
            .select("*")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        booking = b_res.data[0]

        if str(booking["customer_id"]) != str(customer_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

        cur_status = booking.get("booking_status")
        if cur_status != BookingStatus.AWAITING_CUSTOMER_APPROVAL.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot approve estimate when booking is in '{cur_status}'. Expected 'awaiting_customer_approval'.",
            )

        # Calculate immutable price snapshot
        subtotal = Decimal(str(booking.get("subtotal") or "0.00"))
        additional = Decimal(str(booking.get("additional_charges") or "0.00"))
        discount = Decimal(str(booking.get("discount_amount") or "0.00"))

        snapshot = PricingEngine.create_price_snapshot(
            base_service_amount=subtotal,
            additional_work_total=additional,
            discount_amount=discount,
            approved_by=customer_user_id,
        )

        upd = (
            self.client.table("bookings")
            .update({
                "booking_status": BookingStatus.SERVICE_IN_PROGRESS.value,
                "price_snapshot": snapshot.model_dump(mode="json"),
            })
            .eq("id", str(booking_id))
            .eq("booking_status", BookingStatus.AWAITING_CUSTOMER_APPROVAL.value)
            .execute()
        )
        if not upd.data or len(upd.data) == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Concurrent approval detected. Please refresh.")

        # Record audit log
        try:
            record_audit_log(
                action="estimate_approved",
                entity_type="booking",
                entity_id=str(booking_id),
                actor_id=str(customer_user_id),
                actor_role="customer",
                new_data={"price_snapshot": snapshot.model_dump(mode="json")},
            )
        except Exception:
            pass

        return upd.data[0]

    # ==========================================================================
    # 6. Service Completion & Structured Service Report
    # ==========================================================================

    async def complete_service(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: ServiceCompletionRequest,
    ) -> ServiceReportResponse:
        """
        Mechanic explicitly finalizes service execution.
        Server-side validation gates:
        1. Authenticated mechanic holds accepted assignment.
        2. Booking is in 'service_in_progress'.
        3. All mandatory checklist items are marked complete (rejects 400 if any incomplete).
        4. No pending additional work requests exist.
        5. Generates/saves service_reports record.
        6. Ensures invoice is issued and synchronized with final totals.
        7. Advances booking to 'service_completed'.
        8. Notifies customer with invoice link.
        """
        booking, mechanic, _ = self._resolve_mechanic_assignment(booking_id, mechanic_user_id)
        cur_status = booking.get("booking_status")

        if cur_status != BookingStatus.SERVICE_IN_PROGRESS.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot complete service for booking in '{cur_status}' status. Expected 'service_in_progress'.",
            )

        # 1. Gate: Verify mandatory checklist items
        checklist_res = (
            self.client.table("booking_checklist_items")
            .select("item_key, title, is_mandatory, is_completed")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        items = checklist_res.data or []
        incomplete_mandatory = [
            it["title"] for it in items
            if it.get("is_mandatory", True) and not it.get("is_completed", False)
        ]
        if incomplete_mandatory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service completion blocked: Mandatory checklist items incomplete: {', '.join(incomplete_mandatory)}",
            )

        # 2. Gate: Verify no pending additional work requests
        pending_work = (
            self.client.table("additional_work_requests")
            .select("id, title")
            .eq("booking_id", str(booking_id))
            .eq("status", "pending")
            .execute()
        )
        if pending_work.data and len(pending_work.data) > 0:
            titles = [p["title"] for p in pending_work.data]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Service completion blocked: Unresolved additional work requests pending customer response: {', '.join(titles)}",
            )

        # 3. Validate completion evidence paths if provided
        if payload.completion_evidence_paths:
            validate_evidence_paths(
                payload.completion_evidence_paths,
                expected_booking_id=booking_id,
                allowed_categories=["completion", "after_service"],
            )

        # 4. Fetch parts used
        parts_res = (
            self.client.table("booking_parts")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        parts_list = parts_res.data or []

        # 5. Insert or update service_reports
        now = datetime.now(timezone.utc)
        final_totals = {
            "subtotal": booking.get("subtotal"),
            "additional_charges": booking.get("additional_charges"),
            "discount_amount": booking.get("discount_amount"),
            "tax_amount": booking.get("tax_amount"),
            "total_amount": booking.get("total_amount"),
        }

        report_payload = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic["id"]),
            "summary": payload.summary,
            "work_performed": payload.work_performed,
            "recommendations": payload.recommendations,
            "customer_notes": payload.customer_notes,
            "report_file_path": payload.completion_evidence_paths[0] if payload.completion_evidence_paths else None,
            "parts_used": parts_list,
            "checklist_summary": {it["item_key"]: it["is_completed"] for it in items},
            "labor_summary": f"Completed by {mechanic.get('business_name', 'Certified Technician')}",
            "final_totals": final_totals,
            "completed_at": now.isoformat(),
        }

        # Check existing report
        existing_report = (
            self.client.table("service_reports")
            .select("id")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if existing_report.data and len(existing_report.data) > 0:
            rep_res = (
                self.client.table("service_reports")
                .update(report_payload)
                .eq("booking_id", str(booking_id))
                .execute()
            )
        else:
            rep_res = self.client.table("service_reports").insert(report_payload).execute()

        if not rep_res.data or len(rep_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save service report.",
            )

        created_report = rep_res.data[0]

        # 6. Ensure invoice is issued based on authoritative booking totals
        try:
            await self.payment_service._ensure_invoice_issued(
                booking=booking,
                customer_user_id=uuid.UUID(str(booking["customer_id"])),
            )
        except Exception as inv_err:
            logger.warning("invoice_generation_during_completion_failed", error=str(inv_err))

        # 7. Transition booking status: service_in_progress -> service_completed
        upd = (
            self.client.table("bookings")
            .update({"booking_status": BookingStatus.SERVICE_COMPLETED.value})
            .eq("id", str(booking_id))
            .eq("booking_status", BookingStatus.SERVICE_IN_PROGRESS.value)
            .execute()
        )
        if not upd.data or len(upd.data) == 0:
            logger.warning("service_completed_status_update_conflict", booking_id=str(booking_id))

        # 8. Record audit log
        try:
            record_audit_log(
                action="service_completed",
                entity_type="service_report",
                entity_id=str(created_report["id"]),
                actor_id=str(mechanic_user_id),
                actor_role="mechanic",
                new_data={"booking_id": str(booking_id), "completed_at": now.isoformat()},
            )
        except Exception:
            pass

        # 9. Notify customer
        try:
            await self.notif_service.notify_booking_status_change(
                booking_id=booking_id,
                customer_id=uuid.UUID(str(booking["customer_id"])),
                new_status=BookingStatus.SERVICE_COMPLETED.value,
                mechanic_user_id=mechanic_user_id,
                booking_number=booking.get("booking_number"),
            )
        except Exception:
            pass

        return ServiceReportResponse.model_validate(created_report)

    # ==========================================================================
    # 7. Dispute Management
    # ==========================================================================

    async def raise_dispute(
        self,
        booking_id: uuid.UUID,
        customer_user_id: uuid.UUID,
        payload: DisputeCreateRequest,
    ) -> dict[str, Any]:
        """Customer raises formal dispute on a completed or paid booking."""
        b_res = self.client.table("bookings").select("*").eq("id", str(booking_id)).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        booking = b_res.data[0]

        if str(booking["customer_id"]) != str(customer_user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

        cur_status = booking.get("booking_status")
        if cur_status not in [BookingStatus.SERVICE_COMPLETED.value, BookingStatus.PAYMENT_PENDING.value, BookingStatus.PAID.value]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Disputes can only be raised for completed or paid bookings (current status: '{cur_status}').",
            )

        if payload.evidence_paths:
            validate_evidence_paths(
                payload.evidence_paths,
                expected_booking_id=booking_id,
                allowed_categories=["disputes"],
            )

        upd = (
            self.client.table("bookings")
            .update({"booking_status": BookingStatus.DISPUTED.value})
            .eq("id", str(booking_id))
            .execute()
        )

        try:
            record_audit_log(
                action="dispute_raised",
                entity_type="booking",
                entity_id=str(booking_id),
                actor_id=str(customer_user_id),
                actor_role="customer",
                new_data={"reason": payload.reason, "evidence_paths": payload.evidence_paths},
            )
        except Exception:
            pass

        return {"booking_id": booking_id, "booking_status": BookingStatus.DISPUTED.value, "reason": payload.reason}

    async def resolve_dispute(
        self,
        booking_id: uuid.UUID,
        admin_user_id: uuid.UUID,
        payload: DisputeResolveRequest,
    ) -> dict[str, Any]:
        """Admin/Support resolves an active dispute."""
        b_res = self.client.table("bookings").select("*").eq("id", str(booking_id)).execute()
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")
        booking = b_res.data[0]

        if booking.get("booking_status") != BookingStatus.DISPUTED.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Booking is not in disputed status (current status: '{booking.get('booking_status')}').",
            )

        upd = (
            self.client.table("bookings")
            .update({"booking_status": payload.resolution_status})
            .eq("id", str(booking_id))
            .execute()
        )

        try:
            record_audit_log(
                action="dispute_resolved",
                entity_type="booking",
                entity_id=str(booking_id),
                actor_id=str(admin_user_id),
                actor_role="admin",
                new_data={
                    "resolution_status": payload.resolution_status,
                    "resolution_notes": payload.resolution_notes,
                },
            )
        except Exception:
            pass

        return {
            "booking_id": booking_id,
            "booking_status": payload.resolution_status,
            "resolution_notes": payload.resolution_notes,
        }
