"""
Operational Automation & Background Processing Schemas (Phase 13).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator


# =============================================================================
# 1. Background Job Schemas
# =============================================================================

class BackgroundJobExecutionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_name: str
    execution_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: Literal['running', 'completed', 'partial_failure', 'failed']
    records_processed: int
    records_succeeded: int
    records_failed: int
    error_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RunJobsRequest(BaseModel):
    job_names: list[str] | None = Field(
        default=None,
        description="Optional list of specific job names to execute; runs all if omitted."
    )


# =============================================================================
# 2. Scheduled Booking Schemas
# =============================================================================

class ScheduledBookingCreate(BaseModel):
    scheduled_start_at: datetime = Field(..., description="Start of requested service window (UTC)")
    scheduled_end_at: datetime = Field(..., description="End of requested service window (UTC)")
    timezone: str = Field(default="UTC", description="Customer local timezone (e.g. 'Asia/Kolkata')")
    dispatch_window_minutes: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Minutes before scheduled_start_at to initiate mechanic matching"
    )

    @field_validator("scheduled_end_at")
    @classmethod
    def validate_window(cls, v: datetime, info) -> datetime:
        start = info.data.get("scheduled_start_at")
        if start and v < start:
            raise ValueError("scheduled_end_at must be greater than or equal to scheduled_start_at")
        return v


class ScheduledBookingResponse(BaseModel):
    id: uuid.UUID
    booking_id: uuid.UUID
    scheduled_start_at: datetime
    scheduled_end_at: datetime
    timezone: str
    dispatch_at: datetime
    status: Literal['scheduled', 'dispatching', 'dispatched', 'cancelled', 'completed', 'failed']
    attempt_count: int
    last_attempt_at: datetime | None = None
    dispatched_at: datetime | None = None
    cancelled_at: datetime | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# 3. Versioned Matching Policy Schemas
# =============================================================================

class MatchingPolicyBase(BaseModel):
    policy_version: str = Field(..., description="Unique policy version identifier (e.g. 'v1.1')")
    proximity_weight: Decimal = Field(..., ge=0, le=1)
    rating_weight: Decimal = Field(..., ge=0, le=1)
    availability_weight: Decimal = Field(..., ge=0, le=1)
    reliability_weight: Decimal = Field(..., ge=0, le=1)
    workload_weight: Decimal = Field(..., ge=0, le=1)
    acceptance_weight: Decimal = Field(..., ge=0, le=1)
    max_concurrent_jobs: int = Field(default=1, ge=1, le=5)
    offer_timeout_seconds: int = Field(default=60, ge=15, le=300)
    max_offer_attempts: int = Field(default=3, ge=1, le=10)
    description: str | None = None

    @field_validator("acceptance_weight")
    @classmethod
    def validate_weight_sum(cls, v: Decimal, info) -> Decimal:
        data = info.data
        total = (
            data.get("proximity_weight", Decimal(0)) +
            data.get("rating_weight", Decimal(0)) +
            data.get("availability_weight", Decimal(0)) +
            data.get("reliability_weight", Decimal(0)) +
            data.get("workload_weight", Decimal(0)) +
            v
        )
        if abs(total - Decimal("1.000")) > Decimal("0.001"):
            raise ValueError(f"Matching weights must sum to 1.000 (currently {total})")
        return v


class MatchingPolicyCreate(MatchingPolicyBase):
    pass


class MatchingPolicyResponse(MatchingPolicyBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    created_at: datetime
    created_by: uuid.UUID | None = None
    activated_at: datetime | None = None
    activated_by: uuid.UUID | None = None


# =============================================================================
# 4. Location Quality & GPS Anomaly Schemas
# =============================================================================

class LocationAnomalyRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mechanic_id: uuid.UUID
    booking_id: uuid.UUID | None = None
    detected_at: datetime
    previous_location: dict[str, Any] | None = None
    new_location: dict[str, Any]
    distance_meters: float | None = None
    time_delta_seconds: float | None = None
    calculated_speed_kmh: float | None = None
    anomaly_type: Literal[
        'impossible_speed',
        'large_location_jump',
        'stale_location',
        'invalid_coordinates',
        'poor_accuracy',
        'location_spoofing_suspected'
    ]
    severity: Literal['low', 'medium', 'high']
    status: Literal['flagged', 'reviewed', 'dismissed', 'escalated']
    notes: str | None = None
    created_at: datetime


class LocationFreshnessStatus(BaseModel):
    mechanic_id: uuid.UUID
    freshness: Literal['fresh', 'stale', 'offline']
    last_updated_at: datetime | None = None
    seconds_since_update: float | None = None
    current_latitude: float | None = None
    current_longitude: float | None = None


# =============================================================================
# 5. Operational Metrics Snapshot Schema
# =============================================================================

class OperationalMetricsData(BaseModel):
    booking_count: int = 0
    active_bookings: int = 0
    matching_sessions_total: int = 0
    average_time_to_match_seconds: float = 0.0
    matching_exhaustion_rate: float = 0.0
    offer_acceptance_rate: float = 0.0
    offer_expiration_rate: float = 0.0
    average_eta_minutes: float = 0.0
    routing_failure_rate: float = 0.0
    routing_fallback_rate: float = 0.0
    stale_location_rate: float = 0.0
    location_anomaly_count: int = 0
    scheduled_booking_count: int = 0
    scheduled_dispatch_failure_rate: float = 0.0
    inspection_approval_rate: float = 0.0
    service_completion_rate: float = 0.0
    payment_success_rate: float = 0.0
    payment_pending_count: int = 0
    dispute_rate: float = 0.0
    notification_failure_rate: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(datetime.timezone.utc if hasattr(datetime, 'timezone') else None))


class OperationalMetricsResponse(BaseModel):
    id: uuid.UUID | None = None
    snapshot_time: datetime
    metrics: OperationalMetricsData
