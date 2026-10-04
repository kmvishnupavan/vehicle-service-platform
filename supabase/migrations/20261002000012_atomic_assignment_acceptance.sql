-- Migration: 20261002000012_atomic_assignment_acceptance.sql
-- Description: Enforce atomic mechanic assignment acceptance and guarantee at most one accepted assignment per booking.

-- 1. Partial Unique Index: Physical database guarantee that only one assignment can be accepted per booking
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_accepted_assignment_per_booking
ON public.mechanic_assignments (booking_id)
WHERE assignment_status = 'accepted';

-- 2. Concurrency-Safe RPC Function for Atomic Assignment Acceptance
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
    v_assignment RECORD;
    v_booking RECORD;
    v_mechanic_profile_id UUID;
    v_now TIMESTAMPTZ := clock_timestamp();
    v_updated_assignment JSONB;
BEGIN
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
        -- Booking is already assigned or cancelled/completed; cancel this stale offer
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
    -- (This fires trg_track_booking_status automatically to record in booking_status_history)
    UPDATE public.bookings
    SET booking_status = 'mechanic_assigned',
        updated_at = v_now
    WHERE id = v_assignment.booking_id;

    -- 10. Cancel all sibling offered assignments for this booking
    UPDATE public.mechanic_assignments
    SET assignment_status = 'cancelled',
        updated_at = v_now
    WHERE booking_id = v_assignment.booking_id
      AND id <> p_assignment_id
      AND assignment_status = 'offered';

    -- 11. Customer notification
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
        -- Caught if another transaction committed accepted assignment concurrently
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

-- Grant execution to authenticated and service_role
GRANT EXECUTE ON FUNCTION public.accept_mechanic_assignment(UUID, UUID) TO authenticated, service_role;
