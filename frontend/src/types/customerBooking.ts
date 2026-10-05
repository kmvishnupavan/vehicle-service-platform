export interface VehicleType {
  id: string;
  name: 'bike' | 'car';
  description?: string | null;
  icon_url?: string | null;
  is_active: boolean;
}

export interface VehicleBrand {
  id: string;
  name: string;
  logo_url?: string | null;
  is_active: boolean;
}

export interface VehicleModel {
  id: string;
  brand_id: string;
  vehicle_type_id: string;
  name: string;
  year_start?: number | null;
  year_end?: number | null;
  is_active: boolean;
}

export interface CustomerVehicle {
  id: string;
  customer_id: string;
  vehicle_type_id: string;
  brand_id: string;
  model_id: string;
  registration_number: string;
  nickname?: string | null;
  manufacture_year?: number | null;
  color?: string | null;
  fuel_type?: string | null;
  odometer_km?: number | null;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
  vehicle_types?: VehicleType;
  vehicle_brands?: VehicleBrand;
  vehicle_models?: VehicleModel;
}

export interface VehicleCreatePayload {
  vehicle_type_id: string;
  brand_id: string;
  model_id: string;
  registration_number: string;
  nickname?: string | null;
  manufacture_year?: number | null;
  color?: string | null;
  fuel_type?: string | null;
  odometer_km?: number | null;
  is_primary?: boolean;
}

export interface ServiceCategory {
  id: string;
  name: string;
  slug: string;
  description?: string | null;
  icon_url?: string | null;
  display_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ServicePricingTier {
  id: string;
  service_id: string;
  vehicle_type_id?: string | null;
  vehicle_type_name?: string | null;
  base_price: string | number;
  minimum_price: string | number;
  pricing_parameters?: Record<string, any>;
  effective_from: string;
  effective_to?: string | null;
  is_active: boolean;
}

export interface CatalogServiceItem {
  id: string;
  category_id: string;
  category_name?: string | null;
  name: string;
  description?: string | null;
  vehicle_type: 'bike' | 'car' | 'both';
  estimated_duration_minutes: number;
  is_emergency: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  pricing: ServicePricingTier[];
}

export interface CustomerAddress {
  id: string;
  customer_id: string;
  label: string;
  address_line: string;
  area: string;
  city: string;
  state: string;
  postal_code: string;
  latitude: number | string;
  longitude: number | string;
  landmark?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface AddressCreatePayload {
  label?: string;
  address_line: string;
  area: string;
  city: string;
  state: string;
  postal_code: string;
  latitude: number;
  longitude: number;
  landmark?: string | null;
  is_default?: boolean;
}

export interface BookingItemPayload {
  service_id: string;
  quantity: number;
  notes?: string | null;
}

export interface BookingCreatePayload {
  vehicle_id: string;
  address_id: string;
  items: BookingItemPayload[];
  scheduled_at?: string | null;
  customer_notes?: string | null;
}
