import { useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { bookingKeys } from './useBookings';
import { BookingCreatePayload } from '../types/customerBooking';
import { Booking } from '../types/booking';

export function useCreateBooking() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (payload: BookingCreatePayload) => {
      // 1. Create booking authoritatively via FastAPI backend
      const booking = await api.post<Booking>('/bookings', payload);

      // 2. Automatically trigger matching dispatch if booking successfully initialized
      try {
        await api.post(`/matching/dispatch/${booking.id}`);
      } catch {
        // If matching has no candidates or dispatch encounters a temporary delay,
        // the booking remains in 'pending' / 'searching_mechanic' safely.
      }

      return booking;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bookingKeys.lists() });
    },
  });
}
