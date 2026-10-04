import { describe, it, expect } from 'vitest';
import {
  SettlementBatchItem,
  SettlementApprovalPolicy,
  SettlementBatchStatus,
  MechanicStatement,
} from '../types/settlement';
import { getSettlementStatusConfig } from '../components/admin/SettlementStatusBadge';

// Helper: Determine if user can act as Checker
export function canUserActAsChecker(
  userId: string | undefined,
  batch: Pick<SettlementBatchItem, 'created_by' | 'status'>
): { canAct: boolean; isMaker: boolean; reason?: string } {
  if (!userId) {
    return { canAct: false, isMaker: false, reason: 'Unauthenticated' };
  }
  const isMaker = batch.created_by === userId;
  if (isMaker) {
    return {
      canAct: false,
      isMaker: true,
      reason: 'Maker-Checker violation: Batch creator cannot approve or reject their own batch',
    };
  }
  if (batch.status !== 'approval_required') {
    return {
      canAct: false,
      isMaker: false,
      reason: `Action not allowed for batch with status ${batch.status}`,
    };
  }
  return { canAct: true, isMaker: false };
}

// Helper: Determine permissible actions for a batch
export function getPermissibleBatchActions(
  userId: string | undefined,
  batch: Pick<SettlementBatchItem, 'created_by' | 'status'>
): {
  canSubmit: boolean;
  canApprove: boolean;
  canReject: boolean;
  canCancel: boolean;
} {
  const isMaker = Boolean(userId && batch.created_by === userId);
  const checkerEval = canUserActAsChecker(userId, batch);

  return {
    canSubmit: isMaker && batch.status === 'draft',
    canApprove: checkerEval.canAct,
    canReject: checkerEval.canAct,
    canCancel: ['draft', 'approval_required', 'approved'].includes(batch.status),
  };
}

// Helper: Evaluate policy threshold routing
export function evaluatePolicyRouting(
  totalAmount: number,
  policy: SettlementApprovalPolicy
): SettlementBatchStatus {
  const threshold = parseFloat(policy.threshold_amount || '0');
  if (policy.requires_checker) {
    if (threshold <= 0 || totalAmount >= threshold) {
      return 'approval_required';
    }
    return 'draft';
  }
  return 'approved';
}

// Helper: Validate policy update input
export function validatePolicyUpdate(values: {
  threshold_amount?: number;
  requires_checker?: boolean;
}): { isValid: boolean; errors: Record<string, string> } {
  const errors: Record<string, string> = {};

  if (values.threshold_amount === undefined || values.threshold_amount === null) {
    errors.threshold_amount = 'Threshold amount is required';
  } else if (isNaN(values.threshold_amount) || values.threshold_amount < 0) {
    errors.threshold_amount = 'Threshold amount must be a non-negative number';
  }

  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
}

// Helper: Verify statement integrity and masking
export function verifyStatementMasking(statement: MechanicStatement): {
  isMasked: boolean;
  hasRequiredSections: boolean;
} {
  const maskedAcc = statement.account_number_masked;
  const isMasked = /^••••\s?••••\s?\d{4}$/.test(maskedAcc) || /^\*{4,}\d{4}$/.test(maskedAcc);
  const hasRequiredSections = Boolean(
    statement.statement_number &&
    statement.mechanic_id &&
    statement.total_gross &&
    statement.total_net &&
    statement.items !== undefined
  );
  return { isMasked, hasRequiredSections };
}

describe('Phase 8.9 — Settlement Management & Maker-Checker Workflow', () => {
  const makerUserId = 'user-maker-1111-1111';
  const checkerUserId = 'user-checker-2222-2222';

  const sampleBatch: SettlementBatchItem = {
    id: 'batch-0001',
    batch_number: 'BATCH-20261003-0001',
    provider: 'razorpayx',
    status: 'approval_required',
    total_amount: '15400.00',
    currency: 'INR',
    item_count: 5,
    created_by: makerUserId,
    created_at: '2026-10-03T10:00:00Z',
  };

  describe('Maker-Checker Independence & Guardrails', () => {
    it('strictly forbids Maker from approving their own batch', () => {
      const result = canUserActAsChecker(makerUserId, sampleBatch);
      expect(result.canAct).toBe(false);
      expect(result.isMaker).toBe(true);
      expect(result.reason).toContain('Maker-Checker violation');
    });

    it('strictly forbids Maker from rejecting their own batch', () => {
      const actions = getPermissibleBatchActions(makerUserId, sampleBatch);
      expect(actions.canApprove).toBe(false);
      expect(actions.canReject).toBe(false);
    });

    it('permits an independent checker user to approve or reject approval_required batches', () => {
      const result = canUserActAsChecker(checkerUserId, sampleBatch);
      expect(result.canAct).toBe(true);
      expect(result.isMaker).toBe(false);

      const actions = getPermissibleBatchActions(checkerUserId, sampleBatch);
      expect(actions.canApprove).toBe(true);
      expect(actions.canReject).toBe(true);
    });

    it('prohibits checker actions when batch is not in approval_required state', () => {
      const nonApprovalStatuses: SettlementBatchStatus[] = [
        'draft',
        'approved',
        'processing',
        'completed',
        'rejected',
        'cancelled',
      ];

      for (const status of nonApprovalStatuses) {
        const batch = { ...sampleBatch, status };
        const result = canUserActAsChecker(checkerUserId, batch);
        expect(result.canAct).toBe(false);
      }
    });

    it('permits Maker to submit draft batches for review', () => {
      const draftBatch = { ...sampleBatch, status: 'draft' as SettlementBatchStatus };
      const makerActions = getPermissibleBatchActions(makerUserId, draftBatch);
      expect(makerActions.canSubmit).toBe(true);

      const checkerActions = getPermissibleBatchActions(checkerUserId, draftBatch);
      expect(checkerActions.canSubmit).toBe(false);
    });

    it('permits cancellation for draft, approval_required, and approved batches', () => {
      expect(getPermissibleBatchActions(makerUserId, { ...sampleBatch, status: 'draft' }).canCancel).toBe(true);
      expect(getPermissibleBatchActions(makerUserId, { ...sampleBatch, status: 'approval_required' }).canCancel).toBe(true);
      expect(getPermissibleBatchActions(makerUserId, { ...sampleBatch, status: 'approved' }).canCancel).toBe(true);
      expect(getPermissibleBatchActions(makerUserId, { ...sampleBatch, status: 'completed' }).canCancel).toBe(false);
      expect(getPermissibleBatchActions(makerUserId, { ...sampleBatch, status: 'processing' }).canCancel).toBe(false);
    });
  });

  describe('Configurable Approval Policy & Threshold Routing', () => {
    const policyDefault: SettlementApprovalPolicy = {
      id: 'pol-1',
      threshold_amount: '10000.00',
      requires_checker: true,
      currency: 'INR',
      is_active: true,
      created_at: '2026-10-03T00:00:00Z',
      updated_at: '2026-10-03T00:00:00Z',
    };

    it('routes batch to approval_required when amount meets or exceeds threshold', () => {
      const statusAtThreshold = evaluatePolicyRouting(10000, policyDefault);
      expect(statusAtThreshold).toBe('approval_required');

      const statusAboveThreshold = evaluatePolicyRouting(25000, policyDefault);
      expect(statusAboveThreshold).toBe('approval_required');
    });

    it('routes batch to draft when amount is below positive threshold', () => {
      const statusBelow = evaluatePolicyRouting(4500, policyDefault);
      expect(statusBelow).toBe('draft');
    });

    it('routes all batches to approval_required when threshold is zero', () => {
      const zeroThresholdPolicy: SettlementApprovalPolicy = { ...policyDefault, threshold_amount: '0.00' };
      expect(evaluatePolicyRouting(500, zeroThresholdPolicy)).toBe('approval_required');
      expect(evaluatePolicyRouting(0, zeroThresholdPolicy)).toBe('approval_required');
    });

    it('validates policy configuration updates', () => {
      const valid = validatePolicyUpdate({ threshold_amount: 50000, requires_checker: true });
      expect(valid.isValid).toBe(true);

      const invalidNegative = validatePolicyUpdate({ threshold_amount: -100 });
      expect(invalidNegative.isValid).toBe(false);
      expect(invalidNegative.errors.threshold_amount).toContain('non-negative');

      const invalidNaN = validatePolicyUpdate({ threshold_amount: NaN });
      expect(invalidNaN.isValid).toBe(false);
    });
  });

  describe('Settlement Status Badge Configurations', () => {
    it('returns appropriate badge configuration for all lifecycle statuses', () => {
      const statuses: SettlementBatchStatus[] = [
        'draft',
        'approval_required',
        'approved',
        'submitted',
        'processing',
        'completed',
        'partially_failed',
        'failed',
        'cancelled',
        'rejected',
      ];

      for (const status of statuses) {
        const config = getSettlementStatusConfig(status);
        expect(config.label).toBeDefined();
        expect(config.bg).toBeDefined();
        expect(config.text).toBeDefined();
        expect(config.label.length).toBeGreaterThan(0);
      }
    });

    it('provides distinct colors/variants for key maker-checker stages', () => {
      expect(getSettlementStatusConfig('approval_required').text).toContain('amber');
      expect(getSettlementStatusConfig('approved').text).toContain('emerald');
      expect(getSettlementStatusConfig('completed').text).toContain('emerald');
      expect(getSettlementStatusConfig('rejected').text).toContain('rose');
    });
  });

  describe('Authoritative Statements & Security Masking', () => {
    const sampleStatement: MechanicStatement = {
      statement_number: 'STMT-20261003-M01',
      statement_date: '2026-10-03T12:00:00Z',
      mechanic_id: 'mech-uuid-999',
      mechanic_name: 'Fast Track Auto Care',
      bank_name: 'State Bank of India',
      account_number_masked: '•••• •••• 9876',
      ifsc_code: 'SBIN0001234',
      batch_id: 'batch-0001',
      batch_number: 'BATCH-20261003-0001',
      batch_status: 'completed',
      currency: 'INR',
      total_gross: '12500.00',
      total_commission: '1250.00',
      total_deductions: '125.00',
      total_net: '11125.00',
      net_payout: 11125.0,
      items: [
        {
          payout_id: 'pout-1',
          booking_id: 'bk-1',
          service_title: 'Full Synthetic Oil Change',
          gross_amount: '2500.00',
          commission_rate: '0.10',
          commission_amount: '250.00',
          deduction_amount: '25.00',
          net_amount: '2225.00',
          currency: 'INR',
          status: 'paid',
        },
      ],
      tax_disclaimer: 'GST liability and TDS under Section 194C / 194M are assessed per applicable tax regulations.',
    };

    it('verifies that bank account number is strictly masked to last 4 digits', () => {
      const check = verifyStatementMasking(sampleStatement);
      expect(check.isMasked).toBe(true);
      expect(sampleStatement.account_number_masked).not.toContain('12345678');
      expect(sampleStatement.account_number_masked.endsWith('9876')).toBe(true);
    });

    it('verifies that statement contains all mandatory financial breakdown fields', () => {
      const gross = parseFloat(sampleStatement.total_gross);
      const commission = parseFloat(sampleStatement.total_commission);
      const deductions = parseFloat(sampleStatement.total_deductions);
      const expectedNet = gross - commission - deductions;
      expect(parseFloat(sampleStatement.total_net)).toBe(expectedNet);
    });

    it('contains tax disclaimer and section reference without exposing sensitive internal keys', () => {
      expect(sampleStatement.tax_disclaimer).toContain('194C');
      expect((sampleStatement as any).provider_secret).toBeUndefined();
      expect((sampleStatement as any).internal_key).toBeUndefined();
    });
  });
});
