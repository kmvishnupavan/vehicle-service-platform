import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 15: Controlled Failure Injection & Graceful Recovery E2E', () => {
  test('gracefully displays retry banner when backend API fails with 500 error', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);

    // Inject 500 internal server error on bookings API
    await page.route('**/api/v1/bookings/my-bookings*', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Database connection temporarily unavailable' }),
      });
    });

    await page.goto('/dashboard');

    // Verify graceful error card is displayed with Retry button
    await expect(page.locator('text=Failed to load bookings')).toBeVisible();
    await expect(page.locator('button:has-text("Retry")')).toBeVisible();
  });

  test('mechanic dashboard displays recovery banner when telemetry metrics fail', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.mechanic);

    // Inject 503 error on overview
    await page.route('**/api/v1/mechanics/me/dashboard/overview', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Service Unavailable' }),
      });
    });

    await page.goto('/mechanic/dashboard');

    // Verify recovery alert banner is displayed
    await expect(page.locator('text=Failed to load authoritative dashboard data')).toBeVisible();
    await expect(page.locator('button:has-text("Retry Connection")')).toBeVisible();
  });
});
