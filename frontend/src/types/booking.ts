/**
 * Booking and Mechanic Domain Types for Frontend.
 *
 * Corresponds to backend PostgreSQL models and Pydantic schemas.
 */

export type BookingStatus =
  | 'pending'
  | 'confirmed'
  | 'mechanic_assigned'
  | 'mechanic_en_route'
  | 'mechanic_arrived'
  | 'inspection'
  | 'awaiting_customer_approval'
  | 'service_in_progress'
  | 'additional_work'
  | 'service_completed'
  | 'payment_pending'
  | 'paid'
  | 'cancelled'
  | 'disputed';

export type PaymentStatus =
  | 'unpaid'
  | 'pending'
  | 'authorized'
  | 'paid'
  | 'failed'
  | 'refunded';

export interface BookingItem {
  id: string;
  booking_id: string;
  service_id: string;
  unit_price: string;
  services?: {
    name: string;
    description?: string;
  };
}

export interface ServiceAddress {
  id: string;
  street_address: string;
  city: string;
  state: string;
  postal_code: string;
  latitude?: number | null;
  longitude?: number | null;
}

export interface CustomerVehicle {
  id: string;
  license_plate: string;
  year?: number;
  vehicle_models?: {
    name: string;
    brands?: {
      name: string;
    };
  };
}

export interface AssignedMechanicProfile {
  id: string;
  user_id?: string;
  full_name?: string;
  business_name?: string | null;
  experience_years?: number;
  average_rating?: number | string;
  review_count?: number;
  avatar_url?: string | null;
  current_latitude?: number | null;
  current_longitude?: number | null;
}

export interface Booking {
  id: string;
  booking_number: string;
  customer_id: string;
  vehicle_id: string;
  address_id: string;
  booking_status: BookingStatus;
  payment_status: PaymentStatus;
  subtotal: string;
  additional_charges: string;
  discount_amount: string;
  tax_amount: string;
  total_amount: string;
  scheduled_at: string;
  created_at: string;
  updated_at: string;
  items?: BookingItem[];
  booking_items?: BookingItem[];
  address?: ServiceAddress;
  vehicle?: CustomerVehicle;
  assigned_mechanic?: AssignedMechanicProfile | null;
}

export interface MechanicLocationRestResponse {
  mechanic_id: string;
  latitude: number;
  longitude: number;
  accuracy_meters?: number | null;
  recorded_at: string;
}
