-- Migration: 20261002000008_storage_realtime_and_hardening.sql
-- Description: Supabase Storage configuration, Realtime publications, and function security hardening

-- ============================================================================
-- 1. Function Security Hardening (Search path & RPC Execution Privileges)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
  NEW.updated_at = clock_timestamp();
  RETURN NEW;
END;
$$;

-- Revoke RPC access for internal trigger functions so they cannot be executed via PostgREST
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.track_booking_status_change() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.sync_mechanic_stats_on_review() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.sync_mechanic_completed_jobs() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.create_chat_room_on_assignment_accept() FROM PUBLIC, anon, authenticated;

-- Revoke RPC execution from anon role for internal helper functions
REVOKE EXECUTE ON FUNCTION public.get_current_user_role() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.get_mechanic_id_for_user(uuid) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_admin() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.is_admin_or_support() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.find_nearby_mechanics(numeric, numeric, numeric) FROM PUBLIC, anon;

-- Grant execution to authenticated users for client-invokable functions
GRANT EXECUTE ON FUNCTION public.get_current_user_role() TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_mechanic_id_for_user(uuid) TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin() TO authenticated;
GRANT EXECUTE ON FUNCTION public.is_admin_or_support() TO authenticated;
GRANT EXECUTE ON FUNCTION public.find_nearby_mechanics(numeric, numeric, numeric) TO authenticated;

-- ============================================================================
-- 2. Storage Buckets Configuration
-- ============================================================================
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
    ('avatars', 'avatars', true, 5242880, ARRAY['image/jpeg', 'image/png', 'image/webp']),
    ('mechanic-documents', 'mechanic-documents', false, 10485760, ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf']),
    ('service-evidence', 'service-evidence', false, 15728640, ARRAY['image/jpeg', 'image/png', 'image/webp', 'video/mp4']),
    ('service-reports', 'service-reports', false, 10485760, ARRAY['application/pdf', 'image/jpeg', 'image/png']),
    ('chat-attachments', 'chat-attachments', false, 10485760, ARRAY['image/jpeg', 'image/png', 'image/webp', 'application/pdf'])
ON CONFLICT (id) DO UPDATE
SET public = EXCLUDED.public,
    file_size_limit = EXCLUDED.file_size_limit,
    allowed_mime_types = EXCLUDED.allowed_mime_types;

-- Storage RLS Policies
CREATE POLICY "avatars_public_select" ON storage.objects
    FOR SELECT TO public
    USING (bucket_id = 'avatars');

CREATE POLICY "avatars_user_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "avatars_user_update" ON storage.objects
    FOR UPDATE TO authenticated
    USING (bucket_id = 'avatars' AND (storage.foldername(name))[1] = auth.uid()::text);

CREATE POLICY "mechanic_docs_select" ON storage.objects
    FOR SELECT TO authenticated
    USING (
        bucket_id = 'mechanic-documents'
        AND (
            (storage.foldername(name))[1] = auth.uid()::text
            OR public.is_admin_or_support()
        )
    );

CREATE POLICY "mechanic_docs_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (
        bucket_id = 'mechanic-documents'
        AND (
            (storage.foldername(name))[1] = auth.uid()::text
            OR public.is_admin()
        )
    );

CREATE POLICY "service_evidence_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'service-evidence');

CREATE POLICY "service_evidence_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'service-evidence');

CREATE POLICY "service_reports_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'service-reports');

CREATE POLICY "service_reports_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'service-reports');

CREATE POLICY "chat_attachments_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'chat-attachments');

CREATE POLICY "chat_attachments_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'chat-attachments');

-- ============================================================================
-- 3. Supabase Realtime Publication
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE
    public.bookings,
    public.mechanic_locations,
    public.chat_messages,
    public.notifications,
    public.additional_work_requests;
