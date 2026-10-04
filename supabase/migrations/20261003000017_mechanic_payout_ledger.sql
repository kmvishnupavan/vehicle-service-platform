-- ==============================================================================
-- Phase 8.7 — Mechanic Payout Ledger & Settlement Foundation
-- Migration: 20261003000017_mechanic_payout_ledger.sql
-- ==============================================================================

-- 1. Commission Policies Table
CREATE TABLE IF NOT EXISTS public.commission_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    commission_rate NUMERIC(5, 4) NOT NULL CHECK (commission_rate >= 0.0000 AND commission_rate <= 1.0000),
    currency TEXT NOT NULL DEFAULT 'INR',
    is_active BOOLEAN NOT NULL DEFAULT true,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Insert baseline default commission policy (20% platform commission, 80% mechanic payout)
INSERT INTO public.commission_policies (id, name, commission_rate, currency, is_active, effective_from)
VALUES (
    'c0000000-0000-0000-0000-000000000001',
    'Standard Platform Commission (20%)',
    0.2000,
    'INR',
    true,
    '2026-01-01T00:00:00Z'
)
ON CONFLICT (id) DO NOTHING;

-- 2. Mechanic Payout Ledger Table
CREATE TABLE IF NOT EXISTS public.mechanic_payout_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE RESTRICT,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE RESTRICT,
    payment_id UUID NULL REFERENCES public.payments(id) ON DELETE SET NULL,
    payment_transaction_id UUID NULL REFERENCES public.payment_transactions(id) ON DELETE SET NULL,
    policy_id UUID NULL REFERENCES public.commission_policies(id) ON DELETE SET NULL,

    gross_amount NUMERIC(12, 2) NOT NULL CHECK (gross_amount >= 0.00),
    commission_rate NUMERIC(5, 4) NOT NULL CHECK (commission_rate >= 0.0000 AND commission_rate <= 1.0000),
    commission_amount NUMERIC(12, 2) NOT NULL CHECK (commission_amount >= 0.00),
    deduction_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (deduction_amount >= 0.00),
    net_amount NUMERIC(12, 2) NOT NULL CHECK (net_amount >= 0.00),

    currency TEXT NOT NULL DEFAULT 'INR',
    status TEXT NOT NULL CHECK (status IN ('pending', 'eligible', 'processing', 'paid', 'failed', 'reversed', 'cancelled')),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    eligible_at TIMESTAMPTZ NULL,
    settled_at TIMESTAMPTZ NULL,
    reversed_at TIMESTAMPTZ NULL,

    provider TEXT NOT NULL DEFAULT 'manual',
    provider_payout_id TEXT NULL,
    failure_reason TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT uq_payout_ledger_booking_mechanic UNIQUE (booking_id, mechanic_id)
);

-- 3. Indexes for Query Performance and Financial Reporting
CREATE INDEX IF NOT EXISTS idx_payout_ledger_mechanic_id ON public.mechanic_payout_ledger(mechanic_id);
CREATE INDEX IF NOT EXISTS idx_payout_ledger_booking_id ON public.mechanic_payout_ledger(booking_id);
CREATE INDEX IF NOT EXISTS idx_payout_ledger_status ON public.mechanic_payout_ledger(status);
CREATE INDEX IF NOT EXISTS idx_payout_ledger_created_at ON public.mechanic_payout_ledger(created_at);
CREATE INDEX IF NOT EXISTS idx_payout_ledger_eligible_at ON public.mechanic_payout_ledger(eligible_at) WHERE status = 'eligible';
CREATE INDEX IF NOT EXISTS idx_commission_policies_active ON public.commission_policies(is_active, effective_from);

-- 4. Triggers for Automatic updated_at Maintenance
CREATE TRIGGER trg_commission_policies_updated_at
    BEFORE UPDATE ON public.commission_policies
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_mechanic_payout_ledger_updated_at
    BEFORE UPDATE ON public.mechanic_payout_ledger
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- 5. Row-Level Security (RLS) Configuration
ALTER TABLE public.commission_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mechanic_payout_ledger ENABLE ROW LEVEL SECURITY;

-- Policies for commission_policies
CREATE POLICY commission_policies_select
    ON public.commission_policies FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY commission_policies_admin_write
    ON public.commission_policies FOR ALL
    TO authenticated
    USING (is_admin())
    WITH CHECK (is_admin());

-- Policies for mechanic_payout_ledger
CREATE POLICY mechanic_payout_ledger_select
    ON public.mechanic_payout_ledger FOR SELECT
    TO authenticated
    USING (
        (mechanic_id = get_mechanic_id_for_user(auth.uid()))
        OR is_admin_or_support()
    );

CREATE POLICY mechanic_payout_ledger_admin_insert
    ON public.mechanic_payout_ledger FOR INSERT
    TO authenticated
    WITH CHECK (is_admin_or_support());

CREATE POLICY mechanic_payout_ledger_admin_update
    ON public.mechanic_payout_ledger FOR UPDATE
    TO authenticated
    USING (is_admin_or_support())
    WITH CHECK (is_admin_or_support());

CREATE POLICY mechanic_payout_ledger_admin_delete
    ON public.mechanic_payout_ledger FOR DELETE
    TO authenticated
    USING (is_admin());
