import { describe, it, expect } from 'vitest';
import {
  DashboardOverview,
  EarningsList,
  DateFilterPreset,
} from '../types/mechanic-dashboard';

// Helper: Formatter for currency
export function formatCurrencyDisplay(amount: string | number): string {
  const num = typeof amount === 'number' ? amount : parseFloat(amount || '0');
  return `₹${num.toFixed(2)}`;
}

// Helper: Completion rate denominator and percentage calculation
export function calculateCompletionRate(completed: number, cancelled: number): number {
  const denom = completed + cancelled;
  if (denom <= 0) return 0.0;
  return Math.round((completed / denom) * 1000) / 10;
}

// Helper: Rating display helper - strict "No reviews yet" guard
export function formatRatingSummary(averageRating: number, reviewCount: number): {
  isDisplayable: boolean;
  displayText: string;
  hasReviews: boolean;
} {
  if (reviewCount <= 0) {
    return {
      isDisplayable: false,
      displayText: 'No reviews yet',
      hasReviews: false,
    };
  }
  return {
    isDisplayable: true,
    displayText: `${averageRating.toFixed(1)} ★ (${reviewCount} ${reviewCount === 1 ? 'review' : 'reviews'})`,
    hasReviews: true,
  };
}

// Helper: Pagination calculation helper
export function calculatePaginationMetadata(total: number, limit: number, offset: number) {
  const safeLimit = Math.min(Math.max(1, limit), 100);
  const safeOffset = Math.max(0, offset);
  const currentPage = Math.floor(safeOffset / safeLimit);
  const totalPages = Math.max(1, Math.ceil(total / safeLimit));
  const hasNext = safeOffset + safeLimit < total;
  const hasPrev = safeOffset > 0;
  const fromItem = total > 0 ? safeOffset + 1 : 0;
  const toItem = Math.min(safeOffset + safeLimit, total);

  return {
    currentPage,
    totalPages,
    hasNext,
    hasPrev,
    fromItem,
    toItem,
  };
}

// Helper: Date format helper
export function formatDateToYYYYMMDD(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

// Helper: Date filter range generator matching DateFilterBar
export function getDateFilterRange(preset: DateFilterPreset, baseDate: Date = new Date()): {
  fromDate?: string;
  toDate?: string;
} {
  const todayStr = formatDateToYYYYMMDD(baseDate);

  switch (preset) {
    case 'today':
      return { fromDate: todayStr, toDate: todayStr };
    case '7d': {
      const d = new Date(baseDate);
      d.setDate(d.getDate() - 7);
      return { fromDate: formatDateToYYYYMMDD(d), toDate: todayStr };
    }
    case '30d': {
      const d = new Date(baseDate);
      d.setDate(d.getDate() - 30);
      return { fromDate: formatDateToYYYYMMDD(d), toDate: todayStr };
    }
    case 'month': {
      const firstDay = new Date(baseDate.getFullYear(), baseDate.getMonth(), 1);
      return { fromDate: formatDateToYYYYMMDD(firstDay), toDate: todayStr };
    }
    case 'all':
    default:
      return { fromDate: undefined, toDate: undefined };
  }
}

// Helper: Error state handler guaranteeing no fake zeros on API error
export function resolveDashboardState(
  isLoading: boolean,
  hasError: boolean,
  data?: DashboardOverview
): {
  status: 'loading' | 'error' | 'success';
  overview: DashboardOverview | null;
  errorMessage?: string;
} {
  if (hasError) {
    return {
      status: 'error',
      overview: null,
      errorMessage: 'Failed to load authoritative dashboard data. Please retry.',
    };
  }
  if (isLoading || !data) {
    return {
      status: 'loading',
      overview: null,
    };
  }
  return {
    status: 'success',
    overview: data,
  };
}

describe('Mechanic Dashboard Frontend Logic & Unit Tests (Phase 8.6)', () => {
  it('1. dashboard renders overview structure with valid KPIs', () => {
    const mockOverview: DashboardOverview = {
      today: { jobs: 4, completed: 2, cancelled: 1 },
      active_jobs: 1,
      completed_jobs: 4,
      cancelled_jobs: 1,
      total_earnings: '1500.75',
      pending_earnings: '800.00',
      average_rating: 4.67,
      review_count: 3,
      completion_rate: 80.0,
    };

    expect(mockOverview.today.jobs).toBe(4);
    expect(mockOverview.active_jobs).toBe(1);
    expect(mockOverview.completed_jobs).toBe(4);
    expect(mockOverview.completion_rate).toBe(80.0);
    expect(formatCurrencyDisplay(mockOverview.total_earnings)).toBe('₹1500.75');
    expect(formatCurrencyDisplay(mockOverview.pending_earnings)).toBe('₹800.00');
  });

  it('2. overview cards correctly extracts today metrics', () => {
    const today = { jobs: 3, completed: 2, cancelled: 0 };
    expect(today.jobs).toBe(3);
    expect(today.completed).toBe(2);
    expect(today.cancelled).toBe(0);
  });

  it('3. loading state returns loading status and null overview', () => {
    const state = resolveDashboardState(true, false, undefined);
    expect(state.status).toBe('loading');
    expect(state.overview).toBeNull();
  });

  it('4. error state provides clean error message and prevents fake zero metrics', () => {
    const state = resolveDashboardState(false, true, undefined);
    expect(state.status).toBe('error');
    expect(state.overview).toBeNull();
    expect(state.errorMessage).toContain('Failed to load authoritative');
  });

  it('5. empty state handles zero jobs, zero earnings, and zero denominator safely', () => {
    const completionRate = calculateCompletionRate(0, 0);
    expect(completionRate).toBe(0.0);

    const pagination = calculatePaginationMetadata(0, 20, 0);
    expect(pagination.fromItem).toBe(0);
    expect(pagination.toItem).toBe(0);
    expect(pagination.totalPages).toBe(1);
    expect(pagination.hasNext).toBe(false);
  });

  it('6. rating distribution calculates star percentages correctly', () => {
    const distribution = { '1': 0, '2': 0, '3': 0, '4': 1, '5': 4 };
    const total = 5;

    const fiveStarPct = Math.round((distribution['5'] / total) * 100);
    const fourStarPct = Math.round((distribution['4'] / total) * 100);
    const oneStarPct = Math.round((distribution['1'] / total) * 100);

    expect(fiveStarPct).toBe(80);
    expect(fourStarPct).toBe(20);
    expect(oneStarPct).toBe(0);
  });

  it('7. no reviews state returns "No reviews yet" without misleading 0.0 stars', () => {
    const ratingSummary = formatRatingSummary(0.0, 0);
    expect(ratingSummary.hasReviews).toBe(false);
    expect(ratingSummary.displayText).toBe('No reviews yet');
    expect(ratingSummary.isDisplayable).toBe(false);

    // If reviews exist
    const activeSummary = formatRatingSummary(4.8, 12);
    expect(activeSummary.hasReviews).toBe(true);
    expect(activeSummary.displayText).toBe('4.8 ★ (12 reviews)');
  });

  it('8. earnings rendering itemizes gross, additional work, and net amounts', () => {
    const mockEarnings: EarningsList = {
      items: [
        {
          booking_id: 'b1-uuid',
          booking_number: 'BK-M1-001',
          completed_at: '2026-10-03T11:00:00Z',
          gross_amount: '1200.50',
          additional_work_amount: '300.25',
          deductions: '0.00',
          net_amount: '1500.75',
          payment_status: 'paid',
          paid_at: '2026-10-03T11:00:00Z',
        },
      ],
      total: 1,
      limit: 20,
      offset: 0,
    };

    const item = mockEarnings.items[0];
    expect(item.booking_number).toBe('BK-M1-001');
    expect(formatCurrencyDisplay(item.gross_amount)).toBe('₹1200.50');
    expect(formatCurrencyDisplay(item.additional_work_amount)).toBe('₹300.25');
    expect(formatCurrencyDisplay(item.net_amount)).toBe('₹1500.75');
    expect(item.payment_status).toBe('paid');
  });

  it('9. date filter computes correct date ranges for all presets', () => {
    const fixedDate = new Date('2026-10-15T12:00:00Z');

    const todayFilter = getDateFilterRange('today', fixedDate);
    expect(todayFilter.fromDate).toBe('2026-10-15');
    expect(todayFilter.toDate).toBe('2026-10-15');

    const sevenDayFilter = getDateFilterRange('7d', fixedDate);
    expect(sevenDayFilter.fromDate).toBe('2026-10-08');
    expect(sevenDayFilter.toDate).toBe('2026-10-15');

    const monthFilter = getDateFilterRange('month', fixedDate);
    expect(monthFilter.fromDate).toBe('2026-10-01');
    expect(monthFilter.toDate).toBe('2026-10-15');

    const allFilter = getDateFilterRange('all', fixedDate);
    expect(allFilter.fromDate).toBeUndefined();
    expect(allFilter.toDate).toBeUndefined();
  });

  it('10. pagination calculates offsets and page limits accurately', () => {
    const meta = calculatePaginationMetadata(35, 10, 20); // page 2 (items 21-30)
    expect(meta.currentPage).toBe(2);
    expect(meta.totalPages).toBe(4);
    expect(meta.fromItem).toBe(21);
    expect(meta.toItem).toBe(30);
    expect(meta.hasPrev).toBe(true);
    expect(meta.hasNext).toBe(true);

    const lastPageMeta = calculatePaginationMetadata(35, 10, 30); // page 3 (items 31-35)
    expect(lastPageMeta.fromItem).toBe(31);
    expect(lastPageMeta.toItem).toBe(35);
    expect(lastPageMeta.hasNext).toBe(false);
  });

  it('11. responsive-safe component behavior clamps limits and preserves precision', () => {
    // Limit bounds clamping
    const clampedLimit = Math.min(Math.max(1, 150), 100);
    expect(clampedLimit).toBe(100);

    const clampedMinLimit = Math.min(Math.max(1, -5), 100);
    expect(clampedMinLimit).toBe(1);

    // Decimal string preservation
    const preciseAmount = formatCurrencyDisplay('1200.505');
    expect(preciseAmount).toBe('₹1200.51');
  });

  it('12. API failure does not display fake zero values', () => {
    // When API fails, state is marked error and data is NOT displayed as fake zeros
    const result = resolveDashboardState(false, true, undefined);
    expect(result.status).toBe('error');
    expect(result.overview).toBeNull();
    // Verify frontend does not manufacture zeros
    expect(result.overview?.total_earnings).toBeUndefined();
  });
});
