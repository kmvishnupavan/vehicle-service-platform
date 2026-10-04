"""
Intelligent Mechanic Matching, Dispatch & Service Operations API Endpoints (Phase 11).

Mounts under /api/v1/matching.
Provides endpoints for:
1. Candidate mechanic discovery and explainable ranking.
2. Automated matching session dispatch and offer creation.
3. Matching session state inspection for customers and admins.
4. Atomic offer acceptance and rejection for mechanics.
5. Maintenance expiration of stale offers.
6. Service capability management for mechanics.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db.dependencies import (
    get_current_user,
    require_admin,
    require_customer,
    require_mechanic,
    require_roles,
    require_support,
)
from app.schemas.matching import (
    CandidateMechanic,
    MatchingSessionResponse,
    MechanicCapabilityCreate,
    MechanicCapabilityResponse,
    OfferResponse,
    RejectAssignmentRequest,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.matching_service import MatchingService
from app.services.mechanic_service import MechanicService

router = APIRouter(prefix="/matching", tags=["Intelligent Matching & Dispatch"])


# =============================================================================
# 1. Candidate Discovery & Ranking
# =============================================================================

@router.post(
    "/candidates/{booking_id}",
    response_model=list[CandidateMechanic],
    summary="Discover and rank candidate mechanics for a booking",
    description=(
        "Discovers qualified, available, non-busy nearby mechanics and ranks them "
        "using a deterministic multi-factor model (proximity, rating, workload, reliability, acceptance). "
        "Accessible to the booking customer owner and admin/support operators."
    ),
)
async def discover_and_rank_candidates_endpoint(
    booking_id: uuid.UUID,
    max_distance_km: float = Query(25.0, ge=1.0, le=100.0, description="Search radius in kilometers"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[CandidateMechanic]:
    """Discover candidate mechanics for a booking and return ranked explainable results."""
    matching_svc = MatchingService()

    # Authorize: Must be customer owner or admin/support
    b_res = (
        matching_svc.client.table("bookings")
        .select("customer_id")
        .eq("id", str(booking_id))
        .execute()
    )
    if not b_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    is_owner = str(b_res.data[0]["customer_id"]) == str(current_user.id)
    is_staff = current_user.role in [UserRole.ADMIN, UserRole.SUPPORT, "admin", "support"]

    if not (is_owner or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this booking.")

    booking, candidates = await matching_svc.find_eligible_candidates(booking_id, max_distance_km=max_distance_km)
    ranked = await matching_svc.rank_candidate_mechanics(candidates, booking)
    return ranked


# =============================================================================
# 2. Matching Session Dispatch
# =============================================================================

@router.post(
    "/dispatch/{booking_id}",
    response_model=MatchingSessionResponse,
    summary="Dispatch automated matching and offer assignment",
    description=(
        "Initiates the automated dispatch flow: ranks candidates, creates a matching session, "
        "and sends a 60-second countdown job offer to the top-ranked candidate."
    ),
)
async def dispatch_matching_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MatchingSessionResponse:
    """Dispatch matching and create initial candidate offer."""
    matching_svc = MatchingService()

    b_res = (
        matching_svc.client.table("bookings")
        .select("customer_id")
        .eq("id", str(booking_id))
        .execute()
    )
    if not b_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    is_owner = str(b_res.data[0]["customer_id"]) == str(current_user.id)
    is_staff = current_user.role in [UserRole.ADMIN, UserRole.SUPPORT, "admin", "support"]

    if not (is_owner or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this booking.")

    session_resp = await matching_svc.dispatch_matching_for_booking(booking_id)

    # Privacy scrubbing: if customer, do not expose other mechanics' private details
    if is_owner and not is_staff:
        session_resp.candidates = []

    return session_resp


# =============================================================================
# 3. Matching Session Inspection
# =============================================================================

@router.get(
    "/sessions/{booking_id}",
    response_model=MatchingSessionResponse,
    summary="Get matching session status for a booking",
)
async def get_matching_session_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MatchingSessionResponse:
    """Retrieve session state for a booking."""
    matching_svc = MatchingService()

    b_res = (
        matching_svc.client.table("bookings")
        .select("customer_id")
        .eq("id", str(booking_id))
        .execute()
    )
    if not b_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    is_owner = str(b_res.data[0]["customer_id"]) == str(current_user.id)
    is_staff = current_user.role in [UserRole.ADMIN, UserRole.SUPPORT, "admin", "support"]

    if not (is_owner or is_staff):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this booking.")

    s_res = (
        matching_svc.client.table("matching_sessions")
        .select("*")
        .eq("booking_id", str(booking_id))
        .execute()
    )
    if not s_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No matching session found for booking.")

    row = s_res.data[0]
    candidates_data = row.get("candidates_ranked") or []
    candidates = []

    if is_staff:
        # Full explainable candidates view for admins
        for c in candidates_data:
            try:
                candidates.append(CandidateMechanic.model_validate(c))
            except Exception:
                pass

    return MatchingSessionResponse(
        session_id=uuid.UUID(row["id"]),
        booking_id=uuid.UUID(row["booking_id"]),
        status=row["status"],
        candidate_count=row.get("candidate_count", 0),
        current_attempt=row.get("current_attempt", 1),
        max_attempts=row.get("max_attempts", 3),
        selected_mechanic_id=uuid.UUID(row["selected_mechanic_id"]) if row.get("selected_mechanic_id") else None,
        candidates=candidates,
        failure_reason=row.get("failure_reason"),
        started_at=row["started_at"],
        completed_at=row.get("completed_at"),
    )


@router.get(
    "/admin/sessions",
    response_model=list[MatchingSessionResponse],
    summary="List matching sessions for admin dashboard",
)
async def list_admin_matching_sessions_endpoint(
    status_filter: str | None = Query(None, description="Optional status filter"),
    limit: int = Query(50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_support),
) -> list[MatchingSessionResponse]:
    """Admin view: inspect all matching sessions across the platform."""
    matching_svc = MatchingService()
    query = matching_svc.client.table("matching_sessions").select("*").order("created_at", desc=True).limit(limit)
    if status_filter:
        query = query.eq("status", status_filter)

    res = query.execute()
    results: list[MatchingSessionResponse] = []
    for row in (res.data or []):
        candidates = []
        for c in (row.get("candidates_ranked") or []):
            try:
                candidates.append(CandidateMechanic.model_validate(c))
            except Exception:
                pass

        results.append(
            MatchingSessionResponse(
                session_id=uuid.UUID(row["id"]),
                booking_id=uuid.UUID(row["booking_id"]),
                status=row["status"],
                candidate_count=row.get("candidate_count", 0),
                current_attempt=row.get("current_attempt", 1),
                max_attempts=row.get("max_attempts", 3),
                selected_mechanic_id=uuid.UUID(row["selected_mechanic_id"]) if row.get("selected_mechanic_id") else None,
                candidates=candidates,
                failure_reason=row.get("failure_reason"),
                started_at=row["started_at"],
                completed_at=row.get("completed_at"),
            )
        )
    return results


# =============================================================================
# 4. Mechanic Assignment Response (Accept / Reject)
# =============================================================================

@router.post(
    "/assignments/{assignment_id}/accept",
    summary="Accept offered assignment (Mechanic)",
    description=(
        "Mechanic accepts an offered assignment atomically. "
        "Enforces identity matching, single-acceptance constraints, and advances booking to 'mechanic_assigned'."
    ),
)
async def accept_assignment_endpoint(
    assignment_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> dict[str, Any]:
    """Atomic acceptance of a dispatched assignment offer."""
    service = MechanicService()
    result = await service.accept_assignment(
        assignment_id=assignment_id,
        mechanic_user_id=current_user.id,
    )
    return {"success": True, "assignment": result}


@router.post(
    "/assignments/{assignment_id}/reject",
    summary="Reject offered assignment (Mechanic)",
    description=(
        "Mechanic explicitly declines an offered assignment. "
        "Marks the assignment as 'rejected' and automatically retries with the next candidate."
    ),
)
async def reject_assignment_endpoint(
    assignment_id: uuid.UUID,
    payload: RejectAssignmentRequest,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> dict[str, Any]:
    """Atomic rejection and automatic progression to next candidate."""
    matching_svc = MatchingService()
    result = await matching_svc.handle_mechanic_rejection(
        assignment_id=assignment_id,
        mechanic_user_id=current_user.id,
        reason=payload.reason,
    )
    return {"success": True, "assignment": result}


# =============================================================================
# 5. Maintenance / Background Workers
# =============================================================================

@router.post(
    "/maintenance/expire-stale-offers",
    summary="Expire stale job offers and retry next candidates",
    description=(
        "Maintenance routine: sweeps all offered assignments past expires_at, "
        "marks them as expired, and advances to the next candidate."
    ),
)
async def expire_stale_offers_endpoint(
    current_user: AuthenticatedUser = Depends(require_support),
) -> dict[str, Any]:
    """Execute offer timeout sweep."""
    matching_svc = MatchingService()
    expired_count = await matching_svc.expire_stale_offers()
    return {"success": True, "expired_count": expired_count}


# =============================================================================
# 6. Mechanic Service Capabilities
# =============================================================================

@router.get(
    "/mechanics/{mechanic_id}/capabilities",
    response_model=list[MechanicCapabilityResponse],
    summary="List mechanic service capabilities",
)
async def list_mechanic_capabilities_endpoint(
    mechanic_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[MechanicCapabilityResponse]:
    """List service qualifications for a mechanic."""
    matching_svc = MatchingService()
    res = (
        matching_svc.client.table("mechanic_service_capabilities")
        .select("*")
        .eq("mechanic_id", str(mechanic_id))
        .eq("is_active", True)
        .execute()
    )
    return [
        MechanicCapabilityResponse(
            id=uuid.UUID(row["id"]),
            mechanic_id=uuid.UUID(row["mechanic_id"]),
            category_id=uuid.UUID(row["category_id"]) if row.get("category_id") else None,
            service_id=uuid.UUID(row["service_id"]) if row.get("service_id") else None,
            is_active=row["is_active"],
            created_at=row["created_at"],
        )
        for row in (res.data or [])
    ]


@router.post(
    "/mechanics/{mechanic_id}/capabilities",
    response_model=MechanicCapabilityResponse,
    summary="Add a service capability to a mechanic profile",
)
async def add_mechanic_capability_endpoint(
    mechanic_id: uuid.UUID,
    payload: MechanicCapabilityCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MechanicCapabilityResponse:
    """Add a qualified category or service to a mechanic profile."""
    matching_svc = MatchingService()

    # Verify authorization: mechanic owner or admin
    p_res = (
        matching_svc.client.table("mechanic_profiles")
        .select("user_id")
        .eq("id", str(mechanic_id))
        .execute()
    )
    if not p_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic profile not found.")

    is_owner = str(p_res.data[0]["user_id"]) == str(current_user.id)
    is_admin = current_user.role in [UserRole.ADMIN, "admin"]

    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    if not payload.category_id and not payload.service_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of category_id or service_id must be provided.",
        )

    ins_data = {
        "mechanic_id": str(mechanic_id),
        "category_id": str(payload.category_id) if payload.category_id else None,
        "service_id": str(payload.service_id) if payload.service_id else None,
        "is_active": True,
    }
    ins_res = matching_svc.client.table("mechanic_service_capabilities").insert(ins_data).execute()
    if not ins_res.data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to register capability.")

    row = ins_res.data[0]
    return MechanicCapabilityResponse(
        id=uuid.UUID(row["id"]),
        mechanic_id=uuid.UUID(row["mechanic_id"]),
        category_id=uuid.UUID(row["category_id"]) if row.get("category_id") else None,
        service_id=uuid.UUID(row["service_id"]) if row.get("service_id") else None,
        is_active=row["is_active"],
        created_at=row["created_at"],
    )


@router.delete(
    "/mechanics/{mechanic_id}/capabilities/{capability_id}",
    summary="Remove a service capability",
)
async def delete_mechanic_capability_endpoint(
    mechanic_id: uuid.UUID,
    capability_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Remove a capability from a mechanic profile."""
    matching_svc = MatchingService()

    p_res = (
        matching_svc.client.table("mechanic_profiles")
        .select("user_id")
        .eq("id", str(mechanic_id))
        .execute()
    )
    if not p_res.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mechanic profile not found.")

    is_owner = str(p_res.data[0]["user_id"]) == str(current_user.id)
    is_admin = current_user.role in [UserRole.ADMIN, "admin"]

    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    matching_svc.client.table("mechanic_service_capabilities").delete().eq("id", str(capability_id)).execute()
    return {"success": True, "message": "Capability removed successfully."}
