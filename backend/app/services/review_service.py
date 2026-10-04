"""
Review Service Layer (Phase 8.5).

Implements authoritative customer review and rating workflows:
- Strict lifecycle verification (only completed bookings: 'service_completed', 'payment_pending', 'paid')
- Server-side derivation of assigned mechanic (never trusted from client)
- Authoritative customer identity from JWT
- Database-enforced uniqueness (one review per booking)
- Concurrency-safe atomic database triggers for mechanic average_rating calculation
- Privacy-preserving reviewer masking
- Non-blocking notification dispatch and audit logging
"""

from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.audit import record_audit_log
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.review import (
    MechanicReviewsListResponse,
    ReviewCreate,
    ReviewListItem,
    ReviewResponse,
    ReviewUpdate,
)
from app.services.notification_service import NotificationService

logger = get_logger("services.review")


def mask_customer_name(full_name: str | None) -> str:
    """Format full name into privacy-safe representation (e.g. 'Jane Doe' -> 'Jane D.')."""
    if not full_name or not full_name.strip():
        return "Customer"
    parts = full_name.strip().split()
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[-1][0]}."


class ReviewService:
    """Authoritative service governing review creation, retrieval, updates, and mechanic aggregation."""

    ELIGIBLE_BOOKING_STATUSES = {"service_completed", "payment_pending", "paid"}
    INVALID_BOOKING_STATUSES = {
        "pending",
        "searching_mechanic",
        "mechanic_assigned",
        "mechanic_en_route",
        "mechanic_arrived",
        "inspection",
        "awaiting_customer_approval",
        "service_in_progress",
        "additional_work",
        "cancelled",
        "disputed",
    }

    def __init__(self, client=None):
        self.client = client or get_supabase_service_client()

    async def create_review(
        self,
        booking_id: uuid.UUID,
        customer_id: uuid.UUID,
        payload: ReviewCreate,
    ) -> dict[str, Any]:
        """
        Create a new review for an eligible booking.
        Derives mechanic authoritatively from the booking's accepted mechanic assignment.
        Enforces one review per booking at application and database constraint levels.
        """
        # 1. Fetch booking to verify existence and ownership
        b_res = (
            self.client.table("bookings")
            .select("id, booking_number, customer_id, booking_status")
            .eq("id", str(booking_id))
            .execute()
        )
        if not b_res.data or len(b_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Booking not found.",
            )
        booking = b_res.data[0]

        # 2. Verify booking ownership
        if str(booking["customer_id"]) != str(customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to submit a review for this booking.",
            )

        # 3. Verify booking is in an eligible completed state
        booking_status = booking.get("booking_status")
        if booking_status not in self.ELIGIBLE_BOOKING_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Review cannot be submitted for booking with status '{booking_status}'. "
                    "Service must be completed before leaving a review."
                ),
            )

        # 4. Derive assigned mechanic authoritatively from assignments
        a_res = (
            self.client.table("mechanic_assignments")
            .select("id, mechanic_id, assignment_status")
            .eq("booking_id", str(booking_id))
            .in_("assignment_status", ["accepted", "completed"])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if not a_res.data or len(a_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No assigned mechanic found for this booking.",
            )
        assignment = a_res.data[0]
        mechanic_id = assignment["mechanic_id"]

        # 5. Check if review already exists for this booking (Application-level precheck)
        existing_res = (
            self.client.table("reviews")
            .select("id")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if existing_res.data and len(existing_res.data) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A review has already been submitted for this booking.",
            )

        # 6. Insert review into database
        review_data = {
            "booking_id": str(booking_id),
            "customer_id": str(customer_id),
            "mechanic_id": str(mechanic_id),
            "rating": payload.rating,
            "review_text": payload.comment,
        }

        try:
            insert_res = self.client.table("reviews").insert(review_data).execute()
        except Exception as exc:
            err_msg = str(exc)
            if "duplicate key" in err_msg.lower() or "unique" in err_msg.lower() or "23505" in err_msg:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A review has already been submitted for this booking.",
                )
            logger.error("review_insert_database_error", error=err_msg, booking_id=str(booking_id))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save review.",
            )

        if not insert_res.data or len(insert_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save review.",
            )

        created_review = insert_res.data[0]
        review_id = created_review["id"]

        # 7. Non-blocking Notification to mechanic
        try:
            m_res = (
                self.client.table("mechanic_profiles")
                .select("user_id")
                .eq("id", str(mechanic_id))
                .execute()
            )
            if m_res.data and len(m_res.data) > 0:
                mechanic_user_id = m_res.data[0]["user_id"]
                notif_service = NotificationService()
                await notif_service.send_notification(
                    user_id=uuid.UUID(str(mechanic_user_id)),
                    title="New customer review",
                    message=(
                        f"You received a {payload.rating}-star review for booking "
                        f"#{booking.get('booking_number', '')}."
                    ),
                    notification_type="review",
                    data={
                        "booking_id": str(booking_id),
                        "review_id": str(review_id),
                        "rating": payload.rating,
                    },
                    event_id=f"review_created_{review_id}",
                )
        except Exception as exc:
            logger.warning("review_notification_dispatch_failed", error=str(exc), review_id=str(review_id))

        # 8. Record audit log
        try:
            record_audit_log(
                action="review_created",
                entity_type="review",
                entity_id=review_id,
                actor_id=customer_id,
                actor_role="customer",
                new_data={
                    "booking_id": str(booking_id),
                    "mechanic_id": str(mechanic_id),
                    "rating": payload.rating,
                    "has_comment": bool(payload.comment),
                },
            )
        except Exception as exc:
            logger.warning("review_audit_log_failed", error=str(exc), review_id=str(review_id))

        # Map review_text to comment for client consistency
        created_review["comment"] = created_review.get("review_text")
        return created_review

    async def get_booking_review(
        self,
        booking_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """Retrieve authoritative review for a booking with role-based access checks."""
        # 1. Fetch booking to verify authorization
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

        # 2. Authorization check
        is_owner = str(booking["customer_id"]) == str(user_id)
        is_admin = user_role in ["admin", "support"]

        is_assigned_mechanic = False
        if not is_owner and not is_admin:
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(user_id))
                .execute()
            )
            if m_res.data and len(m_res.data) > 0:
                mech_id = m_res.data[0]["id"]
                a_res = (
                    self.client.table("mechanic_assignments")
                    .select("id")
                    .eq("booking_id", str(booking_id))
                    .eq("mechanic_id", str(mech_id))
                    .in_("assignment_status", ["accepted", "completed"])
                    .execute()
                )
                if a_res.data and len(a_res.data) > 0:
                    is_assigned_mechanic = True

        if not is_owner and not is_admin and not is_assigned_mechanic:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view the review for this booking.",
            )

        # 3. Fetch review
        r_res = (
            self.client.table("reviews")
            .select("*")
            .eq("booking_id", str(booking_id))
            .execute()
        )
        if not r_res.data or len(r_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No review found for this booking.",
            )

        review = r_res.data[0]
        review["comment"] = review.get("review_text")
        return review

    async def get_review_by_id(
        self,
        review_id: uuid.UUID,
        user_id: uuid.UUID,
        user_role: str,
    ) -> dict[str, Any]:
        """Retrieve review by its primary UUID."""
        r_res = (
            self.client.table("reviews")
            .select("*")
            .eq("id", str(review_id))
            .execute()
        )
        if not r_res.data or len(r_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found.",
            )
        review = r_res.data[0]
        review["comment"] = review.get("review_text")
        return review

    async def update_review(
        self,
        review_id: uuid.UUID,
        customer_id: uuid.UUID,
        payload: ReviewUpdate,
    ) -> dict[str, Any]:
        """Update an existing review's rating or comment. Only authoring customer is permitted."""
        # 1. Fetch review
        r_res = (
            self.client.table("reviews")
            .select("*")
            .eq("id", str(review_id))
            .execute()
        )
        if not r_res.data or len(r_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Review not found.",
            )
        review = r_res.data[0]

        # 2. Check ownership
        if str(review["customer_id"]) != str(customer_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to update this review.",
            )

        # 3. Prepare update payload (strictly rating and review_text only)
        update_fields: dict[str, Any] = {}
        if payload.rating is not None:
            update_fields["rating"] = payload.rating
        if payload.comment is not None or "comment" in payload.model_fields_set:
            update_fields["review_text"] = payload.comment

        if not update_fields:
            review["comment"] = review.get("review_text")
            return review

        update_res = (
            self.client.table("reviews")
            .update(update_fields)
            .eq("id", str(review_id))
            .execute()
        )
        if not update_res.data or len(update_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update review.",
            )

        updated_review = update_res.data[0]
        updated_review["comment"] = updated_review.get("review_text")
        return updated_review

    async def get_mechanic_reviews(
        self,
        mechanic_id: uuid.UUID,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """
        Public/authorized list of reviews for a mechanic.
        Returns paginated items with privacy-safe masked customer names, plus authoritative aggregates.
        """
        # 1. Verify mechanic profile exists
        m_res = (
            self.client.table("mechanic_profiles")
            .select("id, average_rating")
            .eq("id", str(mechanic_id))
            .execute()
        )
        if not m_res.data or len(m_res.data) == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mechanic profile not found.",
            )
        mech_profile = m_res.data[0]

        # 2. Sanitize pagination bounds
        safe_limit = min(max(1, limit), 50)
        safe_offset = max(0, offset)

        # 3. Query reviews with customer profile for safe name display
        r_res = (
            self.client.table("reviews")
            .select("id, rating, review_text, created_at, customer_id, profiles!customer_id(full_name)")
            .eq("mechanic_id", str(mechanic_id))
            .order("created_at", desc=True)
            .range(safe_offset, safe_offset + safe_limit - 1)
            .execute()
        )

        # 4. Count total reviews authoritatively
        count_res = (
            self.client.table("reviews")
            .select("id", count="exact")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        total_count = count_res.count if count_res.count is not None else 0

        # Parse items safely
        items = []
        for row in (r_res.data or []):
            prof_data = row.pop("profiles", None) or {}
            raw_name = prof_data.get("full_name")
            items.append({
                "id": row["id"],
                "rating": row["rating"],
                "comment": row.get("review_text"),
                "created_at": row["created_at"],
                "customer_name": mask_customer_name(raw_name),
            })

        avg_rating = float(mech_profile.get("average_rating") or 0.0)

        return {
            "items": items,
            "total_count": total_count,
            "average_rating": avg_rating,
            "limit": safe_limit,
            "offset": safe_offset,
        }
