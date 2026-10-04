/**
 * TanStack React Query Hooks for Reviews and Ratings (Phase 8.5).
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../lib/api';
import { MechanicReviewsList, Review, ReviewSubmissionPayload } from '../types/review';
import { bookingKeys } from './useBookings';

export const reviewKeys = {
  all: ['reviews'] as const,
  booking: (bookingId: string) => [...reviewKeys.all, 'booking', bookingId] as const,
  mechanic: (mechanicId: string, limit: number, offset: number) =>
    [...reviewKeys.all, 'mechanic', mechanicId, limit, offset] as const,
};

export function useBookingReview(bookingId: string | undefined) {
  return useQuery<Review | null>({
    queryKey: reviewKeys.booking(bookingId || ''),
    queryFn: async () => {
      if (!bookingId) return null;
      try {
        return await api.get<Review>(`/bookings/${bookingId}/review`);
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    enabled: Boolean(bookingId),
    staleTime: 30_000,
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 404) return false;
      return failureCount < 2;
    },
  });
}

export function useSubmitReview() {
  const queryClient = useQueryClient();

  return useMutation<Review, ApiError, { bookingId: string; payload: ReviewSubmissionPayload }>({
    mutationFn: async ({ bookingId, payload }) => {
      return api.post<Review>(`/bookings/${bookingId}/review`, payload);
    },
    onSuccess: (data, variables) => {
      queryClient.setQueryData(reviewKeys.booking(variables.bookingId), data);
      queryClient.invalidateQueries({ queryKey: reviewKeys.booking(variables.bookingId) });
      queryClient.invalidateQueries({ queryKey: bookingKeys.detail(variables.bookingId) });
      queryClient.invalidateQueries({ queryKey: bookingKeys.lists() });
      if (data.mechanic_id) {
        queryClient.invalidateQueries({ queryKey: [...reviewKeys.all, 'mechanic', data.mechanic_id] });
      }
    },
  });
}

export function useMechanicReviews(mechanicId: string | undefined, limit: number = 20, offset: number = 0) {
  return useQuery<MechanicReviewsList>({
    queryKey: reviewKeys.mechanic(mechanicId || '', limit, offset),
    queryFn: async () => {
      if (!mechanicId) throw new Error('Missing mechanic ID');
      return api.get<MechanicReviewsList>(`/mechanics/${mechanicId}/reviews?limit=${limit}&offset=${offset}`);
    },
    enabled: Boolean(mechanicId),
    staleTime: 30_000,
  });
}
