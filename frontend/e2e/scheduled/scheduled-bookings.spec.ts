import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 9: Scheduled Booking E2E Validation', () => {
  test.beforeEach(async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);

    // Mock Customer's Bookings API with an unscheduled pending booking
    await page.route(/\/api\/v1\/bookings(\?.*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            id: '77777777-7777-7777-7777-777777777777',
            booking_number: 'BK-SCHED-01',
            booking_status: 'pending',
            scheduled_at: null,
            total_amount: '1200.00',
            payment_status: 'pending',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            booking_items: [
              {
                id: 'item-sched-1',
                service_id: 'srv-sched',
                quantity: 1,
                unit_price: '1200.00',
                services: {
                  name: 'Standard Doorstep Service',
                  description: 'Periodic inspection and lube service',
                },
              },
            ],
          },
        ]),
      });
    });

    // Mock Scheduled Booking Detail Check
    await page.route('**/api/v1/bookings/77777777-7777-7777-7777-777777777777/schedule', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 404,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'No schedule found' }),
        });
      } else if (route.request().method() === 'POST') {
        const body = JSON.parse(route.request().postData() || '{}');
        await route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({
            id: 'sched-record-1',
            booking_id: '77777777-7777-7777-7777-777777777777',
            scheduled_start_at: body.scheduled_start_at,
            scheduled_end_at: body.scheduled_end_at,
            timezone: body.timezone || 'Asia/Kolkata',
            dispatch_at: new Date(Date.now() + 3600000).toISOString(),
            status: 'scheduled',
            attempt_count: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          }),
        });
      }
    });
  });

  test('customer opens schedule service modal, chooses window, and confirms appointment', async ({ page }) => {
    await page.goto('/dashboard');

    // Click "Schedule" button on BK-SCHED-01
    const scheduleBtn = page.locator('button:has-text("Schedule")');
    await expect(scheduleBtn).toBeVisible();
    await scheduleBtn.click();

    // Verify Schedule Modal opened
    await expect(page.locator('text=Schedule Doorstep Service')).toBeVisible();
    await expect(page.locator('text=Booking #BK-SCHED-01')).toBeVisible();

    // Select slot & submit
    const confirmBtn = page.locator('button:has-text("Confirm Schedule")');
    await expect(confirmBtn).toBeVisible();
    await confirmBtn.click();

    // Verify confirmation feedback
    await expect(page.locator('text=Appointment scheduled successfully!')).toBeVisible();
  });
});
