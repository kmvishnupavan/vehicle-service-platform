import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import { AddressCreatePayload, CustomerAddress } from '../types/customerBooking';

export const addressKeys = {
  all: ['addresses'] as const,
  list: () => [...addressKeys.all, 'list'] as const,
};

export function useMyAddresses() {
  return useQuery<CustomerAddress[]>({
    queryKey: addressKeys.list(),
    queryFn: () => api.get<CustomerAddress[]>('/addresses'),
    staleTime: 60_000,
  });
}

export function useCreateAddress() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AddressCreatePayload) =>
      api.post<CustomerAddress>('/addresses', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: addressKeys.list() });
    },
  });
}
