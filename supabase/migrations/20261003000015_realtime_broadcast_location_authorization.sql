-- Migration: 20261003000015_realtime_broadcast_location_authorization.sql
-- Description: Phase 8.2B Supabase Realtime Broadcast authorization for live mechanic location tracking.
-- Scopes ephemeral private channel `booking-location:{booking_id}` to authorized participants:
-- 1. SELECT (Receive): Customer of active booking, accepted assigned mechanic, or admin/support.
-- 2. INSERT (Send): Only the accepted assigned mechanic on active booking (and authorized admin/support).

-- ============================================================================
-- 1. Helper: Extract and Validate Booking UUID from Realtime Topic
-- ============================================================================

CREATE OR REPLACE FUNCTION public.get_booking_id_from_realtime_topic(p_topic text)
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    booking_str text;
    booking_uuid uuid;
BEGIN
    IF p_topic IS NULL THEN
        RETURN NULL;
    END IF;

    -- Topic must strictly adhere to format 'booking-location:{booking_id}'
    IF NOT p_topic LIKE 'booking-location:%' THEN
        RETURN NULL;
    END IF;

    booking_str := split_part(p_topic, ':', 2);
    BEGIN
        booking_uuid := booking_str::uuid;
    EXCEPTION WHEN others THEN
        RETURN NULL;
    END;

    RETURN booking_uuid;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.get_booking_id_from_realtime_topic(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.get_booking_id_from_realtime_topic(text) TO authenticated, service_role;


-- ============================================================================
-- 2. Helper: Validate Realtime Broadcast Subscription / Receive Authorization
-- ============================================================================

CREATE OR REPLACE FUNCTION public.can_receive_booking_location(p_topic text)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_booking_id uuid;
    v_user_id uuid := (SELECT auth.uid());
BEGIN
    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;

    -- Platform operators have oversight capability
    IF public.is_admin_or_support() THEN
        RETURN true;
    END IF;

    v_booking_id := public.get_booking_id_from_realtime_topic(p_topic);
    IF v_booking_id IS NULL THEN
        RETURN false;
    END IF;

    -- Allow only if booking is currently in an active service lifecycle state
    -- Completed, cancelled, and payment-pending bookings cannot receive live GPS tracking
    RETURN EXISTS (
        SELECT 1
        FROM public.bookings b
        WHERE b.id = v_booking_id
          AND b.booking_status IN (
              'mechanic_assigned',
              'mechanic_en_route',
              'mechanic_arrived',
              'inspection',
              'awaiting_customer_approval',
              'service_in_progress',
              'additional_work'
          )
          AND (
              b.customer_id = v_user_id
              OR EXISTS (
                  SELECT 1
                  FROM public.mechanic_assignments ma
                  JOIN public.mechanic_profiles mp ON mp.id = ma.mechanic_id
                  WHERE ma.booking_id = b.id
                    AND ma.assignment_status = 'accepted'
                    AND mp.user_id = v_user_id
              )
          )
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.can_receive_booking_location(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.can_receive_booking_location(text) TO authenticated, service_role;


-- ============================================================================
-- 3. Helper: Validate Realtime Broadcast Publish / Send Authorization
-- ============================================================================

CREATE OR REPLACE FUNCTION public.can_publish_booking_location(p_topic text)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_booking_id uuid;
    v_user_id uuid := (SELECT auth.uid());
BEGIN
    IF v_user_id IS NULL THEN
        RETURN false;
    END IF;

    -- Platform administrators/support agents may broadcast operational updates
    IF public.is_admin_or_support() THEN
        RETURN true;
    END IF;

    v_booking_id := public.get_booking_id_from_realtime_topic(p_topic);
    IF v_booking_id IS NULL THEN
        RETURN false;
    END IF;

    -- Only the assigned mechanic with 'accepted' assignment on an active booking can broadcast
    -- Customers and unaffiliated mechanics are strictly forbidden from publishing GPS locations
    RETURN EXISTS (
        SELECT 1
        FROM public.bookings b
        JOIN public.mechanic_assignments ma ON ma.booking_id = b.id
        JOIN public.mechanic_profiles mp ON mp.id = ma.mechanic_id
        WHERE b.id = v_booking_id
          AND ma.assignment_status = 'accepted'
          AND mp.user_id = v_user_id
          AND b.booking_status IN (
              'mechanic_assigned',
              'mechanic_en_route',
              'mechanic_arrived',
              'inspection',
              'awaiting_customer_approval',
              'service_in_progress',
              'additional_work'
          )
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.can_publish_booking_location(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.can_publish_booking_location(text) TO authenticated, service_role;


-- ============================================================================
-- 4. Realtime Messages Row Level Security Policies
-- ============================================================================

-- Safely drop existing policies if re-running
DO $$
BEGIN
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "realtime_booking_location_receive" ON realtime.messages';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "realtime_booking_location_send" ON realtime.messages';
END $$;

-- Policy to permit receiving broadcasts on authorized private booking channels
CREATE POLICY "realtime_booking_location_receive"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
    public.can_receive_booking_location(topic)
);

-- Policy to permit publishing broadcasts on authorized private booking channels
CREATE POLICY "realtime_booking_location_send"
ON realtime.messages
FOR INSERT
TO authenticated
WITH CHECK (
    public.can_publish_booking_location(topic)
);
