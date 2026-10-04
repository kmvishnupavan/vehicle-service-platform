import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 5: Admin Operations & Reliability Center E2E Flow', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.admin);

    // Mock Operations Stats
    await page.route('**/api/v1/admin/operations/stats', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          environment: 'staging',
          system_health: {
            status: 'ready',
            environment: 'staging',
            checks: { database: 'connected', api: 'healthy', realtime: 'connected' },
            timestamp: new Date().toISOString(),
          },
          safety_guard: {
            environment: 'staging',
            live_payouts_enabled: false,
            payout_mode: 'sandbox',
            safety_barrier_active: true,
            real_money_movement: 'REAL-MONEY PAYOUTS: DISABLED',
          },
          bookings_breakdown: { in_service: 4, assigned: 2, completed: 86, cancelled: 3 },
          payments_breakdown: { captured: 84, pending: 2, failed: 1, refunded: 0 },
          payouts_breakdown: { paid: 80, processing: 4, approval_required: 0, eligible: 6 },
          webhooks_breakdown: { processed: 142, processing: 0, failed: 0 },
          notifications_breakdown: { sent: 230 },
          timestamp: new Date().toISOString(),
        }),
      });
    });

    // Mock Background Jobs History
    await page.route('**/api/v1/admin/background-jobs/history*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'job-exec-1',
            job_name: 'expire_mechanic_offers',
            execution_id: 'exec-101-alpha',
            started_at: new Date(Date.now() - 60000).toISOString(),
            completed_at: new Date(Date.now() - 58000).toISOString(),
            status: 'completed',
            records_processed: 2,
            records_succeeded: 2,
            records_failed: 0,
            metadata: {},
            created_at: new Date().toISOString(),
          },
          {
            id: 'job-exec-2',
            job_name: 'dispatch_scheduled_bookings',
            execution_id: 'exec-102-beta',
            started_at: new Date(Date.now() - 120000).toISOString(),
            completed_at: new Date(Date.now() - 119000).toISOString(),
            status: 'completed',
            records_processed: 1,
            records_succeeded: 1,
            records_failed: 0,
            metadata: {},
            created_at: new Date().toISOString(),
          },
        ]),
      });
    });

    // Mock Operational Metrics
    await page.route('**/api/v1/admin/operational-metrics', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          snapshot_time: new Date().toISOString(),
          metrics: {
            booking_count: 95,
            active_bookings: 6,
            matching_sessions_total: 42,
            average_time_to_match_seconds: 36.4,
            matching_exhaustion_rate: 0.04,
            offer_acceptance_rate: 0.92,
            offer_expiration_rate: 0.08,
            average_eta_minutes: 15.8,
            routing_failure_rate: 0.01,
            routing_fallback_rate: 0.02,
            stale_location_rate: 0.03,
            location_anomaly_count: 0,
            scheduled_booking_count: 8,
            scheduled_dispatch_failure_rate: 0.0,
            inspection_approval_rate: 0.96,
            service_completion_rate: 0.91,
            payment_success_rate: 0.99,
            payment_pending_count: 2,
            dispute_rate: 0.01,
            notification_failure_rate: 0.005,
          },
        }),
      });
    });

    // Mock Matching Policies
    await page.route('**/api/v1/admin/matching-policies', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            policy_version: 'v1.0',
            description: 'Balanced Multi-Factor Production Heuristic',
            proximity_weight: 0.3,
            rating_weight: 0.2,
            availability_weight: 0.15,
            reliability_weight: 0.15,
            workload_weight: 0.1,
            acceptance_weight: 0.1,
            max_concurrent_jobs: 1,
            offer_timeout_seconds: 60,
            max_offer_attempts: 3,
            is_active: true,
          },
        ]),
      });
    });
  });

  test('admin views System Operations Center with real-money safety barrier', async ({ page }) => {
    await page.goto('/admin/operations');

    await expect(page.locator('h1')).toContainText('Operations & Reliability Center');
    await expect(page.locator('text=REAL-MONEY PAYOUTS: DISABLED')).toBeVisible();
    await expect(page.locator('text=System Readiness: READY')).toBeVisible();
  });

  test('admin views background job runner history and verifies executed jobs', async ({ page }) => {
    await page.goto('/admin/operations');

    // Verify background jobs section
    await expect(page.locator('text=Automated Background Job Runner')).toBeVisible();
    await expect(page.locator('text=expire_mechanic_offers')).toBeVisible();
    await expect(page.locator('text=dispatch_scheduled_bookings')).toBeVisible();
    await expect(page.locator('text=Trigger All Jobs Now')).toBeVisible();
  });

  test('admin navigates between operational tabs and inspects matching policies', async ({ page }) => {
    await page.goto('/admin/operations');

    // Click on Matching Policies Tab
    await page.click('button:has-text("Matching Policies")');

    // Verify Matching Policies table rendered
    await expect(page.locator('text=Versioned Matching Policies')).toBeVisible();
    await expect(page.locator('text=v1.0')).toBeVisible();
    await expect(page.locator('text=ACTIVE')).toBeVisible();
    await expect(page.locator('text=30%')).toBeVisible(); // Proximity weight
  });
});
