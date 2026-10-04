/**
 * Settlement Management & Maker-Checker Types (Phase 8.9).
 */

export type SettlementBatchStatus =
  | 'draft'
  | 'approval_required'
  | 'approved'
  | 'rejected'
  | 'submitted'
  | 'processing'
  | 'completed'
  | 'partially_failed'
  | 'failed'
  | 'cancelled';

export interface SettlementApprovalRecord {
  id: string;
  settlement_batch_id: string;
  action: 'submitted_for_approval' | 'approved' | 'rejected' | 'cancelled';
  actor_id: string;
  actor_role: string;
  reason?: string | null;
  created_at: string;
}

export interface SettlementBatchItem {
  id: string;
  batch_number: string;
  provider: string;
  status: SettlementBatchStatus;
  total_amount: string;
  currency: string;
  item_count: number;
  provider_batch_id?: string | null;
  error_details?: Record<string, unknown> | null;
  submitted_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  created_by?: string | null;
  approvals?: SettlementApprovalRecord[];
}

export interface SettlementBatchListResponse {
  items: SettlementBatchItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface SettlementApprovalPolicy {
  id: string;
  threshold_amount: string;
  currency: string;
  requires_checker: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StatementItem {
  payout_id: string;
  booking_id: string;
  booking_number?: string | null;
  service_title?: string | null;
  gross_amount: string;
  commission_rate: string;
  commission_amount: string;
  deduction_amount: string;
  net_amount: string;
  currency: string;
  status: string;
  settled_at?: string | null;
}

export interface MechanicStatement {
  statement_number: string;
  statement_date: string;
  mechanic_id: string;
  mechanic_name: string;
  bank_name?: string | null;
  account_number_masked: string;
  ifsc_code?: string | null;
  batch_id: string;
  batch_number: string;
  batch_status: string;
  currency: string;
  total_gross: string;
  total_commission: string;
  total_deductions: string;
  total_net: string;
  net_payout?: number | null;
  items: StatementItem[];
  tax_disclaimer: string;
}
