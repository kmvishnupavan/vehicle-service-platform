"""
Mechanic Domain and Discovery Service.

Authoritative coordinator for:
1. PostGIS-based geographic proximity discovery of verified and available mechanics.
2. Mechanic assignment lifecycle transitions (offered -> accepted / rejected / cancelled).
3. Concurrency protection against double assignment.
4. Booking lifecycle progression (pending -> searching_mechanic -> mechanic_assigned).
5. Safe profile projection ensuring mechanic phone and personal data remain private.

Distance Model Note:
Distances returned are geodesic/straight-line geographic distances calculated via PostGIS ST_Distance.
Road routing distance, road turn-by-turn ETA, and live traffic-aware routing are deferred to a future phase.
"""

from datetime import datetime, timezone
from decimal import Decimal
import math
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.booking import BookingStatus
from app.schemas.mechanic import NearbyMechanicResponse
from app.services.booking_state_machine import BookingStateMachine
from app.services.location_reliability_service import LocationReliabilityService
from app.services.realtime_location_service import RealtimeLocationService

logger = get_logger("services.mechanic")
settings = get_settings()


def calculate_geodesic_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> Decimal:
    """Calculate straight-line geodesic distance on Earth spheroidal surface (in km)."""
    r_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return Decimal(str(round(r_km * c, 2)))


class MechanicService:
    """Encapsulates mechanic domain operations, PostGIS discovery, and assignment lifecycle."""

    def __init__(self, realtime_service: RealtimeLocationService | None = None):
        self.client = get_supabase_service_client()
        self.realtime_service = realtime_service or RealtimeLocationService()

    # ==========================================================================
    # 1. Nearby Mechanic Discovery
    # ==========================================================================

    async def find_nearby_mechanics_for_booking(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "customer",
        max_distance_km: float = 20.0,
    ) -> list[NearbyMechanicResponse]:
        """
        Discover eligible nearby mechanics using trusted coordinates from an existing booking.

        Security & Validation:
        - Customer must own the booking (404 returned if inaccessible to avoid leaking existence).
        - Booking must exist and not be cancelled/completed.
        - Uses booking's trusted requested_latitude and requested_longitude.
        - Automatically transitions booking from 'pending' to 'searching_mechanic'.
        - Excludes mechanics currently engaged in active accepted assignments.
        - Filters out unavailable or unverified mechanics.
        - Returns safe fields: NO phone, NO email, NO private documents.
        """
        # 1. Fetch booking with ownership check
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id, requested_latitude, requested_longitude, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        booking = b_res.data[0]

        # Ownership enforcement: Customers can only search for their own bookings
        if user_role == "customer" and str(booking["customer_id"]) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # Check booking status eligibility
        if booking["booking_status"] in ["cancelled", "service_completed", "paid"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot search for mechanics on booking with status '{booking['booking_status']}'.",
            )

        # 2. Advance booking state to 'searching_mechanic' if currently 'pending'
        if booking["booking_status"] == "pending":
            try:
                self.client.table("bookings").update(
                    {"booking_status": "searching_mechanic"}
                ).eq("id", str(booking_id)).execute()
            except Exception as exc:
                logger.error("failed_to_update_booking_to_searching", error=str(exc))

        # 3. Trusted coordinates from verified booking address
        cust_lat = float(booking["requested_latitude"])
        cust_lng = float(booking["requested_longitude"])

        # 4. Invoke PostGIS RPC find_nearby_mechanics
        try:
            rpc_res = self.client.rpc(
                "find_nearby_mechanics",
                {
                    "cust_lat": cust_lat,
                    "cust_lng": cust_lng,
                    "max_distance_km": max_distance_km,
                },
            ).execute()
            raw_mechanics = rpc_res.data or []
        except Exception as exc:
            logger.error("find_nearby_mechanics_rpc_failed", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to discover nearby mechanics due to internal error.",
            )

        if not raw_mechanics:
            return []

        # 5. Check for currently busy mechanics (actively accepted assignment)
        try:
            busy_res = (
                self.client.table("mechanic_assignments")
                .select("mechanic_id")
                .eq("assignment_status", "accepted")
                .execute()
            )
            busy_ids = {row["mechanic_id"] for row in (busy_res.data or [])}
        except Exception as exc:
            logger.warning("busy_mechanics_lookup_failed", error=str(exc))
            busy_ids = set()

        # 6. Format safe response objects
        results: list[NearbyMechanicResponse] = []
        for m in raw_mechanics:
            m_id = str(m["mechanic_id"])
            if m_id in busy_ids:
                continue

            results.append(
                NearbyMechanicResponse(
                    mechanic_id=uuid.UUID(m_id),
                    user_id=uuid.UUID(str(m["user_id"])),
                    full_name=m["full_name"],
                    avatar_url=m.get("avatar_url"),
                    business_name=m.get("business_name"),
                    experience_years=int(m.get("experience_years") or 0),
                    average_rating=Decimal(str(m.get("average_rating") or "0.00")),
                    distance_km=Decimal(str(m["distance_km"])),
                    service_radius_km=Decimal(str(m["service_radius_km"])),
                )
            )

        return results

    # ==========================================================================
    # 2. Assignment Management
    # ==========================================================================

    async def offer_assignment(
        self,
        booking_id: uuid.UUID,
        mechanic_id: uuid.UUID,
        estimated_arrival_minutes: int | None = None,
    ) -> dict[str, Any]:
        """
        Offer a service booking to a specific verified and available mechanic.
        """
        # 1. Verify booking is in valid state
        b_res = (
            self.client.table("bookings")
            .select("id, customer_id, requested_latitude, requested_longitude, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]

        if booking["booking_status"] not in ["pending", "searching_mechanic"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot offer assignment for booking with status '{booking['booking_status']}'.",
            )

        # 2. Verify mechanic profile
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, is_available, verification_status, service_radius_km, current_latitude, current_longitude")
            .eq("id", str(mechanic_id))
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found.",
            )
        mech = m_res.data[0]

        if not mech.get("is_available"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mechanic is currently unavailable for dispatch.",
            )

        if mech.get("verification_status") != "verified":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mechanic account is not verified.",
            )

        # 3. Calculate distance if mechanic location is known
        distance_km = None
        if mech.get("current_latitude") and mech.get("current_longitude"):
            distance_km = calculate_geodesic_distance_km(
                float(booking["requested_latitude"]),
                float(booking["requested_longitude"]),
                float(mech["current_latitude"]),
                float(mech["current_longitude"]),
            )
            # Enforce mechanic's operating radius
            if distance_km > Decimal(str(mech["service_radius_km"])):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Booking location ({distance_km} km) exceeds mechanic service radius ({mech['service_radius_km']} km).",
                )

        # 4. Check for existing active assignment for this booking and mechanic
        existing = (
            self.client.table("mechanic_assignments")
            .select("id, assignment_status")
            .eq("booking_id", str(booking_id))
            .eq("mechanic_id", str(mechanic_id))
            .in_("assignment_status", ["offered", "accepted"])
            .execute()
        )
        if existing.data and len(existing.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignment already exists in '{existing.data[0]['assignment_status']}' status.",
            )

        # 5. Insert mechanic_assignments record
        assignment_payload = {
            "booking_id": str(booking_id),
            "mechanic_id": str(mechanic_id),
            "assignment_status": "offered",
            "distance_km": str(distance_km) if distance_km is not None else None,
            "estimated_arrival_minutes": estimated_arrival_minutes,
        }

        try:
            ins_res = self.client.table("mechanic_assignments").insert(assignment_payload).execute()
        except Exception as exc:
            logger.error("failed_to_create_mechanic_assignment", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to dispatch mechanic assignment offer.",
            )

        if not ins_res.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record mechanic assignment offer.",
            )

        # 6. Ensure booking is in 'searching_mechanic' status
        if booking["booking_status"] == "pending":
            self.client.table("bookings").update(
                {"booking_status": "searching_mechanic"}
            ).eq("id", str(booking_id)).execute()

        return ins_res.data[0]

    async def accept_assignment(
        self,
        assignment_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
    ) -> dict[str, Any]:
        """
        Mechanic accepts an offered assignment.

        Concurrency & State Rules:
        - Resolves mechanic profile from authenticated user_id.
        - Verifies assignment was dispatched to this mechanic.
        - Verifies assignment is in 'offered' status.
        - Checks that another mechanic has not already accepted the booking.
        - Transitions assignment to 'accepted'.
        - Advances booking status to 'mechanic_assigned'.
        - Automatically creates chat room via database trigger trg_create_chat_room_on_assignment.
        - Cancels any other outstanding offered assignments for the same booking.
        - Notifies the customer.
        """
        # 0. Attempt atomic PostgreSQL RPC execution first
        # Guarantees atomic row-level locking (FOR UPDATE) and enforcement of the partial unique index
        try:
            rpc_res = self.client.rpc(
                "accept_mechanic_assignment",
                {
                    "p_assignment_id": str(assignment_id),
                    "p_mechanic_user_id": str(mechanic_user_id),
                },
            ).execute()
            if rpc_res and isinstance(rpc_res.data, dict) and "success" in rpc_res.data:
                res_data = rpc_res.data
                if res_data.get("success"):
                    logger.info(
                        "assignment_accepted_via_atomic_rpc",
                        assignment_id=str(assignment_id),
                        mechanic_user_id=str(mechanic_user_id),
                    )
                    return res_data.get("assignment")

                err_code = res_data.get("error_code")
                msg = res_data.get("message", "Assignment acceptance failed.")
                if err_code == "BOOKING_ALREADY_ASSIGNED":
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Booking has already been assigned to another mechanic.",
                    )
                elif err_code == "FORBIDDEN":
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=msg,
                    )
                elif err_code in ["ASSIGNMENT_NOT_FOUND", "MECHANIC_PROFILE_NOT_FOUND", "BOOKING_NOT_FOUND"]:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=msg,
                    )
                elif err_code == "INVALID_ASSIGNMENT_STATUS":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=msg,
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=msg,
                    )
        except HTTPException:
            raise
        except Exception as rpc_exc:
            logger.debug("atomic_rpc_not_mocked_falling_back_to_application_layer", error=str(rpc_exc))

        # 1. Resolve mechanic profile (fallback)
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
        mechanic_id = m_res.data[0]["id"]

        # 2. Retrieve assignment
        a_res = (
            self.client.table("mechanic_assignments")
            .select("*, bookings(*)")
            .eq("id", str(assignment_id))
            .execute()
        )
        if not a_res.data or len(a_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found.",
            )
        assignment = a_res.data[0]

        # 3. Verify assignment ownership
        if str(assignment["mechanic_id"]) != str(mechanic_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only accept assignments offered to your profile.",
            )

        # 4. Verify status is 'offered'
        if assignment["assignment_status"] != "offered":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot accept assignment in '{assignment['assignment_status']}' status.",
            )

        booking_id = assignment["booking_id"]
        booking = assignment.get("bookings") or {}

        # 5. Verify booking is still open for assignment via BookingStateMachine
        is_valid, error_msg = BookingStateMachine.validate_transition(
            current_status=booking.get("booking_status", "pending"),
            new_status=BookingStatus.MECHANIC_ASSIGNED,
            actor_role="mechanic",
            is_customer_owner=False,
            is_assigned_mechanic=True,
        )
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Booking is no longer available for assignment (current status: {booking.get('booking_status')}).",
            )

        # 6. Concurrency check: Ensure no other mechanic has already accepted this booking
        existing_accepted = (
            self.client.table("mechanic_assignments")
            .select("id")
            .eq("booking_id", str(booking_id))
            .eq("assignment_status", "accepted")
            .execute()
        )
        if existing_accepted.data and len(existing_accepted.data) > 0:
            # Another mechanic won the race; cancel this stale offer
            self.client.table("mechanic_assignments").update(
                {"assignment_status": "cancelled"}
            ).eq("id", str(assignment_id)).execute()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Booking has already been accepted by another mechanic.",
            )

        # 7. Execute conditional update on mechanic_assignments
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            upd_res = (
                self.client.table("mechanic_assignments")
                .update({
                    "assignment_status": "accepted",
                    "responded_at": now_iso,
                    "assigned_at": now_iso,
                })
                .eq("id", str(assignment_id))
                .eq("assignment_status", "offered")
                .execute()
            )
            if not upd_res.data or len(upd_res.data) == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Assignment state was modified concurrently. Acceptance aborted.",
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.error("failed_to_accept_assignment", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to confirm assignment acceptance.",
            )

        accepted_assignment = upd_res.data[0]

        # 8. Advance booking status to 'mechanic_assigned'
        # DB trigger trg_track_booking_status will automatically log this in booking_status_history
        self.client.table("bookings").update(
            {"booking_status": "mechanic_assigned"}
        ).eq("id", str(booking_id)).execute()

        # 9. Cancel any other offered assignments for this booking
        try:
            self.client.table("mechanic_assignments").update(
                {"assignment_status": "cancelled"}
            ).eq("booking_id", str(booking_id)).neq("id", str(assignment_id)).eq("assignment_status", "offered").execute()
        except Exception as exc:
            logger.warning("failed_to_cancel_sibling_offers", error=str(exc))

        # 10. Record customer notification (Note: chat_rooms is created automatically by DB trigger)
        customer_id = booking.get("customer_id")
        if customer_id:
            try:
                self.client.table("notifications").insert({
                    "user_id": str(customer_id),
                    "type": "mechanic_assigned",
                    "title": "Mechanic Assigned",
                    "message": "A mechanic has accepted your booking and has been assigned.",
                    "data": {
                        "booking_id": str(booking_id),
                        "assignment_id": str(assignment_id),
                        "mechanic_id": str(mechanic_id),
                    },
                }).execute()
            except Exception as notify_exc:
                logger.warning("customer_assignment_notification_failed", error=str(notify_exc))

        logger.info(
            "assignment_accepted_successfully",
            assignment_id=str(assignment_id),
            booking_id=str(booking_id),
            mechanic_id=str(mechanic_id),
        )

        return accepted_assignment

    async def reject_assignment(
        self,
        assignment_id: uuid.UUID,
        mechanic_user_id: uuid.UUID,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """
        Mechanic rejects an offered assignment.
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
        mechanic_id = m_res.data[0]["id"]

        # 2. Retrieve assignment
        a_res = (
            self.client.table("mechanic_assignments")
            .select("*")
            .eq("id", str(assignment_id))
            .execute()
        )
        if not a_res.data or len(a_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found.",
            )
        assignment = a_res.data[0]

        # 3. Ownership check
        if str(assignment["mechanic_id"]) != str(mechanic_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only reject assignments offered to your profile.",
            )

        # 4. Status check
        if assignment["assignment_status"] != "offered":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reject assignment in '{assignment['assignment_status']}' status.",
            )

        # 5. Update assignment to rejected
        now_iso = datetime.now(timezone.utc).isoformat()
        upd_res = (
            self.client.table("mechanic_assignments")
            .update({
                "assignment_status": "rejected",
                "responded_at": now_iso,
                "rejected_reason": reason,
            })
            .eq("id", str(assignment_id))
            .execute()
        )

        return upd_res.data[0]

    async def get_assignment_by_id(
        self,
        assignment_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """Fetch assignment details with strict RBAC and ownership verification."""
        response = (
            self.client.table("mechanic_assignments")
            .select("*, bookings(customer_id)")
            .eq("id", str(assignment_id))
            .execute()
        )
        if not response.data or len(response.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found.",
            )
        assignment = response.data[0]

        # Access check
        if user_role == "customer":
            booking = assignment.get("bookings") or {}
            if str(booking.get("customer_id")) != str(user_id):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignment not found.",
                )
        elif user_role == "mechanic":
            # Check if mechanic_id belongs to user
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if not m_res.data or str(assignment["mechanic_id"]) != str(m_res.data[0]["id"]):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignment not found.",
                )

        return assignment

    async def get_mechanic_by_id(self, mechanic_id: uuid.UUID) -> dict[str, Any] | None:
        """Fetch public mechanic profile without disclosing personal phone or email."""
        response = (
            self.client.table("mechanic_profiles")
            .select("id, user_id, business_name, experience_years, bio, verification_status, is_available, service_radius_km, average_rating, total_completed_jobs, profiles!user_id(full_name, avatar_url)")
            .eq("id", str(mechanic_id))
            .execute()
        )
        if response.data and len(response.data) > 0:
            row = response.data[0]
            profile_data = row.pop("profiles", None) or {}
            row["full_name"] = profile_data.get("full_name")
            row["avatar_url"] = profile_data.get("avatar_url")
            try:
                cnt_res = (
                    self.client.table("reviews")
                    .select("id", count="exact")
                    .eq("mechanic_id", str(mechanic_id))
                    .execute()
                )
                row["review_count"] = cnt_res.count if cnt_res.count is not None else 0
            except Exception:
                row["review_count"] = 0
            return row
        return None

    # ==========================================================================
    # 3. Realtime Location Tracking
    # ==========================================================================

    async def update_mechanic_location(
        self,
        user_id: uuid.UUID,
        latitude: Decimal,
        longitude: Decimal,
        accuracy_meters: Decimal | None = None,
        sequence: int | None = None,
    ) -> dict[str, Any]:
        """
        Record a live mechanic GPS location ping.

        Updates both:
        1. mechanic_profiles: current_latitude, current_longitude, current_location_updated_at (for fast spatial discovery).
        2. mechanic_locations: Historical append-only record (persisted subject to 5s throttling).
        3. Realtime Broadcast: Ephemeral live broadcast to active booking channels (topic: booking-location:{booking_id}).
        """
        # 1. Resolve mechanic profile for authenticated user
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, verification_status, is_available, current_latitude, current_longitude, current_location_updated_at")
            .eq("user_id", str(user_id))
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found for authenticated user.",
            )
        mech = m_res.data[0]
        mechanic_id = mech["id"]

        if mech.get("verification_status") != "verified":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Mechanic account is not verified. Location broadcasting is disabled.",
            )

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Phase 13: Validate location quality and detect GPS anomalies
        try:
            reliability_svc = LocationReliabilityService(client=self.client)
            await reliability_svc.validate_and_record_ping(
                mechanic_id=uuid.UUID(str(mechanic_id)),
                latitude=float(latitude),
                longitude=float(longitude),
                accuracy_meters=float(accuracy_meters) if accuracy_meters is not None else None,
            )
        except Exception as anomaly_exc:
            logger.warning("location_anomaly_check_error", error=str(anomaly_exc))

        # Helper to broadcast to active accepted booking channels (isolated, non-blocking)
        async def _dispatch_broadcasts():
            try:
                asgn_res = (
                    self.client.table("mechanic_assignments")
                    .select("booking_id, bookings(id, booking_status)")
                    .eq("mechanic_id", str(mechanic_id))
                    .eq("assignment_status", "accepted")
                    .execute()
                )
                if asgn_res.data:
                    active_statuses = {
                        "mechanic_assigned",
                        "mechanic_en_route",
                        "mechanic_arrived",
                        "inspection",
                        "awaiting_customer_approval",
                        "service_in_progress",
                        "additional_work",
                    }
                    for asgn in asgn_res.data:
                        bk_id = asgn.get("booking_id")
                        bk_info = asgn.get("bookings") or {}
                        bk_status = bk_info.get("booking_status")
                        if bk_id and bk_status in active_statuses:
                            await self.realtime_service.broadcast_mechanic_location(
                                booking_id=uuid.UUID(str(bk_id)),
                                mechanic_id=uuid.UUID(str(mechanic_id)),
                                latitude=latitude,
                                longitude=longitude,
                                accuracy_meters=accuracy_meters,
                                recorded_at=now_iso,
                                sequence=sequence,
                            )
            except Exception as bcast_err:
                logger.warning(
                    "realtime_location_broadcast_error",
                    mechanic_id=str(mechanic_id),
                    error=str(bcast_err),
                )

        # Check update throttling against minimum interval
        last_updated_str = mech.get("current_location_updated_at")
        min_interval = settings.MECHANIC_LOCATION_MIN_INTERVAL_SECONDS
        if last_updated_str:
            try:
                last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
                elapsed = (now - last_updated).total_seconds()
                if elapsed < min_interval:
                    logger.info(
                        "mechanic_location_update_throttled",
                        mechanic_id=mechanic_id,
                        elapsed_seconds=elapsed,
                        min_interval=min_interval,
                    )
                    # Update current snapshot on mechanic_profiles
                    try:
                        self.client.table("mechanic_profiles").update({
                            "current_latitude": str(latitude),
                            "current_longitude": str(longitude),
                            "current_location_updated_at": now_iso,
                        }).eq("id", str(mechanic_id)).execute()
                    except Exception as exc:
                        logger.error("failed_to_update_current_location_snapshot", error=str(exc))

                    # Dispatch ephemeral broadcast even when DB history write is throttled
                    await _dispatch_broadcasts()

                    # Return latest accepted location without inserting another history row
                    return {
                        "mechanic_id": uuid.UUID(mechanic_id),
                        "latitude": Decimal(str(mech.get("current_latitude") or latitude)),
                        "longitude": Decimal(str(mech.get("current_longitude") or longitude)),
                        "accuracy_meters": accuracy_meters,
                        "recorded_at": last_updated,
                    }
            except Exception as parse_err:
                logger.warning("last_location_timestamp_parse_error", error=str(parse_err))

        # 2. Update current snapshot on mechanic_profiles
        try:
            self.client.table("mechanic_profiles").update({
                "current_latitude": str(latitude),
                "current_longitude": str(longitude),
                "current_location_updated_at": now_iso,
            }).eq("id", str(mechanic_id)).execute()
        except Exception as exc:
            logger.error("failed_to_update_current_location_snapshot", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update mechanic location snapshot.",
            )

        # 3. Append to mechanic_locations history
        history_payload = {
            "mechanic_id": str(mechanic_id),
            "latitude": str(latitude),
            "longitude": str(longitude),
            "accuracy_meters": str(accuracy_meters) if accuracy_meters is not None else None,
            "recorded_at": now_iso,
        }

        try:
            loc_res = self.client.table("mechanic_locations").insert(history_payload).execute()
        except Exception as exc:
            logger.error("failed_to_insert_mechanic_location_history", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to record mechanic location ping.",
            )

        # Dispatch ephemeral live Realtime Broadcast
        await _dispatch_broadcasts()

        return {
            "mechanic_id": uuid.UUID(mechanic_id),
            "latitude": latitude,
            "longitude": longitude,
            "accuracy_meters": accuracy_meters,
            "recorded_at": now_iso,
        }

    async def get_mechanic_location_for_booking(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str = "customer",
    ) -> dict[str, Any]:
        """
        Customer retrieves the authoritative latest location of the mechanic assigned to their booking.

        Security & Validation:
        - Customer must own the booking (404 if inaccessible, preventing leakage).
        - Booking must have an accepted mechanic assignment (400 if no mechanic assigned yet).
        - Queries the latest location from mechanic_locations using (mechanic_id, recorded_at DESC) limit 1.
        - Falls back to mechanic_profiles current coordinates if history record not found.
        - Returns safe fields only: mechanic_id, latitude, longitude, accuracy_meters, recorded_at.
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

        # Ownership check
        if user_role == "customer" and str(booking.get("customer_id")) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )

        # 2. Find accepted mechanic assignment
        a_res = (
            self.client.table("mechanic_assignments")
            .select("id, mechanic_id, assignment_status")
            .eq("booking_id", str(booking_id))
            .eq("assignment_status", "accepted")
            .execute()
        )
        if not a_res.data or len(a_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No mechanic has been assigned to this booking yet.",
            )
        assignment = a_res.data[0]
        mechanic_id = assignment["mechanic_id"]

        # 3. Retrieve latest location from mechanic_locations (hits index: mechanic_id, recorded_at DESC)
        l_res = (
            self.client.table("mechanic_locations")
            .select("mechanic_id, latitude, longitude, accuracy_meters, recorded_at")
            .eq("mechanic_id", str(mechanic_id))
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if l_res.data and len(l_res.data) > 0:
            latest = l_res.data[0]
            return {
                "mechanic_id": uuid.UUID(str(latest["mechanic_id"])),
                "latitude": Decimal(str(latest["latitude"])),
                "longitude": Decimal(str(latest["longitude"])),
                "accuracy_meters": Decimal(str(latest["accuracy_meters"])) if latest.get("accuracy_meters") is not None else None,
                "recorded_at": latest["recorded_at"],
            }

        # 4. Fallback to mechanic_profiles snapshot if available
        p_res = (
            self.client.table("mechanic_profiles")
            .select("id, current_latitude, current_longitude, current_location_updated_at")
            .eq("id", str(mechanic_id))
            .execute()
        )
        if p_res.data and len(p_res.data) > 0:
            prof = p_res.data[0]
            if prof.get("current_latitude") and prof.get("current_longitude"):
                return {
                    "mechanic_id": uuid.UUID(str(prof["id"])),
                    "latitude": Decimal(str(prof["current_latitude"])),
                    "longitude": Decimal(str(prof["current_longitude"])),
                    "accuracy_meters": None,
                    "recorded_at": prof.get("current_location_updated_at") or datetime.now(timezone.utc).isoformat(),
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanic location is not currently available.",
        )

