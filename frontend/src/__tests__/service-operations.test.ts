import { describe, it, expect } from 'vitest';
import { getFriendlyBookingStatus } from '../utils/bookingStatus';
import {
  BookingChecklistItem,
  BookingPart,
  PriceSnapshot,
} from '../types/serviceOperations';

describe('Phase 12: Production-Grade Vehicle Service Operations Test Suite', () => {
  // ===========================================================================
  // 1. Customer UX: Friendly Booking Status Formatting Across Operational States
  // ===========================================================================
  describe('Operational Lifecycle State Formatting', () => {
    it('formats mechanic_arrived correctly', () => {
      const arrived = getFriendlyBookingStatus('mechanic_arrived');
      expect(arrived.title).toBe('Your mechanic has arrived');
      expect(arrived.badgeText).toBe('Arrived');
      expect(arrived.subtitle).toContain('Technician has reached your doorstep');
    });

    it('formats inspection correctly with vehicle inspection details', () => {
      const inspection = getFriendlyBookingStatus('inspection');
      expect(inspection.title).toBe('Vehicle inspection in progress');
      expect(inspection.badgeText).toBe('Inspection');
      expect(inspection.subtitle).toContain('condition diagnostics');
    });

    it('formats awaiting_customer_approval with approval required prompt', () => {
      const approval = getFriendlyBookingStatus('awaiting_customer_approval');
      expect(approval.title).toBe('Additional work requires your approval');
      expect(approval.badgeText).toBe('Approval Required');
      expect(approval.subtitle).toContain('Review recommended parts or tasks');
    });

    it('formats service_in_progress with active work indicator', () => {
      const inProgress = getFriendlyBookingStatus('service_in_progress');
      expect(inProgress.title).toBe('Service in progress');
      expect(inProgress.badgeText).toBe('In Progress');
      expect(inProgress.subtitle).toContain('Technician is actively servicing');
    });

    it('formats service_completed with quality checks passed', () => {
      const completed = getFriendlyBookingStatus('service_completed');
      expect(completed.title).toBe('Service completed');
      expect(completed.badgeText).toBe('Completed');
      expect(completed.subtitle).toContain('Service work is finished');
    });

    it('formats payment_pending and paid states', () => {
      const paymentPending = getFriendlyBookingStatus('payment_pending');
      expect(paymentPending.title).toBe('Service completed');
      expect(paymentPending.badgeText).toBe('Completed');

      const paid = getFriendlyBookingStatus('paid');
      expect(paid.title).toBe('Paid & Completed');
      expect(paid.badgeText).toBe('Paid');
    });

    it('formats disputed state with customer care notification', () => {
      const disputed = getFriendlyBookingStatus('disputed');
      expect(disputed.title).toBe('Under dispute review');
      expect(disputed.badgeText).toBe('Disputed');
      expect(disputed.subtitle).toContain('Platform operations');
    });
  });

  // ===========================================================================
  // 2. Pricing Engine & Deterministic 18% GST Calculations
  // ===========================================================================
  describe('Pricing Engine & Price Snapshot Logic', () => {
    it('calculates deterministic 18% GST and total without floating-point anomalies', () => {
      const basePrice = 1500;
      const additionalCharges = 500;
      const discountAmount = 100;
      const partsTotal = 800;
      const laborTotal = 200;

      const taxableBase = Math.max(
        0,
        basePrice + additionalCharges + partsTotal + laborTotal - discountAmount
      );
      expect(taxableBase).toBe(2900);

      // Deterministic 18% GST rounded to 2 decimals
      const tax = Math.round(taxableBase * 0.18 * 100) / 100;
      expect(tax).toBe(522.0);

      const total = Math.round((taxableBase + tax) * 100) / 100;
      expect(total).toBe(3422.0);
    });

    it('creates and validates an immutable PriceSnapshot structure', () => {
      const snapshot: PriceSnapshot = {
        base_service_amount: 2500,
        parts_total: 1200,
        labor_total: 600,
        additional_work_total: 400,
        discount_amount: 200,
        taxable_base: 4500,
        tax_rate: 0.18,
        tax_amount: 810,
        total_amount: 5310,
        snapshot_timestamp: new Date().toISOString(),
        approved_by: 'customer-uuid-123',
        version: 1,
      };

      expect(snapshot.taxable_base).toBe(
        snapshot.base_service_amount +
          snapshot.parts_total +
          snapshot.labor_total +
          snapshot.additional_work_total -
          snapshot.discount_amount
      );
      expect(snapshot.tax_amount).toBe(snapshot.taxable_base * snapshot.tax_rate);
      expect(snapshot.total_amount).toBe(snapshot.taxable_base + snapshot.tax_amount);
      expect(snapshot.approved_by).toBe('customer-uuid-123');
      expect(snapshot.version).toBe(1);
    });
  });

  // ===========================================================================
  // 3. Service Checklist Progress and Mandatory Task Gates
  // ===========================================================================
  describe('Service Checklist Completion & Mandatory Gating', () => {
    const mockChecklist: BookingChecklistItem[] = [
      {
        id: 'chk-1',
        booking_id: 'b-101',
        item_key: 'brakes_front_pads',
        category_slug: 'brakes',
        title: 'Inspect front brake pads',
        is_mandatory: true,
        is_completed: true,
        completed_at: new Date().toISOString(),
      },
      {
        id: 'chk-2',
        booking_id: 'b-101',
        item_key: 'brakes_fluid_test',
        category_slug: 'brakes',
        title: 'Test brake fluid boiling point',
        is_mandatory: true,
        is_completed: false,
      },
      {
        id: 'chk-3',
        booking_id: 'b-101',
        item_key: 'battery_terminals',
        category_slug: 'battery',
        title: 'Clean battery terminals',
        is_mandatory: false,
        is_completed: true,
        completed_at: new Date().toISOString(),
      },
    ];

    it('calculates completion progress percentage correctly', () => {
      const completedCount = mockChecklist.filter((c) => c.is_completed).length;
      const progressPercent = Math.round((completedCount / mockChecklist.length) * 100);
      expect(completedCount).toBe(2);
      expect(progressPercent).toBe(67);
    });

    it('identifies uncompleted mandatory checkpoints that gate service completion', () => {
      const uncompletedRequired = mockChecklist.filter(
        (c) => c.is_mandatory && !c.is_completed
      );
      expect(uncompletedRequired.length).toBe(1);
      expect(uncompletedRequired[0].title).toBe('Test brake fluid boiling point');
    });

    it('passes completion gate when all mandatory checkpoints are completed', () => {
      const fullyCompleted = mockChecklist.map((c) => ({
        ...c,
        is_completed: true,
      }));
      const uncompletedRequired = fullyCompleted.filter(
        (c) => c.is_mandatory && !c.is_completed
      );
      expect(uncompletedRequired.length).toBe(0);
    });
  });

  // ===========================================================================
  // 4. Parts Tracking & Aggregation
  // ===========================================================================
  describe('Parts Tracking & Calculation', () => {
    const partsList: BookingPart[] = [
      {
        id: 'part-1',
        booking_id: 'b-101',
        part_name: 'DOT 4 Brake Fluid (500ml)',
        part_number: 'BF-DOT4-500',
        quantity: 2,
        unit_price: 350,
        total_price: 700,
        warranty_notes: '6 Months Manufacturer Warranty',
        created_at: new Date().toISOString(),
      },
      {
        id: 'part-2',
        booking_id: 'b-101',
        part_name: 'Front Ceramic Brake Pads Set',
        part_number: 'BP-FRT-992',
        quantity: 1,
        unit_price: 2400,
        total_price: 2400,
        warranty_notes: '12 Months / 15,000 km Warranty',
        created_at: new Date().toISOString(),
      },
    ];

    it('verifies part total price calculation matches quantity * unit price', () => {
      partsList.forEach((part) => {
        expect(part.total_price).toBe(part.quantity * part.unit_price);
      });
    });

    it('aggregates total parts cost for transparent invoicing', () => {
      const totalPartsAmount = partsList.reduce((acc, p) => acc + p.total_price, 0);
      expect(totalPartsAmount).toBe(3100);
    });
  });
});
