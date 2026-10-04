/**
 * Mechanic Payout Account & Settlement Batch TypeScript Interfaces (Phase 8.8).
 */

export type PayoutAccountVerificationStatus =
  | 'not_configured'
  | 'pending'
  | 'submitted'
  | 'verified'
  | 'failed'
  | 'suspended';

export interface PayoutAccount {
  id: string;
  mechanic_id: string;
  provider: string;
  provider_account_id?: string | null;
  account_holder_name: string;
  bank_name?: string | null;
  account_number_masked: string;
  ifsc_code?: string | null;
  verification_status: PayoutAccountVerificationStatus;
  verification_details?: Record<string, any> | null;
  verified_at?: string | null;
  is_active: boolean;
  is_primary: boolean;
  created_at: string;
  updated_at: string;
}

export interface PayoutAccountCreatePayload {
  account_holder_name: string;
  account_number: string;
  ifsc_code: string;
  bank_name?: string;
}

export interface PayoutAccountUpdatePayload {
  account_holder_name?: string;
  account_number?: string;
  ifsc_code?: string;
  bank_name?: string;
}

export interface SettlementHistoryItem {
  id: string;
  booking_id: string;
  booking_number?: string | null;
  net_amount: string;
  currency: string;
  status: string;
  provider_payout_id?: string | null;
  settlement_batch_id?: string | null;
  batch_number?: string | null;
  batch_status?: string | null;
  created_at: string;
  eligible_at?: string | null;
  settled_at?: string | null;
  failure_reason?: string | null;
}
