"""
Payout and Commission Pydantic Schemas (Phase 8.7).

Authoritative models for:
- Commission policy configuration
- Payout ledger records (gross, commission, deductions, net)
- Payout summaries and aggregated balances
- State machine statuses and paginated lists
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field
from app.services.payout_state_machine import PayoutStatus


class CommissionPolicyResponse(BaseModel):
    """Platform commission policy record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Commission policy UUID")
    name: str = Field(..., description="Policy display name")
    commission_rate: Decimal = Field(..., ge=0, le=1, description="Commission fraction (e.g. 0.2000)")
    currency: str = Field(default="INR", description="Currency code")
    is_active: bool = Field(default=True, description="Whether policy is active")
    effective_from: datetime = Field(..., description="Activation timestamp")
    effective_to: datetime | None = Field(default=None, description="Expiration timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")


class PayoutResponse(BaseModel):
    """Authoritative mechanic payout ledger line item."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Payout ledger UUID")
    booking_id: uuid.UUID = Field(..., description="Associated booking UUID")
    mechanic_id: uuid.UUID = Field(..., description="Associated mechanic profile UUID")
    booking_number: str | None = Field(default=None, description="Human-readable booking number")
    payment_id: uuid.UUID | None = Field(default=None, description="Associated payment UUID")
    payment_transaction_id: uuid.UUID | None = Field(default=None, description="Payment transaction UUID")

    gross_amount: str = Field(..., description="Customer-paid service gross amount (subtotal + additional work)")
    commission_rate: str = Field(..., description="Applied platform commission rate (e.g. 0.2000)")
    commission_amount: str = Field(..., description="Platform commission retained (INR)")
    deduction_amount: str = Field(default="0.00", description="Mechanic deductions or charges (INR)")
    net_amount: str = Field(..., description="Net amount payable to mechanic (INR)")

    currency: str = Field(default="INR", description="Currency code")
    status: PayoutStatus = Field(..., description="Current payout lifecycle status")

    created_at: datetime = Field(..., description="Record creation timestamp")
    updated_at: datetime = Field(..., description="Last record update timestamp")
    eligible_at: datetime | None = Field(default=None, description="Timestamp when funds became eligible for disbursement")
    settled_at: datetime | None = Field(default=None, description="Timestamp when payout disbursement completed")
    reversed_at: datetime | None = Field(default=None, description="Timestamp when payout was reversed/refunded")

    provider: str = Field(default="manual", description="Payout processor provider")
    provider_payout_id: str | None = Field(default=None, description="External provider payout transaction ID")
    failure_reason: str | None = Field(default=None, description="Failure reason description if failed")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Sanitized audit metadata")


class PayoutListResponse(BaseModel):
    """Paginated list of mechanic payout records."""
    model_config = ConfigDict(from_attributes=True)

    items: list[PayoutResponse]
    total: int = Field(..., ge=0, description="Total matching payout records")
    limit: int = Field(..., ge=1, le=100, description="Items per page limit")
    offset: int = Field(..., ge=0, description="Page offset")


class PayoutSummary(BaseModel):
    """Aggregated financial summary across all ledger records for a mechanic."""
    model_config = ConfigDict(from_attributes=True)

    total_gross: str = Field("0.00", description="Sum of gross attributable revenue")
    total_commission: str = Field("0.00", description="Sum of platform commission retained")
    total_deductions: str = Field("0.00", description="Sum of applicable deductions")
    total_net: str = Field("0.00", description="Sum of net mechanic earnings across all statuses")

    pending_amount: str = Field("0.00", description="Funds awaiting payment clearance / hold period")
    eligible_amount: str = Field("0.00", description="Cleared funds eligible for disbursement")
    processing_amount: str = Field("0.00", description="Funds currently in transfer processing")
    paid_amount: str = Field("0.00", description="Settled funds successfully paid to mechanic")
    reversed_amount: str = Field("0.00", description="Clawed back / refunded funds")

    currency: str = Field(default="INR", description="Currency code")
