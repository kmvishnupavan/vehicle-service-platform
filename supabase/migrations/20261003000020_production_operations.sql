-- ============================================================================
-- Migration: 20261003000020_production_operations.sql
-- Description: Phase 9 Production Operations, Webhook Recovery & Reconciliation
-- Author: Vehicle Service Platform Engineering Team
-- ============================================================================

-- 1. Webhook Crash Recovery & Operational Metadata
ALTER TABLE public.webhook_events
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'processing',
    ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ DEFAULT now(),
    ADD COLUMN IF NOT EXISTS processing_attempts INT DEFAULT 1,
    ADD COLUMN IF NOT EXISTS last_error TEXT;

-- Update existing processed events so their status is 'processed'
UPDATE public.webhook_events
SET status = 'processed'
WHERE processed_at IS NOT NULL AND status IS NULL;

-- Index for identifying stuck/stale webhook reservations
CREATE INDEX IF NOT EXISTS idx_webhook_events_status_started
    ON public.webhook_events(status, processing_started_at);

-- 2. Financial & System Reconciliation Discrepancies Table
CREATE TABLE IF NOT EXISTS public.reconciliation_discrepancies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type VARCHAR(50) NOT NULL,
    entity_id UUID,
    provider_reference VARCHAR(100),
    discrepancy_type VARCHAR(100) NOT NULL,
    severity VARCHAR(20) NOT NULL DEFAULT 'medium' CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    internal_status VARCHAR(50),
    provider_status VARCHAR(50),
    details JSONB DEFAULT '{}'::jsonb,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acknowledged', 'resolved', 'ignored')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indices for reconciliation dashboard queries
CREATE INDEX IF NOT EXISTS idx_recon_entity ON public.reconciliation_discrepancies(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_recon_status_severity ON public.reconciliation_discrepancies(status, severity);
CREATE INDEX IF NOT EXISTS idx_recon_detected_at ON public.reconciliation_discrepancies(detected_at DESC);

-- Enable Row Level Security
ALTER TABLE public.reconciliation_discrepancies ENABLE ROW LEVEL SECURITY;

-- 3. RLS Policies for Reconciliation Table
-- Admins and Support staff have read access
DROP POLICY IF EXISTS "recon_admin_select" ON public.reconciliation_discrepancies;
CREATE POLICY "recon_admin_select" ON public.reconciliation_discrepancies
    FOR SELECT
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE id = auth.uid()
            AND role IN ('admin', 'support')
        )
    );

-- Admins can update discrepancy resolution status
DROP POLICY IF EXISTS "recon_admin_update" ON public.reconciliation_discrepancies;
CREATE POLICY "recon_admin_update" ON public.reconciliation_discrepancies
    FOR UPDATE
    TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.profiles
            WHERE id = auth.uid()
            AND role = 'admin'
        )
    );

-- Service role has full access (for automated background scanner)
DROP POLICY IF EXISTS "recon_service_role_all" ON public.reconciliation_discrepancies;
CREATE POLICY "recon_service_role_all" ON public.reconciliation_discrepancies
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Ensure public cannot execute or access
REVOKE ALL ON public.reconciliation_discrepancies FROM anon, public;
GRANT SELECT, UPDATE ON public.reconciliation_discrepancies TO authenticated;
GRANT ALL ON public.reconciliation_discrepancies TO service_role;
