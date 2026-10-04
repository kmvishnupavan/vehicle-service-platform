"""
Inspection Service Layer (Phase 7A).

Coordinates mechanic vehicle inspection reports, RBAC, lifecycle progression,
evidence path validation, and persistence.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.evidence import validate_evidence_paths
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.booking import BookingStatus
from app.schemas.inspection import InspectionCreate, InspectionUpdate
from app.services.booking_state_machine import BookingStateMachine

logger = get_logger("services.inspection")


class InspectionService:
    """Encapsulates inspection domain logic, lifecycle guards, and database queries."""

    def __init__(self):
        self.client = get_supabase_service_client()

    async def create_inspection(
        self,
        booking_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        payload: InspectionCreate,
    ) -> dict[str, Any]:
        """
        Mechanic submits inspection report for a booking.

        Rules:
        1. Authenticated mechanic required.
        2. Mechanic must have an ACCEPTED assignment for this booking.
        3. Mechanic ID matches accepted assignment.
        4. Booking lifecycle permits inspection submission (mechanic_arrived or inspection).
        5. Findings non-empty, estimated_additional_cost >= 0.
        6. Never trust mechanic_id from request body; derived from authenticated user.
        7. Evidence paths validated to belong to booking.
        8. Conflict (409) if inspection already exists for this booking.
        9. Does NOT modify booking financial totals.
        """
        # 1. Resolve mechanic profile for authenticated user
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

        # 2. Retrieve booking record
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

        # 3. Verify booking lifecycle permits inspection submission
        if cur_status not in ["mechanic_arrived", "inspection"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit inspection for booking with status '{cur_status}'.",
            )

        # 4. Verify mechanic has an ACCEPTED assignment for this booking
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

        # 5. Check if inspection already exists for this booking
        existing_res = (
            self.client.table("service_inspections")
            .select("id")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if existing_res.data and len(existing_res.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An inspection report already exists for this booking.",
            )

        # 6. Validate evidence file paths if provided
        if payload.evidence_file_paths:
            validate_evidence_paths(
                payload.evidence_file_paths,
                expected_booking_id=booking_id,
                allowed_categories=["inspections"],
            )

        # 7. Advance booking to 'inspection' status if currently 'mechanic_arrived'
        if cur_status == "mechanic_arrived":
            self.client.table("bookings").update(
                {"booking_status": BookingStatus.INSPECTION.value}
            ).eq("id", str(booking_id)).eq("booking_status", "mechanic_arrived").execute()

        # 8. Insert into service_inspections
        insert_data = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic_profile_id),
            "findings": payload.findings.strip(),
            "vehicle_condition": payload.vehicle_condition.strip() if payload.vehicle_condition else None,
            "estimated_additional_cost": str(payload.estimated_additional_cost),
        }

        try:
            ins_res = self.client.table("service_inspections").insert(insert_data).execute()
        except Exception as exc:
            logger.error("failed_to_insert_service_inspection", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save inspection report.",
            )

        if not ins_res.data or len(ins_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save inspection report.",
            )

        created_inspection = ins_res.data[0]
        created_inspection["evidence_file_paths"] = payload.evidence_file_paths or []

        logger.info(
            "inspection_created_successfully",
            inspection_id=created_inspection["id"],
            booking_id=str(booking_id),
            mechanic_id=str(mechanic_profile_id),
            estimated_cost=str(payload.estimated_additional_cost),
        )

        return created_inspection

    async def get_inspection(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """
        Retrieve inspection for a booking.
        Authorized for: booking customer owner, assigned mechanic, admin/support.
        Returns 404 for unauthorized customer to prevent resource enumeration.
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

        # 2. Role-based authorization
        if role == "customer":
            if str(booking.get("customer_id")) != str(user_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Booking not found.",
                )
        elif role == "mechanic":
            # Verify mechanic has accepted assignment for this booking
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

        # 3. Retrieve inspection
        insp_res = (
            self.client.table("service_inspections")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not insp_res.data or len(insp_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection report not found for this booking.",
            )

        inspection = insp_res.data[0]
        if "evidence_file_paths" not in inspection:
            inspection["evidence_file_paths"] = []
        return inspection

    async def update_inspection(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
        payload: InspectionUpdate,
    ) -> dict[str, Any]:
        """
        Update an existing inspection report.
        Strictly restricted to assigned mechanic or admin/support.
        Prevents altering booking_id or mechanic_id.
        """
        role = user_role.lower()

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

        # 2. Retrieve existing inspection
        insp_res = (
            self.client.table("service_inspections")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not insp_res.data or len(insp_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Inspection report not found.",
            )
        inspection = insp_res.data[0]
        inspection_id = inspection["id"]

        # 3. RBAC authorization
        if role == "customer":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customers are not permitted to modify inspection reports.",
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
            if str(inspection["mechanic_id"]) != str(mechanic_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only edit inspection reports you created.",
                )
        elif role not in ["admin", "support"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied.",
            )

        # 4. Validate evidence paths if provided
        if payload.evidence_file_paths is not None:
            validate_evidence_paths(
                payload.evidence_file_paths,
                expected_booking_id=booking_id,
                allowed_categories=["inspections"],
            )

        # 5. Build update payload (strictly excludes booking_id, mechanic_id)
        update_fields: dict[str, Any] = {}
        if payload.findings is not None:
            update_fields["findings"] = payload.findings.strip()
        if payload.vehicle_condition is not None:
            update_fields["vehicle_condition"] = payload.vehicle_condition.strip()
        if payload.estimated_additional_cost is not None:
            update_fields["estimated_additional_cost"] = str(payload.estimated_additional_cost)

        if not update_fields:
            # No changes to DB columns
            inspection["evidence_file_paths"] = payload.evidence_file_paths or []
            return inspection

        # 6. Execute update on service_inspections
        upd_res = (
            self.client.table("service_inspections")
            .update(update_fields)
            .eq("id", str(inspection_id))
            .execute()
        )
        if not upd_res.data or len(upd_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update inspection report.",
            )

        updated_record = upd_res.data[0]
        updated_record["evidence_file_paths"] = payload.evidence_file_paths or []
        return updated_record
