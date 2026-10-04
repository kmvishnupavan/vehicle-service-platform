/**
 * Phase 13: Operational Automation, Background Jobs, Scheduled Bookings & Reliability Types.
 */

export interface ScheduledBooking {
  id: string;
  booking_id: string;
  scheduled_start_at: string;
  scheduled_end_at: string;
  timezone: string;
  dispatch_at: string;
  status: 'scheduled' | 'dispatching' | 'dispatched' | 'cancelled' | 'failed';
  attempt_count: number;
  cancelled_at?: string | null;
  failure_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleBookingRequest {
  scheduled_start_at: string;
  scheduled_end_at: string;
  timezone?: string;
  dispatch_window_minutes?: number;
}

export interface BackgroundJobExecutionSummary {
  id: string;
  job_name: string;
  execution_id: string;
  started_at: string;
  completed_at?: string | null;
  status: 'running' | 'completed' | 'partial_failure' | 'failed';
  records_processed: number;
  records_succeeded: number;
  records_failed: number;
  error_summary?: string | null;
  metadata?: Record<string, any>;
  created_at: string;
}

export interface MatchingPolicy {
  id?: string;
  policy_version: string;
  description: string;
  proximity_weight: number;
  rating_weight: number;
  availability_weight: number;
  reliability_weight: number;
  workload_weight: number;
  acceptance_weight: number;
  max_concurrent_jobs: number;
  offer_timeout_seconds: number;
  max_offer_attempts: number;
  is_active: boolean;
  created_at?: string;
  activated_at?: string | null;
}

export interface LocationAnomaly {
  id: string;
  mechanic_id: string;
  detected_at: string;
  anomaly_type: 'impossible_speed' | 'large_location_jump' | 'coordinates_out_of_bounds' | 'stale_heartbeat';
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'detected' | 'investigating' | 'resolved' | 'false_positive';
  description?: string;
  created_at: string;
}

export interface OperationalMetrics {
  snapshot_time: string;
  metrics: {
    booking_count: number;
    active_bookings: number;
    matching_sessions_total: number;
    average_time_to_match_seconds: number;
    matching_exhaustion_rate: number;
    offer_acceptance_rate: number;
    offer_expiration_rate: number;
    average_eta_minutes: number;
    routing_failure_rate: number;
    routing_fallback_rate: number;
    stale_location_rate: number;
    location_anomaly_count: number;
    scheduled_booking_count: number;
    scheduled_dispatch_failure_rate: number;
    inspection_approval_rate: number;
    service_completion_rate: number;
    payment_success_rate: number;
    payment_pending_count: number;
    dispute_rate: number;
    notification_failure_rate: number;
    timestamp?: string;
  };
}

export interface OperationalAlertThresholds {
  matching_exhaustion_rate: number;
  stale_location_rate: number;
  routing_failure_rate: number;
  notification_failure_rate: number;
  scheduled_dispatch_failure_rate: number;
  dispute_rate: number;
}

export const DEFAULT_OPERATIONAL_THRESHOLDS: OperationalAlertThresholds = {
  matching_exhaustion_rate: 0.10, // 10%
  stale_location_rate: 0.05,      // 5%
  routing_failure_rate: 0.05,     // 5%
  notification_failure_rate: 0.02,// 2%
  scheduled_dispatch_failure_rate: 0.02, // 2%
  dispute_rate: 0.03,             // 3%
};
