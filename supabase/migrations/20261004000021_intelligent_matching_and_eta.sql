-- Migration: 20261004000021_intelligent_matching_and_eta.sql
-- Description: Phase 11 Intelligent Mechanic Matching, ETA, Availability Model, and Operations Infrastructure
-- Author: Vehicle Service Platform Engineering Team

-- ============================================================================
-- 1. Mechanic Availability & Operational States
-- ============================================================================

ALTER TABLE public.mechanic_profiles
    ADD COLUMN IF NOT EXISTS availability_status TEXT NOT NULL DEFAULT 'available'
        CHECK (availability_status IN ('offline', 'available', 'busy', 'on_job', 'paused', 'suspended'));

-- Ensure availability_status and is_available stay in sync
CREATE OR REPLACE FUNCTION public.sync_mechanic_availability_status()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF NEW.verification_status = 'suspended' THEN
        NEW.availability_status := 'suspended';
        NEW.is_available := false;
    ELSIF NEW.availability_status = 'available' AND NEW.verification_status = 'verified' THEN
        NEW.is_available := true;
    ELSE
        NEW.is_available := false;
    END IF;
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_sync_mechanic_availability') THEN
        CREATE TRIGGER trg_sync_mechanic_availability
            BEFORE INSERT OR UPDATE OF availability_status, verification_status ON public.mechanic_profiles
            FOR EACH ROW EXECUTE FUNCTION public.sync_mechanic_availability_status();
    END IF;
END $$;


-- ============================================================================
-- 2. Mechanic Service Capabilities (Capability Matching)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.mechanic_service_capabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    category_id UUID REFERENCES public.service_categories(id) ON DELETE CASCADE,
    service_id UUID REFERENCES public.services(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_mech_cap_target CHECK (category_id IS NOT NULL OR service_id IS NOT NULL),
    CONSTRAINT uq_mech_cap_target UNIQUE (mechanic_id, category_id, service_id)
);

ALTER TABLE public.mechanic_service_capabilities ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_mechanic_service_capabilities_updated_at') THEN
        CREATE TRIGGER trg_mechanic_service_capabilities_updated_at
            BEFORE UPDATE ON public.mechanic_service_capabilities
            FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'mechanic_service_capabilities' AND policyname = 'mech_cap_select_active') THEN
        CREATE POLICY "mech_cap_select_active" ON public.mechanic_service_capabilities
            FOR SELECT
            TO authenticated
            USING (
                is_active = true
                OR public.is_admin_or_support()
                OR EXISTS (
                    SELECT 1 FROM public.mechanic_profiles mp
                    WHERE mp.id = mechanic_service_capabilities.mechanic_id
                      AND mp.user_id = auth.uid()
                )
            );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'mechanic_service_capabilities' AND policyname = 'mech_cap_manage_own') THEN
        CREATE POLICY "mech_cap_manage_own" ON public.mechanic_service_capabilities
            FOR ALL
            TO authenticated
            USING (
                public.is_admin_or_support()
                OR EXISTS (
                    SELECT 1 FROM public.mechanic_profiles mp
                    WHERE mp.id = mechanic_service_capabilities.mechanic_id
                      AND mp.user_id = auth.uid()
                )
            )
            WITH CHECK (
                public.is_admin_or_support()
                OR EXISTS (
                    SELECT 1 FROM public.mechanic_profiles mp
                    WHERE mp.id = mechanic_service_capabilities.mechanic_id
                      AND mp.user_id = auth.uid()
                )
            );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'mechanic_service_capabilities' AND policyname = 'mech_cap_service_role') THEN
        CREATE POLICY "mech_cap_service_role" ON public.mechanic_service_capabilities
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.mechanic_service_capabilities TO authenticated;
GRANT ALL ON public.mechanic_service_capabilities TO service_role;


-- ============================================================================
-- 3. Matching Sessions (Admin Visibility, Explainability & Audit)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.matching_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'searching'
        CHECK (status IN ('searching', 'offer_pending', 'matched', 'exhausted', 'timed_out', 'failed')),
    candidate_count INTEGER NOT NULL DEFAULT 0,
    candidates_ranked JSONB NOT NULL DEFAULT '[]'::jsonb,
    selected_mechanic_id UUID REFERENCES public.mechanic_profiles(id) ON DELETE SET NULL,
    current_attempt INTEGER NOT NULL DEFAULT 1,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.matching_sessions ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_matching_sessions_updated_at') THEN
        CREATE TRIGGER trg_matching_sessions_updated_at
            BEFORE UPDATE ON public.matching_sessions
            FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matching_sessions' AND policyname = 'matching_sessions_admin') THEN
        CREATE POLICY "matching_sessions_admin" ON public.matching_sessions
            FOR ALL
            TO authenticated
            USING (public.is_admin_or_support())
            WITH CHECK (public.is_admin_or_support());
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matching_sessions' AND policyname = 'matching_sessions_customer_select') THEN
        CREATE POLICY "matching_sessions_customer_select" ON public.matching_sessions
            FOR SELECT
            TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    WHERE b.id = matching_sessions.booking_id
                      AND b.customer_id = auth.uid()
                )
            );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'matching_sessions' AND policyname = 'matching_sessions_service_role') THEN
        CREATE POLICY "matching_sessions_service_role" ON public.matching_sessions
            FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

GRANT SELECT ON public.matching_sessions TO authenticated;
GRANT ALL ON public.matching_sessions TO service_role;


-- ============================================================================
-- 4. Mechanic Assignment Fields (Score, Expiration, Breakdown)
-- ============================================================================

ALTER TABLE public.mechanic_assignments
    ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS attempt_number INTEGER NOT NULL DEFAULT 1 CHECK (attempt_number >= 1),
    ADD COLUMN IF NOT EXISTS match_score NUMERIC(5, 4) CHECK (match_score IS NULL OR (match_score >= 0.0000 AND match_score <= 1.0000)),
    ADD COLUMN IF NOT EXISTS score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb;


-- ============================================================================
-- 5. Tighten Concurrency & Security on Atomic Acceptance RPC
-- ============================================================================

CREATE OR REPLACE FUNCTION public.accept_mechanic_assignment(
    p_assignment_id UUID,
    p_mechanic_user_id UUID
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_caller_id UUID := auth.uid();
    v_caller_role TEXT := auth.role();
    v_assignment RECORD;
    v_booking RECORD;
    v_mechanic_profile_id UUID;
    v_now TIMESTAMPTZ := clock_timestamp();
    v_updated_assignment JSONB;
BEGIN
    -- Caller identity verification
    IF v_caller_role = 'authenticated' THEN
        IF v_caller_id IS NULL OR (v_caller_id <> p_mechanic_user_id AND NOT public.is_admin_or_support()) THEN
            RETURN jsonb_build_object(
                'success', false,
                'error_code', 'FORBIDDEN',
                'message', 'Caller identity mismatch: cannot accept assignment for another user.'
            );
        END IF;
    END IF;

    -- 1. Resolve mechanic profile for authenticated user
    SELECT id INTO v_mechanic_profile_id
    FROM public.mechanic_profiles
    WHERE user_id = p_mechanic_user_id;

    IF v_mechanic_profile_id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'MECHANIC_PROFILE_NOT_FOUND',
            'message', 'Mechanic profile not found for authenticated user.'
        );
    END IF;

    -- 2. Lock the assignment row for update
    SELECT * INTO v_assignment
    FROM public.mechanic_assignments
    WHERE id = p_assignment_id
    FOR UPDATE;

    IF v_assignment.id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'ASSIGNMENT_NOT_FOUND',
            'message', 'Assignment not found.'
        );
    END IF;

    -- 3. Verify assignment belongs to this mechanic
    IF v_assignment.mechanic_id <> v_mechanic_profile_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'FORBIDDEN',
            'message', 'You can only accept assignments offered to your profile.'
        );
    END IF;

    -- 4. Verify assignment status is offered
    IF v_assignment.assignment_status <> 'offered' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'INVALID_ASSIGNMENT_STATUS',
            'message', 'Cannot accept assignment in ' || quote_literal(v_assignment.assignment_status) || ' status.'
        );
    END IF;

    -- Check if assignment has expired
    IF v_assignment.expires_at IS NOT NULL AND v_assignment.expires_at < v_now THEN
        UPDATE public.mechanic_assignments
        SET assignment_status = 'expired',
            updated_at = v_now
        WHERE id = p_assignment_id;

        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'OFFER_EXPIRED',
            'message', 'This job offer has expired.'
        );
    END IF;

    -- 5. Lock the booking row for update to serialize concurrent mechanic acceptance attempts
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE id = v_assignment.booking_id
    FOR UPDATE;

    IF v_booking.id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'BOOKING_NOT_FOUND',
            'message', 'Associated booking not found.'
        );
    END IF;

    -- 6. Check if booking is in an assignable status (pending or searching_mechanic)
    IF v_booking.booking_status NOT IN ('pending', 'searching_mechanic') THEN
        UPDATE public.mechanic_assignments
        SET assignment_status = 'cancelled',
            updated_at = v_now
        WHERE id = p_assignment_id;

        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'BOOKING_ALREADY_ASSIGNED',
            'message', 'Booking has already been assigned to another mechanic.'
        );
    END IF;

    -- 7. Double check if any other assignment was already accepted for this booking
    IF EXISTS (
        SELECT 1 FROM public.mechanic_assignments
        WHERE booking_id = v_assignment.booking_id
          AND assignment_status = 'accepted'
    ) THEN
        UPDATE public.mechanic_assignments
        SET assignment_status = 'cancelled',
            updated_at = v_now
        WHERE id = p_assignment_id;

        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'BOOKING_ALREADY_ASSIGNED',
            'message', 'Booking has already been assigned to another mechanic.'
        );
    END IF;

    -- 8. Atomically update assignment to accepted
    UPDATE public.mechanic_assignments
    SET assignment_status = 'accepted',
        responded_at = v_now,
        assigned_at = v_now,
        updated_at = v_now
    WHERE id = p_assignment_id
    RETURNING to_jsonb(mechanic_assignments.*) INTO v_updated_assignment;

    -- 9. Atomically advance booking status to mechanic_assigned
    UPDATE public.bookings
    SET booking_status = 'mechanic_assigned',
        updated_at = v_now
    WHERE id = v_assignment.booking_id;

    -- 10. Update matching session if present
    UPDATE public.matching_sessions
    SET status = 'matched',
        selected_mechanic_id = v_mechanic_profile_id,
        completed_at = v_now,
        updated_at = v_now
    WHERE booking_id = v_assignment.booking_id
      AND status IN ('searching', 'offer_pending');

    -- 11. Cancel all sibling offered assignments for this booking
    UPDATE public.mechanic_assignments
    SET assignment_status = 'cancelled',
        updated_at = v_now
    WHERE booking_id = v_assignment.booking_id
      AND id <> p_assignment_id
      AND assignment_status = 'offered';

    -- 12. Customer notification
    IF v_booking.customer_id IS NOT NULL THEN
        INSERT INTO public.notifications (
            user_id,
            type,
            title,
            message,
            data
        ) VALUES (
            v_booking.customer_id,
            'mechanic_assigned',
            'Mechanic Assigned',
            'A mechanic has accepted your booking and has been assigned.',
            jsonb_build_object(
                'booking_id', v_assignment.booking_id,
                'assignment_id', p_assignment_id,
                'mechanic_id', v_mechanic_profile_id
            )
        );
    END IF;

    RETURN jsonb_build_object(
        'success', true,
        'assignment', v_updated_assignment
    );
EXCEPTION
    WHEN unique_violation THEN
        UPDATE public.mechanic_assignments
        SET assignment_status = 'cancelled',
            updated_at = clock_timestamp()
        WHERE id = p_assignment_id;

        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'BOOKING_ALREADY_ASSIGNED',
            'message', 'Booking has already been assigned to another mechanic.'
        );
END;
$$;

GRANT EXECUTE ON FUNCTION public.accept_mechanic_assignment(UUID, UUID) TO authenticated, service_role;


-- ============================================================================
-- 6. Atomic Offer Rejection RPC
-- ============================================================================

CREATE OR REPLACE FUNCTION public.reject_mechanic_assignment(
    p_assignment_id UUID,
    p_mechanic_user_id UUID,
    p_reason TEXT DEFAULT NULL
)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, extensions, pg_temp
AS $$
DECLARE
    v_caller_id UUID := auth.uid();
    v_caller_role TEXT := auth.role();
    v_assignment RECORD;
    v_mechanic_profile_id UUID;
    v_now TIMESTAMPTZ := clock_timestamp();
    v_updated_assignment JSONB;
BEGIN
    IF v_caller_role = 'authenticated' THEN
        IF v_caller_id IS NULL OR (v_caller_id <> p_mechanic_user_id AND NOT public.is_admin_or_support()) THEN
            RETURN jsonb_build_object(
                'success', false,
                'error_code', 'FORBIDDEN',
                'message', 'Caller identity mismatch: cannot reject assignment for another user.'
            );
        END IF;
    END IF;

    SELECT id INTO v_mechanic_profile_id
    FROM public.mechanic_profiles
    WHERE user_id = p_mechanic_user_id;

    IF v_mechanic_profile_id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'MECHANIC_PROFILE_NOT_FOUND',
            'message', 'Mechanic profile not found for authenticated user.'
        );
    END IF;

    SELECT * INTO v_assignment
    FROM public.mechanic_assignments
    WHERE id = p_assignment_id
    FOR UPDATE;

    IF v_assignment.id IS NULL THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'ASSIGNMENT_NOT_FOUND',
            'message', 'Assignment not found.'
        );
    END IF;

    IF v_assignment.mechanic_id <> v_mechanic_profile_id THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'FORBIDDEN',
            'message', 'You can only reject assignments offered to your profile.'
        );
    END IF;

    IF v_assignment.assignment_status <> 'offered' THEN
        RETURN jsonb_build_object(
            'success', false,
            'error_code', 'INVALID_ASSIGNMENT_STATUS',
            'message', 'Cannot reject assignment in ' || quote_literal(v_assignment.assignment_status) || ' status.'
        );
    END IF;

    UPDATE public.mechanic_assignments
    SET assignment_status = 'rejected',
        responded_at = v_now,
        rejected_reason = p_reason,
        updated_at = v_now
    WHERE id = p_assignment_id
    RETURNING to_jsonb(mechanic_assignments.*) INTO v_updated_assignment;

    RETURN jsonb_build_object(
        'success', true,
        'assignment', v_updated_assignment
    );
END;
$$;

GRANT EXECUTE ON FUNCTION public.reject_mechanic_assignment(UUID, UUID, TEXT) TO authenticated, service_role;


-- ============================================================================
-- 7. High-Performance Indices for Matching Queries
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_mech_prof_matching_eligibility
    ON public.mechanic_profiles(is_available, verification_status, availability_status)
    WHERE is_available = true AND verification_status = 'verified';

CREATE INDEX IF NOT EXISTS idx_mech_prof_location_freshness
    ON public.mechanic_profiles(current_location_updated_at DESC)
    WHERE current_latitude IS NOT NULL AND current_longitude IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_mech_cap_mech_lookup
    ON public.mechanic_service_capabilities(mechanic_id, category_id, service_id)
    WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_matching_sessions_lookup
    ON public.matching_sessions(booking_id, status);

CREATE INDEX IF NOT EXISTS idx_mech_assign_timeout
    ON public.mechanic_assignments(assignment_status, expires_at)
    WHERE assignment_status = 'offered';
