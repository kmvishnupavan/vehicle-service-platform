-- ============================================================================
-- VehicleCare Doorstep Vehicle Service Platform
-- Migration: 20261004000023_production_operations_automation.sql
-- Description: Phase 13 - Production Reliability, Background Jobs, Scheduled Bookings,
--              Dynamic ETA, Location Quality, and Matching Policy Versioning.
-- ============================================================================

-- ============================================================================
-- 1. Background Job Executions Ledger
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.background_job_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name TEXT NOT NULL,
    execution_id TEXT NOT NULL UNIQUE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'partial_failure', 'failed')),
    records_processed INTEGER NOT NULL DEFAULT 0,
    records_succeeded INTEGER NOT NULL DEFAULT 0,
    records_failed INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.background_job_executions ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_bg_job_name_started 
ON public.background_job_executions(job_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_bg_job_status 
ON public.background_job_executions(status);

-- RLS: Admin/support read-only; service_role full
CREATE POLICY bg_job_executions_admin_select ON public.background_job_executions
    FOR SELECT TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY bg_job_executions_service_all ON public.background_job_executions
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- 2. Distributed Advisory Locking Helpers for Background Jobs
-- ============================================================================

CREATE OR REPLACE FUNCTION public.try_acquire_job_lock(p_job_name TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    RETURN pg_try_advisory_lock(hashtext(p_job_name));
END;
$$;

CREATE OR REPLACE FUNCTION public.release_job_lock(p_job_name TEXT)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
BEGIN
    RETURN pg_advisory_unlock(hashtext(p_job_name));
END;
$$;

GRANT EXECUTE ON FUNCTION public.try_acquire_job_lock(TEXT) TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.release_job_lock(TEXT) TO authenticated, service_role;


-- ============================================================================
-- 3. Scheduled Bookings Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.scheduled_bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL UNIQUE REFERENCES public.bookings(id) ON DELETE CASCADE,
    scheduled_start_at TIMESTAMPTZ NOT NULL,
    scheduled_end_at TIMESTAMPTZ NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    dispatch_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'dispatching', 'dispatched', 'cancelled', 'completed', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    dispatched_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    failure_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_scheduled_window CHECK (scheduled_end_at >= scheduled_start_at),
    CONSTRAINT chk_dispatch_before_start CHECK (dispatch_at <= scheduled_start_at)
);

ALTER TABLE public.scheduled_bookings ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_scheduled_bookings_dispatch 
ON public.scheduled_bookings(status, dispatch_at);

CREATE INDEX IF NOT EXISTS idx_scheduled_bookings_booking_id 
ON public.scheduled_bookings(booking_id);

-- RLS Policies
CREATE POLICY scheduled_bookings_customer_select ON public.scheduled_bookings
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = scheduled_bookings.booking_id
              AND b.customer_id = auth.uid()
        )
        OR public.is_admin_or_support()
    );

CREATE POLICY scheduled_bookings_customer_cancel ON public.scheduled_bookings
    FOR UPDATE TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = scheduled_bookings.booking_id
              AND b.customer_id = auth.uid()
        )
        OR public.is_admin_or_support()
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = scheduled_bookings.booking_id
              AND b.customer_id = auth.uid()
        )
        OR public.is_admin_or_support()
    );

CREATE POLICY scheduled_bookings_service_all ON public.scheduled_bookings
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- 4. Versioned Matching Policies Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.matching_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_version TEXT NOT NULL UNIQUE,
    proximity_weight NUMERIC(4,3) NOT NULL CHECK (proximity_weight >= 0 AND proximity_weight <= 1),
    rating_weight NUMERIC(4,3) NOT NULL CHECK (rating_weight >= 0 AND rating_weight <= 1),
    availability_weight NUMERIC(4,3) NOT NULL CHECK (availability_weight >= 0 AND availability_weight <= 1),
    reliability_weight NUMERIC(4,3) NOT NULL CHECK (reliability_weight >= 0 AND reliability_weight <= 1),
    workload_weight NUMERIC(4,3) NOT NULL CHECK (workload_weight >= 0 AND workload_weight <= 1),
    acceptance_weight NUMERIC(4,3) NOT NULL CHECK (acceptance_weight >= 0 AND acceptance_weight <= 1),
    max_concurrent_jobs INTEGER NOT NULL DEFAULT 1 CHECK (max_concurrent_jobs > 0),
    offer_timeout_seconds INTEGER NOT NULL DEFAULT 60 CHECK (offer_timeout_seconds > 0),
    max_offer_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_offer_attempts > 0),
    is_active BOOLEAN NOT NULL DEFAULT false,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    created_by UUID REFERENCES public.profiles(id),
    activated_at TIMESTAMPTZ,
    activated_by UUID REFERENCES public.profiles(id),
    CONSTRAINT chk_weights_sum_to_one CHECK (
        (proximity_weight + rating_weight + availability_weight + reliability_weight + workload_weight + acceptance_weight) = 1.000
    )
);

ALTER TABLE public.matching_policies ENABLE ROW LEVEL SECURITY;

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_matching_policy 
ON public.matching_policies(is_active) 
WHERE is_active = true;

-- RLS Policies
CREATE POLICY matching_policies_read_active ON public.matching_policies
    FOR SELECT TO authenticated
    USING (is_active = true OR public.is_admin_or_support());

CREATE POLICY matching_policies_admin_manage ON public.matching_policies
    FOR ALL TO authenticated
    USING (public.is_admin_or_support())
    WITH CHECK (public.is_admin_or_support());

CREATE POLICY matching_policies_service_all ON public.matching_policies
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);

-- Seed Initial Default Matching Policy v1.0
INSERT INTO public.matching_policies (
    policy_version,
    proximity_weight,
    rating_weight,
    availability_weight,
    reliability_weight,
    workload_weight,
    acceptance_weight,
    max_concurrent_jobs,
    offer_timeout_seconds,
    max_offer_attempts,
    is_active,
    description,
    activated_at
) VALUES (
    'v1.0',
    0.300,
    0.200,
    0.150,
    0.150,
    0.100,
    0.100,
    1,
    60,
    3,
    true,
    'Standard Production Matching Policy v1.0',
    clock_timestamp()
) ON CONFLICT (policy_version) DO NOTHING;


-- ============================================================================
-- 5. Mechanic Location Quality & GPS Anomaly Log
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.mechanic_location_anomalies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    booking_id UUID REFERENCES public.bookings(id) ON DELETE SET NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    previous_location JSONB,
    new_location JSONB NOT NULL,
    distance_meters NUMERIC(10,2),
    time_delta_seconds NUMERIC(10,2),
    calculated_speed_kmh NUMERIC(10,2),
    anomaly_type TEXT NOT NULL CHECK (anomaly_type IN (
        'impossible_speed',
        'large_location_jump',
        'stale_location',
        'invalid_coordinates',
        'poor_accuracy',
        'location_spoofing_suspected'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    status TEXT NOT NULL DEFAULT 'flagged' CHECK (status IN ('flagged', 'reviewed', 'dismissed', 'escalated')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.mechanic_location_anomalies ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_location_anomalies_mech 
ON public.mechanic_location_anomalies(mechanic_id, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_location_anomalies_status 
ON public.mechanic_location_anomalies(status, severity);

-- RLS Policies
CREATE POLICY location_anomalies_admin_select ON public.mechanic_location_anomalies
    FOR SELECT TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY location_anomalies_admin_update ON public.mechanic_location_anomalies
    FOR UPDATE TO authenticated
    USING (public.is_admin_or_support())
    WITH CHECK (public.is_admin_or_support());

CREATE POLICY location_anomalies_service_all ON public.mechanic_location_anomalies
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- 6. Notification Retries Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.notification_retries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    last_attempt_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'retrying', 'delivered', 'exhausted', 'cancelled')),
    last_error TEXT,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.notification_retries ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_notification_retries_queue 
ON public.notification_retries(status, next_retry_at);

CREATE INDEX IF NOT EXISTS idx_notification_retries_user 
ON public.notification_retries(user_id);

-- RLS Policies
CREATE POLICY notification_retries_user_select ON public.notification_retries
    FOR SELECT TO authenticated
    USING (user_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY notification_retries_service_all ON public.notification_retries
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);


-- ============================================================================
-- 7. Operational Metrics Snapshots Table
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.operational_metrics_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_time TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    metrics JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.operational_metrics_snapshots ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_operational_metrics_time 
ON public.operational_metrics_snapshots(snapshot_time DESC);

-- RLS Policies
CREATE POLICY operational_metrics_admin_select ON public.operational_metrics_snapshots
    FOR SELECT TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY operational_metrics_service_all ON public.operational_metrics_snapshots
    FOR ALL TO service_role
    USING (true)
    WITH CHECK (true);
