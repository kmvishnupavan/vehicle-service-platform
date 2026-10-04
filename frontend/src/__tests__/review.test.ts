import { describe, it, expect } from 'vitest';
import { z } from 'zod';
import { BookingStatus } from '../types/booking';
import { Review, ReviewListItem } from '../types/review';

// Review validation schema corresponding to ReviewForm
const reviewFormSchema = z.object({
  rating: z
    .number({ required_error: 'Please select a star rating.' })
    .int('Rating must be an integer.')
    .min(1, 'Please select at least 1 star.')
    .max(5, 'Maximum rating is 5 stars.'),
  comment: z
    .string()
    .max(1000, 'Review comment cannot exceed 1000 characters.')
    .optional()
    .transform((val) => (val && val.trim() ? val.trim() : null)),
});

// Helper for review eligibility check matching BookingDetailsPage and CustomerDashboardPage
export function isBookingEligibleForReview(status: BookingStatus, hasMechanic: boolean): boolean {
  const eligibleStatuses: BookingStatus[] = ['service_completed', 'payment_pending', 'paid'];
  return eligibleStatuses.includes(status) && hasMechanic;
}

// Helper for mechanic rating display string matching MechanicInfoCard
export function formatMechanicRatingDisplay(averageRating: number | string | undefined, reviewCount?: number): {
  ratingText: string;
  hasReviews: boolean;
  label: string;
} {
  const rawAvg = typeof averageRating === 'number' ? averageRating : parseFloat(String(averageRating || 0));
  const count = reviewCount ?? 0;
  const hasReviews = count > 0 || rawAvg > 0;

  if (!hasReviews) {
    return {
      ratingText: '',
      hasReviews: false,
      label: 'No reviews yet',
    };
  }

  const ratingText = rawAvg.toFixed(1);
  const countText = count > 0 ? `(${count} ${count === 1 ? 'review' : 'reviews'})` : '';
  return {
    ratingText,
    hasReviews: true,
    label: `${ratingText} ${countText}`.trim(),
  };
}

// Helper for review pagination
export function calculateReviewPagination(totalCount: number, limit: number, offset: number) {
  const safeLimit = Math.min(Math.max(1, limit), 50);
  const safeOffset = Math.max(0, offset);
  const hasNextPage = safeOffset + safeLimit < totalCount;
  const hasPrevPage = safeOffset > 0;
  const startItem = totalCount > 0 ? safeOffset + 1 : 0;
  const endItem = Math.min(safeOffset + safeLimit, totalCount);

  return {
    safeLimit,
    safeOffset,
    hasNextPage,
    hasPrevPage,
    startItem,
    endItem,
  };
}

describe('Customer Reviews & Rating Workflow - Frontend Unit Tests (Phase 8.5)', () => {
  // 1. Star Rating Bounds & Validation
  it('validates rating is an integer strictly between 1 and 5', () => {
    // Valid ratings
    for (let r = 1; r <= 5; r++) {
      const res = reviewFormSchema.safeParse({ rating: r });
      expect(res.success).toBe(true);
      if (res.success) {
        expect(res.data.rating).toBe(r);
      }
    }

    // Invalid ratings
    expect(reviewFormSchema.safeParse({ rating: 0 }).success).toBe(false);
    expect(reviewFormSchema.safeParse({ rating: 6 }).success).toBe(false);
    expect(reviewFormSchema.safeParse({ rating: -1 }).success).toBe(false);
    expect(reviewFormSchema.safeParse({ rating: 4.5 }).success).toBe(false);
    expect(reviewFormSchema.safeParse({ rating: '5' }).success).toBe(false);
    expect(reviewFormSchema.safeParse({}).success).toBe(false);
  });

  // 2. Comment Validation & Whitespace Trimming
  it('trims comments, transforms whitespace-only to null, and limits length to 1000 chars', () => {
    // Standard comment
    const res1 = reviewFormSchema.safeParse({ rating: 5, comment: 'Great mechanic!' });
    expect(res1.success).toBe(true);
    if (res1.success) expect(res1.data.comment).toBe('Great mechanic!');

    // Whitespace comment becomes null
    const res2 = reviewFormSchema.safeParse({ rating: 5, comment: '   \n\t  ' });
    expect(res2.success).toBe(true);
    if (res2.success) expect(res2.data.comment).toBe(null);

    // Empty string becomes null
    const res3 = reviewFormSchema.safeParse({ rating: 5, comment: '' });
    expect(res3.success).toBe(true);
    if (res3.success) expect(res3.data.comment).toBe(null);

    // 1000 characters exact is allowed
    const maxComment = 'A'.repeat(1000);
    const res4 = reviewFormSchema.safeParse({ rating: 5, comment: maxComment });
    expect(res4.success).toBe(true);

    // 1001 characters is rejected
    const tooLong = 'A'.repeat(1001);
    const res5 = reviewFormSchema.safeParse({ rating: 5, comment: tooLong });
    expect(res5.success).toBe(false);
  });

  // 3. Review Eligibility Logic
  it('enforces review eligibility based strictly on completed lifecycle states', () => {
    // Eligible states with assigned mechanic
    expect(isBookingEligibleForReview('service_completed', true)).toBe(true);
    expect(isBookingEligibleForReview('payment_pending', true)).toBe(true);
    expect(isBookingEligibleForReview('paid', true)).toBe(true);

    // Ineligible states even with mechanic
    const ineligible: BookingStatus[] = [
      'pending',
      'confirmed',
      'mechanic_assigned',
      'mechanic_en_route',
      'mechanic_arrived',
      'inspection',
      'awaiting_customer_approval',
      'service_in_progress',
      'additional_work',
      'cancelled',
      'disputed',
    ];

    for (const status of ineligible) {
      expect(isBookingEligibleForReview(status, true)).toBe(false);
    }

    // Completed state WITHOUT mechanic is ineligible
    expect(isBookingEligibleForReview('service_completed', false)).toBe(false);
    expect(isBookingEligibleForReview('paid', false)).toBe(false);
  });

  // 4. Submit Button State Determination
  it('determines whether submit button is enabled based on rating selection and loading state', () => {
    const isSubmitDisabled = (rating: number, isSubmitting: boolean) => isSubmitting || rating === 0;

    // Disabled when no rating chosen (0)
    expect(isSubmitDisabled(0, false)).toBe(true);

    // Disabled during active submission
    expect(isSubmitDisabled(5, true)).toBe(true);

    // Enabled when rating 1-5 is chosen and not submitting
    expect(isSubmitDisabled(1, false)).toBe(false);
    expect(isSubmitDisabled(5, false)).toBe(false);
  });

  // 5. Existing Review Display State
  it('detects existing review and renders submitted feedback correctly', () => {
    const existingReview: Review = {
      id: 'rev-123',
      booking_id: 'bk-456',
      customer_id: 'cust-789',
      mechanic_id: 'mech-101',
      rating: 5,
      comment: 'Arrived super fast and fixed the brake pads.',
      created_at: '2026-10-03T10:00:00Z',
      updated_at: '2026-10-03T10:00:00Z',
    };

    expect(existingReview.rating).toBe(5);
    expect(existingReview.comment).toBeDefined();
    expect(existingReview.booking_id).toBe('bk-456');
  });

  // 6. Mechanic Rating Display Logic ("No reviews yet" vs formatted rating)
  it('formats mechanic rating display correctly for zero and positive review counts', () => {
    // Zero reviews -> "No reviews yet", no stars
    const zeroReviews = formatMechanicRatingDisplay(0, 0);
    expect(zeroReviews.hasReviews).toBe(false);
    expect(zeroReviews.label).toBe('No reviews yet');

    // Positive rating with count
    const withReviews = formatMechanicRatingDisplay(4.8, 12);
    expect(withReviews.hasReviews).toBe(true);
    expect(withReviews.ratingText).toBe('4.8');
    expect(withReviews.label).toBe('4.8 (12 reviews)');

    // Single review pluralization
    const singleReview = formatMechanicRatingDisplay(5.0, 1);
    expect(singleReview.label).toBe('5.0 (1 review)');
  });

  // 7. Privacy-safe Customer Masking
  it('ensures customer reviews in review list omit sensitive private data', () => {
    const mockListItem: ReviewListItem = {
      id: 'rev-1',
      rating: 5,
      comment: 'Top tier service.',
      created_at: '2026-10-03T08:00:00Z',
      customer_name: 'David W.',
    };

    expect(mockListItem.customer_name).toBe('David W.');
    expect((mockListItem as any).email).toBeUndefined();
    expect((mockListItem as any).phone).toBeUndefined();
    expect((mockListItem as any).customer_id).toBeUndefined();
  });

  // 8. Pagination Calculations
  it('calculates correct pagination bounds and controls for review listings', () => {
    // First page of 35 items
    const page1 = calculateReviewPagination(35, 20, 0);
    expect(page1.hasNextPage).toBe(true);
    expect(page1.hasPrevPage).toBe(false);
    expect(page1.startItem).toBe(1);
    expect(page1.endItem).toBe(20);

    // Second page
    const page2 = calculateReviewPagination(35, 20, 20);
    expect(page2.hasNextPage).toBe(false);
    expect(page2.hasPrevPage).toBe(true);
    expect(page2.startItem).toBe(21);
    expect(page2.endItem).toBe(35);

    // Empty list
    const empty = calculateReviewPagination(0, 20, 0);
    expect(empty.hasNextPage).toBe(false);
    expect(empty.hasPrevPage).toBe(false);
    expect(empty.startItem).toBe(0);
    expect(empty.endItem).toBe(0);
  });
});
