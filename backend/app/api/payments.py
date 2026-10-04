"""
Payments and Invoices Endpoints.

Mounts under /api/v1/payments.

Security & Architectural Rules:
- Frontend must NEVER calculate totals, amounts, or capture payments.
- Authoritative amounts are derived exclusively from PostgreSQL bookings.total_amount.
- Verification uses constant-time HMAC-SHA256 signature checking.
- Webhook verification reads raw bytes before JSON parsing.
- Sensitive credentials (Razorpay secret, webhook secret, Supabase service-role key) are NEVER exposed.
"""

from typing import Any
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from app.db.dependencies import get_current_user, require_customer
from app.schemas.payment import (
    InvoiceDetailResponse,
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentResponse,
    PaymentVerifyRequest,
    PaymentVerifyResponse,
    WebhookResponse,
)
from app.schemas.user import AuthenticatedUser
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/create-order",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Razorpay payment order",
    description=(
        "Initiate payment for a completed booking. Derives authoritative amount directly from PostgreSQL. "
        "Strictly forbids client-supplied monetary amounts or status values."
    ),
)
async def create_payment_order(
    payload: PaymentOrderCreate,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> PaymentOrderResponse:
    """Create a server-controlled Razorpay order."""
    service = PaymentService()
    result = await service.create_payment_order(
        booking_id=payload.booking_id,
        customer_user_id=current_user.id,
    )
    return PaymentOrderResponse.model_validate(result)


@router.post(
    "/verify",
    response_model=PaymentVerifyResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify payment and settle booking",
    description=(
        "Cryptographically verify Razorpay signature and settle payment, booking status, and invoice atomically. "
        "Strictly idempotent against duplicate client requests."
    ),
)
async def verify_payment(
    payload: PaymentVerifyRequest,
    current_user: AuthenticatedUser = Depends(require_customer),
) -> PaymentVerifyResponse:
    """Verify Razorpay payment and perform atomic settlement."""
    service = PaymentService()
    result = await service.verify_payment(
        booking_id=payload.booking_id,
        razorpay_order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        razorpay_signature=payload.razorpay_signature,
        customer_user_id=current_user.id,
    )
    return PaymentVerifyResponse.model_validate(result)


@router.post(
    "/webhook",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Razorpay asynchronous webhook listener",
    description=(
        "Receive and process asynchronous payment events directly from Razorpay. "
        "Authenticated exclusively via HMAC-SHA256 signature in X-Razorpay-Signature header."
    ),
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
) -> WebhookResponse:
    """Process incoming Razorpay webhook event."""
    raw_body = await request.body()
    service = PaymentService()
    result = await service.process_webhook(
        raw_body=raw_body,
        signature_header=x_razorpay_signature,
    )
    return WebhookResponse.model_validate(result)


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get payment record status",
    description="Retrieve payment record by ID with customer ownership authorization.",
)
async def get_payment(
    payment_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PaymentResponse:
    """Retrieve payment record with strict ownership checks."""
    service = PaymentService()
    payment = await service.get_payment_by_id(payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment record not found.",
        )

    # Verify ownership
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if user_role_str == "customer" and str(payment.get("customer_id")) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to payment record.",
        )
    if user_role_str not in ["customer", "admin", "support"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to payment record.",
        )

    return PaymentResponse.model_validate(payment)


@router.get(
    "/booking/{booking_id}/invoice",
    response_model=InvoiceDetailResponse,
    summary="Get booking invoice details",
    description=(
        "Retrieve production-style detailed invoice for a booking, including line items, "
        "approved additional work, vehicle information, and tax breakdown."
    ),
)
async def get_booking_invoice(
    booking_id: uuid.UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> InvoiceDetailResponse:
    """Retrieve detailed invoice with ownership verification."""
    service = PaymentService()
    user_role_str = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    invoice = await service.get_detailed_invoice(
        booking_id=booking_id,
        user_id=current_user.id,
        user_role=user_role_str,
    )
    return InvoiceDetailResponse.model_validate(invoice)
