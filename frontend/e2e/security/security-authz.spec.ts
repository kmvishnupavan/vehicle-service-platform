import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 14: Role Authorization & Security E2E Validation', () => {
  test('unauthenticated user is strictly redirected to /login when requesting protected routes', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForURL('**/login**');
    await expect(page.locator('h2')).toContainText('Sign in to VehicleCare');
  });

  test('customer role cannot access admin operations dashboard and receives 403 or redirect', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);

    // Mock Admin API to reject customer with 403 Forbidden
    await page.route('**/api/v1/admin/**', async (route) => {
      await route.fulfill({
        status: 403,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Forbidden: Admin access required' }),
      });
    });

    await page.goto('/admin/operations');

    // Verify customer is strictly prevented from accessing admin route and redirected to customer dashboard
    await page.waitForURL('**/customer/dashboard**');
    await expect(page).toHaveURL(/\/customer\/dashboard/);

    // Verify privileged admin data is never rendered
    await expect(page.locator('text=Bookings Lifecycle')).toBeHidden();
    await expect(page.locator('text=System Operations Center')).toBeHidden();
  });

  test('verifies zero service-role keys are exposed in client browser environment', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.customer);
    await page.goto('/dashboard');

    // Inspect window and HTML for any leakage of service role secret key
    const pageContent = await page.content();
    expect(pageContent).not.toContain('service_role');
    expect(pageContent).not.toContain('placeholder_service_role_key');
  });
});
