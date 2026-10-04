-- Migration: 20261002000010_add_covering_foreign_key_indexes.sql
-- Description: Cover all unindexed foreign keys identified by performance advisor

CREATE INDEX IF NOT EXISTS idx_additional_work_requests_mechanic_id ON public.additional_work_requests(mechanic_id);
CREATE INDEX IF NOT EXISTS idx_booking_items_service_id ON public.booking_items(service_id);
CREATE INDEX IF NOT EXISTS idx_booking_status_history_changed_by ON public.booking_status_history(changed_by);
CREATE INDEX IF NOT EXISTS idx_bookings_address_id ON public.bookings(address_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_sender_id ON public.chat_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_coupon_usage_booking_id ON public.coupon_usage(booking_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_reminders_service_id ON public.maintenance_reminders(service_id);
CREATE INDEX IF NOT EXISTS idx_mechanic_documents_verified_by ON public.mechanic_documents(verified_by);
CREATE INDEX IF NOT EXISTS idx_service_inspections_mechanic_id ON public.service_inspections(mechanic_id);
CREATE INDEX IF NOT EXISTS idx_service_pricing_vehicle_type_id ON public.service_pricing(vehicle_type_id);
CREATE INDEX IF NOT EXISTS idx_support_messages_sender_id ON public.support_messages(sender_id);
CREATE INDEX IF NOT EXISTS idx_support_tickets_booking_id ON public.support_tickets(booking_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_models_vehicle_type_id ON public.vehicle_models(vehicle_type_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_brand_id ON public.vehicles(brand_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_model_id ON public.vehicles(model_id);
CREATE INDEX IF NOT EXISTS idx_vehicles_vehicle_type_id ON public.vehicles(vehicle_type_id);
