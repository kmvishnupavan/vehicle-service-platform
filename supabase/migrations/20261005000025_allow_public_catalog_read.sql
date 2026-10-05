-- Migration: 20261005000025_allow_public_catalog_read.sql
-- Description: Allow public (anon and authenticated) read access to vehicle and service catalogs as intended

ALTER POLICY "service_categories_read" ON public.service_categories TO anon, authenticated;
ALTER POLICY "services_read" ON public.services TO anon, authenticated;
ALTER POLICY "service_pricing_read" ON public.service_pricing TO anon, authenticated;
ALTER POLICY "vehicle_types_read" ON public.vehicle_types TO anon, authenticated;
ALTER POLICY "vehicle_brands_read" ON public.vehicle_brands TO anon, authenticated;
ALTER POLICY "vehicle_models_read" ON public.vehicle_models TO anon, authenticated;
