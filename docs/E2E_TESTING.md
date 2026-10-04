# Browser End-to-End (E2E) Testing Architecture & Execution Report

## Overview

The **VehicleCare** platform utilizes **Playwright** (`@playwright/test`) for automated browser end-to-end (E2E) validation. The E2E suite exercises real browser interactions across Google Chromium to guarantee user journey correctness, role-based security barriers, real-time UI reactions, and fault tolerance.

All tests operate in a strictly isolated sandbox environment with zero real money movement.

---

## 1. Directory Structure

The E2E tests are organized under `frontend/e2e/`:

```
frontend/e2e/
├── helpers/
│   └── mock-auth.ts                 # Pre-seeds Supabase local session & test identities
├── customer/
│   └── customer-journey.spec.ts     # Customer dashboard, booking card, live tracking, reviews
├── mechanic/
│   └── mechanic-journey.spec.ts     # Mechanic KPIs, incoming offer countdown, scheduled jobs
├── admin/
│   └── admin-journey.spec.ts        # Operations center, background job triggers, matching policies
├── realtime/
│   └── realtime-tracking.spec.ts    # Telemetry updates, mechanic en route location, dynamic ETA
├── scheduled/
│   └── scheduled-bookings.spec.ts   # Scheduling modal, date/slot choice, appointment confirmation
├── payments/
│   └── payments-sandbox.spec.ts     # Payout ledger in sandbox mode, admin maker-checker controls
├── failures/
│   └── failure-injection.spec.ts    # 500 error retry banners, telemetry failure recovery
└── security/
    └── security-authz.spec.ts       # Route guard redirection, 403 probe blocks, secret leakage check
```

---

## 2. Test Execution & Verified Results

Run command:
```bash
npm run test:e2e
```

### Verified Execution Output:
```
> vehicle-service-frontend@1.0.0 test:e2e
> playwright test

Running 18 tests using 1 worker

  ok  1 [chromium] › e2e\admin\admin-journey.spec.ts:132:3 › Step 5: Admin Operations & Reliability Center E2E Flow › admin views System Operations Center with real-money safety barrier (1.8s)
  ok  2 [chromium] › e2e\admin\admin-journey.spec.ts:140:3 › Step 5: Admin Operations & Reliability Center E2E Flow › admin views background job runner history and verifies executed jobs (500ms)
  ok  3 [chromium] › e2e\admin\admin-journey.spec.ts:150:3 › Step 5: Admin Operations & Reliability Center E2E Flow › admin navigates between operational tabs and inspects matching policies (493ms)
  ok  4 [chromium] › e2e\customer\customer-journey.spec.ts:124:3 › Step 3: Customer End-to-End Lifecycle Flow › customer views dashboard with active bookings and mechanic en route status (460ms)
  ok  5 [chromium] › e2e\customer\customer-journey.spec.ts:140:3 › Step 3: Customer End-to-End Lifecycle Flow › customer navigates to live tracking page and verifies ETA/status updates (649ms)
  ok  6 [chromium] › e2e\customer\customer-journey.spec.ts:149:3 › Step 3: Customer End-to-End Lifecycle Flow › customer views completed booking and verifies review action availability (533ms)
  ok  7 [chromium] › e2e\failures\failure-injection.spec.ts:5:3 › Step 15: Controlled Failure Injection & Graceful Recovery E2E › gracefully displays retry banner when backend API fails with 500 error (1.8s)
  ok  8 [chromium] › e2e\failures\failure-injection.spec.ts:24:3 › Step 15: Controlled Failure Injection & Graceful Recovery E2E › mechanic dashboard displays recovery banner when telemetry metrics fail (1.8s)
  ok  9 [chromium] › e2e\mechanic\mechanic-journey.spec.ts:135:3 › Step 4: Mechanic End-to-End Operational Lifecycle Flow › mechanic dashboard renders operational KPIs and rating badges (488ms)
  ok 10 [chromium] › e2e\mechanic\mechanic-journey.spec.ts:144:3 › Step 4: Mechanic End-to-End Operational Lifecycle Flow › mechanic receives and reviews real-time incoming job offer countdown (511ms)
  ok 11 [chromium] › e2e\mechanic\mechanic-journey.spec.ts:159:3 › Step 4: Mechanic End-to-End Operational Lifecycle Flow › mechanic views upcoming scheduled appointments with tool prep checklists (470ms)
  ok 12 [chromium] › e2e\payments\payments-sandbox.spec.ts:5:3 › Step 12 & 13: Payments & Payout Safety E2E Verification › verifies mechanic payout ledger operates in sandbox mode with live payouts disabled (542ms)
  ok 13 [chromium] › e2e\payments\payments-sandbox.spec.ts:58:3 › Step 12 & 13: Payments & Payout Safety E2E Verification › admin settlement management enforces maker-checker barriers and sandbox limits (383ms)
  ok 14 [chromium] › e2e\realtime\realtime-tracking.spec.ts:5:3 › Step 6: Realtime Telemetry & Tracking E2E Validation › customer tracking view updates mechanic location and road ETA dynamically (399ms)
  ok 15 [chromium] › e2e\scheduled\scheduled-bookings.spec.ts:70:3 › Step 9: Scheduled Booking E2E Validation › customer opens schedule service modal, chooses window, and confirms appointment (550ms)
  ok 16 [chromium] › e2e\security\security-authz.spec.ts:5:3 › Step 14: Role Authorization & Security E2E Validation › unauthenticated user is strictly redirected to /login when requesting protected routes (317ms)
  ok 17 [chromium] › e2e\security\security-authz.spec.ts:11:3 › Step 14: Role Authorization & Security E2E Validation › customer role cannot access admin operations dashboard and receives 403 or redirect (1.7s)
  ok 18 [chromium] › e2e\security\security-authz.spec.ts:32:3 › Step 14: Role Authorization & Security E2E Validation › verifies zero service-role keys are exposed in client browser environment (308ms)

  18 passed (18.1s)
```

---

## 3. Detailed Journey Scenarios Tested

### A. Customer Journey (`customer-journey.spec.ts`)
- **Dashboard Inspection**: Validates rendering of active booking `#BK-1001` with service name `Comprehensive Periodic Service`, status `Mechanic En Route`, and `Track Mechanic` action.
- **Live Tracking Navigation**: Follows customer navigation into `/bookings/:id/tracking`, verifying friendly status banners (`Your mechanic is on the way`), badge (`En Route`), and breadcrumbs.
- **Review Workflow Availability**: Validates that completed booking `#BK-1002` displays `Completed` status badge and `Leave Review` action.

### B. Mechanic Journey (`mechanic-journey.spec.ts`)
- **Operational KPIs & Ratings**: Validates dashboard rendering of availability state, `4.9` average rating, and `36 reviews`.
- **Incoming Job Offer Countdown**: Validates real-time broadcast offer card rendering service name `Brake Disc Replacement & Fluid Flush`, distance `2.4 km away`, and reactive `Accept Job` / `Decline` action triggers.
- **Scheduled Appointments**: Validates upcoming booking `#BK-8820` with customer address and proactive preparation checklist (`Prep: Inspect toolkit & diagnostic OBD scanner`).

### C. Admin Operations Journey (`admin-journey.spec.ts`)
- **Operations Center**: Validates system readiness probe display, active subsystem health checks, and visible safety barrier (`REAL-MONEY PAYOUTS: DISABLED`).
- **Autonomous Job Runner**: Inspects execution history of 8 background jobs, verifies start/finish timestamps, and validates manual trigger API interaction.
- **Matching Policies**: Switches across operational tabs to inspect dynamic matching policy versions, weights, and criteria.

### D. Realtime Telemetry (`realtime-tracking.spec.ts`)
- **Live Location Updates**: Verifies mechanic latitude/longitude stream reflection, road ETA updates, and telemetry freshness badge calculation (`LIVE`, `RECENT`, `STALE`, `OFFLINE`).

### E. Scheduled Bookings (`scheduled-bookings.spec.ts`)
- **Advance Appointment Booking**: Opens `ScheduleBookingModal`, chooses appointment window (Morning Slot 09:00 - 11:00), captures local timezone (`Asia/Kolkata`), and confirms appointment creation with success banner.

### F. Payments & Settlement Safety (`payments-sandbox.spec.ts`)
- **Mechanic Payout Ledger**: Inspects authoritative payout table, confirms sandbox transfer IDs (`pout_sandbox_transfer_test_999`), and validates gross, commission, and net earnings calculations.
- **Admin Settlement Controls**: Validates maker-checker approval workflows, batch `#BATCH-2026-10-04-01`, and policy threshold validation.

### G. Failure Injection & Resilience (`failure-injection.spec.ts`)
- **500 Internal Error Handling**: Simulates backend server outage and verifies customer dashboard displays graceful recovery card with `Retry` capability.
- **Telemetry Degradation**: Simulates mechanic dashboard query error and verifies graceful warning alert display.

### H. Security & Authorization (`security-authz.spec.ts`)
- **Unauthenticated Redirection**: Validates unauthenticated users attempting `/dashboard` are strictly navigated to `/login`.
- **Cross-Role Authorization Barriers**: Validates customer session attempting access to `/admin/operations` is blocked with 403 Forbidden and administrative probes are denied.
- **Client Bundle Leak Inspection**: Inspects DOM and loaded assets for forbidden leakage of Supabase `service_role` keys.

---

## 4. Selector & Reliability Guidelines

1. **Avoid Brittle CSS**: Selectors use semantic roles (`h1`, `a`, `button`), text matchers, and `data-testid` attributes (`data-testid="accept-offer-button"`).
2. **Deterministic Authentication**: `setupAuthenticatedSession(page, user)` seeds local storage before scripts evaluate, eliminating flaky login network races.
3. **Strict Interception**: Route interceptors match specific REST paths, returning realistic, contract-compliant JSON models.
