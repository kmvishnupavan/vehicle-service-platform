-- Migration: 20261005000024_seed_catalog_data.sql
-- Description: Seed vehicle catalog, models, service categories, services, and authoritative pricing

DO $$
DECLARE
    v_bike_type_id UUID;
    v_car_type_id UUID;

    -- Brands
    v_brand_honda UUID;
    v_brand_hero UUID;
    v_brand_bajaj UUID;
    v_brand_tvs UUID;
    v_brand_yamaha UUID;
    v_brand_re UUID;
    v_brand_maruti UUID;
    v_brand_hyundai UUID;
    v_brand_tata UUID;
    v_brand_toyota UUID;

    -- Categories
    v_cat_maintenance UUID;
    v_cat_inspection UUID;
    v_cat_brakes UUID;
    v_cat_battery UUID;
    v_cat_engine UUID;
    v_cat_ac UUID;
    v_cat_emergency UUID;

    -- Helper procedure for service insertion
    v_svc_id UUID;
BEGIN
    -- 1. Vehicle Types
    INSERT INTO public.vehicle_types (name, description, is_active)
    VALUES 
        ('bike', 'Motorcycles and scooters maintenance & emergency repair', true),
        ('car', 'Hatchbacks, sedans, SUVs, and luxury passenger vehicles', true)
    ON CONFLICT (name) DO UPDATE SET is_active = true;

    SELECT id INTO v_bike_type_id FROM public.vehicle_types WHERE name = 'bike';
    SELECT id INTO v_car_type_id FROM public.vehicle_types WHERE name = 'car';

    -- 2. Vehicle Brands
    INSERT INTO public.vehicle_brands (name, is_active) VALUES
        ('Honda', true),
        ('Hero', true),
        ('Bajaj', true),
        ('TVS', true),
        ('Yamaha', true),
        ('Royal Enfield', true),
        ('Maruti Suzuki', true),
        ('Hyundai', true),
        ('Tata', true),
        ('Toyota', true)
    ON CONFLICT (name) DO UPDATE SET is_active = true;

    SELECT id INTO v_brand_honda FROM public.vehicle_brands WHERE name = 'Honda';
    SELECT id INTO v_brand_hero FROM public.vehicle_brands WHERE name = 'Hero';
    SELECT id INTO v_brand_bajaj FROM public.vehicle_brands WHERE name = 'Bajaj';
    SELECT id INTO v_brand_tvs FROM public.vehicle_brands WHERE name = 'TVS';
    SELECT id INTO v_brand_yamaha FROM public.vehicle_brands WHERE name = 'Yamaha';
    SELECT id INTO v_brand_re FROM public.vehicle_brands WHERE name = 'Royal Enfield';
    SELECT id INTO v_brand_maruti FROM public.vehicle_brands WHERE name = 'Maruti Suzuki';
    SELECT id INTO v_brand_hyundai FROM public.vehicle_brands WHERE name = 'Hyundai';
    SELECT id INTO v_brand_tata FROM public.vehicle_brands WHERE name = 'Tata';
    SELECT id INTO v_brand_toyota FROM public.vehicle_brands WHERE name = 'Toyota';

    -- 3. Vehicle Models
    INSERT INTO public.vehicle_models (brand_id, vehicle_type_id, name, year_start, is_active) VALUES
        (v_brand_honda, v_bike_type_id, 'Activa 6G', 2018, true),
        (v_brand_honda, v_bike_type_id, 'Shine 125', 2015, true),
        (v_brand_honda, v_bike_type_id, 'CB Unicorn', 2016, true),
        (v_brand_hero, v_bike_type_id, 'Splendor Plus', 2012, true),
        (v_brand_hero, v_bike_type_id, 'HF Deluxe', 2015, true),
        (v_brand_hero, v_bike_type_id, 'Passion Pro', 2014, true),
        (v_brand_bajaj, v_bike_type_id, 'Pulsar 150', 2015, true),
        (v_brand_bajaj, v_bike_type_id, 'Platina 100', 2016, true),
        (v_brand_bajaj, v_bike_type_id, 'Avenger 220', 2017, true),
        (v_brand_tvs, v_bike_type_id, 'Jupiter', 2016, true),
        (v_brand_tvs, v_bike_type_id, 'Apache RTR 160', 2017, true),
        (v_brand_tvs, v_bike_type_id, 'Raider 125', 2021, true),
        (v_brand_yamaha, v_bike_type_id, 'FZ-S Fi', 2018, true),
        (v_brand_yamaha, v_bike_type_id, 'MT-15', 2019, true),
        (v_brand_re, v_bike_type_id, 'Classic 350', 2015, true),
        (v_brand_re, v_bike_type_id, 'Bullet 350', 2014, true),
        (v_brand_re, v_bike_type_id, 'Hunter 350', 2022, true)
    ON CONFLICT (brand_id, vehicle_type_id, name) DO UPDATE SET is_active = true;

    INSERT INTO public.vehicle_models (brand_id, vehicle_type_id, name, year_start, is_active) VALUES
        (v_brand_maruti, v_car_type_id, 'Swift', 2015, true),
        (v_brand_maruti, v_car_type_id, 'Baleno', 2016, true),
        (v_brand_maruti, v_car_type_id, 'Brezza', 2016, true),
        (v_brand_maruti, v_car_type_id, 'WagonR', 2014, true),
        (v_brand_hyundai, v_car_type_id, 'i20', 2016, true),
        (v_brand_hyundai, v_car_type_id, 'Creta', 2016, true),
        (v_brand_hyundai, v_car_type_id, 'Venue', 2019, true),
        (v_brand_hyundai, v_car_type_id, 'Verna', 2017, true),
        (v_brand_tata, v_car_type_id, 'Nexon', 2017, true),
        (v_brand_tata, v_car_type_id, 'Punch', 2021, true),
        (v_brand_tata, v_car_type_id, 'Altroz', 2020, true),
        (v_brand_tata, v_car_type_id, 'Harrier', 2019, true),
        (v_brand_toyota, v_car_type_id, 'Innova Crysta', 2016, true),
        (v_brand_toyota, v_car_type_id, 'Fortuner', 2016, true),
        (v_brand_toyota, v_car_type_id, 'Glanza', 2019, true),
        (v_brand_honda, v_car_type_id, 'City', 2015, true),
        (v_brand_honda, v_car_type_id, 'Amaze', 2016, true),
        (v_brand_honda, v_car_type_id, 'Elevate', 2023, true)
    ON CONFLICT (brand_id, vehicle_type_id, name) DO UPDATE SET is_active = true;

    -- 4. Service Categories
    INSERT INTO public.service_categories (name, slug, description, display_order, is_active) VALUES
        ('Periodic Maintenance', 'periodic-maintenance', 'Scheduled maintenance, lubrication, filters, and standard service checkups', 1, true),
        ('General Inspection', 'inspection', 'Comprehensive diagnostic inspections, health reviews, and multi-point condition checks', 2, true),
        ('Brakes & Wheels', 'brakes-wheels', 'Brake pad replacement, disc rotor inspection, tyre punctures, and alignment', 3, true),
        ('Battery & Electrical', 'battery-electrical', 'Battery health testing, jumpstart assistance, and electrical diagnoses', 4, true),
        ('Engine & Performance', 'engine-performance', 'Engine oil flush, spark plugs, fluid top-ups, and tuning', 5, true),
        ('AC & Cooling', 'ac-cooling', 'Car air conditioning service, coolant replacement, and radiator checks', 6, true),
        ('Emergency Breakdown', 'emergency-services', 'Fast roadside breakdown, flat tyre, and emergency assistance', 7, true)
    ON CONFLICT (slug) DO UPDATE SET 
        name = EXCLUDED.name, 
        description = EXCLUDED.description, 
        display_order = EXCLUDED.display_order, 
        is_active = true;

    SELECT id INTO v_cat_maintenance FROM public.service_categories WHERE slug = 'periodic-maintenance';
    SELECT id INTO v_cat_inspection FROM public.service_categories WHERE slug = 'inspection';
    SELECT id INTO v_cat_brakes FROM public.service_categories WHERE slug = 'brakes-wheels';
    SELECT id INTO v_cat_battery FROM public.service_categories WHERE slug = 'battery-electrical';
    SELECT id INTO v_cat_engine FROM public.service_categories WHERE slug = 'engine-performance';
    SELECT id INTO v_cat_ac FROM public.service_categories WHERE slug = 'ac-cooling';
    SELECT id INTO v_cat_emergency FROM public.service_categories WHERE slug = 'emergency-services';

    -- 5. Services & Authoritative Pricing (Additive checks)

    -- 5.1 Standard Periodic Service
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Standard Periodic Service' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_maintenance, 'Standard Periodic Service', 'Engine oil replacement, oil filter check, air filter cleaning, chain/cable adjustment, and safety inspection.', 'both', 90, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 799.00, 699.00, true),
            (v_svc_id, v_car_type_id, 1999.00, 1799.00, true);
    END IF;

    -- 5.2 Comprehensive Full Service
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Comprehensive Full Service' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_maintenance, 'Comprehensive Full Service', 'Complete fluids flush, brake overhaul, electrical scan, suspension check, spark plug check, and detailed wash.', 'both', 150, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 1499.00, 1399.00, true),
            (v_svc_id, v_car_type_id, 3999.00, 3599.00, true);
    END IF;

    -- 5.3 Comprehensive 40-Point Inspection
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Comprehensive 40-Point Inspection' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_inspection, 'Comprehensive 40-Point Inspection', 'Comprehensive safety inspection covering powertrain, chassis, tyres, electronics, battery, and fluid levels.', 'both', 45, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 399.00, 349.00, true),
            (v_svc_id, v_car_type_id, 799.00, 699.00, true);
    END IF;

    -- 5.4 Pre-Purchase Health Check
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Pre-Purchase Health Check' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_inspection, 'Pre-Purchase Health Check', 'Detailed pre-purchase assessment including scanner diagnostics, bodywork inspection, and test drive evaluation.', 'car', 60, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_car_type_id, 1299.00, 1099.00, true);
    END IF;

    -- 5.5 Brake Pad Replacement & Inspection
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Brake Pad Replacement & Inspection' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_brakes, 'Brake Pad Replacement & Inspection', 'Installation of front/rear brake pads, rotor scoring check, caliper pin lubrication, and brake fluid top-up.', 'both', 45, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 299.00, 249.00, true),
            (v_svc_id, v_car_type_id, 699.00, 599.00, true);
    END IF;

    -- 5.6 Wheel Alignment & Balancing
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Wheel Alignment & Balancing' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_brakes, 'Wheel Alignment & Balancing', 'Laser 4-wheel computerized alignment and dynamic balancing for enhanced safety and tyre life.', 'car', 45, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_car_type_id, 599.00, 499.00, true);
    END IF;

    -- 5.7 Tyre Puncture & Valve Replacement
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Tyre Puncture & Valve Replacement' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_brakes, 'Tyre Puncture & Valve Replacement', 'Tubeless tyre puncture repair and pressure calibration with valve check.', 'both', 30, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 149.00, 99.00, true),
            (v_svc_id, v_car_type_id, 249.00, 199.00, true);
    END IF;

    -- 5.8 Battery Diagnostics & Jumpstart
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Battery Diagnostics & Jumpstart' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_battery, 'Battery Diagnostics & Jumpstart', 'On-spot battery load testing, alternator test, terminal de-corrosion, and rapid jumpstart assistance.', 'both', 30, true, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 299.00, 249.00, true),
            (v_svc_id, v_car_type_id, 499.00, 449.00, true);
    END IF;

    -- 5.9 Battery Replacement & Testing
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Battery Replacement & Testing' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_battery, 'Battery Replacement & Testing', 'Removal of depleted battery, installation of tested replacement, and charging system verification.', 'both', 30, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 199.00, 149.00, true),
            (v_svc_id, v_car_type_id, 399.00, 299.00, true);
    END IF;

    -- 5.10 Engine Oil & Filter Flush
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Engine Oil & Filter Flush' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_engine, 'Engine Oil & Filter Flush', 'High-performance engine oil change, premium oil filter replacement, and engine sump leak check.', 'both', 45, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 499.00, 449.00, true),
            (v_svc_id, v_car_type_id, 999.00, 899.00, true);
    END IF;

    -- 5.11 Spark Plug Replacement & Tuning
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Spark Plug Replacement & Tuning' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_engine, 'Spark Plug Replacement & Tuning', 'High-grade spark plug installation, ignition coil check, and throttle body cleaning.', 'both', 40, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 249.00, 199.00, true),
            (v_svc_id, v_car_type_id, 499.00, 399.00, true);
    END IF;

    -- 5.12 AC Gas Recharge & Cooling Inspection
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'AC Gas Recharge & Cooling Inspection' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_ac, 'AC Gas Recharge & Cooling Inspection', 'Evaporator coil cleaning, cabin filter replacement, condenser cleaning, and refrigerant gas recharge.', 'car', 60, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_car_type_id, 1499.00, 1299.00, true);
    END IF;

    -- 5.13 Radiator Coolant Flush & Leak Test
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Radiator Coolant Flush & Leak Test' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_ac, 'Radiator Coolant Flush & Leak Test', 'Complete drainage of degraded coolant, system anti-rust flush, and high-efficiency coolant refilling.', 'car', 45, false, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_car_type_id, 699.00, 599.00, true);
    END IF;

    -- 5.14 Roadside Emergency Assistance
    SELECT id INTO v_svc_id FROM public.services WHERE name = 'Roadside Emergency Assistance' LIMIT 1;
    IF v_svc_id IS NULL THEN
        INSERT INTO public.services (category_id, name, description, vehicle_type, estimated_duration_minutes, is_emergency, is_active)
        VALUES (v_cat_emergency, 'Roadside Emergency Assistance', 'Immediate on-site breakdown assistance for stranded vehicles, minor mechanical fixes, and fuel dispatch.', 'both', 45, true, true)
        RETURNING id INTO v_svc_id;

        INSERT INTO public.service_pricing (service_id, vehicle_type_id, base_price, minimum_price, is_active) VALUES
            (v_svc_id, v_bike_type_id, 499.00, 399.00, true),
            (v_svc_id, v_car_type_id, 799.00, 699.00, true);
    END IF;

END $$;
