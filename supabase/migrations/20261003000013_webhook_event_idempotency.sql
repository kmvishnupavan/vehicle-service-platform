-- Migration: 20261003000013_webhook_event_idempotency.sql
-- Description: Database-level webhook event idempotency via public.webhook_events
-- Phase 8.1B: vehicle-service-platform

CREATE TABLE IF NOT EXISTS public.webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL DEFAULT 'razorpay',
    event_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_webhook_events_provider_event
        UNIQUE (provider, event_id)
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_provider_event
ON public.webhook_events (provider, event_id);

-- Enable Row Level Security (defense-in-depth)
ALTER TABLE public.webhook_events ENABLE ROW LEVEL SECURITY;

-- Explicitly revoke normal table privileges from anon and authenticated users
REVOKE ALL ON TABLE public.webhook_events FROM PUBLIC, anon, authenticated;

-- Grant required table privileges to service_role (used by backend)
GRANT ALL ON TABLE public.webhook_events TO service_role;
