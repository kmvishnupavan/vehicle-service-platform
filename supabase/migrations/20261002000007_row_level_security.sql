-- Migration: 20261002000007_row_level_security.sql
-- Description: Enable Row Level Security and configure least-privilege policies on all 33 tables

-- ============================================================================
-- 1. Enable Row Level Security on ALL Application Tables
-- ============================================================================
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.customer_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mechanic_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mechanic_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicle_types ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicle_brands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicle_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.addresses ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.services ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_pricing ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.bookings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.booking_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.booking_status_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mechanic_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mechanic_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_inspections ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.additional_work_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.invoices ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.service_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupons ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coupon_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_rooms ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.support_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.maintenance_reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 2. Profiles Policies
-- ============================================================================
CREATE POLICY "profiles_select_policy" ON public.profiles
    FOR SELECT TO authenticated
    USING (id = auth.uid() OR public.is_admin_or_support() OR role = 'mechanic');

CREATE POLICY "profiles_update_own" ON public.profiles
    FOR UPDATE TO authenticated
    USING (id = auth.uid() OR public.is_admin())
    WITH CHECK (id = auth.uid() OR public.is_admin());

CREATE POLICY "profiles_insert_policy" ON public.profiles
    FOR INSERT TO authenticated
    WITH CHECK (id = auth.uid() OR public.is_admin());

-- ============================================================================
-- 3. Customer Profiles Policies
-- ============================================================================
CREATE POLICY "customer_profiles_select" ON public.customer_profiles
    FOR SELECT TO authenticated
    USING (user_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "customer_profiles_insert" ON public.customer_profiles
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "customer_profiles_update" ON public.customer_profiles
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================================
-- 4. Mechanic Profiles Policies
-- ============================================================================
CREATE POLICY "mechanic_profiles_select" ON public.mechanic_profiles
    FOR SELECT TO authenticated
    USING (verification_status = 'verified' OR user_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "mechanic_profiles_insert" ON public.mechanic_profiles
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid() OR public.is_admin());

CREATE POLICY "mechanic_profiles_update" ON public.mechanic_profiles
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid() OR public.is_admin())
    WITH CHECK (user_id = auth.uid() OR public.is_admin());

-- ============================================================================
-- 5. Mechanic Documents Policies
-- ============================================================================
CREATE POLICY "mechanic_documents_select" ON public.mechanic_documents
    FOR SELECT TO authenticated
    USING (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

CREATE POLICY "mechanic_documents_insert" ON public.mechanic_documents
    FOR INSERT TO authenticated
    WITH CHECK (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin());

CREATE POLICY "mechanic_documents_update" ON public.mechanic_documents
    FOR UPDATE TO authenticated
    USING (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

-- ============================================================================
-- 6. Vehicle Catalog (Types, Brands, Models) - Public Read, Admin Write
-- ============================================================================
CREATE POLICY "vehicle_types_read" ON public.vehicle_types FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "vehicle_types_admin" ON public.vehicle_types FOR ALL TO authenticated USING (public.is_admin());

CREATE POLICY "vehicle_brands_read" ON public.vehicle_brands FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "vehicle_brands_admin" ON public.vehicle_brands FOR ALL TO authenticated USING (public.is_admin());

CREATE POLICY "vehicle_models_read" ON public.vehicle_models FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "vehicle_models_admin" ON public.vehicle_models FOR ALL TO authenticated USING (public.is_admin());

-- ============================================================================
-- 7. Vehicles & Addresses Policies (Customer Ownership)
-- ============================================================================
CREATE POLICY "vehicles_select" ON public.vehicles
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "vehicles_insert" ON public.vehicles
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "vehicles_update" ON public.vehicles
    FOR UPDATE TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin())
    WITH CHECK (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "vehicles_delete" ON public.vehicles
    FOR DELETE TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "addresses_select" ON public.addresses
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "addresses_insert" ON public.addresses
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "addresses_update" ON public.addresses
    FOR UPDATE TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin())
    WITH CHECK (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "addresses_delete" ON public.addresses
    FOR DELETE TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin());

-- ============================================================================
-- 8. Service Catalog & Pricing - Public Read, Admin Write
-- ============================================================================
CREATE POLICY "service_categories_read" ON public.service_categories FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "service_categories_admin" ON public.service_categories FOR ALL TO authenticated USING (public.is_admin());

CREATE POLICY "services_read" ON public.services FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "services_admin" ON public.services FOR ALL TO authenticated USING (public.is_admin());

CREATE POLICY "service_pricing_read" ON public.service_pricing FOR SELECT TO authenticated USING (is_active = true OR public.is_admin_or_support());
CREATE POLICY "service_pricing_admin" ON public.service_pricing FOR ALL TO authenticated USING (public.is_admin());

-- ============================================================================
-- 9. Bookings & Booking Items
-- ============================================================================
CREATE POLICY "bookings_select" ON public.bookings
    FOR SELECT TO authenticated
    USING (
        customer_id = auth.uid()
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.mechanic_assignments
            WHERE booking_id = bookings.id
              AND mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        )
    );

CREATE POLICY "bookings_insert" ON public.bookings
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "bookings_update" ON public.bookings
    FOR UPDATE TO authenticated
    USING (
        customer_id = auth.uid()
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.mechanic_assignments
            WHERE booking_id = bookings.id
              AND mechanic_id = public.get_mechanic_id_for_user(auth.uid())
              AND assignment_status = 'accepted'
        )
    );

CREATE POLICY "booking_items_select" ON public.booking_items
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = booking_items.booking_id
              AND (
                  b.customer_id = auth.uid()
                  OR public.is_admin_or_support()
                  OR EXISTS (
                      SELECT 1 FROM public.mechanic_assignments ma
                      WHERE ma.booking_id = b.id
                        AND ma.mechanic_id = public.get_mechanic_id_for_user(auth.uid())
                  )
              )
        )
    );

CREATE POLICY "booking_items_insert" ON public.booking_items
    FOR INSERT TO authenticated
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = booking_items.booking_id
              AND (b.customer_id = auth.uid() OR public.is_admin_or_support())
        )
    );

CREATE POLICY "booking_items_admin" ON public.booking_items
    FOR ALL TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY "booking_status_history_select" ON public.booking_status_history
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = booking_status_history.booking_id
              AND (
                  b.customer_id = auth.uid()
                  OR public.is_admin_or_support()
                  OR EXISTS (
                      SELECT 1 FROM public.mechanic_assignments ma
                      WHERE ma.booking_id = b.id
                        AND ma.mechanic_id = public.get_mechanic_id_for_user(auth.uid())
                  )
              )
        )
    );

CREATE POLICY "booking_status_history_insert" ON public.booking_status_history
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() IS NOT NULL);

-- ============================================================================
-- 10. Mechanic Assignments & Locations
-- ============================================================================
CREATE POLICY "mechanic_assignments_select" ON public.mechanic_assignments
    FOR SELECT TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = mechanic_assignments.booking_id AND b.customer_id = auth.uid()
        )
    );

CREATE POLICY "mechanic_assignments_update" ON public.mechanic_assignments
    FOR UPDATE TO authenticated
    USING (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

CREATE POLICY "mechanic_assignments_admin_insert" ON public.mechanic_assignments
    FOR INSERT TO authenticated
    WITH CHECK (public.is_admin_or_support());

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
        )
    );

CREATE POLICY "mechanic_locations_insert" ON public.mechanic_locations
    FOR INSERT TO authenticated
    WITH CHECK (mechanic_id = public.get_mechanic_id_for_user(auth.uid()));

-- ============================================================================
-- 11. Service Inspections & Additional Work Requests
-- ============================================================================
CREATE POLICY "service_inspections_select" ON public.service_inspections
    FOR SELECT TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = service_inspections.booking_id AND b.customer_id = auth.uid()
        )
    );

CREATE POLICY "service_inspections_manage" ON public.service_inspections
    FOR ALL TO authenticated
    USING (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

CREATE POLICY "additional_work_requests_select" ON public.additional_work_requests
    FOR SELECT TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = additional_work_requests.booking_id AND b.customer_id = auth.uid()
        )
    );

CREATE POLICY "additional_work_requests_insert" ON public.additional_work_requests
    FOR INSERT TO authenticated
    WITH CHECK (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

CREATE POLICY "additional_work_requests_update" ON public.additional_work_requests
    FOR UPDATE TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = additional_work_requests.booking_id AND b.customer_id = auth.uid()
        )
    );

-- ============================================================================
-- 12. Payments, Transactions & Invoices
-- ============================================================================
CREATE POLICY "payments_select" ON public.payments
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "payments_insert" ON public.payments
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "payments_admin" ON public.payments
    FOR UPDATE TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY "payment_transactions_select" ON public.payment_transactions
    FOR SELECT TO authenticated
    USING (
        public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.payments p
            WHERE p.id = payment_transactions.payment_id AND p.customer_id = auth.uid()
        )
    );

CREATE POLICY "payment_transactions_admin" ON public.payment_transactions
    FOR INSERT TO authenticated
    WITH CHECK (public.is_admin_or_support());

CREATE POLICY "invoices_select" ON public.invoices
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "invoices_admin" ON public.invoices
    FOR ALL TO authenticated
    USING (public.is_admin_or_support());

-- ============================================================================
-- 13. Service Reports & Reviews
-- ============================================================================
CREATE POLICY "service_reports_select" ON public.service_reports
    FOR SELECT TO authenticated
    USING (
        mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
        OR EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = service_reports.booking_id AND b.customer_id = auth.uid()
        )
    );

CREATE POLICY "service_reports_manage" ON public.service_reports
    FOR ALL TO authenticated
    USING (mechanic_id = public.get_mechanic_id_for_user(auth.uid()) OR public.is_admin_or_support());

CREATE POLICY "reviews_select" ON public.reviews
    FOR SELECT TO authenticated
    USING (true);

CREATE POLICY "reviews_insert" ON public.reviews
    FOR INSERT TO authenticated
    WITH CHECK (
        customer_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.bookings b
            WHERE b.id = reviews.booking_id
              AND b.customer_id = auth.uid()
              AND b.booking_status IN ('service_completed', 'paid')
        )
    );

CREATE POLICY "reviews_update" ON public.reviews
    FOR UPDATE TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin());

CREATE POLICY "reviews_delete" ON public.reviews
    FOR DELETE TO authenticated
    USING (public.is_admin());

-- ============================================================================
-- 14. Coupons & Usage
-- ============================================================================
CREATE POLICY "coupons_select" ON public.coupons
    FOR SELECT TO authenticated
    USING (is_active = true OR public.is_admin_or_support());

CREATE POLICY "coupons_admin" ON public.coupons
    FOR ALL TO authenticated
    USING (public.is_admin());

CREATE POLICY "coupon_usage_select" ON public.coupon_usage
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "coupon_usage_insert" ON public.coupon_usage
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin_or_support());

-- ============================================================================
-- 15. Notifications
-- ============================================================================
CREATE POLICY "notifications_select" ON public.notifications
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "notifications_update" ON public.notifications
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "notifications_insert" ON public.notifications
    FOR INSERT TO authenticated
    WITH CHECK (user_id = auth.uid() OR public.is_admin_or_support());

-- ============================================================================
-- 16. Chat Rooms & Messages
-- ============================================================================
CREATE POLICY "chat_rooms_select" ON public.chat_rooms
    FOR SELECT TO authenticated
    USING (
        customer_id = auth.uid()
        OR mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
    );

CREATE POLICY "chat_rooms_update" ON public.chat_rooms
    FOR UPDATE TO authenticated
    USING (
        customer_id = auth.uid()
        OR mechanic_id = public.get_mechanic_id_for_user(auth.uid())
        OR public.is_admin_or_support()
    );

CREATE POLICY "chat_messages_select" ON public.chat_messages
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.chat_rooms cr
            WHERE cr.id = chat_messages.room_id
              AND (
                  cr.customer_id = auth.uid()
                  OR cr.mechanic_id = public.get_mechanic_id_for_user(auth.uid())
                  OR public.is_admin_or_support()
              )
        )
    );

CREATE POLICY "chat_messages_insert" ON public.chat_messages
    FOR INSERT TO authenticated
    WITH CHECK (
        sender_id = auth.uid()
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

-- ============================================================================
-- 17. Support Tickets & Messages
-- ============================================================================
CREATE POLICY "support_tickets_select" ON public.support_tickets
    FOR SELECT TO authenticated
    USING (
        customer_id = auth.uid()
        OR assigned_to = auth.uid()
        OR public.is_admin_or_support()
    );

CREATE POLICY "support_tickets_insert" ON public.support_tickets
    FOR INSERT TO authenticated
    WITH CHECK (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "support_tickets_update" ON public.support_tickets
    FOR UPDATE TO authenticated
    USING (
        customer_id = auth.uid()
        OR assigned_to = auth.uid()
        OR public.is_admin_or_support()
    );

CREATE POLICY "support_messages_select" ON public.support_messages
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM public.support_tickets st
            WHERE st.id = support_messages.ticket_id
              AND (
                  st.customer_id = auth.uid()
                  OR st.assigned_to = auth.uid()
                  OR public.is_admin_or_support()
              )
        )
    );

CREATE POLICY "support_messages_insert" ON public.support_messages
    FOR INSERT TO authenticated
    WITH CHECK (
        sender_id = auth.uid()
        AND EXISTS (
            SELECT 1 FROM public.support_tickets st
            WHERE st.id = support_messages.ticket_id
              AND (
                  st.customer_id = auth.uid()
                  OR st.assigned_to = auth.uid()
                  OR public.is_admin_or_support()
              )
        )
    );

-- ============================================================================
-- 18. Maintenance Reminders & Audit Logs
-- ============================================================================
CREATE POLICY "maintenance_reminders_select" ON public.maintenance_reminders
    FOR SELECT TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "maintenance_reminders_manage" ON public.maintenance_reminders
    FOR ALL TO authenticated
    USING (customer_id = auth.uid() OR public.is_admin_or_support());

CREATE POLICY "audit_logs_select" ON public.audit_logs
    FOR SELECT TO authenticated
    USING (public.is_admin_or_support());

CREATE POLICY "audit_logs_insert" ON public.audit_logs
    FOR INSERT TO authenticated
    WITH CHECK (auth.uid() IS NOT NULL);
