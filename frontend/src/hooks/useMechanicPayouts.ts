/**
 * TanStack React Query Hooks for Mechanic Payout Ledger & Settlement (Phase 8.7).
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  PayoutFilterParams,
  PayoutItem,
  PayoutListResponse,
  PayoutSummary,
} from '../types/payout';

export const mechanicPayoutKeys = {
  all: ['mechanic-payouts'] as const,
  summary: () => [...mechanicPayoutKeys.all, 'summary'] as const,
  list: (filters: PayoutFilterParams) =>
    [...mechanicPayoutKeys.all, 'list', filters] as const,
  detail: (id: string) => [...mechanicPayoutKeys.all, 'detail', id] as const,
};

export function useMechanicPayoutSummary() {
  return useQuery<PayoutSummary>({
    queryKey: mechanicPayoutKeys.summary(),
    queryFn: async () => {
      return await api.get<PayoutSummary>('/mechanics/payouts/summary');
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicPayouts(filters: PayoutFilterParams = {}) {
  const limit = filters.limit ?? 10;
  const offset = filters.offset ?? 0;

  return useQuery<PayoutListResponse>({
    queryKey: mechanicPayoutKeys.list({ ...filters, limit, offset }),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.fromDate) params.append('from_date', filters.fromDate);
      if (filters.toDate) params.append('to_date', filters.toDate);
      if (filters.status && filters.status !== 'all') params.append('status', filters.status);
      params.append('limit', String(limit));
      params.append('offset', String(offset));

      return await api.get<PayoutListResponse>(`/mechanics/payouts?${params.toString()}`);
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicPayoutDetail(payoutId?: string) {
  return useQuery<PayoutItem>({
    queryKey: mechanicPayoutKeys.detail(payoutId || ''),
    queryFn: async () => {
      if (!payoutId) throw new Error('Payout ID is required');
      return await api.get<PayoutItem>(`/mechanics/payouts/${payoutId}`);
    },
    enabled: Boolean(payoutId),
    staleTime: 60_000,
  });
}
