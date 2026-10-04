"""
Payment and Invoice Pydantic Schemas.

Maps to database tables:
- public.payments
- public.payment_transactions
- public.invoices

Enforces strict input validation (extra='forbid') and authoritative server-side pricing.
Clients are strictly forbidden from passing financial values or status flags.
"""

from datetime import datetime
from enum import Enum
import uuid
from pydantic import BaseModel, ConfigDict, Field


class PaymentGatewayStatus(str, Enum):
    """Payment transaction states matching PostgreSQL check constraints."""
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentTransactionStatus(str, Enum):
    """Payment gateway attempt transaction status."""
    INITIATED = "initiated"
    PROCESSING = "processing"
    SUCCESSFUL = "successful"
    FAILED = "failed"
    REFUNDED = "refunded"


class InvoiceStatus(str, Enum):
    """Invoice lifecycle status."""
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"
    REFUNDED = "refunded"


# ==============================================================================
# Request Schemas (Strict: extra='forbid', no client financial/status fields)
# ==============================================================================

class PaymentOrderCreate(BaseModel):
    """Request payload to create a Razorpay payment order for a completed booking."""
    model_config = ConfigDict(extra="forbid")

    booking_id: uuid.UUID = Field(
        ...,
        description="UUID of the vehicle service booking to initiate payment for.",
    )


class PaymentVerifyRequest(BaseModel):
    """
    Request payload to verify Razorpay payment completion.

    Strictly forbids client-supplied monetary amounts, currencies, or statuses.
    """
    model_config = ConfigDict(extra="forbid")

    booking_id: uuid.UUID = Field(
        ...,
        description="UUID of the booking being settled.",
    )
    razorpay_order_id: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="Gateway order identifier issued by Razorpay (order_XXXXXXXX).",
    )
    razorpay_payment_id: str = Field(
        ...,
        min_length=5,
        max_length=100,
        description="Gateway payment identifier returned by Razorpay Checkout (pay_XXXXXXXX).",
    )
    razorpay_signature: str = Field(
        ...,
        min_length=10,
        max_length=200,
        description="HMAC-SHA256 signature returned by Razorpay Checkout.",
    )


# ==============================================================================
# Response Schemas
# ==============================================================================

class PaymentOrderResponse(BaseModel):
    """Safe response containing order details needed by Razorpay frontend Checkout."""
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(..., description="Razorpay order ID")
    amount: int = Field(..., description="Authoritative booking total in paise (INR cents)")
    currency: str = Field(default="INR", description="Three-letter currency code")
    key_id: str = Field(..., description="Razorpay publishable Key ID for client SDK")
    booking_id: uuid.UUID = Field(..., description="Target booking identifier")


class PaymentVerifyResponse(BaseModel):
    """Response returned upon successful payment verification and settlement."""
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="Settlement result status (e.g. success, already_paid)")
    message: str = Field(..., description="Human-readable confirmation message")
    booking_id: uuid.UUID = Field(..., description="Settled booking identifier")
    payment_id: uuid.UUID = Field(..., description="Internal payment record identifier")
    transaction_id: str | None = Field(default=None, description="Recorded gateway payment ID")


class PaymentResponse(BaseModel):
    """Payment record response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    amount: float
    currency: str = "INR"
    status: PaymentGatewayStatus
    provider: str = "razorpay"
    provider_payment_id: str | None = None
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InvoiceItemResponse(BaseModel):
    """Line item in a detailed invoice."""
    model_config = ConfigDict(from_attributes=True)

    service_name: str
    tier_name: str | None = None
    unit_price: float
    quantity: int = 1
    total_price: float


class InvoiceAdditionalWorkResponse(BaseModel):
    """Approved additional work item in an invoice."""
    model_config = ConfigDict(from_attributes=True)

    description: str
    amount: float
    status: str


class InvoiceResponse(BaseModel):
    """Base invoice response schema."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    subtotal: float
    tax: float
    discount: float
    total: float
    status: str
    issued_at: datetime
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class InvoiceDetailResponse(BaseModel):
    """Rich, production-style invoice response including line items and customer/vehicle details."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    booking_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    vehicle_info: str | None = None
    items: list[InvoiceItemResponse] = Field(default_factory=list)
    additional_work: list[InvoiceAdditionalWorkResponse] = Field(default_factory=list)
    subtotal: float
    tax: float
    discount: float
    total: float
    status: str
    issued_at: datetime
    paid_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class WebhookResponse(BaseModel):
    """Response returned to Razorpay webhook dispatcher."""
    model_config = ConfigDict(extra="forbid")

    status: str
    message: str
    event: str | None = None
    event_id: str | None = None
