-- Migration: 20261002000005_create_communication_support_and_audit_tables.sql
-- Description: Notifications, Chat Rooms, Chat Messages, Support Tickets, Support Messages, Maintenance Reminders, and Audit Logs

-- 27. Notifications
CREATE TABLE public.notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_read BOOLEAN NOT NULL DEFAULT false,
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 28. Chat Rooms (For Booking-specific customer/mechanic communication)
CREATE TABLE public.chat_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL UNIQUE REFERENCES public.bookings(id) ON DELETE CASCADE,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 29. Chat Messages
CREATE TABLE public.chat_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES public.chat_rooms(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'text' CHECK (message_type IN ('text', 'image', 'system', 'location')),
    attachment_path TEXT,
    is_read BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 30. Support Tickets
CREATE TABLE public.support_tickets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_number TEXT NOT NULL UNIQUE,
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE RESTRICT,
    booking_id UUID REFERENCES public.bookings(id) ON DELETE SET NULL,
    assigned_to UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    category TEXT NOT NULL CHECK (category IN ('booking', 'payment', 'service_quality', 'mechanic_behavior', 'dispute', 'general')),
    priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
    subject TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'in_progress', 'waiting_customer', 'resolved', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 31. Support Messages
CREATE TABLE public.support_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id UUID NOT NULL REFERENCES public.support_tickets(id) ON DELETE CASCADE,
    sender_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    attachment_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 32. Maintenance Reminders
CREATE TABLE public.maintenance_reminders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL REFERENCES public.vehicles(id) ON DELETE CASCADE,
    service_id UUID REFERENCES public.services(id) ON DELETE SET NULL,
    reminder_type TEXT NOT NULL CHECK (reminder_type IN ('periodic_service', 'oil_change', 'brake_check', 'battery_check', 'tyre_rotation', 'insurance', 'pollution', 'custom')),
    due_date DATE,
    due_odometer_km INTEGER CHECK (due_odometer_km IS NULL OR due_odometer_km > 0),
    message TEXT NOT NULL,
    is_completed BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 33. Audit Logs
CREATE TABLE public.audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID,
    old_data JSONB,
    new_data JSONB,
    ip_address TEXT,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Triggers for updated_at
CREATE TRIGGER trg_chat_rooms_updated_at
    BEFORE UPDATE ON public.chat_rooms
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_support_tickets_updated_at
    BEFORE UPDATE ON public.support_tickets
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_maintenance_reminders_updated_at
    BEFORE UPDATE ON public.maintenance_reminders
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Auto-create chat room when a mechanic accepts a booking assignment
CREATE OR REPLACE FUNCTION public.create_chat_room_on_assignment_accept()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    booking_customer_id UUID;
BEGIN
    IF NEW.assignment_status = 'accepted' AND (OLD.assignment_status IS DISTINCT FROM 'accepted') THEN
        SELECT customer_id INTO booking_customer_id
        FROM public.bookings
        WHERE id = NEW.booking_id;

        IF booking_customer_id IS NOT NULL THEN
            INSERT INTO public.chat_rooms (booking_id, customer_id, mechanic_id)
            VALUES (NEW.booking_id, booking_customer_id, NEW.mechanic_id)
            ON CONFLICT (booking_id) DO NOTHING;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_create_chat_room_on_assignment
    AFTER INSERT OR UPDATE OF assignment_status ON public.mechanic_assignments
    FOR EACH ROW EXECUTE FUNCTION public.create_chat_room_on_assignment_accept();
