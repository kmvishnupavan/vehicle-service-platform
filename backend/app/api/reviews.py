"""
Reviews API Endpoints (Phase 8.5).

Mounts under /api/v1/reviews.
Provides endpoints for:
1. Updating an existing review (rating and/or comment) by authoring customer.
2. Fetching a review by primary UUID with authorization checks.
"""

import uuid
from fastapi import APIRouter, Depends, status
from app.db.dependencies import get_current_user, require_customer
from app.schemas.review import ReviewResponse, ReviewUpdate
from app.schemas.user import AuthenticatedUser
from app.services.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["Reviews"])


@router.patch(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Update customer review",
    description="Update rating and/or comment of an existing review. Restricted to the authoring customer.",
)
async def update_review_endpoint(
    review_id: uuid.UUID,
    payload: ReviewUpdate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> ReviewResponse:
    """Update an existing review."""
    service = ReviewService()
    updated = await service.update_review(
        review_id=review_id,
        customer_id=current_user.id,
        payload=payload,
    )
    return ReviewResponse.model_validate(updated)


@router.get(
    "/{review_id}",
    response_model=ReviewResponse,
    summary="Get review by ID",
    description="Retrieve review details with role-based authorization.",
)
async def get_review_endpoint(
    review_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ReviewResponse:
    """Retrieve review by ID."""
    service = ReviewService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    review = await service.get_review_by_id(
        review_id=review_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return ReviewResponse.model_validate(review)
