# Payout Provider Integration & Research (Phase 8.8)

**Target System:** Vehicle Service Platform (Domestic India Operations)  
**Date Checked:** October 3, 2026  
**Primary Provider Evaluated & Selected:** RazorpayX (Razorpay Software Private Limited)  
**Alternative Evaluated:** Stripe Connect (Custom/Express Accounts)

---

## 1. Provider Selection Analysis

### RazorpayX (Selected for India Domestic Payouts)
- **Official Documentation:**
  - RazorpayX Overview: https://razorpay.com/docs/x/
  - RazorpayX Contacts: https://razorpay.com/docs/x/contacts/
  - RazorpayX Fund Accounts: https://razorpay.com/docs/x/fund-accounts/
  - Bank Account Validation (Penny Drop): https://razorpay.com/docs/x/bank-account-validation/
  - RazorpayX Payouts API: https://razorpay.com/docs/x/payouts/api/
  - RazorpayX Webhooks: https://razorpay.com/docs/x/webhooks/
- **Availability:** Fully operational across India. Disburses directly via IMPS, NEFT, RTGS, and UPI.
- **Business Onboarding & KYC:**
  - Requires Indian business registration (Private Limited, LLP, Partnership, or Sole Proprietorship).
  - Current account with authorized banking partner (e.g., RBL Bank, ICICI Bank, Yes Bank).
  - Business KYC documents: Certificate of Incorporation, GSTIN, PAN, and signatory documentation.
- **Fund Account Model:**
  - Direct 2-step onboarding: Contact creation (`POST /v1/contacts`) followed by Fund Account creation (`POST /v1/fund_accounts`).
  - Supports Bank Account type (`bank_account`) with `account_number` and `ifsc_code`.
- **Beneficiary Verification:**
  - Supports automated Penny Drop Validation (`POST /v1/fund_accounts/validations`).
  - Transfers ₹1 to the target beneficiary account and retrieves the beneficiary name registered with NPCI/bank to prevent name mismatch fraud.
- **Payout Creation & Idempotency:**
  - Endpoint: `POST /v1/payouts`.
  - Idempotency: Mandatory `X-Payout-Idempotency` HTTP header. RazorpayX guarantees that requests with identical keys within 24 hours return the exact identical payout object without duplicate debits.
- **Webhook Authentication:**
  - Webhooks signed via HMAC-SHA256 in the `X-Razorpay-Signature` header.
  - Verification compares HMAC-SHA256 signature calculated over raw request body using `RAZORPAYX_WEBHOOK_SECRET`.
- **Lifecycle Events Supported:**
  - `payout.processed`: Payout settled successfully to the beneficiary bank.
  - `payout.failed`: Payout rejected or failed by beneficiary bank or NPCI.
  - `payout.reversed`: Payout reversed due to clearing failure after initial acceptance.
  - `payout.updated`: Status changes across processing stages.

### Stripe Connect (Evaluated Alternative — Not Selected)
- **Official Documentation:** https://stripe.com/docs/connect
- **India Limitations & RBI Restrictions:**
  - Stripe Connect in India is heavily restricted for multi-party marketplaces under Reserve Bank of India (RBI) Payment Aggregator and Payment Gateway (PA/PG) guidelines.
  - Stripe accounts in India currently operate under merchant export transaction mandates requiring individual merchant verification, IEC, and stringent cross-border regulations.
  - Pure domestic INR vendor payouts to non-registered mechanics without separate merchant onboarding face major compliance hurdles compared to domestic payout providers like RazorpayX.
- **Conclusion:** RazorpayX is selected as the primary provider for domestic INR mechanic payouts.

---

## 2. API Contract Specification (RazorpayX)

### 2.1 Contact Creation
- **Endpoint:** `POST https://api.razorpay.com/v1/contacts`
- **Headers:** `Authorization: Basic <base64(KEY_ID:KEY_SECRET)>`, `Content-Type: application/json`
- **Request:**
  ```json
  {
    "name": "Ramesh Kumar Verma",
    "email": "mechanic@example.com",
    "contact": "+919876543210",
    "type": "vendor",
    "reference_id": "mech_9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
  }
  ```
- **Response:** Returns `id` (e.g., `cont_J8xABC123XYZ`).

### 2.2 Fund Account Creation
- **Endpoint:** `POST https://api.razorpay.com/v1/fund_accounts`
- **Request:**
  ```json
  {
    "contact_id": "cont_J8xABC123XYZ",
    "account_type": "bank_account",
    "bank_account": {
      "name": "Ramesh Kumar Verma",
      "ifsc": "HDFC0001234",
      "account_number": "50100234567890"
    }
  }
  ```
- **Response:** Returns `id` (e.g., `fa_J8xABC123XYZ`). Plain account numbers are tokenized; only masked values are returned by the provider.

### 2.3 Fund Account Validation (Penny Drop)
- **Endpoint:** `POST https://api.razorpay.com/v1/fund_accounts/validations`
- **Request:**
  ```json
  {
    "fund_account": {
      "id": "fa_J8xABC123XYZ"
    },
    "amount": 100,
    "currency": "INR",
    "notes": {
      "purpose": "mechanic_bank_verification"
    }
  }
  ```
- **Response:**
  ```json
  {
    "id": "fav_J8xABC123XYZ",
    "entity": "fund_account.validation",
    "fund_account": { "id": "fa_J8xABC123XYZ" },
    "status": "completed",
    "results": {
      "account_status": "active",
      "registered_name": "RAMESH KUMAR VERMA"
    }
  }
  ```

### 2.4 Payout Creation
- **Endpoint:** `POST https://api.razorpay.com/v1/payouts`
- **Headers:**
  - `Authorization: Basic <base64(KEY_ID:KEY_SECRET)>`
  - `X-Payout-Idempotency: <UUIDv4>`
  - `Content-Type: application/json`
- **Request:**
  ```json
  {
    "account_number": "2323230034567890",
    "fund_account_id": "fa_J8xABC123XYZ",
    "amount": 150000,
    "currency": "INR",
    "mode": "IMPS",
    "purpose": "payout",
    "queue_if_low_balance": true,
    "reference_id": "pout_ledger_uuid_here",
    "narration": "VehicleCare Settlement"
  }
  ```

### 2.5 Webhook Signature Verification
- RazorpayX transmits `X-Razorpay-Signature` with incoming HTTP POST bodies.
- Verification algorithm:
  ```python
  expected_signature = hmac.new(
      key=webhook_secret.encode("utf-8"),
      msg=raw_request_body,
      digestmod=hashlib.sha256,
  ).hexdigest()
  is_valid = hmac.compare_digest(expected_signature, header_signature)
  ```

---

## 3. Sandbox / Test-Mode Safety Architecture

To guarantee that no real money movement occurs during development or staging:
1. `RazorpayXProvider` checks for `RAZORPAYX_KEY_ID` and `RAZORPAYX_KEY_SECRET`.
2. When credentials are not configured or set to sandbox mode, the platform automatically switches to a strictly typed Sandbox Adapter.
3. The Sandbox Adapter:
   - Simulates contact creation and fund-account tokenization (`fa_test_{uuid}`).
   - Generates simulated penny-drop validation responses.
   - Generates simulated payout responses with realistic statuses (`processing`, `processed`).
   - Generates and signs synthetic webhooks using the exact HMAC-SHA256 protocol.
   - Never interacts with live banking clearinghouses (IMPS/NEFT/NPCI).
   - Emits structured audit logs with `[SANDBOX]` tags.

---

## 4. Production Prerequisites for Live Payouts

Before switching to live money movement:
1. **RazorpayX Live Merchant Account:** Complete business registration and submit board resolution.
2. **Current Account Funding:** RazorpayX virtual account must be loaded with sufficient clearing balance.
3. **Environment Secrets:** Provide `RAZORPAYX_KEY_ID`, `RAZORPAYX_KEY_SECRET`, and `RAZORPAYX_WEBHOOK_SECRET` via secure production key manager.
4. **Penny Drop Thresholds:** Configure beneficiary name fuzzy match score thresholds (minimum 80% match).
5. **Two-Factor Approval:** Enable maker-checker batch approvals for high-value settlement batches.
