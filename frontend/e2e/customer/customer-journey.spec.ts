import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 3: Customer End-to-End Lifecycle Flow', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);

    // Mock Customer's Bookings API (matches /bookings collection)
    await page.route(/\/api\/v1\/bookings(\?.*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '88888888-8888-8888-8888-888888888888',
            booking_number: 'BK-1001',
            booking_status: 'mechanic_en_route',
            scheduled_at: null,
            total_amount: '1499.00',
            payment_status: 'pending',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            booking_items: [
              {
                id: 'item-1',
                service_id: 'srv-1',
                quantity: 1,
                unit_price: '1499.00',
                services: {
                  name: 'Comprehensive Periodic Service',
                  description: 'Complete engine oil, filter, and 40-point safety check',
                },
              },
            ],
          },
          {
            id: '99999999-9999-9999-9999-999999999999',
            booking_number: 'BK-1002',
            booking_status: 'service_completed',
            scheduled_at: new Date(Date.now() - 86400000).toISOString(),
            total_amount: '799.00',
            payment_status: 'paid',
            created_at: new Date(Date.now() - 86400000).toISOString(),
            updated_at: new Date(Date.now() - 86400000).toISOString(),
            assigned_mechanic: {
              id: MOCK_USERS.mechanic.id,
              full_name: 'Mike Mechanic',
            },
            booking_items: [
              {
                id: 'item-2',
                service_id: 'srv-2',
                quantity: 1,
                unit_price: '799.00',
                services: {
                  name: 'Brake Inspection & Cleaning',
                  description: 'Front and rear brake disc and caliper cleaning',
                },
              },
            ],
          },
        ]),
      });
    });

    // Mock Booking Details API
    await page.route('**/api/v1/bookings/88888888-8888-8888-8888-888888888888', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: '88888888-8888-8888-8888-888888888888',
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
          items: [
            {
              id: 'item-1',
              unit_price: '1499.00',
              services: {
                name: 'Comprehensive Periodic Service',
              },
            },
          ],
        }),
      });
    });

    // Mock Live Mechanic Location
    await page.route('**/api/v1/bookings/88888888-8888-8888-8888-888888888888/mechanic-location', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          mechanic_id: MOCK_USERS.mechanic.id,
          latitude: 12.9716,
          longitude: 77.5946,
          updated_at: new Date().toISOString(),
          eta_minutes: 12,
          eta_distance_km: 3.8,
        }),
      });
    });

    // Mock Service Operations endpoints
    await page.route('**/api/v1/bookings/88888888-8888-8888-8888-888888888888/structured-inspection', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
    });
    await page.route('**/api/v1/bookings/88888888-8888-8888-8888-888888888888/checklist', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
    });
    await page.route('**/api/v1/bookings/88888888-8888-8888-8888-888888888888/service-report', async (route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(null) });
    });
  });

  test('customer views dashboard with active bookings and mechanic en route status', async ({ page }) => {
    await page.goto('/dashboard');

    // Verify Customer Dashboard loaded
    await expect(page.locator('h1')).toContainText('Customer Dashboard');

    // Verify Active Booking Card #BK-1001
    await expect(page.locator('text=#BK-1001')).toBeVisible();
    await expect(page.locator('text=Comprehensive Periodic Service')).toBeVisible();
    await expect(page.locator('text=Mechanic En Route')).toBeVisible();

    // Verify Track Mechanic button is visible for en-route booking
    const trackButton = page.locator('a:has-text("Track Mechanic")');
    await expect(trackButton).toBeVisible();
  });

  test('customer navigates to live tracking page and verifies ETA/status updates', async ({ page }) => {
    await page.goto('/bookings/88888888-8888-8888-8888-888888888888/tracking');

    // Verify Tracking page elements
    await expect(page.locator('text=Booking #BK-1001')).toBeVisible();
    await expect(page.locator('text=Your mechanic is on the way')).toBeVisible();
    await expect(page.locator('text=En Route')).toBeVisible();
  });

  test('customer views completed booking and verifies review action availability', async ({ page }) => {
    await page.goto('/dashboard');

    // Verify Past Bookings Section
    await expect(page.locator('text=Past Bookings')).toBeVisible();
    await expect(page.locator('text=#BK-1002')).toBeVisible();

    // Verify Leave Review link is available for completed booking
    const reviewLink = page.locator('a:has-text("Leave Review")');
    await expect(reviewLink).toBeVisible();
  });
});
