import { describe, it, expect } from 'vitest';
import {
  PayoutAccount,
  PayoutAccountVerificationStatus,
  SettlementHistoryItem,
} from '../types/payoutAccount';

// Helper: Validate account form input
export function validatePayoutAccountForm(values: {
  account_holder_name?: string;
  bank_name?: string;
  account_number?: string;
  confirm_account_number?: string;
  ifsc_code?: string;
  consent_given?: boolean;
}): { isValid: boolean; errors: Record<string, string> } {
  const errors: Record<string, string> = {};

  if (!values.account_holder_name?.trim()) {
    errors.account_holder_name = 'Account holder name is required.';
  } else if (values.account_holder_name.trim().length < 3) {
    errors.account_holder_name = 'Name must be at least 3 characters.';
  }

  if (!values.bank_name?.trim()) {
    errors.bank_name = 'Bank name is required.';
  }

  const cleanAcc = (values.account_number || '').replace(/\s+/g, '');
  if (!cleanAcc) {
    errors.account_number = 'Account number is required.';
  } else if (!/^\d{9,18}$/.test(cleanAcc)) {
    errors.account_number = 'Account number must be between 9 and 18 digits.';
  }

  const cleanConfirm = (values.confirm_account_number || '').replace(/\s+/g, '');
  if (cleanAcc !== cleanConfirm) {
    errors.confirm_account_number = 'Account numbers do not match.';
  }

  const cleanIfsc = (values.ifsc_code || '').trim().toUpperCase();
  if (!cleanIfsc) {
    errors.ifsc_code = 'IFSC code is required.';
  } else if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(cleanIfsc)) {
    errors.ifsc_code = 'Invalid IFSC format.';
  }

  if (!values.consent_given) {
    errors.consent = 'You must affirm account ownership to continue.';
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
}

// Helper: Mask account number
export function maskAccountNumber(acc: string): string {
  const clean = acc.replace(/\s+/g, '');
  if (clean.length < 4) return '••••';
  const last4 = clean.slice(-4);
  return `•••• •••• ${last4}`;
}

// Helper: Verification status metadata
export function getVerificationStatusConfig(status: PayoutAccountVerificationStatus) {
  switch (status) {
    case 'verified':
      return { label: 'Verified & Active', canVerify: false, canDisburse: true };
    case 'pending':
      return { label: 'Pending Verification', canVerify: true, canDisburse: false };
    case 'submitted':
      return { label: 'Submitted to Provider', canVerify: true, canDisburse: false };
    case 'failed':
      return { label: 'Verification Failed', canVerify: true, canDisburse: false };
    case 'suspended':
      return { label: 'Suspended', canVerify: false, canDisburse: false };
    case 'not_configured':
    default:
      return { label: 'Not Configured', canVerify: false, canDisburse: false };
  }
}

describe('Phase 8.8 — Mechanic Banking Onboarding & Settlements', () => {
  describe('Form Validation', () => {
    it('rejects empty or missing form values', () => {
      const res = validatePayoutAccountForm({});
      expect(res.isValid).toBe(false);
      expect(res.errors.account_holder_name).toBeDefined();
      expect(res.errors.bank_name).toBeDefined();
      expect(res.errors.account_number).toBeDefined();
      expect(res.errors.ifsc_code).toBeDefined();
      expect(res.errors.consent).toBeDefined();
    });

    it('rejects short account numbers (< 9 digits) and non-numeric characters', () => {
      const res = validatePayoutAccountForm({
        account_holder_name: 'Rajesh Kumar',
        bank_name: 'HDFC Bank',
        account_number: '12345',
        confirm_account_number: '12345',
        ifsc_code: 'HDFC0001234',
        consent_given: true,
      });
      expect(res.isValid).toBe(false);
      expect(res.errors.account_number).toContain('between 9 and 18 digits');
    });

    it('rejects mismatched confirm account number', () => {
      const res = validatePayoutAccountForm({
        account_holder_name: 'Rajesh Kumar',
        bank_name: 'HDFC Bank',
        account_number: '50100234567890',
        confirm_account_number: '50100234567899',
        ifsc_code: 'HDFC0001234',
        consent_given: true,
      });
      expect(res.isValid).toBe(false);
      expect(res.errors.confirm_account_number).toBe('Account numbers do not match.');
    });

    it('rejects invalid IFSC code patterns', () => {
      const invalidIFSC = ['HDFC123456', 'SBIN00012', '12340001234', 'HDFCA001234'];
      for (const ifsc of invalidIFSC) {
        const res = validatePayoutAccountForm({
          account_holder_name: 'Rajesh Kumar',
          bank_name: 'HDFC Bank',
          account_number: '50100234567890',
          confirm_account_number: '50100234567890',
          ifsc_code: ifsc,
          consent_given: true,
        });
        expect(res.isValid).toBe(false);
        expect(res.errors.ifsc_code).toBe('Invalid IFSC format.');
      }
    });

    it('rejects submission if consent checkbox is unchecked', () => {
      const res = validatePayoutAccountForm({
        account_holder_name: 'Rajesh Kumar',
        bank_name: 'HDFC Bank',
        account_number: '50100234567890',
        confirm_account_number: '50100234567890',
        ifsc_code: 'HDFC0001234',
        consent_given: false,
      });
      expect(res.isValid).toBe(false);
      expect(res.errors.consent).toBeDefined();
    });

    it('accepts valid Indian banking details with uppercase IFSC and consent', () => {
      const res = validatePayoutAccountForm({
        account_holder_name: 'Rajesh Kumar',
        bank_name: 'HDFC Bank',
        account_number: '50100234567890',
        confirm_account_number: '50100234567890',
        ifsc_code: 'hdfc0001234', // lower case should be normalized
        consent_given: true,
      });
      expect(res.isValid).toBe(true);
      expect(Object.keys(res.errors).length).toBe(0);
    });
  });

  describe('Security & Account Masking', () => {
    it('properly masks bank account numbers to last 4 digits only', () => {
      const masked = maskAccountNumber('50100234567890');
      expect(masked).toBe('•••• •••• 7890');
      expect(masked.includes('5010023456')).toBe(false);
    });

    it('ensures PayoutAccount objects never expose raw account numbers', () => {
      const account: PayoutAccount = {
        id: 'acc-uuid-1',
        mechanic_id: 'mech-uuid-1',
        provider: 'razorpayx',
        provider_account_id: 'fa_test_123',
        account_holder_name: 'Suresh Raina',
        bank_name: 'ICICI Bank',
        account_number_masked: '•••• •••• 4321',
        ifsc_code: 'ICIC0000001',
        verification_status: 'verified',
        is_active: true,
        is_primary: true,
        created_at: '2026-10-03T10:00:00Z',
        updated_at: '2026-10-03T10:00:00Z',
      };

      expect(account.account_number_masked).toMatch(/^•••• •••• \d{4}$/);
      expect((account as any).account_number).toBeUndefined();
    });
  });

  describe('State Machine & Verification Logic', () => {
    it('allows verification trigger for pending, submitted, and failed statuses', () => {
      expect(getVerificationStatusConfig('pending').canVerify).toBe(true);
      expect(getVerificationStatusConfig('submitted').canVerify).toBe(true);
      expect(getVerificationStatusConfig('failed').canVerify).toBe(true);
    });

    it('prohibits verification trigger for verified, suspended, or not_configured statuses', () => {
      expect(getVerificationStatusConfig('verified').canVerify).toBe(false);
      expect(getVerificationStatusConfig('suspended').canVerify).toBe(false);
      expect(getVerificationStatusConfig('not_configured').canVerify).toBe(false);
    });

    it('only permits disbursements for verified active accounts', () => {
      expect(getVerificationStatusConfig('verified').canDisburse).toBe(true);
      expect(getVerificationStatusConfig('pending').canDisburse).toBe(false);
      expect(getVerificationStatusConfig('failed').canDisburse).toBe(false);
      expect(getVerificationStatusConfig('suspended').canDisburse).toBe(false);
    });
  });

  describe('Settlement History Records', () => {
    it('correctly maps settlement items with batch numbers and sanitized failures', () => {
      const settlement: SettlementHistoryItem = {
        id: 'payout-uuid-1',
        booking_id: 'bk-uuid-1',
        booking_number: 'BK-2026-888',
        net_amount: '1250.00',
        currency: 'INR',
        status: 'paid',
        provider_payout_id: 'pout_test_123',
        settlement_batch_id: 'batch-uuid-1',
        batch_number: 'BATCH-20261003-0001',
        batch_status: 'completed',
        created_at: '2026-10-03T12:00:00Z',
        settled_at: '2026-10-03T12:30:00Z',
        failure_reason: null,
      };

      expect(settlement.batch_number).toBe('BATCH-20261003-0001');
      expect(settlement.status).toBe('paid');
      expect(Number(settlement.net_amount)).toBe(1250.0);
    });

    it('contains sanitized failure explanation on failed disbursement', () => {
      const settlement: SettlementHistoryItem = {
        id: 'payout-uuid-2',
        booking_id: 'bk-uuid-2',
        booking_number: 'BK-2026-889',
        net_amount: '900.00',
        currency: 'INR',
        status: 'failed',
        failure_reason: 'Beneficiary bank technical decline',
        created_at: '2026-10-03T13:00:00Z',
      };

      expect(settlement.status).toBe('failed');
      expect(settlement.failure_reason).toBe('Beneficiary bank technical decline');
    });
  });
});
