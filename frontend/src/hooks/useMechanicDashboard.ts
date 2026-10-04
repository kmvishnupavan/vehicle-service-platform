/**
 * TanStack React Query Hooks for Mechanic Performance, Earnings & Dashboard (Phase 8.6).
 *
 * Provides query hooks for:
 * - Overview KPIs (Today, Active, Completed, Earnings, Ratings)
 * - Performance metrics (Completion rate, rating distribution, monthly breakdown)
 * - Paginated earnings breakdown with date & status filters
 * - Recent jobs and reviews with privacy preservation
 */

import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  DashboardOverview,
  EarningsList,
  MechanicPerformance,
  RecentJobsList,
  RecentReviewsList,
} from '../types/mechanic-dashboard';

export const mechanicDashboardKeys = {
  all: ['mechanic-dashboard'] as const,
  overview: () => [...mechanicDashboardKeys.all, 'overview'] as const,
  performance: (filters: { fromDate?: string; toDate?: string }) =>
    [...mechanicDashboardKeys.all, 'performance', filters] as const,
  earnings: (filters: { fromDate?: string; toDate?: string; status?: string; limit?: number; offset?: number }) =>
    [...mechanicDashboardKeys.all, 'earnings', filters] as const,
  recentJobs: (limit: number, offset: number) =>
    [...mechanicDashboardKeys.all, 'recent-jobs', limit, offset] as const,
  recentReviews: (limit: number, offset: number) =>
    [...mechanicDashboardKeys.all, 'recent-reviews', limit, offset] as const,
};

export function useMechanicDashboardOverview() {
  return useQuery<DashboardOverview>({
    queryKey: mechanicDashboardKeys.overview(),
    queryFn: async () => {
      return await api.get<DashboardOverview>('/mechanics/dashboard/overview');
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicPerformance(filters: { fromDate?: string; toDate?: string } = {}) {
  return useQuery<MechanicPerformance>({
    queryKey: mechanicDashboardKeys.performance(filters),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.fromDate) params.append('from_date', filters.fromDate);
      if (filters.toDate) params.append('to_date', filters.toDate);
      const queryStr = params.toString() ? `?${params.toString()}` : '';
      return await api.get<MechanicPerformance>(`/mechanics/dashboard/performance${queryStr}`);
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicEarnings(
  filters: {
    fromDate?: string;
    toDate?: string;
    status?: string;
    limit?: number;
    offset?: number;
  } = {}
) {
  const limit = filters.limit ?? 20;
  const offset = filters.offset ?? 0;

  return useQuery<EarningsList>({
    queryKey: mechanicDashboardKeys.earnings({ ...filters, limit, offset }),
    queryFn: async () => {
      const params = new URLSearchParams();
      if (filters.fromDate) params.append('from_date', filters.fromDate);
      if (filters.toDate) params.append('to_date', filters.toDate);
      if (filters.status && filters.status !== 'all') params.append('status', filters.status);
      params.append('limit', String(limit));
      params.append('offset', String(offset));

      return await api.get<EarningsList>(`/mechanics/dashboard/earnings?${params.toString()}`);
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicRecentJobs(limit: number = 10, offset: number = 0) {
  return useQuery<RecentJobsList>({
    queryKey: mechanicDashboardKeys.recentJobs(limit, offset),
    queryFn: async () => {
      return await api.get<RecentJobsList>(
        `/mechanics/dashboard/recent-jobs?limit=${limit}&offset=${offset}`
      );
    },
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  });
}

export function useMechanicRecentReviews(limit: number = 10, offset: number = 0) {
  return useQuery<RecentReviewsList>({
    queryKey: mechanicDashboardKeys.recentReviews(limit, offset),
    queryFn: async () => {
      return await api.get<RecentReviewsList>(
        `/mechanics/dashboard/recent-reviews?limit=${limit}&offset=${offset}`
      );
    },
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
}
