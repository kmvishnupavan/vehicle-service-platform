"""
Admin Operations, System Health & Financial Reconciliation Endpoints (Phase 9).

Mounts under /api/v1/admin/...
Strictly restricted to users with ADMIN and SUPPORT roles.
"""

from datetime import datetime, timezone
from typing import Any
import uuid
from fastapi import APIRouter, Depends, Query, status
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.safety import ProductionSafetyGuard
from app.db.dependencies import require_admin, require_support
from app.db.supabase import get_supabase_service_client
from app.schemas.admin_operations import (
    AdminSystemStatsResponse,
    AuditLogItem,
    AuditLogListResponse,
    ReconciliationDiscrepancyItem,
    ReconciliationReportResponse,
)
from app.schemas.user import AuthenticatedUser
from app.services.health_service import HealthService
from app.services.reconciliation_service import ReconciliationService

logger = get_logger("api.admin_operations")

def get_admin_db():
    """Returns Supabase service client for administrative operations."""
    return get_supabase_service_client()


router = APIRouter(prefix="/admin", tags=["Admin Operations"])


# ============================================================================
# 1. OPERATIONAL DASHBOARD STATS
# ============================================================================

@router.get(
    "/operations/stats",
    response_model=AdminSystemStatsResponse,
    summary="Get aggregated operational dashboard statistics",
    description="Aggregates system health, safety flags, and lifecycle counts across bookings, payments, payouts, and webhooks.",
)
async def get_operations_stats(
    current_user: AuthenticatedUser = Depends(require_support),
) -> AdminSystemStatsResponse:
    """Retrieve operational metrics for dashboard visualization."""
    client = get_admin_db()
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. System Health & Safety Guard
    _, health_payload = await HealthService.get_readiness()
    safety_guard = ProductionSafetyGuard.get_safety_status()

    # 2. Bookings breakdown
    bookings_breakdown: dict[str, int] = {
        "pending": 0,
        "searching_mechanic": 0,
        "assigned": 0,
        "en_route": 0,
        "in_service": 0,
        "completed": 0,
        "cancelled": 0,
        "disputed": 0,
    }
    try:
        b_res = client.table("bookings").select("status").execute()
        for b in b_res.data or []:
            st = str(b.get("status") or "").lower()
            if st in bookings_breakdown:
                bookings_breakdown[st] += 1
            elif "route" in st:
                bookings_breakdown["en_route"] += 1
            elif "progress" in st:
                bookings_breakdown["in_service"] += 1
            elif "assign" in st:
                bookings_breakdown["assigned"] += 1
    except Exception as e:
        logger.warning("stats_bookings_fetch_failed", error=str(e))

    # 3. Payments breakdown
    payments_breakdown: dict[str, int] = {
        "pending": 0,
        "captured": 0,
        "failed": 0,
        "refunded": 0,
    }
    try:
        p_res = client.table("payments").select("status").execute()
        for p in p_res.data or []:
            st = str(p.get("status") or "").lower()
            if st in payments_breakdown:
                payments_breakdown[st] += 1
    except Exception as e:
        logger.warning("stats_payments_fetch_failed", error=str(e))

    # 4. Payouts breakdown
    payouts_breakdown: dict[str, int] = {
        "eligible": 0,
        "approval_required": 0,
        "approved": 0,
        "processing": 0,
        "paid": 0,
        "failed": 0,
        "reversed": 0,
    }
    try:
        l_res = client.table("mechanic_payout_ledger").select("status").execute()
        for l in l_res.data or []:
            st = str(l.get("status") or "").lower()
            if st in payouts_breakdown:
                payouts_breakdown[st] += 1
    except Exception as e:
        logger.warning("stats_payouts_fetch_failed", error=str(e))

    # 5. Webhooks breakdown
    webhooks_breakdown: dict[str, int] = {
        "processing": 0,
        "processed": 0,
        "failed": 0,
        "duplicate": 0,
        "stale": 0,
    }
    try:
        w_res = client.table("webhook_events").select("status, processing_attempts").execute()
        for w in w_res.data or []:
            st = str(w.get("status") or "processed").lower()
            if st in webhooks_breakdown:
                webhooks_breakdown[st] += 1
            else:
                webhooks_breakdown["processed"] += 1
    except Exception as e:
        logger.warning("stats_webhooks_fetch_failed", error=str(e))

    # 6. Notifications breakdown
    notifications_breakdown: dict[str, int] = {
        "queued": 0,
        "sent": 0,
        "failed": 0,
    }
    try:
        n_res = client.table("notifications").select("id, is_read").execute()
        notifications_breakdown["sent"] = len(n_res.data or [])
    except Exception as e:
        logger.warning("stats_notifications_fetch_failed", error=str(e))

    return AdminSystemStatsResponse(
        environment=settings.ENVIRONMENT,
        system_health=health_payload,
        safety_guard=safety_guard,
        bookings_breakdown=bookings_breakdown,
        payments_breakdown=payments_breakdown,
        payouts_breakdown=payouts_breakdown,
        webhooks_breakdown=webhooks_breakdown,
        notifications_breakdown=notifications_breakdown,
        timestamp=now_iso,
        bookings=bookings_breakdown,
        payments=payments_breakdown,
        payouts=payouts_breakdown,
        webhooks=webhooks_breakdown,
    )


# ============================================================================
# 2. RECONCILIATION REPORTS
# ============================================================================

@router.get(
    "/reconciliation/payments",
    response_model=ReconciliationReportResponse,
    summary="Scan and detect payment discrepancies",
    description="Identifies payment records with unpaid bookings, stuck pending status, or duplicate transactions.",
)
async def get_reconciliation_payments(
    persist: bool = Query(default=False, description="Persist detected discrepancies to database"),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ReconciliationReportResponse:
    """Run payment reconciliation scanner."""
    svc = ReconciliationService(db=get_admin_db())
    items = await svc.reconcile_payments(persist_discrepancies=persist)
    discrepancies = [ReconciliationDiscrepancyItem.model_validate(it) for it in items]
    return ReconciliationReportResponse(
        subsystem="payments",
        discrepancies=discrepancies,
        count=len(discrepancies),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/reconciliation/payouts",
    response_model=ReconciliationReportResponse,
    summary="Scan and detect payout discrepancies",
    description="Identifies mechanic payouts stuck in processing, paid without provider references, or in unapproved batches.",
)
async def get_reconciliation_payouts(
    persist: bool = Query(default=False, description="Persist detected discrepancies to database"),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ReconciliationReportResponse:
    """Run payout reconciliation scanner."""
    svc = ReconciliationService(db=get_admin_db())
    items = await svc.reconcile_payouts(persist_discrepancies=persist)
    discrepancies = [ReconciliationDiscrepancyItem.model_validate(it) for it in items]
    return ReconciliationReportResponse(
        subsystem="payouts",
        discrepancies=discrepancies,
        count=len(discrepancies),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/reconciliation/settlements",
    response_model=ReconciliationReportResponse,
    summary="Scan and detect settlement batch discrepancies",
    description="Identifies total amount calculation mismatches, terminal item batch lag, or approval SLA breaches.",
)
async def get_reconciliation_settlements(
    persist: bool = Query(default=False, description="Persist detected discrepancies to database"),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ReconciliationReportResponse:
    """Run settlement batch reconciliation scanner."""
    svc = ReconciliationService(db=get_admin_db())
    items = await svc.reconcile_settlements(persist_discrepancies=persist)
    discrepancies = [ReconciliationDiscrepancyItem.model_validate(it) for it in items]
    return ReconciliationReportResponse(
        subsystem="settlements",
        discrepancies=discrepancies,
        count=len(discrepancies),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/reconciliation/webhooks",
    response_model=ReconciliationReportResponse,
    summary="Scan and detect webhook anomalies",
    description="Identifies stuck reservations (>5m) or events with repeated delivery failures.",
)
async def get_reconciliation_webhooks(
    persist: bool = Query(default=False, description="Persist detected discrepancies to database"),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> ReconciliationReportResponse:
    """Run webhook reconciliation scanner."""
    svc = ReconciliationService(db=get_admin_db())
    items = await svc.reconcile_webhooks(persist_discrepancies=persist)
    discrepancies = [ReconciliationDiscrepancyItem.model_validate(it) for it in items]
    return ReconciliationReportResponse(
        subsystem="webhooks",
        discrepancies=discrepancies,
        count=len(discrepancies),
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )


# ============================================================================
# 3. AUDIT LOG SEARCH & VIEWER
# ============================================================================

@router.get(
    "/audit-logs",
    response_model=AuditLogListResponse,
    summary="Search immutable system audit logs",
    description="Filter and paginate platform audit events by actor, action, entity, date range, or request ID.",
)
async def get_audit_logs(
    actor_id: uuid.UUID | None = Query(default=None, description="Filter by actor user UUID"),
    action: str | None = Query(default=None, description="Filter by action name"),
    entity_type: str | None = Query(default=None, description="Filter by entity type (booking, payment, batch)"),
    request_id: str | None = Query(default=None, description="Filter by exact request ID"),
    limit: int = Query(default=25, ge=1, le=100, description="Page limit"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    current_user: AuthenticatedUser = Depends(require_admin),
) -> AuditLogListResponse:
    """Retrieve paginated audit logs."""
    client = get_admin_db()
    query = client.table("audit_logs").select("*", count="exact")

    if actor_id:
        query = query.eq("actor_id", str(actor_id))
    if action:
        query = query.ilike("action", f"%{action}%")
    if entity_type:
        query = query.eq("entity_type", entity_type)
    if request_id:
        query = query.eq("request_id", request_id)

    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)
    res = query.execute()

    items = [
        AuditLogItem(
            id=row["id"],
            actor_id=row.get("actor_id"),
            actor_role=row.get("actor_role"),
            action=row.get("action") or "UNKNOWN",
            entity_type=row.get("entity_type") or "system",
            entity_id=row.get("entity_id"),
            old_data=row.get("old_data"),
            new_data=row.get("new_data"),
            ip_address=row.get("ip_address"),
            request_id=row.get("request_id"),
            severity=row.get("severity") or "info",
            created_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
        )
        for row in res.data or []
    ]

    total = res.count if res.count is not None else len(items)
    return AuditLogListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
