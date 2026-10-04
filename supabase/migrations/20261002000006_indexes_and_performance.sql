-- Migration: 20261002000006_indexes_and_performance.sql
-- Description: Performance, composite, foreign-key, and PostGIS spatial indexes

-- 1. Profiles & Roles
CREATE INDEX idx_profiles_role ON public.profiles(role);
CREATE INDEX idx_profiles_email ON public.profiles(email);
CREATE INDEX idx_profiles_phone ON public.profiles(phone);

-- 2. Mechanic Profiles & Availability
CREATE INDEX idx_mechanic_profiles_availability ON public.mechanic_profiles(is_available, verification_status);
CREATE INDEX idx_mechanic_profiles_rating ON public.mechanic_profiles(average_rating DESC);
CREATE INDEX idx_mechanic_profiles_geo ON public.mechanic_profiles
    USING GIST ((extensions.ST_SetSRID(extensions.ST_MakePoint(current_longitude, current_latitude), 4326)::extensions.geography))
    WHERE current_latitude IS NOT NULL AND current_longitude IS NOT NULL;

-- 3. Mechanic Documents
CREATE INDEX idx_mechanic_documents_mechanic_id ON public.mechanic_documents(mechanic_id);
CREATE INDEX idx_mechanic_documents_status ON public.mechanic_documents(verification_status);

-- 4. Vehicle Catalog & Customer Vehicles
CREATE INDEX idx_vehicle_models_brand_type ON public.vehicle_models(brand_id, vehicle_type_id);
CREATE INDEX idx_vehicles_customer_id ON public.vehicles(customer_id);
CREATE INDEX idx_vehicles_reg_number ON public.vehicles(upper(registration_number));

-- 5. Addresses
CREATE INDEX idx_addresses_customer_id ON public.addresses(customer_id);
CREATE INDEX idx_addresses_default ON public.addresses(customer_id, is_default) WHERE is_default = true;
CREATE INDEX idx_addresses_geo ON public.addresses
    USING GIST ((extensions.ST_SetSRID(extensions.ST_MakePoint(longitude, latitude), 4326)::extensions.geography));

-- 6. Services & Pricing
CREATE INDEX idx_services_category_id ON public.services(category_id);
CREATE INDEX idx_services_active ON public.services(is_active, vehicle_type);
CREATE INDEX idx_service_pricing_lookup ON public.service_pricing(service_id, vehicle_type_id, is_active);

-- 7. Bookings (Common access patterns specified by user)
CREATE INDEX idx_bookings_customer_id ON public.bookings(customer_id);
CREATE INDEX idx_bookings_vehicle_id ON public.bookings(vehicle_id);
CREATE INDEX idx_bookings_booking_status ON public.bookings(booking_status);
CREATE INDEX idx_bookings_scheduled_at ON public.bookings(scheduled_at);
CREATE INDEX idx_bookings_number ON public.bookings(booking_number);
CREATE INDEX idx_bookings_geo ON public.bookings
    USING GIST ((extensions.ST_SetSRID(extensions.ST_MakePoint(requested_longitude, requested_latitude), 4326)::extensions.geography));

-- 8. Booking Items & Status History
CREATE INDEX idx_booking_items_booking_id ON public.booking_items(booking_id);
CREATE INDEX idx_booking_status_history_booking_id ON public.booking_status_history(booking_id, created_at DESC);

-- 9. Mechanic Matching & Location Updates
CREATE INDEX idx_mechanic_assignments_booking_id ON public.mechanic_assignments(booking_id);
CREATE INDEX idx_mechanic_assignments_mechanic_id ON public.mechanic_assignments(mechanic_id);
CREATE INDEX idx_mechanic_assignments_status ON public.mechanic_assignments(assignment_status);
CREATE INDEX idx_mechanic_locations_mechanic_recorded ON public.mechanic_locations(mechanic_id, recorded_at DESC);
CREATE INDEX idx_mechanic_locations_geo ON public.mechanic_locations
    USING GIST ((extensions.ST_SetSRID(extensions.ST_MakePoint(longitude, latitude), 4326)::extensions.geography));

-- 10. Inspections & Additional Work
CREATE INDEX idx_service_inspections_booking ON public.service_inspections(booking_id);
CREATE INDEX idx_additional_work_booking ON public.additional_work_requests(booking_id);
CREATE INDEX idx_additional_work_status ON public.additional_work_requests(status);

-- 11. Payments & Invoices
CREATE INDEX idx_payments_booking_id ON public.payments(booking_id);
CREATE INDEX idx_payments_customer_id ON public.payments(customer_id);
CREATE INDEX idx_payments_status ON public.payments(status);
CREATE INDEX idx_payment_transactions_payment_id ON public.payment_transactions(payment_id);
CREATE INDEX idx_invoices_booking_id ON public.invoices(booking_id);
CREATE INDEX idx_invoices_customer_id ON public.invoices(customer_id);

-- 12. Service Reports & Reviews
CREATE INDEX idx_service_reports_booking ON public.service_reports(booking_id);
CREATE INDEX idx_service_reports_mechanic ON public.service_reports(mechanic_id);
CREATE INDEX idx_reviews_mechanic_id ON public.reviews(mechanic_id);
CREATE INDEX idx_reviews_customer_id ON public.reviews(customer_id);

-- 13. Coupons & Usage
CREATE INDEX idx_coupons_code ON public.coupons(upper(code));
CREATE INDEX idx_coupon_usage_customer ON public.coupon_usage(customer_id, coupon_id);

-- 14. Notifications & Communication
CREATE INDEX idx_notifications_user_unread ON public.notifications(user_id, is_read) WHERE is_read = false;
CREATE INDEX idx_notifications_user_all ON public.notifications(user_id, created_at DESC);
CREATE INDEX idx_chat_rooms_booking_id ON public.chat_rooms(booking_id);
CREATE INDEX idx_chat_rooms_customer_id ON public.chat_rooms(customer_id);
CREATE INDEX idx_chat_rooms_mechanic_id ON public.chat_rooms(mechanic_id);
CREATE INDEX idx_chat_messages_room_created ON public.chat_messages(room_id, created_at ASC);

-- 15. Support Tickets & Messages
CREATE INDEX idx_support_tickets_customer_id ON public.support_tickets(customer_id);
CREATE INDEX idx_support_tickets_status ON public.support_tickets(status);
CREATE INDEX idx_support_tickets_assigned ON public.support_tickets(assigned_to);
CREATE INDEX idx_support_messages_ticket_id ON public.support_messages(ticket_id, created_at ASC);

-- 16. Maintenance Reminders & Audit Logs
CREATE INDEX idx_maintenance_reminders_vehicle_id ON public.maintenance_reminders(vehicle_id);
CREATE INDEX idx_maintenance_reminders_customer_pending ON public.maintenance_reminders(customer_id, is_completed, due_date) WHERE is_completed = false;
CREATE INDEX idx_audit_logs_entity ON public.audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_logs_actor ON public.audit_logs(actor_id, created_at DESC);

-- PostGIS Helper Function for Proximity Search
CREATE OR REPLACE FUNCTION public.find_nearby_mechanics(
    cust_lat NUMERIC,
    cust_lng NUMERIC,
    max_distance_km NUMERIC DEFAULT 20.0
)
RETURNS TABLE (
    mechanic_id UUID,
    user_id UUID,
    full_name TEXT,
    phone TEXT,
    avatar_url TEXT,
    business_name TEXT,
    experience_years INTEGER,
    average_rating NUMERIC,
    distance_km NUMERIC,
    service_radius_km NUMERIC
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, extensions
AS $$
    SELECT
        m.id AS mechanic_id,
        m.user_id,
        p.full_name,
        p.phone,
        p.avatar_url,
        m.business_name,
        m.experience_years,
        m.average_rating,
        ROUND((extensions.ST_Distance(
            extensions.ST_SetSRID(extensions.ST_MakePoint(m.current_longitude, m.current_latitude), 4326)::extensions.geography,
            extensions.ST_SetSRID(extensions.ST_MakePoint(cust_lng, cust_lat), 4326)::extensions.geography
        ) / 1000.0)::numeric, 2) AS distance_km,
        m.service_radius_km
    FROM public.mechanic_profiles m
    JOIN public.profiles p ON p.id = m.user_id
    WHERE m.is_available = true
      AND m.verification_status = 'verified'
      AND m.current_latitude IS NOT NULL
      AND m.current_longitude IS NOT NULL
      AND extensions.ST_DWithin(
          extensions.ST_SetSRID(extensions.ST_MakePoint(m.current_longitude, m.current_latitude), 4326)::extensions.geography,
          extensions.ST_SetSRID(extensions.ST_MakePoint(cust_lng, cust_lat), 4326)::extensions.geography,
          LEAST(m.service_radius_km, max_distance_km) * 1000.0
      )
    ORDER BY distance_km ASC;
$$;
