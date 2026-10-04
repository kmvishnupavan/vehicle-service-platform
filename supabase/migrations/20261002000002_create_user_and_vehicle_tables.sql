-- Migration: 20261002000002_create_user_and_vehicle_tables.sql
-- Description: Core profile, vehicle catalog, customer vehicles, and addresses

-- 1. Profiles Table (Referencing auth.users)
CREATE TABLE public.profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    avatar_url TEXT,
    role TEXT NOT NULL DEFAULT 'customer' CHECK (role IN ('customer', 'mechanic', 'admin', 'support')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Helper functions for RLS that depend on profiles
CREATE OR REPLACE FUNCTION public.get_current_user_role()
RETURNS text
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT role FROM public.profiles WHERE id = auth.uid();
$$;

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role = 'admin' AND is_active = true
  );
$$;

CREATE OR REPLACE FUNCTION public.is_admin_or_support()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND role IN ('admin', 'support') AND is_active = true
  );
$$;

-- 2. Customer Profiles
CREATE TABLE public.customer_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 3. Mechanic Profiles
CREATE TABLE public.mechanic_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES public.profiles(id) ON DELETE CASCADE,
    business_name TEXT,
    experience_years INTEGER NOT NULL DEFAULT 0 CHECK (experience_years >= 0),
    bio TEXT,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending', 'under_review', 'verified', 'rejected', 'suspended')),
    is_available BOOLEAN NOT NULL DEFAULT false,
    service_radius_km NUMERIC(6, 2) NOT NULL DEFAULT 15.00 CHECK (service_radius_km > 0),
    current_latitude NUMERIC(10, 7) CHECK (current_latitude BETWEEN -90.0 AND 90.0),
    current_longitude NUMERIC(10, 7) CHECK (current_longitude BETWEEN -180.0 AND 180.0),
    current_location_updated_at TIMESTAMPTZ,
    average_rating NUMERIC(3, 2) NOT NULL DEFAULT 0.00 CHECK (average_rating >= 0.00 AND average_rating <= 5.00),
    total_completed_jobs INTEGER NOT NULL DEFAULT 0 CHECK (total_completed_jobs >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

CREATE OR REPLACE FUNCTION public.get_mechanic_id_for_user(user_uuid uuid)
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id FROM public.mechanic_profiles WHERE user_id = user_uuid;
$$;

-- 4. Mechanic Documents
CREATE TABLE public.mechanic_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mechanic_id UUID NOT NULL REFERENCES public.mechanic_profiles(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL CHECK (document_type IN ('identity', 'driving_license', 'mechanic_certificate', 'address_proof', 'other')),
    document_number TEXT,
    file_path TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'pending' CHECK (verification_status IN ('pending', 'under_review', 'verified', 'rejected')),
    rejection_reason TEXT,
    verified_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 5. Vehicle Types (Bike, Car)
CREATE TABLE public.vehicle_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE CHECK (name IN ('bike', 'car')),
    icon_url TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 6. Vehicle Brands
CREATE TABLE public.vehicle_brands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL UNIQUE,
    logo_url TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- 7. Vehicle Models
CREATE TABLE public.vehicle_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES public.vehicle_brands(id) ON DELETE CASCADE,
    vehicle_type_id UUID NOT NULL REFERENCES public.vehicle_types(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    year_start INTEGER,
    year_end INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_brand_type_model UNIQUE (brand_id, vehicle_type_id, name)
);

-- 8. Vehicles (Customer Vehicles)
CREATE TABLE public.vehicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    vehicle_type_id UUID NOT NULL REFERENCES public.vehicle_types(id) ON DELETE RESTRICT,
    brand_id UUID NOT NULL REFERENCES public.vehicle_brands(id) ON DELETE RESTRICT,
    model_id UUID NOT NULL REFERENCES public.vehicle_models(id) ON DELETE RESTRICT,
    registration_number TEXT NOT NULL,
    nickname TEXT,
    manufacture_year INTEGER CHECK (manufacture_year BETWEEN 1970 AND EXTRACT(YEAR FROM CURRENT_DATE) + 2),
    color TEXT,
    fuel_type TEXT CHECK (fuel_type IN ('petrol', 'diesel', 'electric', 'hybrid', 'cng', 'lpg', 'other')),
    odometer_km INTEGER CHECK (odometer_km >= 0),
    is_primary BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_customer_vehicle_reg UNIQUE (customer_id, registration_number)
);

-- 9. Addresses
CREATE TABLE public.addresses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id UUID NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
    label TEXT NOT NULL DEFAULT 'Home',
    address_line TEXT NOT NULL,
    area TEXT NOT NULL,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    latitude NUMERIC(10, 7) NOT NULL CHECK (latitude BETWEEN -90.0 AND 90.0),
    longitude NUMERIC(10, 7) NOT NULL CHECK (longitude BETWEEN -180.0 AND 180.0),
    landmark TEXT,
    is_default BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

-- Triggers for updated_at
CREATE TRIGGER trg_profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_customer_profiles_updated_at
    BEFORE UPDATE ON public.customer_profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_mechanic_profiles_updated_at
    BEFORE UPDATE ON public.mechanic_profiles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_mechanic_documents_updated_at
    BEFORE UPDATE ON public.mechanic_documents
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_vehicles_updated_at
    BEFORE UPDATE ON public.vehicles
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER trg_addresses_updated_at
    BEFORE UPDATE ON public.addresses
    FOR EACH ROW EXECUTE FUNCTION public.handle_updated_at();

-- Safe profile creation trigger on auth.users
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
SECURITY DEFINER
SET search_path = public
LANGUAGE plpgsql
AS $$
DECLARE
    assigned_role text;
BEGIN
    assigned_role := COALESCE(NEW.raw_user_meta_data->>'role', 'customer');
    IF assigned_role NOT IN ('customer', 'mechanic', 'admin', 'support') THEN
        assigned_role := 'customer';
    END IF;

    INSERT INTO public.profiles (id, full_name, phone, email, avatar_url, role)
    VALUES (
        NEW.id,
        COALESCE(NULLIF(NEW.raw_user_meta_data->>'full_name', ''), COALESCE(NEW.email, 'User')),
        NEW.raw_user_meta_data->>'phone',
        NEW.email,
        NEW.raw_user_meta_data->>'avatar_url',
        assigned_role
    )
    ON CONFLICT (id) DO UPDATE
    SET email = EXCLUDED.email,
        full_name = CASE WHEN public.profiles.full_name = '' THEN EXCLUDED.full_name ELSE public.profiles.full_name END;

    IF assigned_role = 'customer' THEN
        INSERT INTO public.customer_profiles (user_id)
        VALUES (NEW.id)
        ON CONFLICT (user_id) DO NOTHING;
    ELSIF assigned_role = 'mechanic' THEN
        INSERT INTO public.mechanic_profiles (user_id)
        VALUES (NEW.id)
        ON CONFLICT (user_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
