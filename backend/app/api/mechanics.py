"""
Mechanics Discovery and Assignment Endpoints.

Mounts under /api/v1/mechanics.
Provides endpoints for:
1. Customer nearby mechanic discovery via trusted booking coordinates.
2. Mechanic assignment acceptance and rejection.
3. Safe public mechanic profiles without exposing phone numbers.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db.dependencies import get_current_user, require_mechanic
from app.schemas.mechanic import (
    AssignmentRejectRequest,
    AssignmentResponse,
    MechanicLocationResponse,
    MechanicLocationUpdate,
    NearbyMechanicResponse,
)
from app.schemas.review import MechanicReviewsListResponse
from app.schemas.user import AuthenticatedUser
from app.services.mechanic_service import MechanicService
from app.services.review_service import ReviewService

router = APIRouter(prefix="/mechanics", tags=["Mechanics"])


@router.post(
    "/location",
    response_model=MechanicLocationResponse,
    summary="Update mechanic live location",
    description=(
        "Authenticated mechanic broadcasts their current GPS coordinates. "
        "Updates current location snapshot on mechanic_profiles and logs an append-only "
        "history entry in mechanic_locations (which triggers Realtime subscription updates)."
    ),
)
async def update_mechanic_location_endpoint(
    payload: MechanicLocationUpdate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> MechanicLocationResponse:
    """Record GPS ping for authenticated mechanic."""
    service = MechanicService()
    result = await service.update_mechanic_location(
        user_id=current_user.id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        accuracy_meters=payload.accuracy_meters,
        sequence=payload.sequence,
    )
    return MechanicLocationResponse.model_validate(result)



@router.get(
    "/nearby",
    response_model=list[NearbyMechanicResponse],
    summary="Discover nearby mechanics for a booking",
    description=(
        "Discover verified and available mechanics within geodesic search radius of a booking. "
        "Coordinates are derived authoritatively from the booking address. "
        "Never exposes mechanic phone numbers or personal contact data."
    ),
)
async def find_nearby_mechanics_endpoint(
    booking_id: uuid.UUID = Query(..., description="UUID of customer booking"),
    max_distance_km: float = Query(
        default=20.0, gt=0, le=50.0, description="Geodesic search radius in km"
    ),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[NearbyMechanicResponse]:
    """Search for eligible mechanics for an authenticated customer's booking."""
    service = MechanicService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    return await service.find_nearby_mechanics_for_booking(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
        max_distance_km=max_distance_km,
    )


@router.post(
    "/assignments/{assignment_id}/accept",
    response_model=AssignmentResponse,
    summary="Mechanic accepts an offered assignment",
    description=(
        "Transition assignment to accepted and advance booking status to mechanic_assigned. "
        "Guards against race conditions and concurrent double assignment."
    ),
)
async def accept_assignment_endpoint(
    assignment_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> AssignmentResponse:
    """Accept an offered assignment as the assigned mechanic."""
    service = MechanicService()
    result = await service.accept_assignment(
        assignment_id=assignment_id,
        mechanic_user_id=current_user.id,
    )
    return AssignmentResponse.model_validate(result)


@router.post(
    "/assignments/{assignment_id}/reject",
    response_model=AssignmentResponse,
    summary="Mechanic rejects an offered assignment",
    description="Record rejection of an offered assignment with optional reason.",
)
async def reject_assignment_endpoint(
    assignment_id: uuid.UUID,
    payload: AssignmentRejectRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> AssignmentResponse:
    """Reject an offered assignment as the assigned mechanic."""
    service = MechanicService()
    result = await service.reject_assignment(
        assignment_id=assignment_id,
        mechanic_user_id=current_user.id,
        reason=payload.reason if payload else None,
    )
    return AssignmentResponse.model_validate(result)


@router.get(
    "/pending-offer",
    summary="Get latest pending job offer for mechanic",
    description="Retrieve any currently offered assignment for authenticated mechanic with active countdown.",
)
async def get_pending_offer_endpoint(
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> dict[str, Any] | None:
    """Retrieve active pending offer for the authenticated mechanic."""
    from datetime import datetime, timezone
    from app.db.supabase import get_supabase_service_client
    service_client = get_supabase_service_client()
    m_res = service_client.table("mechanic_profiles").select("id").eq("user_id", str(current_user.id)).execute()
    if not m_res.data:
        return None
    mech_id = m_res.data[0]["id"]
    now_iso = datetime.now(timezone.utc).isoformat()
    assign_res = (
        service_client.table("mechanic_assignments")
        .select("id, booking_id, assignment_status, distance_km, estimated_arrival_minutes, expires_at, attempt_number, bookings(booking_number, address_id, addresses(street_address, city), booking_items(services(name)))")
        .eq("mechanic_id", str(mech_id))
        .eq("assignment_status", "offered")
        .gt("expires_at", now_iso)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not assign_res.data or len(assign_res.data) == 0:
        return None

    row = assign_res.data[0]
    b_data = row.get("bookings") or {}
    addr_data = b_data.get("addresses") or {}
    items = b_data.get("booking_items") or []
    svc_name = "Doorstep Vehicle Service"
    if items and items[0].get("services") and items[0]["services"].get("name"):
        svc_name = items[0]["services"]["name"]

    area_parts = [addr_data.get("street_address"), addr_data.get("city")]
    customer_area = ", ".join([p for p in area_parts if p]) or "Local Service Area"

    return {
        "assignment_id": row["id"],
        "booking_id": row["booking_id"],
        "booking_number": b_data.get("booking_number", "N/A"),
        "service_name": svc_name,
        "customer_area": customer_area,
        "distance_km": float(row.get("distance_km") or 0.0),
        "estimated_arrival_minutes": int(row.get("estimated_arrival_minutes") or 15),
        "expires_at": row["expires_at"],
        "attempt_number": row.get("attempt_number", 1),
    }


@router.get(
    "/assignments/{assignment_id}",
    response_model=AssignmentResponse,
    summary="Get assignment details",
    description="Retrieve assignment details with role-based access verification.",
)
async def get_assignment_details(
    assignment_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> AssignmentResponse:
    """Retrieve assignment details."""
    service = MechanicService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await service.get_assignment_by_id(
        assignment_id=assignment_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return AssignmentResponse.model_validate(result)


@router.get(
    "/{mechanic_id}",
    summary="Get public mechanic profile",
    description="Retrieve public profile for a mechanic without revealing private contact details.",
)
async def get_mechanic_public_profile(
    mechanic_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Retrieve public mechanic profile."""
    service = MechanicService()
    profile = await service.get_mechanic_by_id(mechanic_id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanic profile not found.",
        )
    return profile


@router.get(
    "/{mechanic_id}/reviews",
    response_model=MechanicReviewsListResponse,
    summary="List reviews for mechanic",
    description="Retrieve paginated customer reviews and rating metrics for a mechanic. Omits private reviewer contact details.",
)
async def list_mechanic_reviews(
    mechanic_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=50, description="Max reviews to return (up to 50)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MechanicReviewsListResponse:
    """Retrieve paginated public reviews for a mechanic."""
    service = ReviewService()
    result = await service.get_mechanic_reviews(
        mechanic_id=mechanic_id,
        limit=limit,
        offset=offset,
    )
    return MechanicReviewsListResponse.model_validate(result)

