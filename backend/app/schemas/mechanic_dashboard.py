"""
Mechanic Dashboard Pydantic Schemas (Phase 8.6).

Defines authoritative response models and filter parameters for:
- Dashboard Overview (today metrics, active/completed/cancelled counts, earnings, ratings)
- Performance and Statistics (completion rate, rating distribution 1-5, monthly breakdown)
- Authoritative Earnings (gross, additional work, deductions, net amounts, payment status)
- Recent Jobs and Reviews with strict PII protection
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


class TodayJobs(BaseModel):
    """Jobs summary for the current day."""
    model_config = ConfigDict(from_attributes=True)

    jobs: int = Field(0, ge=0, description="Total jobs scheduled for today")
    completed: int = Field(0, ge=0, description="Total jobs completed today")
    cancelled: int = Field(0, ge=0, description="Total jobs cancelled today")


class DashboardOverviewResponse(BaseModel):
    """Authoritative top-level dashboard statistics."""
    model_config = ConfigDict(from_attributes=True)

    today: TodayJobs
    active_jobs: int = Field(0, ge=0, description="Currently active jobs in progress")
    completed_jobs: int = Field(0, ge=0, description="Total completed jobs")
    cancelled_jobs: int = Field(0, ge=0, description="Total cancelled jobs")
    total_earnings: str = Field("0.00", description="Authoritative settled earnings (INR) formatted to 2 decimals")
    pending_earnings: str = Field("0.00", description="Authoritative pending earnings (INR) formatted to 2 decimals")
    average_rating: float = Field(0.0, ge=0.0, le=5.0, description="Average review rating")
    review_count: int = Field(0, ge=0, description="Total number of reviews")
    completion_rate: float = Field(0.0, ge=0.0, le=100.0, description="Job completion rate percentage")


class MonthlyBreakdown(BaseModel):
    """Monthly performance and earnings breakdown."""
    model_config = ConfigDict(from_attributes=True)

    month: str = Field(..., description="Year and month in YYYY-MM format")
    completed: int = Field(0, ge=0, description="Completed jobs in this month")
    cancelled: int = Field(0, ge=0, description="Cancelled jobs in this month")
    earnings: str = Field("0.00", description="Earnings in this month formatted to 2 decimals")


class MechanicPerformanceResponse(BaseModel):
    """Detailed performance metrics and rating distribution."""
    model_config = ConfigDict(from_attributes=True)

    total_jobs: int = Field(0, ge=0, description="Total jobs in period")
    completed_jobs: int = Field(0, ge=0, description="Completed jobs in period")
    cancelled_jobs: int = Field(0, ge=0, description="Cancelled jobs in period")
    active_jobs: int = Field(0, ge=0, description="Active jobs in progress")
    completion_rate: float = Field(0.0, ge=0.0, le=100.0, description="Completion percentage completed/(completed+cancelled)")
    average_rating: float = Field(0.0, ge=0.0, le=5.0, description="Average rating in period")
    review_count: int = Field(0, ge=0, description="Total reviews in period")
    rating_distribution: dict[str, int] = Field(
        default_factory=lambda: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        description="Rating distribution breakdown for stars 1 through 5",
    )
    monthly_breakdown: list[MonthlyBreakdown] = Field(
        default_factory=list,
        description="Historical monthly breakdown",
    )


class EarningsItem(BaseModel):
    """Line item representing earnings attributable to a booking."""
    model_config = ConfigDict(from_attributes=True)

    booking_id: uuid.UUID = Field(..., description="Unique booking UUID")
    booking_number: str = Field(..., description="Human-readable booking number")
    completed_at: str | None = Field(default=None, description="ISO completion timestamp")
    gross_amount: str = Field("0.00", description="Base service subtotal (INR)")
    additional_work_amount: str = Field("0.00", description="Approved additional work subtotal (INR)")
    deductions: str = Field("0.00", description="Applicable platform charges / commission deductions (INR)")
    net_amount: str = Field("0.00", description="Net mechanic earnings (INR)")
    payment_status: str = Field(..., description="Payment status (paid, pending, refunded, failed, unpaid)")
    paid_at: str | None = Field(default=None, description="ISO payment settlement timestamp")


class EarningsListResponse(BaseModel):
    """Paginated list of mechanic earnings."""
    model_config = ConfigDict(from_attributes=True)

    items: list[EarningsItem]
    total: int = Field(..., ge=0, description="Total matching earnings records")
    limit: int = Field(..., ge=1, le=100, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")


class RecentJobItem(BaseModel):
    """Summary of a recent booking for mechanic dashboard."""
    model_config = ConfigDict(from_attributes=True)

    booking_id: uuid.UUID = Field(..., description="Unique booking UUID")
    booking_number: str = Field(..., description="Human-readable booking number")
    service_summary: str = Field(..., description="Summary of service items")
    vehicle_summary: str = Field(..., description="Privacy-safe vehicle summary (Make Model Year)")
    booking_status: str = Field(..., description="Current booking lifecycle status")
    assignment_status: str = Field(..., description="Mechanic assignment status")
    scheduled_at: str = Field(..., description="Scheduled appointment timestamp")
    amount: str = Field("0.00", description="Attributable booking amount formatted to 2 decimals")
    payment_status: str = Field(..., description="Booking payment status")


class RecentJobsResponse(BaseModel):
    """Paginated list of recent jobs."""
    model_config = ConfigDict(from_attributes=True)

    items: list[RecentJobItem]
    total: int = Field(..., ge=0, description="Total matching jobs")
    limit: int = Field(..., ge=1, le=50, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")


class RecentReviewItem(BaseModel):
    """Customer review summary with masked name and no PII."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Review UUID")
    booking_id: uuid.UUID = Field(..., description="Associated booking UUID")
    rating: int = Field(..., ge=1, le=5, description="Star rating 1-5")
    review_text: str | None = Field(default=None, description="Customer review comment")
    customer_name: str = Field(..., description="Privacy-masked customer display name")
    created_at: str = Field(..., description="Creation ISO timestamp")


class RecentReviewsResponse(BaseModel):
    """Paginated list of recent reviews."""
    model_config = ConfigDict(from_attributes=True)

    items: list[RecentReviewItem]
    total: int = Field(..., ge=0, description="Total reviews count")
    limit: int = Field(..., ge=1, le=50, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")
