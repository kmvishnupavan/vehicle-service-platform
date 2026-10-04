"""
Admin Settlement Management & Maker-Checker API Router (Phase 8.9).

Endpoints:
- POST   /api/v1/admin/settlements
- GET    /api/v1/admin/settlements
- GET    /api/v1/admin/settlements/policy
- PATCH  /api/v1/admin/settlements/policy
- GET    /api/v1/admin/settlements/{batch_id}
- POST   /api/v1/admin/settlements/{batch_id}/submit-for-approval
- POST   /api/v1/admin/settlements/{batch_id}/approve
- POST   /api/v1/admin/settlements/{batch_id}/reject
- POST   /api/v1/admin/settlements/{batch_id}/cancel
- POST   /api/v1/admin/settlements/{batch_id}/process

Security & Authorization:
- Derives actor identity strictly from verified server JWT session.
- Enforces Maker != Checker: Maker is strictly prohibited from approving or rejecting their own batch.
- Mechanics and Customers are denied with HTTP 403.
- All actions generate immutable records in public.settlement_batch_approvals and public.audit_logs.
"""

from typing import Annotated
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.db.dependencies import get_current_user, require_admin, require_support
from app.schemas.payout_account import (
    SettlementApprovalPolicyResponse,
    SettlementApprovalPolicyUpdateRequest,
    SettlementApprovalRequest,
    SettlementBatchDetailResponse,
    SettlementBatchListResponse,
    SettlementBatchResponse,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.payout_account_service import PayoutAccountService

router = APIRouter(prefix="/admin/settlements", tags=["Admin Settlement Maker-Checker"])


def get_account_service() -> PayoutAccountService:
    """Dependency injector for PayoutAccountService."""
    return PayoutAccountService()


@router.post(
    "",
    response_model=SettlementBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a settlement batch from eligible payouts (Maker action)",
)
async def create_batch(
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    payout_ids: list[uuid.UUID] | None = None,
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Maker action: Creates a settlement batch aggregating eligible payouts for mechanics
    with verified bank accounts. Evaluates approval threshold policy to set initial status.
    """
    return await service.create_settlement_batch(
        eligible_payout_ids=payout_ids,
        created_by=current_user.id,
    )


@router.get(
    "",
    response_model=SettlementBatchListResponse,
    summary="List settlement batches with pagination and status filter",
)
async def list_batches(
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    status: str | None = Query(None, description="Filter by batch status (or 'all')"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchListResponse:
    """List settlement batches with item count and amounts."""
    return await service.list_batches(
        status_filter=status,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/policy",
    response_model=SettlementApprovalPolicyResponse,
    summary="Get active settlement approval threshold policy",
)
async def get_policy(
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementApprovalPolicyResponse:
    """Retrieve current threshold amount and maker-checker requirement configuration."""
    return await service.get_approval_policy()


@router.patch(
    "/policy",
    response_model=SettlementApprovalPolicyResponse,
    summary="Update settlement approval threshold policy (Admin only)",
)
async def update_policy(
    payload: SettlementApprovalPolicyUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_admin)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementApprovalPolicyResponse:
    """Configure high-value settlement thresholds and checker requirement."""
    return await service.update_approval_policy(
        threshold_amount=payload.threshold_amount,
        requires_checker=payload.requires_checker,
        is_active=payload.is_active,
        actor_id=current_user.id,
    )


@router.get(
    "/{batch_id}",
    response_model=SettlementBatchDetailResponse,
    summary="Get settlement batch details, payout items, and approval history",
)
async def get_batch_details(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchDetailResponse:
    """Retrieve full batch details, approval trail, and associated ledger items."""
    return await service.get_batch_details(batch_id=batch_id)


@router.post(
    "/{batch_id}/submit-for-approval",
    response_model=SettlementBatchResponse,
    summary="Submit draft settlement batch for checker review (Maker action)",
)
async def submit_for_approval(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """Transitions batch from draft to approval_required and dispatches notifications."""
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.submit_batch_for_approval(
        batch_id=batch_id,
        actor_id=current_user.id,
        actor_role=user_role_str,
    )


@router.post(
    "/{batch_id}/approve",
    response_model=SettlementBatchResponse,
    summary="Approve settlement batch (Checker action — Maker != Checker)",
)
async def approve_batch(
    batch_id: uuid.UUID,
    payload: SettlementApprovalRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Checker approves a batch in approval_required status.
    Strictly verifies that current_user.id != batch.created_by.
    """
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.approve_settlement_batch(
        batch_id=batch_id,
        checker_id=current_user.id,
        checker_role=user_role_str,
        reason=payload.reason,
    )


@router.post(
    "/{batch_id}/reject",
    response_model=SettlementBatchResponse,
    summary="Reject settlement batch (Checker action — Maker != Checker)",
)
async def reject_batch(
    batch_id: uuid.UUID,
    payload: SettlementApprovalRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Checker rejects batch. Payouts are returned to eligible status.
    Strictly verifies that current_user.id != batch.created_by.
    """
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.reject_settlement_batch(
        batch_id=batch_id,
        checker_id=current_user.id,
        checker_role=user_role_str,
        reason=payload.reason,
    )


@router.post(
    "/{batch_id}/cancel",
    response_model=SettlementBatchResponse,
    summary="Cancel settlement batch and release ledger items",
)
async def cancel_batch(
    batch_id: uuid.UUID,
    payload: SettlementApprovalRequest,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """Cancels batch and resets payout ledger items back to eligible."""
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.cancel_settlement_batch(
        batch_id=batch_id,
        actor_id=current_user.id,
        actor_role=user_role_str,
        reason=payload.reason,
    )


@router.post(
    "/{batch_id}/process",
    response_model=SettlementBatchResponse,
    summary="Disburse approved settlement batch through provider",
)
async def process_batch(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(require_support)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Disburses an approved batch through RazorpayX provider with idempotency keys.
    Fails if batch is not in 'approved' status.
    """
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.process_settlement_batch(
        batch_id=batch_id,
        actor_id=current_user.id,
        actor_role=user_role_str,
    )
