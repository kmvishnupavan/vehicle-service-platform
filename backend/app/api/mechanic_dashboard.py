"""
Mechanic Dashboard API Router (Phase 8.6).

Exposes authoritative dashboard endpoints:
- GET /api/v1/mechanics/dashboard/overview
- GET /api/v1/mechanics/dashboard/performance
- GET /api/v1/mechanics/dashboard/earnings
- GET /api/v1/mechanics/dashboard/recent-jobs
- GET /api/v1/mechanics/dashboard/recent-reviews
"""

from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, Query, status
from app.db.dependencies import get_current_user
from app.schemas.mechanic_dashboard import (
    DashboardOverviewResponse,
    EarningsListResponse,
    MechanicPerformanceResponse,
    RecentJobsResponse,
    RecentReviewsResponse,
)
from app.schemas.user import AuthenticatedUser
from app.services.mechanic_dashboard_service import MechanicDashboardService

router = APIRouter(prefix="/mechanics/dashboard", tags=["Mechanic Dashboard"])


def get_dashboard_service() -> MechanicDashboardService:
    """Dependency injector for MechanicDashboardService."""
    return MechanicDashboardService()


@router.get(
    "/overview",
    response_model=DashboardOverviewResponse,
    summary="Get authoritative mechanic dashboard overview statistics",
)
async def get_dashboard_overview(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(
        None,
        description="Target mechanic ID (admin/support only; ignored or verified for mechanics)",
    ),
    service: MechanicDashboardService = Depends(get_dashboard_service),
) -> DashboardOverviewResponse:
    """
    Retrieve top-level operational and financial KPIs for the mechanic.
    Calculates today's metrics, active/completed/cancelled jobs, total/pending earnings,
    completion rate, and rating aggregates.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_overview(mechanic_id=effective_mech_id)


@router.get(
    "/performance",
    response_model=MechanicPerformanceResponse,
    summary="Get detailed performance statistics and rating distribution",
)
async def get_dashboard_performance(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD or ISO timestamp)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD or ISO timestamp)"),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: MechanicDashboardService = Depends(get_dashboard_service),
) -> MechanicPerformanceResponse:
    """
    Retrieve performance statistics including job counts, completion rate,
    1-to-5 star rating breakdown, and monthly historical breakdown.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_performance(
        mechanic_id=effective_mech_id,
        from_date=from_date,
        to_date=to_date,
    )


@router.get(
    "/earnings",
    response_model=EarningsListResponse,
    summary="Get paginated earnings breakdown by booking",
)
async def get_dashboard_earnings(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD or ISO timestamp)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD or ISO timestamp)"),
    status: str | None = Query(None, description="Payment status filter (all, paid, pending, refunded, failed)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    offset: int = Query(0, ge=0, description="Items offset"),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: MechanicDashboardService = Depends(get_dashboard_service),
) -> EarningsListResponse:
    """
    Retrieve paginated earnings with itemized gross, additional work, and net amounts.
    Authoritatively isolates customer discounts and platform taxes from mechanic earnings.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_earnings(
        mechanic_id=effective_mech_id,
        from_date=from_date,
        to_date=to_date,
        status_filter=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/recent-jobs",
    response_model=RecentJobsResponse,
    summary="Get recent jobs for the mechanic",
)
async def get_dashboard_recent_jobs(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    offset: int = Query(0, ge=0, description="Items offset"),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: MechanicDashboardService = Depends(get_dashboard_service),
) -> RecentJobsResponse:
    """
    Retrieve recently assigned jobs with service and vehicle summaries.
    Strictly excludes customer contact PII (no phone number or email).
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_recent_jobs(
        mechanic_id=effective_mech_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/recent-reviews",
    response_model=RecentReviewsResponse,
    summary="Get recent customer reviews for the mechanic",
)
async def get_dashboard_recent_reviews(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: int = Query(10, ge=1, le=50, description="Items per page (max 50)"),
    offset: int = Query(0, ge=0, description="Items offset"),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: MechanicDashboardService = Depends(get_dashboard_service),
) -> RecentReviewsResponse:
    """
    Retrieve recently submitted customer reviews with ratings and comments.
    Customer names are privacy-masked; zero private identifiers are exposed.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_recent_reviews(
        mechanic_id=effective_mech_id,
        limit=limit,
        offset=offset,
    )
