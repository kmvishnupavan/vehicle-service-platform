"""
Mechanic Payout Account & Settlement Batch Schemas (Phase 8.8).

Defines request/response models with:
- Strict masking (never returns full bank account numbers)
- IFSC format validation
- Sanitized provider metadata
- Verification statuses
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
import re
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.payout import PayoutResponse


class AccountType(str, Enum):
    BANK_ACCOUNT = "bank_account"
    VPA = "vpa"


class PayoutAccountVerificationStatus(str, Enum):
    NOT_CONFIGURED = "not_configured"
    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    FAILED = "failed"
    SUSPENDED = "suspended"


class SettlementBatchStatus(str, Enum):
    DRAFT = "draft"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"
    PARTIALLY_FAILED = "partially_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"


IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


class PayoutAccountCreateRequest(BaseModel):
    """Payload submitted by mechanic to configure their payout bank account."""
    model_config = ConfigDict(str_strip_whitespace=True)

    account_holder_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Beneficiary account holder name matching bank records",
    )
    account_number: str = Field(
        ...,
        min_length=8,
        max_length=22,
        description="Bank account number (digits only)",
    )
    ifsc_code: str = Field(
        ...,
        min_length=11,
        max_length=11,
        description="11-character Indian Financial System Code (IFSC)",
    )
    bank_name: str | None = Field(
        None,
        max_length=100,
        description="Optional bank name",
    )
    account_type: AccountType = Field(
        default=AccountType.BANK_ACCOUNT,
        description="Account type (default: bank_account)",
    )

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str) -> str:
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit():
            raise ValueError("Bank account number must contain digits only.")
        if len(clean) < 8 or len(clean) > 22:
            raise ValueError("Bank account number must be between 8 and 22 digits.")
        return clean

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: str) -> str:
        clean = v.upper().strip()
        if not IFSC_REGEX.match(clean):
            raise ValueError("Invalid IFSC code format. Expected 11 characters, e.g., HDFC0001234.")
        return clean


class PayoutAccountUpdateRequest(BaseModel):
    """Payload to update an existing payout bank account."""
    model_config = ConfigDict(str_strip_whitespace=True)

    account_holder_name: str | None = Field(None, min_length=2, max_length=100)
    account_number: str | None = Field(None, min_length=8, max_length=22)
    ifsc_code: str | None = Field(None, min_length=11, max_length=11)
    bank_name: str | None = Field(None, max_length=100)

    @field_validator("account_number")
    @classmethod
    def validate_account_number(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = re.sub(r"[\s\-]", "", v)
        if not clean.isdigit():
            raise ValueError("Bank account number must contain digits only.")
        if len(clean) < 8 or len(clean) > 22:
            raise ValueError("Bank account number must be between 8 and 22 digits.")
        return clean

    @field_validator("ifsc_code")
    @classmethod
    def validate_ifsc(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.upper().strip()
        if not IFSC_REGEX.match(clean):
            raise ValueError("Invalid IFSC code format. Expected 11 characters, e.g., HDFC0001234.")
        return clean


class PayoutAccountResponse(BaseModel):
    """
    Sanitized payout account response.
    Never exposes raw unmasked bank account numbers.
    """
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Payout account UUID")
    mechanic_id: uuid.UUID = Field(..., description="Associated mechanic profile UUID")
    provider: str = Field(default="razorpayx", description="Payout provider")
    provider_contact_id: str | None = Field(None, description="Provider contact reference")
    provider_fund_account_id: str | None = Field(None, description="Provider fund account reference")

    account_holder_name: str = Field(..., description="Beneficiary account holder name")
    account_type: str = Field(default="bank_account", description="Account type")
    masked_account_number: str = Field(..., description="Masked account number (e.g. •••• •••• 1234)")
    ifsc_code: str | None = Field(None, description="Bank IFSC code")
    bank_name: str | None = Field(None, description="Bank display name")

    verification_status: PayoutAccountVerificationStatus = Field(
        ..., description="Verification lifecycle status"
    )
    verification_error: str | None = Field(None, description="Sanitized verification error if failed")
    is_primary: bool = Field(default=True, description="Whether this is the primary disbursement account")
    is_active: bool = Field(default=True, description="Whether this account is active")

    verified_at: datetime | None = Field(None, description="Timestamp of successful verification")
    last_verified_at: datetime | None = Field(None, description="Last verification check timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class SettlementBatchCreateRequest(BaseModel):
    """Payload to create a new settlement batch."""
    model_config = ConfigDict(str_strip_whitespace=True)

    eligible_payout_ids: list[uuid.UUID] | None = Field(
        default=None,
        description="Optional list of specific payout ledger IDs to include in batch",
    )


class SettlementBatchResponse(BaseModel):
    """Settlement disbursement batch details."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Batch UUID")
    batch_number: str = Field(..., description="Unique settlement batch reference")
    provider: str = Field(default="razorpayx", description="Settlement provider")
    status: SettlementBatchStatus = Field(..., description="Batch lifecycle status")
    total_amount: str = Field(..., description="Total settled amount (INR)")
    currency: str = Field(default="INR", description="Currency code")
    item_count: int = Field(..., ge=0, description="Number of ledger items in batch")
    provider_batch_id: str | None = Field(None, description="External provider batch identifier")
    error_details: dict[str, Any] | None = Field(None, description="Sanitized batch error details")
    submitted_at: datetime | None = Field(None, description="Submission timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    created_at: datetime = Field(..., description="Creation timestamp")
    created_by: uuid.UUID | None = Field(default=None, description="Maker user ID")
    items: list[PayoutResponse] | None = Field(default=None, description="Ledger items in batch")


class SettlementBatchListResponse(BaseModel):
    """Paginated list of settlement batches."""
    model_config = ConfigDict(from_attributes=True)

    items: list[SettlementBatchResponse]
    total: int = Field(..., ge=0)
    limit: int = Field(..., ge=1, le=100)
    offset: int = Field(..., ge=0)


class SettlementApprovalAction(str, Enum):
    SUBMITTED_FOR_APPROVAL = "submitted_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SettlementApprovalRequest(BaseModel):
    """Request payload for maker-checker approval actions."""
    model_config = ConfigDict(str_strip_whitespace=True)

    reason: str | None = Field(default=None, max_length=500, description="Optional rejection or approval reason")


class SettlementApprovalRecordResponse(BaseModel):
    """Immutable audit record of a maker-checker approval action."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    settlement_batch_id: uuid.UUID
    action: str
    actor_id: uuid.UUID
    actor_role: str
    reason: str | None = None
    created_at: datetime


class SettlementBatchDetailResponse(SettlementBatchResponse):
    """Detailed settlement batch with approval history and payout items."""
    approvals: list[SettlementApprovalRecordResponse] = Field(default_factory=list)


class SettlementApprovalPolicyResponse(BaseModel):
    """Settlement approval policy configuration."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    threshold_amount: Decimal
    currency: str
    requires_checker: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class SettlementApprovalPolicyUpdateRequest(BaseModel):
    """Update high-value settlement threshold policy."""
    model_config = ConfigDict(str_strip_whitespace=True)

    threshold_amount: Decimal | None = Field(None, ge=0)
    requires_checker: bool | None = None
    is_active: bool | None = None


class SettlementStatementItem(BaseModel):
    """Itemized booking and commission line in mechanic statement."""
    model_config = ConfigDict(from_attributes=True)

    payout_id: str
    booking_id: str
    booking_number: str | None = None
    service_title: str | None = None
    gross_amount: str
    commission_rate: str
    commission_amount: str
    deduction_amount: str
    net_amount: str
    currency: str
    status: str
    settled_at: datetime | None = None


class MechanicSettlementStatementResponse(BaseModel):
    """Authoritative mechanic settlement and disbursement statement."""
    model_config = ConfigDict(from_attributes=True)

    statement_number: str
    statement_date: datetime
    mechanic_id: str
    mechanic_name: str
    bank_name: str | None = None
    account_number_masked: str
    ifsc_code: str | None = None
    batch_id: str
    batch_number: str
    batch_status: str
    currency: str
    total_gross: str
    total_commission: str
    total_deductions: str
    total_net: str
    net_payout: Decimal | None = None
    items: list[SettlementStatementItem]
    tax_disclaimer: str = (
        "Tax/GST compliance requires configuration and validation against the "
        "business's actual tax status and applicable Indian tax rules."
    )

