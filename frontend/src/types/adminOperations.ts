/**
 * Phase 9 — Admin Operations, Reconciliation & Audit Viewer Types.
 */

export interface SystemHealthCheck {
  status: string;
  environment: string;
  checks: Record<string, string>;
  timestamp: string;
}

export interface SafetyGuardStatus {
  environment: string;
  live_payouts_enabled: boolean;
  payout_mode: 'sandbox' | 'live';
  safety_barrier_active: boolean;
  real_money_movement: string;
}

export interface AdminSystemStats {
  environment: string;
  system_health: SystemHealthCheck;
  safety_guard: SafetyGuardStatus;
  bookings_breakdown: Record<string, number>;
  payments_breakdown: Record<string, number>;
  payouts_breakdown: Record<string, number>;
  webhooks_breakdown: Record<string, number>;
  notifications_breakdown: Record<string, number>;
  timestamp: string;
}

export interface ReconciliationDiscrepancy {
  id?: string;
  entity_type: string;
  entity_id?: string | null;
  provider_reference?: string | null;
  internal_status?: string | null;
  provider_status?: string | null;
  discrepancy_type: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  details: Record<string, unknown>;
  detected_at: string;
  resolution_status: 'open' | 'acknowledged' | 'resolved' | 'ignored';
}

export interface ReconciliationReport {
  subsystem: string;
  discrepancies: ReconciliationDiscrepancy[];
  count: number;
  scanned_at: string;
}

export interface AuditLogItem {
  id: string;
  actor_id?: string | null;
  actor_role?: string | null;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  old_data?: Record<string, unknown> | null;
  new_data?: Record<string, unknown> | null;
  ip_address?: string | null;
  request_id?: string | null;
  severity: string;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogItem[];
  total: number;
  limit: number;
  offset: number;
}
