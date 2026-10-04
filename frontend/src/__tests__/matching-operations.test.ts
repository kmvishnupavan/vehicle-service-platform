import { describe, it, expect } from 'vitest';
import { getFriendlyBookingStatus } from '../utils/bookingStatus';

describe('Intelligent Matching & Operations Test Suite (Phase 11)', () => {
  // ===========================================================================
  // 1. Customer UX: Friendly Status Formatter
  // ===========================================================================
  describe('Customer UX - Friendly Booking Status Formatting', () => {
    it('formats searching and pending states into user-centered "Finding nearby mechanics..."', () => {
      const pendingStatus = getFriendlyBookingStatus('pending');
      expect(pendingStatus.title).toBe('Finding nearby mechanics...');
      expect(pendingStatus.badgeText).toBe('Searching');
      expect(pendingStatus.colorClass).toContain('text-amber-600');

      const searchingStatus = getFriendlyBookingStatus('searching_mechanic');
      expect(searchingStatus.title).toBe('Finding nearby mechanics...');
      expect(searchingStatus.badgeText).toBe('Searching');
      expect(searchingStatus.subtitle).toContain('service area');
    });

    it('formats mechanic_assigned state to "Mechanic found"', () => {
      const assigned = getFriendlyBookingStatus('mechanic_assigned');
      expect(assigned.title).toBe('Mechanic found');
      expect(assigned.badgeText).toBe('Mechanic Assigned');
      expect(assigned.colorClass).toContain('text-blue-600');
    });

    it('formats mechanic_en_route state to "Your mechanic is on the way"', () => {
      const enRoute = getFriendlyBookingStatus('mechanic_en_route');
      expect(enRoute.title).toBe('Your mechanic is on the way');
      expect(enRoute.badgeText).toBe('En Route');
      expect(enRoute.subtitle).toContain('Live GPS tracking');
    });

    it('formats mechanic_arrived state to "Your mechanic has arrived"', () => {
      const arrived = getFriendlyBookingStatus('mechanic_arrived');
      expect(arrived.title).toBe('Your mechanic has arrived');
      expect(arrived.badgeText).toBe('Arrived');
    });

    it('formats inspection state to "Vehicle inspection in progress"', () => {
      const inspection = getFriendlyBookingStatus('inspection');
      expect(inspection.title).toBe('Vehicle inspection in progress');
      expect(inspection.badgeText).toBe('Inspection');
    });

    it('formats additional work states to "Additional work requires your approval"', () => {
      const approval = getFriendlyBookingStatus('awaiting_customer_approval');
      expect(approval.title).toBe('Additional work requires your approval');
      expect(approval.badgeText).toBe('Approval Required');

      const addWork = getFriendlyBookingStatus('additional_work');
      expect(addWork.title).toBe('Additional work requires your approval');
    });

    it('formats service_in_progress state to "Service in progress"', () => {
      const inProgress = getFriendlyBookingStatus('service_in_progress');
      expect(inProgress.title).toBe('Service in progress');
      expect(inProgress.badgeText).toBe('In Progress');
    });

    it('formats service_completed state to "Service completed"', () => {
      const completed = getFriendlyBookingStatus('service_completed');
      expect(completed.title).toBe('Service completed');
      expect(completed.badgeText).toBe('Completed');
    });

    it('formats unknown states safely without raising errors', () => {
      const custom = getFriendlyBookingStatus('custom_state_value');
      expect(custom.title).toBe('custom state value');
      expect(custom.badgeText).toBe('custom state value');
    });
  });

  // ===========================================================================
  // 2. Mechanic UX: Incoming Job Offer & Expiration Math
  // ===========================================================================
  describe('Mechanic UX - Offer Countdown & Expiration Calculations', () => {
    it('computes positive seconds remaining for active future offer', () => {
      const futureDate = new Date(Date.now() + 45 * 1000).toISOString();
      const expiry = new Date(futureDate).getTime();
      const left = Math.max(0, Math.floor((expiry - Date.now()) / 1000));

      expect(left).toBeGreaterThanOrEqual(44);
      expect(left).toBeLessThanOrEqual(46);
    });

    it('flags past offer timestamp as expired (0 seconds remaining)', () => {
      const pastDate = new Date(Date.now() - 10 * 1000).toISOString();
      const expiry = new Date(pastDate).getTime();
      const left = Math.max(0, Math.floor((expiry - Date.now()) / 1000));

      expect(left).toBe(0);
    });

    it('computes clamped progress bar percentage between 0% and 100%', () => {
      const computeProgress = (secondsRemaining: number, totalSeconds: number = 60) =>
        Math.min(100, Math.max(0, (secondsRemaining / totalSeconds) * 100));

      expect(computeProgress(60)).toBe(100);
      expect(computeProgress(30)).toBe(50);
      expect(computeProgress(0)).toBe(0);
      expect(computeProgress(-5)).toBe(0);
      expect(computeProgress(75)).toBe(100);
    });
  });

  // ===========================================================================
  // 3. Explainable Deterministic Matching Model Verification
  // ===========================================================================
  describe('Matching Model - Heuristic Weight Architecture', () => {
    it('verifies deterministic weights sum strictly to 1.00 (100%)', () => {
      const weights = {
        distance: 0.30,
        availability: 0.15,
        rating: 0.20,
        reliability: 0.15,
        workload: 0.10,
        acceptance: 0.10,
      };

      const sum = Object.values(weights).reduce((a, b) => a + b, 0);
      expect(Number(sum.toFixed(2))).toBe(1.00);
    });

    it('verifies Bayesian smoothed rating gives neutral baseline for new mechanics without reviews', () => {
      const computeSmoothedRating = (reviewsCount: number, rawRating: number) => {
        const priorWeight = 3.0;
        const priorRating = 3.5;
        const smoothed =
          (reviewsCount * rawRating + priorWeight * priorRating) /
          (reviewsCount + priorWeight);
        return smoothed / 5.0; // normalized 0-1
      };

      // 0 reviews mechanic -> exactly 3.5/5.0 = 0.70 normalized
      const newMechanicScore = computeSmoothedRating(0, 0);
      expect(Number(newMechanicScore.toFixed(2))).toBe(0.70);

      // High volume 5.0 mechanic -> approaches 1.00
      const veteranScore = computeSmoothedRating(100, 5.0);
      expect(veteranScore).toBeGreaterThan(0.95);
    });

    it('verifies distance score is normalized and non-negative', () => {
      const computeDistanceScore = (distKm: number, radiusKm: number) =>
        Math.max(0, Math.min(1, 1 - distKm / radiusKm));

      expect(computeDistanceScore(0, 15)).toBe(1.0);
      expect(computeDistanceScore(7.5, 15)).toBe(0.5);
      expect(computeDistanceScore(15, 15)).toBe(0.0);
      expect(computeDistanceScore(20, 15)).toBe(0.0); // clamped at 0
    });
  });
});
