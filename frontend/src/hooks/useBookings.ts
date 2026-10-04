/**
 * TanStack Query Hooks for Bookings & Mechanic Locations.
 */

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { Booking, MechanicLocationRestResponse } from '../types/booking';

export const bookingKeys = {
  all: ['bookings'] as const,
  lists: () => [...bookingKeys.all, 'list'] as const,
  detail: (id: string) => [...bookingKeys.all, 'detail', id] as const,
  mechanicLocation: (id: string) => [...bookingKeys.all, 'mechanicLocation', id] as const,
};

export function useMyBookings() {
  return useQuery<Booking[]>({
    queryKey: bookingKeys.lists(),
    queryFn: async () => {
      return api.get<Booking[]>('/bookings');
    },
    staleTime: 30_000,
  });
}

export function useBooking(bookingId: string | undefined) {
  return useQuery<Booking>({
    queryKey: bookingKeys.detail(bookingId || ''),
    queryFn: async () => {
      if (!bookingId) throw new Error('Missing booking ID');
      return api.get<Booking>(`/bookings/${bookingId}`);
    },
    enabled: Boolean(bookingId),
    staleTime: 15_000,
  });
}

export function useMechanicLocation(bookingId: string | undefined) {
  return useQuery<MechanicLocationRestResponse>({
    queryKey: bookingKeys.mechanicLocation(bookingId || ''),
    queryFn: async () => {
      if (!bookingId) throw new Error('Missing booking ID');
      return api.get<MechanicLocationRestResponse>(`/bookings/${bookingId}/mechanic-location`);
    },
    enabled: Boolean(bookingId),
    staleTime: 10_000,
    retry: 1,
  });
}

export function useInvalidateBooking() {
  const queryClient = useQueryClient();
  return (bookingId: string) => {
    queryClient.invalidateQueries({ queryKey: bookingKeys.detail(bookingId) });
    queryClient.invalidateQueries({ queryKey: bookingKeys.mechanicLocation(bookingId) });
  };
}
