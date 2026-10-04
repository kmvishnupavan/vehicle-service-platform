/**
 * TanStack React Query Hooks for Mechanic Payout Accounts & Settlements (Phase 8.8).
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../lib/api';
import {
  PayoutAccount,
  PayoutAccountCreatePayload,
  SettlementHistoryItem,
} from '../types/payoutAccount';

export const payoutAccountKeys = {
  all: ['mechanic-payout-account'] as const,
  detail: () => [...payoutAccountKeys.all, 'detail'] as const,
  settlements: (params?: { limit?: number; offset?: number }) =>
    ['mechanic-settlements', params] as const,
};

export function usePayoutAccount() {
  return useQuery<PayoutAccount | null>({
    queryKey: payoutAccountKeys.detail(),
    queryFn: async () => {
      try {
        return await api.get<PayoutAccount>('/mechanics/payout-account');
      } catch (err: any) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    staleTime: 30_000,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}

export function useSavePayoutAccount() {
  const queryClient = useQueryClient();

  return useMutation<PayoutAccount, ApiError, PayoutAccountCreatePayload>({
    mutationFn: async (payload: PayoutAccountCreatePayload) => {
      return await api.post<PayoutAccount>('/mechanics/payout-account', payload);
    },
    onSuccess: (data) => {
      queryClient.setQueryData(payoutAccountKeys.detail(), data);
      queryClient.invalidateQueries({ queryKey: payoutAccountKeys.all });
    },
  });
}

export function useVerifyPayoutAccount() {
  const queryClient = useQueryClient();

  return useMutation<PayoutAccount, ApiError, void>({
    mutationFn: async () => {
      return await api.post<PayoutAccount>('/mechanics/payout-account/verification');
    },
    onSuccess: (data) => {
      queryClient.setQueryData(payoutAccountKeys.detail(), data);
      queryClient.invalidateQueries({ queryKey: payoutAccountKeys.all });
    },
  });
}

export function useSettlementHistory(params: { limit?: number; offset?: number } = {}) {
  const limit = params.limit ?? 20;
  const offset = params.offset ?? 0;

  return useQuery<SettlementHistoryItem[]>({
    queryKey: payoutAccountKeys.settlements({ limit, offset }),
    queryFn: async () => {
      const q = new URLSearchParams();
      q.append('limit', String(limit));
      q.append('offset', String(offset));
      return await api.get<SettlementHistoryItem[]>(`/mechanics/settlements?${q.toString()}`);
    },
    staleTime: 30_000,
  });
}
