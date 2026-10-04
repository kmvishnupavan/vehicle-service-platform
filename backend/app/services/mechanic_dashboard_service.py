"""
Mechanic Dashboard Service Layer (Phase 8.6).

Authoritative coordinator for:
- Mechanic identity resolution and authorization (preventing cross-mechanic access)
- Dashboard Overview calculations (today jobs, active/completed/cancelled, earnings, completion rate)
- Performance metrics, rating distribution (1-5), and monthly historical breakdown
- Authoritative earnings derivation with strict Decimal precision and payment status reconciliation
- Recent jobs listing with zero customer PII leakage
- Recent reviews listing with privacy-safe name masking
"""

from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
import uuid
from fastapi import HTTPException, status
from app.core.logging import get_logger
from app.db.supabase import get_supabase_service_client
from app.schemas.mechanic_dashboard import (
    DashboardOverviewResponse,
    EarningsItem,
    EarningsListResponse,
    MechanicPerformanceResponse,
    MonthlyBreakdown,
    RecentJobItem,
    RecentJobsResponse,
    RecentReviewItem,
    RecentReviewsResponse,
    TodayJobs,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.review_service import mask_customer_name

logger = get_logger("services.mechanic_dashboard")


def format_decimal(val: Any) -> str:
    """Safely format numeric/string value to 2 decimal places using Decimal."""
    if val is None:
        return "0.00"
    try:
        dec = Decimal(str(val)).quantize(Decimal("0.01"))
        return f"{dec:.2f}"
    except Exception:
        return "0.00"


def safe_uuid(val: Any) -> uuid.UUID:
    """Safely parse or convert value to UUID."""
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except Exception:
        # Fallback to deterministic UUID if non-UUID string encountered
        return uuid.uuid5(uuid.NAMESPACE_DNS, str(val))


def parse_iso_datetime(dt_str: str | None, is_end_of_day: bool = False) -> datetime | None:
    """Parse and validate ISO date string; raises 422 if invalid."""
    if not dt_str:
        return None
    try:
        # Check simple YYYY-MM-DD
        if len(dt_str) == 10 and dt_str[4] == "-" and dt_str[7] == "-":
            d = date.fromisoformat(dt_str)
            if is_end_of_day:
                return datetime(d.year, d.month, d.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
            return datetime(d.year, d.month, d.day, 0, 0, 0, 0, tzinfo=timezone.utc)
        dt_clean = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ISO date format: '{dt_str}'. Expected format: YYYY-MM-DD or ISO timestamp.",
        )


class MechanicDashboardService:
    """Authoritative service for mechanic performance, earnings, and dashboard analytics."""

    ACTIVE_STATUSES = {
        "mechanic_assigned",
        "mechanic_en_route",
        "mechanic_arrived",
        "inspection",
        "awaiting_customer_approval",
        "service_in_progress",
        "additional_work",
    }
    COMPLETED_STATUSES = {"service_completed", "payment_pending", "paid"}
    CANCELLED_STATUSES = {"cancelled"}

    def __init__(self, client=None):
        self.client = client or get_supabase_service_client()

    # ==========================================================================
    # IDENTITY & AUTHORIZATION RESOLUTION
    # ==========================================================================

    async def resolve_mechanic_id(
        self,
        current_user: AuthenticatedUser,
        target_mechanic_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """
        Derive authoritative mechanic_profile_id from user session.
        - Mechanic users: Strictly locked to their own mechanic_profile.id. Client query param cannot override.
        - Admin/Support: Can inspect a specific mechanic via target_mechanic_id.
        - Customer users: Rejected with 403 Forbidden.
        """
        user_role_str = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )

        if user_role_str == UserRole.CUSTOMER.value:
            logger.warning(
                "mechanic_dashboard_access_denied_customer",
                user_id=str(current_user.id),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Operation requires mechanic role.",
            )

        if user_role_str in [UserRole.ADMIN.value, UserRole.SUPPORT.value]:
            if target_mechanic_id:
                # Verify requested mechanic exists
                m_res = (
                    self.client.table("mechanic_profiles")
                    .select("id")
                    .eq("id", str(target_mechanic_id))
                    .execute()
                )
                if not m_res.data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Mechanic profile not found.",
                    )
                return target_mechanic_id
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query parameter 'mechanic_id' is required for admin/support users.",
            )

        if user_role_str == UserRole.MECHANIC.value:
            # Resolve mechanic profile for authenticated user
            m_res = (
                self.client.table("mechanic_profiles")
                .select("id")
                .eq("user_id", str(current_user.id))
                .execute()
            )
            if not m_res.data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Mechanic profile details not found.",
                )
            own_profile_id = uuid.UUID(str(m_res.data[0]["id"]))

            # Cross-mechanic access prevention: if client passed an explicit target_mechanic_id that doesn't match
            if target_mechanic_id and target_mechanic_id != own_profile_id:
                logger.warning(
                    "cross_mechanic_dashboard_access_attempt",
                    user_id=str(current_user.id),
                    attempted_mechanic_id=str(target_mechanic_id),
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own mechanic dashboard.",
                )
            return own_profile_id

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Unauthorized role.",
        )

    # ==========================================================================
    # DATA RETRIEVAL HELPERS
    # ==========================================================================

    async def _get_mechanic_assignments_and_bookings(
        self,
        mechanic_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        """Fetch all assignments with associated booking data for mechanic."""
        asgn_res = (
            self.client.table("mechanic_assignments")
            .select("id, booking_id, assignment_status, created_at, bookings(id, booking_number, booking_status, payment_status, subtotal, additional_charges, discount_amount, tax_amount, total_amount, scheduled_at, created_at, updated_at)")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        raw_assignments = asgn_res.data or []

        results = []
        missing_booking_ids = []
        for a in raw_assignments:
            booking = a.get("bookings")
            if isinstance(booking, list) and len(booking) > 0:
                booking = booking[0]
            if not booking and a.get("booking_id"):
                missing_booking_ids.append(a.get("booking_id"))
            a["_resolved_booking"] = booking
            results.append(a)

        # Fallback if embedded bookings was not supported by mock/client
        if missing_booking_ids:
            b_res = (
                self.client.table("bookings")
                .select("id, booking_number, booking_status, payment_status, subtotal, additional_charges, discount_amount, tax_amount, total_amount, scheduled_at, created_at, updated_at")
                .in_("id", missing_booking_ids)
                .execute()
            )
            b_map = {str(b["id"]): b for b in (b_res.data or [])}
            for a in results:
                if not a.get("_resolved_booking"):
                    a["_resolved_booking"] = b_map.get(str(a.get("booking_id")))

        return results

    # ==========================================================================
    # 1. DASHBOARD OVERVIEW
    # ==========================================================================

    async def get_overview(self, mechanic_id: uuid.UUID) -> DashboardOverviewResponse:
        """
        Aggregate authoritative top-level dashboard metrics for the mechanic.
        Calculates:
        - Today's scheduled, completed, and cancelled jobs
        - Overall active, completed, and cancelled jobs
        - Total earned revenue and pending revenue using Decimal
        - Completion rate = completed / (completed + cancelled)
        - Authoritative average rating and review count
        """
        assignments = await self._get_mechanic_assignments_and_bookings(mechanic_id)

        now_utc = datetime.now(timezone.utc)
        today_date = now_utc.date()

        today_jobs_count = 0
        today_completed_count = 0
        today_cancelled_count = 0

        active_jobs_count = 0
        completed_jobs_count = 0
        cancelled_jobs_count = 0

        total_earnings = Decimal("0.00")
        pending_earnings = Decimal("0.00")

        for a in assignments:
            booking = a.get("_resolved_booking")
            if not booking:
                continue

            asgn_status = a.get("assignment_status")
            b_status = booking.get("booking_status")
            p_status = booking.get("payment_status")

            # Check if relevant to this mechanic:
            # - accepted or completed assignment
            # - or cancelled assignment where this mechanic was assigned
            if asgn_status not in ["accepted", "completed", "cancelled"]:
                continue

            # Parse scheduled / completion date
            sched_str = booking.get("scheduled_at") or booking.get("created_at")
            sched_date = None
            if sched_str:
                try:
                    sched_dt = parse_iso_datetime(sched_str)
                    if sched_dt:
                        sched_date = sched_dt.date()
                except Exception:
                    pass

            is_today = (sched_date == today_date)
            if is_today:
                today_jobs_count += 1
                if b_status in self.COMPLETED_STATUSES:
                    today_completed_count += 1
                elif b_status in self.CANCELLED_STATUSES:
                    today_cancelled_count += 1

            # Job status aggregation
            if b_status in self.ACTIVE_STATUSES and asgn_status == "accepted":
                active_jobs_count += 1
            elif b_status in self.COMPLETED_STATUSES:
                completed_jobs_count += 1
            elif b_status in self.CANCELLED_STATUSES:
                cancelled_jobs_count += 1

            # Financial calculation using Decimal
            gross_amount = Decimal(str(booking.get("subtotal") or "0.00"))
            additional_work = Decimal(str(booking.get("additional_charges") or "0.00"))
            # Attributable service amount = gross + approved additional work
            attributable_amount = gross_amount + additional_work

            # Exclude failed or refunded payments from earnings
            if p_status == "paid" or b_status == "paid":
                total_earnings += attributable_amount
            elif b_status in ["service_completed", "payment_pending"] and p_status not in ["failed", "refunded"]:
                pending_earnings += attributable_amount

        # Check authoritative payout ledger for earnings (Phase 8.7 reconciliation)
        try:
            payout_ledger_res = (
                self.client.table("mechanic_payout_ledger")
                .select("net_amount, status")
                .eq("mechanic_id", str(mechanic_id))
                .execute()
            )
            ledger_entries = payout_ledger_res.data or []
            if ledger_entries:
                total_earnings = Decimal("0.00")
                pending_earnings = Decimal("0.00")
                for entry in ledger_entries:
                    st = str(entry.get("status", "")).lower()
                    net_val = Decimal(str(entry.get("net_amount") or "0.00"))
                    if st in ["paid", "eligible"]:
                        total_earnings += net_val
                    elif st in ["pending", "processing"]:
                        pending_earnings += net_val
        except Exception as ledger_err:
            logger.debug("payout_ledger_query_fallback", error=str(ledger_err))

        # Fetch reviews and ratings
        rev_res = (
            self.client.table("reviews")
            .select("rating")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        reviews = rev_res.data or []
        review_count = len(reviews)
        if review_count > 0:
            avg_rating = round(sum(float(r["rating"]) for r in reviews) / review_count, 2)
        else:
            # Fallback to mechanic_profiles.average_rating if set
            m_prof = (
                self.client.table("mechanic_profiles")
                .select("average_rating")
                .eq("id", str(mechanic_id))
                .execute()
            )
            if m_prof.data and m_prof.data[0].get("average_rating") is not None:
                avg_rating = round(float(m_prof.data[0]["average_rating"]), 2)
            else:
                avg_rating = 0.0

        # Completion rate: completed / (completed + cancelled)
        completion_denom = completed_jobs_count + cancelled_jobs_count
        if completion_denom > 0:
            completion_rate = round((completed_jobs_count / completion_denom) * 100.0, 1)
        else:
            completion_rate = 0.0

        return DashboardOverviewResponse(
            today=TodayJobs(
                jobs=today_jobs_count,
                completed=today_completed_count,
                cancelled=today_cancelled_count,
            ),
            active_jobs=active_jobs_count,
            completed_jobs=completed_jobs_count,
            cancelled_jobs=cancelled_jobs_count,
            total_earnings=format_decimal(total_earnings),
            pending_earnings=format_decimal(pending_earnings),
            average_rating=avg_rating,
            review_count=review_count,
            completion_rate=completion_rate,
        )

    # ==========================================================================
    # 2. JOB STATISTICS & PERFORMANCE
    # ==========================================================================

    async def get_performance(
        self,
        mechanic_id: uuid.UUID,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> MechanicPerformanceResponse:
        """
        Calculate performance metrics with optional date range filter:
        - Job counts and completion rate
        - Rating distribution (1 to 5 breakdown)
        - Historical monthly breakdown of completed, cancelled, and earnings
        """
        from_dt = parse_iso_datetime(from_date, is_end_of_day=False)
        to_dt = parse_iso_datetime(to_date, is_end_of_day=True)

        assignments = await self._get_mechanic_assignments_and_bookings(mechanic_id)

        completed_jobs = 0
        cancelled_jobs = 0
        active_jobs = 0

        # Monthly aggregation: { "YYYY-MM": {"completed": 0, "cancelled": 0, "earnings": Decimal(0)} }
        monthly_map = defaultdict(lambda: {"completed": 0, "cancelled": 0, "earnings": Decimal("0.00")})

        for a in assignments:
            booking = a.get("_resolved_booking")
            if not booking:
                continue

            asgn_status = a.get("assignment_status")
            b_status = booking.get("booking_status")
            p_status = booking.get("payment_status")

            if asgn_status not in ["accepted", "completed", "cancelled"]:
                continue

            # Date filter matching
            sched_str = booking.get("scheduled_at") or booking.get("created_at")
            booking_dt = None
            if sched_str:
                try:
                    booking_dt = parse_iso_datetime(sched_str)
                except Exception:
                    pass

            if from_dt and booking_dt and booking_dt < from_dt:
                continue
            if to_dt and booking_dt and booking_dt > to_dt:
                continue

            # Monthly key
            m_key = booking_dt.strftime("%Y-%m") if booking_dt else "Unknown"

            if b_status in self.ACTIVE_STATUSES and asgn_status == "accepted":
                active_jobs += 1
            elif b_status in self.COMPLETED_STATUSES:
                completed_jobs += 1
                if m_key != "Unknown":
                    monthly_map[m_key]["completed"] += 1
            elif b_status in self.CANCELLED_STATUSES:
                cancelled_jobs += 1
                if m_key != "Unknown":
                    monthly_map[m_key]["cancelled"] += 1

            # Monthly earnings (only paid)
            if (p_status == "paid" or b_status == "paid") and m_key != "Unknown":
                gross = Decimal(str(booking.get("subtotal") or "0.00"))
                extra = Decimal(str(booking.get("additional_charges") or "0.00"))
                monthly_map[m_key]["earnings"] += (gross + extra)

        total_jobs = completed_jobs + cancelled_jobs + active_jobs

        # Completion rate
        denom = completed_jobs + cancelled_jobs
        completion_rate = round((completed_jobs / denom) * 100.0, 1) if denom > 0 else 0.0

        # Rating distribution from reviews table
        rev_res = (
            self.client.table("reviews")
            .select("rating, created_at")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        reviews = rev_res.data or []

        distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        total_rating_sum = 0
        filtered_review_count = 0

        for r in reviews:
            r_created_str = r.get("created_at")
            r_dt = parse_iso_datetime(r_created_str) if r_created_str else None
            if from_dt and r_dt and r_dt < from_dt:
                continue
            if to_dt and r_dt and r_dt > to_dt:
                continue

            r_val = r.get("rating")
            if r_val in [1, 2, 3, 4, 5]:
                distribution[str(r_val)] += 1
                total_rating_sum += r_val
                filtered_review_count += 1

        avg_rating = (
            round(total_rating_sum / filtered_review_count, 2)
            if filtered_review_count > 0
            else 0.0
        )

        # Build sorted monthly breakdown
        monthly_breakdown = []
        for m_str in sorted(monthly_map.keys(), reverse=True):
            data = monthly_map[m_str]
            monthly_breakdown.append(
                MonthlyBreakdown(
                    month=m_str,
                    completed=data["completed"],
                    cancelled=data["cancelled"],
                    earnings=format_decimal(data["earnings"]),
                )
            )

        return MechanicPerformanceResponse(
            total_jobs=total_jobs,
            completed_jobs=completed_jobs,
            cancelled_jobs=cancelled_jobs,
            active_jobs=active_jobs,
            completion_rate=completion_rate,
            average_rating=avg_rating,
            review_count=filtered_review_count,
            rating_distribution=distribution,
            monthly_breakdown=monthly_breakdown,
        )

    # ==========================================================================
    # 3. EARNINGS LIST & BREAKDOWN
    # ==========================================================================

    async def get_earnings(
        self,
        mechanic_id: uuid.UUID,
        from_date: str | None = None,
        to_date: str | None = None,
        status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EarningsListResponse:
        """
        List paginated earnings by booking for the mechanic.
        Features:
        - Strict limit clamping (1 to 100)
        - Date filtering
        - Status filtering (paid, pending, refunded, failed, unpaid)
        - Gross, additional work, deductions, and net amount calculated using Decimal
        - Exclusion of customer private payment secrets
        """
        safe_limit = min(max(1, limit), 100)
        safe_offset = max(0, offset)

        from_dt = parse_iso_datetime(from_date, is_end_of_day=False)
        to_dt = parse_iso_datetime(to_date, is_end_of_day=True)

        assignments = await self._get_mechanic_assignments_and_bookings(mechanic_id)

        all_items: list[EarningsItem] = []

        for a in assignments:
            booking = a.get("_resolved_booking")
            if not booking:
                continue

            asgn_status = a.get("assignment_status")
            if asgn_status not in ["accepted", "completed"]:
                continue

            sched_str = booking.get("scheduled_at") or booking.get("created_at")
            b_dt = parse_iso_datetime(sched_str) if sched_str else None
            if from_dt and b_dt and b_dt < from_dt:
                continue
            if to_dt and b_dt and b_dt > to_dt:
                continue

            raw_p_status = booking.get("payment_status")
            b_status = booking.get("booking_status")

            # Derive mapped payment status
            if raw_p_status == "paid" or b_status == "paid":
                mapped_status = "paid"
            elif raw_p_status == "refunded":
                mapped_status = "refunded"
            elif raw_p_status == "failed":
                mapped_status = "failed"
            elif b_status in ["service_completed", "payment_pending"]:
                mapped_status = "pending"
            else:
                mapped_status = raw_p_status or "unpaid"

            if status_filter and status_filter.lower() != "all":
                if mapped_status.lower() != status_filter.lower():
                    continue

            gross = Decimal(str(booking.get("subtotal") or "0.00"))
            additional = Decimal(str(booking.get("additional_charges") or "0.00"))
            deductions = Decimal("0.00")
            net = gross + additional - deductions

            # Check if an authoritative payout ledger entry exists for this booking (Phase 8.7)
            try:
                p_res = (
                    self.client.table("mechanic_payout_ledger")
                    .select("commission_amount, deduction_amount, net_amount, status")
                    .eq("booking_id", str(booking["id"]))
                    .execute()
                )
                if p_res.data and len(p_res.data) > 0:
                    p_item = p_res.data[0]
                    deductions = (
                        Decimal(str(p_item.get("commission_amount") or "0.00")) +
                        Decimal(str(p_item.get("deduction_amount") or "0.00"))
                    )
                    net = Decimal(str(p_item.get("net_amount") or "0.00"))
            except Exception:
                pass

            completed_at = booking.get("updated_at") if b_status in self.COMPLETED_STATUSES else None
            paid_at = booking.get("updated_at") if mapped_status == "paid" else None

            all_items.append(
                EarningsItem(
                    booking_id=safe_uuid(booking["id"]),
                    booking_number=booking.get("booking_number", "N/A"),
                    completed_at=completed_at,
                    gross_amount=format_decimal(gross),
                    additional_work_amount=format_decimal(additional),
                    deductions=format_decimal(deductions),
                    net_amount=format_decimal(net),
                    payment_status=mapped_status,
                    paid_at=paid_at,
                )
            )

        total_count = len(all_items)
        paginated_items = all_items[safe_offset : safe_offset + safe_limit]

        return EarningsListResponse(
            items=paginated_items,
            total=total_count,
            limit=safe_limit,
            offset=safe_offset,
        )

    # ==========================================================================
    # 4. RECENT JOBS
    # ==========================================================================

    async def get_recent_jobs(
        self,
        mechanic_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> RecentJobsResponse:
        """
        List recent jobs assigned to the mechanic with vehicle and service summary.
        Zero customer PII leakage (no phone, email, full address, or customer ID).
        """
        safe_limit = min(max(1, limit), 50)
        safe_offset = max(0, offset)

        assignments = await self._get_mechanic_assignments_and_bookings(mechanic_id)

        # Sort assignments by created_at or booking scheduled_at descending
        sorted_assignments = sorted(
            assignments,
            key=lambda a: a.get("_resolved_booking", {}).get("scheduled_at") or a.get("created_at") or "",
            reverse=True,
        )

        all_items: list[RecentJobItem] = []
        for a in sorted_assignments:
            booking = a.get("_resolved_booking")
            if not booking:
                continue

            gross = Decimal(str(booking.get("subtotal") or "0.00"))
            extra = Decimal(str(booking.get("additional_charges") or "0.00"))
            amount_str = format_decimal(gross + extra)

            service_summary = "Vehicle Service"
            vehicle_summary = "Vehicle"

            all_items.append(
                RecentJobItem(
                    booking_id=safe_uuid(booking["id"]),
                    booking_number=booking.get("booking_number", "N/A"),
                    service_summary=service_summary,
                    vehicle_summary=vehicle_summary,
                    booking_status=booking.get("booking_status", "pending"),
                    assignment_status=a.get("assignment_status", "offered"),
                    scheduled_at=booking.get("scheduled_at") or booking.get("created_at") or "",
                    amount=amount_str,
                    payment_status=booking.get("payment_status", "unpaid"),
                )
            )

        total_count = len(all_items)
        paginated_items = all_items[safe_offset : safe_offset + safe_limit]

        return RecentJobsResponse(
            items=paginated_items,
            total=total_count,
            limit=safe_limit,
            offset=safe_offset,
        )

    # ==========================================================================
    # 5. RECENT REVIEWS
    # ==========================================================================

    async def get_recent_reviews(
        self,
        mechanic_id: uuid.UUID,
        limit: int = 10,
        offset: int = 0,
    ) -> RecentReviewsResponse:
        """
        List recent reviews for the mechanic with privacy-masked customer names.
        Never exposes customer email, phone, or raw profile IDs.
        """
        safe_limit = min(max(1, limit), 50)
        safe_offset = max(0, offset)

        rev_res = (
            self.client.table("reviews")
            .select("id, booking_id, rating, review_text, created_at, customer_id, profiles!customer_id(full_name)")
            .eq("mechanic_id", str(mechanic_id))
            .order("created_at", desc=True)
            .range(safe_offset, safe_offset + safe_limit - 1)
            .execute()
        )
        raw_reviews = rev_res.data or []

        # Count total reviews
        count_res = (
            self.client.table("reviews")
            .select("id", count="exact")
            .eq("mechanic_id", str(mechanic_id))
            .execute()
        )
        total_count = count_res.count if hasattr(count_res, "count") and count_res.count is not None else len(raw_reviews)

        # Fallback profile lookup if not embedded
        missing_customer_ids = [
            r["customer_id"] for r in raw_reviews
            if not r.get("profiles") and r.get("customer_id")
        ]
        p_map = {}
        if missing_customer_ids:
            p_res = (
                self.client.table("profiles")
                .select("id, full_name")
                .in_("id", missing_customer_ids)
                .execute()
            )
            p_map = {str(p["id"]): p.get("full_name") for p in (p_res.data or [])}

        items: list[RecentReviewItem] = []
        for r in raw_reviews:
            prof = r.get("profiles")
            if isinstance(prof, dict):
                raw_name = prof.get("full_name")
            else:
                raw_name = p_map.get(str(r.get("customer_id")))

            masked_name = mask_customer_name(raw_name)

            items.append(
                RecentReviewItem(
                    id=safe_uuid(r["id"]),
                    booking_id=safe_uuid(r["booking_id"]),
                    rating=int(r["rating"]),
                    review_text=r.get("review_text"),
                    customer_name=masked_name,
                    created_at=str(r["created_at"]),
                )
            )

        return RecentReviewsResponse(
            items=items,
            total=total_count,
            limit=safe_limit,
            offset=safe_offset,
        )
