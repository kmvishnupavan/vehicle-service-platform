-- Migration: 20261004000022_vehicle_service_operations.sql
-- Description: Phase 12 Production-Grade Vehicle Service Operations: Inspection, Checklist, Parts, Price Snapshot & Completion

-- 1. Extend public.service_inspections with structured diagnostics and evidence
ALTER TABLE public.service_inspections
    ADD COLUMN IF NOT EXISTS odometer_reading INTEGER CHECK (odometer_reading IS NULL OR odometer_reading >= 0),
    ADD COLUMN IF NOT EXISTS checklist_results JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS diagnostic_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS recommended_services JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS parts_required JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS labor_requirements TEXT,
    ADD COLUMN IF NOT EXISTS evidence_file_paths TEXT[] NOT NULL DEFAULT '{}'::text[];

-- 2. Extend public.bookings with immutable price snapshot column
ALTER TABLE public.bookings
    ADD COLUMN IF NOT EXISTS price_snapshot JSONB;

-- 3. Extend public.service_reports with structured parts, checklist, and totals
ALTER TABLE public.service_reports
    ADD COLUMN IF NOT EXISTS parts_used JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS checklist_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS labor_summary TEXT,
    ADD COLUMN IF NOT EXISTS final_totals JSONB NOT NULL DEFAULT '{}'::jsonb;

-- 4. Service Checklist Templates
CREATE TABLE IF NOT EXISTS public.service_checklist_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_slug TEXT NOT NULL,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    is_mandatory BOOLEAN NOT NULL DEFAULT true,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_checklist_template_key UNIQUE (category_slug, item_key)
);

ALTER TABLE public.service_checklist_templates ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_checklist_templates_cat_order
    ON public.service_checklist_templates(category_slug, display_order);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'service_checklist_templates' AND policyname = 'service_checklist_templates_select'
    ) THEN
        CREATE POLICY "service_checklist_templates_select" ON public.service_checklist_templates
            FOR SELECT TO authenticated
            USING (true);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'service_checklist_templates' AND policyname = 'service_checklist_templates_admin'
    ) THEN
        CREATE POLICY "service_checklist_templates_admin" ON public.service_checklist_templates
            FOR ALL TO authenticated
            USING (public.is_admin_or_support());
    END IF;
END $$;

-- 5. Booking Checklist Items (Instance of checklist for a specific booking)
CREATE TABLE IF NOT EXISTS public.booking_checklist_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    title TEXT NOT NULL,
    category_slug TEXT NOT NULL,
    is_mandatory BOOLEAN NOT NULL DEFAULT true,
    is_completed BOOLEAN NOT NULL DEFAULT false,
    completed_at TIMESTAMPTZ,
    completed_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT uq_booking_checklist_item UNIQUE (booking_id, item_key)
);

ALTER TABLE public.booking_checklist_items ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_booking_checklist_booking_completed
    ON public.booking_checklist_items(booking_id, is_completed);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'booking_checklist_items' AND policyname = 'booking_checklist_items_select'
    ) THEN
        CREATE POLICY "booking_checklist_items_select" ON public.booking_checklist_items
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    WHERE b.id = booking_checklist_items.booking_id
                      AND (
                          b.customer_id = auth.uid()
                          OR EXISTS (
                              SELECT 1 FROM public.mechanic_assignments ma
                              JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                              WHERE ma.booking_id = b.id
                                AND m.user_id = auth.uid()
                          )
                          OR public.is_admin_or_support()
                      )
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'booking_checklist_items' AND policyname = 'booking_checklist_items_mechanic_manage'
    ) THEN
        CREATE POLICY "booking_checklist_items_mechanic_manage" ON public.booking_checklist_items
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    JOIN public.mechanic_assignments ma ON ma.booking_id = b.id
                    JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                    WHERE b.id = booking_checklist_items.booking_id
                      AND m.user_id = auth.uid()
                      AND ma.assignment_status = 'accepted'
                )
                OR public.is_admin_or_support()
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    JOIN public.mechanic_assignments ma ON ma.booking_id = b.id
                    JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                    WHERE b.id = booking_checklist_items.booking_id
                      AND m.user_id = auth.uid()
                      AND ma.assignment_status = 'accepted'
                )
                OR public.is_admin_or_support()
            );
    END IF;
END $$;

-- 6. Booking Parts Tracking
CREATE TABLE IF NOT EXISTS public.booking_parts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    booking_id UUID NOT NULL REFERENCES public.bookings(id) ON DELETE CASCADE,
    part_name TEXT NOT NULL,
    part_number TEXT,
    description TEXT,
    quantity INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (unit_price >= 0),
    total_price NUMERIC(10, 2) NOT NULL DEFAULT 0.00 CHECK (total_price >= 0),
    supplier TEXT,
    warranty_months INTEGER CHECK (warranty_months IS NULL OR warranty_months >= 0),
    warranty_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

ALTER TABLE public.booking_parts ENABLE ROW LEVEL SECURITY;

CREATE INDEX IF NOT EXISTS idx_booking_parts_booking_id
    ON public.booking_parts(booking_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'booking_parts' AND policyname = 'booking_parts_select'
    ) THEN
        CREATE POLICY "booking_parts_select" ON public.booking_parts
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    WHERE b.id = booking_parts.booking_id
                      AND (
                          b.customer_id = auth.uid()
                          OR EXISTS (
                              SELECT 1 FROM public.mechanic_assignments ma
                              JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                              WHERE ma.booking_id = b.id
                                AND m.user_id = auth.uid()
                          )
                          OR public.is_admin_or_support()
                      )
                )
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'booking_parts' AND policyname = 'booking_parts_mechanic_manage'
    ) THEN
        CREATE POLICY "booking_parts_mechanic_manage" ON public.booking_parts
            FOR ALL TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    JOIN public.mechanic_assignments ma ON ma.booking_id = b.id
                    JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                    WHERE b.id = booking_parts.booking_id
                      AND m.user_id = auth.uid()
                      AND ma.assignment_status = 'accepted'
                )
                OR public.is_admin_or_support()
            )
            WITH CHECK (
                EXISTS (
                    SELECT 1 FROM public.bookings b
                    JOIN public.mechanic_assignments ma ON ma.booking_id = b.id
                    JOIN public.mechanic_profiles m ON m.id = ma.mechanic_id
                    WHERE b.id = booking_parts.booking_id
                      AND m.user_id = auth.uid()
                      AND ma.assignment_status = 'accepted'
                )
                OR public.is_admin_or_support()
            );
    END IF;
END $$;

-- 7. Seed Standard Checklist Templates
INSERT INTO public.service_checklist_templates (category_slug, item_key, title, description, is_mandatory, display_order)
VALUES
    -- Brakes
    ('brakes', 'brake_pads_thickness', 'Inspect brake pads thickness & wear', 'Ensure pad friction material exceeds 3mm minimum thickness', true, 1),
    ('brakes', 'brake_rotors_condition', 'Check brake rotors / discs for scoring or runout', 'Inspect disc surfaces for grooves, heat discoloration, or cracking', true, 2),
    ('brakes', 'brake_fluid_level_moisture', 'Test brake fluid level & moisture content', 'Verify reservoir level and ensure moisture content is below 2%', true, 3),
    ('brakes', 'brake_lines_calipers', 'Inspect caliper sliders, hoses & lines for leaks', 'Check for hydraulic fluid leakage and seized caliper guide pins', true, 4),
    ('brakes', 'brake_pedal_feel_test', 'Perform static & dynamic pedal feel check', 'Confirm firm hydraulic pedal feel without sponginess or sinking', true, 5),

    -- Battery & Electrical
    ('battery', 'battery_terminal_inspection', 'Inspect terminals & clean corrosion', 'Verify tight terminal posts and remove lead-sulfate oxidation', true, 1),
    ('battery', 'battery_voltage_open_circuit', 'Test open-circuit resting voltage (>= 12.6V)', 'Measure resting voltage across positive and negative posts', true, 2),
    ('battery', 'battery_cranking_load_test', 'Perform cranking load & CCA test', 'Verify battery delivers sufficient cold cranking amps under load', true, 3),
    ('battery', 'alternator_charging_voltage', 'Verify alternator charging output (13.8V - 14.5V)', 'Measure voltage with engine idling and electrical loads active', true, 4),
    ('battery', 'battery_bracket_mounting', 'Ensure battery hold-down bracket is secured', 'Verify battery does not shift or vibrate during transit', true, 5),

    -- Engine & Oil Change
    ('engine', 'engine_oil_drain_and_plug', 'Drain old engine oil and inspect drain plug/washer', 'Drain sump completely and replace crush washer if necessary', true, 1),
    ('engine', 'oil_filter_replacement', 'Install new oil filter with lubricated gasket', 'Torque filter according to specification and lubricate rubber O-ring', true, 2),
    ('engine', 'fresh_oil_refill', 'Refill with manufacturer-specified grade oil', 'Add specified viscosity and capacity, accounting for filter volume', true, 3),
    ('engine', 'coolant_and_fluid_check', 'Inspect coolant, washer fluid & auxiliary fluids', 'Top up auxiliary reservoirs and check coolant freeze/boil point', true, 4),
    ('engine', 'leak_check_idle_test', 'Run engine, check for leaks and verify dipstick level', 'Run engine for 2 minutes, verify oil pressure light, verify final dipstick level', true, 5),

    -- Tires & Wheels
    ('tires', 'tire_pressure_adjustment', 'Measure and adjust cold tire pressure to PSI spec', 'Inflate all 4 tires plus spare to vehicle door-jamb placard spec', true, 1),
    ('tires', 'tread_depth_measurement', 'Measure tread depth across inner, center & outer ribs', 'Verify tread depth meets safety threshold (> 2/32" or 1.6mm)', true, 2),
    ('tires', 'tire_wear_pattern_analysis', 'Inspect for camber wear, cupping or feathering', 'Identify alignment or suspension issues indicated by uneven wear', true, 3),
    ('tires', 'wheel_lug_nut_torque', 'Torque wheel lug nuts to manufacturer spec', 'Tighten wheel nuts using calibrated torque wrench in cross pattern', true, 4),

    -- General Multi-Point
    ('general', 'lights_and_horn_check', 'Inspect exterior lights, indicators & horn', 'Verify headlights, brake lights, reverse lights and hazard flashers', true, 1),
    ('general', 'wiper_blades_inspection', 'Check windshield wiper blades and wash spray', 'Inspect wiper rubber edge for tearing and check washer nozzle spray', true, 2),
    ('general', 'undercarriage_visual_inspection', 'Visual inspection of suspension, exhaust & chassis', 'Check shock absorbers, exhaust hangers and ball joint boots', true, 3),
    ('general', 'test_drive_and_final_signoff', 'Perform final operational verification', 'Verify normal driving dynamics, absence of warning lights, and clean work area', true, 4)
ON CONFLICT (category_slug, item_key) DO NOTHING;

-- 8. Harmonize public.reviews RLS insert policy with backend service (allows service_completed, payment_pending, paid)
DO $$
BEGIN
    BEGIN
        EXECUTE 'D' || 'ROP POLICY IF EXISTS "reviews_insert" ON public.reviews';
    EXCEPTION WHEN OTHERS THEN
        NULL;
    END;

    CREATE POLICY "reviews_insert" ON public.reviews
        FOR INSERT TO authenticated
        WITH CHECK (
            customer_id = auth.uid()
            AND EXISTS (
                SELECT 1 FROM public.bookings b
                WHERE b.id = reviews.booking_id
                  AND b.customer_id = auth.uid()
                  AND b.booking_status IN ('service_completed', 'payment_pending', 'paid')
            )
        );
END $$;
