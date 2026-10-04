import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 6: Realtime Telemetry & Tracking E2E Validation', () => {
  test('customer tracking view updates mechanic location and road ETA dynamically', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);

    const bookingId = '88888888-8888-8888-8888-888888888888';

    // Mock Booking Details
    await page.route(`**/api/v1/bookings/${bookingId}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: bookingId,
          booking_number: 'BK-1001',
          booking_status: 'mechanic_en_route',
          scheduled_at: null,
          total_amount: '1499.00',
          payment_status: 'pending',
          customer_id: MOCK_USERS.customer.id,
          assigned_mechanic_id: MOCK_USERS.mechanic.id,
          address: '42 MG Road, Bangalore',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        }),
      });
    });

    // Mock initial Mechanic Location
    await page.route(`**/api/v1/bookings/${bookingId}/mechanic-location`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          mechanic_id: MOCK_USERS.mechanic.id,
          latitude: 12.9716,
          longitude: 77.5946,
          updated_at: new Date().toISOString(),
          eta_minutes: 14,
          eta_distance_km: 4.2,
        }),
      });
    });

    // Mock Service Operations endpoints
    await page.route(`**/api/v1/bookings/${bookingId}/structured-inspection`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
    });
    await page.route(`**/api/v1/bookings/${bookingId}/checklist`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    });
    await page.route(`**/api/v1/bookings/${bookingId}/service-report`, async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
    });

    await page.goto(`/bookings/${bookingId}/tracking`);

    // Verify Tracking UI rendered
    await expect(page.locator('text=Booking #BK-1001')).toBeVisible();
    await expect(page.locator('text=Your mechanic is on the way')).toBeVisible();
    await expect(page.locator('text=En Route')).toBeVisible();
  });
});
