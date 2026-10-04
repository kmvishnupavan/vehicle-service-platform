"""
Bookings Endpoints.

Mounts under /api/v1/bookings.
Delegates business logic, authoritative pricing, and ownership enforcement to BookingService.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.core.config import get_settings
from app.db.dependencies import get_current_user, require_customer, require_mechanic
from app.schemas.additional_work import (
    AdditionalWorkCreate,
    AdditionalWorkResponse,
    CustomerApprovalRequest,
    CustomerRejectRequest,
)
from app.schemas.booking import BookingCreate, BookingResponse, BookingStatusUpdate
from app.schemas.inspection import (
    InspectionCreate,
    InspectionResponse,
    InspectionUpdate,
)
from app.schemas.mechanic import MechanicLocationResponse
from app.schemas.review import ReviewCreate, ReviewResponse
from app.schemas.user import AuthenticatedUser
from app.services.additional_work_service import AdditionalWorkService
from app.services.booking_service import BookingService
from app.services.inspection_service import InspectionService
from app.services.review_service import ReviewService


router = APIRouter(prefix="/bookings", tags=["Bookings"])



@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new booking",
    description=(
        "Authoritative customer booking creation. Validates ownership of vehicle and address, "
        "enforces catalog and vehicle compatibility, and calculates final pricing authoritatively "
        "without trusting client monetary values."
    ),
)
async def create_booking(
    payload: BookingCreate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> BookingResponse:
    """Create a new booking for authenticated customer."""
    if get_settings().KILL_SWITCH_NEW_BOOKINGS_DISABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="New booking creation is temporarily paused by pilot safety kill switch.",
        )
    booking_service = BookingService()
    created_booking = await booking_service.create_booking(
        customer_id=current_user.id,
        payload=payload,
    )
    return BookingResponse.model_validate(created_booking)


@router.get(
    "/my-bookings",
    response_model=list[BookingResponse],
    summary="List user's bookings",
    description="Retrieve all bookings belonging to authenticated customer with line items.",
)
async def list_user_bookings(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(require_customer),
) -> list[BookingResponse]:
    """Retrieve bookings for authenticated customer."""
    booking_service = BookingService()
    bookings = await booking_service.list_customer_bookings(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [BookingResponse.model_validate(b) for b in bookings]


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    summary="Get booking details",
    description="Retrieve booking details with line items. Returns 404 for inaccessible bookings to prevent resource leakage.",
)
async def get_booking_details(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BookingResponse:
    """Retrieve booking details with strict ownership verification."""
    booking_service = BookingService()
    booking = await booking_service.get_booking_by_id(booking_id)

    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )

    # Ownership check: customers can only access their own bookings
    if current_user.role == "customer" and str(booking.get("customer_id")) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )

    # Mechanics and other non-admin roles: if not admin/support and not owner, return 404
    if current_user.role not in ["customer", "admin", "support"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Booking not found.",
        )

    return BookingResponse.model_validate(booking)


@router.get(
    "/{booking_id}/mechanic-location",
    response_model=MechanicLocationResponse,
    summary="Get latest location of assigned mechanic",
    description=(
        "Retrieve the latest GPS coordinates of the mechanic assigned to an active booking. "
        "Strictly restricted to the booking's customer owner or admin/support. "
        "Returns 404 for inaccessible bookings to prevent leakage, and 400 if no mechanic is assigned."
    ),
)
async def get_booking_mechanic_location(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> MechanicLocationResponse:
    """Retrieve the latest GPS location for the mechanic assigned to a customer booking."""
    from app.services.mechanic_service import MechanicService

    mechanic_service = MechanicService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await mechanic_service.get_mechanic_location_for_booking(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return MechanicLocationResponse.model_validate(result)


@router.patch(
    "/{booking_id}/status",
    response_model=BookingResponse,
    summary="Update booking lifecycle status",
    description=(
        "Transition booking lifecycle state according to the authoritative Booking State Machine. "
        "Strictly enforces role-based transition authorization, ownership, and conditional concurrency checks."
    ),
)
async def update_booking_status_endpoint(
    booking_id: uuid.UUID,
    payload: BookingStatusUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> BookingResponse:
    """Transition booking lifecycle status with role authorization."""
    booking_service = BookingService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    updated_booking = await booking_service.update_booking_status(
        booking_id=booking_id,
        new_status=payload.new_status,
        user_id=current_user.id,
        user_role=user_role_str,
        reason=payload.reason,
    )
    return BookingResponse.model_validate(updated_booking)


# ==============================================================================
# Phase 7A: Inspection Endpoints
# ==============================================================================

@router.post(
    "/{booking_id}/inspections",
    response_model=InspectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit vehicle inspection report",
    description=(
        "Assigned mechanic submits diagnostic findings and condition summary. "
        "Strictly verifies accepted assignment and booking lifecycle."
    ),
)
async def submit_inspection(
    booking_id: uuid.UUID,
    payload: InspectionCreate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> InspectionResponse:
    """Submit diagnostic inspection findings for a booking."""
    service = InspectionService()
    result = await service.create_inspection(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )
    return InspectionResponse.model_validate(result)


@router.get(
    "/{booking_id}/inspection",
    response_model=InspectionResponse,
    summary="Get booking inspection report",
    description=(
        "Retrieve inspection report. Accessible to booking customer owner, "
        "assigned mechanic, or platform admin/support."
    ),
)
async def get_inspection(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> InspectionResponse:
    """Retrieve inspection report with strict ownership verification."""
    service = InspectionService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await service.get_inspection(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return InspectionResponse.model_validate(result)


@router.patch(
    "/{booking_id}/inspection",
    response_model=InspectionResponse,
    summary="Update inspection report",
    description="Update findings or estimated additional costs. Restricted to assigned mechanic or admin/support.",
)
async def update_inspection(
    booking_id: uuid.UUID,
    payload: InspectionUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> InspectionResponse:
    """Update inspection report details."""
    service = InspectionService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    result = await service.update_inspection(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
        payload=payload,
    )
    return InspectionResponse.model_validate(result)


# ==============================================================================
# Phase 7B & 7C: Additional Work Endpoints
# ==============================================================================

@router.post(
    "/{booking_id}/additional-work",
    response_model=AdditionalWorkResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose additional work",
    description=(
        "Assigned mechanic submits an additional work proposal. "
        "Creates request in 'pending' status and advances booking status to 'awaiting_customer_approval'."
    ),
)
async def create_additional_work(
    booking_id: uuid.UUID,
    payload: AdditionalWorkCreate,
    current_user: AuthenticatedUser = Depends(require_mechanic),
) -> AdditionalWorkResponse:
    """Propose additional work items for customer approval."""
    service = AdditionalWorkService()
    result = await service.create_additional_work_request(
        booking_id=booking_id,
        mechanic_user_id=current_user.id,
        payload=payload,
    )
    return AdditionalWorkResponse.model_validate(result)


@router.get(
    "/{booking_id}/additional-work",
    response_model=list[AdditionalWorkResponse],
    summary="List additional work requests",
    description="Retrieve all additional work requests for a booking. Accessible to customer owner, assigned mechanic, or admin.",
)
async def list_additional_work(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> list[AdditionalWorkResponse]:
    """List additional work requests with strict ownership check."""
    service = AdditionalWorkService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    results = await service.list_additional_work_requests(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return [AdditionalWorkResponse.model_validate(r) for r in results]


@router.post(
    "/{booking_id}/additional-work/{request_id}/approve",
    response_model=AdditionalWorkResponse,
    summary="Approve additional work request",
    description=(
        "Customer approves additional work request. Authoritatively recalculates "
        "booking additional_charges, tax, and total, and advances booking to service_in_progress."
    ),
)
async def approve_additional_work(
    booking_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CustomerApprovalRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> AdditionalWorkResponse:
    """Customer approves pending additional work proposal."""
    service = AdditionalWorkService()
    result = await service.approve_additional_work_request(
        booking_id=booking_id,
        request_id=request_id,
        customer_user_id=current_user.id,
        payload=payload,
    )
    return AdditionalWorkResponse.model_validate(result)


@router.post(
    "/{booking_id}/additional-work/{request_id}/reject",
    response_model=AdditionalWorkResponse,
    summary="Reject additional work request",
    description=(
        "Customer rejects additional work request. Sets status to rejected, "
        "advances booking to service_in_progress, and leaves financial totals unchanged."
    ),
)
async def reject_additional_work(
    booking_id: uuid.UUID,
    request_id: uuid.UUID,
    payload: CustomerRejectRequest | None = None,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> AdditionalWorkResponse:
    """Customer rejects pending additional work proposal."""
    service = AdditionalWorkService()
    result = await service.reject_additional_work_request(
        booking_id=booking_id,
        request_id=request_id,
        customer_user_id=current_user.id,
        payload=payload,
    )
    return AdditionalWorkResponse.model_validate(result)


@router.post(
    "/{booking_id}/review",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit customer review for completed booking",
    description=(
        "Customer submits rating (1-5) and optional comment for a completed service. "
        "Server authoritatively derives assigned mechanic, verifies customer ownership, "
        "and enforces one review per booking."
    ),
)
async def submit_booking_review(
    booking_id: uuid.UUID,
    payload: ReviewCreate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> ReviewResponse:
    """Submit a review for a completed booking."""
    service = ReviewService()
    review = await service.create_review(
        booking_id=booking_id,
        customer_id=current_user.id,
        payload=payload,
    )
    return ReviewResponse.model_validate(review)


@router.get(
    "/{booking_id}/review",
    response_model=ReviewResponse,
    summary="Get review for a booking",
    description="Retrieve the customer review submitted for a booking. Restricted to booking owner, assigned mechanic, and admin.",
)
async def get_booking_review_endpoint(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReviewResponse:
    """Retrieve review for a booking."""
    service = ReviewService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    review = await service.get_booking_review(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return ReviewResponse.model_validate(review)




