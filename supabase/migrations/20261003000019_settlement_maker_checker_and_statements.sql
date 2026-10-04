-- Migration: 20261003000019_settlement_maker_checker_and_statements.sql
-- Description: Phase 8.9 — Maker-Checker Settlement Approvals, Policies & Financial Immutability
-- Author: Antigravity Assistant
-- Target Database: vehicle-service-platform (dfigtryvvujhwuiyzdvs)

-- 1. Extend settlement_batches status CHECK constraint with approval states
ALTER TABLE public.settlement_batches 
    DROP CONSTRAINT IF EXISTS settlement_batches_status_check;

ALTER TABLE public.settlement_batches 
    ADD CONSTRAINT settlement_batches_status_check 
    CHECK (status IN (
        'draft', 
        'approval_required', 
        'approved', 
        'rejected', 
        'submitted', 
        'processing', 
        'completed', 
        'partially_failed',
        'failed', 
        'cancelled'
    ));

-- 2. Settlement Approval Policies Table (Configurable High-Value Thresholds)
CREATE TABLE IF NOT EXISTS public.settlement_approval_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    threshold_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (threshold_amount >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    requires_checker BOOLEAN NOT NULL DEFAULT true,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed default policy: All batches require checker approval during development / test
INSERT INTO public.settlement_approval_policies (threshold_amount, currency, requires_checker, is_active)
SELECT 0.00, 'INR', true, true
WHERE NOT EXISTS (SELECT 1 FROM public.settlement_approval_policies);

-- 3. Dedicated Settlement Batch Approvals Audit Trail Table
CREATE TABLE IF NOT EXISTS public.settlement_batch_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    settlement_batch_id UUID NOT NULL REFERENCES public.settlement_batches(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('submitted_for_approval', 'approved', 'rejected', 'cancelled')),
    actor_id UUID NOT NULL REFERENCES auth.users(id),
    actor_role TEXT NOT NULL,
    reason TEXT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes for fast querying of approvals
CREATE INDEX IF NOT EXISTS idx_batch_approvals_batch_id ON public.settlement_batch_approvals(settlement_batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_approvals_actor_id ON public.settlement_batch_approvals(actor_id);
CREATE INDEX IF NOT EXISTS idx_batch_approvals_action ON public.settlement_batch_approvals(action);

-- 4. Database-Enforced Maker != Checker Trigger
CREATE OR REPLACE FUNCTION public.check_maker_checker_approval()
RETURNS TRIGGER AS $$
DECLARE
    v_created_by UUID;
    v_current_status TEXT;
BEGIN
    IF NEW.action IN ('approved', 'rejected') THEN
        SELECT created_by, status INTO v_created_by, v_current_status
        FROM public.settlement_batches
        WHERE id = NEW.settlement_batch_id;

        IF v_created_by IS NOT NULL AND v_created_by = NEW.actor_id THEN
            RAISE EXCEPTION 'Maker-checker violation: User % created batch % and cannot approve or reject it.', NEW.actor_id, NEW.settlement_batch_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_check_maker_checker ON public.settlement_batch_approvals;
CREATE TRIGGER trg_check_maker_checker
    BEFORE INSERT ON public.settlement_batch_approvals
    FOR EACH ROW EXECUTE FUNCTION public.check_maker_checker_approval();

-- 5. Financial Immutability Trigger on mechanic_payout_ledger
-- Once a batch is approved, submitted, processing, or completed, financial fields cannot be modified.
CREATE OR REPLACE FUNCTION public.lock_settled_payout_ledger()
RETURNS TRIGGER AS $$
DECLARE
    v_batch_status TEXT;
BEGIN
    IF OLD.settlement_batch_id IS NOT NULL THEN
        SELECT status INTO v_batch_status 
        FROM public.settlement_batches 
        WHERE id = OLD.settlement_batch_id;

        IF v_batch_status IN ('approved', 'submitted', 'processing', 'completed') THEN
            IF (OLD.net_amount IS DISTINCT FROM NEW.net_amount) OR
               (OLD.gross_amount IS DISTINCT FROM NEW.gross_amount) OR
               (OLD.commission_amount IS DISTINCT FROM NEW.commission_amount) OR
               (OLD.deduction_amount IS DISTINCT FROM NEW.deduction_amount) OR
               (OLD.settlement_batch_id IS DISTINCT FROM NEW.settlement_batch_id) THEN
                RAISE EXCEPTION 'Financial immutability violation: Payout ledger item % belongs to locked batch % with status %', 
                    OLD.id, OLD.settlement_batch_id, v_batch_status;
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_lock_settled_payout_ledger ON public.mechanic_payout_ledger;
CREATE TRIGGER trg_lock_settled_payout_ledger
    BEFORE UPDATE ON public.mechanic_payout_ledger
    FOR EACH ROW EXECUTE FUNCTION public.lock_settled_payout_ledger();

-- 6. Trigger for updated_at on policies
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_settlement_approval_policies_updated_at') THEN
        CREATE TRIGGER trg_settlement_approval_policies_updated_at
            BEFORE UPDATE ON public.settlement_approval_policies
            FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
    END IF;
END $$;

-- 7. Row Level Security (RLS)
ALTER TABLE public.settlement_approval_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settlement_batch_approvals ENABLE ROW LEVEL SECURITY;

-- Policies RLS
DROP POLICY IF EXISTS settlement_policies_select ON public.settlement_approval_policies;
CREATE POLICY settlement_policies_select ON public.settlement_approval_policies
    FOR SELECT TO authenticated
    USING (is_admin_or_support());

DROP POLICY IF EXISTS settlement_policies_admin ON public.settlement_approval_policies;
CREATE POLICY settlement_policies_admin ON public.settlement_approval_policies
    FOR ALL TO authenticated
    USING (is_admin())
    WITH CHECK (is_admin());

-- Batch Approvals RLS (Read-only for staff, immutable: no direct client UPDATE or DELETE)
DROP POLICY IF EXISTS settlement_approvals_select ON public.settlement_batch_approvals;
CREATE POLICY settlement_approvals_select ON public.settlement_batch_approvals
    FOR SELECT TO authenticated
    USING (is_admin_or_support());

DROP POLICY IF EXISTS settlement_approvals_insert ON public.settlement_batch_approvals;
CREATE POLICY settlement_approvals_insert ON public.settlement_batch_approvals
    FOR INSERT TO authenticated
    WITH CHECK (is_admin_or_support());
