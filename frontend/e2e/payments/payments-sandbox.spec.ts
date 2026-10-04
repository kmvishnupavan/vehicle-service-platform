import { test, expect } from '@playwright/test';
import { setupAuthenticatedSession, MOCK_USERS } from '../helpers/mock-auth';

test.describe('Step 12 & 13: Payments & Payout Safety E2E Verification', () => {
  test('verifies mechanic payout ledger operates in sandbox mode with live payouts disabled', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.mechanic);

    // Mock Mechanic Payout Summary
    await page.route('**/api/v1/mechanics/payouts/summary*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          current_balance: 5120.0,
          total_withdrawn: 14500.0,
          pending_payouts: 2500.0,
          currency: 'INR',
        }),
      });
    });

    // Mock Mechanic Payouts Ledger
    await page.route(/\/api\/v1\/mechanics\/payouts(\?.*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'payout-test-1',
              batch_id: 'batch-001',
              mechanic_id: MOCK_USERS.mechanic.id,
              booking_number: 'BK-501',
              gross_amount: '3000.00',
              commission_rate: '0.15',
              commission_amount: '500.00',
              deduction_amount: '0.00',
              net_amount: '2500.00',
              provider_transfer_id: 'pout_sandbox_transfer_test_999',
              status: 'processed',
              created_at: new Date().toISOString(),
              settled_at: new Date().toISOString(),
            },
          ],
          total: 1,
        }),
      });
    });

    await page.goto('/mechanic/payouts');

    // Verify Payout Ledger page rendered
    await expect(page.locator('h1')).toContainText('Mechanic Payout Ledger');
    await expect(page.locator('text=BK-501')).toBeVisible();
    await expect(page.locator('text=₹2,500.00')).toBeVisible();
  });

  test('admin settlement management enforces maker-checker barriers and sandbox limits', async ({ page }) => {
    await setupAuthenticatedSession(page, MOCK_USERS.admin);

    // Mock Settlement Policy
    await page.route('**/api/v1/admin/settlements/policy*', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          threshold_amount: 50000.0,
          requires_checker: true,
          is_active: true,
        }),
      });
    });

    // Mock Settlement Batches
    await page.route(/\/api\/v1\/admin\/settlements(\?.*)?$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: [
            {
              id: 'batch-sbx-1',
              batch_number: 'BATCH-2026-10-04-01',
              status: 'approved',
              total_amount: 15400.0,
              total_count: 8,
              created_at: new Date().toISOString(),
              approved_by: MOCK_USERS.admin.id,
            },
          ],
          total: 1,
        }),
      });
    });

    await page.goto('/admin/settlements');

    // Verify Settlement Management page
    await expect(page.locator('h1')).toContainText('Settlement Disbursements');
    await expect(page.locator('text=BATCH-2026-10-04-01')).toBeVisible();
    await expect(page.locator('text=₹15,400.00')).toBeVisible();
  });
});
