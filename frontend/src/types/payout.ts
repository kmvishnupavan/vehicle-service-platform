/**
 * Mechanic Payout Ledger & Settlement Foundation TypeScript Interfaces (Phase 8.7).
 */

export type PayoutStatus =
  | 'pending'
  | 'eligible'
  | 'processing'
  | 'paid'
  | 'failed'
  | 'reversed'
  | 'cancelled';

export interface PayoutItem {
  id: string;
  booking_id: string;
  mechanic_id: string;
  booking_number?: string | null;
  payment_id?: string | null;
  payment_transaction_id?: string | null;

  gross_amount: string;
  commission_rate: string;
  commission_amount: string;
  deduction_amount: string;
  net_amount: string;

  currency: string;
  status: PayoutStatus;

  created_at: string;
  updated_at: string;
  eligible_at?: string | null;
  settled_at?: string | null;
  reversed_at?: string | null;

  provider: string;
  provider_payout_id?: string | null;
  failure_reason?: string | null;
  metadata?: Record<string, any>;
}

export interface PayoutListResponse {
  items: PayoutItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface PayoutSummary {
  total_gross: string;
  total_commission: string;
  total_deductions: string;
  total_net: string;

  pending_amount: string;
  eligible_amount: string;
  processing_amount: string;
  paid_amount: string;
  reversed_amount: string;

  currency: string;
}

export interface PayoutFilterParams {
  fromDate?: string;
  toDate?: string;
  status?: string;
  limit?: number;
  offset?: number;
}
