/**
 * TanStack React Query Hooks for Admin Settlement Maker-Checker (Phase 8.9).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../lib/api';
import {
  SettlementBatchItem,
  SettlementBatchListResponse,
  SettlementApprovalPolicy,
} from '../types/settlement';

export const adminSettlementKeys = {
  all: ['admin-settlements'] as const,
  list: (status?: string, limit?: number, offset?: number) =>
    [...adminSettlementKeys.all, 'list', { status, limit, offset }] as const,
  detail: (id: string) => [...adminSettlementKeys.all, 'detail', id] as const,
  policy: () => [...adminSettlementKeys.all, 'policy'] as const,
};

export function useAdminSettlements(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}) {
  return useQuery<SettlementBatchListResponse>({
    queryKey: adminSettlementKeys.list(params?.status, params?.limit, params?.offset),
    queryFn: async () => {
      const q = new URLSearchParams();
      if (params?.status && params.status !== 'all') q.append('status', params.status);
      if (params?.limit) q.append('limit', String(params.limit));
      if (params?.offset !== undefined) q.append('offset', String(params.offset));
      const queryStr = q.toString() ? `?${q.toString()}` : '';
      return await api.get<SettlementBatchListResponse>(`/admin/settlements${queryStr}`);
    },
    staleTime: 15_000,
  });
}

export function useAdminSettlementDetail(batchId: string | null) {
  return useQuery<SettlementBatchItem | null>({
    queryKey: adminSettlementKeys.detail(batchId || ''),
    queryFn: async () => {
      if (!batchId) return null;
      return await api.get<SettlementBatchItem>(`/admin/settlements/${batchId}`);
    },
    enabled: Boolean(batchId),
  });
}

export function useSettlementPolicy() {
  return useQuery<SettlementApprovalPolicy>({
    queryKey: adminSettlementKeys.policy(),
    queryFn: async () => {
      return await api.get<SettlementApprovalPolicy>('/admin/settlements/policy');
    },
    staleTime: 60_000,
  });
}

export function useUpdateSettlementPolicy() {
  const queryClient = useQueryClient();

  return useMutation<
    SettlementApprovalPolicy,
    ApiError,
    { threshold_amount?: number; requires_checker?: boolean; is_active?: boolean }
  >({
    mutationFn: async (payload) => {
      return await api.patch<SettlementApprovalPolicy>('/admin/settlements/policy', payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.policy() });
    },
  });
}

export function useCreateSettlementBatch() {
  const queryClient = useQueryClient();

  return useMutation<SettlementBatchItem, ApiError, { payout_ids?: string[] } | void>({
    mutationFn: async (payload) => {
      return await api.post<SettlementBatchItem>('/admin/settlements', payload || {});
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.all });
    },
  });
}

export function useSubmitSettlementBatch() {
  const queryClient = useQueryClient();

  return useMutation<SettlementBatchItem, ApiError, { batchId: string }>({
    mutationFn: async ({ batchId }) => {
      return await api.post<SettlementBatchItem>(
        `/admin/settlements/${batchId}/submit-for-approval`
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.all });
    },
  });
}

export function useApproveSettlementBatch() {
  const queryClient = useQueryClient();

  return useMutation<SettlementBatchItem, ApiError, { batchId: string; reason?: string }>({
    mutationFn: async ({ batchId, reason }) => {
      return await api.post<SettlementBatchItem>(`/admin/settlements/${batchId}/approve`, {
        reason,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.all });
    },
  });
}

export function useRejectSettlementBatch() {
  const queryClient = useQueryClient();

  return useMutation<SettlementBatchItem, ApiError, { batchId: string; reason?: string }>({
    mutationFn: async ({ batchId, reason }) => {
      return await api.post<SettlementBatchItem>(`/admin/settlements/${batchId}/reject`, {
        reason,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.all });
    },
  });
}

export function useCancelSettlementBatch() {
  const queryClient = useQueryClient();

  return useMutation<SettlementBatchItem, ApiError, { batchId: string; reason?: string }>({
    mutationFn: async ({ batchId, reason }) => {
      return await api.post<SettlementBatchItem>(`/admin/settlements/${batchId}/cancel`, {
        reason,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: adminSettlementKeys.all });
    },
  });
}
