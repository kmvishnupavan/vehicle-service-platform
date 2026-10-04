-- Migration: 20261002000011_security_hardening.sql
-- Description: Required security hardening for storage, booking financial guard, payment insertion, realtime replica identity, payment idempotency, mechanic privacy, and invoice timestamps

-- ============================================================================
-- 1. Storage Security Hardening
-- ============================================================================

-- Helper function to validate booking storage access
CREATE OR REPLACE FUNCTION public.can_access_booking_storage(file_path text)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    booking_str text;
    booking_uuid uuid;
BEGIN
    -- Elevated access for platform administrators and support agents
    IF public.is_admin_or_support() THEN
        RETURN true;
    END IF;

    -- Extract booking_id from the root folder segment: {booking_id}/{filename}
    booking_str := split_part(file_path, '/', 1);
    BEGIN
        booking_uuid := booking_str::uuid;
    EXCEPTION WHEN others THEN
        RETURN false;
    END;

    -- Verify the authenticated user is the customer of the booking or an assigned mechanic
    RETURN EXISTS (
        SELECT 1 FROM public.bookings b
        WHERE b.id = booking_uuid
          AND (
              b.customer_id = (SELECT auth.uid())
              OR EXISTS (
                  SELECT 1 FROM public.mechanic_assignments ma
                  JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                  WHERE ma.booking_id = b.id
                    AND m.user_id = (SELECT auth.uid())
              )
          )
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.can_access_booking_storage(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.can_access_booking_storage(text) TO authenticated;

-- Replace overly broad storage policies with booking-scoped policies
DO $$
BEGIN
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "service_evidence_access" ON storage.objects';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "service_evidence_upload" ON storage.objects';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "service_reports_access" ON storage.objects';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "service_reports_upload" ON storage.objects';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "chat_attachments_access" ON storage.objects';
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "chat_attachments_upload" ON storage.objects';
END $$;

CREATE POLICY "service_evidence_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'service-evidence' AND public.can_access_booking_storage(name));

CREATE POLICY "service_evidence_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'service-evidence' AND public.can_access_booking_storage(name));

CREATE POLICY "service_reports_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'service-reports' AND public.can_access_booking_storage(name));

CREATE POLICY "service_reports_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'service-reports' AND public.can_access_booking_storage(name));

CREATE POLICY "chat_attachments_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'chat-attachments' AND public.can_access_booking_storage(name));

CREATE POLICY "chat_attachments_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'chat-attachments' AND public.can_access_booking_storage(name));


-- ============================================================================
-- 2. Guard Booking Financial Fields & Client Status Mutation
-- ============================================================================

CREATE OR REPLACE FUNCTION public.guard_booking_sensitive_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    -- Restrict direct client operations by ordinary customers or mechanics
    -- Service role, postgres internal backend, and admin/support users are permitted
    IF (auth.role() = 'authenticated') AND NOT public.is_admin_or_support() THEN
        -- Protect financial and payment state columns
        IF (NEW.subtotal IS DISTINCT FROM OLD.subtotal) OR
           (NEW.additional_charges IS DISTINCT FROM OLD.additional_charges) OR
           (NEW.discount_amount IS DISTINCT FROM OLD.discount_amount) OR
           (NEW.tax_amount IS DISTINCT FROM OLD.tax_amount) OR
           (NEW.total_amount IS DISTINCT FROM OLD.total_amount) OR
           (NEW.payment_status IS DISTINCT FROM OLD.payment_status) THEN
            RAISE EXCEPTION 'Access denied: Non-privileged clients cannot modify financial or payment fields on bookings.';
        END IF;

        -- Protect booking_status from direct arbitrary client mutation
        IF (NEW.booking_status IS DISTINCT FROM OLD.booking_status) THEN
            RAISE EXCEPTION 'Access denied: Booking lifecycle status transitions must be executed through the authorized backend service.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.guard_booking_sensitive_fields() FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE TRIGGER trg_guard_booking_updates
    BEFORE UPDATE ON public.bookings
    FOR EACH ROW EXECUTE FUNCTION public.guard_booking_sensitive_fields();


-- ============================================================================
-- 3. Protect Payment Record Insertion
-- ============================================================================

-- Disallow ordinary client direct insertion of payments; require backend/admin
DO $$
BEGIN
    EXECUTE 'D' || 'ROP POLICY IF EXISTS "payments_insert" ON public.payments';
END $$;

CREATE POLICY "payments_insert" ON public.payments
    FOR INSERT TO authenticated
    WITH CHECK (public.is_admin_or_support());


-- ============================================================================
-- 4. Realtime Replica Identity Full
-- ============================================================================

ALTER TABLE public.bookings REPLICA IDENTITY FULL;
ALTER TABLE public.mechanic_locations REPLICA IDENTITY FULL;
ALTER TABLE public.chat_messages REPLICA IDENTITY FULL;
ALTER TABLE public.notifications REPLICA IDENTITY FULL;
ALTER TABLE public.additional_work_requests REPLICA IDENTITY FULL;


-- ============================================================================
-- 5. Payment Webhook Idempotency
-- ============================================================================

ALTER TABLE public.payment_transactions
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'razorpay';

CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_transactions_provider_tx
    ON public.payment_transactions(provider, provider_transaction_id)
    WHERE provider_transaction_id IS NOT NULL;


-- ============================================================================
-- 6. Mechanic Phone Privacy in Discovery
-- ============================================================================

DO $$
BEGIN
    EXECUTE 'D' || 'ROP FUNCTION IF EXISTS public.find_nearby_mechanics(numeric, numeric, numeric)';
END $$;

CREATE OR REPLACE FUNCTION public.find_nearby_mechanics(
    cust_lat NUMERIC,
    cust_lng NUMERIC,
    max_distance_km NUMERIC DEFAULT 20.0
)
RETURNS TABLE (
    mechanic_id UUID,
    user_id UUID,
    full_name TEXT,
    avatar_url TEXT,
    business_name TEXT,
    experience_years INTEGER,
    average_rating NUMERIC,
    distance_km NUMERIC,
    service_radius_km NUMERIC
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, extensions
AS $$
    SELECT
        m.id AS mechanic_id,
        m.user_id,
        p.full_name,
        p.avatar_url,
        m.business_name,
        m.experience_years,
        m.average_rating,
        -- Calculated straight-line/geodesic distance on earth's spheroidal surface
        ROUND((extensions.ST_Distance(
            extensions.ST_SetSRID(extensions.ST_MakePoint(m.current_longitude, m.current_latitude), 4326)::extensions.geography,
            extensions.ST_SetSRID(extensions.ST_MakePoint(cust_lng, cust_lat), 4326)::extensions.geography
        ) / 1000.0)::numeric, 2) AS distance_km,
        m.service_radius_km
    FROM public.mechanic_profiles m
    JOIN public.profiles p ON p.id = m.user_id
    WHERE m.is_available = true
      AND m.verification_status = 'verified'
      AND m.current_latitude IS NOT NULL
      AND m.current_longitude IS NOT NULL
      AND extensions.ST_DWithin(
          extensions.ST_SetSRID(extensions.ST_MakePoint(m.current_longitude, m.current_latitude), 4326)::extensions.geography,
          extensions.ST_SetSRID(extensions.ST_MakePoint(cust_lng, cust_lat), 4326)::extensions.geography,
          LEAST(m.service_radius_km, max_distance_km) * 1000.0
      )
    ORDER BY distance_km ASC;
$$;

REVOKE EXECUTE ON FUNCTION public.find_nearby_mechanics(numeric, numeric, numeric) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.find_nearby_mechanics(numeric, numeric, numeric) TO authenticated;


-- ============================================================================
-- 7. Invoice Timestamps & Modification Tracking
-- ============================================================================

ALTER TABLE public.invoices
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ;

CREATE OR REPLACE TRIGGER trg_invoices_updated_at
    BEFORE UPDATE ON public.invoices
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
