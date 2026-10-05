import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { bookingKeys } from './useBookings';

export interface PaymentOrderResponse {
  order_id: string;
  amount: number;
  currency: string;
  key_id: string;
  booking_id: string;
}

export interface PaymentVerifyPayload {
  booking_id: string;
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

export interface PaymentVerifyResponse {
  status: string;
  message: string;
  booking_id: string;
  payment_id: string;
  transaction_id?: string | null;
}

export interface InvoiceDetail {
  id: string;
  invoice_number: string;
  booking_id: string;
  customer_id: string;
  subtotal: string | number;
  tax: string | number;
  discount: string | number;
  total: string | number;
  status: string;
  issued_at: string;
}

export function useCreatePaymentOrder() {
  return useMutation({
    mutationFn: (bookingId: string) =>
      api.post<PaymentOrderResponse>('/payments/create-order', { booking_id: bookingId }),
  });
}

export function useVerifyPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PaymentVerifyPayload) =>
      api.post<PaymentVerifyResponse>('/payments/verify', payload),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: bookingKeys.detail(variables.booking_id) });
      queryClient.invalidateQueries({ queryKey: bookingKeys.lists() });
    },
  });
}

export function useBookingInvoice(bookingId?: string) {
  return useQuery<InvoiceDetail>({
    queryKey: ['payments', 'invoice', bookingId || ''],
    queryFn: () => {
      if (!bookingId) throw new Error('Missing booking ID');
      return api.get<InvoiceDetail>(`/payments/booking/${bookingId}/invoice`);
    },
    enabled: Boolean(bookingId),
    staleTime: 60_000 * 5,
  });
}
