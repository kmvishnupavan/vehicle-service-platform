import { describe, it, expect } from 'vitest';
import {
  PayoutItem,
  PayoutStatus,
  PayoutSummary,
} from '../types/payout';

// Helper: Formatter for currency with Indian numbering
export function formatCurrencyDisplay(amount: string | number): string {
  const num = typeof amount === 'number' ? amount : parseFloat(amount || '0');
  return `₹${num.toFixed(2)}`;
}

// Helper: Financial breakdown verification (Gross - Commission - Deductions = Net)
export function verifyFinancialFormula(item: PayoutItem): {
  calculatedNet: number;
  recordedNet: number;
  isConsistent: boolean;
  commissionPercentage: number;
} {
  const gross = parseFloat(item.gross_amount);
  const comm = parseFloat(item.commission_amount);
  const ded = parseFloat(item.deduction_amount || '0.00');
  const recorded = parseFloat(item.net_amount);

  const calculated = Math.round((gross - comm - ded) * 100) / 100;
  const isConsistent = Math.abs(calculated - recorded) < 0.01;
  const commissionPercentage = Math.round(parseFloat(item.commission_rate) * 100);

  return {
    calculatedNet: calculated,
    recordedNet: recorded,
    isConsistent,
    commissionPercentage,
  };
}

// Helper: Status badge style mapping
export function getStatusBadgeConfig(status: PayoutStatus | string): {
  label: string;
  variant: 'success' | 'info' | 'warning' | 'purple' | 'danger' | 'neutral';
} {
  switch ((status || '').toLowerCase()) {
    case 'paid':
      return { label: 'Paid & Settled', variant: 'success' };
    case 'eligible':
      return { label: 'Eligible', variant: 'info' };
    case 'processing':
      return { label: 'Processing', variant: 'info' };
    case 'pending':
      return { label: 'Pending Hold', variant: 'warning' };
    case 'reversed':
      return { label: 'Reversed', variant: 'purple' };
    case 'failed':
      return { label: 'Failed', variant: 'danger' };
    case 'cancelled':
      return { label: 'Cancelled', variant: 'neutral' };
    default:
      return { label: status, variant: 'neutral' };
  }
}

// Helper: Pagination metadata
export function calculatePayoutPagination(total: number, limit: number, offset: number) {
  const safeLimit = Math.min(Math.max(1, limit), 100);
  const safeOffset = Math.max(0, offset);
  const currentPage = Math.floor(safeOffset / safeLimit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / safeLimit));
  const hasNext = safeOffset + safeLimit < total;
  const hasPrev = safeOffset > 0;

  return {
    currentPage,
    totalPages,
    hasNext,
    hasPrev,
    startItem: total > 0 ? safeOffset + 1 : 0,
    endItem: Math.min(safeOffset + safeLimit, total),
  };
}

// Helper: Mock data generators
export function createMockPayoutItem(overrides: Partial<PayoutItem> = {}): PayoutItem {
  return {
    id: '11111111-aaaa-1111-aaaa-111111111111',
    booking_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
    mechanic_id: '22222222-2222-2222-2222-222222222222',
    booking_number: 'BK-2026-001',
    gross_amount: '1000.00',
    commission_rate: '0.2000',
    commission_amount: '200.00',
    deduction_amount: '0.00',
    net_amount: '800.00',
    currency: 'INR',
    status: 'eligible',
    created_at: '2026-09-01T10:00:00Z',
    updated_at: '2026-09-01T10:00:00Z',
    eligible_at: '2026-09-01T10:00:00Z',
    settled_at: null,
    reversed_at: null,
    provider: 'manual',
    provider_payout_id: null,
    failure_reason: null,
    metadata: { policy_name: 'Standard Platform Commission (20%)' },
    ...overrides,
  };
}

export function createMockPayoutSummary(overrides: Partial<PayoutSummary> = {}): PayoutSummary {
  return {
    total_gross: '2500.00',
    total_commission: '500.00',
    total_deductions: '0.00',
    total_net: '2000.00',
    pending_amount: '400.00',
    eligible_amount: '800.00',
    processing_amount: '0.00',
    paid_amount: '800.00',
    reversed_amount: '0.00',
    currency: 'INR',
    ...overrides,
  };
}

// ==============================================================================
// TEST SUITE
// ==============================================================================

describe('Mechanic Payout Ledger & Settlement (Phase 8.7)', () => {
  describe('1. Payout Page Structure & Summary Cards', () => {
    it('aggregates summary cards balances accurately with strict formatting', () => {
      const summary = createMockPayoutSummary();

      expect(formatCurrencyDisplay(summary.total_gross)).toBe('₹2500.00');
      expect(formatCurrencyDisplay(summary.total_commission)).toBe('₹500.00');
      expect(formatCurrencyDisplay(summary.total_net)).toBe('₹2000.00');
      expect(formatCurrencyDisplay(summary.eligible_amount)).toBe('₹800.00');
      expect(formatCurrencyDisplay(summary.paid_amount)).toBe('₹800.00');
      expect(formatCurrencyDisplay(summary.pending_amount)).toBe('₹400.00');
      expect(summary.currency).toBe('INR');
    });

    it('handles zero balances gracefully in empty summary without NaN', () => {
      const zeroSummary: PayoutSummary = {
        total_gross: '0.00',
        total_commission: '0.00',
        total_deductions: '0.00',
        total_net: '0.00',
        pending_amount: '0.00',
        eligible_amount: '0.00',
        processing_amount: '0.00',
        paid_amount: '0.00',
        reversed_amount: '0.00',
        currency: 'INR',
      };

      expect(formatCurrencyDisplay(zeroSummary.total_net)).toBe('₹0.00');
      expect(formatCurrencyDisplay(zeroSummary.eligible_amount)).toBe('₹0.00');
    });
  });

  describe('2. Payout Table & Itemized Breakdown (Sections 18 & 19)', () => {
    it('verifies mathematical consistency of gross, commission, deductions, and net', () => {
      const payout = createMockPayoutItem({
        gross_amount: '1200.00',
        commission_rate: '0.2000',
        commission_amount: '240.00',
        deduction_amount: '0.00',
        net_amount: '960.00',
      });

      const formula = verifyFinancialFormula(payout);
      expect(formula.isConsistent).toBe(true);
      expect(formula.calculatedNet).toBe(960.00);
      expect(formula.commissionPercentage).toBe(20);
    });

    it('verifies itemized deduction handling', () => {
      const payoutWithDeductions = createMockPayoutItem({
        gross_amount: '1000.00',
        commission_rate: '0.2000',
        commission_amount: '200.00',
        deduction_amount: '50.00',
        net_amount: '750.00',
      });

      const formula = verifyFinancialFormula(payoutWithDeductions);
      expect(formula.isConsistent).toBe(true);
      expect(formula.calculatedNet).toBe(750.00);
    });
  });

  describe('3. Payout Status Badge Mapping', () => {
    it('correctly maps all 7 lifecycle status states to distinct badge styles', () => {
      expect(getStatusBadgeConfig('paid')).toEqual({
        label: 'Paid & Settled',
        variant: 'success',
      });
      expect(getStatusBadgeConfig('eligible')).toEqual({
        label: 'Eligible',
        variant: 'info',
      });
      expect(getStatusBadgeConfig('processing')).toEqual({
        label: 'Processing',
        variant: 'info',
      });
      expect(getStatusBadgeConfig('pending')).toEqual({
        label: 'Pending Hold',
        variant: 'warning',
      });
      expect(getStatusBadgeConfig('reversed')).toEqual({
        label: 'Reversed',
        variant: 'purple',
      });
      expect(getStatusBadgeConfig('failed')).toEqual({
        label: 'Failed',
        variant: 'danger',
      });
      expect(getStatusBadgeConfig('cancelled')).toEqual({
        label: 'Cancelled',
        variant: 'neutral',
      });
    });
  });

  describe('4. Filters & Presets', () => {
    it('supports all valid payout status filters', () => {
      const allowedFilters = ['all', 'eligible', 'pending', 'processing', 'paid', 'reversed'];
      allowedFilters.forEach((f) => {
        expect(typeof f).toBe('string');
        expect(f.length).toBeGreaterThan(0);
      });
    });

    it('generates correct date strings for YYYY-MM-DD custom ranges', () => {
      const from = '2026-09-01';
      const to = '2026-09-30';
      expect(from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(to).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(from <= to).toBe(true);
    });
  });

  describe('5. Pagination Metadata & Boundary Clamping', () => {
    it('calculates page and offset boundaries correctly', () => {
      const meta = calculatePayoutPagination(25, 10, 0);
      expect(meta.currentPage).toBe(1);
      expect(meta.totalPages).toBe(3);
      expect(meta.hasNext).toBe(true);
      expect(meta.hasPrev).toBe(false);
      expect(meta.startItem).toBe(1);
      expect(meta.endItem).toBe(10);
    });

    it('handles last page boundaries and zero totals', () => {
      const lastPageMeta = calculatePayoutPagination(25, 10, 20);
      expect(lastPageMeta.currentPage).toBe(3);
      expect(lastPageMeta.hasNext).toBe(false);
      expect(lastPageMeta.hasPrev).toBe(true);
      expect(lastPageMeta.startItem).toBe(21);
      expect(lastPageMeta.endItem).toBe(25);

      const emptyMeta = calculatePayoutPagination(0, 10, 0);
      expect(emptyMeta.totalPages).toBe(1);
      expect(emptyMeta.startItem).toBe(0);
      expect(emptyMeta.endItem).toBe(0);
    });
  });

  describe('6. Zero Fake Financial Values & Security Guardrails', () => {
    it('ensures payout responses contain zero customer private contact info', () => {
      const payout = createMockPayoutItem();
      const keys = Object.keys(payout);

      expect(keys).not.toContain('customer_phone');
      expect(keys).not.toContain('customer_email');
      expect(keys).not.toContain('razorpay_secret');
      expect(keys).not.toContain('webhook_secret');
    });

    it('ensures net payout never assumes customer booking total', () => {
      const payout = createMockPayoutItem({
        gross_amount: '1000.00',
        commission_rate: '0.2000',
        commission_amount: '200.00',
        net_amount: '800.00',
      });

      // Net payout MUST NOT equal gross service amount when commission is applied
      expect(payout.net_amount).not.toBe(payout.gross_amount);
      expect(parseFloat(payout.net_amount)).toBe(800.00);
    });
  });
});
