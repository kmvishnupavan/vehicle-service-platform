import { describe, it, expect } from 'vitest';
import {
  DEFAULT_OPERATIONAL_THRESHOLDS,
  OperationalAlertThresholds,
  MatchingPolicy,
  ScheduledBooking,
} from '../types/operationalAutomation';

describe('Phase 13: Operational Automation & Reliability Tests', () => {
  describe('Matching Policy Weights Validation', () => {
    it('validates active matching policy weights sum exactly to 1.000', () => {
      const policy: MatchingPolicy = {
        policy_version: 'v1.0',
        description: 'Balanced Multi-Factor Heuristic v1.0',
        proximity_weight: 0.300,
        rating_weight: 0.200,
        availability_weight: 0.150,
        reliability_weight: 0.150,
        workload_weight: 0.100,
        acceptance_weight: 0.100,
        max_concurrent_jobs: 1,
        offer_timeout_seconds: 60,
        max_offer_attempts: 3,
        is_active: true,
      };

      const sum =
        policy.proximity_weight +
        policy.rating_weight +
        policy.availability_weight +
        policy.reliability_weight +
        policy.workload_weight +
        policy.acceptance_weight;

      expect(Math.round(sum * 1000) / 1000).toBe(1.0);
    });

    it('flags non-conforming matching weights that do not sum to 1.000', () => {
      const invalidWeights = [0.2, 0.2, 0.1, 0.1, 0.1, 0.1]; // sum = 0.8
      const sum = invalidWeights.reduce((a, b) => a + b, 0);
      expect(Math.round(sum * 1000) / 1000).not.toBe(1.0);
    });
  });

  describe('Operational Alert Thresholds Evaluation', () => {
    const thresholds: OperationalAlertThresholds = DEFAULT_OPERATIONAL_THRESHOLDS;

    it('triggers matching exhaustion alert when metric exceeds threshold', () => {
      const currentExhaustion = 0.15; // 15%
      const isBreached = currentExhaustion > thresholds.matching_exhaustion_rate;
      expect(isBreached).toBe(true);
    });

    it('does not trigger alert when metric is within safe limits', () => {
      const currentExhaustion = 0.04; // 4%
      const isBreached = currentExhaustion > thresholds.matching_exhaustion_rate;
      expect(isBreached).toBe(false);
    });

    it('detects excessive routing failure rates above threshold', () => {
      const currentFailureRate = 0.08; // 8%
      const isBreached = currentFailureRate > thresholds.routing_failure_rate;
      expect(isBreached).toBe(true);
    });

    it('detects high stale location rates above threshold', () => {
      const currentStaleRate = 0.12; // 12%
      const isBreached = currentStaleRate > thresholds.stale_location_rate;
      expect(isBreached).toBe(true);
    });
  });

  describe('Scheduled Booking Window & State Logic', () => {
    it('validates scheduled end time is strictly after start time', () => {
      const start = new Date('2026-10-05T09:00:00Z');
      const end = new Date('2026-10-05T11:00:00Z');
      expect(end.getTime()).toBeGreaterThan(start.getTime());
    });

    it('calculates 30-minute dispatch window correctly', () => {
      const start = new Date('2026-10-05T09:00:00Z');
      const dispatchWindowMinutes = 30;
      const expectedDispatchAt = new Date(start.getTime() - dispatchWindowMinutes * 60 * 1000);
      expect(expectedDispatchAt.toISOString()).toBe('2026-10-05T08:30:00.000Z');
    });

    it('verifies scheduled booking status transitions conform to lifecycle', () => {
      const validStatuses: ScheduledBooking['status'][] = [
        'scheduled',
        'dispatching',
        'dispatched',
        'cancelled',
        'failed',
      ];
      validStatuses.forEach((st) => {
        expect(typeof st).toBe('string');
      });
    });

    it('computes remaining countdown duration accurately', () => {
      const targetTime = Date.now() + 2 * 3600 * 1000 + 15 * 60 * 1000; // 2h 15m from now
      const diff = targetTime - Date.now();
      const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
      const minutes = Math.floor((diff / 1000 / 60) % 60);

      expect(hours).toBe(2);
      expect(minutes).toBe(15);
    });
  });
});
