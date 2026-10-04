-- Migration: 20261002000003_create_service_and_booking_tables.sql
-- Description: Services, Pricing, Bookings, Status History, Assignments, Locations, Inspections, and Additional Work

-- 10. Service Categories
CREATE TABLE public.service_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    icon_url TEXT,
    display_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 11. Services
CREATE TABLE public.services (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id UUID NOT NULL REFERENCES public.service_categories(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    description TEXT,
    vehicle_type TEXT NOT NULL CHECK (vehicle_type IN ('bike', 'car', 'both')),
    estimated_duration_minutes INTEGER NOT NULL DEFAULT 60 CHECK (estimated_duration_minutes > 0),
    is_emergency BOOLEAN NOT NULL DEFAULT false,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 12. Service Pricing
CREATE TABLE public.service_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_id UUID NOT NULL REFERENCES public.services(id) ON DELETE CASCADE,
    vehicle_type_id UUID REFERENCES public.vehicle_types(id) ON DELETE CASCADE,
    base_price NUMERIC(10, 2) NOT NULL CHECK (base_price >= 0),
    minimum_price NUMERIC(10, 2) NOT NULL CHECK (minimum_price >= 0),
    pricing_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    effective_to TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_service_pricing_dates CHECK (effective_to IS NULL OR effective_to > effective_from)
);

-- 13. Bookings
CREATE TABLE public.bookings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_number TEXT NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    vehicle_id UUID NOT NULL REFERENCES public.vehicles(id) ON DELETE RESTRICT,
    address_id UUID NOT NULL REFERENCES public.addresses(id) ON DELETE RESTRICT,
    scheduled_at TIMESTAMPTZ NOT NULL,
    requested_latitude NUMERIC(10, 7) NOT NULL CHECK (requested_latitude BETWEEN -90.0 AND 90.0),
    requested_longitude NUMERIC(10, 7) NOT NULL CHECK (requested_longitude BETWEEN -180.0 AND 180.0),
    customer_notes TEXT,
    subtotal NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (subtotal >= 0),
    additional_charges NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (additional_charges >= 0),
    discount_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (discount_amount >= 0),
    tax_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (tax_amount >= 0),
    total_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (total_amount >= 0),
    payment_status TEXT NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'partially_paid', 'paid', 'refunded', 'failed')),
    booking_status TEXT NOT NULL DEFAULT 'pending' CHECK (booking_status IN (
        'pending',
        'searching_mechanic',
        'mechanic_assigned',
        'mechanic_en_route',
        'mechanic_arrived',
        'inspection',
        'awaiting_customer_approval',
        'service_in_progress',
        'additional_work',
        'service_completed',
        'payment_pending',
        'paid',
        'cancelled',
        'disputed'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 14. Booking Items
CREATE TABLE public.booking_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    service_id UUID NOT NULL REFERENCES public.services(id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL CHECK (unit_price >= 0),
    total_price NUMERIC(10, 2) NOT NULL CHECK (total_price >= 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 15. Booking Status History
CREATE TABLE public.booking_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 16. Mechanic Assignments
CREATE TABLE public.mechanic_assignments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    assignment_status TEXT NOT NULL DEFAULT 'offered' CHECK (assignment_status IN ('offered', 'accepted', 'rejected', 'expired', 'cancelled', 'completed')),
    distance_km NUMERIC(6, 2) CHECK (distance_km >= 0),
    estimated_arrival_minutes INTEGER CHECK (estimated_arrival_minutes >= 0),
    offered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    responded_at TIMESTAMPTZ,
    assigned_at TIMESTAMPTZ,
    rejected_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 17. Mechanic Locations (Tracking)
CREATE TABLE public.mechanic_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    latitude NUMERIC(10, 7) NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude NUMERIC(10, 7) NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    accuracy_meters NUMERIC(6, 2) CHECK (accuracy_meters >= 0),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 18. Service Inspections
CREATE TABLE public.service_inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    findings TEXT NOT NULL,
    vehicle_condition TEXT,
    estimated_additional_cost NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (estimated_additional_cost >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 19. Additional Work Requests
CREATE TABLE public.additional_work_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    evidence_file_paths TEXT[] NOT NULL DEFAULT '{}'::text[],
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'completed')),
    customer_response TEXT,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Triggers for updated_at
CREATE TRIGGER trg_service_categories_updated_at
    BEFORE UPDATE ON public.service_categories
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_services_updated_at
    BEFORE UPDATE ON public.services
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_service_pricing_updated_at
    BEFORE UPDATE ON public.service_pricing
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_bookings_updated_at
    BEFORE UPDATE ON public.bookings
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_mechanic_assignments_updated_at
    BEFORE UPDATE ON public.mechanic_assignments
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_service_inspections_updated_at
    BEFORE UPDATE ON public.service_inspections
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_additional_work_requests_updated_at
    BEFORE UPDATE ON public.additional_work_requests
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Trigger to record booking status history automatically on status change
CREATE OR REPLACE FUNCTION public.track_booking_status_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (TG_OP = 'INSERT') OR (OLD.booking_status IS DISTINCT FROM NEW.booking_status) THEN
        INSERT INTO public.booking_status_history (
            booking_id,
            old_status,
            new_status,
            changed_by,
            reason
        ) VALUES (
            NEW.id,
            CASE WHEN TG_OP = 'INSERT' THEN NULL ELSE OLD.booking_status END,
            NEW.booking_status,
            auth.uid(),
            CASE WHEN TG_OP = 'INSERT' THEN 'Initial booking creation' ELSE 'Booking status updated' END
        );
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_track_booking_status
    AFTER INSERT OR UPDATE ON public.bookings
    FOR EACH ROW EXECUTE FUNCTION public.track_booking_status_change();
