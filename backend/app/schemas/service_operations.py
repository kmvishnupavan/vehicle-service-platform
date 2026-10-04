"""
Service Operations Schemas (Phase 12).

Defines Pydantic models for doorstep vehicle service operations:
- Arrival workflow
- Structured inspection & diagnostic findings
- Service checklist templates & booking items
- Parts tracking
- Price snapshot & financial calculations
- Service completion & service report
- Dispute raising & resolution
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


# ==============================================================================
# Arrival Schemas
# ==============================================================================

class ArrivalResponse(BaseModel):
    """Authoritative response confirming mechanic arrival at customer location."""
    model_config = ConfigDict(from_attributes=True)

    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    arrived_at: datetime
    booking_status: str
    message: str = "Mechanic arrival verified and recorded successfully."


# ==============================================================================
# Structured Inspection Schemas
# ==============================================================================

class DiagnosticFinding(BaseModel):
    """Structured vehicle diagnostic finding or error code."""
    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., min_length=1, max_length=50, description="e.g. brakes, battery, engine, electrical")
    finding: str = Field(..., min_length=1, max_length=500, description="Specific finding description")
    severity: str = Field(default="medium", description="Severity level: low, medium, high, critical")
    recommended_action: str | None = Field(default=None, max_length=500)


class RecommendedService(BaseModel):
    """Recommended additional service from vehicle inspection."""
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=500)
    is_required: bool = Field(default=False, description="True if critical safety requirement, False if optional")
    estimated_price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"))


class StructuredInspectionCreate(BaseModel):
    """Mechanic input for submitting comprehensive structured vehicle inspection."""
    model_config = ConfigDict(extra="forbid")

    findings: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Comprehensive summary of diagnostic findings and vehicle condition",
    )
    vehicle_condition: str | None = Field(
        default=None,
        max_length=500,
        description="Summary of physical and mechanical vehicle condition (e.g. Good, Fair, Urgent Repairs)",
    )
    odometer_reading: int | None = Field(
        default=None,
        ge=0,
        description="Vehicle odometer reading in kilometers at time of inspection",
    )
    checklist_results: dict[str, Any] = Field(
        default={},
        description="Key-value mapping of inspection checkpoint results",
    )
    diagnostic_findings: list[DiagnosticFinding] = Field(
        default=[],
        description="List of structured diagnostic issues found",
    )
    recommended_services: list[RecommendedService] = Field(
        default=[],
        description="List of recommended services with required/optional distinction",
    )
    parts_required: list[dict[str, Any]] = Field(
        default=[],
        description="List of replacement parts required for recommended work",
    )
    labor_requirements: str | None = Field(
        default=None,
        max_length=1000,
        description="Detailed description of labor required",
    )
    estimated_additional_cost: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        description="Estimated monetary cost for additional repairs discovered (>= 0)",
    )
    evidence_file_paths: list[str] = Field(
        default=[],
        description="Storage paths for evidence media files in service-evidence bucket",
    )

    @field_validator("findings")
    @classmethod
    def validate_findings_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Inspection findings must not be empty.")
        return stripped


class StructuredInspectionResponse(BaseModel):
    """Authoritative structured inspection response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    findings: str
    vehicle_condition: str | None = None
    odometer_reading: int | None = None
    checklist_results: dict[str, Any] = Field(default={})
    diagnostic_findings: list[dict[str, Any]] = Field(default=[])
    recommended_services: list[dict[str, Any]] = Field(default=[])
    parts_required: list[dict[str, Any]] = Field(default=[])
    labor_requirements: str | None = None
    estimated_additional_cost: Decimal
    evidence_file_paths: list[str] = Field(default=[])
    created_at: datetime
    updated_at: datetime


# ==============================================================================
# Service Checklist Schemas
# ==============================================================================

class ChecklistTemplateResponse(BaseModel):
    """Pre-configured standard service checklist item template."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_slug: str
    item_key: str
    title: str
    description: str | None = None
    is_mandatory: bool
    display_order: int


class BookingChecklistItemResponse(BaseModel):
    """Active checklist task instance for a booking."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    item_key: str
    title: str
    category_slug: str
    is_mandatory: bool
    is_completed: bool
    completed_at: datetime | None = None
    notes: str | None = None


class BookingChecklistItemUpdate(BaseModel):
    """Mechanic input for checking off a single checklist item."""
    model_config = ConfigDict(extra="forbid")

    is_completed: bool = Field(..., description="True to mark completed, False to mark incomplete")
    notes: str | None = Field(default=None, max_length=500, description="Optional mechanic note on execution")


class BatchChecklistUpdateRequest(BaseModel):
    """Batch update for multiple checklist tasks."""
    model_config = ConfigDict(extra="forbid")

    items: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="List of objects containing item_key, is_completed, and optional notes",
    )


# ==============================================================================
# Parts Tracking Schemas
# ==============================================================================

class BookingPartCreate(BaseModel):
    """Mechanic input for recording a replacement part used during service."""
    model_config = ConfigDict(extra="forbid")

    part_name: str = Field(..., min_length=1, max_length=150, description="Name or title of part installed")
    part_number: str | None = Field(default=None, max_length=100, description="OEM or aftermarket part number")
    description: str | None = Field(default=None, max_length=500)
    quantity: int = Field(default=1, gt=0, description="Quantity installed")
    unit_price: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0.00"), description="Unit price per item")
    supplier: str | None = Field(default=None, max_length=150, description="Supplier or manufacturer source")
    warranty_months: int | None = Field(default=None, ge=0, description="Warranty period in months")
    warranty_notes: str | None = Field(default=None, max_length=500)

    @field_validator("part_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Part name must not be blank.")
        return s


class BookingPartResponse(BaseModel):
    """Authoritative response for a recorded service part."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    part_name: str
    part_number: str | None = None
    description: str | None = None
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    supplier: str | None = None
    warranty_months: int | None = None
    warranty_notes: str | None = None
    created_at: datetime


# ==============================================================================
# Price Snapshot Schemas
# ==============================================================================

class PriceSnapshot(BaseModel):
    """Immutable price snapshot frozen at customer approval boundary."""
    model_config = ConfigDict(extra="ignore")

    base_service_amount: Decimal
    parts_total: Decimal
    labor_total: Decimal
    additional_work_total: Decimal
    discount_amount: Decimal
    taxable_base: Decimal
    tax_rate: Decimal = Decimal("0.18")
    tax_amount: Decimal
    total_amount: Decimal
    snapshot_timestamp: datetime
    approved_by: uuid.UUID | None = None
    version: int = 1


# ==============================================================================
# Service Completion & Report Schemas
# ==============================================================================

class ServiceCompletionRequest(BaseModel):
    """Mechanic input to finalize service and issue service report."""
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(..., min_length=1, max_length=2000, description="Overall summary of completed work")
    work_performed: str = Field(..., min_length=1, max_length=5000, description="Detailed list and description of work executed")
    recommendations: str | None = Field(default=None, max_length=2000, description="Future maintenance recommendations")
    customer_notes: str | None = Field(default=None, max_length=1000, description="Special instructions or notes for the customer")
    completion_evidence_paths: list[str] = Field(
        default=[],
        description="After-service photo paths in service-evidence bucket confirming completed work",
    )

    @field_validator("summary", "work_performed")
    @classmethod
    def validate_non_blank(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field must not be blank.")
        return s


class ServiceReportResponse(BaseModel):
    """Authoritative detailed service report response."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    mechanic_id: uuid.UUID
    summary: str
    work_performed: str
    recommendations: str | None = None
    customer_notes: str | None = None
    report_file_path: str | None = None
    parts_used: list[dict[str, Any]] = Field(default=[])
    checklist_summary: dict[str, Any] = Field(default={})
    labor_summary: str | None = None
    final_totals: dict[str, Any] = Field(default={})
    completed_at: datetime
    created_at: datetime


# ==============================================================================
# Dispute Schemas
# ==============================================================================

class DisputeCreateRequest(BaseModel):
    """Customer request to dispute a completed or paid booking."""
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=5, max_length=2000, description="Detailed explanation of the issue or dispute")
    evidence_paths: list[str] = Field(default=[], description="Optional photo or invoice proof paths in service-evidence bucket")

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        s = v.strip()
        if len(s) < 5:
            raise ValueError("Dispute reason must be at least 5 characters.")
        return s


class DisputeResolveRequest(BaseModel):
    """Admin/Support request to resolve an active dispute."""
    model_config = ConfigDict(extra="forbid")

    resolution_status: str = Field(
        ...,
        description="Target status after dispute resolution: paid, service_completed, or cancelled",
    )
    resolution_notes: str = Field(..., min_length=5, max_length=2000, description="Support team resolution documentation")

    @field_validator("resolution_status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"paid", "service_completed", "cancelled"}
        if v not in allowed:
            raise ValueError(f"Resolution status must be one of {allowed}")
        return v
