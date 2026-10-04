-- Migration: 20261002000004_create_payment_invoice_review_tables.sql
-- Description: Payments, Transactions, Invoices, Service Reports, Reviews, Coupons, and Coupon Usage

-- 20. Payments
CREATE TABLE public.payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    currency VARCHAR(3) NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'authorized', 'captured', 'failed', 'refunded')),
    payment_method TEXT,
    provider TEXT NOT NULL,
    provider_payment_id TEXT,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 21. Payment Transactions
CREATE TABLE public.payment_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    payment_id UUID NOT NULL REFERENCES public.payments(id) ON DELETE CASCADE,
    provider_transaction_id TEXT,
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0),
    status TEXT NOT NULL CHECK (status IN ('initiated', 'processing', 'successful', 'failed', 'refunded')),
    raw_provider_response JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 22. Invoices
CREATE TABLE public.invoices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invoice_number TEXT NOT NULL UNIQUE,
    booking_id UUID NOT NULL UNIQUE REFERENCES public.bookings(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    subtotal NUMERIC(10, 2) NOT NULL CHECK (subtotal >= 0),
    tax NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (tax >= 0),
    discount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (discount >= 0),
    total NUMERIC(10, 2) NOT NULL CHECK (total >= 0),
    issued_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('draft', 'issued', 'paid', 'void', 'refunded')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 23. Service Reports
CREATE TABLE public.service_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL UNIQUE REFERENCES public.bookings(id) ON DELETE CASCADE,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    summary TEXT NOT NULL,
    work_performed TEXT NOT NULL,
    recommendations TEXT,
    customer_notes TEXT,
    report_file_path TEXT,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 24. Reviews
CREATE TABLE public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL UNIQUE REFERENCES public.bookings(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    review_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 25. Coupons
CREATE TABLE public.coupons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    description TEXT,
    discount_type TEXT NOT NULL CHECK (discount_type IN ('percentage', 'flat')),
    discount_value NUMERIC(10, 2) NOT NULL CHECK (discount_value > 0),
    minimum_order_amount NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (minimum_order_amount >= 0),
    maximum_discount NUMERIC(10, 2) CHECK (maximum_discount IS NULL OR maximum_discount > 0),
    usage_limit INTEGER CHECK (usage_limit IS NULL OR usage_limit > 0),
    per_user_limit INTEGER NOT NULL DEFAULT 1 CHECK (per_user_limit > 0),
    starts_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT chk_coupon_dates CHECK (expires_at IS NULL OR expires_at > starts_at)
);

-- 26. Coupon Usage
CREATE TABLE public.coupon_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    coupon_id UUID NOT NULL REFERENCES public.coupons(id) ON DELETE RESTRICT,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    discount_applied NUMERIC(10, 2) NOT NULL CHECK (discount_applied > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_coupon_booking UNIQUE (coupon_id, booking_id)
);

-- Triggers for updated_at
CREATE TRIGGER trg_payments_updated_at
    BEFORE UPDATE ON public.payments
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_service_reports_updated_at
    BEFORE UPDATE ON public.service_reports
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_reviews_updated_at
    BEFORE UPDATE ON public.reviews
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_coupons_updated_at
    BEFORE UPDATE ON public.coupons
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Trigger to recalculate mechanic ratings and total jobs
CREATE OR REPLACE FUNCTION public.sync_mechanic_stats_on_review()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    target_mechanic_id UUID;
    calc_avg NUMERIC(3, 2);
BEGIN
    target_mechanic_id := COALESCE(NEW.mechanic_id, OLD.mechanic_id);

    SELECT COALESCE(ROUND(AVG(rating)::numeric, 2), 0.00)
    INTO calc_avg
    FROM public.reviews
    WHERE mechanic_id = target_mechanic_id;

    UPDATE public.mechanic_profiles
    SET average_rating = calc_avg
    WHERE id = target_mechanic_id;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_sync_mechanic_review_stats
    AFTER INSERT OR UPDATE OR DELETE ON public.reviews
    FOR EACH ROW EXECUTE FUNCTION public.sync_mechanic_stats_on_review();

-- Trigger to update mechanic completed jobs counter when booking completes
CREATE OR REPLACE FUNCTION public.sync_mechanic_completed_jobs()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    assigned_mechanic UUID;
BEGIN
    IF NEW.booking_status = 'service_completed' AND (OLD.booking_status IS DISTINCT FROM 'service_completed') THEN
        SELECT mechanic_id INTO assigned_mechanic
        FROM public.mechanic_assignments
        WHERE booking_id = NEW.id AND assignment_status = 'accepted'
        ORDER BY created_at DESC
        LIMIT 1;

        IF assigned_mechanic IS NOT NULL THEN
            UPDATE public.mechanic_profiles
            SET total_completed_jobs = total_completed_jobs + 1
            WHERE id = assigned_mechanic;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_sync_mechanic_completed_jobs
    AFTER UPDATE OF booking_status ON public.bookings
    FOR EACH ROW EXECUTE FUNCTION public.sync_mechanic_completed_jobs();
