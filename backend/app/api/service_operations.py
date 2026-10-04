"""
Service Operations Endpoints (Phase 12).

Mounts under /api/v1/bookings.
Coordinates arrival, structured inspection, service checklists, parts tracking,
customer estimate approvals, service completion, and dispute handling.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db.dependencies import (
    get_current_user,
    require_admin_or_support,
    require_customer,
    require_mechanic,
)
from app.schemas.service_operations import (
    ArrivalResponse,
    BookingChecklistItemResponse,
    BookingChecklistItemUpdate,
    BookingPartCreate,
    BookingPartResponse,
    DisputeCreateRequest,
    DisputeResolveRequest,
    ServiceCompletionRequest,
    ServiceReportResponse,
    StructuredInspectionCreate,
    StructuredInspectionResponse,
)
from app.schemas.user import AuthenticatedUser
from app.services.service_operations_service import ServiceOperationsService

router = APIRouter(prefix="/bookings", tags=["Service Operations"])


# ==============================================================================
# 1. Arrival Workflow
# ==============================================================================

@router.post(
    "/{booking_id}/arrive",
    response_model=ArrivalResponse,
    summary="Record mechanic arrival",
    description="Assigned mechanic confirms arrival at the customer vehicle location with authoritative server timestamp.",
)
async def record_arrival_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> ArrivalResponse:
    """Record mechanic arrival at destination."""
    service = ServiceOperationsService()
    return await service.record_arrival(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
    )


# ==============================================================================
# 2. Structured Vehicle Inspection
# ==============================================================================

@router.post(
    "/{booking_id}/structured-inspection",
    response_model=StructuredInspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit structured vehicle inspection",
    description="Assigned mechanic submits comprehensive diagnostic checkpoints, odometer, and repair recommendations.",
)
async def submit_structured_inspection_endpoint(
    booking_id: uuid.UUID,
    payload: StructuredInspectionCreate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> StructuredInspectionResponse:
    """Submit diagnostic inspection with structured checkpoints."""
    service = ServiceOperationsService()
    result = await service.submit_structured_inspection(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )
    return StructuredInspectionResponse.model_validate(result)


@router.get(
    "/{booking_id}/structured-inspection",
    response_model=StructuredInspectionResponse,
    summary="Get structured vehicle inspection",
    description="Retrieve comprehensive vehicle inspection report. Restricted to customer owner, assigned mechanic, or admin.",
)
async def get_structured_inspection_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> StructuredInspectionResponse:
    """Retrieve structured diagnostic inspection."""
    service = ServiceOperationsService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await service.get_structured_inspection(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return StructuredInspectionResponse.model_validate(result)


# ==============================================================================
# 3. Service Checklist Management
# ==============================================================================

@router.get(
    "/{booking_id}/checklist",
    response_model=list[BookingChecklistItemResponse],
    summary="Get service checklist tasks",
    description="Retrieve service checklist for a booking, automatically seeded from templates based on requested services.",
)
async def get_checklist_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[BookingChecklistItemResponse]:
    """Retrieve service checklist items."""
    service = ServiceOperationsService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    results = await service.get_or_initialize_booking_checklist(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return [BookingChecklistItemResponse.model_validate(r) for r in results]


@router.patch(
    "/{booking_id}/checklist/{item_id}",
    response_model=BookingChecklistItemResponse,
    summary="Update checklist task item",
    description="Assigned mechanic updates completion state and notes for a specific checklist item.",
)
async def update_checklist_item_endpoint(
    booking_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: BookingChecklistItemUpdate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> BookingChecklistItemResponse:
    """Update checklist task state."""
    service = ServiceOperationsService()
    result = await service.update_checklist_item(
        booking_id=booking_id,
        item_id=item_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )
    return BookingChecklistItemResponse.model_validate(result)


# ==============================================================================
# 4. Service Parts Tracking
# ==============================================================================

@router.post(
    "/{booking_id}/parts",
    response_model=BookingPartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record installed service part",
    description="Assigned mechanic records a replacement part used during vehicle repair or servicing.",
)
async def add_booking_part_endpoint(
    booking_id: uuid.UUID,
    payload: BookingPartCreate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> BookingPartResponse:
    """Record replacement part installed during service."""
    service = ServiceOperationsService()
    result = await service.add_booking_part(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )
    return BookingPartResponse.model_validate(result)


@router.get(
    "/{booking_id}/parts",
    response_model=list[BookingPartResponse],
    summary="List parts installed on booking",
    description="Retrieve list of replacement parts recorded for this booking.",
)
async def list_booking_parts_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[BookingPartResponse]:
    """List service parts for booking."""
    service = ServiceOperationsService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    results = await service.list_booking_parts(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return [BookingPartResponse.model_validate(r) for r in results]


# ==============================================================================
# 5. Customer Estimate Approval & Price Snapshot
# ==============================================================================

@router.post(
    "/{booking_id}/approve-estimate",
    summary="Customer approves service estimate",
    description="Customer approves inspection findings and cost estimate, freezing an immutable price snapshot.",
)
async def approve_estimate_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> dict[str, Any]:
    """Customer approves estimate and advances service."""
    service = ServiceOperationsService()
    return await service.customer_approve_estimate(
        booking_id=booking_id,
        customer_user_id=current_user.id,
    )


# ==============================================================================
# 6. Service Completion & Service Report
# ==============================================================================

@router.post(
    "/{booking_id}/complete",
    response_model=ServiceReportResponse,
    summary="Complete service and generate report",
    description="Mechanic finalizes service execution with checklist verification and issues service report.",
)
async def complete_service_endpoint(
    booking_id: uuid.UUID,
    payload: ServiceCompletionRequest,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> ServiceReportResponse:
    """Finalize service and issue report."""
    service = ServiceOperationsService()
    return await service.complete_service(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )


@router.get(
    "/{booking_id}/service-report",
    response_model=ServiceReportResponse,
    summary="Get service report",
    description="Retrieve completed service report for a booking.",
)
async def get_service_report_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ServiceReportResponse:
    """Retrieve service report."""
    client = ServiceOperationsService().client
    res = client.table("service_reports").select("*").eq("booking_id", str(booking_id)).execute()
    if not res.data or len(res.data) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service report not found.")
    return ServiceReportResponse.model_validate(res.data[0])


# ==============================================================================
# 7. Dispute Management
# ==============================================================================

@router.post(
    "/{booking_id}/dispute",
    summary="Raise dispute for booking",
    description="Customer raises formal dispute on a completed or paid booking.",
)
async def raise_dispute_endpoint(
    booking_id: uuid.UUID,
    payload: DisputeCreateRequest,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> dict[str, Any]:
    """Customer raises formal dispute."""
    service = ServiceOperationsService()
    return await service.raise_dispute(
        booking_id=booking_id,
        customer_user_id=current_user.id,
        payload=payload,
    )


@router.post(
    "/{booking_id}/dispute/resolve",
    summary="Resolve active dispute",
    description="Admin or support operator resolves an active dispute.",
)
async def resolve_dispute_endpoint(
    booking_id: uuid.UUID,
    payload: DisputeResolveRequest,
    current_user: AuthenticatedUser = Depends(require_admin_or_support),
) -> dict[str, Any]:
    """Admin resolves dispute."""
    service = ServiceOperationsService()
    return await service.resolve_dispute(
        booking_id=booking_id,
        admin_user_id=current_user.id,
        payload=payload,
    )


# ==============================================================================
# 8. Service Evidence Signed URL Helper
# ==============================================================================

@router.get(
    "/{booking_id}/evidence/signed-url",
    summary="Get signed URL for service evidence",
    description="Generate temporary, secure signed URL for accessing private service evidence or report objects.",
)
async def get_evidence_signed_url_endpoint(
    booking_id: uuid.UUID,
    path: str = Query(..., description="Relative storage path within service-evidence or service-reports"),
    bucket: str = Query(default="service-evidence", description="Target storage bucket"),
    expires_in: int = Query(default=3600, ge=60, le=86400, description="Expiration in seconds"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, str]:
    """Generate temporary signed URL for evidence objects."""
    allowed_buckets = {"service-evidence", "service-reports"}
    if bucket not in allowed_buckets:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid bucket. Allowed: {allowed_buckets}")

    # Check path begins with booking_id
    if not path.startswith(str(booking_id)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Evidence path must belong to booking {booking_id}",
        )

    client = ServiceOperationsService().client
    # Verify booking exists and user is authorized
    b_res = client.table("bookings").select("id, customer_id").eq("id", str(booking_id)).execute()
    if not b_res.data or len(b_res.data) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    booking = b_res.data[0]
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role_str == "customer" and str(booking["customer_id"]) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found.")

    try:
        signed = client.storage.from_(bucket).create_signed_url(path, expires_in)
        signed_url = signed.get("signedURL") or signed.get("signedUrl") or f"/mock-storage/{bucket}/{path}"
        return {"signed_url": signed_url, "expires_in": str(expires_in)}
    except Exception as exc:
        logger.warning("storage_signed_url_failed", error=str(exc))
        return {"signed_url": f"/mock-storage/{bucket}/{path}", "expires_in": str(expires_in)}
