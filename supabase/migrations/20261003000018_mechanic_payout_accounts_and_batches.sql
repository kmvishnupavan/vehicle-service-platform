-- Migration: 20261003000018_mechanic_payout_accounts_and_batches.sql
-- Description: Mechanic Payout Accounts, Settlement Batches, and Payout Ledger Associations (Phase 8.8)

-- 1. Create mechanic_payout_accounts table
CREATE TABLE IF NOT EXISTS public.mechanic_payout_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'razorpayx',
    provider_contact_id TEXT NULL,
    provider_fund_account_id TEXT NULL,
    account_holder_name TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'bank_account' CHECK (account_type IN ('bank_account', 'vpa')),
    masked_account_number TEXT NOT NULL,
    account_number_hash TEXT NULL,
    ifsc_code TEXT NULL CHECK (ifsc_code IS NULL OR ifsc_code ~ '^[A-Z]{4}0[A-Z0-9]{6}$'),
    bank_name TEXT NULL,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('not_configured', 'pending', 'submitted', 'verified', 'failed', 'suspended')),
    verification_error TEXT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT true,
    is_active BOOLEAN NOT NULL DEFAULT true,
    verified_at TIMESTAMPTZ NULL,
    last_verified_at TIMESTAMPTZ NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. Create settlement_batches table
CREATE TABLE IF NOT EXISTS public.settlement_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_number TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL DEFAULT 'razorpayx',
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'submitted', 'processing', 'completed', 'failed', 'cancelled')),
    total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00 CHECK (total_amount >= 0),
    currency TEXT NOT NULL DEFAULT 'INR',
    item_count INTEGER NOT NULL DEFAULT 0 CHECK (item_count >= 0),
    provider_batch_id TEXT NULL,
    error_details JSONB NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by UUID NULL REFERENCES auth.users(id),
    submitted_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 3. Extend mechanic_payout_ledger with batch and account foreign keys
ALTER TABLE public.mechanic_payout_ledger 
    ADD COLUMN IF NOT EXISTS settlement_batch_id UUID NULL REFERENCES public.settlement_batches(id) ON DELETE SET NULL;

ALTER TABLE public.mechanic_payout_ledger 
    ADD COLUMN IF NOT EXISTS payout_account_id UUID NULL REFERENCES public.mechanic_payout_accounts(id) ON DELETE SET NULL;

-- 4. Create Indexes
CREATE INDEX IF NOT EXISTS idx_payout_accounts_mechanic_id ON public.mechanic_payout_accounts (mechanic_id);
CREATE INDEX IF NOT EXISTS idx_payout_accounts_status ON public.mechanic_payout_accounts (verification_status);
CREATE INDEX IF NOT EXISTS idx_payout_accounts_provider_fa ON public.mechanic_payout_accounts (provider_fund_account_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_uq_mechanic_primary_active_account ON public.mechanic_payout_accounts (mechanic_id) WHERE is_active = true AND is_primary = true;

CREATE INDEX IF NOT EXISTS idx_settlement_batches_status ON public.settlement_batches (status);
CREATE INDEX IF NOT EXISTS idx_settlement_batches_created_at ON public.settlement_batches (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payout_ledger_batch_id ON public.mechanic_payout_ledger (settlement_batch_id);
CREATE INDEX IF NOT EXISTS idx_payout_ledger_account_id ON public.mechanic_payout_ledger (payout_account_id);

-- 5. Attach updated_at triggers
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_mechanic_payout_accounts_updated_at') THEN
        CREATE TRIGGER trg_mechanic_payout_accounts_updated_at
            BEFORE UPDATE ON public.mechanic_payout_accounts
            FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_settlement_batches_updated_at') THEN
        CREATE TRIGGER trg_settlement_batches_updated_at
            BEFORE UPDATE ON public.settlement_batches
            FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();
    END IF;
END $$;

-- 6. Row Level Security (RLS)
ALTER TABLE public.mechanic_payout_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.settlement_batches ENABLE ROW LEVEL SECURITY;

-- Payout Accounts RLS Policies
CREATE POLICY payout_accounts_select ON public.mechanic_payout_accounts
    FOR SELECT TO authenticated
    USING (
        (mechanic_id = get_mechanic_id_for_user(auth.uid()))
        OR is_admin_or_support()
    );

CREATE POLICY payout_accounts_insert ON public.mechanic_payout_accounts
    FOR INSERT TO authenticated
    WITH CHECK (
        (
            mechanic_id = get_mechanic_id_for_user(auth.uid())
            AND verification_status IN ('not_configured', 'pending', 'submitted')
        )
        OR is_admin_or_support()
    );

CREATE POLICY payout_accounts_update ON public.mechanic_payout_accounts
    FOR UPDATE TO authenticated
    USING (
        (
            mechanic_id = get_mechanic_id_for_user(auth.uid())
            AND verification_status IN ('not_configured', 'pending', 'submitted')
        )
        OR is_admin_or_support()
    );

CREATE POLICY payout_accounts_delete ON public.mechanic_payout_accounts
    FOR DELETE TO authenticated
    USING (is_admin());

-- Settlement Batches RLS Policies
CREATE POLICY settlement_batches_select ON public.settlement_batches
    FOR SELECT TO authenticated
    USING (
        is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.mechanic_payout_ledger mpl
            WHERE mpl.settlement_batch_id = settlement_batches.id
            AND mpl.mechanic_id = get_mechanic_id_for_user(auth.uid())
        )
    );

CREATE POLICY settlement_batches_admin_all ON public.settlement_batches
    FOR ALL TO authenticated
    USING (is_admin_or_support())
    WITH CHECK (is_admin_or_support());
