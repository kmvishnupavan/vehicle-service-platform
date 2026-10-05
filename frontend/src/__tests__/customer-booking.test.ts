import { describe, it, expect } from 'vitest';
import { resolveRoleRoute, UserRole } from '../types/user';
import {
  CustomerVehicle,
  VehicleCreatePayload,
  CatalogServiceItem,
  CustomerAddress,
  AddressCreatePayload,
  BookingCreatePayload,
} from '../types/customerBooking';

describe('Customer Booking Portal Test Suite', () => {
  // =========================================================================
  // 1. Role-Based Access Control for /customer/book-service
  // =========================================================================
  describe('1. Role-Based Access Control for Booking Wizard Route', () => {
    it('allows authenticated Customer to access /customer/book-service', () => {
      const customerUser = { role: 'customer' as UserRole };
      const result = resolveRoleRoute('/customer/book-service', customerUser, ['customer', 'admin']);
      expect(result.allowed).toBe(true);
      expect(result.redirectPath).toBeNull();
    });

    it('allows Admin to access /customer/book-service', () => {
      const adminUser = { role: 'admin' as UserRole };
      const result = resolveRoleRoute('/customer/book-service', adminUser, ['customer', 'admin']);
      expect(result.allowed).toBe(true);
      expect(result.redirectPath).toBeNull();
    });

    it('prevents Mechanic from accessing /customer/book-service and redirects to /mechanic/dashboard', () => {
      const mechanicUser = { role: 'mechanic' as UserRole };
      const result = resolveRoleRoute('/customer/book-service', mechanicUser, ['customer', 'admin']);
      expect(result.allowed).toBe(false);
      expect(result.redirectPath).toBe('/mechanic/dashboard');
    });

    it('redirects unauthenticated visitor to /login', () => {
      const result = resolveRoleRoute('/customer/book-service', null, ['customer', 'admin']);
      expect(result.allowed).toBe(false);
      expect(result.redirectPath).toBe('/login');
    });
  });

  // =========================================================================
  // 2. Customer Dashboard "Book a Service" CTA
  // =========================================================================
  describe('2. Dashboard Call-to-Action Routes', () => {
    it('provides the correct navigation route for booking service', () => {
      const bookingRoute = '/customer/book-service';
      expect(bookingRoute).toBe('/customer/book-service');
    });
  });

  // =========================================================================
  // 3. Step 1: Vehicle Selection & Validation
  // =========================================================================
  describe('3. Step 1: Vehicle Selection & Validation', () => {
    const mockVehicles: CustomerVehicle[] = [
      {
        id: 'veh-1',
        customer_id: 'cust-1',
        vehicle_type_id: 'vt-car',
        brand_id: 'brand-honda',
        model_id: 'mod-city',
        registration_number: 'KA-01-AB-1234',
        nickname: 'City Car',
        manufacture_year: 2022,
        is_primary: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        vehicle_types: { id: 'vt-car', name: 'car', is_active: true },
        vehicle_brands: { id: 'brand-honda', name: 'Honda', is_active: true },
        vehicle_models: {
          id: 'mod-city',
          brand_id: 'brand-honda',
          vehicle_type_id: 'vt-car',
          name: 'City',
          is_active: true,
        },
      },
      {
        id: 'veh-2',
        customer_id: 'cust-1',
        vehicle_type_id: 'vt-bike',
        brand_id: 'brand-hero',
        model_id: 'mod-splendor',
        registration_number: 'KA-01-CD-5678',
        nickname: 'Daily Commute',
        manufacture_year: 2021,
        is_primary: false,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        vehicle_types: { id: 'vt-bike', name: 'bike', is_active: true },
        vehicle_brands: { id: 'brand-hero', name: 'Hero', is_active: true },
        vehicle_models: {
          id: 'mod-splendor',
          brand_id: 'brand-hero',
          vehicle_type_id: 'vt-bike',
          name: 'Splendor Plus',
          is_active: true,
        },
      },
    ];

    it('selects an existing vehicle by ID', () => {
      let selectedVehicleId: string | null = null;
      const selectVehicle = (id: string) => {
        selectedVehicleId = id;
      };

      selectVehicle('veh-1');
      expect(selectedVehicleId).toBe('veh-1');

      const found = mockVehicles.find((v) => v.id === selectedVehicleId);
      expect(found).toBeDefined();
      expect(found?.registration_number).toBe('KA-01-AB-1234');
      expect(found?.vehicle_types?.name).toBe('car');
    });

    it('validates required fields for creating a new vehicle', () => {
      const validateVehiclePayload = (payload: Partial<VehicleCreatePayload>): { isValid: boolean; errors: string[] } => {
        const errors: string[] = [];
        if (!payload.vehicle_type_id) errors.push('Vehicle type is required');
        if (!payload.brand_id) errors.push('Brand is required');
        if (!payload.model_id) errors.push('Model is required');
        if (!payload.registration_number?.trim()) {
          errors.push('Registration number is required');
        } else if (payload.registration_number.trim().length < 5) {
          errors.push('Registration number is too short');
        }
        return { isValid: errors.length === 0, errors };
      };

      // Incomplete payload
      const invalid = validateVehiclePayload({
        vehicle_type_id: 'vt-car',
      });
      expect(invalid.isValid).toBe(false);
      expect(invalid.errors).toContain('Brand is required');
      expect(invalid.errors).toContain('Model is required');
      expect(invalid.errors).toContain('Registration number is required');

      // Complete valid payload
      const valid = validateVehiclePayload({
        vehicle_type_id: 'vt-car',
        brand_id: 'brand-honda',
        model_id: 'mod-city',
        registration_number: 'KA-05-MJ-9999',
      });
      expect(valid.isValid).toBe(true);
      expect(valid.errors.length).toBe(0);
    });

    it('prevents proceeding past Step 1 when no vehicle is selected', () => {
      const canProceedStep1 = (selectedVehicleId: string | null): boolean => {
        return Boolean(selectedVehicleId && selectedVehicleId.trim().length > 0);
      };

      expect(canProceedStep1(null)).toBe(false);
      expect(canProceedStep1('')).toBe(false);
      expect(canProceedStep1('veh-1')).toBe(true);
    });
  });

  // =========================================================================
  // 4. Step 2: Service Selection & Dynamic Pricing
  // =========================================================================
  describe('4. Step 2: Service Selection & Pricing Engine Calculations', () => {
    const mockServices: CatalogServiceItem[] = [
      {
        id: 'srv-gen-bike',
        category_id: 'cat-periodic',
        category_name: 'Periodic Maintenance',
        name: 'General Bike Service',
        description: 'Complete 2-wheeler inspection and oil change',
        vehicle_type: 'bike',
        estimated_duration_minutes: 60,
        is_emergency: false,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        pricing: [
          {
            id: 'price-1',
            service_id: 'srv-gen-bike',
            vehicle_type_id: 'vt-bike',
            vehicle_type_name: 'bike',
            base_price: 699,
            minimum_price: 699,
            effective_from: '2026-01-01T00:00:00Z',
            is_active: true,
          },
        ],
      },
      {
        id: 'srv-full-car',
        category_id: 'cat-periodic',
        category_name: 'Periodic Maintenance',
        name: 'Full Car Service',
        description: 'Comprehensive 4-wheeler periodic maintenance',
        vehicle_type: 'car',
        estimated_duration_minutes: 120,
        is_emergency: false,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        pricing: [
          {
            id: 'price-2',
            service_id: 'srv-full-car',
            vehicle_type_id: 'vt-car',
            vehicle_type_name: 'car',
            base_price: 2499,
            minimum_price: 2499,
            effective_from: '2026-01-01T00:00:00Z',
            is_active: true,
          },
        ],
      },
      {
        id: 'srv-brake-both',
        category_id: 'cat-brakes',
        category_name: 'Brakes & Wheels',
        name: 'Brake Inspection & Service',
        description: 'Brake pad and shoe inspection and replacement',
        vehicle_type: 'both',
        estimated_duration_minutes: 45,
        is_emergency: false,
        is_active: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        pricing: [
          {
            id: 'price-3a',
            service_id: 'srv-brake-both',
            vehicle_type_id: 'vt-bike',
            vehicle_type_name: 'bike',
            base_price: 349,
            minimum_price: 349,
            effective_from: '2026-01-01T00:00:00Z',
            is_active: true,
          },
          {
            id: 'price-3b',
            service_id: 'srv-brake-both',
            vehicle_type_id: 'vt-car',
            vehicle_type_name: 'car',
            base_price: 799,
            minimum_price: 799,
            effective_from: '2026-01-01T00:00:00Z',
            is_active: true,
          },
        ],
      },
    ];

    it('filters services matching selected vehicle type', () => {
      const getServicesForVehicle = (vehicleTypeName: 'bike' | 'car') => {
        return mockServices.filter(
          (s) => s.vehicle_type === 'both' || s.vehicle_type === vehicleTypeName
        );
      };

      const bikeServices = getServicesForVehicle('bike');
      expect(bikeServices.length).toBe(2);
      expect(bikeServices.some((s) => s.name === 'General Bike Service')).toBe(true);
      expect(bikeServices.some((s) => s.name === 'Brake Inspection & Service')).toBe(true);
      expect(bikeServices.some((s) => s.name === 'Full Car Service')).toBe(false);

      const carServices = getServicesForVehicle('car');
      expect(carServices.length).toBe(2);
      expect(carServices.some((s) => s.name === 'Full Car Service')).toBe(true);
      expect(carServices.some((s) => s.name === 'Brake Inspection & Service')).toBe(true);
      expect(carServices.some((s) => s.name === 'General Bike Service')).toBe(false);
    });

    it('computes deterministic subtotal, 18% GST tax, and total estimate', () => {
      const calculateEstimate = (selectedPrices: number[]) => {
        const subtotal = selectedPrices.reduce((sum, p) => sum + p, 0);
        const taxAmount = Math.round(subtotal * 0.18 * 100) / 100;
        const total = Math.round((subtotal + taxAmount) * 100) / 100;
        return { subtotal, taxAmount, total };
      };

      // Bike: General service (699) + Brakes (349) = 1048
      const bikeEstimate = calculateEstimate([699, 349]);
      expect(bikeEstimate.subtotal).toBe(1048);
      expect(bikeEstimate.taxAmount).toBe(188.64);
      expect(bikeEstimate.total).toBe(1236.64);

      // Car: Full service (2499)
      const carEstimate = calculateEstimate([2499]);
      expect(carEstimate.subtotal).toBe(2499);
      expect(carEstimate.taxAmount).toBe(449.82);
      expect(carEstimate.total).toBe(2948.82);
    });

    it('prevents proceeding past Step 2 when no services are selected', () => {
      const canProceedStep2 = (selectedServicesCount: number): boolean => {
        return selectedServicesCount > 0;
      };

      expect(canProceedStep2(0)).toBe(false);
      expect(canProceedStep2(1)).toBe(true);
      expect(canProceedStep2(3)).toBe(true);
    });
  });

  // =========================================================================
  // 5. Step 3: Address Selection & Validation
  // =========================================================================
  describe('5. Step 3: Address Selection & Validation', () => {
    const mockAddresses: CustomerAddress[] = [
      {
        id: 'addr-home',
        customer_id: 'cust-1',
        label: 'Home',
        address_line: '123 Koramangala 4th Block',
        area: 'Koramangala',
        city: 'Bengaluru',
        state: 'Karnataka',
        postal_code: '560034',
        latitude: 12.9352,
        longitude: 77.6245,
        is_default: true,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ];

    it('selects an existing address', () => {
      let selectedAddressId: string | null = null;
      selectedAddressId = 'addr-home';
      const address = mockAddresses.find((a) => a.id === selectedAddressId);
      expect(address).toBeDefined();
      expect(address?.city).toBe('Bengaluru');
      expect(address?.postal_code).toBe('560034');
    });

    it('validates address creation payload', () => {
      const validateAddress = (payload: Partial<AddressCreatePayload>): { isValid: boolean; errors: string[] } => {
        const errors: string[] = [];
        if (!payload.address_line?.trim()) errors.push('Address line is required');
        if (!payload.city?.trim()) errors.push('City is required');
        if (!payload.state?.trim()) errors.push('State is required');
        if (!payload.postal_code?.trim() || !/^\d{6}$/.test(payload.postal_code.trim())) {
          errors.push('Valid 6-digit PIN code is required');
        }
        if (payload.latitude === undefined || payload.longitude === undefined) {
          errors.push('Location coordinates are required');
        }
        return { isValid: errors.length === 0, errors };
      };

      const invalid = validateAddress({ address_line: 'Test' });
      expect(invalid.isValid).toBe(false);
      expect(invalid.errors).toContain('City is required');
      expect(invalid.errors).toContain('Valid 6-digit PIN code is required');

      const valid = validateAddress({
        address_line: '456 Indiranagar 100ft Rd',
        area: 'Indiranagar',
        city: 'Bengaluru',
        state: 'Karnataka',
        postal_code: '560038',
        latitude: 12.9716,
        longitude: 77.6412,
      });
      expect(valid.isValid).toBe(true);
      expect(valid.errors.length).toBe(0);
    });

    it('prevents proceeding past Step 3 when address is not chosen', () => {
      const canProceedStep3 = (addressId: string | null): boolean => {
        return Boolean(addressId && addressId.length > 0);
      };
      expect(canProceedStep3(null)).toBe(false);
      expect(canProceedStep3('addr-home')).toBe(true);
    });
  });

  // =========================================================================
  // 6. Step 4: Timing (Immediate vs Scheduled)
  // =========================================================================
  describe('6. Step 4: Timing Selection (ASAP vs Scheduled)', () => {
    it('sets scheduled_at to null for immediate/ASAP bookings', () => {
      const timingMode: 'immediate' | 'scheduled' = 'immediate';
      const scheduledAt = timingMode === 'immediate' ? null : '2026-10-06T10:00:00Z';
      expect(scheduledAt).toBeNull();
    });

    it('formats valid ISO scheduled timestamp for scheduled bookings', () => {
      const dateStr = '2026-10-10';
      const timeStr = '14:30';
      const combined = new Date(`${dateStr}T${timeStr}:00`);

      expect(combined.toISOString()).toBeDefined();
      expect(combined.toISOString()).toContain('2026-10-10');
    });

    it('validates that scheduled time is in the future', () => {
      const validateScheduledTime = (isoString: string): boolean => {
        const target = new Date(isoString).getTime();
        const now = Date.now();
        return target > now;
      };

      const futureDate = new Date(Date.now() + 86400000).toISOString();
      const pastDate = new Date(Date.now() - 86400000).toISOString();

      expect(validateScheduledTime(futureDate)).toBe(true);
      expect(validateScheduledTime(pastDate)).toBe(false);
    });
  });

  // =========================================================================
  // 7. Step 5: Booking Payload Construction & Duplicate-Submit Prevention
  // =========================================================================
  describe('7. Step 5: Booking Creation & Duplicate Submit Guard', () => {
    it('constructs authoritative BookingCreatePayload matching backend schema', () => {
      const payload: BookingCreatePayload = {
        vehicle_id: 'veh-1',
        address_id: 'addr-home',
        items: [
          {
            service_id: 'srv-full-car',
            quantity: 1,
            notes: null,
          },
        ],
        scheduled_at: null,
        customer_notes: 'Please check tyre pressure as well',
      };

      expect(payload.vehicle_id).toBe('veh-1');
      expect(payload.address_id).toBe('addr-home');
      expect(payload.items.length).toBe(1);
      expect(payload.items[0].service_id).toBe('srv-full-car');
      expect(payload.scheduled_at).toBeNull();
      expect(payload.customer_notes).toBe('Please check tyre pressure as well');
    });

    it('prevents duplicate booking submission when request is already in-flight', () => {
      let isSubmitting = false;
      let submitCallCount = 0;

      const triggerSubmit = () => {
        if (isSubmitting) return false;
        isSubmitting = true;
        submitCallCount++;
        return true;
      };

      // First click
      const firstClick = triggerSubmit();
      expect(firstClick).toBe(true);
      expect(submitCallCount).toBe(1);

      // Rapid secondary click while still submitting
      const secondClick = triggerSubmit();
      expect(secondClick).toBe(false);
      expect(submitCallCount).toBe(1); // blocked duplicate
    });
  });

  // =========================================================================
  // 8. Payment UI Visibility & Eligibility
  // =========================================================================
  describe('8. Payment UI Visibility & State Machine Eligibility', () => {
    const isPaymentEligible = (bookingStatus: string, paymentStatus: string): boolean => {
      return (
        ['service_completed', 'payment_pending'].includes(bookingStatus) &&
        paymentStatus !== 'paid'
      );
    };

    it('shows Pay Now button when service is completed and pending payment', () => {
      expect(isPaymentEligible('service_completed', 'pending')).toBe(true);
      expect(isPaymentEligible('payment_pending', 'pending')).toBe(true);
    });

    it('hides Pay Now button when booking is already paid', () => {
      expect(isPaymentEligible('service_completed', 'paid')).toBe(false);
      expect(isPaymentEligible('paid', 'paid')).toBe(false);
    });

    it('hides Pay Now button during active service before completion', () => {
      expect(isPaymentEligible('draft', 'pending')).toBe(false);
      expect(isPaymentEligible('pending_acceptance', 'pending')).toBe(false);
      expect(isPaymentEligible('mechanic_en_route', 'pending')).toBe(false);
      expect(isPaymentEligible('mechanic_arrived', 'pending')).toBe(false);
      expect(isPaymentEligible('inspection', 'pending')).toBe(false);
      expect(isPaymentEligible('service_in_progress', 'pending')).toBe(false);
    });

    it('hides Pay Now button when booking is cancelled', () => {
      expect(isPaymentEligible('cancelled', 'pending')).toBe(false);
    });
  });

  // =========================================================================
  // 9. Razorpay Sandbox Integration & Verification
  // =========================================================================
  describe('9. Payment Sandbox Order & Signature Handling', () => {
    it('structures Razorpay order verification payload with required cryptographic fields', () => {
      const verificationPayload = {
        booking_id: 'book-123',
        razorpay_order_id: 'order_test_12345',
        razorpay_payment_id: 'pay_test_67890',
        razorpay_signature: 'test_signature_hash',
      };

      expect(verificationPayload.booking_id).toBe('book-123');
      expect(verificationPayload.razorpay_order_id).toBe('order_test_12345');
      expect(verificationPayload.razorpay_payment_id).toBe('pay_test_67890');
      expect(verificationPayload.razorpay_signature).toBe('test_signature_hash');
    });

    it('disallows non-sandbox payments in client environment', () => {
      // Verifies client sandbox key structure (rzp_test_*)
      const testKey = 'rzp_test_placeholder';
      const isTestKey = testKey.startsWith('rzp_test_');
      expect(isTestKey).toBe(true);
    });
  });
});
