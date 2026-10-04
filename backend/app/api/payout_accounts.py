"""
Mechanic Payout Account & Settlement Batch API Router (Phase 8.8).

Endpoints:
- GET /api/v1/mechanics/payout-account
- POST /api/v1/mechanics/payout-account
- PATCH /api/v1/mechanics/payout-account
- POST /api/v1/mechanics/payout-account/verification
- GET /api/v1/mechanics/settlements
- POST /api/v1/mechanics/settlements/batches (Admin/Support)
- POST /api/v1/mechanics/settlements/batches/{batch_id}/process (Admin/Support)
- POST /api/v1/mechanics/payouts/webhook (Provider Webhooks)

Security:
- Strict JWT authentication.
- Identity derived from server session.
- Masked responses only (zero full bank account numbers).
"""

from typing import Annotated, Any
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from app.db.dependencies import get_current_user
from app.schemas.payout_account import (
    MechanicSettlementStatementResponse,
    PayoutAccountCreateRequest,
    PayoutAccountResponse,
    PayoutAccountUpdateRequest,
    SettlementBatchResponse,
)
from app.schemas.user import AuthenticatedUser, UserRole
from app.services.payout_account_service import PayoutAccountService
from app.services.settlement_statement_service import SettlementStatementService

router = APIRouter(prefix="/mechanics", tags=["Mechanic Payout Accounts & Settlements"])


def get_account_service() -> PayoutAccountService:
    """Dependency injector for PayoutAccountService."""
    return PayoutAccountService()


@router.get(
    "/payout-account",
    response_model=PayoutAccountResponse,
    summary="Get active mechanic payout bank account details",
)
async def get_mechanic_payout_account(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutAccountService = Depends(get_account_service),
) -> PayoutAccountResponse:
    """
    Retrieve active payout account for authenticated mechanic.
    Account numbers are masked with leading bullets.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    account = await service.get_payout_account(mechanic_id=effective_mech_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payout bank account not configured for this mechanic.",
        )
    return account


@router.post(
    "/payout-account",
    response_model=PayoutAccountResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Onboard or replace mechanic payout bank account",
)
async def create_mechanic_payout_account(
    payload: PayoutAccountCreateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutAccountService = Depends(get_account_service),
) -> PayoutAccountResponse:
    """
    Onboard bank account for mechanic payouts.
    Validates IFSC and account format.
    Never stores plain account number; returns masked account response.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.create_or_replace_payout_account(
        mechanic_id=effective_mech_id,
        payload=payload,
        actor_id=current_user.id,
        actor_role=user_role_str,
    )


@router.patch(
    "/payout-account",
    response_model=PayoutAccountResponse,
    summary="Update mechanic payout bank account details",
)
async def update_mechanic_payout_account(
    payload: PayoutAccountUpdateRequest,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutAccountService = Depends(get_account_service),
) -> PayoutAccountResponse:
    """
    Update bank account details.
    If account number is updated, resets verification status to pending.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    existing = await service.get_payout_account(mechanic_id=effective_mech_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payout bank account not configured. Use POST to create one.",
        )

    # If updating account number, reuse create_or_replace flow for safety
    if payload.account_number:
        full_create = PayoutAccountCreateRequest(
            account_holder_name=payload.account_holder_name or existing.account_holder_name,
            account_number=payload.account_number,
            ifsc_code=payload.ifsc_code or existing.ifsc_code or "HDFC0001234",
            bank_name=payload.bank_name or existing.bank_name,
        )
        user_role_str = (
            current_user.role.value
            if isinstance(current_user.role, UserRole)
            else str(current_user.role)
        )
        return await service.create_or_replace_payout_account(
            mechanic_id=effective_mech_id,
            payload=full_create,
            actor_id=current_user.id,
            actor_role=user_role_str,
        )

    # Otherwise update holder name or bank name directly
    update_data = {}
    if payload.account_holder_name:
        update_data["account_holder_name"] = payload.account_holder_name
    if payload.bank_name:
        update_data["bank_name"] = payload.bank_name
    if payload.ifsc_code:
        update_data["ifsc_code"] = payload.ifsc_code

    if update_data:
        service.client.table("mechanic_payout_accounts").update(update_data).eq("id", str(existing.id)).execute()

    updated = await service.get_payout_account(mechanic_id=effective_mech_id)
    return updated or existing


@router.post(
    "/payout-account/verification",
    response_model=PayoutAccountResponse,
    summary="Initiate Penny Drop / Fund Account verification",
)
async def verify_payout_account_endpoint(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutAccountService = Depends(get_account_service),
) -> PayoutAccountResponse:
    """
    Trigger provider account verification (Penny Drop / Fund Account Validation).
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    return await service.verify_payout_account(
        mechanic_id=effective_mech_id,
        actor_id=current_user.id,
        actor_role=user_role_str,
    )


@router.get(
    "/settlements",
    summary="List settlement disbursement history for mechanic",
)
async def list_mechanic_settlements(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    service: PayoutAccountService = Depends(get_account_service),
) -> list[dict[str, Any]]:
    """
    Retrieve settled payout history and batch numbers for the mechanic.
    """
    effective_mech_id = await service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    return await service.list_settlements_for_mechanic(
        mechanic_id=effective_mech_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/settlements/{batch_id}",
    response_model=MechanicSettlementStatementResponse,
    summary="Get authoritative settlement statement details (JSON)",
)
async def get_mechanic_statement_json(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    account_service: PayoutAccountService = Depends(get_account_service),
) -> MechanicSettlementStatementResponse:
    """
    Retrieve itemized disbursement statement data for a batch.
    Mechanics can only access batches containing their own ledger entries.
    """
    effective_mech_id = await account_service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    statement_service = SettlementStatementService()
    return await statement_service.get_settlement_statement_data(
        batch_id=batch_id,
        mechanic_id=effective_mech_id,
    )


@router.get(
    "/settlements/{batch_id}/statement",
    summary="Download PDF settlement disbursement statement",
)
async def download_mechanic_statement_pdf(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    mechanic_id: uuid.UUID | None = Query(None, description="Target mechanic ID (admin/support only)"),
    account_service: PayoutAccountService = Depends(get_account_service),
) -> Response:
    """
    Download a formatted PDF settlement statement.
    Generated on-demand using ReportLab from authoritative database records.
    Never exposes raw unmasked bank account numbers.
    """
    effective_mech_id = await account_service.resolve_mechanic_id(
        current_user=current_user,
        target_mechanic_id=mechanic_id,
    )
    statement_service = SettlementStatementService()
    statement_data = await statement_service.get_settlement_statement_data(
        batch_id=batch_id,
        mechanic_id=effective_mech_id,
    )
    pdf_bytes = statement_service.generate_statement_pdf(statement_data)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="statement_{statement_data.statement_number}.pdf"',
            "Content-Type": "application/pdf",
        },
    )



# ==============================================================================
# ADMIN / SUPPORT SETTLEMENT BATCH ENDPOINTS
# ==============================================================================

@router.post(
    "/settlements/batches",
    response_model=SettlementBatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a settlement batch from eligible payouts (Admin/Support only)",
)
async def create_settlement_batch_endpoint(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    payout_ids: list[uuid.UUID] | None = None,
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Create a settlement batch aggregating eligible ledger entries with verified accounts.
    """
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    if user_role_str not in [UserRole.ADMIN.value, UserRole.SUPPORT.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admin or support role required.",
        )

    return await service.create_settlement_batch(
        eligible_payout_ids=payout_ids,
        created_by=current_user.id,
    )


@router.post(
    "/settlements/batches/{batch_id}/process",
    response_model=SettlementBatchResponse,
    summary="Process and disburse a settlement batch (Admin/Support only)",
)
async def process_settlement_batch_endpoint(
    batch_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: PayoutAccountService = Depends(get_account_service),
) -> SettlementBatchResponse:
    """
    Process settlement batch through provider with mandatory idempotency key.
    """
    user_role_str = (
        current_user.role.value
        if isinstance(current_user.role, UserRole)
        else str(current_user.role)
    )
    if user_role_str not in [UserRole.ADMIN.value, UserRole.SUPPORT.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Admin or support role required.",
        )

    return await service.process_settlement_batch(
        batch_id=batch_id,
        actor_id=current_user.id,
        actor_role=user_role_str,
    )


# ==============================================================================
# PROVIDER WEBHOOK RECONCILIATION
# ==============================================================================

@router.post(
    "/payouts/webhook",
    summary="RazorpayX Payout & Verification Webhook Receiver",
)
async def handle_payout_webhook(
    request: Request,
    x_razorpay_signature: Annotated[str | None, Header()] = None,
    service: PayoutAccountService = Depends(get_account_service),
) -> dict[str, Any]:
    """
    Webhook receiver for RazorpayX events:
    - payout.processed
    - payout.failed
    - payout.reversed
    - fund_account.validation.completed
    - fund_account.validation.failed
    """
    raw_body = await request.body()
    return await service.process_payout_webhook(
        raw_body=raw_body,
        signature_header=x_razorpay_signature,
        provider="razorpayx",
    )
