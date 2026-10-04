import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  ScheduledBooking,
  ScheduleBookingRequest,
  BackgroundJobExecutionSummary,
  MatchingPolicy,
  LocationAnomaly,
  OperationalMetrics,
} from '../types/operationalAutomation';

export function useOperationalMetrics() {
  return useQuery<OperationalMetrics>({
    queryKey: ['operational-metrics'],
    queryFn: async () => {
      return await api.get<OperationalMetrics>('/admin/operational-metrics');
    },
    refetchInterval: 15000,
  });
}

export function useBackgroundJobHistory(limit: number = 20) {
  return useQuery<BackgroundJobExecutionSummary[]>({
    queryKey: ['background-jobs-history', limit],
    queryFn: async () => {
      return await api.get<BackgroundJobExecutionSummary[]>(`/admin/background-jobs/history?limit=${limit}`);
    },
    refetchInterval: 10000,
  });
}

export function useTriggerBackgroundJobs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (jobNames?: string[]) => {
      return await api.post<Record<string, any>[]>('/admin/background-jobs/run', {
        job_names: jobNames || null,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['background-jobs-history'] });
      queryClient.invalidateQueries({ queryKey: ['operational-metrics'] });
    },
  });
}

export function useLocationAnomalies(limit: number = 30) {
  return useQuery<LocationAnomaly[]>({
    queryKey: ['location-anomalies', limit],
    queryFn: async () => {
      return await api.get<LocationAnomaly[]>(`/admin/location-anomalies?limit=${limit}`);
    },
    refetchInterval: 20000,
  });
}

export function useMatchingPolicies() {
  return useQuery<MatchingPolicy[]>({
    queryKey: ['matching-policies'],
    queryFn: async () => {
      return await api.get<MatchingPolicy[]>('/admin/matching-policies');
    },
  });
}

export function useActivateMatchingPolicy() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (version: string) => {
      return await api.post<MatchingPolicy>(`/admin/matching-policies/${version}/activate`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['matching-policies'] });
    },
  });
}

export function useAdminScheduledBookings(statusFilter?: string) {
  return useQuery<ScheduledBooking[]>({
    queryKey: ['admin-scheduled-bookings', statusFilter],
    queryFn: async () => {
      const url = statusFilter
        ? `/admin/scheduled-bookings?status_filter=${encodeURIComponent(statusFilter)}`
        : '/admin/scheduled-bookings';
      return await api.get<ScheduledBooking[]>(url);
    },
    refetchInterval: 15000,
  });
}

export function useMechanicScheduledJobs() {
  return useQuery<any[]>({
    queryKey: ['mechanic-scheduled-jobs'],
    queryFn: async () => {
      return await api.get<any[]>('/mechanics/scheduled-jobs');
    },
    refetchInterval: 20000,
  });
}

export function useScheduledBooking(bookingId?: string) {
  return useQuery<ScheduledBooking | null>({
    queryKey: ['scheduled-booking', bookingId],
    queryFn: async () => {
      if (!bookingId) return null;
      try {
        return await api.get<ScheduledBooking>(`/bookings/${bookingId}/schedule`);
      } catch {
        return null;
      }
    },
    enabled: !!bookingId,
  });
}

export function useScheduleBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      bookingId,
      data,
    }: {
      bookingId: string;
      data: ScheduleBookingRequest;
    }) => {
      return await api.post<ScheduledBooking>(`/bookings/${bookingId}/schedule`, data);
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-booking', vars.bookingId] });
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
      queryClient.invalidateQueries({ queryKey: ['my-bookings'] });
    },
  });
}

export function useCancelScheduledBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      bookingId,
      reason,
    }: {
      bookingId: string;
      reason?: string;
    }) => {
      const q = reason ? `?reason=${encodeURIComponent(reason)}` : '';
      return await api.delete(`/bookings/${bookingId}/schedule${q}`);
    },
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-booking', vars.bookingId] });
      queryClient.invalidateQueries({ queryKey: ['bookings'] });
      queryClient.invalidateQueries({ queryKey: ['my-bookings'] });
    },
  });
}
