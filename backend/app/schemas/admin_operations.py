"""
Admin Operations, Observability & Reconciliation Schemas (Phase 9).
"""

from typing import Any
import uuid
from pydantic import BaseModel, Field


class ReconciliationDiscrepancyItem(BaseModel):
    """Schema for individual financial or system discrepancy."""
    id: uuid.UUID | str | None = None
    entity_type: str
    entity_id: uuid.UUID | str | None = None
    provider_reference: str | None = None
    internal_status: str | None = None
    provider_status: str | None = None
    discrepancy_type: str
    severity: str = "medium"
    details: dict[str, Any] = Field(default_factory=dict)
    detected_at: str
    resolution_status: str = "open"


class ReconciliationReportResponse(BaseModel):
    """List of detected discrepancies for a subsystem."""
    subsystem: str
    discrepancies: list[ReconciliationDiscrepancyItem]
    count: int
    scanned_at: str


class AdminSystemStatsResponse(BaseModel):
    """Aggregated operational metrics for admin dashboard."""
    environment: str
    system_health: dict[str, Any]
    safety_guard: dict[str, Any]
    bookings_breakdown: dict[str, int]
    payments_breakdown: dict[str, int]
    payouts_breakdown: dict[str, int]
    webhooks_breakdown: dict[str, int]
    notifications_breakdown: dict[str, int]
    timestamp: str
    bookings: dict[str, int] | None = None
    payments: dict[str, int] | None = None
    payouts: dict[str, int] | None = None
    webhooks: dict[str, int] | None = None


class AuditLogItem(BaseModel):
    """Schema for individual audit log entry."""
    id: uuid.UUID | str
    actor_id: uuid.UUID | str | None = None
    actor_role: str | None = None
    action: str
    entity_type: str
    entity_id: uuid.UUID | str | None = None
    old_data: dict[str, Any] | None = None
    new_data: dict[str, Any] | None = None
    ip_address: str | None = None
    request_id: str | None = None
    severity: str = "info"
    created_at: str


class AuditLogListResponse(BaseModel):
    """Paginated audit log search results."""
    items: list[AuditLogItem]
    total: int
    limit: int
    offset: int
