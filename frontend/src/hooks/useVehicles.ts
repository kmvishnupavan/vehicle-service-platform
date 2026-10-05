import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../lib/api';
import {
  CustomerVehicle,
  VehicleBrand,
  VehicleCreatePayload,
  VehicleModel,
  VehicleType,
} from '../types/customerBooking';

export const vehicleKeys = {
  all: ['vehicles'] as const,
  myVehicles: () => [...vehicleKeys.all, 'my-vehicles'] as const,
  types: () => [...vehicleKeys.all, 'types'] as const,
  makes: () => [...vehicleKeys.all, 'makes'] as const,
  models: (brandId?: string) => [...vehicleKeys.all, 'models', brandId || ''] as const,
};

export function useMyVehicles() {
  return useQuery<CustomerVehicle[]>({
    queryKey: vehicleKeys.myVehicles(),
    queryFn: () => api.get<CustomerVehicle[]>('/vehicles/my-vehicles'),
    staleTime: 30_000,
  });
}

export function useVehicleTypes() {
  return useQuery<VehicleType[]>({
    queryKey: vehicleKeys.types(),
    queryFn: () => api.get<VehicleType[]>('/vehicles/types'),
    staleTime: 60_000 * 5,
  });
}

export function useVehicleMakes() {
  return useQuery<VehicleBrand[]>({
    queryKey: vehicleKeys.makes(),
    queryFn: () => api.get<VehicleBrand[]>('/vehicles/makes'),
    staleTime: 60_000 * 5,
  });
}

export function useBrandModels(brandId?: string) {
  return useQuery<VehicleModel[]>({
    queryKey: vehicleKeys.models(brandId),
    queryFn: () => api.get<VehicleModel[]>(`/vehicles/models/${brandId}`),
    enabled: Boolean(brandId),
    staleTime: 60_000 * 5,
  });
}

export function useCreateVehicle() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: VehicleCreatePayload) =>
      api.post<CustomerVehicle>('/vehicles', payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: vehicleKeys.myVehicles() });
    },
  });
}
