-- Migration: 20261003000014_harden_notifications_realtime_and_chat.sql
-- Description: Phase 8.2A security hardening for notifications, additional work, chat attachments storage, chat messages read receipts, and mechanic location privacy.

-- ============================================================================
-- 1. Notification Idempotency and Role-Based Insert/Update Hardening
-- ============================================================================

-- Add nullable event_id for idempotency tracking
ALTER TABLE public.notifications ADD COLUMN IF NOT EXISTS event_id TEXT;

-- Create partial unique index on (user_id, event_id) to prevent duplicate event delivery per recipient
CREATE UNIQUE INDEX IF NOT EXISTS idx_notifications_user_event
    ON public.notifications (user_id, event_id)
    WHERE (event_id IS NOT NULL);

-- Restrict direct client notification creation: only admin/support and backend service_role can insert
DROP POLICY IF EXISTS "notifications_insert" ON public.notifications;
CREATE POLICY "notifications_insert" ON public.notifications
    FOR INSERT TO authenticated
    WITH CHECK (public.is_admin_or_support());

-- Ensure clients can only update read status on their own notifications
DROP POLICY IF EXISTS "notifications_update" ON public.notifications;
CREATE POLICY "notifications_update" ON public.notifications
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

-- Trigger to prevent client mutation of notification message, type, title, event_id, or data
CREATE OR REPLACE FUNCTION public.guard_notifications_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (auth.role() = 'authenticated') AND NOT public.is_admin_or_support() THEN
        IF (NEW.user_id IS DISTINCT FROM OLD.user_id) OR
           (NEW.type IS DISTINCT FROM OLD.type) OR
           (NEW.title IS DISTINCT FROM OLD.title) OR
           (NEW.message IS DISTINCT FROM OLD.message) OR
           (NEW.data IS DISTINCT FROM OLD.data) OR
           (NEW.event_id IS DISTINCT FROM OLD.event_id) OR
           (NEW.created_at IS DISTINCT FROM OLD.created_at) THEN
            RAISE EXCEPTION 'Access denied: Only read status (is_read, read_at) can be updated on notifications.';
        END IF;
    END IF;

    -- Automatically manage read_at timestamp
    IF NEW.is_read = true AND OLD.is_read = false AND NEW.read_at IS NULL THEN
        NEW.read_at = clock_timestamp();
    ELSIF NEW.is_read = false THEN
        NEW.read_at = NULL;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_notifications_fields ON public.notifications;
CREATE TRIGGER trg_guard_notifications_fields
    BEFORE UPDATE ON public.notifications
    FOR EACH ROW EXECUTE FUNCTION public.guard_notifications_fields();


-- ============================================================================
-- 2. Additional Work Requests Security Hardening
-- ============================================================================

-- Disallow arbitrary direct updates by authenticated customers or mechanics;
-- mutations must occur through the authoritative backend service_role workflow.
DROP POLICY IF EXISTS "additional_work_requests_update" ON public.additional_work_requests;

CREATE POLICY "additional_work_requests_admin_update" ON public.additional_work_requests
    FOR UPDATE TO authenticated
    USING (public.is_admin_or_support())
    WITH CHECK (public.is_admin_or_support());

CREATE OR REPLACE FUNCTION public.guard_additional_work_requests()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (auth.role() = 'authenticated') AND NOT public.is_admin_or_support() THEN
        RAISE EXCEPTION 'Access denied: Additional work lifecycle transitions must be executed through the authorized backend service.';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_additional_work_requests ON public.additional_work_requests;
CREATE TRIGGER trg_guard_additional_work_requests
    BEFORE UPDATE ON public.additional_work_requests
    FOR EACH ROW EXECUTE FUNCTION public.guard_additional_work_requests();


-- ============================================================================
-- 3. Chat Read Receipts, Immutability & RPC
-- ============================================================================

-- Partial index for fast unread message counts
CREATE INDEX IF NOT EXISTS idx_chat_messages_unread
    ON public.chat_messages (room_id, is_read)
    WHERE (is_read = false);

-- RPC for secure chat message read-receipt marking
CREATE OR REPLACE FUNCTION public.mark_chat_message_read(p_message_id UUID)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_msg RECORD;
    v_room RECORD;
    v_user_id UUID := auth.uid();
    v_mechanic_profile_id UUID;
    v_is_participant BOOLEAN := false;
BEGIN
    IF v_user_id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'UNAUTHORIZED', 'message', 'Authentication required.');
    END IF;

    SELECT * INTO v_msg FROM public.chat_messages WHERE id = p_message_id;
    IF v_msg.id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'NOT_FOUND', 'message', 'Message not found.');
    END IF;

    -- Verify user is not the sender marking their own message
    IF v_msg.sender_id = v_user_id THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'FORBIDDEN', 'message', 'Sender cannot mark own message as read.');
    END IF;

    SELECT * INTO v_room FROM public.chat_rooms WHERE id = v_msg.room_id;
    IF v_room.id IS NULL THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'NOT_FOUND', 'message', 'Chat room not found.');
    END IF;

    SELECT id INTO v_mechanic_profile_id FROM public.mechanic_profiles WHERE user_id = v_user_id;

    IF v_room.customer_id = v_user_id OR (v_mechanic_profile_id IS NOT NULL AND v_room.mechanic_id = v_mechanic_profile_id) OR public.is_admin_or_support() THEN
        v_is_participant := true;
    END IF;

    IF NOT v_is_participant THEN
        RETURN jsonb_build_object('success', false, 'error_code', 'FORBIDDEN', 'message', 'User is not a participant in this chat room.');
    END IF;

    UPDATE public.chat_messages
    SET is_read = true
    WHERE id = p_message_id;

    RETURN jsonb_build_object('success', true, 'message_id', p_message_id, 'is_read', true);
END;
$$;

REVOKE EXECUTE ON FUNCTION public.mark_chat_message_read(UUID) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.mark_chat_message_read(UUID) TO authenticated;

-- RLS policy allowing recipients to update is_read
DROP POLICY IF EXISTS "chat_messages_update_read" ON public.chat_messages;
CREATE POLICY "chat_messages_update_read" ON public.chat_messages
    FOR UPDATE TO authenticated
    USING (
        sender_id <> auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.chat_rooms cr
            WHERE cr.id = chat_messages.room_id
              AND (
                  cr.customer_id = auth.uid()
                  OR cr.mechanic_id = public.get_mechanic_id_for_user(auth.uid())
                  OR public.is_admin_or_support()
              )
        )
    )
    WITH CHECK (
        sender_id <> auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.chat_rooms cr
            WHERE cr.id = chat_messages.room_id
              AND (
                  cr.customer_id = auth.uid()
                  OR cr.mechanic_id = public.get_mechanic_id_for_user(auth.uid())
                  OR public.is_admin_or_support()
              )
        )
    );

-- Strict trigger ensuring chat message content and metadata can never be modified
CREATE OR REPLACE FUNCTION public.guard_chat_messages_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (auth.role() = 'authenticated') AND NOT public.is_admin_or_support() THEN
        IF (NEW.message IS DISTINCT FROM OLD.message) OR
           (NEW.sender_id IS DISTINCT FROM OLD.sender_id) OR
           (NEW.room_id IS DISTINCT FROM OLD.room_id) OR
           (NEW.message_type IS DISTINCT FROM OLD.message_type) OR
           (NEW.attachment_path IS DISTINCT FROM OLD.attachment_path) OR
           (NEW.created_at IS DISTINCT FROM OLD.created_at) THEN
            RAISE EXCEPTION 'Access denied: Chat message content and metadata are strictly immutable.';
        END IF;

        IF (OLD.sender_id = auth.uid()) THEN
            RAISE EXCEPTION 'Access denied: Sender cannot update message read status.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_chat_messages_immutable ON public.chat_messages;
CREATE TRIGGER trg_guard_chat_messages_immutable
    BEFORE UPDATE ON public.chat_messages
    FOR EACH ROW EXECUTE FUNCTION public.guard_chat_messages_immutable();


-- ============================================================================
-- 4. Chat Rooms Immutability Guard
-- ============================================================================

CREATE OR REPLACE FUNCTION public.guard_chat_rooms_immutable()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF (auth.role() = 'authenticated') AND NOT public.is_admin_or_support() THEN
        IF (NEW.booking_id IS DISTINCT FROM OLD.booking_id) OR
           (NEW.customer_id IS DISTINCT FROM OLD.customer_id) OR
           (NEW.mechanic_id IS DISTINCT FROM OLD.mechanic_id) OR
           (NEW.created_at IS DISTINCT FROM OLD.created_at) THEN
            RAISE EXCEPTION 'Access denied: Core chat room participants and booking links are immutable.';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_guard_chat_rooms_immutable ON public.chat_rooms;
CREATE TRIGGER trg_guard_chat_rooms_immutable
    BEFORE UPDATE ON public.chat_rooms
    FOR EACH ROW EXECUTE FUNCTION public.guard_chat_rooms_immutable();


-- ============================================================================
-- 5. Chat Attachments Storage Security (Participant-Scoped)
-- ============================================================================

CREATE OR REPLACE FUNCTION public.can_access_chat_attachment(file_path text)
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
    IF public.is_admin_or_support() THEN
        RETURN true;
    END IF;

    booking_str := split_part(file_path, '/', 1);
    BEGIN
        booking_uuid := booking_str::uuid;
    EXCEPTION WHEN others THEN
        RETURN false;
    END;

    RETURN EXISTS (
        SELECT 1 FROM public.bookings b
        WHERE b.id = booking_uuid
          AND (
              b.customer_id = (SELECT auth.uid())
              OR EXISTS (
                  SELECT 1 FROM public.mechanic_assignments ma
                  JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                  WHERE ma.booking_id = b.id
                    AND ma.assignment_status = 'accepted'
                    AND m.user_id = (SELECT auth.uid())
              )
          )
    );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.can_access_chat_attachment(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.can_access_chat_attachment(text) TO authenticated;

DROP POLICY IF EXISTS "chat_attachments_access" ON storage.objects;
DROP POLICY IF EXISTS "chat_attachments_upload" ON storage.objects;

CREATE POLICY "chat_attachments_access" ON storage.objects
    FOR SELECT TO authenticated
    USING (bucket_id = 'chat-attachments' AND public.can_access_chat_attachment(name));

CREATE POLICY "chat_attachments_upload" ON storage.objects
    FOR INSERT TO authenticated
    WITH CHECK (bucket_id = 'chat-attachments' AND public.can_access_chat_attachment(name));


-- ============================================================================
-- 6. Mechanic Location Historical Privacy Fix
-- ============================================================================

DROP POLICY IF EXISTS "mechanic_locations_select" ON public.mechanic_locations;

CREATE POLICY "mechanic_locations_select" ON public.mechanic_locations
    FOR SELECT TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.mechanic_assignments ma
            JOIN public.bookings b ON b.id = ma.booking_id
            WHERE ma.mechanic_id = mechanic_locations.mechanic_id
              AND b.customer_id = auth.uid()
              AND ma.assignment_status = 'accepted'
              AND b.booking_status IN ('mechanic_en_route', 'mechanic_arrived', 'service_in_progress', 'additional_work')
              AND mechanic_locations.recorded_at >= COALESCE(ma.assigned_at, ma.offered_at)
        )
    );
