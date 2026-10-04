import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 4: Mechanic End-to-End Operational Lifecycle Flow', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.mechanic);

    // Mock Mechanic Dashboard Overview
    await page.route('**/api/v1/mechanics/dashboard/overview*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          mechanic_id: MOCK_USERS.mechanic.id,
          total_completed_jobs: 48,
          active_jobs: 1,
          today_earnings: 2450.0,
          pending_payout_amount: 5120.0,
          average_rating: 4.9,
          review_count: 36,
          is_available: true,
        }),
      });
    });

    // Mock Mechanic Performance
    await page.route('**/api/v1/mechanics/dashboard/performance*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          period_days: 30,
          acceptance_rate: 0.94,
          average_response_time_seconds: 14.5,
          on_time_arrival_rate: 0.96,
          rework_rate: 0.02,
          rating_distribution: { '5': 32, '4': 4, '3': 0, '2': 0, '1': 0 },
        }),
      });
    });

    // Mock Mechanic Earnings
    await page.route('**/api/v1/mechanics/dashboard/earnings*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0, total_earned: 2450.0 }),
      });
    });

    // Mock Incoming Job Offer
    await page.route('**/api/v1/mechanics/pending-offer*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          assignment_id: 'assign-777',
          booking_id: 'bk-777',
          booking_number: 'BK-7770',
          service_name: 'Brake Disc Replacement & Fluid Flush',
          customer_area: 'Indiranagar 100ft Road',
          distance_km: 2.4,
          estimated_payout: 850.0,
          expires_at: new Date(Date.now() + 55000).toISOString(),
          vehicle_summary: '2022 Honda City (KA-01-MJ-5501)',
        }),
      });
    });

    // Mock Upcoming Scheduled Jobs (Phase 13)
    await page.route('**/api/v1/mechanics/scheduled-jobs*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: 'sched-101',
            booking_number: 'BK-8820',
            booking_status: 'mechanic_assigned',
            scheduled_at: new Date(Date.now() + 7200000).toISOString(),
            total_amount: 1850.0,
            address: '77 Residency Road, Bangalore',
          },
        ]),
      });
    });

    // Mock Recent Jobs
    await page.route('**/api/v1/mechanics/dashboard/recent-jobs*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              assignment_id: 'asgn-prev-1',
              booking_id: 'bk-prev-1',
              booking_number: 'BK-501',
              service_name: 'Engine Oil & Filter Service',
              booking_status: 'service_in_progress',
              customer_name: 'Ravi Kumar',
              customer_phone: '+919876543210',
              address: '15 Koramangala 4th Block',
              scheduled_at: new Date().toISOString(),
              total_amount: 1299.0,
              payment_status: 'pending',
              can_record_arrival: false,
              has_active_inspection: true,
            },
          ],
          total: 1,
        }),
      });
    });

    // Mock Recent Reviews
    await page.route('**/api/v1/mechanics/dashboard/recent-reviews*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      });
    });

    // Mock Accept Offer endpoint
    await page.route('**/api/v1/matching/assignments/*/accept', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'accepted' }),
      });
    });
  });

  test('mechanic dashboard renders operational KPIs and rating badges', async ({ page }) => {
    await page.goto('/mechanic/dashboard');

    await expect(page.locator('h1')).toContainText('Mechanic Dashboard');
    await expect(page.locator('text=Available')).toBeVisible();
    await expect(page.getByText('4.9').first()).toBeVisible();
    await expect(page.getByText('36 reviews').first()).toBeVisible();
  });

  test('mechanic receives and reviews real-time incoming job offer countdown', async ({ page }) => {
    await page.goto('/mechanic/dashboard');

    // Verify incoming job offer card
    await expect(page.locator('text=New Job Offer')).toBeVisible();
    await expect(page.locator('text=Brake Disc Replacement & Fluid Flush')).toBeVisible();
    await expect(page.locator('text=2.4 km away')).toBeVisible();

    // Verify Accept and Decline buttons are present
    const acceptBtn = page.getByTestId('accept-offer-button');
    const declineBtn = page.getByTestId('decline-offer-button');
    await expect(acceptBtn).toBeVisible();
    await expect(declineBtn).toBeVisible();
  });

  test('mechanic views upcoming scheduled appointments with tool prep checklists', async ({ page }) => {
    await page.goto('/mechanic/dashboard');

    // Verify Upcoming Scheduled Appointments Section
    await expect(page.locator('text=Upcoming Scheduled Appointments')).toBeVisible();
    await expect(page.locator('text=BK-8820')).toBeVisible();
    await expect(page.locator('text=77 Residency Road, Bangalore')).toBeVisible();
    await expect(page.locator('text=Prep: Inspect toolkit & diagnostic OBD scanner')).toBeVisible();
  });
});
