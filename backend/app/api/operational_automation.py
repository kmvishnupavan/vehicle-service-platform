"""
Operational Automation, Scheduled Bookings & Reliability API Endpoints (Phase 13).
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.logging import get_logger
from app.db.dependencies import (
    get_current_user,
    require_customer,
    require_admin_or_support,
    require_mechanic,
)
from app.schemas.operational_automation import (
    BackgroundJobExecutionSummary,
    LocationAnomalyRecord,
    MatchingPolicyCreate,
    MatchingPolicyResponse,
    OperationalMetricsResponse,
    RunJobsRequest,
    ScheduledBookingCreate,
    ScheduledBookingResponse,
)
from app.services.background_jobs import BackgroundJobRunner, BackgroundJobsService
from app.services.location_reliability_service import LocationReliabilityService
from app.services.matching_policy_service import MatchingPolicyService
from app.services.operational_metrics_service import OperationalMetricsService
from app.services.scheduled_booking_service import ScheduledBookingService

logger = get_logger("api.operational_automation")
router = APIRouter(tags=["Operational Automation & Reliability"])


# =============================================================================
# 1. Scheduled Bookings (Customer Facing)
# =============================================================================

@router.post(
    "/bookings/{booking_id}/schedule",
    response_model=ScheduledBookingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a service booking",
)
async def schedule_booking(
    booking_id: uuid.UUID,
    payload: ScheduledBookingCreate,
    current_user: Any = Depends(require_customer),
):
    """Customer schedules service within a specific date/time window."""
    svc = ScheduledBookingService()
    user_id = current_user.id if hasattr(current_user, "id") else uuid.UUID(current_user["id"])
    rec = await svc.schedule_booking(booking_id, user_id, payload)
    return ScheduledBookingResponse(**rec)


@router.get(
    "/bookings/{booking_id}/schedule",
    response_model=ScheduledBookingResponse | None,
    summary="Get scheduled booking window",
)
async def get_scheduled_booking(
    booking_id: uuid.UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Retrieve schedule window and dispatch status for a booking."""
    svc = ScheduledBookingService()
    rec = await svc.get_scheduled_booking(booking_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No schedule found for booking.")
    return ScheduledBookingResponse(**rec)


@router.delete(
    "/bookings/{booking_id}/schedule",
    summary="Cancel scheduled booking",
)
async def cancel_scheduled_booking(
    booking_id: uuid.UUID,
    reason: str = Query(default="Customer requested schedule cancellation"),
    current_user: Any = Depends(require_customer),
):
    """Customer cancels a scheduled booking prior to dispatch."""
    svc = ScheduledBookingService()
    user_id = current_user.id if hasattr(current_user, "id") else uuid.UUID(current_user["id"])
    return await svc.cancel_scheduled_booking(booking_id, user_id, reason)


@router.get(
    "/admin/scheduled-bookings",
    response_model=list[ScheduledBookingResponse],
    summary="List scheduled bookings for admin monitoring",
    dependencies=[Depends(require_admin_or_support)],
)
async def list_scheduled_bookings(
    status_filter: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin lists scheduled bookings with optional status filtering."""
    svc = ScheduledBookingService()
    query = svc.client.table("scheduled_bookings").select("*").order("scheduled_start_at", desc=False)
    if status_filter:
        query = query.eq("status", status_filter)
    res = query.limit(limit).execute()
    return [ScheduledBookingResponse.model_validate(r) for r in (res.data or [])]


@router.get(
    "/mechanics/scheduled-jobs",
    response_model=list[dict[str, Any]],
    summary="List assigned upcoming scheduled jobs for mechanic",
    dependencies=[Depends(require_mechanic)],
)
async def list_mechanic_scheduled_jobs(
    current_user: Any = Depends(require_mechanic),
    limit: int = Query(default=20, ge=1, le=50),
):
    """Mechanic lists their upcoming assigned scheduled bookings and preparation info."""
    svc = ScheduledBookingService()
    mechanic_id = str(current_user.id if hasattr(current_user, "id") else current_user["id"])

    res = (
        svc.client.table("bookings")
        .select("id, booking_number, booking_status, scheduled_at, total_amount, address, customer_id")
        .eq("assigned_mechanic_id", mechanic_id)
        .order("scheduled_at", desc=False)
        .limit(limit)
        .execute()
    )
    return res.data or []


# =============================================================================
# 2. Background Jobs Execution & Observability (Admin)
# =============================================================================

@router.post(
    "/admin/background-jobs/run",
    response_model=list[dict[str, Any]],
    summary="Trigger operational background jobs",
    dependencies=[Depends(require_admin_or_support)],
)
async def run_background_jobs(
    payload: RunJobsRequest | None = None,
):
    """Admin triggers background job execution on demand with distributed locking."""
    runner = BackgroundJobRunner()
    jobs_svc = BackgroundJobsService()

    all_jobs = {
        "expire_mechanic_offers": jobs_svc.job_expire_mechanic_offers,
        "advance_expired_matching_sessions": jobs_svc.job_advance_expired_matching_sessions,
        "reconcile_webhook_reservations": jobs_svc.job_reconcile_webhook_reservations,
        "reconcile_pending_payments": jobs_svc.job_reconcile_pending_payments,
        "reconcile_payouts": jobs_svc.job_reconcile_payouts,
        "retry_failed_notifications": jobs_svc.job_retry_failed_notifications,
        "dispatch_scheduled_bookings": jobs_svc.job_dispatch_scheduled_bookings,
        "refresh_operational_metrics": jobs_svc.job_refresh_operational_metrics,
    }

    selected = payload.job_names if (payload and payload.job_names) else list(all_jobs.keys())
    summaries = []

    for name in selected:
        fn = all_jobs.get(name)
        if fn:
            res = await runner.execute_job(name, fn)
            summaries.append(res)

    return summaries


@router.get(
    "/admin/background-jobs/history",
    response_model=list[BackgroundJobExecutionSummary],
    summary="List background job execution history",
    dependencies=[Depends(require_admin_or_support)],
)
async def list_background_job_history(
    limit: int = Query(default=30, ge=1, le=100),
):
    """List recent background job executions and status."""
    runner = BackgroundJobRunner()
    res = (
        runner.client.table("background_job_executions")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [BackgroundJobExecutionSummary.model_validate(r) for r in (res.data or [])]


# =============================================================================
# 3. Matching Policy Governance (Admin)
# =============================================================================

@router.get(
    "/admin/matching-policies",
    response_model=list[MatchingPolicyResponse],
    summary="List versioned matching policies",
    dependencies=[Depends(require_admin_or_support)],
)
async def list_matching_policies():
    """List all versioned matching policies."""
    svc = MatchingPolicyService()
    policies = await svc.list_policies()
    return [MatchingPolicyResponse(**p) for p in policies]


@router.post(
    "/admin/matching-policies",
    response_model=MatchingPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a matching policy draft",
    dependencies=[Depends(require_admin_or_support)],
)
async def create_matching_policy(
    payload: MatchingPolicyCreate,
    current_user: Any = Depends(get_current_user),
):
    """Admin creates a new matching policy draft with validated weights (sum = 1.000)."""
    svc = MatchingPolicyService()
    admin_id = current_user.id if hasattr(current_user, "id") else uuid.UUID(current_user["id"])
    created = await svc.create_policy_draft(payload, admin_id=admin_id)
    return MatchingPolicyResponse(**created)


@router.post(
    "/admin/matching-policies/{policy_version}/activate",
    response_model=MatchingPolicyResponse,
    summary="Activate a matching policy",
    dependencies=[Depends(require_admin_or_support)],
)
async def activate_matching_policy(
    policy_version: str,
    current_user: Any = Depends(get_current_user),
):
    """Admin atomically activates a matching policy, deactivating all others."""
    svc = MatchingPolicyService()
    admin_id = current_user.id if hasattr(current_user, "id") else uuid.UUID(current_user["id"])
    activated = await svc.activate_policy(policy_version, admin_id=admin_id)
    return MatchingPolicyResponse(**activated)


# =============================================================================
# 4. Location Quality & Anomalies (Admin)
# =============================================================================

@router.get(
    "/admin/location-anomalies",
    response_model=list[LocationAnomalyRecord],
    summary="List detected GPS location anomalies",
    dependencies=[Depends(require_admin_or_support)],
)
async def list_location_anomalies(
    status_filter: str | None = Query(default=None),
    severity_filter: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Admin lists detected mechanic GPS anomalies."""
    runner = BackgroundJobRunner()
    query = runner.client.table("mechanic_location_anomalies").select("*").order("detected_at", desc=True)
    if status_filter:
        query = query.eq("status", status_filter)
    if severity_filter:
        query = query.eq("severity", severity_filter)
    res = query.limit(limit).execute()
    return [LocationAnomalyRecord.model_validate(r) for r in (res.data or [])]


# =============================================================================
# 5. Operational Metrics (Admin)
# =============================================================================

@router.get(
    "/admin/operational-metrics",
    response_model=OperationalMetricsResponse,
    summary="Get current operational platform metrics",
    dependencies=[Depends(require_admin_or_support)],
)
async def get_operational_metrics():
    """Retrieve current platform operational health metrics."""
    svc = OperationalMetricsService()
    return await svc.get_latest_metrics()


@router.get(
    "/admin/operational-metrics/history",
    response_model=list[OperationalMetricsResponse],
    summary="Get historical operational metrics",
    dependencies=[Depends(require_admin_or_support)],
)
async def get_operational_metrics_history(
    limit: int = Query(default=30, ge=1, le=100),
):
    """Retrieve historical snapshots of operational health metrics."""
    svc = OperationalMetricsService()
    return await svc.get_metrics_history(limit=limit)
