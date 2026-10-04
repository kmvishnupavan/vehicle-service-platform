/**
 * TanStack React Query Hooks for Admin Operations, Reconciliation & Audit Logs (Phase 9).
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  AdminSystemStats,
  ReconciliationReport,
  AuditLogListResponse,
} from '../types/adminOperations';

export const adminOpKeys = {
  all: ['admin-operations'] as const,
  stats: () => [...adminOpKeys.all, 'stats'] as const,
  reconciliation: (subsystem: string) => [...adminOpKeys.all, 'reconciliation', subsystem] as const,
  auditLogs: (params?: Record<string, unknown>) => [...adminOpKeys.all, 'audit-logs', params] as const,
};

export function useOperationsStats() {
  return useQuery<AdminSystemStats>({
    queryKey: adminOpKeys.stats(),
    queryFn: async () => {
      return await api.get<AdminSystemStats>('/admin/operations/stats');
    },
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}

export function useReconciliationReport(subsystem: 'payments' | 'payouts' | 'settlements' | 'webhooks') {
  return useQuery<ReconciliationReport>({
    queryKey: adminOpKeys.reconciliation(subsystem),
    queryFn: async () => {
      return await api.get<ReconciliationReport>(`/admin/reconciliation/${subsystem}`);
    },
    staleTime: 30_000,
  });
}

export function useAuditLogs(params?: {
  actor_id?: string;
  action?: string;
  entity_type?: string;
  request_id?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery<AuditLogListResponse>({
    queryKey: adminOpKeys.auditLogs(params),
    queryFn: async () => {
      const q = new URLSearchParams();
      if (params?.actor_id) q.append('actor_id', params.actor_id);
      if (params?.action) q.append('action', params.action);
      if (params?.entity_type) q.append('entity_type', params.entity_type);
      if (params?.request_id) q.append('request_id', params.request_id);
      if (params?.limit) q.append('limit', String(params.limit));
      if (params?.offset !== undefined) q.append('offset', String(params.offset));
      const queryStr = q.toString() ? `?${q.toString()}` : '';
      return await api.get<AuditLogListResponse>(`/admin/audit-logs${queryStr}`);
    },
    staleTime: 15_000,
  });
}
