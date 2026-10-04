"""
Mechanic Payout Ledger & Settlement API Router (Phase 8.7).

Authoritative endpoints:
- GET /api/v1/mechanics/payouts
- GET /api/v1/mechanics/payouts/summary
- GET /api/v1/mechanics/payouts/{payout_id}

Strict security:
- Mechanic identity derived directly from authenticated JWT (never trusted from raw client input).
- Cross-mechanic isolation: mechanics cannot read other mechanics' ledger lines.
- Customers forbidden (403).
- Strict pagination, date, and status validation.
"""

from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, Query
from app.db.dependencies import get_current_user
from app.schemas.payout import PayoutListResponse, PayoutResponse, PayoutSummary
from app.schemas.user import AuthenticatedUser
from app.services.payout_service import PayoutService

router = APIRouter(prefix="/mechanics/payouts", tags=["Mechanic Payouts"])


def get_payout_service() -> PayoutService:
    """Dependency injector for PayoutService."""
    return PayoutService()


@router.get(
    "",
    response_model=PayoutListResponse,
    summary="List paginated mechanic payout ledger entries",
)
async def list_mechanic_payouts(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD or ISO timestamp)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD or ISO timestamp)"),
    status: str | None = Query(None, description="Payout status filter (pending, eligible, processing, paid, failed, reversed, cancelled)"),
    limit: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    offset: int = Query(0, ge=0, description="Items offset"),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutService = Depends(get_payout_service),
) -> PayoutListResponse:
    """
    Retrieve paginated payout ledger entries for the authenticated mechanic.
    Guarantees strict Decimal money handling and zero leakage of raw provider secrets.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.list_payouts(
        mechanic_id=effective_mech_id,
        from_date=from_date,
        to_date=to_date,
        status_filter=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=PayoutSummary,
    summary="Get aggregated financial summary of mechanic payouts",
)
async def get_mechanic_payout_summary(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutService = Depends(get_payout_service),
) -> PayoutSummary:
    """
    Aggregate authoritative financial balances (total gross, commission, deductions,
    net, pending, eligible, processing, paid, reversed) from the ledger.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_payout_summary(mechanic_id=effective_mech_id)


@router.get(
    "/{payout_id}",
    response_model=PayoutResponse,
    summary="Get single payout ledger entry by ID",
)
async def get_payout_by_id(
    payout_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutService = Depends(get_payout_service),
) -> PayoutResponse:
    """
    Retrieve a specific payout ledger entry.
    Verifies ownership if accessed by a mechanic.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.get_payout_by_id(
        payout_id=payout_id,
        mechanic_id=effective_mech_id,
    )
